// build_submission.js - builds the two submission documents from the final live-run results:
//   report/Technical_Report.docx             main report, 6-8 pages (brief: "Technical Report, target 6-8 pages")
//   report/Technical_Report_Appendices.docx  Appendix A reproduce, B key scripts, C evidence screenshots
// Yellow highlight = something the author must still fill in.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, ImageRun, LevelFormat, PageBreak, Footer, PageNumber, Header,
} = require("docx");

const ROOT = path.resolve(__dirname, "..");
const FIG = path.join(__dirname, "final_figures");
const EVD = path.join(__dirname, "evidence");
const MARGIN = 1134;                       // 2 cm
const W = 11906 - 2 * MARGIN;              // content width (DXA)
const FONT = "Calibri", MONO = "Consolas", BLUE = "2A78D6", BODY = 21, SMALL = 17;

function runs(text, base = {}) {
  const out = [], re = /(\*\*[^*]+\*\*|`[^`]+`|==[^=]+==|\*[^*]+\*)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ text: t.slice(2, -2), bold: true, ...base }));
    else if (t.startsWith("`")) out.push(new TextRun({ text: t.slice(1, -1), font: MONO, size: (base.size || BODY) - 2, ...base, ...{ font: MONO } }));
    else if (t.startsWith("==")) out.push(new TextRun({ text: t.slice(2, -2), highlight: "yellow", bold: true, ...base }));
    else out.push(new TextRun({ text: t.slice(1, -1), italics: true, ...base }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}
const P = (t, o = {}) => new Paragraph({ children: runs(t), spacing: { after: 110, line: 264 }, alignment: AlignmentType.JUSTIFIED, ...o });
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const B = (t) => new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: runs(t), spacing: { after: 40 }, alignment: AlignmentType.JUSTIFIED });
const N = (t) => new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: runs(t), spacing: { after: 40 } });
const PB = () => new Paragraph({ children: [new PageBreak()] });
const SP = (a = 40) => new Paragraph({ children: [], spacing: { after: a } });

function CODE(text, size = 14) {
  return text.replace(/\s+$/, "").split("\n").map((line, i, arr) => new Paragraph({
    children: [new TextRun({ text: line.length ? line : " ", font: MONO, size })],
    shading: { type: ShadingType.CLEAR, fill: "F4F4F2" },
    spacing: { before: 0, after: i === arr.length - 1 ? 100 : 0, line: 228 }, indent: { left: 100, right: 100 },
  }));
}
const border = { style: BorderStyle.SINGLE, size: 4, color: "D6D5D0" };
const borders = { top: border, bottom: border, left: border, right: border };
const none = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const noBorders = { top: none, bottom: none, left: none, right: none };
function TABLE(header, rows, pct, size = SMALL) {
  const widths = pct.map(p => Math.round(W * p));
  widths[widths.length - 1] += W - widths.reduce((a, b) => a + b, 0);
  const cell = (t, i, head) => new TableCell({
    borders, width: { size: widths[i], type: WidthType.DXA },
    shading: head ? { type: ShadingType.CLEAR, fill: "EEF4FC" } : undefined,
    margins: { top: 30, bottom: 30, left: 70, right: 70 },
    children: [new Paragraph({ children: runs(String(t), { size, bold: head || undefined }) })],
  });
  return new Table({
    width: { size: W, type: WidthType.DXA }, columnWidths: widths,
    rows: [new TableRow({ tableHeader: true, children: header.map((h, i) => cell(h, i, true)) }),
           ...rows.map(r => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, i, false)) }))],
  });
}
function pngSize(f) { const b = fs.readFileSync(f); return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) }; }
function imgRun(file, widthIn, maxHIn = 9) {
  const s = pngSize(file);
  let w = widthIn * 96, h = w * s.h / s.w;
  if (h > maxHIn * 96) { h = maxHIn * 96; w = h * s.w / s.h; }
  return new ImageRun({ type: "png", data: fs.readFileSync(file), transformation: { width: w, height: h },
    altText: { title: path.basename(file), description: path.basename(file), name: path.basename(file) } });
}
const caption = (t) => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 20, after: 120 },
  children: runs(t, { size: 15, italics: true, color: "52514E" }) });
function FIGURE(file, cap, widthIn) {
  return [new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 60 }, children: [imgRun(path.join(FIG, file), widthIn)] }),
          caption(cap)];
}
// two figures side by side
function PAIR(f1, c1, f2, c2, w1 = 0.5) {
  const a = Math.round(W * w1), b = W - a;
  const cell = (f, cap, wd) => new TableCell({ borders: noBorders, width: { size: wd, type: WidthType.DXA },
    margins: { left: 40, right: 40 },
    children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [imgRun(path.join(FIG, f), wd / 1440 - 0.1)] }), caption(cap)] });
  return new Table({ width: { size: W, type: WidthType.DXA }, columnWidths: [a, b],
    rows: [new TableRow({ cantSplit: true, children: [cell(f1, c1, a), cell(f2, c2, b)] })] });
}
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");

