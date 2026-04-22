#!/bin/bash
set -euo pipefail

BASE=~/tw-stock-backtest
DESIGN=/Volumes/AI_Drive/AI_Workspace/openclaw_design
PROP_DIR="$DESIGN/stock_strategy/v1.01/proposals"
mkdir -p "$PROP_DIR"

DATE=$(date +%F)
PROP="$PROP_DIR/$DATE.md"

# 1) Ask deepseek for rule
RES=$(python3 /Users/jues/.openclaw/workspace/scripts/deepseek_v1_01_success_rule.py)
OK=$(python3 -c 'import json,sys; j=json.loads(sys.argv[1]); print(j.get("ok"))' "$RES")
RULE=$(python3 -c 'import json,sys; j=json.loads(sys.argv[1]); print(j.get("rule","close_ge_entry"))' "$RES")
RAW=$(python3 -c 'import json,sys; j=json.loads(sys.argv[1]); print(j.get("raw",""))' "$RES")

# 2) Generate v1.01 program based on方案1 RULE
SUCCESS_RULE="$RULE" python3 /Users/jues/.openclaw/workspace/scripts/make_stock_strategy_v1_01.py

# 3) Run a test (target 0056.TW) and let program write runs.jsonl+summary.md
/usr/bin/time -p "$BASE/.venv/bin/python" "$BASE/src/stock_strategy_v1_01.py" --symbol 0056.TW --change "v1.01 RULE=$RULE" > /tmp/stock_v101.out 2> /tmp/stock_v101.time

# 4) Append proposal doc
{
  echo "# v1.01 Proposal — $DATE"
  echo
  echo "## deepseek raw reply"
  echo '```'
  echo "$RAW"
  echo '```'
  echo
  echo "## chosen (方案1)"
  echo "- RULE: $RULE"
  echo "- generated: $BASE/src/stock_strategy_v1_01.py"
  echo
  echo "## run time"
  cat /tmp/stock_v101.time
  echo
  echo "## daily outputs"
  echo "- $BASE/results/stock_tests/$DATE/runs.jsonl"
  echo "- $BASE/results/stock_tests/$DATE/summary.md"
} >> "$PROP"

echo "OK nightly v1.01 done: RULE=$RULE"
