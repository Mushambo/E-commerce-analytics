// build_final_report.js - builds the FINAL technical report: report/Technical_Report_Final.docx
// Numbers come from the live Docker run (output/*.csv); screenshots from report/evidence/.
// Yellow highlight = something the author must do or confirm before submitting.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, ImageRun, LevelFormat, PageBreak, Footer, PageNumber,
  TableOfContents, Header,
} = require("docx");

const ROOT = path.resolve(__dirname, "..");
const FIG = path.join(__dirname, "final_figures");
const EVD = path.join(__dirname, "evidence");
const W = 9638;
const FONT = "Calibri", MONO = "Consolas", BLUE = "2A78D6";

function runs(text, base = {}) {
  const out = [], re = /(\*\*[^*]+\*\*|`[^`]+`|==[^=]+==|\*[^*]+\*)/g;
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
const H3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)] });
const B = (t) => new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: runs(t), spacing: { after: 60 } });
const N = (t, ref = "numbers") => new Paragraph({ numbering: { reference: ref, level: 0 }, children: runs(t), spacing: { after: 60 } });
const PB = () => new Paragraph({ children: [new PageBreak()] });
const SP = () => new Paragraph({ children: [], spacing: { after: 40 } });

function CODE(text) {
  return text.replace(/\s+$/, "").split("\n").map((line, i, arr) => new Paragraph({
    children: [new TextRun({ text: line.length ? line : " ", font: MONO, size: 15 })],
    shading: { type: ShadingType.CLEAR, fill: "F4F4F2" },
    spacing: { before: 0, after: i === arr.length - 1 ? 120 : 0, line: 240 },
    indent: { left: 120, right: 120 }, keepLines: true,
  }));
}
const border = { style: BorderStyle.SINGLE, size: 4, color: "D6D5D0" };
const borders = { top: border, bottom: border, left: border, right: border };
function TABLE(header, rows, pct) {
  const widths = pct.map(p => Math.round(W * p));
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
function pngSize(f) { const b = fs.readFileSync(f); return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) }; }
function IMG(file, widthIn, maxHIn = 8.6) {
  const s = pngSize(file);
  let w = widthIn * 96, h = w * s.h / s.w;
  if (h > maxHIn * 96) { h = maxHIn * 96; w = h * s.w / s.h; }
  return new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 100 },
    children: [new ImageRun({ type: "png", data: fs.readFileSync(file), transformation: { width: w, height: h },
      altText: { title: path.basename(file), description: path.basename(file), name: path.basename(file) } })] });
}
function FIGURE(file, caption, widthIn = 6.2) {
  return [IMG(path.join(FIG, file), widthIn),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 160 }, children: runs(caption, { size: 17, italics: true, color: "52514E" }) })];
}
// evidence screenshot: title line, command, image, comment ("What it shows")
function SHOT(n, title, command, file, comment, widthIn = 6.5, maxH = 7.6) {
  const out = [new Paragraph({ keepNext: true, spacing: { before: 200, after: 40 },
    children: runs(`**Screenshot S${n} - ${title}**`, { size: 20, color: "1B1B1A" }) })];
  if (command) out.push(new Paragraph({ keepNext: true, spacing: { after: 40 }, children: runs(`Command: \`${command}\``, { size: 17, color: "52514E" }) }));
  out.push(IMG(path.join(EVD, file), widthIn, maxH));
  out.push(new Paragraph({ spacing: { before: 60, after: 160 }, alignment: AlignmentType.JUSTIFIED,
    border: { left: { style: BorderStyle.SINGLE, size: 18, color: BLUE, space: 6 } }, indent: { left: 140 },
    children: runs(`**Comment:** ${comment}`, { size: 18 }) }));
  return out;
}
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");

// ======================================================================================= CONTENT
const c = [];

// ---------------- title page
c.push(new Paragraph({ spacing: { before: 2000, after: 200 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "Distributed Multi-Model Analytics for E-commerce Data", bold: true, size: 44 })] }));
c.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 500 },
  children: [new TextRun({ text: "MongoDB  ·  HBase  ·  Apache Spark", size: 28, color: BLUE })] }));
for (const t of ["Technical Report - AUCA Big Data Analytics, Final Project (October 2026)", "Author: Godfrey Mushambo",
                 "Student ID: ==[enter your student ID]==", "Lecturer: ==[enter lecturer name]==",
                 "GitHub repository: ==[paste your repository URL]==", "Submission date: ==[e.g. 11 November 2026]=="])
  c.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: runs(t, { size: 24 }) }));
c.push(PB());

