"""
dataset_generator.py  (improved version of the course-provided generator)
=========================================================================

Generates the synthetic e-commerce dataset (users, categories, products,
sessions, transactions) described in the AUCA Big Data Analytics final project.

The simulation logic (page-flow Markov chain, cart behaviour, 70 % checkout
conversion, inventory checks, discounts, "extra" transactions) is IDENTICAL to
the original script in `dataset_generator_original.py`. The changes are
engineering fixes so the script can actually run on a laptop and so the output
matches the data dictionary in the project brief:

  1. `subcategory_id` is now assigned to every product. The brief's sample
     product document has it, the original script never set it.
  2. Sessions are STREAMED to disk in chunks of 100 000 instead of being held
     in one Python list. 2 M sessions with nested page views need >10 GB of
     RAM in the original; this version stays well under 2 GB.
  3. IDs are derived from the seeded RNG instead of uuid4(), so two runs with
     the same seed produce exactly the same dataset (reproducible results).
  4. A `--scale` flag shrinks NUM_SESSIONS / NUM_TRANSACTIONS for quick
     development runs (users, products and categories stay at full size).
  5. Output goes to an `--out` directory; file names are unchanged
     (users.json, products.json, categories.json, transactions.json,
     sessions_0.json, sessions_1.json, ...), each a JSON array like before.

Usage
-----
    pip install faker numpy
    python data_generation/dataset_generator.py --out data/raw            # full size
    python data_generation/dataset_generator.py --out data/raw --scale 0.1  # 10 %
"""
import argparse
import datetime
import json
import os
import random
import threading
import time

import numpy as np
from faker import Faker

# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
parser = argparse.ArgumentParser(description="Synthetic e-commerce dataset generator")
parser.add_argument("--out", default="data/raw", help="output directory")
parser.add_argument("--scale", type=float, default=1.0,
                    help="fraction of sessions/transactions to generate (default 1.0 = 2M/500k)")
parser.add_argument("--seed", type=int, default=42)
args = parser.parse_args()
os.makedirs(args.out, exist_ok=True)

# --------------------------------------------------------------------------
# Configuration (same defaults as the original)
# --------------------------------------------------------------------------
NUM_USERS = 10000
NUM_PRODUCTS = 5000
NUM_CATEGORIES = 25
NUM_TRANSACTIONS = int(500000 * args.scale)
NUM_SESSIONS = int(2000000 * args.scale)
TIMESPAN_DAYS = 90
MAX_ITERATIONS = (NUM_SESSIONS + NUM_TRANSACTIONS) * 2  # fail-safe
CHUNK_SIZE = 100000

np.random.seed(args.seed)
random.seed(args.seed)
Faker.seed(args.seed)
fake = Faker()

print(f"Initializing dataset generation (scale={args.scale}, "
      f"{NUM_SESSIONS:,} sessions, {NUM_TRANSACTIONS:,} transactions)...")


# --------------------------------------------------------------------------
# ID generators - seeded, therefore reproducible (fix #3)
# --------------------------------------------------------------------------
def generate_session_id():
    return f"sess_{random.getrandbits(40):010x}"


def generate_transaction_id():
    return f"txn_{random.getrandbits(48):012x}"


# --------------------------------------------------------------------------
# Inventory management (unchanged)
# --------------------------------------------------------------------------
class InventoryManager:
    def __init__(self, products):
        self.products = {p["product_id"]: p for p in products}
        self.lock = threading.RLock()

    def update_stock(self, product_id, quantity):
        with self.lock:
            if product_id not in self.products:
                return False
            if self.products[product_id]["current_stock"] >= quantity:
                self.products[product_id]["current_stock"] -= quantity
                return True
            return False

    def get_product(self, product_id):
        with self.lock:
            return self.products.get(product_id)


