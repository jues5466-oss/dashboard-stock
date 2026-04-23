"""
AI 股市戰情室 - V4.xx 策略版 (多指標獨立買點)
"""
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import os
from plotly.subplots import make_subplots

st.set_page_config(page_title="AI 股市 V4", layout="wide")

STOCK_DATA_DIR = '/Volumes/AI_Drive/StockData'
OHLC_FILE = f'{STOCK_DATA_DIR}/monthly_data/ohlc_full.csv'

@st.cache_data(ttl=60)
def fetch_stock(code, period='1y'):
    OHLC_FILE = f'{STOCK_DATA_DIR}/monthly_data/ohlc_full.csv'
    if os.path.exists(OHLC_FILE):
        df = pd.read_csv(OHLC_FILE, low_memory=False)
        df['Date'] = pd.to_datetime(df['date'], format='%Y%m%d')
        df = df[df['code'].astype(str) == code].sort_values('Date').tail(200)
        if len(df) > 50:
            return df.reset_index(drop=True)
    return pd.DataFrame()

def fetch_legal(symbol):
    import glob
    import re
    t86_dir = f"{STOCK_DATA_DIR}/t86"
    files = sorted(glob.glob(f"{t86_dir}/t86_*.csv"))
    if files:
        dfs = []
        for f in files:
            df = pd.read_csv(f)
            # 从文件名提取日期 t86_YYYYMMDD.csv
            match = re.search(r't86_(\d{8})\.csv', f)
            if match:
                date_str = match.group(1)
                df["date"] = date_str
            dfs.append(df)
        df = pd.concat(dfs, ignore_index=True)
        df["code"] = df["code"].astype(str).str.lstrip("0")
        df = df[df["code"].str.lstrip("0") == symbol]
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
        return df.sort_values("date").tail(200)
    return pd.DataFrame()

