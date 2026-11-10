// aggregations.js - the same analytics pipelines as aggregations.py, for mongosh.
// Run:  mongosh "mongodb://localhost:27017/ecommerce" mongodb/aggregations.js
// (or docker exec -i mongo mongosh ecommerce < mongodb/aggregations.js)

// ---------------------------------------------------------------- 1. Product popularity
print("\n=== 1. Top-selling products ===");
printjson(db.transactions.aggregate([
  { $match: { status: { $in: ["completed", "shipped", "delivered", "processing"] } } },
  { $unwind: "$items" },
  { $group: { _id: "$items.product_id", product_name: { $first: "$items.product_name" },
              category_id: { $first: "$items.category_id" },
              units_sold: { $sum: "$items.quantity" }, revenue: { $sum: "$items.subtotal" },
              orders: { $sum: 1 } } },
  { $sort: { units_sold: -1, revenue: -1 } },
  { $limit: 10 },
  { $lookup: { from: "products", localField: "_id", foreignField: "_id", as: "product" } },
  { $unwind: "$product" },
  { $project: { _id: 0, product_id: "$_id", product_name: 1, category_id: 1, units_sold: 1, orders: 1,
                revenue: { $round: ["$revenue", 2] }, current_stock: "$product.current_stock" } }
]).toArray());

// ---------------------------------------------------------------- 2. Revenue by category & month
print("\n=== 2. Revenue & estimated profit by category and month ===");
printjson(db.transactions.aggregate([
  { $unwind: "$items" },
  { $lookup: { from: "categories", localField: "items.category_id", foreignField: "_id", as: "cat" } },
  { $unwind: "$cat" },
  { $addFields: { sub: { $arrayElemAt: [ { $filter: { input: "$cat.subcategories", as: "s",
        cond: { $eq: ["$$s.subcategory_id", "$items.subcategory_id"] } } }, 0 ] } } },
  { $group: { _id: { category: "$cat.name", month: { $dateToString: { format: "%Y-%m", date: "$timestamp" } } },
              revenue: { $sum: "$items.subtotal" },
              est_profit: { $sum: { $multiply: ["$items.subtotal", "$sub.profit_margin"] } },
              units: { $sum: "$items.quantity" } } },
  { $sort: { "_id.month": 1, revenue: -1 } },
  { $limit: 30 }
], { allowDiskUse: true }).toArray());

// Same idea restricted to a time window (uses the {timestamp:1} index)
print("\n=== 2b. Revenue in October 2026 ===");
printjson(db.transactions.aggregate([
  { $match: { timestamp: { $gte: ISODate("2026-10-01"), $lt: ISODate("2026-11-01") } } },
  { $group: { _id: null, revenue: { $sum: "$total" }, orders: { $sum: 1 }, aov: { $avg: "$total" } } }
]).toArray());

// ---------------------------------------------------------------- 3. User segmentation
print("\n=== 3. User segmentation by purchase frequency and spend ===");
printjson(db.transactions.aggregate([
  { $group: { _id: "$user_id", orders: { $sum: 1 }, spent: { $sum: "$total" }, last_order: { $max: "$timestamp" } } },
  { $facet: {
      by_frequency: [ { $bucket: { groupBy: "$orders", boundaries: [1, 3, 6, 10, 1000], default: "other",
                         output: { users: { $sum: 1 }, avg_spent: { $avg: "$spent" }, total_revenue: { $sum: "$spent" } } } } ],
      by_spend: [ { $bucket: { groupBy: "$spent", boundaries: [0, 500, 1500, 3000, 6000, 1e9], default: "other",
                     output: { users: { $sum: 1 }, avg_orders: { $avg: "$orders" } } } } ],
      top_customers: [ { $sort: { spent: -1 } }, { $limit: 5 } ]
  } }
], { allowDiskUse: true }).toArray());

// Because users embed purchase_summary, the "top customers" question is a simple indexed find:
print("\n=== 3b. Top customers straight from the users collection ===");
printjson(db.users.find({}, { "purchase_summary.total_spent": 1, "purchase_summary.order_count": 1, geo_data: 1 })
  .sort({ "purchase_summary.total_spent": -1 }).limit(5).toArray());

// ---------------------------------------------------------------- 4. Journey funnel (sessions sample)
print("\n=== 4. Session funnel by referrer ===");
printjson(db.sessions.aggregate([
  { $project: { referrer: 1, conversion_status: 1, pages: "$page_views.page_type" } },
  { $group: { _id: "$referrer", sessions: { $sum: 1 },
      viewed_product: { $sum: { $cond: [{ $in: ["product_detail", "$pages"] }, 1, 0] } },
      reached_cart: { $sum: { $cond: [{ $in: ["cart", "$pages"] }, 1, 0] } },
      reached_checkout: { $sum: { $cond: [{ $in: ["checkout", "$pages"] }, 1, 0] } },
      converted: { $sum: { $cond: [{ $eq: ["$conversion_status", "converted"] }, 1, 0] } } } },
  { $addFields: { conversion_rate: { $round: [{ $divide: ["$converted", "$sessions"] }, 4] } } },
  { $sort: { conversion_rate: -1 } }
]).toArray());

// Full journey of one user's most recent session - one document read, no joins
print("\n=== 5. Latest session journey for user_000042 ===");
printjson(db.sessions.find({ user_id: "user_000042" }).sort({ start_time: -1 }).limit(1).toArray());