# --------------------------------------------------------------------------
# Page-flow model (unchanged transition probabilities)
# --------------------------------------------------------------------------
TRANSITIONS = {
    "home": (["category_listing", "search", "product_detail"], [0.5, 0.3, 0.2]),
    "category_listing": (["product_detail", "category_listing", "search", "home"], [0.7, 0.1, 0.1, 0.1]),
    "search": (["product_detail", "search", "category_listing", "home"], [0.6, 0.2, 0.1, 0.1]),
    "product_detail": (["product_detail", "cart", "category_listing", "search", "home"], [0.3, 0.3, 0.2, 0.1, 0.1]),
    "cart": (["checkout", "product_detail", "category_listing", "home"], [0.6, 0.2, 0.1, 0.1]),
    "checkout": (["confirmation", "cart", "home"], [0.8, 0.1, 0.1]),
    "confirmation": (["home", "product_detail", "category_listing"], [0.6, 0.2, 0.2]),
}


def determine_page_type(position, previous_pages):
    if position == 0:
        return random.choice(["home", "search", "category_listing"])
    if not previous_pages:
        return "home"
    prev_page = previous_pages[-1]["page_type"]
    if prev_page in TRANSITIONS:
        choices, weights = TRANSITIONS[prev_page]
        return random.choices(choices, weights=weights)[0]
    return "home"


def get_page_content(page_type, products_list, category_by_id):
    """Return (product, category) for a page. O(1) category lookup instead of a linear scan."""
    if page_type == "product_detail":
        for _ in range(10):
            product = random.choice(products_list)
            if product["is_active"] and product["current_stock"] > 0:
                return product, category_by_id[product["category_id"]]
        product = random.choice(products_list)
        return product, category_by_id[product["category_id"]]
    if page_type == "category_listing":
        category = random.choice(categories)
        return None, category
    return None, None


# --------------------------------------------------------------------------
# Categories
# --------------------------------------------------------------------------
categories = []
for cat_id in range(NUM_CATEGORIES):
    category = {"category_id": f"cat_{cat_id:03d}", "name": fake.company(), "subcategories": []}
    for sub_id in range(random.randint(3, 5)):
        category["subcategories"].append({
            "subcategory_id": f"sub_{cat_id:03d}_{sub_id:02d}",
            "name": fake.bs(),
            "profit_margin": round(random.uniform(0.1, 0.4), 2),
        })
    categories.append(category)
category_by_id = {c["category_id"]: c for c in categories}
print(f"Generated {len(categories)} categories")

