"""
Replays a CSV of orders through the book and prints a market-data feed.

Usage:
    python replay.py sample_orders.csv
    python replay.py sample_orders.csv --db trades.db

CSV columns: action,side,quantity,price,trader,ref
  action = NEW or CANCEL. For CANCEL, ref is the line number (1-based, data rows only)
  of the NEW order to cancel. Leave price empty for a market order.
"""

from __future__ import annotations

import argparse
import csv

from orderbook import OrderBook
from tradestore import TradeStore


def fmt(x: float | None) -> str:
    return "-" if x is None else f"{x:.2f}"


def replay(path: str, db: str = ":memory:", quiet: bool = False) -> tuple[OrderBook, TradeStore]:
    book, store = OrderBook("DEMO"), TradeStore(db)
    line_to_order: dict[int, int] = {}

    with open(path, newline="") as f:
        for line_no, row in enumerate(csv.DictReader(f), start=1):
            action = row["action"].strip().upper()
            if action == "CANCEL":
                target = line_to_order.get(int(row["ref"]))
                ok = target is not None and book.cancel(target)
                event = f"CANCEL line {row['ref']} -> {'ok' if ok else 'not found'}"
            else:
                price = float(row["price"]) if row["price"].strip() else None
                order, trades = book.submit(row["side"].strip().upper(), int(row["quantity"]),
                                            price, row["trader"].strip())
                line_to_order[line_no] = order.order_id
                store.record_order(order.order_id, row["trader"].strip(), row["side"].strip().upper())
                store.record_trades(trades)
                kind = "MKT" if price is None else f"LMT {price:.2f}"
                event = f"{row['side']:<4} {row['quantity']:>4} {kind:<10} {row['trader']:<6}"
                if trades:
                    event += "  fills: " + ", ".join(f"{t.quantity}@{t.price:.2f}" for t in trades)
            if not quiet:
                print(f"{event:<58} | bid {fmt(book.best_bid()):>6}  ask {fmt(book.best_ask()):>6}"
                      f"  spread {fmt(book.spread()):>5}")
    return book, store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv")
    parser.add_argument("--db", default=":memory:", help="SQLite file to keep the trades in")
    args = parser.parse_args()

    book, store = replay(args.csv, args.db)
    print("\nDepth (top 5 levels):")
    depth = book.depth(5)
    for (bp, bq), (ap, aq) in zip(depth["bids"] + [(0, 0)] * 5, depth["asks"] + [(0, 0)] * 5):
        if not bq and not aq:
            break
        print(f"  {bq or '':>5} @ {bp or '':<7}   |   {ap or '':>7} @ {aq or ''}")
    print("\nSession summary:", store.summary())
    print("Volume by trader:", store.volume_by_trader())


if __name__ == "__main__":
    main()
