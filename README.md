# Distributed Multi-Model Analytics for E-commerce Data
AUCA Big Data Analytics, Final Project (Oct 2026): **MongoDB + HBase + Apache Spark**

The project generates a synthetic e-commerce dataset, stores it in a **document store** (MongoDB) and a **wide-column store** (HBase), processes it with **Spark** (cleaning, recommendations, cohorts, Spark SQL), runs **integrated cross-store analytics** (Customer Lifetime Value and funnel conversion), and produces **charts and a technical report**.

```
auca-ecommerce-analytics/
├── config.py                      # paths + connection settings (all overridable by env vars)
├── requirements.txt / docker-compose.yml / run_all.sh
├── common/json_stream.py          # streaming reader for the big JSON-array files
├── data_generation/
│   ├── dataset_generator_original.py   # the script as provided
│   └── dataset_generator.py            # same simulation + fixes (see below)
├── mongodb/
│   ├── load_mongodb.py            # document model + bulk load + indexes
│   ├── aggregations.py            # 4 aggregation pipelines (python)
│   └── aggregations.js            # same pipelines for mongosh
├── hbase/
│   ├── create_tables.hbase        # schema (row keys, column families) - HBase shell
│   ├── hbase_client.py            # happybase connection + SQLite emulator + row-key helpers
│   ├── load_hbase.py              # sessions -> user_sessions, daily metrics -> product_metrics
│   ├── query_hbase.py             # 5 example queries (python)
│   └── sample_queries.hbase       # the same queries for the HBase shell
├── spark/
│   ├── spark_utils.py             # SparkSession + explicit JSON schemas
│   ├── 01_clean_normalize.py      # raw JSON -> 9 clean Parquet tables + data-quality report
│   ├── 02_recommendations.py      # bought-together / viewed-together / category affinity
│   ├── 03_cohort_analysis.py      # registration-month cohorts
│   └── 04_spark_sql_analytics.py  # complex Spark SQL + "MongoDB/HBase-shaped" SQL joins
├── integration/
│   ├── sources.py                 # one loader per dataset: files | mongo | hbase | hbase-emulator
│   ├── clv_analysis.py            # integrated query 1: CLV + RFM segmentation
│   └── funnel_analysis.py         # integrated query 2: view -> cart -> checkout -> purchase
├── visualization/make_charts.py   # 7 static PNG figures
├── report/technical_report.html   # report source  -> report/Technical_Report.pdf
└── output/                        # every result as CSV (+ sample query printouts)
```

---

## 1. Setup