# --------------------------------------------------------------------------
# Products
# --------------------------------------------------------------------------
products = []
product_creation_start = datetime.datetime.now() - datetime.timedelta(days=TIMESPAN_DAYS * 2)
for prod_id in range(NUM_PRODUCTS):
    category = random.choice(categories)
    subcategory = random.choice(category["subcategories"])          # fix #1
    base_price = round(random.uniform(5, 500), 2)
    initial_date = fake.date_time_between(
        start_date=product_creation_start,
        end_date=product_creation_start + datetime.timedelta(days=TIMESPAN_DAYS // 3))
    price_history = [{"price": base_price, "date": initial_date.isoformat()}]
    for _ in range(random.randint(0, 2)):
        price_change_date = fake.date_time_between(start_date=initial_date, end_date="now")
        new_price = round(base_price * random.uniform(0.8, 1.2), 2)
        price_history.append({"price": new_price, "date": price_change_date.isoformat()})
        initial_date = price_change_date
    price_history.sort(key=lambda x: x["date"])
    products.append({
        "product_id": f"prod_{prod_id:05d}",
        "name": fake.catch_phrase().title(),
        "category_id": category["category_id"],
        "subcategory_id": subcategory["subcategory_id"],
        "base_price": price_history[-1]["price"],
        "current_stock": random.randint(10, 1000),
        "is_active": random.choices([True, False], weights=[0.95, 0.05])[0],
        "price_history": price_history,
        "creation_date": price_history[0]["date"],
    })
print(f"Generated {len(products)} products")

# --------------------------------------------------------------------------
# Users
# --------------------------------------------------------------------------
users = []
for user_id in range(NUM_USERS):
    reg_date = fake.date_time_between(start_date=f"-{TIMESPAN_DAYS * 3}d", end_date=f"-{TIMESPAN_DAYS}d")
    users.append({
        "user_id": f"user_{user_id:06d}",
        "geo_data": {"city": fake.city(), "state": fake.state_abbr(), "country": fake.country_code()},
        "registration_date": reg_date.isoformat(),
        "last_active": fake.date_time_between(start_date=reg_date, end_date="now").isoformat(),
    })
print(f"Generated {len(users)} users")


# --------------------------------------------------------------------------
# Streaming JSON-array writer for sessions (fix #2)
# --------------------------------------------------------------------------
class ChunkedJsonArrayWriter:
    """Writes records into prefix_0.json, prefix_1.json ... each a valid JSON array."""

    def __init__(self, out_dir, prefix, chunk_size):
        self.out_dir, self.prefix, self.chunk_size = out_dir, prefix, chunk_size
        self.file_idx, self.in_chunk, self.fh, self.total = 0, 0, None, 0

    def write(self, record):
        if self.fh is None:
            path = os.path.join(self.out_dir, f"{self.prefix}_{self.file_idx}.json")
            self.fh = open(path, "w")
            self.fh.write("[")
        elif self.in_chunk:
            self.fh.write(",")
        self.fh.write(json.dumps(record))
        self.in_chunk += 1
        self.total += 1
        if self.in_chunk >= self.chunk_size:
            self._close_chunk()

    def _close_chunk(self):
        if self.fh:
            self.fh.write("]")
            self.fh.close()
            self.fh, self.in_chunk = None, 0
            self.file_idx += 1

    def close(self):
        self._close_chunk()


# --------------------------------------------------------------------------
# Sessions & transactions (simulation logic unchanged)
# --------------------------------------------------------------------------
def make_transaction(user_id, session_id, timestamp, items, payment_methods, statuses):
    subtotal = round(sum(i["subtotal"] for i in items), 2)
    discount = 0
    if random.random() < 0.2:
        discount = round(subtotal * random.choice([0.05, 0.1, 0.15, 0.2]), 2)
    return {
        "transaction_id": generate_transaction_id(),
        "session_id": session_id,
        "user_id": user_id,
        "timestamp": timestamp,
        "items": items,
        "subtotal": subtotal,
        "discount": discount,
        "total": round(subtotal - discount, 2),
        "payment_method": random.choice(payment_methods),
        "status": random.choice(statuses),
    }


inventory = InventoryManager(products)
session_writer = ChunkedJsonArrayWriter(args.out, "sessions", CHUNK_SIZE)
transactions = []
transaction_counter = session_counter = iteration = 0
t0 = time.time()

print("Generating sessions and transactions...")
while (session_counter < NUM_SESSIONS or transaction_counter < NUM_TRANSACTIONS) and iteration < MAX_ITERATIONS:
    iteration += 1

    if session_counter < NUM_SESSIONS:
        user = random.choice(users)
        session_id = generate_session_id()
        session_start = fake.date_time_between(start_date=f"-{TIMESPAN_DAYS}d", end_date="now")
        session_duration = random.randint(30, 3600)

        page_views, viewed_products, cart_contents = [], set(), {}
        time_slots = sorted([0] + [random.randint(1, session_duration - 1)
                                   for _ in range(random.randint(3, 15))] + [session_duration])

        for i in range(len(time_slots) - 1):
            view_duration = time_slots[i + 1] - time_slots[i]
            page_type = determine_page_type(i, page_views)
            product, category = get_page_content(page_type, products, category_by_id)

            if page_type == "product_detail" and product:
                pid = product["product_id"]
                viewed_products.add(pid)
                if random.random() < 0.3:
                    if pid not in cart_contents:
                        cart_contents[pid] = {"quantity": 0, "price": product["base_price"]}
                    max_possible = min(3, inventory.get_product(pid)["current_stock"] - cart_contents[pid]["quantity"])
                    if max_possible > 0:
                        cart_contents[pid]["quantity"] += random.randint(1, max_possible)

            page_views.append({
                "timestamp": (session_start + datetime.timedelta(seconds=time_slots[i])).isoformat(),
                "page_type": page_type,
                "product_id": product["product_id"] if product else None,
                "category_id": category["category_id"] if category else None,
                "view_duration": view_duration,
            })

        converted = False
        if cart_contents and any(p["page_type"] in ("checkout", "confirmation") for p in page_views):
            converted = random.random() < 0.7

        session_geo = user["geo_data"].copy()
        session_geo["ip_address"] = fake.ipv4()

        session_writer.write({
            "session_id": session_id,
            "user_id": user["user_id"],
            "start_time": session_start.isoformat(),
            "end_time": (session_start + datetime.timedelta(seconds=session_duration)).isoformat(),
            "duration_seconds": session_duration,
            "geo_data": session_geo,
            "device_profile": {
                "type": random.choice(["mobile", "desktop", "tablet"]),
                "os": random.choice(["iOS", "Android", "Windows", "macOS"]),
                "browser": random.choice(["Chrome", "Safari", "Firefox", "Edge"]),
            },
            "viewed_products": sorted(viewed_products),
            "page_views": page_views,
            "cart_contents": {k: v for k, v in cart_contents.items() if v["quantity"] > 0},
            "conversion_status": "converted" if converted else "abandoned" if cart_contents else "browsed",
            "referrer": random.choice(["direct", "email", "social", "search_engine", "affiliate"]),
        })
        session_counter += 1

        if converted and transaction_counter < NUM_TRANSACTIONS:
            items, valid = [], True
            for pid, details in cart_contents.items():
                qty = details["quantity"]
                if qty > 0:
                    if inventory.update_stock(pid, qty):
                        items.append({"product_id": pid, "quantity": qty, "unit_price": details["price"],
                                      "subtotal": round(qty * details["price"], 2)})
                    else:
                        valid = False
                        break
            if valid and items:
                transactions.append(make_transaction(
                    user["user_id"], session_id,
                    (session_start + datetime.timedelta(seconds=session_duration)).isoformat(),
                    items, ["credit_card", "paypal", "apple_pay", "crypto"], ["completed"]))
                transaction_counter += 1

    # "offline"/app transactions with no session (unchanged)
    if transaction_counter < NUM_TRANSACTIONS and random.random() < 0.2:
        user = random.choice(users)
        items = []
        for product in random.sample(products, k=min(3, len(products))):
            if product["is_active"]:
                qty = random.randint(1, 3)
                if inventory.update_stock(product["product_id"], qty):
                    items.append({"product_id": product["product_id"], "quantity": qty,
                                  "unit_price": product["base_price"],
                                  "subtotal": round(qty * product["base_price"], 2)})
        if items:
            transactions.append(make_transaction(
                user["user_id"], None,
                fake.date_time_between(start_date=f"-{TIMESPAN_DAYS}d", end_date="now").isoformat(),
                items, ["credit_card", "paypal", "bank_transfer", "gift_card"],
                ["completed", "processing", "shipped", "delivered"]))
            transaction_counter += 1

    if iteration % 50000 == 0:
        print(f"Progress: {session_counter:,}/{NUM_SESSIONS:,} sessions, "
              f"{transaction_counter:,}/{NUM_TRANSACTIONS:,} transactions ({time.time() - t0:.0f}s)")

session_writer.close()

# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------
print("Saving datasets...")
for name, data in [("users", users), ("products", list(inventory.products.values())),
                   ("categories", categories), ("transactions", transactions)]:
    with open(os.path.join(args.out, f"{name}.json"), "w") as f:
        json.dump(data, f)

print(f"""
Dataset generation complete in {time.time() - t0:.0f}s -> {args.out}
- Sessions: {session_writer.total:,} (target: {NUM_SESSIONS:,}) in {session_writer.file_idx} file(s)
- Transactions: {len(transactions):,} (target: {NUM_TRANSACTIONS:,})
- Remaining stock units: {sum(p['current_stock'] for p in inventory.products.values()):,}
""")
