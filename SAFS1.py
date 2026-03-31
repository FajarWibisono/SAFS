import streamlit as st
import yfinance as yf
import pandas as pd
import datetime as dt
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Constants ---
RATIO_KEYS = [
    "ROE", "DER", "P/E", "P/B", "P/S",
    "Dividend Yield", "Operating Margin", "GPM", "ROA",
    "Earnings Yield", "Current Ratio", "PEG Ratio",
]

# --- Page Config ---
st.set_page_config(page_title="🔍 SAFS", layout="wide")
st.title("📊 Screening Awal Fundamental Saham")
st.markdown(
    "Aplikasi ini membantu Anda untuk menganalisa dan membandingkan Saham yang menarik perhatian "
    "Anda untuk investasi. **APLIKASI TIDAK BERLAKU UNTUK EMITEN perBANKan.** Aplikasi ini secara "
    "otomatis akan membandingkan berbagai RATIO FUNDAMENTAL dari **maksimal 7 saham** yang Anda "
    "masukkan, dan Memilih 3 yang terbaik diantara lainnya. **Happy Cuan!!!**"
)

# --- Session State Init ---
for _key, _default in [
    ('should_display_results', False),
    ('manual_values', {}),
    ('ratio_data', {}),
    ('evaluations', {}),
    ('scores', {}),
    ('stock_prices', {}),
    ('target_prices', {}),
    ('estimated_eps', {}),
]:
    if _key not in st.session_state:
        st.session_state[_key] = _default

# --- Stock Input ---
st.subheader("Masukkan Kode Saham")
col1, col2 = st.columns(2)
with col1:
    stock1 = st.text_input("Saham 1", "AUTO.JK")
    stock3 = st.text_input("Saham 3", "TLKM.JK")
    stock5 = st.text_input("Saham 5", "ASII.JK")
    stock7 = st.text_input("Saham 7", "")
with col2:
    stock2 = st.text_input("Saham 2", "IPCC.JK")
    stock4 = st.text_input("Saham 4", "UNVR.JK")
    stock6 = st.text_input("Saham 6", "PALM.JK")


def normalize_ticker(ticker: str) -> str:
    """Normalize ticker to IDX format — auto-append .JK if missing."""
    t = ticker.strip().upper()
    if t and not t.endswith(".JK"):
        t += ".JK"
    return t


# Normalize and collect non-empty tickers
stocks = [normalize_ticker(s) for s in [stock1, stock2, stock3, stock4, stock5, stock6, stock7] if s.strip()]


# ─────────────────────────────────────────────
# Helper: safe field lookup with multiple name variants
# ─────────────────────────────────────────────

def _get_field(df: pd.DataFrame, *field_names):
    """Return the first matching row's latest value from a financial DataFrame.
    Returns float or None. Tries all provided field_names before giving up."""
    if df is None or df.empty:
        return None
    for name in field_names:
        if name in df.index:
            val = df.loc[name].iloc[0]
            return float(val) if pd.notna(val) else None
    return None


# ─────────────────────────────────────────────
# Fetch: cached per ticker (1 hour TTL)
# ─────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ticker_data(stock: str) -> dict:
    """Fetch raw yfinance data for one IDX stock. Results cached for 1 hour."""
    for attempt in range(3):
        try:
            ticker = yf.Ticker(stock)
            info = ticker.info

            # Resolve current price
            current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            if current_price is None:
                hist = ticker.history(period="5d")
                if hist.empty:
                    raise ValueError(f"Tidak ada data harga untuk {stock}")
                current_price = float(hist["Close"].iloc[-1])

            return {
                "info": info,
                "financials": ticker.financials,      # = ticker.income_stmt
                "balance_sheet": ticker.balance_sheet,
                "current_price": float(current_price),
            }
        except Exception as exc:
            if attempt < 2:
                time.sleep(2 ** attempt)  # exponential backoff: 1s, 2s
            else:
                raise RuntimeError(
                    f"Gagal mengambil data {stock} setelah 3 percobaan: {exc}"
                ) from exc


# ─────────────────────────────────────────────
# Compute: all fundamental ratios from raw data
# ─────────────────────────────────────────────

