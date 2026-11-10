import pandas as pd
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Delivery Guide", page_icon="📈")
st.title("📈 Delivery Guide")
st.caption("Sirf stock ya company ka naam likho. Data automatic aayega (Yahoo Finance, NSE/BSE).")

UA = {"User-Agent": "Mozilla/5.0"}


@st.cache_data(ttl=3600)
def search(q):
    r = requests.get(
        "https://query2.finance.yahoo.com/v1/finance/search",
        params={"q": q, "quotesCount": 10, "newsCount": 0},
        headers=UA,
        timeout=10,
    )
    out = []
    for x in r.json().get("quotes", []):
        s = x.get("symbol", "")
        if s.endswith(".NS") or s.endswith(".BO"):
            name = x.get("longname") or x.get("shortname") or s
            out.append((f"{name} ({s})", s))
    out.sort(key=lambda t: not t[1].endswith(".NS"))
    return out


@st.cache_data(ttl=300)
def load(sym):
    df = yf.Ticker(sym).history(period="1y", interval="1d", auto_adjust=False)
    return df[["Open", "High", "Low", "Close"]].dropna()


@st.cache_data(ttl=3600)
def get_info(sym):
    try:
        return yf.Ticker(sym).info or {}
    except Exception:
        return {}


def rsi(c, n=14):
    d = c.diff()
    g = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
    l = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
    return 100.0 if l == 0 else float(100 - 100 / (1 + g / l))


def candle(l, p):
    body = abs(l.Close - l.Open)
    rg = (l.High - l.Low) or 1e-9
    up = l.High - max(l.Open, l.Close)
    lo = min(l.Open, l.Close) - l.Low
    g = l.Close >= l.Open
    if g and p.Close < p.Open and l.Close >= p.Open and l.Open <= p.Close:
        return "Bullish Engulfing", 1, "pichhli red candle cover kar li, buyers ka control"
    if (not g) and p.Close > p.Open and l.Open >= p.Close and l.Close <= p.Open:
        return "Bearish Engulfing", -1, "pichhli green candle cover kar li, sellers ka control"
    if body <= 0.1 * rg:
        return "Doji", 0, "indecision, agli candle ka wait karo"
    if lo >= 2 * body and up <= 0.5 * body:
        return "Hammer", 1, "neeche se buying aayi (lamba lower wick)"
    if up >= 2 * body and lo <= 0.5 * body:
        return "Shooting Star", -1, "upar se selling aayi (lamba upper wick)"
    if body >= 0.85 * rg:
        return ("Bullish Marubozu", 1, "poora din buyers ka") if g else ("Bearish Marubozu", -1, "poora din sellers ka")
    return ("Green candle" if g else "Red candle"), 0, "koi khaas pattern nahi"


def analyse(df):
    c = df.Close
    last, prev = df.iloc[-1], df.iloc[-2]
    e20 = c.ewm(span=20, adjust=False).mean().iloc[-1]
    e50 = c.ewm(span=50, adjust=False).mean().iloc[-1]
    s200 = c.rolling(200).mean().iloc[-1] if len(c) >= 200 else None
    r = rsi(c)
    pc = c.shift()
    tr = pd.concat([df.High - df.Low, (df.High - pc).abs(), (df.Low - pc).abs()], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1])
    pat = candle(last, prev)
    score, why = 0, []

    def add(ok, good, bad):
        nonlocal score
        score += 1 if ok else -1
        why.append(("✅ " + good) if ok else ("❌ " + bad))

    add(last.Close > e20, f"Close EMA20 (₹{e20:,.2f}) ke upar: short-term trend upar.",
        f"Close EMA20 (₹{e20:,.2f}) ke neeche: short-term trend kamzor.")
    add(e20 > e50, f"EMA20 > EMA50 (₹{e50:,.2f}): medium trend positive.",
        f"EMA20 < EMA50 (₹{e50:,.2f}): medium trend negative.")
    if s200 is not None and pd.notna(s200):
        add(last.Close > s200, f"Close 200-DMA (₹{s200:,.2f}) ke upar: long-term trend strong.",
            f"Close 200-DMA (₹{s200:,.2f}) ke neeche: long-term trend weak.")
    if r > 70:
        why.append(f"⚠️ RSI {r:.0f}: overbought, chase mat karo, dip ka wait behtar.")
    elif r >= 45:
        score += 1
        why.append(f"✅ RSI {r:.0f}: healthy momentum.")
    elif r < 40:
        score -= 1
        why.append(f"❌ RSI {r:.0f}: momentum weak.")
    else:
        why.append(f"⚠️ RSI {r:.0f}: neutral zone.")
    score += pat[1]
    icon = "✅" if pat[1] > 0 else "❌" if pat[1] < 0 else "⚠️"
    why.append(f"{icon} Last candle: {pat[0]} ({pat[2]}).")

    if score >= 3 and r <= 70:
        verdict = ("success", "SAHI lag raha hai: delivery ke liye accumulate (2-3 hisson me lo)")
    elif score >= 3:
        verdict = ("warning", "Trend achha hai par RSI overbought: dip ka wait karo")
    elif score >= 0:
        verdict = ("warning", "Abhi clear signal nahi: wait & watch")
    else:
        verdict = ("error", "GALAT time lag raha hai: abhi naya mat lo, trend kamzor hai")
    return dict(score=score, why=why, verdict=verdict, e20=e20, e50=e50, atr=atr, r=r,
                last=last, hi20=df.High.tail(20).max(), lo20=df.Low.tail(20).min())


