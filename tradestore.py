"""
Stores trades in SQLite and runs the analytics a market-data team would want.

Why SQL here: trades are rows with a fixed shape, and questions like
"volume-weighted average price" or "volume per trader" are one GROUP BY away.
"""

from __future__ import annotations

import sqlite3

from orderbook import Trade

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id  INTEGER PRIMARY KEY,
    trader    TEXT NOT NULL,
    side      TEXT NOT NULL CHECK (side IN ('BUY', 'SELL'))
);
CREATE TABLE IF NOT EXISTS trades (
    trade_id       INTEGER PRIMARY KEY,
    buy_order_id   INTEGER NOT NULL REFERENCES orders(order_id),
    sell_order_id  INTEGER NOT NULL REFERENCES orders(order_id),
    price          REAL    NOT NULL CHECK (price > 0),
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    ts             INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trades_ts ON trades(ts);
"""


class TradeStore:
    def __init__(self, path: str = ":memory:") -> None:
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)

    def record_order(self, order_id: int, trader: str, side: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO orders (order_id, trader, side) VALUES (?, ?, ?)",
            (order_id, trader, side),
        )

    def record_trades(self, trades: list[Trade]) -> None:
        # Parameterised queries (the ? marks) stop SQL injection.
        self.conn.executemany(
            "INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?)",
            [(t.trade_id, t.buy_order_id, t.sell_order_id, t.price, t.quantity, t.timestamp)
             for t in trades],
        )
        self.conn.commit()

    def vwap(self) -> float | None:
        """Volume-weighted average price: sum(price x qty) / sum(qty)."""
        row = self.conn.execute(
            "SELECT SUM(price * quantity) * 1.0 / SUM(quantity) FROM trades"
        ).fetchone()
        return None if row[0] is None else round(row[0], 4)

    def summary(self) -> dict[str, float]:
        count, volume, high, low = self.conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(quantity), 0), MAX(price), MIN(price) FROM trades"
        ).fetchone()
        return {"trades": count, "volume": volume, "high": high, "low": low, "vwap": self.vwap()}

    def volume_by_trader(self) -> list[tuple[str, int]]:
        """Each trade has a buyer and a seller, so count both sides with UNION ALL, then group."""
        return self.conn.execute(
            """
            SELECT o.trader, SUM(t.quantity) AS traded
            FROM (
                SELECT buy_order_id  AS order_id, quantity FROM trades
                UNION ALL
                SELECT sell_order_id AS order_id, quantity FROM trades
            ) AS t
            JOIN orders AS o ON o.order_id = t.order_id
            GROUP BY o.trader
            ORDER BY traded DESC, o.trader
            """
        ).fetchall()
