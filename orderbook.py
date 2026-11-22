"""
A limit order book with price-time priority matching.

How a real exchange order book works, in miniature:
  * Buyers post BIDS (the most they will pay). Sellers post ASKS (the least they will accept).
  * The highest bid and the lowest ask form the "top of book". The gap between them is the spread.
  * When a new order crosses the spread (a buy priced at or above the best ask, or a sell at or
    below the best bid) it trades immediately against resting orders.
  * Price-time priority: better prices fill first; at the same price, the order that arrived
    first fills first (FIFO).

Data structures and why:
  * Each side is a dict {price -> deque of orders}. A deque gives O(1) append to the back
    and O(1) pop from the front, which is exactly FIFO at one price level.
  * A heap of prices per side finds the best price in O(log n). Bids use negative prices so
    Python's min-heap behaves like a max-heap.
  * Cancelled orders are removed lazily: we mark them and skip them when they reach the front.
    This keeps cancel at O(1) instead of searching through a deque.
"""

from __future__ import annotations

import heapq
import itertools
from collections import deque
from dataclasses import dataclass, field
from enum import Enum


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class Order:
    order_id: int
    side: Side
    price: float | None  # None means a market order
    quantity: int
    trader: str = "anon"
    timestamp: int = 0
    cancelled: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.price is not None and self.price <= 0:
            raise ValueError("price must be positive")


@dataclass(frozen=True)
class Trade:
    trade_id: int
    buy_order_id: int
    sell_order_id: int
    price: float
    quantity: int
    timestamp: int


class OrderBook:
    def __init__(self, symbol: str = "DEMO") -> None:
        self.symbol = symbol
        self._bids: dict[float, deque[Order]] = {}
        self._asks: dict[float, deque[Order]] = {}
        self._bid_heap: list[float] = []  # stores -price
        self._ask_heap: list[float] = []  # stores price
        self._orders: dict[int, Order] = {}
        self._clock = itertools.count(1)
        self._order_ids = itertools.count(1)
        self._trade_ids = itertools.count(1)
        self.trades: list[Trade] = []

    # ------------------------------------------------------------------ public API
    def submit(self, side: Side | str, quantity: int, price: float | None = None,
               trader: str = "anon") -> tuple[Order, list[Trade]]:
        """Submit a limit order (price given) or a market order (price=None).

        Returns the order and the trades it caused. Any unfilled part of a limit
        order rests on the book; any unfilled part of a market order is dropped.
        """
        side = Side(side)
        order = Order(next(self._order_ids), side, price, quantity, trader, next(self._clock))
        trades = self._match(order)
        if order.quantity > 0 and order.price is not None:
            self._rest(order)
        return order, trades

    def cancel(self, order_id: int) -> bool:
        """Cancel a resting order. Returns False if it is unknown or already gone."""
        order = self._orders.pop(order_id, None)
        if order is None or order.cancelled:
            return False
        order.cancelled = True
        return True

    def best_bid(self) -> float | None:
        return self._best(self._bid_heap, self._bids, is_bid=True)

    def best_ask(self) -> float | None:
        return self._best(self._ask_heap, self._asks, is_bid=False)

    def spread(self) -> float | None:
        bid, ask = self.best_bid(), self.best_ask()
        if bid is None or ask is None:
            return None
        return round(ask - bid, 10)

    def mid_price(self) -> float | None:
        bid, ask = self.best_bid(), self.best_ask()
        if bid is None or ask is None:
            return None
        return (bid + ask) / 2

    def depth(self, levels: int = 5) -> dict[str, list[tuple[float, int]]]:
        """Market-data snapshot: total live quantity at the best N price levels per side."""
        def side_depth(book: dict[float, deque[Order]], reverse: bool) -> list[tuple[float, int]]:
            out = []
            for price in sorted(book, reverse=reverse):
                qty = sum(o.quantity for o in book[price] if not o.cancelled)
                if qty:
                    out.append((price, qty))
                if len(out) == levels:
                    break
            return out

        return {"bids": side_depth(self._bids, True), "asks": side_depth(self._asks, False)}

    # ------------------------------------------------------------------ internals
    def _match(self, incoming: Order) -> list[Trade]:
        trades: list[Trade] = []
        if incoming.side is Side.BUY:
            book, heap, best = self._asks, self._ask_heap, self.best_ask
            crosses = lambda p: incoming.price is None or incoming.price >= p
        else:
            book, heap, best = self._bids, self._bid_heap, self.best_bid
            crosses = lambda p: incoming.price is None or incoming.price <= p

        while incoming.quantity > 0:
            level_price = best()
            if level_price is None or not crosses(level_price):
                break
            queue = book[level_price]
            resting = queue[0]
            fill = min(incoming.quantity, resting.quantity)
            buy_id = incoming.order_id if incoming.side is Side.BUY else resting.order_id
            sell_id = resting.order_id if incoming.side is Side.BUY else incoming.order_id
            # The trade happens at the RESTING order's price: the earlier order set the price.
            trade = Trade(next(self._trade_ids), buy_id, sell_id, level_price, fill, next(self._clock))
            trades.append(trade)
            incoming.quantity -= fill
            resting.quantity -= fill
            if resting.quantity == 0:
                queue.popleft()
                self._orders.pop(resting.order_id, None)
            if not queue:
                del book[level_price]
                # the price stays in the heap; _best() discards it lazily

        self.trades.extend(trades)
        return trades

    def _rest(self, order: Order) -> None:
        if order.side is Side.BUY:
            book, heap, key = self._bids, self._bid_heap, -order.price
        else:
            book, heap, key = self._asks, self._ask_heap, order.price
        if order.price not in book:
            book[order.price] = deque()
            heapq.heappush(heap, key)
        book[order.price].append(order)
        self._orders[order.order_id] = order

    @staticmethod
    def _best(heap: list[float], book: dict[float, deque[Order]], is_bid: bool) -> float | None:
        while heap:
            price = -heap[0] if is_bid else heap[0]
            queue = book.get(price)
            # drop cancelled orders sitting at the front of the queue
            while queue and queue[0].cancelled:
                queue.popleft()
            if queue:
                return price
            book.pop(price, None)
            heapq.heappop(heap)
        return None
