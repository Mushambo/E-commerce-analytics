"""
04_spark_sql_analytics.py - Spark SQL analytics over the cleaned tables.

Part A: complex SQL on DataFrames derived from the JSON files
  Q1  top-3 products per category by revenue                      (CTE + RANK window)
  Q2  conversion funnel by device type and referrer                 (conditional aggregation)
  Q3  daily revenue with 7-day rolling average & week-over-week     (RANGE window, LAG)
  Q4  price-change impact: units/day before vs after latest change  (join on exploded history)
  Q5  most-viewed vs best-selling products, view->purchase rate     (multi-source join)

Part B: "polyglot" SQL - the same engine querying data that notionally lives in
  MongoDB (users with embedded purchase_summary, transactions with embedded items) and
  HBase (user_sessions keyed by user_id|reverse_ts|session_id, product_metrics keyed by
  product_id|yyyymmdd). We build DataFrames in exactly those shapes and register them as
  views `mongo_users`, `mongo_transactions`, `hbase_user_sessions`, `hbase_product_metrics`.
  In production the views would be created with the connectors instead:

    # MongoDB Spark Connector 10.x
    spark.read.format("mongodb").option("connection.uri", MONGO_URI) \
         .option("database", "ecommerce").option("collection", "users").load() \
         .createOrReplaceTempView("mongo_users")
    # HBase: hbase-spark connector (org.apache.hadoop.hbase.spark) with a catalog,
    #        or integration/sources.py which scans via Thrift and builds a DataFrame.
"""
import os
import sys

from pyspark.sql import functions as F

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spark_utils as su  # noqa: E402

spark = su.get_spark("04_spark_sql_analytics")
for t in ["users", "products", "categories", "sessions", "page_views", "transactions",
          "transaction_items", "price_history", "cart_items"]:
    su.read_clean(spark, t).createOrReplaceTempView(t)


def run(name, sql, n=15):
    print(f"\n==================== {name}")
    df = spark.sql(sql)
    df.show(n, truncate=False)
    su.save_csv(df, f"sql_{name}")
    return df


# ---------------------------------------------------------------------------- PART A
run("q1_top3_products_per_category", """
WITH product_rev AS (
    SELECT category_name, product_id,
           SUM(quantity)                AS units,
           ROUND(SUM(net_revenue), 2)   AS revenue,
           ROUND(SUM(est_profit), 2)    AS est_profit
    FROM transaction_items
    GROUP BY category_name, product_id
), ranked AS (
    SELECT pr.*, p.product_name,
           RANK() OVER (PARTITION BY pr.category_name ORDER BY pr.revenue DESC) AS rnk,
           ROUND(100 * pr.revenue / SUM(pr.revenue) OVER (PARTITION BY pr.category_name), 2) AS pct_of_category
    FROM product_rev pr JOIN products p ON pr.product_id = p.product_id
)
SELECT category_name, rnk, product_id, product_name, units, revenue, est_profit, pct_of_category
FROM ranked WHERE rnk <= 3
ORDER BY category_name, rnk
""")

run("q2_funnel_by_device_referrer", """
WITH s AS (
    SELECT s.*, (t.session_id IS NOT NULL) AS purchased
    FROM sessions s
    LEFT JOIN (SELECT DISTINCT session_id FROM transactions WHERE session_id IS NOT NULL) t
      USING (session_id)
)
SELECT device_type, referrer,
       COUNT(*)                                              AS sessions,
       ROUND(100 * AVG(CAST(has_product_view AS INT)), 1)    AS pct_product_view,
       ROUND(100 * AVG(CAST(n_cart_products > 0 AS INT)), 1) AS pct_add_to_cart,
       ROUND(100 * AVG(CAST(has_checkout AS INT)), 1)        AS pct_checkout,
       ROUND(100 * AVG(CAST(conversion_status = 'converted' AS INT)), 2) AS pct_converted_flag,
       ROUND(100 * AVG(CAST(purchased AS INT)), 2)           AS pct_with_transaction,
       ROUND(AVG(duration_seconds) / 60, 1)                  AS avg_minutes
FROM s
GROUP BY ROLLUP(device_type, referrer)
ORDER BY device_type NULLS LAST, referrer NULLS LAST
""", 25)

