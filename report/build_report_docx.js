// Builds report/Technical_Report.docx (editable Word version of the technical report)
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, ImageRun, LevelFormat, PageBreak, Footer, PageNumber,
  TableOfContents, Header,
} = require("docx");

const ROOT = "/home/claude/auca-ecommerce-analytics";
const FIG = path.join(ROOT, "report", "figures");
const W = 9638; // content width in DXA (A4, 2 cm margins)
const FONT = "Calibri", MONO = "Consolas";
const BLUE = "2A78D6";

// ---------- inline mini-markup:  **bold**  `code`  ==highlight (to fill/check)==  *italic*
function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|==[^=]+==|\*[^*]+\*)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ text: t.slice(2, -2), bold: true, ...base }));
    else if (t.startsWith("`")) out.push(new TextRun({ text: t.slice(1, -1), font: MONO, size: 18, ...base }));
    else if (t.startsWith("==")) out.push(new TextRun({ text: t.slice(2, -2), highlight: "yellow", bold: true, ...base }));
    else out.push(new TextRun({ text: t.slice(1, -1), italics: true, ...base }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}
const P = (t, o = {}) => new Paragraph({ children: runs(t), spacing: { after: 100 }, alignment: AlignmentType.JUSTIFIED, ...o });
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const B = (t) => new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: runs(t), spacing: { after: 60 } });
const N = (t) => new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: runs(t), spacing: { after: 60 } });
const PB = () => new Paragraph({ children: [new PageBreak()] });

function CODE(text) {
  return text.replace(/\s+$/, "").split("\n").map((line, i, arr) => new Paragraph({
    children: [new TextRun({ text: line.length ? line : " ", font: MONO, size: 15 })],
    shading: { type: ShadingType.CLEAR, fill: "F4F4F2" },
    spacing: { before: 0, after: i === arr.length - 1 ? 120 : 0, line: 240 },
    indent: { left: 120, right: 120 },
  }));
}

const border = { style: BorderStyle.SINGLE, size: 4, color: "D6D5D0" };
const borders = { top: border, bottom: border, left: border, right: border };
function TABLE(header, rows, widthsPct) {
  const widths = widthsPct.map(p => Math.round(W * p));
  widths[widths.length - 1] += W - widths.reduce((a, b) => a + b, 0);
  const cell = (t, i, head) => new TableCell({
    borders, width: { size: widths[i], type: WidthType.DXA },
    shading: head ? { type: ShadingType.CLEAR, fill: "EEF4FC" } : undefined,
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: [new Paragraph({ children: runs(String(t), { size: 17, bold: head || undefined }) })],
  });
  return new Table({
    width: { size: W, type: WidthType.DXA }, columnWidths: widths,
    rows: [new TableRow({ tableHeader: true, children: header.map((h, i) => cell(h, i, true)) }),
           ...rows.map(r => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, i, false)) }))],
  });
}
const SP = () => new Paragraph({ children: [], spacing: { after: 60 } });

function CALLOUT(lines, fill = "FFF8D6", edge = "E0B400") {
  return new Table({
    width: { size: W, type: WidthType.DXA }, columnWidths: [W],
    rows: [new TableRow({ children: [new TableCell({
      width: { size: W, type: WidthType.DXA },
      borders: { top: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" }, bottom: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
                 right: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" }, left: { style: BorderStyle.SINGLE, size: 24, color: edge } },
      shading: { type: ShadingType.CLEAR, fill }, margins: { top: 100, bottom: 100, left: 160, right: 160 },
      children: lines,
    })] })],
  });
}

function pngSize(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}
function FIGURE(file, caption, widthIn = 6.3) {
  const f = path.join(FIG, file), s = pngSize(f);
  const wpx = widthIn * 96, hpx = wpx * s.h / s.w;
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 120 },
      children: [new ImageRun({ type: "png", data: fs.readFileSync(f), transformation: { width: wpx, height: hpx },
        altText: { title: caption, description: caption, name: file } })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 160 },
      children: runs(caption, { size: 17, italics: true, color: "52514E" }) }),
  ];
}
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");

// ====================================================================== CONTENT
const c = [];

// ---------- title page
c.push(new Paragraph({ spacing: { before: 2200, after: 200 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "Distributed Multi-Model Analytics for E-commerce Data", bold: true, size: 44, color: "1B1B1A" })] }));
c.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 600 },
  children: [new TextRun({ text: "MongoDB  ·  HBase  ·  Apache Spark", size: 28, color: BLUE })] }));