q = st.text_input("Stock / company ka naam", placeholder="Tata Steel, Reliance, HDFC Bank...")
if not q.strip():
    st.stop()

try:
    opts = search(q.strip())
except Exception:
    st.error("Search nahi ho paya. Thodi der baad dobara try karo.")
    st.stop()
if not opts:
    st.warning("Is naam ka NSE/BSE stock nahi mila. Spelling check karo.")
    st.stop()

label = st.selectbox("Sahi stock chuno", [o[0] for o in opts])
sym = dict(opts)[label]

try:
    df = load(sym)
except Exception:
    st.error("Data nahi mila. Thodi der baad try karo.")
    st.stop()
if len(df) < 60:
    st.warning("Is stock ka itna history data nahi hai analysis ke liye.")
    st.stop()

a = analyse(df)
last = a["last"]
chg = (last.Close / df.Close.iloc[-2] - 1) * 100
info = get_info(sym)
c1, c2, c3 = st.columns(3)
c1.metric("Last close", f"₹{last.Close:,.2f}", f"{chg:+.2f}%")
c2.metric("52-wk Low / High", f"₹{df.Low.min():,.0f} / ₹{df.High.max():,.0f}")
pe = info.get("trailingPE")
c3.metric("P/E", f"{pe:.1f}" if isinstance(pe, (int, float)) else "NA")
st.caption(f"Data date: {df.index[-1].date()} (daily candles, thoda delay ho sakta hai)")

getattr(st, a["verdict"][0])(a["verdict"][1])
for w in a["why"]:
    st.write(w)

sl = last.Close - 2 * a["atr"]
st.subheader("Levels")
st.table(pd.DataFrame({
    "Level": ["Support (20-din low)", "Resistance (20-din high)", "Pullback zone (EMA20)",
              "Stop-loss (close − 2×ATR)", "Target 1 (1:1)", "Target 2 (1:2)"],
    "Price (₹)": [round(x, 2) for x in [a["lo20"], a["hi20"], a["e20"], sl,
                                         last.Close + 2 * a["atr"], last.Close + 4 * a["atr"]]],
}))

st.subheader("Kitne share lu?")
cap = st.number_input("Capital (₹)", 1000, 100000000, 10000, step=1000)
rk = st.number_input("Risk per trade (%)", 0.25, 5.0, 1.0, step=0.25)
if last.Close > sl:
    qty = min(int(cap * rk / 100 // (last.Close - sl)), int(cap // last.Close))
    st.write(f"**{qty} share** (invest ₹{qty * last.Close:,.0f}, stop-loss par max loss ₹{qty * (last.Close - sl):,.0f})")

st.subheader("Chart (6 mahine)")
t = df.tail(125).copy()
t["EMA20"] = df.Close.ewm(span=20, adjust=False).mean().tail(125)
t["EMA50"] = df.Close.ewm(span=50, adjust=False).mean().tail(125)
st.line_chart(t[["Close", "EMA20", "EMA50"]])

st.caption("⚠️ Sirf educational, SEBI-registered advice nahi. Signals rule-based hain aur galat bhi ho sakte hain. Final decision aur risk aapka hai.")