function makeDoc(children, headerText) {
  return new Document({
    creator: "Godfrey Mushambo",
    title: "Distributed Multi-Model Analytics for E-commerce Data",
    styles: {
      default: { document: { run: { font: FONT, size: BODY } } },
      paragraphStyles: [
        { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: 25, bold: true, color: "1B1B1A", font: FONT },
          paragraph: { spacing: { before: 200, after: 80 }, outlineLevel: 0, keepNext: true,
                       border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: BLUE, space: 2 } } } },
        { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: 21, bold: true, color: BLUE, font: FONT },
          paragraph: { spacing: { before: 120, after: 50 }, outlineLevel: 1, keepNext: true } },
      ],
    },
    numbering: { config: [
      { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 340, hanging: 220 } } } }] },
      { reference: "numbers", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 340, hanging: 260 } } } }] },
    ] },
    sections: [{
      properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 960, bottom: 900, left: MARGIN, right: MARGIN } } },
      headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
        children: [new TextRun({ text: headerText, size: 14, color: "8A8984" })] })] }) },
      footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new TextRun({ children: ["Page ", PageNumber.CURRENT], size: 14, color: "8A8984" })] })] }) },
      children,
    }],
  });
}

// =========================================================================== MAIN REPORT (6-8 pages)
const c = [];
c.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 40 },
  children: [new TextRun({ text: "Distributed Multi-Model Analytics for E-commerce Data", bold: true, size: 34 })] }));
c.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 40 },
  children: [new TextRun({ text: "Technical Report  ·  MongoDB, HBase and Apache Spark  ·  AUCA Big Data Analytics Final Project", size: 19, color: BLUE })] }));
c.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 140 },
  children: runs("Godfrey Mushambo (Student ID 101376)  ·  Lecturer: Temitope Oguntade  ·  Code: ==[GitHub repository URL]==", { size: 18 }) }));

// 1
c.push(H1("1. Executive summary"));
c.push(P("MongoDB stores the business entities (catalogue, customers, orders), HBase stores the high-volume, time-ordered click-stream and daily product metrics, and Spark cleans the data, runs the batch analytics and joins the two stores. All components ran in Docker (MongoDB 7, HBase 2.1.2, Spark 3.5.3). Dataset (10% scale, seed 42): 10,000 users, 5,000 products, 25 categories, 200,000 sessions, 50,000 transactions, 12 Aug - 10 Nov 2026. Scripts and evidence screenshots (S1-S14) are in the separate *Appendices* document and the repository."));
c.push(TABLE(["Net revenue", "Sessions with a purchase", "Checkout abandonment", "CLV held by 17% of customers"],
  [["$53.2M · 50,000 orders · AOV $1,064", "12.6% (25,197 of 200,000)", "57% of checkouts (33,018)", "27.9% ('Champions')"]], [0.25, 0.25, 0.25, 0.25]));
c.push(SP(60));
c.push(B("**The funnel leaks after the cart.** 98.8% of sessions view a product and 65% add to cart, but only 45% of carts reach checkout and 43% of checkouts become orders - up to ~$25M of unrealised revenue at the $771 average web order."));
c.push(B("**Stock-outs drive the views-sales link.** r = 0.69 across all products but only 0.12 among in-stock products; the 209 sold-out products lost ~60% of their page views."));
c.push(B("**Value is concentrated and partly at risk:** 1,729 Champions hold 27.9% of estimated lifetime value; 1,084 high-value customers have lapsed ~27 days ($4.2M CLV)."));
c.push(B("**Revenue is flat, profit is not:** ~$592k/day (s.d. $31k), category revenue within -17%/+15% of the mean, but margins of 18-36% double the profit spread."));
c.push(B("**Reconciling the stores exposes data issues:** 15,552 of 40,749 sessions flagged 'converted' have no order in MongoDB."));

// 2
c.push(H1("2. System architecture"));
c.push(...FIGURE("fig0_architecture.png", "Figure 1 - Architecture: the generator feeds MongoDB, HBase and Spark; Spark joins all sources; everything runs in Docker (containers mongo, hbase, app).", 6.9));
c.push(P("Python loaders write the raw JSON into the two stores; Spark reads the same JSON with explicit schemas and writes a cleaned Parquet lake. Analyses read through one access layer (`integration/sources.py`) that returns identical DataFrames from Parquet, MongoDB (aggregation pushed down to the server) or HBase (row-key range scans), so analysis code is independent of storage. The course generator was kept but fixed: products now get their `subcategory_id`, sessions are streamed to disk in 100k chunks (the original needs >10 GB RAM at full scale), IDs are seeded for reproducibility, and a `--scale` option was added (S4)."));