// ---------------- final checks page
c.push(H1("Final checks before submission (delete this page)"));
c.push(P("Only the items below still need you. Each one is also **==highlighted in yellow==** where it appears in the report. When done, remove the highlights (Home → Text Highlight Color → No Color) and delete this page."));
c.push(TABLE(["#", "Action", "Where"], [
  ["1", "Fill in student ID, lecturer, GitHub URL and submission date.", "Title page"],
  ["2", "**Reload HBase completely, then retake the funnel screenshot.** Your HBase held 186,713 of 200,000 sessions and an empty product_metrics table (the load was interrupted), so S14 shows 186,713 sessions and an empty category table. Run `docker compose exec -T app python hbase/load_hbase.py --recreate` (wait for '200,000 rows' and the product_metrics line), then `docker compose exec -T app python integration/funnel_analysis.py --mongo mongo --hbase hbase`. Expected: 200,000 → 197,509 → 130,126 → 58,215 → 25,197 (verified on your raw data) and a filled category table.", "Appendix C, S14; Section 5.2"],
  ["3", "After the reload, rerun `integration/clv_analysis.py` and retake S13. Only the *Sessions* and *Session→order* columns can change slightly (CLV values do not depend on HBase).", "Appendix C, S13; Section 5.1 table"],
  ["4", "Retake S1 with `docker compose ps`: the current picture also shows an unrelated nginx container (my-web-server) and a command typed mid-output.", "Appendix C, S1"],
  ["5", "Update the table of contents (right-click → Update Field → Update entire table) and export to PDF (File → Save As → PDF).", "Contents"],
], [0.05, 0.72, 0.23]));
c.push(SP());
c.push(P("**What was cleaned up in this version:** duplicated screenshots removed (run_all output duplicated the generator and MongoDB-load shots; two CLV and two cleaning runs; an older architecture diagram); the seven charts now appear once (Section 6), regenerated from your live Docker results; all numbers updated to the live run; every screenshot moved to Appendix C, grouped by project part, each with the command used and a comment; Appendix B updated to the final docker-compose.yml and the HBase range-scan reader."));
c.push(PB());

