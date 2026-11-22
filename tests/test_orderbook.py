import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orderbook import OrderBook  # noqa: E402
from replay import replay  # noqa: E402
from tradestore import TradeStore  # noqa: E402


class TestMatching(unittest.TestCase):
    def setUp(self):
        self.book = OrderBook()

    def test_non_crossing_orders_rest(self):
        self.book.submit("BUY", 10, 99.0)
        self.book.submit("SELL", 10, 101.0)
        self.assertEqual(self.book.best_bid(), 99.0)
        self.assertEqual(self.book.best_ask(), 101.0)
        self.assertEqual(self.book.spread(), 2.0)
        self.assertEqual(self.book.mid_price(), 100.0)
        self.assertEqual(self.book.trades, [])

    def test_trade_happens_at_resting_price(self):
        self.book.submit("SELL", 10, 100.0)
        _, trades = self.book.submit("BUY", 10, 105.0)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].price, 100.0)

    def test_price_priority(self):
        self.book.submit("SELL", 10, 101.0, "worse")
        good, _ = self.book.submit("SELL", 10, 100.0, "better")
        _, trades = self.book.submit("BUY", 10, 101.0)
        self.assertEqual(trades[0].sell_order_id, good.order_id)

    def test_time_priority_at_same_price(self):
        first, _ = self.book.submit("BUY", 5, 100.0)
        self.book.submit("BUY", 5, 100.0)
        _, trades = self.book.submit("SELL", 5, 100.0)
        self.assertEqual(trades[0].buy_order_id, first.order_id)

    def test_partial_fill_rests_remainder(self):
        self.book.submit("SELL", 4, 100.0)
        order, trades = self.book.submit("BUY", 10, 100.0)
        self.assertEqual(sum(t.quantity for t in trades), 4)
        self.assertEqual(order.quantity, 6)
        self.assertEqual(self.book.best_bid(), 100.0)
        self.assertIsNone(self.book.best_ask())

    def test_sweep_multiple_levels(self):
        self.book.submit("SELL", 5, 100.0)
        self.book.submit("SELL", 5, 101.0)
        self.book.submit("SELL", 5, 102.0)
        _, trades = self.book.submit("BUY", 12, 101.5)
        self.assertEqual([(t.price, t.quantity) for t in trades], [(100.0, 5), (101.0, 5)])
        self.assertEqual(self.book.best_bid(), 101.5)  # 2 left over rests
        self.assertEqual(self.book.best_ask(), 102.0)

    def test_market_order_never_rests(self):
        self.book.submit("SELL", 3, 100.0)
        order, trades = self.book.submit("BUY", 10)  # market
        self.assertEqual(sum(t.quantity for t in trades), 3)
        self.assertIsNone(self.book.best_bid())
        self.assertEqual(order.quantity, 7)

    def test_market_order_into_empty_book(self):
        _, trades = self.book.submit("SELL", 10)
        self.assertEqual(trades, [])

    def test_cancel(self):
        order, _ = self.book.submit("BUY", 10, 100.0)
        self.assertTrue(self.book.cancel(order.order_id))
        self.assertFalse(self.book.cancel(order.order_id))
        self.assertIsNone(self.book.best_bid())
        _, trades = self.book.submit("SELL", 10, 100.0)
        self.assertEqual(trades, [])

    def test_cancel_unknown(self):
        self.assertFalse(self.book.cancel(999))

    def test_depth_skips_cancelled(self):
        a, _ = self.book.submit("BUY", 10, 100.0)
        self.book.submit("BUY", 7, 100.0)
        self.book.submit("BUY", 3, 99.0)
        self.book.cancel(a.order_id)
        self.assertEqual(self.book.depth(5)["bids"], [(100.0, 7), (99.0, 3)])

    def test_invalid_orders_rejected(self):
        with self.assertRaises(ValueError):
            self.book.submit("BUY", 0, 100.0)
        with self.assertRaises(ValueError):
            self.book.submit("BUY", 5, -1.0)
        with self.assertRaises(ValueError):
            self.book.submit("HOLD", 5, 100.0)


class TestTradeStore(unittest.TestCase):
    def test_vwap_and_volume(self):
        book, store = OrderBook(), TradeStore()
        for side, qty, price, who in [("SELL", 10, 100.0, "s1"), ("SELL", 30, 102.0, "s2"),
                                      ("BUY", 40, 102.0, "b1")]:
            order, trades = book.submit(side, qty, price, who)
            store.record_order(order.order_id, who, side)
            store.record_trades(trades)
        # (10*100 + 30*102) / 40 = 101.5
        self.assertEqual(store.vwap(), 101.5)
        self.assertEqual(store.volume_by_trader(), [("b1", 40), ("s2", 30), ("s1", 10)])

    def test_empty_store(self):
        self.assertIsNone(TradeStore().vwap())


class TestReplay(unittest.TestCase):
    def test_sample_file(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        book, store = replay(os.path.join(here, "sample_orders.csv"), quiet=True)
        self.assertGreater(store.summary()["trades"], 0)
        self.assertIsNotNone(book.best_bid())


if __name__ == "__main__":
    unittest.main()