// 3
c.push(H1("3. Data modelling and storage (Part 1)"));
c.push(H2("3.1 MongoDB document model"));
c.push(TABLE(["Collection", "Shape", "Pattern and justification"], [
  ["categories", "category + `subcategories[]` with profit_margin", "Embedded hierarchy: small, bounded, always read together."],
  ["products", "product + `category{id,name}` + `subcategory{id,name,margin}` + `price_history[]`", "Extended reference: catalogue pages and margin maths need no $lookup; bounded price history embedded."],
  ["transactions", "order + `items[]` (product_name, category_id, subcategory_id); BSON Date", "Line items embedded: one atomic write per order; revenue by category is a pure $unwind/$group."],
  ["users", "profile + geo + `purchase_summary{total_spent, order_count, AOV, favourite category, last 5 orders}`", "Computed/subset pattern: frequently read facts pre-aggregated; full history stays in transactions."],
  ["sessions (50k)", "journey with `page_views[]`, `cart_contents[]`", "Whole journey in one document for journey queries; full click-stream in HBase."],
], [0.13, 0.42, 0.45]));
c.push(SP(40));
c.push(P("Indexes match the queries: `{user_id, timestamp}`, `{timestamp}`, multikey `{items.product_id}`, `{purchase_summary.total_spent}`, `{category.category_id, is_active}`. All 120,025 documents loaded in ~10 s (S5). **Four aggregation pipelines** (S6, S7; code in Appendix B.3): (1) **product popularity** - `$unwind` → `$group` → `$sort` → `$lookup` for stock (top product: 84 units, 35 orders); (2) **revenue** and estimated profit by category and month, matching each item to its subcategory margin with `$filter`; (3) **user segmentation** by purchase frequency and spend with `$facet` + `$bucket` (313 users with 10+ orders average $11,449 vs $1,833 for 1-2 orders); (4) **journey funnel** over the embedded `page_views` array by referrer."));
c.push(H2("3.2 HBase wide-column model"));
c.push(TABLE(["Table", "Row key", "Column families", "Queries served"], [
  ["user_sessions", "`user_id|reverse_ts|session_id`, reverse_ts = 9999999999999 - epoch_ms", "**info** session header (15 cells); **pv** one column per page view; **cart** one column per product", "Latest sessions of a user (prefix scan, newest first); a time window (STARTROW/STOPROW); one session (get)"],
  ["product_metrics", "`product_id|yyyymmdd`", "**m**: views, cart_adds, purchases, units_sold, revenue_cents", "A product's history or date range in one contiguous scan; atomic `incr` counters for streaming"],
], [0.14, 0.27, 0.3, 0.29]));
c.push(SP(40));
c.push(P("Putting `user_id` first keeps each user's activity contiguous; the reversed timestamp returns the newest session first without sorting. Families follow access patterns: listing sessions reads only the small `info` family; the variable-width, sparse `pv` and `cart` families are read only on drill-down. VERSIONS = 1 (immutable events), ROW bloom filters, a 180-day TTL on `pv` and four pre-split points (5 regions per table, S2) complete the design. Loaded: 200,000 session rows and 342,423 product-day rows. Queries for a specific user, e.g. `scan 'user_sessions', {ROWPREFIXFILTER => 'user_000042|', COLUMNS => ['info'], LIMIT => 5}`, are in Appendix B.2 and S8."));
c.push(H2("3.3 Why each dataset went to MongoDB or HBase"));
c.push(TABLE(["Criterion", "MongoDB (catalogue, users, orders)", "HBase (sessions, product metrics)"], [
  ["Data shape and volume", "Rich nested entities, modest volume", "Append-only events, very high volume (~20M page views at full scale), counters"],
  ["Query pattern", "Ad-hoc filters, secondary indexes, aggregation framework", "Known key paths: per-user timelines, per-product time ranges"],
  ["Schema and writes", "Flexible documents; atomic per document", "Sparse variable columns; very high write rate; automatic region sharding"],
], [0.2, 0.4, 0.4]));