def compute_ratios(data: dict) -> dict:
    """Derive all fundamental ratios from fetched ticker data."""
    info = data["info"]
    fin  = data["financials"]
    bs   = data["balance_sheet"]

    # Shared equity (used by ROE and DER)
    total_equity = _get_field(
        bs,
        "Stockholders Equity",
        "Total Stockholder Equity",
        "Common Stock Equity",
        "Total Equity Gross Minority Interest",
    )

    # ── ROE ──────────────────────────────────
    net_income_roe = _get_field(fin, "Net Income", "Net Income Common Stockholders")
    if net_income_roe is not None and total_equity is not None and total_equity != 0:
        roe = (net_income_roe / total_equity) * 100
    else:
        raw = info.get("returnOnEquity")
        roe = (float(raw) * 100) if raw is not None else None

    # ── DER ──────────────────────────────────
    total_debt = _get_field(bs, "Total Debt", "Long Term Debt And Capital Lease Obligation")
    if total_debt is None:
        ltd = _get_field(bs, "Long Term Debt")
        std = _get_field(bs, "Short Long Term Debt", "Current Debt", "Current Portion Of Long Term Debt")
        if ltd is not None:
            total_debt = ltd + (std or 0.0)
    if total_debt is not None and total_equity is not None and total_equity != 0:
        der = total_debt / total_equity
    else:
        raw = info.get("debtToEquity")
        # yfinance returns debtToEquity as percentage (e.g. 150 = 1.5x ratio)
        der = (float(raw) / 100) if raw is not None else None

    # ── P/E ──────────────────────────────────
    pe_raw = info.get("trailingPE") or info.get("forwardPE")
    pe = float(pe_raw) if pe_raw is not None else None

    # ── P/B ──────────────────────────────────
    pb_raw = info.get("priceToBook")
    pb = float(pb_raw) if pb_raw is not None else None

    # ── P/S ──────────────────────────────────
    ps_raw = info.get("priceToSalesTrailing12Months")
    if ps_raw is None:
        mktcap  = info.get("marketCap")
        revenue = _get_field(fin, "Total Revenue")
        if mktcap is not None and revenue is not None and revenue != 0:
            ps_raw = mktcap / revenue
    ps = float(ps_raw) if ps_raw is not None else None

    # ── Dividend Yield — stored as % (e.g. 3.5 means 3.5%) ──
    div_raw = info.get("dividendYield")
    # yfinance returns dividendYield as a decimal (0.035 = 3.5%)
    div = (float(div_raw) * 100) if div_raw is not None else None

    # ── Operating Margin ──────────────────────
    om_raw = info.get("operatingMargins")
    if om_raw is not None:
        op_margin = float(om_raw) * 100
    else:
        op_income = _get_field(fin, "Operating Income", "EBIT")
        revenue   = _get_field(fin, "Total Revenue")
        op_margin = ((op_income / revenue) * 100
                     if op_income is not None and revenue is not None and revenue != 0
                     else None)

    # ── GPM ──────────────────────────────────
    gpm_raw = info.get("grossMargins")
    if gpm_raw is not None:
        gpm = float(gpm_raw) * 100
    else:
        gross_profit = _get_field(fin, "Gross Profit")
        revenue      = _get_field(fin, "Total Revenue")
        gpm = ((gross_profit / revenue) * 100
               if gross_profit is not None and revenue is not None and revenue != 0
               else None)

    # ── ROA — independent net_income fetch (not shared with ROE) ──
    net_income_roa = _get_field(fin, "Net Income", "Net Income Common Stockholders")
    total_assets   = _get_field(bs, "Total Assets")
    if net_income_roa is not None and total_assets is not None and total_assets != 0:
        roa = (net_income_roa / total_assets) * 100
    else:
        raw = info.get("returnOnAssets")
        roa = (float(raw) * 100) if raw is not None else None

    # ── Earnings Yield — derived from P/E ────
    ey = ((1 / pe) * 100) if (pe is not None and pe > 0) else None

    # ── Current Ratio ─────────────────────────
    cur_assets = _get_field(bs, "Current Assets")
    cur_liab   = _get_field(bs, "Current Liabilities")
    if cur_assets is not None and cur_liab is not None and cur_liab != 0:
        current_ratio = cur_assets / cur_liab
    else:
        raw = info.get("currentRatio")
        current_ratio = float(raw) if raw is not None else None

    # ── PEG Ratio ─────────────────────────────
    peg_raw = info.get("pegRatio")
    if peg_raw is None and pe is not None:
        growth = info.get("earningsGrowth")
        if growth is not None and growth != 0:
            peg_raw = pe / (growth * 100)
    peg = float(peg_raw) if peg_raw is not None else None

    return {
        "ROE": roe,
        "DER": der,
        "P/E": pe,
        "P/B": pb,
        "P/S": ps,
        "Dividend Yield": div,
        "Operating Margin": op_margin,
        "GPM": gpm,
        "ROA": roa,
        "Earnings Yield": ey,
        "Current Ratio": current_ratio,
        "PEG Ratio": peg,
    }


# ─────────────────────────────────────────────
# Orchestrate: parallel fetch + compute for all stocks
# ─────────────────────────────────────────────