def calc_indicators(df):
    df = df.copy()
    df['MA20'] = df["close"].rolling(20).mean()
    df['MA60'] = df["close"].rolling(60).mean()
    df['MA200'] = df["close"].rolling(200).mean()
    
    ma = df["close"].rolling(20).mean()
    std = df["close"].rolling(20).std()
    df['BB_up'] = ma + 2 * std
    df['BB_mid'] = ma
    df['BB_low'] = ma - 2 * std
    
    low_9 = df["low"].rolling(9).min()
    high_9 = df["high"].rolling(9).max()
    df['K'] = 100 * (df["close"] - low_9) / (high_9 - low_9)
    df['D'] = df['K'].rolling(3).mean()
    
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + gain / loss))
    
    ema12 = df["close"].ewm(span=12).mean()
    ema26 = df["close"].ewm(span=26).mean()
    df['MACD'] = ema12 - ema26
    df['MACD_sig'] = df['MACD'].ewm(span=9).mean()
    
    high14 = df["high"].rolling(14).max()
    low14 = df["low"].rolling(14).min()
    df['Williams'] = -100 * (high14 - df["close"]) / (high14 - low14)
    
    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma_tp = tp.rolling(14).mean()
    mad = tp.rolling(14).apply(lambda x: abs(x - x.mean()).mean())
    df['CCI'] = (tp - sma_tp) / (0.015 * mad)
    
    df['OBV'] = (np.sign(df["close"].diff()) * df["volume"]).cumsum()
    
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - df["close"].shift()).abs()
    tr3 = (df["low"] - df["close"].shift()).abs()
    df['ATR'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean()
    
    return df

# 各指標獨立的訊號檢查
def check_each_indicator(df, indicators):
    """回傳每個指標的買點訊號"""
    conditions = {
        'KD': lambda row, prev: (prev['K'] < prev['D']) & (row['K'] > row['D']) & (row['K'] < 30),
        'RSI': lambda row, prev: (prev['RSI'] < 30) & (row['RSI'] >= 30),
        'MACD': lambda row, prev: (prev['MACD'] < prev['MACD_sig']) & (row['MACD'] > row['MACD_sig']),
        'Williams': lambda row, prev: (prev['Williams'] < -80) & (row['Williams'] >= -80),
        'MA': lambda row, prev: (prev['MA20'] < prev['MA60']) & (row['MA20'] > row['MA60']),
        'CCI': lambda row, prev: (prev['CCI'] < -80) & (row['CCI'] >= -80),
        'OBV': lambda row, prev: row['OBV'] > df['OBV'].rolling(20).max().iloc[df.index.get_loc(row.name)],  # OBV 突破20日新高
        'MA200': lambda row, prev: (prev['Close'] <= prev['MA200']) & (row['Close'] > row['MA200']),
        'ATR': lambda row, prev: row['ATR'] > df['ATR'].rolling(20).max().iloc[df.index.get_loc(row.name)],  # ATR 突破20日新高
    }
    
    colors = {
        'KD': '#9B59B6',     # 紫
        'RSI': '#3498DB',    # 藍
        'MACD': '#1ABC9C',   # 青色
        'Williams': '#E91E63', # 粉紅
        'MA': '#F39C12',     # 橙
        'CCI': '#795548',    # 棕
        'OBV': '#00BCD4',    # 淺藍
        'MA200': '#E74C3C',  # 紅
        'ATR': '#FF9800'     # 橘
    }
    
    result = {}
    
    for ind in indicators:
        if ind not in conditions:
            continue
        signals = []
        for idx in range(50, len(df)):
            row = df.iloc[idx]
            prev = df.iloc[idx-1]
            try:
                if conditions[ind](row, prev):
                    signals.append(idx)
            except:
                pass
        result[ind] = signals
    
    # 找出 5 天內有多個指標訊號的日期
    all_signals = []
    for ind, sigs in result.items():
        for s in sigs:
            all_signals.append(s)
    all_signals = sorted(set(all_signals))
    
    # 聚類：5天內的訊號歸為一組
    clusters = []
    if all_signals:
        current_cluster = [all_signals[0]]
        for i in range(1, len(all_signals)):
            if all_signals[i] - current_cluster[-1] <= 5:  # 5天內
                current_cluster.append(all_signals[i])
            else:
                if len(current_cluster) >= 2:
                    clusters.append(current_cluster)
                current_cluster = [all_signals[i]]
        if len(current_cluster) >= 2:
            clusters.append(current_cluster)
    
    return result, colors, clusters

def plot_chart(df, indicator_signals, colors, clusters=[], legal_df=None):
    # 根據資料總量調整顯示
    plot_days = min(len(df), 200)
    df_plot = df.tail(plot_days).reset_index(drop=True)
    start_idx = df_plot['BB_low'].first_valid_index()
    if start_idx:
        df_plot = df_plot.iloc[start_idx:].reset_index(drop=True)
    
    offset = len(df) - len(df_plot)
    
    # 配色方案
    colors_chart = {
        'up': '#E74C3C',      # 紅漲
        'down': '#27AE60',    # 綠跌
        'ma20': '#F39C12',    # 橙
        'ma60': '#3498DB',    # 藍
        'bb': '#95A5A6',      # 灰
        'k': '#8E44AD',       # 紫
        'd': '#E67E22',       # 橘
        'rsi': '#16A085',     # 綠
        'bg': '#1a1a2e',
        'grid': '#2d2d44'
    }
    
    # 法人买卖超日期对齐
    legal_dates = []
    if False and len(legal_df) > 0:
        legal_df = legal_df.sort_values("date")
        legal_dates = legal_df["date"].tolist()
    
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.7, 0.3],
        subplot_titles=['股價', '法人買賣超']
    )
    
    # K線 - 使用原生 Candlestick (更高效)
    fig.add_trace(go.Candlestick(
        x=df_plot['Date'],
        open=df_plot["open"], high=df_plot["high"],
        low=df_plot["low"], close=df_plot["close"],
        increasing_line_color='#E74C3C', decreasing_line_color='#27AE60',
        increasing_fillcolor='#E74C3C', decreasing_fillcolor='#27AE60'
    ), row=1, col=1)
    
    # MA20, MA60 - 粗線
    fig.add_trace(go.Scatter(
        x=df_plot['Date'], y=df_plot['MA20'],
        mode='lines', name='MA20',
        line=dict(color=colors_chart['ma20'], width=2.5)
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(
        x=df_plot['Date'], y=df_plot['MA60'],
        mode='lines', name='MA60',
        line=dict(color=colors_chart['ma60'], width=2)
    ), row=1, col=1)
    
    # BB 上下軌
    fig.add_trace(go.Scatter(
        x=df_plot['Date'], y=df_plot['BB_up'],
        mode='lines', line=dict(color=colors_chart['bb'], dash='dot', width=1),
        showlegend=False
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df_plot['Date'], y=df_plot['BB_low'],
        mode='lines', name='布林通道',
        line=dict(color=colors_chart['bb'], dash='dot', width=1)
    ), row=1, col=1)
    
    # 聚合買點（不同指標在5天內同時觸發）- 星星標記
    if clusters and len(indicators) >= 2:
        for cluster in clusters:
            # 檢查這個cluster是否有至少2個不同的指標
            unique_indicators = set()
            for idx in cluster:
                for ind, sigs in indicator_signals.items():
                    if idx in sigs:
                        unique_indicators.add(ind)
            
            if len(unique_indicators) >= 2:  # 不同指標
                last_idx = cluster[-1] - offset
                if last_idx >= 0 and last_idx < len(df_plot):
                    d = df_plot.iloc[last_idx]
                    fig.add_trace(go.Scatter(
                        x=[d['Date']], y=[d["close"]],
                        mode='markers', name='🔥',
                        marker=dict(symbol='star', size=15, color='yellow', line=dict(width=1, color='orange'))
                    ), row=1, col=1)
    
    # 各指標買點
    for ind, signals in indicator_signals.items():
        buy_idx = [i - offset for i in signals if i >= offset]
        if buy_idx:
            buy_df = df_plot.iloc[buy_idx]
            color = colors.get(ind, 'yellow')
            fig.add_trace(go.Scatter(
                x=buy_df['Date'], y=buy_df["close"],
                mode='markers', marker=dict(symbol='triangle-up', size=8, color=color, line=dict(width=1, color='white')),
                textfont=dict(size=16, color=color),
                name=f'{ind}訊號'
            ), row=1, col=1)
    

    

    
    # 法人買賣超柱狀圖 (第4個subplot)
    if legal_df is not None and len(legal_df) > 0:
        legal_df_sorted = legal_df.sort_values("date").tail(plot_days).copy()
        legal_df_sorted['date'] = pd.to_datetime(legal_df_sorted['date'])
        
        colors_legal = ['#E74C3C' if x >= 0 else '#27AE60' for x in legal_df_sorted['total_net']]
        fig.add_trace(go.Bar(
            x=legal_df_sorted['date'],
            y=legal_df_sorted['total_net'],
            marker_color=colors_legal,
            name='法人買賣超',
            showlegend=True
        ), row=2, col=1)
        
        fig.add_hline(y=0, line=dict(color='white', width=1), row=2, col=1)
    
    # 樣式
    fig.update_layout(
        paper_bgcolor='#0f0f23',
        plot_bgcolor='#0f0f23',
        font=dict(color='white', size=12),
        xaxis=dict(showgrid=True, gridcolor='#2d2d44', zeroline=False),
        yaxis=dict(showgrid=True, gridcolor='#2d2d44', zeroline=False),
        xaxis2=dict(showgrid=True, gridcolor='#2d2d44', zeroline=False),
        yaxis2=dict(showgrid=True, gridcolor='#2d2d44', zeroline=False),
        xaxis3=dict(showgrid=True, gridcolor='#2d2d44', zeroline=False),
        yaxis3=dict(showgrid=True, gridcolor='#2d2d44', zeroline=False),
        xaxis_rangeslider_visible=False,
        height=750,
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='center', x=0.5, bgcolor='rgba(0,0,0,0)'),
        margin=dict(l=50, r=50, t=30, b=50)
    )
    
    return fig

