#!/usr/bin/env bash
# run_all.sh - reproduce every result in the report, end to end.
#
# Inside Docker (recommended on Windows):
#   docker compose exec app bash run_all.sh            # live MongoDB + HBase containers
# Directly on Linux/macOS/WSL:
#   ./run_all.sh               # live MongoDB + HBase (docker compose up -d first)
#   ./run_all.sh --offline     # no servers: mongomock + SQLite HBase emulator
#   SCALE=1.0 ./run_all.sh     # full-size dataset (2M sessions / 500k transactions)
set -euo pipefail
cd "$(dirname "$0")"
SCALE="${SCALE:-0.1}"
OFFLINE=0; [[ "${1:-}" == "--offline" ]] && OFFLINE=1
mkdir -p output

step() { echo; echo "=================== $*"; }

step "1/7 Generate dataset (scale=$SCALE)"
python data_generation/dataset_generator.py --out data/raw --scale "$SCALE"

if [[ $OFFLINE == 1 ]]; then
  step "2/7 MongoDB load + aggregations (mongomock)"
  python mongodb/aggregations.py --mock | tee output/mongo_aggregations.txt
  step "3/7 HBase load + queries (SQLite emulator)"
  rm -f data/hbase_emulator.sqlite
  python hbase/load_hbase.py --emulate --recreate
  python hbase/query_hbase.py --emulate | tee output/hbase_query_sample.txt
  HB=hbase-emulator; MG=files
else
  step "0/7 Waiting for MongoDB and HBase"
  python wait_for_services.py --timeout 300
  step "2/7 MongoDB load + aggregations"
  python mongodb/load_mongodb.py --sessions-limit 50000
  python mongodb/aggregations.py | tee output/mongo_aggregations.txt
  step "3/7 HBase schema, load + queries"
  if command -v docker >/dev/null 2>&1; then
    # running on the host: (re)create tables with the HBase shell (full options incl. SPLITS)
    printf "disable 'user_sessions'\ndrop 'user_sessions'\ndisable 'product_metrics'\ndrop 'product_metrics'\n" \
      | docker exec -i hbase hbase shell -n || true
    docker exec -i hbase hbase shell -n < hbase/create_tables.hbase || true
    python hbase/load_hbase.py
  else
    # inside the app container (no docker CLI): drop & create the tables through Thrift
    python hbase/load_hbase.py --recreate
  fi
  python hbase/query_hbase.py | tee output/hbase_query_sample.txt
  HB=hbase; MG=mongo
fi

step "4/7 Spark: clean & normalise"
python spark/01_clean_normalize.py
step "5/7 Spark: recommendations, cohorts, Spark SQL"
python spark/02_recommendations.py
python spark/03_cohort_analysis.py
python spark/04_spark_sql_analytics.py
step "6/7 Integrated analytics (Mongo=$MG, HBase=$HB)"
python integration/clv_analysis.py --mongo "$MG" --hbase "$HB"
python integration/funnel_analysis.py --mongo "$MG" --hbase "$HB"
step "7/7 Charts"
python visualization/make_charts.py
echo; echo "Done. Results in output/, figures in report/figures/."