run("q3_daily_revenue_rolling", """
WITH daily AS (
    SELECT txn_date, COUNT(*) AS orders, ROUND(SUM(total), 2) AS revenue,
           ROUND(SUM(discount), 2) AS discounts
    FROM transactions GROUP BY txn_date
)
SELECT txn_date, orders, revenue, discounts,
       ROUND(AVG(revenue) OVER (ORDER BY CAST(txn_date AS TIMESTAMP)
             RANGE BETWEEN INTERVAL 6 DAYS PRECEDING AND CURRENT ROW), 2) AS revenue_7d_avg,
       ROUND(100 * (revenue / LAG(revenue, 7) OVER (ORDER BY txn_date) - 1), 1) AS wow_change_pct,
       DATE_FORMAT(txn_date, 'E') AS weekday
FROM daily ORDER BY txn_date
""", 10)

run("q4_price_change_impact", """
WITH last_change AS (            -- latest price change per product (seq > 0 means a change)
    SELECT product_id, MAX_BY(effective_date, seq) AS change_date,
           MAX_BY(price, seq) AS new_price,
           MAX_BY(price, seq) / FIRST_VALUE_PRICE - 1 AS pct_change
    FROM (SELECT ph.*, FIRST(price) OVER (PARTITION BY product_id ORDER BY seq) AS FIRST_VALUE_PRICE
          FROM price_history ph)
    WHERE seq > 0
    GROUP BY product_id, FIRST_VALUE_PRICE
), window_bounds AS (
    SELECT MIN(txn_time) AS t0, MAX(txn_time) AS t1 FROM transactions
), sales AS (
    SELECT ti.product_id, lc.pct_change,
           SUM(CASE WHEN ti.txn_time <  lc.change_date THEN ti.quantity END) AS units_before,
           SUM(CASE WHEN ti.txn_time >= lc.change_date THEN ti.quantity END) AS units_after,
           GREATEST(DATEDIFF(MIN(lc.change_date), MIN(wb.t0)), 1) AS days_before,
           GREATEST(DATEDIFF(MIN(wb.t1), MIN(lc.change_date)), 1) AS days_after
    FROM transaction_items ti
    JOIN last_change lc USING (product_id)
    CROSS JOIN window_bounds wb
    WHERE lc.change_date BETWEEN wb.t0 AND wb.t1
    GROUP BY ti.product_id, lc.pct_change
)
SELECT CASE WHEN pct_change <= -0.10 THEN '1. cut >10%'
            WHEN pct_change <  0     THEN '2. cut 0-10%'
            WHEN pct_change <  0.10  THEN '3. raise 0-10%'
            ELSE '4. raise >10%' END AS price_move,
       COUNT(*) AS products,
       ROUND(AVG(COALESCE(units_before, 0) / days_before), 3) AS units_per_day_before,
       ROUND(AVG(COALESCE(units_after, 0) / days_after), 3)   AS units_per_day_after
FROM sales GROUP BY 1 ORDER BY 1
""")

run("q5_viewed_vs_sold", """
WITH views AS (
    SELECT product_id, COUNT(*) AS views FROM page_views
    WHERE page_type = 'product_detail' AND product_id IS NOT NULL GROUP BY product_id
), carts AS (
    SELECT product_id, COUNT(*) AS cart_adds FROM cart_items GROUP BY product_id
), sold AS (
    SELECT product_id, SUM(quantity) AS units_sold, COUNT(DISTINCT transaction_id) AS orders,
           ROUND(SUM(net_revenue), 2) AS revenue
    FROM transaction_items GROUP BY product_id
)
SELECT p.product_id, p.product_name, p.category_name, p.current_price, p.current_stock, p.is_active,
       COALESCE(v.views, 0) AS views, COALESCE(c.cart_adds, 0) AS cart_adds,
       COALESCE(s.orders, 0) AS orders, COALESCE(s.units_sold, 0) AS units_sold,
       COALESCE(s.revenue, 0) AS revenue,
       ROUND(COALESCE(c.cart_adds, 0) / NULLIF(v.views, 0), 3) AS view_to_cart,
       RANK() OVER (ORDER BY COALESCE(v.views, 0) DESC)  AS view_rank,
       RANK() OVER (ORDER BY COALESCE(s.units_sold, 0) DESC) AS sales_rank
FROM products p
LEFT JOIN views v USING (product_id)
LEFT JOIN carts c USING (product_id)
LEFT JOIN sold  s USING (product_id)
ORDER BY views DESC
""", 10)

# ---------------------------------------------------------------------------- PART B
print("\n#################### Part B - querying 'MongoDB' and 'HBase' shaped data")
# mongo_users: profile + embedded purchase_summary (as stored by mongodb/load_mongodb.py)
spark.sql("""
SELECT u.user_id AS _id, named_struct('city', u.city, 'state', u.state, 'country', u.country) AS geo_data,
       u.registration_date,
       named_struct('total_spent', ROUND(COALESCE(SUM(t.total), 0), 2),
                    'order_count', COUNT(t.transaction_id),
                    'last_purchase', MAX(t.txn_time)) AS purchase_summary
FROM users u LEFT JOIN transactions t USING (user_id)
GROUP BY u.user_id, u.city, u.state, u.country, u.registration_date
""").createOrReplaceTempView("mongo_users")