# 主程式
st.title("📈 AI 股市 V4.xx 策略")

if "stock_id" not in st.session_state:
    st.session_state["stock_id"] = "2317"
stock_id = st.sidebar.text_input("股票代號", value=st.session_state["stock_id"])

# 顯示股票名稱
if stock_id:
    try:
        active = pd.read_csv("/Volumes/AI_Drive/StockData/active_stocks.csv", dtype={"code": str})
        active["code"] = active["code"].astype(str)
        name_dict = dict(zip(active["code"], active["name"]))
        stock_name = name_dict.get(str(stock_id), "")
        if stock_name:
            st.header(f"📈 {stock_name} ({stock_id})")
    except:
        pass
period_map = {'1個月': '1mo', '3個月': '3mo', '6個月': '6mo', '1年': '1y', '2年': '2y', '3年': '3y', '5年': '5y'}
period_choice = st.sidebar.selectbox('時間範圍', list(period_map.keys()), index=3)
period = period_map[period_choice]
st.sidebar.markdown("---")
st.sidebar.subheader("選擇指標")

indicators = []


if st.sidebar.checkbox("KD (紫色)", value=True):
    indicators.append("KD")
if st.sidebar.checkbox("RSI (藍色)", value=True):
    indicators.append("RSI")
if st.sidebar.checkbox("MACD (青色)", value=True):
    indicators.append("MACD")
