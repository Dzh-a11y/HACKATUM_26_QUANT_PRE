-- demo.py 把两个 Parquet 文件注册为 quotes 视图；视图没有复制行情数据。
-- 1. 看文件里保留的数据类型。
DESCRIBE quotes;

-- 2. 看最早的 8 条报价。价格存整数 tick，展示时换算为欧元。
SELECT event_time, received_at, symbol, venue,
       bid_ticks / 100.0 AS bid_eur,
       ask_ticks / 100.0 AS ask_eur,
       bid_size, ask_size
FROM quotes
ORDER BY event_time, symbol, venue
LIMIT 8;

-- 3. 跨两个文件，按股票和市场计算平均买卖价差。每组应有 600 条。
SELECT symbol, venue, COUNT(*) AS quote_count,
       ROUND(AVG(ask_ticks - bid_ticks), 3) AS average_spread_ticks
FROM quotes
GROUP BY symbol, venue
ORDER BY symbol, venue;

-- 4. 同一股票、同一模拟时刻：X 市场的卖价低于 Y 市场的买价？
-- 两市场的 event_time 在生成器中刻意同步，才能用等值 JOIN。
-- 真实异步行情须按已接收的数据对齐，并限制报价陈旧程度。
-- 此处未扣费用，也没有模拟下单延迟、成交或仓位，结果仅是纸面价格差。
SELECT x.event_time, x.symbol,
       x.ask_ticks / 100.0 AS buy_at_x_eur,
       y.bid_ticks / 100.0 AS sell_at_y_eur,
       y.bid_ticks - x.ask_ticks AS gross_gap_ticks
FROM quotes AS x
JOIN quotes AS y
  ON x.symbol = y.symbol AND x.event_time = y.event_time
WHERE x.venue = 'X' AND y.venue = 'Y'
  AND y.bid_ticks > x.ask_ticks
ORDER BY x.event_time, x.symbol
LIMIT 6;

-- 5. 看查询计划：READ_PARQUET 仅投影 ask_ticks / bid_ticks，
-- 并在扫描中应用 symbol = 'ALPHA' 的过滤；无需返回时间、数量等列。
-- 过滤列本身也可能需要读取。过滤下推不保证一定能跳过整个文件或行组。
EXPLAIN
SELECT AVG(ask_ticks - bid_ticks)
FROM quotes
WHERE symbol = 'ALPHA';