// 4
c.push(H1("4. Spark processing pipeline (Part 2)"));
c.push(P("**Cleaning and normalisation** (`01_clean_normalize.py`): all JSON files, including the `sessions_*.json` glob, are read with explicit schemas (no second inference pass, no type drift) and written as nine Parquet tables - users, flattened category hierarchy, products with margins, price history, sessions (date-partitioned, with funnel flags), exploded page views and cart items, transactions with reconciliation flags, and line items with pro-rated discounts and margins (broadcast join). Rules: de-duplicate on keys; drop rows with missing keys or bad timestamps; trim and normalise enums and codes; clamp negatives; fill missing descriptive values; repair `conversion_status`; and *flag* rather than drop inconsistencies. The data-quality report (S9) found 0 duplicates, 0 invalid rows and 0 orphans, and flagged 15,552 converted sessions without an order."));
c.push(P("**Recommendation indicators** (`02_recommendations.py`): association rules (support, confidence, lift, top-5 per product via a window) for 'bought together' (self-join on transaction, x < y) and 'viewed together' (pairs built inside each session's array with higher-order functions - no shuffle-heavy join). Only 304 product pairs occur twice or more in 50,000 baskets, so their lifts (median 155) are small-count noise, and category lift is ~0.79 (S10): the synthetic data has no real affinity, which validates the method as a null test. **Cohort analysis** (`03_cohort_analysis.py`): users grouped by registration month (Feb-Aug) and followed monthly; about 80-84% of every cohort buys in each full month and 90-day revenue per member is flat at $5,253-$5,370 (S11, Figure 7)."));
c.push(P("**Spark SQL** (`04_spark_sql_analytics.py`, S12): CTE + RANK top-3 products per category; ROLLUP funnel by device and referrer; 7-day RANGE window and week-over-week LAG on daily revenue; price-change impact with MAX_BY over exploded price history (≈0.51 → ≈0.49 units/day after any price move - no elasticity); and viewed-vs-sold ranks. To query data that notionally lives in the stores, views shaped like **MongoDB documents** (`mongo_users` with nested `purchase_summary`; `mongo_transactions` with an `items` array queried via `LATERAL VIEW explode`, Spark's `$unwind`) and like **HBase rows** (`rowkey` + `info:*` columns, key parsed with `SPLIT`) are joined in SQL (Appendix B.4)."));
c.push(P("**Optimisations:** explicit schemas; Parquet + Snappy with date partitioning (partition pruning); broadcast joins for small dimensions; adaptive query execution; caching only reused DataFrames; array functions instead of joins; pruning rare pairs before ranking; fewer shuffle partitions on one machine. Cleaning took ~20 min on a laptop (S9), dominated by multi-line JSON, which cannot be split across tasks - JSON Lines would remove this bottleneck."));

// 5
c.push(H1("5. Integrated analytics (Part 3)"));
c.push(H2("5.1 Customer Lifetime Value - integration/clv_analysis.py"));
c.push(P("**Business question:** which customers are worth most over their expected lifetime, how engaged are they, and who should receive retention spend? **Sources:** user profiles and orders from **MongoDB** (`$unwind` and discount pro-ration pushed into the pipeline); engagement - session count, duration, pages, cart rate - from **HBase** `user_sessions`; margins from the category dimension. **Spark:** joins the sources per user, estimates monthly buyer retention from the data (r = 0.830 → expected lifetime 1/(1-r) = 5.9 months), computes CLV = AOV × orders per month × margin × lifetime, and maps RFM quintiles (NTILE windows) to segments (S13)."));
c.push(TABLE(["Segment", "Users", "Avg CLV", "Share of CLV", "Recency (days)", "Sessions (HBase)", "Session→order"], [
  ["Champions", "1,729", "$4,329", "27.9%", "3.9", "21.1", "17.1%"],
  ["At risk - high value", "1,084", "$3,910", "15.8%", "26.7", "20.2", "14.3%"],
  ["Loyal", "1,260", "$3,395", "16.0%", "9.4", "21.1", "17.9%"],
  ["Needs attention", "1,939", "$2,282", "16.5%", "8.9", "19.6", "10.9%"],
  ["New / promising", "1,041", "$1,663", "6.5%", "4.3", "19.1", "9.1%"],
  ["Hibernating", "2,896", "$1,608", "17.4%", "35.0", "19.4", "9.5%"],
], [0.22, 0.1, 0.12, 0.13, 0.14, 0.15, 0.14]));
c.push(SP(40));
c.push(P("Platinum customers (top CLV quartile) average 20.9 sessions and a 16.2% session-to-order rate against 19.3 and 9.0% for Bronze: value comes from **conversion efficiency**, not browsing time (correlation of CLV with session duration 0.02, with session count 0.13)."));
c.push(H2("5.2 Funnel conversion - integration/funnel_analysis.py"));
c.push(P("**Business question:** where do shoppers drop out, does it differ by device, traffic source or category, and what is the loss worth? **Sources:** journey stages from **HBase** `user_sessions` (`pv`, `cart` families); category views and cart adds from **HBase** `product_metrics`; purchases from **MongoDB** transactions as the source of truth. **Spark:** builds per-session stage flags, left-joins orders on `session_id`, and aggregates by stage, device, referrer, category and week (S14). Result: 200,000 → 197,509 product view → 130,126 cart → 58,215 checkout → 25,197 purchase (Figure 3). Purchase rates differ by < 0.1 point between devices (12.57-12.62%) and < 0.5 between referrers (12.34-12.79%); category view-to-cart rates span only 29.4-30.6%. The loss is a checkout-process problem, not a channel or assortment problem. Using MongoDB as the source of truth matters: the generator flags 40,749 sessions as converted, but only 25,197 have an order."));
c.push(H2("5.3 Technology fit and performance"));
c.push(P("MongoDB serves profiles and orders with server-side aggregation; HBase serves per-user, time-ordered events by key range; Spark performs what neither does well - large cross-store joins and window/statistical computation. A single full-table Thrift scan stalled on single-node HBase, so the reader scans 100 user-id ranges (50 product ranges) and retries a failed range on a new connection (Appendix B.6) - the access path the row key was designed for. At scale, the hbase-spark connector or snapshot export and the MongoDB Spark connector would read partitions in parallel on executors; joins use high-cardinality keys with small dimensions broadcast."));

