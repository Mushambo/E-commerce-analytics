"""
03_cohort_analysis.py - Spark batch job #3: cohort analysis of purchasing behaviour.

Cohort      = month in which the user registered (registration_month)
Period      = calendar month of the purchase, expressed as "months since registration"
Metrics     = active buyers, % of cohort active (retention), revenue, revenue per cohort member,
              average order value; plus cumulative revenue per member (a simple LTV curve)

Output: output/cohort_matrix.csv (long format) and output/cohort_retention_pivot.csv
"""
import os
import sys

from pyspark.sql import functions as F
from pyspark.sql.window import Window

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spark_utils as su  # noqa: E402

spark = su.get_spark("03_cohort_analysis")
users = su.read_clean(spark, "users").select("user_id", "registration_date", "registration_month")
txns = su.read_clean(spark, "transactions").select("user_id", "txn_time", "txn_month", "total")

cohort_size = users.groupBy("registration_month").agg(F.count("*").alias("cohort_users"))

activity = (txns.join(users, "user_id")
            .withColumn("months_since_reg",
                        (F.year("txn_time") - F.year("registration_date")) * 12
                        + (F.month("txn_time") - F.month("registration_date")))
            .groupBy("registration_month", "txn_month", "months_since_reg")
            .agg(F.countDistinct("user_id").alias("active_buyers"),
                 F.count("*").alias("orders"),
                 F.round(F.sum("total"), 2).alias("revenue")))

w = Window.partitionBy("registration_month").orderBy("months_since_reg") \
          .rowsBetween(Window.unboundedPreceding, Window.currentRow)
cohort = (activity.join(cohort_size, "registration_month")
          .withColumn("retention_pct", F.round(100 * F.col("active_buyers") / F.col("cohort_users"), 1))
          .withColumn("revenue_per_member", F.round(F.col("revenue") / F.col("cohort_users"), 2))
          .withColumn("aov", F.round(F.col("revenue") / F.col("orders"), 2))
          .withColumn("cum_revenue_per_member", F.round(F.sum("revenue_per_member").over(w), 2))
          .orderBy("registration_month", "months_since_reg"))
cohort.show(40, truncate=False)
su.save_csv(cohort, "cohort_matrix")

pivot = (cohort.groupBy("registration_month", "cohort_users").pivot("txn_month")
         .agg(F.first("retention_pct")).orderBy("registration_month"))
print("Retention % (rows = registration cohort, columns = purchase month)")
pivot.show(truncate=False)
su.save_csv(pivot, "cohort_retention_pivot")

# cohort-level summary: do earlier cohorts spend more per member over the 90-day window?
summary = (cohort.groupBy("registration_month", "cohort_users")
           .agg(F.round(F.sum("revenue") / F.first("cohort_users"), 2).alias("revenue_per_member_90d"),
                F.round(F.avg("aov"), 2).alias("avg_aov"))
           .orderBy("registration_month"))
summary.show()
su.save_csv(summary, "cohort_summary")
spark.stop()