**Prerequisites:** Python 3.10+, Java 17 (or 11/21) for Spark, Docker Desktop (for MongoDB and HBase).

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
docker compose up -d                                   # MongoDB on 27017, HBase Thrift on 9090
docker ps                                              # wait until both containers are "Up"
```
HBase's master UI is at http://localhost:16010. It takes about 30-60 s after start before the Thrift server accepts connections.

## 2. Run everything

```bash
./run_all.sh                 # live MongoDB + HBase, 10 % scale (200k sessions) - about 6 min
./run_all.sh --offline       # no servers needed: mongomock + SQLite HBase emulator
SCALE=1.0 ./run_all.sh       # full brief size: 2M sessions / 500k transactions (~4 GB JSON)
```
On Windows, run the commands inside `run_all.sh` one by one (or use Git Bash / WSL).

## 3. Step by step (what each step does and why)

### Step 1: Generate the data
```bash
python data_generation/dataset_generator.py --out data/raw --scale 0.1
```
The simulation (page-flow probabilities, 30 % add-to-cart, 70 % checkout completion, stock checks, discounts) is **unchanged** from the provided script. I made four engineering fixes:
1. every product now gets a `subcategory_id`. The brief's data dictionary has this field, but the original script never set it.
2. sessions are **streamed** to `sessions_N.json` (100k per file) instead of kept in RAM. The original needs more than 10 GB at 2M sessions.
3. IDs come from the seeded RNG instead of `uuid4()`, so the IDs are reproducible.
4. `--scale` lets you test quickly.

### Step 2: MongoDB (Part 1)
```bash
python mongodb/load_mongodb.py --sessions-limit 50000
python mongodb/aggregations.py                  # or: mongosh ecommerce mongodb/aggregations.js
```
| Collection | Modelling choice | Why |
|---|---|---|
| `categories` | subcategories **embedded** | small, bounded, always read together |
| `products` | **extended reference** to category/subcategory (name, margin) + embedded `price_history` | catalogue pages and margin maths need no `$lookup` |
| `transactions` | line items **embedded**, each with product name/category/subcategory | one atomic document per order; revenue-by-category is just `$unwind/$group` |
| `users` | **computed/subset** `purchase_summary` (totals, favourite category, last 5 orders) | the most-asked facts in one read without unbounded arrays |
| `sessions` | sample of full journeys | shows "whole journey in one document"; the full click-stream is in HBase |

Pipelines: (1) top-selling products, (2) revenue and estimated profit by category and month, (3) user segmentation (`$facet` + `$bucket`), (4) journey funnel by referrer.

### Step 3: HBase (Part 1)
```bash
Get-Content hbase/create_tables.hbase | docker exec -i hbase hbase shell -n     # bash: docker exec -i hbase hbase shell -n < hbase/create_tables.hbase
python hbase/load_hbase.py                      # add --limit 100000 for a subset
python hbase/query_hbase.py --user user_000042 --product prod_00123
Get-Content hbase/sample_queries.hbase | docker exec -i hbase hbase shell -n   # bash: ... < hbase/sample_queries.hbase
```
* **`user_sessions`**: row key `user_id|reverse_ts|session_id`, where `reverse_ts = 9999999999999 - epoch_ms`. A user's sessions are contiguous and sorted newest first. Column families: `info` (session header), `pv` (one column per page view, sparse), `cart` (one column per product).
* **`product_metrics`**: row key `product_id|yyyymmdd`, family `m` (views, cart_adds, purchases, units_sold, revenue_cents). A product's history or a date range is a single range scan.

### Step 4: Spark batch processing (Part 2)
```bash
python spark/01_clean_normalize.py     # -> data/clean/*.parquet + output/data_quality_report.csv
python spark/02_recommendations.py     # -> output/reco_*.csv
python spark/03_cohort_analysis.py     # -> output/cohort_*.csv
python spark/04_spark_sql_analytics.py # -> output/sql_*.csv
```
The cleaning job uses explicit schemas, de-duplicates, drops rows with missing keys or invalid values, normalises enums and codes, repairs `conversion_status`, and **flags** inconsistencies such as converted sessions that have no order. The Spark SQL job also builds views shaped like the MongoDB documents and HBase rows (`mongo_users`, `hbase_user_sessions`, ...) and joins them in SQL.

### Step 5: Integrated analytics (Part 3)
```bash
python integration/clv_analysis.py    --mongo mongo --hbase hbase
python integration/funnel_analysis.py --mongo mongo --hbase hbase
# without servers: --mongo files --hbase hbase-emulator   (or files for both)
```
`integration/sources.py` returns the same DataFrame whether the data comes from Parquet, MongoDB (aggregation pushed down to the server) or HBase (Thrift scans). The analysis code therefore doesn't depend on where the data is stored.

### Step 6: Charts and report (Part 4)
```bash
python visualization/make_charts.py    # -> report/figures/fig1..fig7.png
```
The editable report is `report/Technical_Report.docx`. Yellow highlights mark the places you need to fill in or check. A PDF version (`report/Technical_Report.pdf`, built from `report/technical_report.html`) is also included. To rebuild the Word file after re-running the analysis, run `node report/build_report_docx.js`.

## 4. Configuration
Environment variables: `MONGO_URI` (default `mongodb://localhost:27017`), `MONGO_DB` (`ecommerce`), `HBASE_HOST` (`localhost`), `HBASE_PORT` (`9090`), `SPARK_MASTER` (`local[*]`), `SPARK_DRIVER_MEMORY` (`4g`), `SHUFFLE_PARTITIONS` (`16`), `HBASE_EMULATE=1`.

## 5. Troubleshooting
* **`happybase` TTransportException**: HBase Thrift isn't up yet. Wait a minute, check `docker logs hbase`, and make sure port 9090 is mapped.
* **Spark "Java gateway process exited"**: install a JDK and set `JAVA_HOME`.
* **Out of memory at SCALE=1.0**: raise `SPARK_DRIVER_MEMORY=6g` and `SHUFFLE_PARTITIONS=64`, or use `--limit` for the HBase load.
* **Results differ slightly between runs**: the generator anchors dates on "now", so boundary days shift. Aggregate figures stay within a fraction of a percent.