// 6
c.push(H1("6. Visualisations and insights (Part 4)"));
c.push(P("Seven static charts (matplotlib, `visualization/make_charts.py`) built from the live-run result tables cover the four kinds of view the brief suggests: sales over time and by category, conversion funnel, product performance, and customer segmentation."));
c.push(...FIGURE("fig1_daily_revenue.png", "Figure 2 - Sales performance over time: daily net revenue with a 7-day rolling average (Spark SQL window query).", 6.0));
c.push(...FIGURE("fig3_conversion_funnel.png", "Figure 3 - Conversion funnel stages over 200,000 sessions (HBase journeys × MongoDB orders); step % = conversion from the previous stage.", 6.0));
c.push(...FIGURE("fig2_category_revenue_profit.png", "Figure 4 - Sales by category: revenue vs estimated gross profit (MongoDB pipeline 2); margins 18-36%.", 6.0));
c.push(...FIGURE("fig6_viewed_vs_sold.png", "Figure 5 - Product performance, most-viewed vs top-selling: each dot is a product; sold-out products lose page views.", 4.8));
c.push(...FIGURE("fig4_clv_segments.png", "Figure 6 - Customer segmentation: RFM segments by size (left) and average estimated CLV with share of total CLV (right).", 6.2));
c.push(PAIR("fig5_cohort_retention.png", "Figure 7 - Cohort analysis: share of each registration cohort buying per month.",
            "fig7_engagement_vs_spend.png", "Figure 8 - Engagement (HBase sessions) vs spend (MongoDB users)."));
c.push(H2("6.1 Key findings and recommended actions"));
c.push(B("**Fix checkout first** - the largest controllable loss (33,018 sessions). Guest checkout, saved payment methods and cart-recovery e-mails: a 5-point lift adds ~2,900 orders (~$2.2M) per 90 days."));
c.push(B("**Replenish before stock-out** using `product_metrics` views and units - sold-out items lose ~60% of their visibility (Figure 5)."));
c.push(B("**Win back 'At risk - high value' customers** (1,084 users, $4.2M estimated CLV) before they hibernate (Figure 6)."));
c.push(B("**Merchandise by margin, not revenue** - revenue is even across categories but profit varies two-fold (Figure 4); engaged users (25+ sessions) spend 27% more than those with fewer than 15 (Figure 8)."));

// 7
c.push(H1("7. Methodology for key analyses"));
c.push(B("**Funnel:** a session reaches a stage if its page sequence contains it; 'checkout' also requires a non-empty cart; 'purchase' requires a MongoDB order with that session_id."));
c.push(B("**CLV:** retention-based model; partial edge months excluded when estimating retention; lifetime capped at 36 months; margin from each item's subcategory. **RFM:** quintiles over buyers, mapped to six named segments."));
c.push(B("**Recommendations:** lift = confidence / P(consequent), minimum pair count 2. **Cohorts:** calendar-month difference between registration and purchase."));

// 8
c.push(H1("8. Scalability and technology selection"));
c.push(TABLE(["Analytical task", "Technology and why", "Scaling path"], [
  ["Catalogue, profiles, order look-ups and aggregations", "**MongoDB** - nested documents, secondary indexes, aggregation framework", "Shard transactions on hashed user_id; replica sets for reads"],
  ["Click-stream, user timelines, product time series", "**HBase** - key-ordered sparse wide rows, high write rate, counters", "Automatic region splits, pre-splitting; salt keys if hot-spots appear"],
  ["Cleaning, co-occurrence, cohorts, CLV, cross-store joins", "**Spark** - distributed in-memory DataFrames and SQL over all sources", "Cluster on YARN/Kubernetes; partitioned Parquet; parallel connectors; Structured Streaming"],
], [0.3, 0.38, 0.32]));
c.push(SP(40));
c.push(P("Processing grows linearly with data: the full dataset (2M sessions, ~4 GB JSON) needs only more partitions. Pair generation is the only super-linear step and is bounded by the 15-page session cap. In production, events would arrive via Kafka, update HBase counters through Spark Structured Streaming, and be compacted nightly to Parquet."));

// 9
c.push(H1("9. Limitations and future work"));
c.push(B("**Synthetic data has little behavioural signal:** uniform devices, referrers and categories; no cohort decay; no price elasticity; product-pair rules suffer from small counts. Real data would need support thresholds, significance tests or collaborative filtering (Spark ALS)."));
c.push(B("**Generator artefacts:** once the transaction target is reached, converted sessions stop producing orders (the 15,552 gap); half the orders have no session; there is no age field, so segmentation is behavioural rather than by age group."));
c.push(B("**Infrastructure:** single-node HBase in Docker was the weak point - it stopped once under memory pressure and stalled on long scans, which led to the retrying range-scan reader. **Future work:** JSON Lines input, Spark ALS, streaming counters, probabilistic (BG/NBD) CLV, an interactive dashboard."));

