# Release Notes

## v2.3.0 (2026-04-27)
### New Features
- **K-line Pattern Toggle**: Added `🕯️ K線型態標記` checkbox in sidebar (default OFF)
  - Bullish patterns: 🔨 Hammer, 📈 Bullish Engulfing, 🌙 Morning Star
  - Bearish patterns: ⭐ Inverted Hammer, 📉 Bearish Engulfing, 🌙 Evening Star
  - Doji detection

### Bug Fixes
- Fixed: All indicators OFF → K-line chart disappeared
- K-line and candlestick patterns now independent from technical indicator checkboxes

### Performance
- `@st.cache_data` added to `fetch_stock` and `fetch_legal` (5 min TTL)
- Smart date filtering — only reads files within selected date range
- Date index cached at startup (1 hour TTL)

### Technical Indicators
- Added DMI indicator (purple, #9C27B0) — shows +DI, -DI, ADX

---

## v2.2 (Previous)
- See GitHub commit history for earlier changes