if st.sidebar.checkbox("Williams (洋紅)", value=True):
    indicators.append("Williams")
if st.sidebar.checkbox("MA (橙色)"):
    indicators.append("MA")
if st.sidebar.checkbox("CCI (棕色)"):
    indicators.append("CCI")
if st.sidebar.checkbox("OBV (粉色)"):
    indicators.append("OBV")
if st.sidebar.checkbox("MA200 (紅色)"):
    indicators.append("MA200")
if st.sidebar.checkbox("ATR (金色)"):
    indicators.append("ATR")

if stock_id and indicators:
    if not indicators:
        st.error("請至少選擇一個指標")
    else:
        with st.spinner('抓取資料中...'):
            df = fetch_stock(stock_id, period)
        
        if df is not None and len(df) > 50:
            df = calc_indicators(df)
            indicator_signals, colors, clusters = check_each_indicator(df, indicators)
            
            # 統計總買點
            total_buys = sum(len(v) for v in indicator_signals.values())
            
            curr = df["close"].iloc[-1]
            prev = df["close"].iloc[-2]
            
            c1, c2, c3 = st.columns(3)
            c1.metric("現在價格", f"{curr:.1f}", f"{curr-prev:.1f}")
            c2.metric("總買點", f"{total_buys} 次")
            st.metric("聚合訊號", f"{len(clusters)} 組")
            c3.metric("指標", f"{len(indicators)} 個")
            
            legal_df = fetch_legal(stock_id)
            st.plotly_chart(plot_chart(df, indicator_signals, colors, clusters, legal_df), use_container_width=True)
            
            # 各指標買點統計
            st.subheader("各指標買點")
            
            # 指標說明
            indicator_info = {
                "KD": "K值穿越D值 且 K<30 黃金交叉",
                "RSI": "RSI從<30回升到>=30 趨勢轉強",
                "MACD": "MACD穿越signal線 且 MACD>0 多頭訊號",
                "Williams": "Williams從<-80回升到>=-80 見底回升",
                "MA": "MA20穿越MA60 多頭排列",
                "CCI": "CCI從<-80回升到>=-80 趨勢轉強",
                "OBV": "OBV突破20日新高 量能增強",
                "MA200": "股價站上MA200 長期趨勢轉多",
                "ATR": "ATR突破20日新高 波動加劇"
            }
            
            for ind, signals in indicator_signals.items():
                color = colors.get(ind, 'red')
                info = indicator_info.get(ind, "")
                st.write(f"**{ind}** ({color}): {len(signals)} 次 - {info}")
                if signals:
                    recent = [df.iloc[s]['Date'].strftime('%m/%d') for s in signals[-5:]]
                    st.write(f"   最近: {', '.join(recent)}")
        else:
            st.error("找不到股票資料")


# ==================== 每日買點推薦 (Sidebar) ====================
import glob

SIGNALS_DIR = "/Volumes/AI_Drive/StockData/signals"
ACTIVE_FILE = "/Volumes/AI_Drive/StockData/active_stocks.csv"