c.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: runs("AUCA Big Data Analytics - Final Project (Technical Report)", { size: 24 }) }));
c.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: runs("Author: Godfrey Mushambo", { size: 24 }) }));
c.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: runs("Student ID: ==[enter your student ID]==", { size: 24 }) }));
c.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: runs("Lecturer: ==[enter lecturer name]==", { size: 24 }) }));
c.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: runs("GitHub repository: ==[paste your repository URL]==", { size: 24 }) }));
c.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: runs("Submission date: ==[e.g. 11 November 2026]==", { size: 24 }) }));
c.push(PB());

// ---------- reviewer checklist (to delete before submitting)
c.push(H1("Before you submit - items to review (delete this page)"));
c.push(P("Everything highlighted in ==yellow== in this document needs your attention: fill in a placeholder, confirm a number after your own run, or add a screenshot. Work through this list, then remove the highlights and this page."));
c.push(TABLE(["#", "What to do", "Where"], [
  ["1", "Fill in student ID, lecturer, repository URL and date.", "Title page"],
  ["2", "Start the databases (`docker compose up -d`) and run `./run_all.sh` in **live** mode so MongoDB and HBase are used for real (the figures in this draft were produced in offline mode).", "Sections 1, 9"],
  ["3", "Compare the key numbers with your `output/*.csv` files. With the same seed and scale they should match closely (dates are anchored on the day you run the generator, so small differences are normal). Update any that differ.", "Sections 1, 5, 6"],
  ["4", "Re-generate the charts (`python visualization/make_charts.py`) and replace the images if your numbers changed (right-click image → Change Picture).", "Section 6"],
  ["5", "Add the screenshots the lecturer will look for: MongoDB Compass or mongosh output of a pipeline, HBase shell `scan` output, and the HBase master UI listing the two tables.", "Placeholders in sections 3 and Appendix C"],
  ["6", "Decide the final dataset scale. 10% (200k sessions) is used here; if you run full scale (`SCALE=1.0`), change the scale statement and all numbers.", "Section 1"],
  ["7", "If you ran live mode, rewrite the 'Infrastructure' limitation bullet to say MongoDB 7 and HBase ran in Docker.", "Section 9"],
  ["8", "Update the table of contents: right-click it → Update Field → Update entire table.", "Contents"],
  ["9", "Export to PDF for submission (File → Save As → PDF). Target length is 6-8 pages excluding title page and appendices.", "-"],
], [0.05, 0.72, 0.23]));
c.push(PB());