def get_ratio_data(stocks: list) -> dict:
    results = {}
    prices = {}
    target_prices = {}
    estimated_eps_values = {}

    def process_stock(stock: str):
        try:
            data   = fetch_ticker_data(stock)
            ratios = compute_ratios(data)
            info   = data["info"]
            return (
                stock,
                ratios,
                data["current_price"],
                info.get("targetMeanPrice"),
                info.get("forwardEps") or info.get("trailingEps"),
                None,
            )
        except Exception as exc:
            return stock, None, None, None, None, str(exc)

    with ThreadPoolExecutor(max_workers=min(4, len(stocks))) as executor:
        futures = {executor.submit(process_stock, s): s for s in stocks}
        for future in as_completed(futures):
            stock, ratios, price, target, eps, error = future.result()
            if error:
                st.warning(f"⚠️ Gagal mengambil data **{stock}**: {error}")
                results[stock] = {k: None for k in RATIO_KEYS}
                prices[stock] = None
                target_prices[stock] = None
                estimated_eps_values[stock] = None
            else:
                results[stock] = ratios
                prices[stock] = price
                target_prices[stock] = target
                estimated_eps_values[stock] = eps

    st.session_state.stock_prices = prices
    st.session_state.target_prices = target_prices
    st.session_state.estimated_eps = estimated_eps_values
    return results


# ─────────────────────────────────────────────
# Evaluate ratios and produce scores
# ─────────────────────────────────────────────

def evaluate_ratios(ratio_data: dict) -> tuple:
    evaluations = {}
    scores = {}

    for stock, ratios in ratio_data.items():
        evaluations[stock] = {}
        scores[stock] = 0
        good_count = 0

        # Apply manual overrides
        if stock in st.session_state.manual_values:
            for ratio, value in st.session_state.manual_values[stock].items():
                if value != "":
                    try:
                        ratios[ratio] = float(value)
                    except ValueError:
                        pass

        def grade(key, good_fn, mid_fn):
            """Helper: grade one ratio and update score."""
            val = ratios.get(key)
            if val is None:
                evaluations[stock][key] = "N/A"
                return
            if good_fn(val):
                evaluations[stock][key] = "Baik"
                scores[stock] += 2
                nonlocal good_count
                good_count += 1
            elif mid_fn(val):
                evaluations[stock][key] = "Biasa"
                scores[stock] += 1
            else:
                evaluations[stock][key] = "Buruk"

        grade("ROE",             lambda v: v > 15,          lambda v: 5 <= v <= 15)
        grade("DER",             lambda v: v < 0.8,         lambda v: 0.8 <= v <= 1)
        grade("P/E",             lambda v: v < 15,          lambda v: 15 <= v <= 25)
        grade("P/B",             lambda v: v < 1.5,         lambda v: 1.5 <= v <= 3)
        grade("P/S",             lambda v: 0 < v < 1,       lambda v: 1 <= v <= 2)
        # Dividend Yield already stored as % (e.g. 3.5 = 3.5%)
        grade("Dividend Yield",  lambda v: v > 3.75,        lambda v: 1 <= v <= 3.75)
        grade("Operating Margin",lambda v: v > 20,          lambda v: 10 <= v <= 20)
        grade("GPM",             lambda v: v > 40,          lambda v: 20 <= v <= 40)
        grade("ROA",             lambda v: v > 5,           lambda v: 2 <= v <= 5)
        grade("Earnings Yield",  lambda v: v > 10,          lambda v: 5 <= v <= 10)
        grade("Current Ratio",   lambda v: v > 2,           lambda v: 1 <= v <= 2)
        grade("PEG Ratio",       lambda v: 0 < v < 1,       lambda v: 0.9 <= v <= 1.1)

    return evaluations, scores


# ─────────────────────────────────────────────
# Display results
# ─────────────────────────────────────────────