// 10 coverage
c.push(H1("10. Coverage of the project brief"));
c.push(TABLE(["Brief requirement", "Where it is answered"], [
  ["P1 MongoDB: catalogue with category hierarchy, user profiles with embedded summary, transactions with line items; loaded subset; ≥ 2 non-trivial pipelines (popularity, segmentation, revenue)", "§3.1, Appendix B.3, S5-S7 (4 pipelines)"],
  ["P1 HBase: column families for time-series sessions and product metrics; loaded subset; queries for a specific user; schema commands", "§3.2, Appendix B.1-B.2, S2, S8"],
  ["P1 design justification and MongoDB vs HBase comparison", "§3.1-3.3"],
  ["P2 Spark cleaning/normalisation; recommendation indicators or cohort analysis (both done)", "§4, S9-S11"],
  ["P2 Spark SQL complex queries + querying MongoDB/HBase-shaped data; pipeline explanation and optimisations", "§4, Appendix B.4, S12"],
  ["P3 integrated query: business question, sources, processing steps, Spark's role, technology fit, performance (two queries: CLV and funnel)", "§5.1-5.3, Appendix B.5-B.6, S13-S14"],
  ["P4 ≥ 3-4 static visualisations: sales over time and by category, segmentation, top-selling vs most-viewed, funnel", "§6, Figures 2-8"],
  ["Report checklist: architecture · modelling · Spark · integration · scalability · technology selection · findings · visualisations · methodology · limitations", "§2 · §3 · §4 · §5 · §8 · §8 · §1, 6.1 · §6 · §7 · §9"],
  ["Repository: all code, sample queries, reproduction instructions", "GitHub repository, README.md, Appendix A"],
], [0.68, 0.32]));

// =========================================================================== APPENDICES DOCUMENT
const a = [];
a.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 40 },
  children: [new TextRun({ text: "Appendices to the Technical Report", bold: true, size: 32 })] }));
a.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 160 },
  children: runs("Distributed Multi-Model Analytics for E-commerce Data  ·  Godfrey Mushambo (101376)  ·  A: reproduce · B: key scripts · C: evidence screenshots S1-S14", { size: 18, color: "52514E" }) }));

a.push(H1("Appendix A - How to reproduce"));
a.push(P("Everything runs in Docker. From Windows PowerShell, in the project folder:"));
a.push(...CODE(`docker compose up -d --build                      # mongo :27017, hbase :9090 / UI :16010, app (Spark UI :4040)
docker compose exec -T app python wait_for_services.py
.\\run_all.ps1                                     # whole pipeline (or .\\run_all.ps1 -Scale 1.0)
.\\evidence.ps1                                    # re-creates the evidence screenshots step by step`, 15));
a.push(TABLE(["Step", "Command (prefix each with  docker compose exec -T app )", "Output"], [
  ["1 Generate data", "`python data_generation/dataset_generator.py --out data/raw --scale 0.1`", "data/raw/*.json"],
  ["2 MongoDB", "`python mongodb/load_mongodb.py --sessions-limit 50000`; `python mongodb/aggregations.py`", "5 collections, indexes, output/mongo_*.csv"],
  ["3 HBase", "`python hbase/load_hbase.py --recreate`; `python hbase/query_hbase.py`", "2 tables; queries Q1-Q5"],
  ["4 Spark clean", "`python spark/01_clean_normalize.py`", "data/clean/*.parquet, data_quality_report.csv"],
  ["5 Spark analytics", "`python spark/02_recommendations.py`; `03_cohort_analysis.py`; `04_spark_sql_analytics.py`", "output/reco_*, cohort_*, sql_*.csv"],
  ["6 Integration", "`python integration/clv_analysis.py --mongo mongo --hbase hbase`; `python integration/funnel_analysis.py --mongo mongo --hbase hbase`", "output/clv_*.csv, funnel_*.csv"],
  ["7 Charts", "`python visualization/make_charts.py`", "report/figures/*.png"],
  ["Shells", "`Get-Content mongodb\\evidence.js | docker exec -i mongo mongosh ecommerce --quiet`; `Get-Content hbase\\evidence.hbase | docker exec -i hbase hbase shell -n`", "S7, S8"],
], [0.15, 0.6, 0.25]));
a.push(SP(80));
a.push(TABLE(["Repository path", "Purpose"], [
  ["data_generation/dataset_generator.py", "Improved generator (original kept as dataset_generator_original.py)"],
  ["mongodb/load_mongodb.py, aggregations.py, aggregations.js, evidence.js", "Document model, bulk load, indexes, 4 pipelines"],
  ["hbase/create_tables.hbase, load_hbase.py, query_hbase.py, sample_queries.hbase, hbase_client.py", "Schema, loader, queries, Thrift client + local emulator"],
  ["spark/spark_utils.py, 01-04 *.py", "Explicit schemas, cleaning, recommendations, cohorts, Spark SQL"],
  ["integration/sources.py, clv_analysis.py, funnel_analysis.py", "Source-independent loaders (range scans) and the two integrated queries"],
  ["visualization/make_charts.py, report/make_architecture_diagram.py", "Charts and architecture diagram"],
  ["Dockerfile, docker-compose.yml, run_all.ps1, run_all.sh, evidence.ps1, wait_for_services.py, README.md", "Docker environment, orchestration, documentation"],
], [0.55, 0.45]));

