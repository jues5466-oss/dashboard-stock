#!/usr/bin/env python3
import os, re
from pathlib import Path

V10=Path('/Volumes/AI_Drive/Python/tw-stock-backtest/src/stock_strategy_v1_0.py')
V101=Path('/Volumes/AI_Drive/Python/tw-stock-backtest/src/stock_strategy_v1_01.py')
rule=os.environ.get('SUCCESS_RULE','close_ge_entry')

text=V10.read_text(encoding='utf-8')

# patch success condition inside eval_trades():
# v1.0: hit_success = float(r["adj_high"]) >= entry_price
# v1.01 default: close >= entry
if rule=='close_ge_entry':
    repl='hit_success = float(r["adj_close"]) >= entry_price'
elif rule=='close_ge_entry_and_vol':
    # use vol_ma already computed in build_signals via rolling mean; compute on fly here for simplicity
    repl='hit_success = (float(r["adj_close"]) >= entry_price) and (float(r["volume"]) >= float(df["volume"].rolling(p.vol_ma).mean().loc[dt]))'
else:
    # fallback
    repl='hit_success = float(r["adj_close"]) >= entry_price'

text2=re.sub(r'hit_success\s*=\s*float\(r\["adj_high"\]\)\s*>=\s*entry_price', repl, text)

# update module doc / version marker
if 'Stock Strategy v1.0' in text2:
    text2=text2.replace('Stock Strategy v1.0', 'Stock Strategy v1.01')

V101.write_text(text2, encoding='utf-8')
print('wrote', V101)