@st.cache_data(ttl=3600)
def load_signals_by_date(date_str, prefix="signal_t86_"):
    if not date_str:
        return pd.DataFrame()
    file_path = f"{SIGNALS_DIR}/{prefix}{date_str}.csv"
    try:
        df = pd.read_csv(file_path)
        active = pd.read_csv(ACTIVE_FILE)
        name_dict = active.set_index("code")["name"].to_dict()
        # Keep existing name if present, otherwise map from active_stocks
        if "name" not in df.columns:
            df["name"] = df["code"].map(name_dict)
        else:
            # Fill missing names from active_stocks
            df["name"] = df.apply(lambda x: x["name"] if pd.notna(x.get("name")) else name_dict.get(str(x["code"]), ""), axis=1)
        return df
    except:
        return pd.DataFrame()

# 取得可用日期
signal_files = sorted(glob.glob(f"{SIGNALS_DIR}/signal_t86_*.csv"))
# 取最近10個檔案
# 選擇訊號類型
signal_type = st.sidebar.radio("訊號類型", ["signal_t86", "summary"], 
                            horizontal=True, key="sig_type")
prefix = "signal_t86_" if signal_type == "signal_t86" else "summary_"
available_files = sorted(glob.glob(f"{SIGNALS_DIR}/{prefix}*.csv"))[-10:]
date_options = [""] + [os.path.basename(f).replace(prefix, "").replace(".csv", "") for f in available_files]

# Sidebar 控制
st.sidebar.markdown("---")
st.sidebar.subheader("📈 歷史買點")
st.sidebar.caption("""
**📊 signal_t86** (舊):
• RSI < 30 → 信號
• Williams < -50 → 信號  
• MACD > signal → 信號
• MA200 上 → 信號

**🆕 summary** (新):
• RSI 回升 >=30 → 信號
• Williams 回升 >=-80 → 信號
• MACD 金叉 > 0 → 信號
""")
selected_date = st.sidebar.selectbox("選擇日期", date_options, index=len(date_options)-1, format_func=lambda x: f"{x[:4]}-{x[4:6]}-{x[6:]}" if len(x)==8 else "最新")

if selected_date:
    sig_df = load_signals_by_date(selected_date, prefix)
    if len(sig_df) > 0:
        strong = sig_df[sig_df["recommendation"] == "strong_buy"]
        buy = sig_df[sig_df["recommendation"] == "buy"]
        
        st.sidebar.markdown("**🔥 強強買** (點擊載入)")
        if len(strong) > 0:
            for _, row in strong.head(5).iterrows():
                code = row['code']
                name = row.get('name', '')
                signals = row.get('signals', row.get('signal', ''))
                # 用 st.button 當作可點擊的連結
                if st.sidebar.button(f"{code} {name} ({signals})", key=f"btn_{code}"):
                    # 設定股票代碼並觸發重新整理
                    st.session_state['stock_id'] = code
                    st.rerun()
        else:
            st.sidebar.info("無")
        
        st.sidebar.markdown("**👍 推薦** (點擊載入)")
        if len(buy) > 0:
            for _, row in buy.head(5).iterrows():
                code = row['code']
                name = row.get('name', '')
                signals = row.get('signals', row.get('signal', ''))
                if st.sidebar.button(f"{code} {name} ({signals})", key=f"btn_{code}_buy"):
                    st.session_state['stock_id'] = code
                    st.rerun()
        else:
            st.sidebar.info("無")
    else:
        st.sidebar.warning("無資料")
else:
    st.sidebar.info("選擇日期")


# ==================== 我的庫存 ====================
MY_STOCKS_FILE = "/Volumes/AI_Drive/StockData/my_stocks.csv"

st.sidebar.markdown("---")
st.sidebar.subheader("📦 我的庫存")

try:
    my_df = pd.read_csv(MY_STOCKS_FILE, dtype={"code": str})
    my_df["code"] = my_df["code"].astype(str)
    my_stocks = dict(zip(my_df["code"], my_df["name"]))
    
    my_options = [""] + list(my_stocks.keys())
    selected_my = st.sidebar.selectbox("選擇庫存", my_options, 
                                  format_func=lambda x: f"{x} {my_stocks.get(x, '')}" if x else "我的庫存")
    
    if selected_my and selected_my != stock_id:
        st.session_state["stock_id"] = selected_my
        st.rerun()
except Exception as e:
    st.sidebar.warning(f"無法讀取庫存: {e}")