# mongo_transactions: order with embedded items array
spark.sql("""
SELECT t.transaction_id AS _id, t.user_id, t.session_id, t.txn_time AS timestamp, t.total, t.status,
       COLLECT_LIST(named_struct('product_id', i.product_id, 'quantity', i.quantity,
                                 'category_id', i.category_id, 'subtotal', i.gross_revenue)) AS items
FROM transactions t JOIN transaction_items i USING (transaction_id)
GROUP BY t.transaction_id, t.user_id, t.session_id, t.txn_time, t.total, t.status
""").createOrReplaceTempView("mongo_transactions")

# hbase_user_sessions: row key + 'info' column family flattened to columns (what a scan returns)
spark.sql("""
SELECT CONCAT(user_id, '|', LPAD(CAST(9999999999999 - UNIX_MILLIS(start_time) AS STRING), 13, '0'),
              '|', session_id) AS rowkey,
       session_id AS `info:session_id`, start_time AS `info:start_time`,
       duration_seconds AS `info:duration`, device_type AS `info:device_type`,
       referrer AS `info:referrer`, conversion_status AS `info:conversion_status`, n_pages AS `info:n_pages`
FROM sessions
""").createOrReplaceTempView("hbase_user_sessions")

# hbase_product_metrics: rowkey product_id|yyyymmdd, family m
spark.sql("""
SELECT CONCAT(product_id, '|', DATE_FORMAT(view_date, 'yyyyMMdd')) AS rowkey, COUNT(*) AS `m:views`
FROM page_views WHERE page_type = 'product_detail' AND product_id IS NOT NULL
GROUP BY product_id, view_date
""").createOrReplaceTempView("hbase_product_metrics")

run("qB1_engagement_vs_value_mongo_x_hbase", """
-- Join MongoDB user documents with HBase session rows. The user id is recovered from the
-- HBase row key with SPLIT - the same parsing a real HBase scan result needs.
WITH engagement AS (
    SELECT SPLIT(rowkey, '\\\\|')[0]           AS user_id,
           COUNT(*)                           AS sessions,
           ROUND(AVG(`info:duration`) / 60, 1) AS avg_session_min,
           ROUND(AVG(`info:n_pages`), 1)      AS avg_pages
    FROM hbase_user_sessions GROUP BY 1
)
SELECT CASE WHEN e.sessions >= 25 THEN '4. 25+ sessions'
            WHEN e.sessions >= 20 THEN '3. 20-24'
            WHEN e.sessions >= 15 THEN '2. 15-19'
            ELSE '1. <15' END                          AS engagement_band,
       COUNT(*)                                        AS users,
       ROUND(AVG(m.purchase_summary.order_count), 2)   AS avg_orders,
       ROUND(AVG(m.purchase_summary.total_spent), 2)   AS avg_spent,
       ROUND(AVG(e.avg_session_min), 1)                AS avg_session_min
FROM mongo_users m JOIN engagement e ON m._id = e.user_id
GROUP BY 1 ORDER BY 1
""")

run("qB2_category_revenue_from_embedded_items", """
-- LATERAL VIEW explode = MongoDB's $unwind, executed by Spark
SELECT item.category_id, ROUND(SUM(item.subtotal), 2) AS gross_revenue, COUNT(DISTINCT _id) AS orders
FROM mongo_transactions LATERAL VIEW explode(items) x AS item
WHERE timestamp >= DATE_SUB((SELECT MAX(timestamp) FROM mongo_transactions), 30)
GROUP BY item.category_id ORDER BY gross_revenue DESC LIMIT 10
""", 10)

run("qB3_product_view_trend_hbase", """
-- weekly views for the 5 most viewed products, parsed from HBase row keys
WITH pm AS (
    SELECT SPLIT(rowkey, '\\\\|')[0] AS product_id,
           TO_DATE(SPLIT(rowkey, '\\\\|')[1], 'yyyyMMdd') AS d, `m:views` AS views
    FROM hbase_product_metrics
), top5 AS (SELECT product_id FROM pm GROUP BY product_id ORDER BY SUM(views) DESC LIMIT 5)
SELECT product_id, DATE_TRUNC('WEEK', d) AS week, SUM(views) AS views
FROM pm JOIN top5 USING (product_id) GROUP BY product_id, DATE_TRUNC('WEEK', d)
ORDER BY product_id, week
""", 10)

spark.stop()