a.push(PB());
a.push(H1("Appendix B - Key scripts"));
a.push(H2("B.1 HBase schema creation (hbase/create_tables.hbase)"));
a.push(...CODE(read("hbase/create_tables.hbase")));
a.push(H2("B.2 HBase sample queries (hbase/sample_queries.hbase)"));
a.push(...CODE(read("hbase/sample_queries.hbase")));
a.push(H2("B.3 MongoDB aggregation pipelines (mongodb/aggregations.js)"));
a.push(...CODE(read("mongodb/aggregations.js")));
a.push(H2("B.4 Spark SQL over MongoDB-shaped and HBase-shaped data (excerpt)"));
a.push(...CODE(`WITH engagement AS (                                     -- HBase: user_sessions rows
    SELECT SPLIT(rowkey, '\\\\|')[0]               AS user_id,
           COUNT(*)                               AS sessions,
           ROUND(AVG(\`info:duration\`) / 60, 1)   AS avg_session_min
    FROM hbase_user_sessions GROUP BY 1
)
SELECT CASE WHEN e.sessions >= 25 THEN '25+ sessions' WHEN e.sessions >= 20 THEN '20-24'
            WHEN e.sessions >= 15 THEN '15-19' ELSE '<15' END    AS engagement_band,
       COUNT(*)                                      AS users,
       ROUND(AVG(m.purchase_summary.order_count), 2) AS avg_orders,       -- MongoDB: users document
       ROUND(AVG(m.purchase_summary.total_spent), 2) AS avg_spent
FROM mongo_users m JOIN engagement e ON m._id = e.user_id
GROUP BY 1 ORDER BY 1;`));
a.push(H2("B.5 CLV core computation (integration/clv_analysis.py, excerpt)"));
a.push(...CODE(`purchases = (items_m.groupBy("user_id").agg(
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
a.push(H2("B.6 Robust HBase reader: row-key range scans with retry (integration/sources.py)"));
a.push(...CODE(fs.readFileSync("/tmp/scan_excerpt.py", "utf8")));
a.push(H2("B.7 Docker environment (docker-compose.yml)"));
a.push(...CODE(read("docker-compose.yml")));

function SHOT(n, title, command, file, comment, widthIn = 6.9, maxH = 8.2) {
  return [
    new Paragraph({ keepNext: true, spacing: { before: 160, after: 30 }, children: runs(`**S${n} - ${title}**`, { size: 20 }) }),
    new Paragraph({ keepNext: true, spacing: { after: 30 }, children: runs(`Command: \`${command}\``, { size: 16, color: "52514E" }) }),
    new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, children: [imgRun(path.join(EVD, file), widthIn, maxH)] }),
    new Paragraph({ spacing: { before: 50, after: 140 }, alignment: AlignmentType.JUSTIFIED,
      border: { left: { style: BorderStyle.SINGLE, size: 18, color: BLUE, space: 6 } }, indent: { left: 140 },
      children: runs(`**Comment:** ${comment}`, { size: 18 }) }),
  ];
}
a.push(PB());
a.push(H1("Appendix C - Evidence screenshots (live Docker run)"));
a.push(H2("C.1 Environment"));
a.push(...SHOT(1, "Running containers", "docker compose ps", "S01_docker_ps.png",
  "The three project containers - app (Python 3.11 + Java 17 + PySpark), hbase (HBase + Thrift) and mongo (MongoDB 7) - are up, with ports 4040, 9090/16010/2181 and 27017 published."));
a.push(...SHOT(2, "HBase master web UI", "http://localhost:16010", "S02_hbase_master_ui.png",
  "HBase 2.1.2 with one region server. Both user tables are ENABLED with **5 regions each**, proving the 4 pre-split points took effect; the description lists the info, pv (TTL 180 days) and cart families."));
a.push(...SHOT(3, "Spark UI during the cleaning job", "http://localhost:4040", "S03_spark_ui.png",
  "Spark 3.5.3 ran 49 jobs for 01_clean_normalize: Parquet writes (up to 2.2 min) and the short data-quality counts; skipped stages show cached data being reused."));
a.push(H2("C.2 Data generation"));
a.push(...SHOT(4, "Dataset generation, scale 0.1", "python data_generation/dataset_generator.py --out data/raw --scale 0.1", "S04_generator.png",
  "200,000 sessions and 50,000 transactions in 2 files in 71 s. The transaction target is reached between 100,000 and 150,000 sessions; after that converted sessions create no orders - the source of the 15,552 gap."));
