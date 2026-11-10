"""
load_mongodb.py - load the generated JSON into MongoDB using the document model
described in report/TECHNICAL_REPORT (Part 1).

Collections
-----------
categories    : category with its subcategories EMBEDDED (small, bounded, always read together)
products      : product + EXTENDED REFERENCE to its category/subcategory (name, margin)
                + bounded price_history array
transactions  : order header with line items EMBEDDED; each item carries an extended
                reference (product name, category_id, subcategory_id) so revenue-by-category
                queries need no $lookup
users         : profile + geo + a pre-computed `purchase_summary` (SUBSET / COMPUTED pattern:
                totals, favourite category and the 5 most recent orders)
sessions      : OPTIONAL sample of full session journeys (page_views array embedded) used
                for journey/funnel aggregations. The full click-stream lives in HBase.

Usage
-----
    python mongodb/load_mongodb.py                        # uses MONGO_URI (default localhost)
    python mongodb/load_mongodb.py --sessions-limit 100000
    python mongodb/load_mongodb.py --mock                 # in-memory mongomock (no server needed)
"""
import argparse
import datetime as dt
import os
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from common.json_stream import iter_json_array, iter_sessions  # noqa: E402

BATCH = 5000


def get_db(mock=False):
    if mock:
        import mongomock
        return mongomock.MongoClient()[config.MONGO_DB]
    from pymongo import MongoClient
    client = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")  # fail fast with a clear error if the server is down
    return client[config.MONGO_DB]


def to_date(s):
    """ISO string -> datetime (stored as BSON Date so date operators & range indexes work)."""
    return dt.datetime.fromisoformat(s) if s else None


def bulk_insert(coll, docs_iter, label):
    """Insert in batches with ordered=False (continues past individual failures)."""
    from pymongo.errors import BulkWriteError
    batch, total, t0 = [], 0, time.time()
    for d in docs_iter:
        batch.append(d)
        if len(batch) >= BATCH:
            total += _flush(coll, batch, BulkWriteError)
            batch = []
    if batch:
        total += _flush(coll, batch, BulkWriteError)
    print(f"  {label:<13} {total:>9,} docs  ({time.time() - t0:.1f}s)")
    return total


