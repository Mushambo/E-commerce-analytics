// mongodb/evidence.js - output for the report screenshot (MongoDB)
// Run (PowerShell):  Get-Content mongodb\evidence.js | docker exec -i mongo mongosh ecommerce --quiet
print("=== Document counts ===");
print("transactions: " + db.transactions.countDocuments());
print("users:        " + db.users.countDocuments());
print("products:     " + db.products.countDocuments());
print("\n=== Pipeline 1: top-selling products ===");
printjson(db.transactions.aggregate([
  { $match: { status: { $in: ["completed", "shipped", "delivered", "processing"] } } },
  { $unwind: "$items" },
  { $group: { _id: "$items.product_id", product_name: { $first: "$items.product_name" },
              units_sold: { $sum: "$items.quantity" }, revenue: { $sum: "$items.subtotal" }, orders: { $sum: 1 } } },
  { $sort: { units_sold: -1, revenue: -1 } },
  { $limit: 10 },
  { $lookup: { from: "products", localField: "_id", foreignField: "_id", as: "p" } },
  { $unwind: "$p" },
  { $project: { _id: 0, product_id: "$_id", product_name: 1, units_sold: 1, orders: 1,
                revenue: { $round: ["$revenue", 2] }, current_stock: "$p.current_stock" } }
]).toArray());
