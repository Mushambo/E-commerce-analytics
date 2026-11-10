"""
aggregations.py - MongoDB analytics pipelines (Part 1).

  1. product_popularity()      top-selling products (units & revenue) + category share
  2. revenue_by_category_month() revenue per category per month, with margin-based profit
  3. user_segmentation()       purchase-frequency / spend segments using $bucket + $facet
  4. session_journey_funnel()  funnel over embedded page_views (needs sessions sample)

The same pipelines are available for mongosh in aggregations.js.
Results are printed and saved to output/mongo_*.csv.

Usage:
    python mongodb/aggregations.py            # against MONGO_URI
    python mongodb/aggregations.py --mock     # loads data into mongomock first, then runs
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402


# --------------------------------------------------------------------------
# 1. Product popularity
# --------------------------------------------------------------------------
PRODUCT_POPULARITY = [
    {"$match": {"status": {"$in": ["completed", "shipped", "delivered", "processing"]}}},
    {"$unwind": "$items"},                               # one doc per line item
    {"$group": {
        "_id": "$items.product_id",
        "product_name": {"$first": "$items.product_name"},
        "category_id": {"$first": "$items.category_id"},
        "units_sold": {"$sum": "$items.quantity"},
        "revenue": {"$sum": "$items.subtotal"},
        "orders": {"$sum": 1},
    }},
    {"$sort": {"units_sold": -1, "revenue": -1}},
    {"$limit": 10},
    # bring in current stock / price from the catalogue
    {"$lookup": {"from": "products", "localField": "_id", "foreignField": "_id", "as": "product"}},
    {"$unwind": "$product"},
    {"$project": {"_id": 0, "product_id": "$_id", "product_name": 1, "category_id": 1,
                  "units_sold": 1, "orders": 1, "revenue": {"$round": ["$revenue", 2]},
                  "current_price": "$product.base_price", "current_stock": "$product.current_stock"}},
]

# --------------------------------------------------------------------------
# 2. Revenue & estimated gross profit by category and month
# --------------------------------------------------------------------------
REVENUE_BY_CATEGORY_MONTH = [
    {"$unwind": "$items"},
    {"$lookup": {"from": "categories", "localField": "items.category_id",
                 "foreignField": "_id", "as": "cat"}},
    {"$unwind": "$cat"},
    # profit margin lives on the subcategory -> pick the matching embedded subcategory
    {"$addFields": {"sub": {"$arrayElemAt": [{"$filter": {
        "input": "$cat.subcategories", "as": "s",
        "cond": {"$eq": ["$$s.subcategory_id", "$items.subcategory_id"]}}}, 0]}}},
    {"$group": {
        "_id": {"category": "$cat.name",
                "month": {"$dateToString": {"format": "%Y-%m", "date": "$timestamp"}}},
        "revenue": {"$sum": "$items.subtotal"},
        "est_profit": {"$sum": {"$multiply": ["$items.subtotal", "$sub.profit_margin"]}},
        "units": {"$sum": "$items.quantity"},
    }},
    {"$sort": {"_id.month": 1, "revenue": -1}},
    {"$project": {"_id": 0, "category": "$_id.category", "month": "$_id.month",
                  "revenue": {"$round": ["$revenue", 2]}, "est_profit": {"$round": ["$est_profit", 2]},
                  "units": 1}},
]

# --------------------------------------------------------------------------
# 3. User segmentation (frequency buckets + spend tiers in one round trip)
# --------------------------------------------------------------------------
USER_SEGMENTATION = [
    {"$group": {"_id": "$user_id", "orders": {"$sum": 1}, "spent": {"$sum": "$total"},
                "last_order": {"$max": "$timestamp"}}},
    {"$facet": {
        "by_frequency": [
            {"$bucket": {"groupBy": "$orders", "boundaries": [1, 3, 6, 10, 1000], "default": "other",
                         "output": {"users": {"$sum": 1}, "avg_spent": {"$avg": "$spent"},
                                    "total_revenue": {"$sum": "$spent"}}}}],
        "by_spend": [
            {"$bucket": {"groupBy": "$spent", "boundaries": [0, 500, 1500, 3000, 6000, 1e9],
                         "default": "other",
                         "output": {"users": {"$sum": 1}, "avg_orders": {"$avg": "$orders"}}}}],
        "top_customers": [{"$sort": {"spent": -1}}, {"$limit": 5}],
    }},
]

# --------------------------------------------------------------------------
# 4. Journey funnel on embedded page_views (sessions sample in MongoDB)
# --------------------------------------------------------------------------
SESSION_FUNNEL = [
    {"$project": {"referrer": 1, "conversion_status": 1,
                  "pages": "$page_views.page_type"}},       # array of page types
    {"$group": {
        "_id": "$referrer",
        "sessions": {"$sum": 1},
        "viewed_product": {"$sum": {"$cond": [{"$in": ["product_detail", "$pages"]}, 1, 0]}},
        "reached_cart": {"$sum": {"$cond": [{"$in": ["cart", "$pages"]}, 1, 0]}},
        "reached_checkout": {"$sum": {"$cond": [{"$in": ["checkout", "$pages"]}, 1, 0]}},
        "converted": {"$sum": {"$cond": [{"$eq": ["$conversion_status", "converted"]}, 1, 0]}},
    }},
    {"$addFields": {"conversion_rate": {"$round": [{"$divide": ["$converted", "$sessions"]}, 4]}}},
    {"$sort": {"conversion_rate": -1}},
]


def mock_compat(node):
    """mongomock lacks $round; strip it (results are rounded in Python instead).
    Real MongoDB (>= 4.2) runs the pipelines unchanged."""
    if isinstance(node, list):
        return [mock_compat(x) for x in node]
    if isinstance(node, dict):
        if set(node) == {"$round"}:
            return mock_compat(node["$round"][0])
        return {k: mock_compat(v) for k, v in node.items()}
    return node


def save_csv(rows, name):
    if not rows:
        return
    path = os.path.join(config.OUTPUT_DIR, f"mongo_{name}.csv")
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def show(title, rows, n=12):
    print(f"\n=== {title} ===")
    for r in rows[:n]:
        print("  ", {k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()})


def run_all(db, mock=False):
    global PRODUCT_POPULARITY, REVENUE_BY_CATEGORY_MONTH, USER_SEGMENTATION, SESSION_FUNNEL
    if mock:
        PRODUCT_POPULARITY, REVENUE_BY_CATEGORY_MONTH, USER_SEGMENTATION, SESSION_FUNNEL = map(
            mock_compat, (PRODUCT_POPULARITY, REVENUE_BY_CATEGORY_MONTH, USER_SEGMENTATION, SESSION_FUNNEL))
    rows = list(db.transactions.aggregate(PRODUCT_POPULARITY))
    show("1. Top-selling products", rows)
    save_csv(rows, "top_products")

    rows = list(db.transactions.aggregate(REVENUE_BY_CATEGORY_MONTH, allowDiskUse=True))
    show("2. Revenue by category & month (first rows)", rows)
    save_csv(rows, "revenue_category_month")

    seg = list(db.transactions.aggregate(USER_SEGMENTATION, allowDiskUse=True))[0]
    freq = [{"orders_bucket": r["_id"], **{k: v for k, v in r.items() if k != "_id"}} for r in seg["by_frequency"]]
    spend = [{"spend_bucket": r["_id"], **{k: v for k, v in r.items() if k != "_id"}} for r in seg["by_spend"]]
    show("3a. Users by purchase frequency (bucket lower bound = orders)", freq)
    show("3b. Users by total spend (bucket lower bound = $)", spend)
    show("3c. Top customers", seg["top_customers"], 5)
    save_csv(freq, "segments_frequency")
    save_csv(spend, "segments_spend")

    if db.sessions.estimated_document_count():
        rows = list(db.sessions.aggregate(SESSION_FUNNEL))
        show("4. Session funnel by referrer", rows)
        save_csv(rows, "funnel_by_referrer")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true")
    a = ap.parse_args()
    if a.mock:
        sys.argv = [sys.argv[0], "--mock"]
        from load_mongodb import main as load
        database = load()
    else:
        from pymongo import MongoClient
        database = MongoClient(config.MONGO_URI)[config.MONGO_DB]
    run_all(database, mock=a.mock)
