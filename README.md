# Mini Order Book & Market-Data Feed

A limit order book in Python. It matches buy and sell orders with **price-time priority**, publishes a live top-of-book feed (best bid, best ask, spread, depth), and stores every trade in **SQLite** for analytics such as VWAP and volume per trader.

**Why I built it:** the Goldman Sachs Birmingham Engineering apprenticeship is sponsored by the firm's Global Head of Market Data Engineering. I wanted to understand, at small scale, what market data actually is and how an exchange turns orders into trades.

## What it does

| Feature | Detail |
| --- | --- |
| Limit and market orders | Limit orders rest if they don't cross; market orders take liquidity and never rest |
| Price-time priority | Best price fills first; at the same price, first-in first-out |
| Partial fills and sweeps | One big order can fill against several price levels |
| Cancels | O(1) lazy cancellation (marked, skipped when reached) |
| Market data | Best bid/ask, spread, mid price, top-N depth per side |
| Trade analytics (SQL) | VWAP, high/low, volume, volume per trader (JOIN + UNION ALL + GROUP BY) |
| Tests | 15 unit tests covering matching rules, edge cases and the SQL layer |

## Run it

```bash
python replay.py sample_orders.csv            # replay orders, print the feed
python replay.py sample_orders.csv --db t.db  # keep the trades in a SQLite file
python -m unittest discover -s tests -v       # run the tests
```

No libraries needed beyond the Python 3.10+ standard library.

Sample output:

```
SELL   60 LMT 99.75  carol   fills: 50@99.75     | bid  99.50  ask  99.75  spread  0.25
BUY   120 MKT        frank   fills: 10@99.75, 10@100.00, 80@100.25 | bid - ask - spread -
Session summary: {'trades': 5, 'volume': 180, 'high': 100.25, 'low': 99.75, 'vwap': 100.0278}
```

## How it works

- Each side of the book is a `dict` of price -> `deque` of orders. A deque gives O(1) FIFO at one price.
- A heap of prices per side finds the best price in O(log n). Bids are stored as negative numbers so Python's min-heap acts as a max-heap.
- A trade always happens at the **resting** order's price, because the order that was there first set the price.
- Cancelled orders are not searched for and deleted. They are flagged and skipped when they reach the front, which keeps cancel O(1).

| Operation | Time complexity |
| --- | --- |
| Submit (no match) | O(log P), P = number of price levels |
| Match one fill | O(1) amortised, plus O(log P) when a level empties |
| Cancel | O(1) |
| Best bid / ask | O(1) amortised |

## What I learned

- [Write 3 honest bullets in your own words after you have stepped through the code, e.g. why a deque and not a list, what broke when you first tested partial fills.]

## Make it yours (do at least one before you list it on your CV)

- [ ] Add an order **modify** (change quantity or price; think about whether it loses time priority)
- [ ] Add **stop orders** that wake up when the last traded price crosses a trigger
- [ ] Generate 100,000 random orders and time it; write the orders-per-second result here
- [ ] Draw a candlestick chart of trades per minute with matplotlib
- [ ] Add a second symbol and route orders to the right book

## Interview questions to be ready for

1. Why does the trade price come from the resting order?
2. What is the spread telling you about a market?
3. Why use a heap here, and what is the cost of lazy deletion?
4. How would you make this safe if two threads submitted orders at once?
5. What would change if this had to handle millions of orders a second? (Hint: language, memory layout, network, no database on the hot path.)