a.push(H2("C.3 Part 1 - MongoDB"));
a.push(...SHOT(5, "Loading MongoDB", "python mongodb/load_mongodb.py --sessions-limit 50000", "S05_mongo_load.png",
  "Five collections loaded with unordered batched inserts in ~10 s, then the indexes were created."));
a.push(...SHOT(6, "The four aggregation pipelines", "python mongodb/aggregations.py", "S06_mongo_aggregations.png",
  "Top sellers (84 units for the leader); revenue and estimated profit per category and month; frequency and spend segments (313 users with 10+ orders average $11,449); top customers; journey funnel by referrer (20-21% flagged converted for every referrer)."));
a.push(...SHOT(7, "mongosh: counts and pipeline 1", "Get-Content mongodb\\evidence.js | docker exec -i mongo mongosh ecommerce --quiet", "S07_mongosh_pipeline1.png",
  "Run directly in the MongoDB shell: 50,000 transactions, 10,000 users, 5,000 products; the top-selling pipeline with $lookup to current stock returns the same units, orders and revenue as the Python run (S6)."));
a.push(H2("C.4 Part 1 - HBase"));
a.push(...SHOT(8, "HBase shell: list, describe and a user prefix scan", "Get-Content hbase\\evidence.hbase | docker exec -i hbase hbase shell -n", "S08_hbase_shell.png",
  "Both tables listed; describe shows VERSIONS 1, ROW bloom filters and the 180-day TTL on pv. The prefix scan of user_000042| returns the user's newest sessions first without sorting - the reversed timestamp in the row key at work."));
a.push(H2("C.5 Part 2 - Spark processing"));
a.push(...SHOT(9, "Cleaning job and data-quality report", "docker compose exec -T app python spark/01_clean_normalize.py", "S09_spark_clean.png",
  "All 200,000 sessions, 50,000 transactions and 10,000 users validated: 0 duplicates, 0 invalid rows, 0 orphans, 0 total mismatches; 15,552 converted sessions without an order are flagged, not deleted. Runtime 1,190 s."));
a.push(...SHOT(10, "Recommendation indicators", "docker compose exec -T app python spark/02_recommendations.py", "S10_recommendations.png",
  "304 product pairs occur twice or more in 50,000 baskets (lifts up to 435 from tiny counts); 59,127 viewed-together pairs; category lift ~0.79. Conclusion: no real affinity in random synthetic data - the method needs support thresholds on real data."));
a.push(...SHOT(11, "Cohort analysis", "docker compose exec -T app python spark/03_cohort_analysis.py", "S11_cohort.png",
  "Seven registration cohorts; about 80-84% of each buys in each full month (Aug and Nov are partial); 90-day revenue per member is flat at $5,253-$5,370."));
a.push(...SHOT(12, "Spark SQL analytics", "docker compose exec -T app python spark/04_spark_sql_analytics.py", "S12_spark_sql.png",
  "Part A: top-3 per category, ROLLUP funnel (12.6% of 200,000 sessions have an order), 7-day rolling revenue, price-change impact, viewed-vs-sold ranks. Part B: MongoDB-shaped users joined with HBase-shaped sessions - spend rises from $4,731 (<15 sessions) to $6,010 (25+).", 6.6, 9.0));
a.push(H2("C.6 Part 3 - Integrated analytics"));
a.push(...SHOT(13, "Customer Lifetime Value (MongoDB + HBase via Spark)", "docker compose exec -T app python integration/clv_analysis.py --mongo mongo --hbase hbase", "S13_clv.png",
  "Spark read orders from MongoDB and all 200,000 sessions from HBase in 100 row-key ranges, estimated retention r = 0.830 (5.9-month lifetime) and produced the segment, tier and correlation tables of §5.1."));
a.push(...SHOT(14, "Funnel conversion (HBase journeys + MongoDB purchases)", "docker compose exec -T app python integration/funnel_analysis.py --mongo mongo --hbase hbase", "S14_funnel.png",
  "200,000 sessions and 342,423 product-day rows read from HBase; funnel 200,000 → 197,509 → 130,126 → 58,215 → 25,197 (12.6%); 40,749 flagged vs 25,197 real orders; $25.5M unrealised at checkout; device, referrer, category and weekly breakdowns are all within ~1 point."));

const hdr = "AUCA Big Data Analytics - Final Project  |  Godfrey Mushambo (101376)";
Promise.all([
  Packer.toBuffer(makeDoc(c, hdr)).then(b => fs.writeFileSync(path.join(__dirname, "Technical_Report.docx"), b)),
  Packer.toBuffer(makeDoc(a, hdr + "  |  Appendices")).then(b => fs.writeFileSync(path.join(__dirname, "Technical_Report_Appendices.docx"), b)),
]).then(() => console.log("wrote Technical_Report.docx and Technical_Report_Appendices.docx"));