// ---------------- TOC
c.push(new Paragraph({ children: [new TextRun({ text: "Contents", bold: true, size: 32, color: BLUE })], spacing: { after: 120 } }));
c.push(new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-2" }));
c.push(PB());

// ---------------- 1 executive summary
c.push(H1("1. Executive summary"));
c.push(P("This project builds a polyglot analytics platform for a synthetic e-commerce business. **MongoDB** stores the document-shaped business entities (catalogue, customers, orders), **HBase** stores the high-volume, time-ordered click-stream and daily product metrics, and **Apache Spark** cleans the raw data, runs the batch analytics and joins data across both stores. Everything runs in Docker (MongoDB 7, HBase 2.1.2, Spark 3.5.3 with Python 3.11). Results come from a live run on a 10% dataset (seed 42): 10,000 users, 5,000 products, 25 categories, 200,000 sessions and 50,000 transactions over 90 days (12 Aug - 10 Nov 2026)."));
c.push(TABLE(["Net revenue", "Sessions ending in a purchase", "Checkout abandonment", "CLV held by top 17% of customers"],
  [["$53.2M (50,000 orders, AOV $1,064)", "12.6% (25,197 of 200,000)", "57% of checkouts", "27.9% ('Champions')"]], [0.25, 0.25, 0.25, 0.25]));
c.push(SP());
c.push(B("**The funnel leaks after the cart, not before it.** 98.8% of sessions view a product and 65% add to cart, but only 45% of carts reach checkout and 43% of checkouts become an order: 33,018 checkout abandoners, worth up to ~$25M at the $771 average web order."));
c.push(B("**Stock-outs, not demand, drive the views-sales link.** Across all products views and units sold correlate at r = 0.69, but among in-stock products only r = 0.12; the 209 products that sold out averaged 52 page views against 132 for in-stock products (-60%)."));
c.push(B("**Value is concentrated and partly at risk.** RFM segmentation finds 1,729 'Champions' holding 27.9% of estimated lifetime value and 1,084 high-value customers who have not bought for ~27 days (15.8% of CLV, $4.2M)."));
c.push(B("**Revenue is flat; profit is not.** Daily revenue is stable (~$592k/day, s.d. $31k) and category revenue stays within -17% / +15% of the mean, but subcategory margins range from 18% to 36%, so category profit differs about two-fold."));
c.push(B("**Cross-system reconciliation finds data issues.** 15,552 of the 40,749 sessions flagged 'converted' (38%) have no matching transaction - visible only by joining HBase sessions with MongoDB orders."));

// ---------------- 2 architecture
c.push(H1("2. System architecture"));
c.push(...FIGURE("fig0_architecture.png", "Figure 1 - System architecture: the generator feeds MongoDB, HBase and Spark; Spark joins all sources for the integrated analytics; all services run as Docker containers.", 6.6));
c.push(TABLE(["Layer", "Component", "Role in the solution"], [
  ["Source", "`dataset_generator.py`", "Generates users, products, categories, sessions_N.json and transactions (JSON arrays)"],
  ["Document store", "**MongoDB 7**", "categories, products, users (+ purchase_summary), transactions (+ embedded items), sessions sample; 4 aggregation pipelines"],
  ["Wide-column store", "**HBase 2.1.2**", "user_sessions (key user|reverse_ts|session) and product_metrics (key product|yyyymmdd)"],
  ["Processing", "**Apache Spark 3.5.3**", "Cleaning → Parquet lake; recommendations; cohorts; Spark SQL; integrated CLV and funnel jobs"],
  ["Access layer", "`integration/sources.py`", "Returns the same DataFrame from Parquet, MongoDB (pipeline pushed down) or HBase (row-key range scans)"],
  ["Deployment", "Docker Compose", "Three containers: mongo (:27017), hbase (:9090 Thrift, :16010 UI), app (Python + Java + PySpark, :4040 Spark UI)"],
], [0.17, 0.25, 0.58]));
c.push(SP());
c.push(P("Raw JSON is loaded into the two operational stores by Python loaders and, in parallel, read by Spark, which writes a clean Parquet 'lake'. The analytical jobs read through one access layer, so the analysis code does not depend on where data is stored; the same code runs against live databases or, for development, against an in-memory MongoDB substitute and a SQLite-backed HBase emulator that keeps HBase's sorted row-key behaviour. Evidence that the three containers ran is in Appendix C (S1-S3)."));
c.push(H2("2.1 Dataset and generator"));
c.push(P("The course generator's simulation logic (page-flow probabilities, 30% add-to-cart, 70% checkout completion, stock checks, discounts) is unchanged. Four engineering fixes were made: (1) products receive the `subcategory_id` shown in the brief's data dictionary but never assigned by the original; (2) sessions are streamed to `sessions_N.json` in 100,000-record chunks instead of being kept in memory (the original needs >10 GB RAM at 2M sessions); (3) IDs come from the seeded random generator instead of `uuid4`, making runs reproducible; (4) a `--scale` option. The 10% dataset generated in 71-106 s (S4)."));

// ---------------- 3 part 1
c.push(H1("3. Data modelling and storage (Part 1)"));
c.push(H2("3.1 MongoDB document model"));
c.push(TABLE(["Collection", "Document shape", "Pattern and justification"], [
  ["categories", "category + `subcategories[]` (3-5) with profit_margin", "Embedding: small, bounded, always read together - one read returns the whole hierarchy."],
  ["products", "product + `category{id,name}` + `subcategory{id,name,profit_margin}` + `price_history[]`", "Extended reference: copies rarely-changing names and margin, so catalogue pages and margin maths need no $lookup. Price history is bounded (1-3 points), so it is embedded."],
  ["transactions", "order header + `items[]` (each with product_name, category_id, subcategory_id); timestamp as BSON Date", "Line items live and die with the order (atomic single-document write). Denormalised category ids make revenue-by-category a pure $unwind/$group."],
  ["users", "profile + geo + `purchase_summary{total_spent, order_count, avg_order_value, favorite_category, recent_orders[5]}`", "Computed + subset pattern: the most-requested facts are pre-aggregated; the full history stays in transactions, avoiding unbounded arrays."],
  ["sessions (50k sample)", "full journey with `page_views[]` and `cart_contents[]`", "Shows the 'whole journey in one document' query; the complete click-stream lives in HBase."],
], [0.15, 0.38, 0.47]));
c.push(SP());
c.push(P("**Indexes** back each query pattern: `{user_id:1, timestamp:-1}` (order history), `{timestamp:1}` (period revenue), multikey `{items.product_id:1}` (product sales), `{purchase_summary.total_spent:-1}` (top customers), `{category.category_id:1, is_active:1}` (catalogue browsing). The loader inserted 25 categories, 5,000 products, 50,000 transactions, 10,000 users and 50,000 sessions in about 10 s (S5). **Four aggregation pipelines** are implemented (`mongodb/aggregations.py` and `.js`, Appendix B.3; output in S6-S7):"));
c.push(N("**Product popularity** - `$match` → `$unwind` → `$group` → `$sort` → `$lookup` (current stock): the top product sold 84 units in 35 orders."));
c.push(N("**Revenue analytics** - revenue and estimated profit per category per month; each item is matched to its embedded subcategory margin with `$filter`."));
c.push(N("**User segmentation** - purchase-frequency and spend buckets with `$facet` + `$bucket` in one round trip: 1,179 users with 1-2 orders spend $1,833 on average, 3,550 users with 6-9 orders spend $7,351, and 313 users with 10+ orders spend $11,449."));
c.push(N("**Journey funnel** over the embedded `page_views` array, by referrer (about 20-21% of sessions per referrer are flagged converted)."));

c.push(H2("3.2 HBase wide-column model"));
c.push(TABLE(["Table", "Row key", "Column families", "Access patterns served"], [
  ["user_sessions", "`user_id|reverse_ts|session_id` (reverse_ts = 9999999999999 - epoch_ms)", "**info**: session header (15 cells); **pv**: one column per page view (000..015); **cart**: qualifier = product_id, value qty|price", "Latest N sessions of a user = prefix scan, newest first; a time window = bounded STARTROW/STOPROW scan; one session = point get."],
  ["product_metrics", "`product_id|yyyymmdd`", "**m**: views, cart_adds, purchases, units_sold, revenue_cents", "A product's daily history or a date range is one contiguous scan; streaming updates use atomic incr counters."],
], [0.15, 0.25, 0.3, 0.3]));
c.push(SP());
c.push(P("**Why this design.** Putting `user_id` first stores a user's activity contiguously; reversing the timestamp returns the most recent session first, so no sort is needed. Column families follow access patterns: listing sessions reads only the small `info` family, while the variable-width `pv` family (3-15 cells) is read only when a journey is drilled into. Sparse columns cost nothing - most sessions have 0-2 `cart` cells. `VERSIONS=1` (events are immutable), a ROW bloom filter for point gets, a 180-day TTL on `pv`, and four pre-split points complete the schema; the HBase UI confirms 5 regions per table (S2). Example queries (all in Appendix B.2; live output in S8 and in Q1-Q5 of `hbase/query_hbase.py`):"));
c.push(...CODE(`scan 'user_sessions', {ROWPREFIXFILTER => 'user_000042|', COLUMNS => ['info'], LIMIT => 5}     # latest sessions
scan 'user_sessions', {STARTROW => 'user_000042|8209187200000',
                       STOPROW  => 'user_000042|8211779199999~'}                      # September 2026
scan 'product_metrics', {STARTROW => 'prod_00123|20260901', STOPROW => 'prod_00123|20261001'}`));

c.push(H2("3.3 Why data was placed in MongoDB or HBase"));
c.push(TABLE(["Criterion", "MongoDB", "HBase"], [
  ["Data", "Entities with rich nested structure and modest volume (catalogue, customers, orders)", "Append-only events at very high volume (2M sessions, ~20M page views at full scale), daily counters"],
  ["Queries", "Ad-hoc filters, secondary indexes, aggregation framework, $lookup", "Known access path by key: per-user timelines, per-product time ranges"],
  ["Schema", "Flexible documents, validation per collection", "Sparse, variable columns per row; the row-key design is the 'index'"],
  ["Writes", "Atomic per document (an order and its items together)", "Very high write throughput, atomic counters, automatic region sharding"],
], [0.16, 0.42, 0.42]));

// ---------------- 4 part 2
c.push(H1("4. Data processing with Apache Spark (Part 2)"));
c.push(H2("4.1 Cleaning and normalisation (01_clean_normalize.py)"));
c.push(P("The job reads every JSON file (sessions via the glob `sessions_*.json`) with **explicit schemas** - avoiding a second inference pass over the large session files and type drift - and writes nine Parquet tables: users, categories (hierarchy flattened to one row per subcategory), products (joined with margin), price_history, sessions (partitioned by date, with funnel flags), page_views (exploded with `posexplode`, partitioned by date), cart_items (the `cart_contents` object read as a MapType and exploded), transactions (with reconciliation flags) and transaction_items (discount pro-rated per line, enriched with category and margin through a broadcast join)."));
c.push(P("**Cleaning rules:** de-duplicate on keys; drop rows with missing keys or unparseable timestamps; trim and case-normalise enums and geo codes; clamp negatives; fill missing descriptive values; repair `conversion_status` ('abandoned' with an empty cart → 'browsed'); and *flag* - not drop - logical inconsistencies. Every check is counted in `output/data_quality_report.csv` (S9). The data was structurally clean (0 duplicates, 0 invalid rows, 0 orphan ids, 0 total mismatches); the one material issue is **15,552 converted sessions without an order**, explained in Section 9."));
c.push(H2("4.2 Product recommendation indicators (02_recommendations.py)"));
c.push(P("Association rules (support, confidence, lift; top-5 per product with a window function) for **'bought together'** (self-join on transaction id with x < y) and **'viewed together'** (pairs built inside each session's `viewed_products` array with the higher-order functions transform/filter, which avoids a shuffle-heavy join), plus category-level affinity. Result (S10): only 304 product pairs occur in 2 or more of the 50,000 baskets, and their lifts (median 155, max 435) are inflated by tiny counts; 'viewed together' gives 59,127 pairs (median lift 20.7); category lift is ~0.79 - i.e. no genuine affinity in this synthetic data, a useful null-model check of the method."));
c.push(H2("4.3 Cohort analysis (03_cohort_analysis.py)"));
c.push(P("Users are grouped by registration month (Feb-Aug 2026) and followed by months since registration: active buyers, retention %, revenue, AOV and cumulative revenue per member (S11). In each full month (September, October) about 80-84% of every cohort buys; the first (from 12 Aug) and last (10 days of November) months are partial. Revenue per member over the 90 days is flat across cohorts ($5,253-$5,370), so cohort age has no effect - another sign of uniform synthetic behaviour."));
c.push(H2("4.4 Spark SQL analytics (04_spark_sql_analytics.py)"));
c.push(P("Part A runs five complex queries on the DataFrames (S12): top-3 products per category (CTE + RANK); funnel by device and referrer with ROLLUP; daily revenue with a 7-day RANGE window and week-over-week LAG; price-change impact using MAX_BY over exploded price history (units per day fall from ~0.51 to ~0.49 after every type of price move, cuts and raises alike - no measurable price elasticity); and viewed-vs-sold ranks. Part B shows how Spark SQL queries data that notionally lives in the two stores: views shaped like MongoDB documents (`mongo_users` with nested purchase_summary; `mongo_transactions` with an items array queried through LATERAL VIEW explode - Spark's equivalent of $unwind) and like HBase rows (`rowkey` + `info:*` columns, user id parsed with SPLIT) are joined in SQL (Appendix B.4)."));
c.push(H2("4.5 Optimisations"));
c.push(P("Explicit schemas; Parquet + Snappy with date partitioning (partition pruning for time ranges); broadcast joins for the 5,000-product and 109-subcategory dimensions; adaptive query execution; `cache()` only for reused DataFrames; array functions instead of joins for co-occurrence; a minimum pair count before ranking; reduced shuffle partitions for a single machine. On the laptop, cleaning took ~20 min (1,190 s, S9), dominated by multi-line JSON parsing - such files cannot be split across tasks, so at scale the generator should write JSON Lines."));

// ---------------- 5 part 3
c.push(H1("5. Integrated analytics (Part 3)"));
c.push(H2("5.1 Customer Lifetime Value (integration/clv_analysis.py)"));
c.push(P("**Business question:** which customers are worth most over their expected lifetime, how engaged are they, and which segment should receive retention spend?"));
c.push(P("**Data sources:** user profiles and orders from **MongoDB** (`$unwind` and discount pro-ration pushed into the aggregation pipeline, so only line-item rows cross the network); engagement from **HBase** `user_sessions` (session count, duration, pages, cart rate); margins from the category dimension."));
c.push(P("**Spark steps:** per-user purchase facts → per-user engagement facts → monthly buyer retention estimated from the data (r = 0.830 ⇒ expected lifetime 1/(1-r) = 5.9 months) → CLV = AOV × orders per month × gross-margin % × lifetime → RFM quintiles (NTILE) mapped to named segments and CLV tiers. Output in S13:"));
c.push(TABLE(["Segment", "Users", "Avg CLV", "Share of CLV", "Recency (days)", "Sessions*", "Session→order*"], [
  ["Champions", "1,729", "$4,329", "27.9%", "3.9", "19.8", "18.3%"],
  ["At risk - high value", "1,084", "$3,910", "15.8%", "26.7", "18.8", "15.3%"],
  ["Loyal", "1,260", "$3,395", "16.0%", "9.4", "19.8", "19.1%"],
  ["Needs attention", "1,939", "$2,282", "16.5%", "8.9", "18.2", "11.7%"],
  ["New / promising", "1,041", "$1,663", "6.5%", "4.3", "17.8", "9.8%"],
  ["Hibernating", "2,896", "$1,608", "17.4%", "35.0", "18.1", "10.3%"],
], [0.24, 0.1, 0.12, 0.13, 0.14, 0.12, 0.15]));
c.push(new Paragraph({ spacing: { after: 100 }, children: runs("==*Columns read from HBase; recheck after the full HBase reload (final-checks item 3).==", { size: 16 }) }));
c.push(P("Platinum customers (top CLV quartile) average 19.5 sessions and a 17.3% session-to-order rate, against 17.9 and 9.7% for Bronze: value is driven by **conversion efficiency** far more than by browsing time (correlation of CLV with session duration 0.02, with session count 0.14, with cart rate 0.11)."));
c.push(H2("5.2 Funnel conversion (integration/funnel_analysis.py)"));
c.push(P("**Business question:** where are shoppers lost, does it differ by device, traffic source or category, and what is the leak worth?"));
c.push(P("**Data sources:** journey stages from **HBase** `user_sessions` (`pv` and `cart` families); category views and cart adds from **HBase** `product_metrics`; purchases from **MongoDB** transactions as the *source of truth* for the last stage."));
c.push(P("**Spark steps:** range scans → per-session stage flags → left join to orders on session_id → stage counts and step conversion; repeated by device, referrer, category (HBase views × MongoDB web purchases) and week. Over the 200,000 sessions: 98.8% view a product, 65.1% add to cart, 29.1% reach checkout with a cart, 12.6% buy (Figure 4). Device purchase rates differ by less than 0.1 point (12.57-12.62%) and device × referrer cells stay within 12.2-13.3%: the leak is a **process** problem at checkout, not a channel problem. The generator flags 40,749 sessions as converted, but only 25,197 have a real order - MongoDB is therefore used as the source of truth. ==S14 must be retaken after the full HBase reload (final-checks item 2).=="));
c.push(H2("5.3 Why these technologies, and performance"));
c.push(P("MongoDB answers the order and profile side with pushed-down aggregation; HBase answers the per-user, time-ordered event side with key-range scans; Spark does what neither store does well - large joins across the two and window/statistical computation. Reading the whole `user_sessions` table as one Thrift scan timed out on the single-node HBase, so the reader scans **100 user-id key ranges** (and 50 product ranges), retrying a failed range on a fresh connection (Appendix B.6). At full scale, the hbase-spark connector or a snapshot export would let executors read regions in parallel, and the MongoDB Spark connector would partition reads by `_id`; joins are on high-cardinality keys with dimension tables broadcast."));

// ---------------- 6 part 4
c.push(H1("6. Visualisations and insights (Part 4)"));
c.push(P("All charts were produced with `python visualization/make_charts.py` (matplotlib) from the result tables of the live run."));
c.push(...FIGURE("fig1_daily_revenue.png", "Figure 2 - Sales performance over time: daily net revenue with a 7-day rolling average (Spark SQL window query).", 6.0));
c.push(...FIGURE("fig2_category_revenue_profit.png", "Figure 3 - Sales by category: revenue and estimated gross profit (MongoDB pipeline 2). Margins range from 18% to 36%.", 6.2));
c.push(...FIGURE("fig3_conversion_funnel.png", "Figure 4 - Conversion funnel over 200,000 sessions (HBase journeys × MongoDB orders). Step % = conversion from the previous stage.", 6.0));
c.push(...FIGURE("fig6_viewed_vs_sold.png", "Figure 5 - Product performance, most-viewed vs top-selling: each dot is a product; sold-out products lose page views.", 5.2));
c.push(...FIGURE("fig4_clv_segments.png", "Figure 6 - Customer segmentation: RFM segments by size (left) and average estimated CLV with share of total CLV (right).", 6.3));
c.push(...FIGURE("fig7_engagement_vs_spend.png", "Figure 7 - Engagement vs value: average spend (MongoDB) by session-count band (HBase).", 5.2));
c.push(...FIGURE("fig5_cohort_retention.png", "Figure 8 - Cohort analysis: share of each registration cohort buying per month (August starts on the 12th; November omitted, 10 days).", 5.2));
c.push(H2("6.1 Key findings and recommended actions"));
c.push(B("**Fix checkout first.** Checkout-to-order is the largest controllable loss (33,018 sessions). Test guest checkout, saved payment methods and cart-recovery e-mails; a 5-point lift adds ~2,900 orders (~$2.2M) per 90 days at current traffic."));
c.push(B("**Replenish before stock-out.** Use `product_metrics` daily views and units to trigger re-orders; sold-out items lose ~60% of their visibility."));
c.push(B("**Win back the 'At risk - high value' segment** (1,084 customers, $4.2M estimated CLV) before they become 'Hibernating'."));
c.push(B("**Steer merchandising by margin, not revenue:** promote the 30-36% margin subcategories; revenue alone hides a two-fold profit spread."));
c.push(B("**Reward engagement:** users with 25+ sessions spend 27% more than those with fewer than 15 (Figure 7), so re-engagement campaigns have a measurable value."));

// ---------------- 7 methodology
c.push(H1("7. Methodology for key analyses"));
c.push(B("**Funnel:** a session reaches a stage if its page sequence contains it; 'Checkout' also requires a non-empty cart; 'Purchase' requires a MongoDB transaction with that session_id."));
c.push(B("**CLV:** retention-based model; partial first/last months are excluded when estimating retention; lifetime capped at 36 months; margin from the item's subcategory."));
c.push(B("**RFM:** quintiles over buyers only, mapped to six named segments. **Recommendations:** lift = confidence / P(consequent), minimum pair count 2. **Cohorts:** calendar-month differences between registration and purchase."));

// ---------------- 8 scalability
c.push(H1("8. Scalability and technology selection"));
c.push(TABLE(["Analytical task", "Technology", "Why", "Scaling path"], [
  ["Catalogue, customer profile, order look-ups and aggregations", "MongoDB", "Nested documents, secondary indexes, aggregation framework", "Shard transactions on {user_id: 'hashed'}; replica sets for reads"],
  ["Click-stream, user timelines, product time series", "HBase", "Key-ordered storage, sparse wide rows, very high write rate, counters", "Automatic region splits; pre-split; salt keys with hash(user_id) % N if hot-spots appear"],
  ["Cleaning, co-occurrence, cohorts, CLV, cross-store joins", "Spark", "Distributed, in-memory, SQL + DataFrame APIs, reads all sources", "YARN/Kubernetes cluster; Parquet partitioning; parallel connectors; Structured Streaming"],
], [0.26, 0.12, 0.3, 0.32]));
c.push(SP());
c.push(P("The pipeline scales linearly with data volume: the full dataset (10×) is ~4 GB of JSON and needs only more shuffle partitions. Pair generation is the only super-linear step (O(k²) per basket/session) and is bounded by the 15-page session cap. In production, session events would arrive through Kafka, be written to HBase with counter increments by a Spark Structured Streaming job, and be compacted nightly into Parquet."));

// ---------------- 9 limitations
c.push(H1("9. Limitations and future work"));
c.push(B("**Synthetic data has little behavioural signal:** devices, referrers and categories are sampled uniformly, cohorts do not decay and prices do not change demand; product-level rules suffer from small counts. Real data would need minimum-support thresholds, significance tests or collaborative filtering (Spark ALS)."));
c.push(B("**Generator artefacts:** once its transaction target is reached, converted sessions stop producing orders (the 15,552 gap); half the orders have no session ('offline/app'); there are no demographics (age), so segmentation is behavioural."));
c.push(B("**Infrastructure:** MongoDB 7, HBase 2.1.2 and Spark 3.5.3 ran as Docker containers on one laptop. Single-node HBase was the weak point - it stopped once under memory pressure and stalled on long full-table scans - which led to the range-scan reader. Cleaning took ~20 minutes because multi-line JSON cannot be split."));
c.push(B("**Future work:** JSON Lines input, Spark ALS recommendations, Structured Streaming into HBase counters, probabilistic (BG/NBD) CLV, and an interactive dashboard."));

// ---------------- Appendix A
c.push(PB());
c.push(H1("Appendix A - How to reproduce"));
c.push(P("All components run in Docker. From Windows PowerShell, in the project folder:"));
c.push(...CODE(`docker compose up -d --build                     # mongo :27017, hbase :9090 / UI :16010, app (Spark UI :4040)
docker compose exec -T app python wait_for_services.py
.\\run_all.ps1                                    # whole pipeline   (or .\\run_all.ps1 -Scale 1.0)
.\\evidence.ps1                                   # re-creates the evidence screenshots step by step`));
c.push(TABLE(["Step", "Command (prefix each with  docker compose exec -T app )", "Output"], [
  ["1 Generate data", "`python data_generation/dataset_generator.py --out data/raw --scale 0.1`", "data/raw/*.json"],
  ["2 MongoDB", "`python mongodb/load_mongodb.py --sessions-limit 50000`  then  `python mongodb/aggregations.py`", "5 collections + indexes; output/mongo_*.csv"],
  ["3 HBase", "`python hbase/load_hbase.py --recreate`  then  `python hbase/query_hbase.py`", "2 tables; Q1-Q5 results"],
  ["4 Spark clean", "`python spark/01_clean_normalize.py`", "data/clean/*.parquet; data_quality_report.csv"],
  ["5 Spark analytics", "`python spark/02_recommendations.py`, `03_cohort_analysis.py`, `04_spark_sql_analytics.py`", "output/reco_*, cohort_*, sql_*.csv"],
  ["6 Integration", "`python integration/clv_analysis.py --mongo mongo --hbase hbase`;  `python integration/funnel_analysis.py --mongo mongo --hbase hbase`", "output/clv_*.csv, funnel_*.csv"],
  ["7 Charts", "`python visualization/make_charts.py`", "report/figures/*.png"],
  ["Shells", "`Get-Content mongodb\\evidence.js | docker exec -i mongo mongosh ecommerce --quiet`;  `Get-Content hbase\\evidence.hbase | docker exec -i hbase hbase shell -n`", "S7, S8"],
], [0.15, 0.6, 0.25]));
c.push(SP());
c.push(TABLE(["Repository path", "Purpose"], [
  ["data_generation/dataset_generator.py", "Improved generator (original kept as dataset_generator_original.py)"],
  ["mongodb/load_mongodb.py, aggregations.py, aggregations.js, evidence.js", "Document model, bulk load, indexes, 4 pipelines"],
  ["hbase/create_tables.hbase, load_hbase.py, query_hbase.py, sample_queries.hbase, hbase_client.py", "Schema, loader, queries, Thrift client + emulator"],
  ["spark/spark_utils.py, 01-04 *.py", "Explicit schemas, cleaning, recommendations, cohorts, Spark SQL"],
  ["integration/sources.py, clv_analysis.py, funnel_analysis.py", "Source-independent loaders (range scans) and the two integrated queries"],
  ["visualization/make_charts.py; report/make_architecture_diagram.py", "The charts and the architecture diagram"],
  ["Dockerfile, docker-compose.yml, run_all.ps1, run_all.sh, evidence.ps1, wait_for_services.py, README.md", "Docker environment, orchestration, documentation"],
], [0.5, 0.5]));

// ---------------- Appendix B
c.push(PB());
c.push(H1("Appendix B - Key scripts"));
c.push(P("The complete, commented source code is in the repository; these are the parts the brief asks to see."));
c.push(H2("B.1 HBase schema (hbase/create_tables.hbase)"));
c.push(...CODE(read("hbase/create_tables.hbase")));
c.push(H2("B.2 HBase sample queries (hbase/sample_queries.hbase)"));
c.push(...CODE(read("hbase/sample_queries.hbase")));
c.push(H2("B.3 MongoDB aggregation pipelines (mongodb/aggregations.js)"));
c.push(...CODE(read("mongodb/aggregations.js")));
c.push(H2("B.4 Spark SQL joining MongoDB-shaped and HBase-shaped data"));
c.push(...CODE(`WITH engagement AS (                                    -- HBase: user_sessions rows
    SELECT SPLIT(rowkey, '\\\\|')[0]              AS user_id,
           COUNT(*)                              AS sessions,
           ROUND(AVG(\`info:duration\`) / 60, 1)  AS avg_session_min
    FROM hbase_user_sessions GROUP BY 1
)
SELECT CASE WHEN e.sessions >= 25 THEN '25+ sessions' WHEN e.sessions >= 20 THEN '20-24'
            WHEN e.sessions >= 15 THEN '15-19' ELSE '<15' END   AS engagement_band,
       COUNT(*)                                      AS users,
       ROUND(AVG(m.purchase_summary.order_count), 2) AS avg_orders,      -- MongoDB: users document
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

lifetime_months = min(1 / (1 - retention), 36)          # retention estimated from the data
clv = clv.withColumn("clv", F.col("aov") * F.col("orders_per_month")
                            * F.col("margin_pct") * F.lit(lifetime_months))`));
c.push(H2("B.6 Robust HBase reader - row-key range scans with retry (integration/sources.py)"));
c.push(...CODE(fs.readFileSync("/tmp/scan_excerpt.py", "utf8")));
c.push(H2("B.7 Docker environment (docker-compose.yml)"));
c.push(...CODE(read("docker-compose.yml")));

// ---------------- Appendix C
c.push(PB());
c.push(H1("Appendix C - Evidence screenshots"));
c.push(P("Screenshots from the live Docker run, grouped by project part. Each shows the command used and a short comment on what it proves."));
c.push(H2("C.1 Environment"));
c.push(...SHOT(1, "Running containers", "docker compose ps", "S01_docker_ps.png",
  "The three project containers - app (Python + Java + PySpark), mongo (MongoDB 7) and hbase (HBase + Thrift) - are up, with ports 27017, 9090/16010 and 4040 published. ==Retake with `docker compose ps`: this image also shows an unrelated nginx container (my-web-server) and a command typed mid-output.==", 6.5));
c.push(...SHOT(2, "HBase master web UI", "http://localhost:16010", "S02_hbase_master_ui.png",
  "HBase 2.1.2 runs with one region server. Both user tables, `user_sessions` and `product_metrics`, are ENABLED with **5 regions each** - the 4 split points of the schema took effect - and the description confirms the `info`, `pv` (TTL 180 days) and `cart` families."));
c.push(...SHOT(3, "Spark UI during the cleaning job", "http://localhost:4040", "S03_spark_ui.png",
  "Spark 3.5.3 executed 49 jobs for `01_clean_normalize`; the final jobs are the Parquet writes (up to 2.2 min) and the many short jobs are the data-quality counts. This is where stage times and skipped (cached) stages can be inspected."));
c.push(H2("C.2 Data generation"));
c.push(...SHOT(4, "Dataset generation (scale 0.1)", "python data_generation/dataset_generator.py --out data/raw --scale 0.1", "S04_generator.png",
  "200,000 sessions and 50,000 transactions were generated in 2 files in 71 s. The transaction target is reached between 100,000 and 150,000 sessions; after that, converted sessions no longer create orders - the root cause of the 15,552 gap reported in S9."));
c.push(H2("C.3 Part 1 - MongoDB"));
c.push(...SHOT(5, "Loading MongoDB", "python mongodb/load_mongodb.py --sessions-limit 50000", "S05_mongo_load.png",
  "All five collections loaded with batched `insert_many` (unordered) in about 10 s, and the indexes were created."));
c.push(...SHOT(6, "The four aggregation pipelines", "python mongodb/aggregations.py", "S06_mongo_aggregations.png",
  "One run shows all pipelines: (1) top sellers - 84 units for the best product; (2) revenue and estimated profit per category per month; (3a/3b) frequency and spend buckets - 313 users with 10+ orders average $11,449; (3c) top customers; (4) session funnel by referrer - about 20-21% of sessions flagged converted for every referrer."));
c.push(...SHOT(7, "mongosh: document counts and pipeline 1", "Get-Content mongodb\\evidence.js | docker exec -i mongo mongosh ecommerce --quiet", "S07_mongosh_pipeline1.png",
  "The same data queried directly in the MongoDB shell: 50,000 transactions, 10,000 users and 5,000 products, and the top-selling products pipeline with `$lookup` to current stock. Units, orders and revenue match the Python run (S6), proving the pipeline is identical in both clients."));
c.push(H2("C.4 Part 1 - HBase"));
c.push(...SHOT(8, "HBase shell: list, describe and a user prefix scan", "Get-Content hbase\\evidence.hbase | docker exec -i hbase hbase shell -n", "S08_hbase_shell.png",
  "`list` shows both tables; `describe` shows the column families with VERSIONS 1, ROW bloom filter and the 180-day TTL on `pv`. The prefix scan of `user_000042|` returns that user's 3 most recent sessions first, without any sort - the reversed timestamp in the row key at work; `info` holds one cell per attribute."));
c.push(H2("C.5 Part 2 - Spark processing"));
c.push(...SHOT(9, "Cleaning job and data-quality report", "docker compose exec -T app python spark/01_clean_normalize.py", "S09_spark_clean.png",
  "All 200,000 sessions, 50,000 transactions and 10,000 users passed validation: 0 duplicates, 0 invalid rows, 0 orphan ids and 0 total mismatches. The one material issue - **15,552 converted sessions without a transaction** - is flagged rather than deleted. Runtime 1,190 s, mostly multi-line JSON parsing.", 6.5, 8.2));
c.push(...SHOT(10, "Recommendation indicators", "docker compose exec -T app python spark/02_recommendations.py", "S10_recommendations.png",
  "Bought-together: only 304 product pairs occur twice or more in 50,000 baskets, and their very high lifts (up to 435) come from tiny counts. Viewed-together: 59,127 pairs. Category lift ~0.79 (< 1). Together these show the random synthetic data contains no real affinity - the method is sound but needs support thresholds on real data."));
c.push(...SHOT(11, "Cohort analysis", "docker compose exec -T app python spark/03_cohort_analysis.py", "S11_cohort.png",
  "Seven registration cohorts (Feb-Aug 2026): about 80-84% of each cohort buys in each full month (September, October); August and November are partial months. Revenue per member over 90 days is flat ($5,253-$5,370), so cohort age makes no difference."));
c.push(...SHOT(12, "Spark SQL analytics", "docker compose exec -T app python spark/04_spark_sql_analytics.py", "S12_spark_sql.png",
  "Part A: top-3 products per category (RANK), funnel by device/referrer with ROLLUP (12.6% of all 200,000 sessions have an order), 7-day rolling revenue, price-change impact (≈0.51 → ≈0.49 units/day for every price move) and viewed-vs-sold ranks. Part B: MongoDB-shaped users joined with HBase-shaped sessions - spend rises from $4,731 (<15 sessions) to $6,010 (25+).", 6.5, 8.6));
c.push(H2("C.6 Part 3 - Integrated analytics"));
c.push(...SHOT(13, "Customer Lifetime Value (MongoDB + HBase via Spark)", "docker compose exec -T app python integration/clv_analysis.py --mongo mongo --hbase hbase", "S13_clv.png",
  "Spark read users and orders from MongoDB and sessions from HBase in 100 row-key ranges, estimated retention r = 0.830 (5.9-month lifetime) and produced the segment, tier and correlation tables of Section 5.1. ==It scanned 186,713 sessions because HBase was only partly loaded; retake after the full reload (expect 200,000).=="));
c.push(...SHOT(14, "Funnel conversion (HBase journeys + MongoDB purchases)", "docker compose exec -T app python integration/funnel_analysis.py --mongo mongo --hbase hbase", "S14_funnel.png",
  "Stage counts, device, referrer and weekly funnels, and the generator-vs-MongoDB reconciliation (38,054 flagged vs 25,197 real orders). ==Retake after the full HBase reload: this run saw 186,713 sessions and 0 product_metrics rows, so the category table is empty. Expected: 200,000 sessions, 40,749 flagged vs 25,197 purchases (12.6%) and a filled category table.=="));

// ======================================================================================= DOCUMENT
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
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 21, bold: true, font: FONT }, paragraph: { spacing: { before: 120, after: 60 }, outlineLevel: 2, keepNext: true } },
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
      children: [new TextRun({ text: "AUCA Big Data Analytics - Final Project  |  Godfrey Mushambo", size: 16, color: "8A8984" })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: ["Page ", PageNumber.CURRENT], size: 16, color: "8A8984" })] })] }) },
    children: c,
  }],
});
Packer.toBuffer(doc).then(buf => {
  const out = path.join(__dirname, "Technical_Report_Final.docx");
  fs.writeFileSync(out, buf);
  console.log("wrote", out);
});