def _flush(coll, batch, BulkWriteError):
    try:
        return len(coll.insert_many(batch, ordered=False).inserted_ids)
    except BulkWriteError as e:  # e.g. duplicate _id when re-running without --drop
        print(f"    warning: {len(e.details.get('writeErrors', []))} write errors in batch")
        return e.details.get("nInserted", 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=config.RAW_DIR)
    ap.add_argument("--sessions-limit", type=int, default=50000,
                    help="how many sessions to also store in MongoDB (0 = none)")
    ap.add_argument("--mock", action="store_true", help="use in-memory mongomock instead of a server")
    ap.add_argument("--no-drop", action="store_true", help="do not drop existing collections")
    a = ap.parse_args()
    db = get_db(a.mock)
    if not a.no_drop:
        for c in ("categories", "products", "users", "transactions", "sessions"):
            db[c].drop()
    print(f"Loading into {'mongomock' if a.mock else config.MONGO_URI}/{config.MONGO_DB}")

    # ---------------- categories ----------------
    categories = list(iter_json_array(os.path.join(a.raw, "categories.json")))
    cat_by_id = {c["category_id"]: c for c in categories}
    sub_by_id = {s["subcategory_id"]: s for c in categories for s in c["subcategories"]}
    bulk_insert(db.categories, ({"_id": c["category_id"], **c} for c in categories), "categories")

    # ---------------- products ----------------
    products = {}

    def product_docs():
        for p in iter_json_array(os.path.join(a.raw, "products.json")):
            cat = cat_by_id.get(p["category_id"], {})
            sub = sub_by_id.get(p.get("subcategory_id"), {})
            doc = {
                "_id": p["product_id"],
                "name": p["name"],
                "category": {"category_id": p["category_id"], "name": cat.get("name")},
                "subcategory": ({"subcategory_id": sub["subcategory_id"], "name": sub["name"],
                                 "profit_margin": sub["profit_margin"]} if sub else None),
                "base_price": p["base_price"],
                "current_stock": p["current_stock"],
                "is_active": p["is_active"],
                "price_history": [{"price": h["price"], "date": to_date(h["date"])} for h in p["price_history"]],
                "creation_date": to_date(p["creation_date"]),
            }
            products[p["product_id"]] = doc
            yield doc
    bulk_insert(db.products, product_docs(), "products")

    # ---------------- transactions (+ build per-user summaries on the fly) ----------------
    summary = defaultdict(lambda: {"total_spent": 0.0, "order_count": 0, "items_bought": 0,
                                   "first_purchase": None, "last_purchase": None,
                                   "cat_counter": Counter(), "recent": []})

    def txn_docs():
        for t in iter_json_array(os.path.join(a.raw, "transactions.json")):
            ts = to_date(t["timestamp"])
            items = []
            for it in t["items"]:
                p = products.get(it["product_id"], {})
                items.append({**it,
                              "product_name": p.get("name"),
                              "category_id": p.get("category", {}).get("category_id"),
                              "subcategory_id": (p.get("subcategory") or {}).get("subcategory_id")})
            s = summary[t["user_id"]]
            s["total_spent"] += t["total"]
            s["order_count"] += 1
            s["items_bought"] += sum(i["quantity"] for i in items)
            s["first_purchase"] = min(filter(None, [s["first_purchase"], ts]))
            s["last_purchase"] = max(filter(None, [s["last_purchase"], ts]))
            for i in items:
                s["cat_counter"][i["category_id"]] += i["quantity"]
            s["recent"].append((ts, t["transaction_id"], t["total"]))
            yield {"_id": t["transaction_id"], "session_id": t["session_id"], "user_id": t["user_id"],
                   "timestamp": ts, "items": items, "subtotal": t["subtotal"], "discount": t["discount"],
                   "total": t["total"], "payment_method": t["payment_method"], "status": t["status"],
                   "channel": "web_session" if t["session_id"] else "offline_or_app"}
    bulk_insert(db.transactions, txn_docs(), "transactions")

    # ---------------- users with embedded purchase summary ----------------
    def user_docs():
        for u in iter_json_array(os.path.join(a.raw, "users.json")):
            s = summary.get(u["user_id"])
            ps = None
            if s:
                recent = sorted(s["recent"], reverse=True)[:5]
                ps = {"total_spent": round(s["total_spent"], 2), "order_count": s["order_count"],
                      "avg_order_value": round(s["total_spent"] / s["order_count"], 2),
                      "items_bought": s["items_bought"],
                      "first_purchase": s["first_purchase"], "last_purchase": s["last_purchase"],
                      "favorite_category": s["cat_counter"].most_common(1)[0][0],
                      "recent_orders": [{"transaction_id": r[1], "timestamp": r[0], "total": r[2]} for r in recent]}
            yield {"_id": u["user_id"], "geo_data": u["geo_data"],
                   "registration_date": to_date(u["registration_date"]),
                   "last_active": to_date(u["last_active"]),
                   "purchase_summary": ps or {"total_spent": 0.0, "order_count": 0}}
    bulk_insert(db.users, user_docs(), "users")

    # ---------------- optional: session journeys ----------------
    if a.sessions_limit:
        def session_docs():
            for s in iter_sessions(a.raw, a.sessions_limit):
                s["_id"] = s.pop("session_id")
                s["start_time"], s["end_time"] = to_date(s["start_time"]), to_date(s["end_time"])
                for pv in s["page_views"]:
                    pv["timestamp"] = to_date(pv["timestamp"])
                # cart_contents is a map keyed by product id -> turn into an array (indexable)
                s["cart_contents"] = [{"product_id": k, **v} for k, v in s["cart_contents"].items()]
                yield s
        bulk_insert(db.sessions, session_docs(), "sessions")

    create_indexes(db)
    print("Done.")
    return db


def create_indexes(db):
    """Indexes that back the query patterns in aggregations.py."""
    db.products.create_index([("category.category_id", 1), ("is_active", 1)])
    db.transactions.create_index([("user_id", 1), ("timestamp", -1)])   # user order history
    db.transactions.create_index([("timestamp", 1)])                    # time-range revenue
    db.transactions.create_index([("items.product_id", 1)])             # multikey: product sales
    db.users.create_index([("purchase_summary.total_spent", -1)])       # top customers
    db.users.create_index([("geo_data.country", 1)])
    db.sessions.create_index([("user_id", 1), ("start_time", -1)])
    db.sessions.create_index([("conversion_status", 1), ("referrer", 1)])
    print("  indexes created")


if __name__ == "__main__":
    main()