// ---------- TOC
c.push(new Paragraph({ children: [new TextRun({ text: "Contents", bold: true, size: 32, color: BLUE })], spacing: { after: 120 } }));
c.push(new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-2" }));
c.push(PB());

// ---------- 1 executive summary
c.push(H1("1. Executive summary"));
c.push(P("This project builds a polyglot analytics platform for a synthetic e-commerce business. **MongoDB** holds the document-shaped business entities (catalogue, customers, orders), **HBase** holds the high-volume, time-ordered click-stream and daily product metrics, and **Apache Spark** cleans the raw data, runs the heavy batch analytics and joins across both stores. All numbers below come from a reproducible run of the pipeline (seed 42, ==scale 0.1: 10,000 users, 5,000 products, 200,000 sessions, 50,000 transactions, 90 days==; `./run_all.sh`)."));
c.push(TABLE(["Net revenue", "Sessions ending in a purchase", "Checkout abandonment", "CLV held by top 17% of customers"],
  [["$53.2M (50,000 orders, AOV $1,064)", "12.6%", "57%", "28%"]], [0.25, 0.25, 0.25, 0.25]));
c.push(SP());
c.push(B("**The funnel leaks after the cart, not before it.** 99% of sessions view a product and 66% add to cart, but only 45% of carts reach checkout and 43% of checkouts produce an order: about 33,000 checkout abandoners, worth up to ~$25M at the $771 average web order."));
c.push(B("**Stock-outs, not demand, explain the link between product views and sales.** Across all products views and units sold correlate at r = 0.70, but among in-stock products r = 0.14; the 209 products that sold out lost ~60% of their page views."));
c.push(B("**Value is concentrated and partly at risk.** RFM segmentation finds 1,727 'Champions' (27.9% of estimated CLV) and 1,079 high-value customers who have not bought for ~27 days (15.7% of CLV), the obvious retention-campaign target."));
c.push(B("**Revenue is flat; profit is not.** Daily revenue is stable (~$590k/day, s.d. $28k) and category revenue spans only -15% to +18% around the mean, but subcategory margins range from 18% to 36%, so category profit differs two-fold."));
c.push(B("**Data quality matters across systems.** 15,552 sessions (38% of those flagged 'converted') have no matching transaction, detected only by reconciling HBase sessions with MongoDB orders."));

// ---------- 2 architecture
c.push(H1("2. System architecture"));
c.push(TABLE(["Layer", "Component", "Role"], [
  ["Source", "`dataset_generator.py`", "Generates users, products, categories, sessions_N.json and transactions as JSON arrays"],
  ["Operational stores", "**MongoDB** (document)", "products, categories, users (+ purchase_summary), transactions (+ embedded items), sample of sessions"],
  ["", "**HBase** (wide-column)", "user_sessions (row key user|reverse_ts|session) and product_metrics (row key product|yyyymmdd)"],
  ["Processing", "**Apache Spark**", "01 clean & normalise → Parquet lake; 02 recommendations; 03 cohorts; 04 Spark SQL; integration jobs (CLV, funnel)"],
  ["Access layer", "`integration/sources.py`", "Same DataFrame from Parquet, MongoDB (pipeline pushed down) or HBase (Thrift scans)"],
  ["Presentation", "matplotlib, CSV, this report", "7 static figures and result tables"],
], [0.18, 0.27, 0.55]));
c.push(SP());
c.push(P("Raw JSON is loaded into the two operational stores by Python loaders and, in parallel, into Spark which writes a clean Parquet 'lake'. Analytical jobs read through a single access layer (`integration/sources.py`) that returns identical DataFrames whether the data comes from Parquet, MongoDB (via an aggregation pipeline pushed down to the server) or HBase (via Thrift prefix/range scans). This keeps the analysis code independent of storage. For development without servers, an offline mode uses *mongomock* and a SQLite-backed HBase emulator that preserves sorted row-key semantics."));
c.push(P("==[Optional: insert an architecture diagram here - e.g. draw the table above as boxes and arrows in draw.io or PowerPoint.]=="));
c.push(H2("2.1 Changes to the provided generator"));
c.push(P("The simulation logic is unchanged; four engineering fixes were needed: (1) products now receive the `subcategory_id` that the brief's data dictionary shows but the original never assigned; (2) sessions are streamed to `sessions_N.json` in 100k chunks instead of being held in memory (the original needs >10 GB RAM at 2M sessions); (3) IDs come from the seeded RNG instead of `uuid4`, making runs reproducible; (4) a `--scale` flag. Full scale (2M sessions, ~4 GB) generates in about 4 minutes."));

// ---------- 3 data modelling
c.push(H1("3. Data modelling (Part 1)"));
c.push(H2("3.1 MongoDB document model"));
c.push(TABLE(["Collection", "Shape", "Pattern & justification"], [
  ["categories", "category + `subcategories[]` (3-5) with profit_margin", "Embedding: small, bounded, always read together; one read returns the whole hierarchy."],
  ["products", "product + `category{id,name}` + `subcategory{id,name,profit_margin}` + `price_history[]`", "Extended reference: copies the rarely-changing names/margin so catalogue pages and margin maths need no $lookup. Price history is bounded (1-3 points), so it is embedded."],
  ["transactions", "order header + `items[]`, each with product_name, category_id, subcategory_id; timestamp as BSON Date", "Line items live and die with the order (atomic single-document writes). Denormalised category ids make revenue-by-category a pure $unwind/$group."],
  ["users", "profile + geo + `purchase_summary{total_spent, order_count, avg_order_value, favorite_category, recent_orders[5]}`", "Computed + subset pattern: the most-requested facts are pre-aggregated; full history stays in transactions (unbounded arrays avoided)."],
  ["sessions (sample)", "full journey with `page_views[]` and `cart_contents[]`", "Shows the 'whole journey in one document' query; the complete click-stream lives in HBase."],
], [0.15, 0.4, 0.45]));
c.push(SP());
c.push(P("Indexes back each query pattern: `{user_id:1, timestamp:-1}` (order history), `{timestamp:1}` (period revenue), multikey `{items.product_id:1}` (product sales), `{purchase_summary.total_spent:-1}` (top customers) and `{category.category_id:1, is_active:1}` (catalogue browsing). Four aggregation pipelines are implemented (`mongodb/aggregations.py` and `.js`, listed in Appendix B):"));
c.push(N("Top-selling products: `$unwind` → `$group` → `$lookup` for current stock."));
c.push(N("Revenue and estimated profit per category per month, matching each item to its embedded subcategory margin with `$filter`."));
c.push(N("User segmentation by purchase frequency and spend with `$facet` + `$bucket` in a single round trip (e.g. 3,550 users with 6-9 orders spend $7,351 on average; 313 users with 10+ orders spend $11,449)."));
c.push(N("A journey funnel over the embedded `page_views` array, by referrer."));
c.push(P("==[Insert screenshot: output of one aggregation pipeline in MongoDB Compass or mongosh.]=="));

c.push(H2("3.2 HBase wide-column model"));
c.push(TABLE(["Table", "Row key", "Column families", "Access patterns served"], [
  ["user_sessions", "`user_id|reverse_ts|session_id`  (reverse_ts = 9999999999999 - epoch_ms)", "**info**: session header (15 cells); **pv**: one column per page view, qualifier 000..015; **cart**: qualifier = product_id, value qty|price", "Latest N sessions of a user = prefix scan, newest first; sessions in a time window = bounded STARTROW/STOPROW scan; one session = point get."],
  ["product_metrics", "`product_id|yyyymmdd`", "**m**: views, cart_adds, purchases, units_sold, revenue_cents", "A product's daily history or a date range is one contiguous scan; streaming updates use atomic incr counters."],
], [0.15, 0.25, 0.3, 0.3]));
c.push(SP());
c.push(P("**Why this design.** Placing `user_id` first makes a user's activity contiguous on disk; reversing the timestamp makes 'most recent activity' the first rows returned, so no sort is needed. Column families are split by access pattern: listing sessions reads only the small `info` family, while the larger, variable-width `pv` family (3-15 cells) is read only when a journey is drilled into. Sparse columns cost nothing: most sessions have 0-2 `cart` cells. `VERSIONS=1` (events are immutable), a ROW bloom filter for point gets, a 180-day TTL on `pv`, and pre-split regions on user-id ranges complete the schema (`hbase/create_tables.hbase`, Appendix B). The load wrote 200,000 session rows and 355,305 product-day rows. Example queries:"));
c.push(...CODE(`scan 'user_sessions', {ROWPREFIXFILTER => 'user_000042|', COLUMNS => ['info'], LIMIT => 5}
scan 'user_sessions', {STARTROW => 'user_000042|8209187200000',
                       STOPROW  => 'user_000042|8211779199999~'}          # sessions in Sept 2026
scan 'product_metrics', {STARTROW => 'prod_00123|20260901', STOPROW => 'prod_00123|20261001'}`));
c.push(P("==[Insert screenshot: HBase shell output of the first scan above, and the HBase master UI (http://localhost:16010) showing both tables.]=="));

c.push(H2("3.3 Why data went to MongoDB vs HBase"));
c.push(TABLE(["Criterion", "MongoDB", "HBase"], [
  ["Data", "Entities with rich nested structure and modest volume (catalogue, customers, orders)", "Append-only events at very high volume (2M sessions, ~20M page views at full scale), daily counters"],
  ["Queries", "Ad-hoc filters, secondary indexes, aggregation framework, $lookup", "Known access path by key: per-user timelines, per-product time ranges"],
  ["Schema", "Flexible documents, validation per collection", "Sparse, variable columns per row; row-key design is the 'index'"],
  ["Writes", "Transactional per document (an order and its items together)", "Massive write throughput, atomic counters, region auto-sharding"],
], [0.16, 0.42, 0.42]));

// ---------- 4 spark
c.push(H1("4. Spark processing pipeline (Part 2)"));
c.push(P("**01_clean_normalize.py** reads every JSON file (sessions via the glob `sessions_*.json`) with **explicit schemas**, avoiding a second inference pass over the multi-GB session files and type drift, and writes nine Parquet tables: users, categories (hierarchy flattened to one row per subcategory), products (joined with margin), price_history, sessions (partitioned by date, with funnel flags), page_views (exploded with `posexplode`, partitioned by date), cart_items (the `cart_contents` object is read as a MapType and exploded), transactions (with reconciliation flags) and transaction_items (discount pro-rated per line, enriched with category and margin via a broadcast join)."));
c.push(P("Cleaning rules: de-duplication on keys; dropping rows with missing keys or unparseable timestamps; trimming and case-normalising enums and geo codes; clamping negatives; filling missing descriptive values; repairing `conversion_status` ('abandoned' with an empty cart → 'browsed'); and *flagging*, not dropping, logical inconsistencies. Every check is counted in `output/data_quality_report.csv`. The generated data proved structurally clean (0 duplicates, 0 orphans, 0 total mismatches); the one material issue was the 15,552 converted sessions without an order."));
c.push(P("**02_recommendations.py** computes association rules (support, confidence, lift, top-5 per product via a window) for 'bought together' (self-join on transaction id with x < y) and 'viewed together' (pairs built inside each session's `viewed_products` array with the higher-order functions transform/filter, which avoids a shuffle-heavy join), plus category-level affinity. **03_cohort_analysis.py** groups users by registration month and tracks buyers, revenue, retention and cumulative revenue per member by months since registration."));
c.push(P("**04_spark_sql_analytics.py** runs five complex SQL queries: top-3 products per category (CTE + RANK); funnel by device/referrer with ROLLUP; daily revenue with a 7-day RANGE window and week-over-week LAG; price-change impact using MAX_BY over exploded price history; viewed-vs-sold ranks. In Part B, views shaped exactly like MongoDB documents (`mongo_users` with a nested purchase_summary, `mongo_transactions` with an items array queried through LATERAL VIEW explode - Spark's $unwind) and HBase rows (`rowkey` + `info:*` columns, user id parsed with SPLIT) are joined in SQL. An example is in Appendix B."));
c.push(P("**Optimisations considered:** explicit schemas; Parquet + Snappy with date partitioning (partition pruning for time-range queries); broadcast joins for the 5,000-product and 109-subcategory dimensions; adaptive query execution (coalescing shuffle partitions); `cache()` only for DataFrames reused several times; array functions instead of joins for co-occurrence; a minimum pair count to prune the long tail before ranking."));

// ---------- 5 integration
c.push(H1("5. Integrated analytics (Part 3)"));
c.push(H2("5.1 Customer Lifetime Value (integration/clv_analysis.py)"));
c.push(P("**Business question:** which customers are worth most over their expected lifetime, how engaged are they, and which segment should get retention spend?"));
c.push(P("**Sources:** user profiles and orders from MongoDB (the $unwind and discount pro-ration are pushed into the aggregation pipeline so only line-item rows cross the network); session engagement from HBase `user_sessions` (frequency, duration, pages, cart rate); margins from the category dimension."));
c.push(P("**Spark steps:** per-user purchase facts; per-user engagement facts; monthly buyer retention estimated from the data (r = 0.825 ⇒ expected lifetime 1/(1-r) = 5.7 months); CLV = AOV × orders per month × gross-margin % × lifetime; RFM quintiles (NTILE) mapped to named segments and CLV quartile tiers."));
c.push(TABLE(["Segment", "Users", "Avg CLV", "Share of CLV", "Recency (days)", "Sessions", "Session→order"], [
  ["Champions", "1,727", "$4,187", "27.9%", "4.1", "21.1", "17.2%"],
  ["At risk - high value", "1,079", "$3,770", "15.7%", "27.0", "20.2", "14.3%"],
  ["Loyal", "1,274", "$3,289", "16.2%", "9.7", "21.1", "17.9%"],
  ["Needs attention", "1,920", "$2,209", "16.4%", "9.2", "19.6", "10.9%"],
  ["New / promising", "1,048", "$1,607", "6.5%", "4.6", "19.0", "9.1%"],
  ["Hibernating", "2,901", "$1,555", "17.4%", "35.2", "19.4", "9.5%"],
], [0.24, 0.11, 0.12, 0.13, 0.14, 0.12, 0.14]));
c.push(SP());
c.push(P("Platinum-tier customers (top CLV quartile) average 20.9 sessions and a 16.2% session-to-order rate versus 19.3 and 9.0% for Bronze: value is driven by *conversion efficiency* far more than by browsing time (correlation of CLV with average session duration is 0.02, with session count 0.13)."));
c.push(H2("5.2 Funnel conversion (integration/funnel_analysis.py)"));
c.push(P("**Business question:** where are shoppers lost, does it differ by device, traffic source or category, and what is the leak worth?"));
c.push(P("**Sources:** journey stages from HBase `user_sessions` (pv and cart families); category views and cart adds from HBase `product_metrics`; purchases from MongoDB transactions as the *source of truth* for the last stage."));
c.push(P("**Spark steps:** scan → per-session stage flags → left join to orders on session_id → stage counts and step conversion; the same by device, referrer, category (views × web purchases) and week. The page-flow is visible in the numbers (Figure 1): 66% add to cart, 45% of carts reach checkout, 43% of checkouts become orders. Device and referrer differences are within ±0.3 percentage points (12.3-12.8% purchase rate), and category view-to-cart rates span only 29.4-30.6%: in this dataset the leak is a *process* problem (checkout), not a channel or assortment problem."));
c.push(P("**Performance considerations.** Through the driver (pymongo/happybase) the integration scans 200k session rows in a few seconds. At full scale the HBase read should use the hbase-spark connector or a snapshot export so that regions are read in parallel by executors, and MongoDB should be read with the Spark connector (partitioned by _id) with filters/aggregations pushed down. Joins are on high-cardinality keys (user_id, session_id) with dimension tables broadcast."));

// ---------- 6 visualisations
c.push(H1("6. Visualisations and insights (Part 4)"));
c.push(...FIGURE("fig3_conversion_funnel.png", "Figure 1 - Session funnel (HBase journeys × MongoDB orders). Step % = conversion from the previous stage.", 6.0));
c.push(...FIGURE("fig6_viewed_vs_sold.png", "Figure 2 - Each dot is a product. Sold-out products lose page views because the storefront stops showing them; among in-stock products, views barely predict sales.", 5.4));
c.push(...FIGURE("fig4_clv_segments.png", "Figure 3 - RFM segments: customers (left) and average estimated CLV with share of total CLV (right).", 6.3));
c.push(...FIGURE("fig2_category_revenue_profit.png", "Figure 4 - Revenue and estimated gross profit by category (MongoDB pipeline 2). Margins range from 18% to 36%.", 6.3));
c.push(...FIGURE("fig7_engagement_vs_spend.png", "Figure 5 - Average spend by session-count band (Spark SQL join of MongoDB-shaped users with HBase-shaped sessions).", 5.2));
c.push(...FIGURE("fig5_cohort_retention.png", "Figure 6 - Share of each registration cohort buying in each month (November omitted: one day of data).", 5.0));
c.push(...FIGURE("fig1_daily_revenue.png", "Figure 7 - Daily net revenue with a 7-day rolling average (Spark SQL window query).", 6.0));
c.push(H2("6.1 Recommended actions"));
c.push(B("**Fix checkout first.** Checkout-to-order is the single largest controllable loss (33,018 sessions). Test guest checkout, saved payment methods and cart-recovery e-mails; even a 5-point lift adds ~2,900 orders (~$2.2M) per 90 days at current traffic."));
c.push(B("**Replenish before stock-out.** Use `product_metrics` daily views and units to trigger re-orders; sold-out items lose ~60% of their visibility."));
c.push(B("**Win back the 'At risk - high value' segment** (1,079 customers, $4.1M estimated CLV) before they slide into 'Hibernating'."));
c.push(B("**Steer merchandising by margin, not revenue:** promote the 30-36% margin subcategories; revenue alone hides a 2× profit spread."));

// ---------- 7 methodology
c.push(H1("7. Methodology notes"));
c.push(B("**Funnel:** a session reaches a stage if its page sequence contains it; 'Checkout' additionally requires a non-empty cart; 'Purchase' requires a transaction with that session_id."));
c.push(B("**CLV:** a simple, explainable retention-based model; partial first/last months are excluded when estimating retention, and lifetime is capped at 36 months."));
c.push(B("**RFM:** quintiles computed over buyers only. **Recommendations:** lift = confidence / P(consequent). **Cohorts:** months since registration use calendar-month differences; edge months (early August, 1 November) are partial."));

// ---------- 8 scalability
c.push(H1("8. Scalability and technology selection"));
c.push(TABLE(["Task", "Technology", "Why", "Scaling path"], [
  ["Catalogue, customer profile, order look-ups", "MongoDB", "Nested documents, secondary indexes, aggregation framework", "Shard transactions on {user_id: 'hashed'} (even writes, user-local history); replica sets for reads"],
  ["Click-stream, user timelines, product time series", "HBase", "Key-ordered storage, sparse wide rows, very high write rate, counters", "Regions split automatically; pre-split and, if write hot-spots appear, salt the key with hash(user_id) % N"],
  ["Cleaning, co-occurrence, cohorts, CLV, cross-store joins", "Spark", "Distributed, in-memory, SQL + DataFrame APIs, reads all sources", "Run on YARN/Kubernetes; Parquet partitioning; connectors read in parallel; Structured Streaming for live counters"],
], [0.24, 0.13, 0.3, 0.33]));
c.push(SP());
c.push(P("The pipeline is linear in data volume: at full scale (10×) the generator produces ~4 GB of JSON, and the Spark jobs need only the shuffle-partition setting raised. The pair-generation step is the only super-linear component (O(k²) per basket/session) and is bounded by the 15-page session cap. In production, session events would arrive through Kafka, be written to HBase with counter increments by a Spark Structured Streaming job, and be compacted nightly into Parquet."));

// ---------- 9 limitations
c.push(H1("9. Limitations and future work"));
c.push(B("**Synthetic data has little behavioural signal.** Devices, referrers and categories are sampled uniformly, so their funnels are statistically identical; cohort activity does not decay (~80% of every cohort buys each month), which is unrealistic. Product-level association rules show the classic small-count problem: pairs seen only twice reach lifts of 150-430, while the denser category-level lift is ~0.8 (no affinity; the <1 value reflects the fixed basket size). A production recommender would need minimum-support thresholds, significance testing or collaborative filtering (Spark ALS) on real data."));
c.push(B("**Generator artefacts:** once the transaction target is reached, converted sessions stop producing orders (the 15,552 gap); half the orders have no session ('offline/app'); no customer demographics (age) exist, so segmentation uses behaviour instead."));
c.push(B("**Infrastructure:** ==the results in this draft were produced in offline mode (mongomock and an SQLite HBase emulator). After running live mode, replace this sentence with: \"MongoDB 7 and HBase 2.x ran in Docker containers; all loaders and queries were executed against them.\"== The emulator mimics row-key ordering but not regions, versions or compression."));
c.push(B("**Future work:** Spark ALS recommendations, Structured Streaming into HBase counters, survival-based (BG/NBD) CLV, and an interactive dashboard."));

// ---------- appendices
c.push(PB());
c.push(H1("Appendix A - How to reproduce"));
c.push(...CODE(`# 1. install
python -m venv .venv && source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt                          # needs Java 17 for Spark

# 2. databases
docker compose up -d                                     # MongoDB :27017, HBase Thrift :9090, UI :16010

# 3. everything end-to-end (live MongoDB + HBase)
./run_all.sh                    # or ./run_all.sh --offline   |   SCALE=1.0 ./run_all.sh`));
c.push(P("Step by step (what `run_all.sh` does):"));
c.push(TABLE(["Step", "Command", "Output"], [
  ["1 Generate data", "`python data_generation/dataset_generator.py --out data/raw --scale 0.1`", "data/raw/*.json"],
  ["2 MongoDB", "`python mongodb/load_mongodb.py --sessions-limit 50000`  then  `python mongodb/aggregations.py`", "5 collections + indexes; output/mongo_*.csv"],
  ["3 HBase", "`docker exec -i hbase hbase shell -n < hbase/create_tables.hbase`;  `python hbase/load_hbase.py`;  `python hbase/query_hbase.py`", "2 tables; output/hbase_query_sample.txt"],
  ["4 Spark clean", "`python spark/01_clean_normalize.py`", "data/clean/*.parquet; data_quality_report.csv"],
  ["5 Spark analytics", "`python spark/02_recommendations.py`, `03_cohort_analysis.py`, `04_spark_sql_analytics.py`", "output/reco_*, cohort_*, sql_*.csv"],
  ["6 Integration", "`python integration/clv_analysis.py --mongo mongo --hbase hbase`;  `python integration/funnel_analysis.py --mongo mongo --hbase hbase`", "output/clv_*.csv, funnel_*.csv"],
  ["7 Charts", "`python visualization/make_charts.py`", "report/figures/*.png"],
], [0.16, 0.56, 0.28]));
c.push(SP());
c.push(P("Repository files:"));
c.push(TABLE(["Path", "Purpose"], [
  ["data_generation/dataset_generator.py", "Improved generator (original kept as dataset_generator_original.py)"],
  ["mongodb/load_mongodb.py, aggregations.py, aggregations.js", "Document model, bulk load, indexes, 4 pipelines"],
  ["hbase/create_tables.hbase, load_hbase.py, query_hbase.py, sample_queries.hbase, hbase_client.py", "Schema, loader, queries, Thrift client + emulator"],
  ["spark/spark_utils.py, 01-04 *.py", "Explicit schemas, cleaning, recommendations, cohorts, Spark SQL"],
  ["integration/sources.py, clv_analysis.py, funnel_analysis.py", "Source-agnostic loaders and the two integrated queries"],
  ["visualization/make_charts.py", "The 7 figures"],
  ["docker-compose.yml, run_all.sh, requirements.txt, README.md", "Environment and orchestration"],
], [0.5, 0.5]));

c.push(PB());
c.push(H1("Appendix B - Key scripts"));
c.push(P("The complete, commented source code is in the repository. The listings below are the parts most often asked for in assessment."));
c.push(H2("B.1 HBase schema (hbase/create_tables.hbase)"));
c.push(...CODE(read("hbase/create_tables.hbase")));
c.push(H2("B.2 HBase sample queries (hbase/sample_queries.hbase)"));
c.push(...CODE(read("hbase/sample_queries.hbase")));
c.push(H2("B.3 MongoDB aggregation pipelines (mongodb/aggregations.js)"));
c.push(...CODE(read("mongodb/aggregations.js")));
c.push(H2("B.4 Spark SQL - joining MongoDB-shaped and HBase-shaped data"));
c.push(...CODE(`WITH engagement AS (                               -- HBase: user_sessions rows
    SELECT SPLIT(rowkey, '\\\\|')[0]          AS user_id,
           COUNT(*)                          AS sessions,
           ROUND(AVG(\`info:duration\`) / 60, 1) AS avg_session_min
    FROM hbase_user_sessions GROUP BY 1
)
SELECT CASE WHEN e.sessions >= 25 THEN '25+ sessions' WHEN e.sessions >= 20 THEN '20-24'
            WHEN e.sessions >= 15 THEN '15-19' ELSE '<15' END  AS engagement_band,
       COUNT(*)                                      AS users,
       ROUND(AVG(m.purchase_summary.order_count), 2) AS avg_orders,   -- MongoDB: users doc
       ROUND(AVG(m.purchase_summary.total_spent), 2) AS avg_spent
FROM mongo_users m JOIN engagement e ON m._id = e.user_id
GROUP BY 1 ORDER BY 1;`));
c.push(H2("B.5 CLV core computation (integration/clv_analysis.py, excerpt)"));
c.push(...CODE(`purchases = (items_m.groupBy("user_id").agg(
    F.countDistinct("transaction_id").alias("orders"),
    F.round(F.sum("net_revenue"), 2).alias("revenue"),
    F.round(F.sum("profit"), 2).alias("gross_profit"),
    F.max("txn_time").alias("last_purchase"))
    .withColumn("aov", F.col("revenue") / F.col("orders"))
    .withColumn("margin_pct", F.col("gross_profit") / F.col("revenue"))
    .withColumn("orders_per_month", F.col("orders") / F.lit(window_months)))

lifetime_months = min(1 / (1 - retention), 36)        # retention estimated from the data
clv = clv.withColumn("clv", F.col("aov") * F.col("orders_per_month")
                            * F.col("margin_pct") * F.lit(lifetime_months))`));
c.push(H2("B.6 Docker environment (docker-compose.yml)"));
c.push(...CODE(read("docker-compose.yml")));

c.push(PB());
c.push(H1("Appendix C - Evidence screenshots"));
c.push(P("==[Add screenshots from your own live run here. Suggested set:]=="));
c.push(B("==`docker ps` showing the mongo and hbase containers running.=="));
c.push(B("==mongosh: `db.transactions.countDocuments()` and the output of pipeline 1 (top-selling products).=="));
c.push(B("==HBase shell: list, describe 'user_sessions', and a prefix scan of user_000042 (query Q1 in sample_queries.hbase).=="));
c.push(B("==Terminal output of `python spark/01_clean_normalize.py` (data-quality counts) and of `integration/clv_analysis.py` (segment table).=="));
c.push(B("==The Spark UI (http://localhost:4040) during a job, showing stages - optional but impressive.=="));

// ====================================================================== DOCUMENT
const doc = new Document({
  features: { updateFields: true },
  creator: "Godfrey Mushambo",
  title: "Distributed Multi-Model Analytics for E-commerce Data",
  styles: {
    default: { document: { run: { font: FONT, size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 30, bold: true, color: "1B1B1A", font: FONT },
        paragraph: { spacing: { before: 300, after: 120 }, outlineLevel: 0, keepNext: true,
                     border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: BLUE, space: 2 } } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, color: BLUE, font: FONT },
        paragraph: { spacing: { before: 200, after: 80 }, outlineLevel: 1, keepNext: true } },
    ],
  },
  numbering: { config: [
    { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 400, hanging: 260 } } } }] },
    { reference: "numbers", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 400, hanging: 300 } } } }] },
  ] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } },
    headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
      children: [new TextRun({ text: "AUCA Big Data Analytics - Final Project", size: 16, color: "8A8984" })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: ["Page ", PageNumber.CURRENT], size: 16, color: "8A8984" })] })] }) },
    children: c,
  }],
});

Packer.toBuffer(doc).then(buf => {
  const out = path.join(ROOT, "report", "Technical_Report.docx");
  fs.writeFileSync(out, buf);
  console.log("wrote", out);
});