def display_results(stocks: list, ratio_data: dict, evaluations: dict, scores: dict):
    # ── Build DataFrame ──────────────────────
    data = []
    for stock in stocks:
        if stock not in ratio_data:
            continue
        row = [stock]

        price = st.session_state.stock_prices.get(stock)
        row.append(f"{price:.2f}" if price is not None else "N/A")

        for ratio in RATIO_KEYS:
            value    = ratio_data[stock].get(ratio)
            penilaian = evaluations[stock].get(ratio, "N/A") if stock in evaluations else "N/A"

            if isinstance(value, float):
                if ratio in ("DER", "P/E", "P/B", "P/S", "Current Ratio", "PEG Ratio"):
                    fmt = f"{value:.2f}"
                else:
                    # ROE, Operating Margin, GPM, ROA, Earnings Yield, Dividend Yield — all in %
                    fmt = f"{value:.2f}%"
            else:
                fmt = "N/A"

            row.extend([fmt, penilaian])

        eps = st.session_state.estimated_eps.get(stock)
        row.append(f"{eps:.2f}" if eps is not None else "N/A")

        target = st.session_state.target_prices.get(stock)
        row.append(f"{target:.2f}" if target is not None else "N/A")

        data.append(row)

    # ── Build MultiIndex columns ─────────────
    h1 = ["SAHAM", "PRICE"]
    h2 = ["", ""]
    for ratio in RATIO_KEYS:
        h1.extend([ratio, ratio])
        h2.extend(["Value", "Penilaian"])
    h1 += ["est.EPS", "TARGET PRICE"]
    h2 += ["", ""]

    df = pd.DataFrame(data, columns=pd.MultiIndex.from_tuples(list(zip(h1, h2))))

    st.subheader("Analisis Fundamental")
    st.dataframe(df, use_container_width=True)

    # ── Manual Input Section ─────────────────
    st.subheader("Input Manual untuk Nilai N/A")

    for stock in stocks:
        if stock not in st.session_state.manual_values:
            st.session_state.manual_values[stock] = {r: "" for r in RATIO_KEYS}

    tabs = st.tabs(stocks)
    for i, stock in enumerate(stocks):
        with tabs[i]:
            st.write(f"Input nilai manual untuk {stock}:")
            cols = st.columns(3)
            has_na = False

            for j, ratio in enumerate(RATIO_KEYS):
                with cols[j % 3]:
                    value = ratio_data[stock].get(ratio)
                    if value is not None and isinstance(value, float):
                        if ratio in ("DER", "P/E", "P/B", "P/S", "Current Ratio", "PEG Ratio"):
                            display_val = f"Current: {value:.2f}"
                        else:
                            display_val = f"Current: {value:.2f}%"
                    else:
                        display_val = "Current: N/A"
                        has_na = True

                    st.text(display_val)
                    current_input = st.session_state.manual_values[stock].get(ratio, "")
                    new_val = st.text_input(
                        f"Input {ratio}",
                        value=current_input,
                        key=f"manual_input_{stock}_{ratio}_{i}",
                    )
                    if new_val != current_input:
                        st.session_state.manual_values[stock][ratio] = new_val

            if not has_na:
                st.info("Semua nilai rasio sudah tersedia. Input manual akan menggantikan nilai yang ada.")

    # ── Re-analyze Button ────────────────────
    if st.button("Analisa Kembali", key="reanalyze_button_inside"):
        if not stocks:
            st.error("Masukkan minimal satu kode saham untuk dianalisis.")
        else:
            with st.spinner("Menganalisis ulang data fundamental..."):
                if st.session_state.ratio_data:
                    evaluations, scores = evaluate_ratios(st.session_state.ratio_data)
                    st.session_state.evaluations = evaluations
                    st.session_state.scores = scores
                    st.session_state.should_display_results = True
                    st.rerun()

    # ── Recommendations ──────────────────────
    st.subheader("REKOMENDASI")

    good_counts = {
        stock: sum(1 for v in evals.values() if v == "Baik")
        for stock, evals in evaluations.items()
    }
    qualified = {s: scores[s] for s in stocks if good_counts.get(s, 0) >= 5}

    if qualified:
        top = sorted(qualified.items(), key=lambda x: x[1], reverse=True)[:3]
        for rank, (stock, score) in enumerate(top, 1):
            st.write(f"{rank}. **{stock}** — Total Score: {score}, Kriteria Baik: {good_counts[stock]}")
    else:
        st.write("Tidak ada Rekomendasi (Minimal 5 rasio harus dengan kriteria Baik)")

    st.write(f"Data diambil pada tanggal {dt.datetime.now().strftime('%d %B %Y')}")


# ─────────────────────────────────────────────
# Main App Flow
# ─────────────────────────────────────────────

if st.button("Analisis Fundamental"):
    if not stocks:
        st.error("Masukkan minimal satu kode saham untuk dianalisis.")
    else:
        with st.spinner("Menganalisis data fundamental..."):
            ratio_data = get_ratio_data(stocks)
            st.session_state.ratio_data = ratio_data
            evaluations, scores = evaluate_ratios(ratio_data)
            st.session_state.evaluations = evaluations
            st.session_state.scores = scores
            st.session_state.should_display_results = True
            st.rerun()

if st.session_state.should_display_results and st.session_state.ratio_data and stocks:
    display_results(
        stocks,
        st.session_state.ratio_data,
        st.session_state.evaluations,
        st.session_state.scores,
    )

# ─────────────────────────────────────────────
# Hide Streamlit Cloud fork/GitHub toolbar
# ─────────────────────────────────────────────
st.markdown(
    """
    <style>
        .stApp [data-testid="stHeader"]  { display: none !important; }
        .stApp [data-testid="stToolbar"] { display: none !important; }
    </style>
    """,
    unsafe_allow_html=True,
)
