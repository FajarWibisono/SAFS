import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime as dt
import time

# Set page title and configuration
st.set_page_config(page_title="🔍 SAFS", layout="wide")

# App title and description
st.title("📊 Screening Awal Fundamental Saham")
st.markdown("Aplikasi ini membantu Anda untuk menganalisa dan membandingkan Saham yang menarik perhatian  Anda untuk investasi. **APLIKASI TIDAK BERLAKU UNTUK EMITEN perBANKan.** Aplikasi ini secara otomatis akan membandingkan berbagai RATIO FUNDAMENTAL dari **maksimal 7 saham** yang Anda masukkan, dan Memilih 3 yang terbaik diantara lainnya. **Happy Cuan!!!**")

# Initialize flag for tracking if we need to display results
if 'should_display_results' not in st.session_state:
    st.session_state.should_display_results = False

# Input for stock tickers
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

# Collect all stocks in a list
stocks = [stock for stock in [stock1, stock2, stock3, stock4, stock5, stock6, stock7] if stock]

# Initialize session state for manual inputs and analysis results
if 'manual_values' not in st.session_state:
    st.session_state.manual_values = {}

if 'ratio_data' not in st.session_state:
    st.session_state.ratio_data = {}

if 'evaluations' not in st.session_state:
    st.session_state.evaluations = {}

if 'scores' not in st.session_state:
    st.session_state.scores = {}

if 'stock_prices' not in st.session_state:
    st.session_state.stock_prices = {}

if 'target_prices' not in st.session_state:
    st.session_state.target_prices = {}

if 'estimated_eps' not in st.session_state:
    st.session_state.estimated_eps = {}

# Function to get ratio data
def get_ratio_data(stocks):
    results = {}
    prices = {}
    target_prices = {}
    estimated_eps_values = {}

    for stock in stocks:
        try:
            # Get stock data with retry mechanism
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    ticker = yf.Ticker(stock)
                    info = ticker.info

                    # Get current price
                    current_price = info.get('currentPrice', None)
                    if current_price is None:
                        # Try alternative methods to get price
                        hist = ticker.history(period="1d")
                        if not hist.empty and 'Close' in hist.columns:
                            current_price = hist['Close'].iloc[-1]

                    prices[stock] = current_price

                    # Get target price
                    target_mean_price = info.get('targetMeanPrice', None)
                    target_prices[stock] = target_mean_price

                    # Get estimated EPS
                    estimated_eps = info.get('forwardEps', None)
                    if estimated_eps is None:
                        estimated_eps = info.get('trailingEps', None)  # Fallback to trailing if forward not available
                    estimated_eps_values[stock] = estimated_eps

                    # Get financial data with longer timeframe
                    financials = ticker.financials
                    balance_sheet = ticker.balance_sheet
                    income_stmt = ticker.income_stmt if hasattr(ticker, 'income_stmt') else ticker.financials
                    cash_flow = ticker.cashflow

                    # If we got here, we succeeded
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        time.sleep(1)  # Wait before retrying
                        continue
                    else:
                        raise e

            # ROE (Return on Equity)
            try:
                net_income = financials.loc['Net Income'].iloc[0]
                total_equity = balance_sheet.loc['Total Stockholder Equity'].iloc[0]
                roe = (net_income / total_equity) * 100
            except:
                try:
                    # Alternative method
                    roe = info.get('returnOnEquity', None)
                    if roe:
                        roe = roe * 100
                except:
                    roe = None

            # D/E Ratio (Debt to Equity)
            try:
                if 'Total Debt' in balance_sheet.index:
                    total_debt = balance_sheet.loc['Total Debt'].iloc[0]
                elif 'Long Term Debt' in balance_sheet.index:
                    if 'Short Long Term Debt' in balance_sheet.index:
                        total_debt = balance_sheet.loc['Long Term Debt'].iloc[0] + balance_sheet.loc['Short Long Term Debt'].iloc[0]
                    else:
                        total_debt = balance_sheet.loc['Long Term Debt'].iloc[0]
                else:
                    total_debt = None

                if total_debt and total_equity:
                    de_ratio = total_debt / total_equity
                else:
                    de_ratio = None
            except:
                try:
                    # Alternative method
                    de_ratio = info.get('debtToEquity', None)
                    if de_ratio:
                        de_ratio = de_ratio / 100  # Convert from percentage
                except:
                    de_ratio = None

            # P/E Ratio (Price to Earnings)
            try:
                pe_ratio = info.get('trailingPE', None)
                if not pe_ratio:
                    pe_ratio = info.get('forwardPE', None)
            except:
                pe_ratio = None

            # P/B Ratio (Price to Book)
            try:
                pb_ratio = info.get('priceToBook', None)
            except:
                pb_ratio = None

            # P/S Ratio (Price to Sales)
            try:
                ps_ratio = info.get('priceToSalesTrailing12Months', None)
                if not ps_ratio:
                    # Calculate manually
                    market_cap = info.get('marketCap', None)
                    revenue = financials.loc['Total Revenue'].iloc[0] if 'Total Revenue' in financials.index else None
                    if market_cap and revenue and revenue != 0:
                        ps_ratio = market_cap / revenue
            except:
                ps_ratio = None

            # Dividend Yield
            try:
                div_yield = info.get('dividendYield', 0)
                # Yahoo Finance returns dividend yield as a decimal (e.g., 0.03 for 3%)
            except:
                div_yield = None

            # Operating Margin
            try:
                op_margin = info.get('operatingMargins', None)
                if op_margin:
                    op_margin = op_margin * 100
                else:
                    # Calculate from financial statements
                    if 'Operating Income' in income_stmt.index and 'Total Revenue' in income_stmt.index:
                        op_income = income_stmt.loc['Operating Income'].iloc[0]
                        revenue = income_stmt.loc['Total Revenue'].iloc[0]
                        if revenue != 0:
                            op_margin = (op_income / revenue) * 100
            except:
                op_margin = None

            # Gross Profit Margin (GPM)
            try:
                gpm = info.get('grossMargins', None)
                if gpm:
                    gpm = gpm * 100
                else:
                    # Calculate from financial statements
                    if 'Gross Profit' in income_stmt.index and 'Total Revenue' in income_stmt.index:
                        gross_profit = income_stmt.loc['Gross Profit'].iloc[0]
                        revenue = income_stmt.loc['Total Revenue'].iloc[0]
                        if revenue != 0:
                            gpm = (gross_profit / revenue) * 100
            except:
                gpm = None

            # ROA (Return on Assets)
            try:
                total_assets = balance_sheet.loc['Total Assets'].iloc[0]
                if net_income and total_assets:
                    roa = (net_income / total_assets) * 100
                else:
                    roa = info.get('returnOnAssets', None)
                    if roa:
                        roa = roa * 100
            except:
                roa = None

            # Earnings Yield
            try:
                if pe_ratio and pe_ratio > 0:
                    earnings_yield = (1 / pe_ratio) * 100
                else:
                    earnings_yield = None
            except:
                earnings_yield = None

            # Current Ratio - NEW
            try:
                if 'Current Assets' in balance_sheet.index and 'Current Liabilities' in balance_sheet.index:
                    current_assets = balance_sheet.loc['Current Assets'].iloc[0]
                    current_liabilities = balance_sheet.loc['Current Liabilities'].iloc[0]
                    if current_liabilities != 0:
                        current_ratio = current_assets / current_liabilities
                    else:
                        current_ratio = None
                else:
                    current_ratio = None
            except:
                current_ratio = None

            # PEG Ratio - NEW
            try:
                peg_ratio = info.get('pegRatio', None)
                if not peg_ratio:
                    # Try to calculate if we have PE and growth rate
                    growth_rate = info.get('earningsGrowth', None)
                    if pe_ratio and growth_rate and growth_rate != 0:
                        peg_ratio = pe_ratio / (growth_rate * 100)
            except:
                peg_ratio = None

            # Store results
            results[stock] = {
                "ROE": roe,
                "DER": de_ratio,
                "P/E": pe_ratio,
                "P/B": pb_ratio,
                "P/S": ps_ratio,
                "Dividend Yield": div_yield,
                "Operating Margin": op_margin,
                "GPM": gpm,
                "ROA": roa,
                "Earnings Yield": earnings_yield,
                "Current Ratio": current_ratio,  # NEW
                "PEG Ratio": peg_ratio  # NEW
            }

        except Exception as e:
            st.error(f"Error analyzing {stock}: {str(e)}")
            results[stock] = {
                "ROE": None,
                "DER": None,
                "P/E": None,
                "P/B": None,
                "P/S": None,
                "Dividend Yield": None,
                "Operating Margin": None,
                "GPM": None,
                "ROA": None,
                "Earnings Yield": None,
                "Current Ratio": None,  # NEW
                "PEG Ratio": None  # NEW
            }
            prices[stock] = None
            target_prices[stock] = None
            estimated_eps_values[stock] = None

    # Store values in session state
    st.session_state.stock_prices = prices
    st.session_state.target_prices = target_prices
    st.session_state.estimated_eps = estimated_eps_values
    return results

# Function to evaluate ratios
def evaluate_ratios(ratio_data):
    evaluations = {}
    scores = {}

    for stock, ratios in ratio_data.items():
        evaluations[stock] = {}
        scores[stock] = 0
        good_count = 0

        # Check if we have manual values for this stock
        if stock in st.session_state.manual_values:
            for ratio, value in st.session_state.manual_values[stock].items():
                if value != "":
                    try:
                        ratios[ratio] = float(value)
                    except:
                        pass

        # ROE
        roe = ratios["ROE"]
        if roe is not None:
            if roe > 15:
                evaluations[stock]["ROE"] = "Baik"
                scores[stock] += 2
                good_count += 1
            elif 5 <= roe <= 15:
                evaluations[stock]["ROE"] = "Biasa"
                scores[stock] += 1
            else:
                evaluations[stock]["ROE"] = "Buruk"
        else:
            evaluations[stock]["ROE"] = "N/A"

        # DER
        de = ratios["DER"]
        if de is not None:
            if de < 0.8:
                evaluations[stock]["DER"] = "Baik"
                scores[stock] += 2
                good_count += 1
            elif 0.8 <= de <= 1:
                evaluations[stock]["DER"] = "Biasa"
                scores[stock] += 1
            else:
                evaluations[stock]["DER"] = "Buruk"
        else:
            evaluations[stock]["DER"] = "N/A"

        # P/E
        pe = ratios["P/E"]
        if pe is not None:
            if pe < 15:
                evaluations[stock]["P/E"] = "Baik"
                scores[stock] += 2
                good_count += 1
            elif 15 <= pe <= 25:
                evaluations[stock]["P/E"] = "Biasa"
                scores[stock] += 1
            else:
                evaluations[stock]["P/E"] = "Buruk"
        else:
            evaluations[stock]["P/E"] = "N/A"

        # P/B
        pb = ratios["P/B"]
        if pb is not None:
            if pb < 1.5:
                evaluations[stock]["P/B"] = "Baik"
                scores[stock] += 2
                good_count += 1
            elif 1.5 <= pb <= 3:
                evaluations[stock]["P/B"] = "Biasa"
                scores[stock] += 1
            else:
                evaluations[stock]["P/B"] = "Buruk"
        else:
            evaluations[stock]["P/B"] = "N/A"

        # P/S
        ps = ratios["P/S"]
        if ps is not None:
            if 0 < ps < 1:
                evaluations[stock]["P/S"] = "Baik"
                scores[stock] += 2
                good_count += 1
            elif 1 <= ps <= 2:
                evaluations[stock]["P/S"] = "Biasa"
                scores[stock] += 1
            else:
                evaluations[stock]["P/S"] = "Buruk"
        else:
            evaluations[stock]["P/S"] = "N/A"

        # Dividend Yield - Updated criteria
        div = ratios["Dividend Yield"]
        if div is not None:
            # Ensure dividend yield is in percentage format (0-100)
            if div > 1 and div <= 100:  # If it's already in percentage format (1-100)
                div_pct = div
            elif div > 0 and div <= 1:  # If it's in decimal format (0-1)
                div_pct = div * 100
            else:
                div_pct = div  # Keep as is if it's an unusual value

            if div_pct > 3.75:
                evaluations[stock]["Dividend Yield"] = "Baik"
                scores[stock] += 2
                good_count += 1
            elif 1 <= div_pct <= 3.75:
                evaluations[stock]["Dividend Yield"] = "Biasa"
                scores[stock] += 1
            else:
                evaluations[stock]["Dividend Yield"] = "Buruk"
        else:
            evaluations[stock]["Dividend Yield"] = "N/A"

        # Operating Margin
        om = ratios["Operating Margin"]
        if om is not None:
            if om > 20:
                evaluations[stock]["Operating Margin"] = "Baik"
                scores[stock] += 2
                good_count += 1
            elif 10 <= om <= 20:
                evaluations[stock]["Operating Margin"] = "Biasa"
                scores[stock] += 1
            else:
                evaluations[stock]["Operating Margin"] = "Buruk"
        else:
            evaluations[stock]["Operating Margin"] = "N/A"

        # GPM
        gpm = ratios["GPM"]
        if gpm is not None:
            if gpm > 40:
                evaluations[stock]["GPM"] = "Baik"
                scores[stock] += 2
                good_count += 1
            elif 20 <= gpm <= 40:
                evaluations[stock]["GPM"] = "Biasa"
                scores[stock] += 1
            else:
                evaluations[stock]["GPM"] = "Buruk"
        else:
            evaluations[stock]["GPM"] = "N/A"

        # ROA
        roa = ratios["ROA"]
        if roa is not None:
            if roa > 5:
                evaluations[stock]["ROA"] = "Baik"
                scores[stock] += 2
                good_count += 1
            elif 2 <= roa <= 5:
                evaluations[stock]["ROA"] = "Biasa"
                scores[stock] += 1
            else:
                evaluations[stock]["ROA"] = "Buruk"
        else:
            evaluations[stock]["ROA"] = "N/A"

        # Earnings Yield
        ey = ratios["Earnings Yield"]
        if ey is not None:
            if ey > 10:
                evaluations[stock]["Earnings Yield"] = "Baik"
                scores[stock] += 2
                good_count += 1
            elif 5 <= ey <= 10:
                evaluations[stock]["Earnings Yield"] = "Biasa"
                scores[stock] += 1
            else:
                evaluations[stock]["Earnings Yield"] = "Buruk"
        else:
            evaluations[stock]["Earnings Yield"] = "N/A"

        # Current Ratio - NEW
        cr = ratios["Current Ratio"]
        if cr is not None:
            if cr > 2:
                evaluations[stock]["Current Ratio"] = "Baik"
                scores[stock] += 2
                good_count += 1
            elif 1 <= cr <= 2:
                evaluations[stock]["Current Ratio"] = "Biasa"
                scores[stock] += 1
            else:
                evaluations[stock]["Current Ratio"] = "Buruk"
        else:
            evaluations[stock]["Current Ratio"] = "N/A"

        # PEG Ratio - NEW with UPDATED criteria
        peg = ratios["PEG Ratio"]
        if peg is not None:
            if peg > 0 and peg < 1:  # Changed: Positive and less than 1
                evaluations[stock]["PEG Ratio"] = "Baik"
                scores[stock] += 2
                good_count += 1
            elif peg == 1 or (0.9 <= peg <= 1.1):  # Approximately 1
                evaluations[stock]["PEG Ratio"] = "Biasa"
                scores[stock] += 1
            else:  # Greater than 1 or negative
                evaluations[stock]["PEG Ratio"] = "Buruk"
        else:
            evaluations[stock]["PEG Ratio"] = "N/A"

    return evaluations, scores

# Function to display results in the new format
def display_results(ratio_data, evaluations, scores):
    # Create a comprehensive table with the new format
    ratios = [
        "ROE",
        "DER",
        "P/E",
        "P/B",
        "P/S",
        "Dividend Yield",
        "Operating Margin",
        "GPM",
        "ROA",
        "Earnings Yield",
        "Current Ratio",  
        "PEG Ratio" 
    ]

    # Prepare data for the DataFrame
    data = []
    for stock in stocks:
        if stock in ratio_data:
            row_data = []

            # First column is the stock ticker
            row_data.append(stock)

            # Second column is price
            price = st.session_state.stock_prices.get(stock, None)
            if price is not None:
                row_data.append(f"{price:.2f}")
            else:
                row_data.append("N/A")

            # Add ratio data
            for ratio in ratios:
                value = ratio_data[stock][ratio]
                if isinstance(value, float):
                    if ratio == "Dividend Yield":
                        # Handle dividend yield specially
                        if value > 1 and value <= 100:
                            formatted_value = f"{value:.2f}%"
                        elif value > 0 and value <= 1:
                            formatted_value = f"{value * 100:.2f}%"
                        else:
                            formatted_value = f"{value:.2f}%"
                    elif ratio in ["DER", "P/E", "P/B", "P/S", "Current Ratio", "PEG Ratio"]:
                        formatted_value = f"{value:.2f}"
                    else:
                        formatted_value = f"{value:.2f}%"
                else:
                    formatted_value = "N/A"

                penilaian = evaluations[stock][ratio] if stock in evaluations else "N/A"
                row_data.extend([formatted_value, penilaian])

            # Add Estimated EPS after PEG Ratio
            estimated_eps = st.session_state.estimated_eps.get(stock, None)
            if estimated_eps is not None:
                row_data.append(f"{estimated_eps:.2f}")
            else:
                row_data.append("N/A")

            # Add target price as the last column
            target_price = st.session_state.target_prices.get(stock, None)
            if target_price is not None:
                row_data.append(f"{target_price:.2f}")
            else:
                row_data.append("N/A")

            data.append(row_data)

    # Create column headers
    # First level: SAHAM, PRICE, ratio names, est.EPS, and TARGET PRICE
    # Second level: Empty for SAHAM/PRICE/est.EPS/TARGET PRICE, "Value" and "Penilaian" for ratios
    header_level_1 = ['SAHAM', 'PRICE']
    header_level_2 = ['', '']

    for ratio in ratios:
        header_level_1.extend([ratio, ratio])
        header_level_2.extend(['Value', 'Penilaian'])

    # Add est.EPS after PEG Ratio
    header_level_1.append('est.EPS')
    header_level_2.append('')

    # Add TARGET PRICE at the end
    header_level_1.append('TARGET PRICE')
    header_level_2.append('')

    # Create multi-index columns
    column_tuples = list(zip(header_level_1, header_level_2))
    multi_index = pd.MultiIndex.from_tuples(column_tuples)

    # Create DataFrame with multi-index columns
    df = pd.DataFrame(data, columns=multi_index)

    # Display the table
    st.subheader("Analisis Fundamental")
    st.dataframe(df, use_container_width=True)

    # Allow manual input for N/A values
    st.subheader("Input Manual untuk Nilai N/A")

    # Initialize manual values for each stock if not already done
    for stock in stocks:
        if stock not in st.session_state.manual_values:
            st.session_state.manual_values[stock] = {ratio: "" for ratio in ratios}

    # Create tabs for each stock
    tabs = st.tabs(stocks)
    for i, stock in enumerate(stocks):
        with tabs[i]:
            st.write(f"Input nilai manual untuk {stock}:")

            # Create columns for inputs without using forms
            cols = st.columns(3)

            # Track if we have any N/A values to show
            has_na_values = False

            for j, ratio in enumerate(ratios):
                col_idx = j % 3
                with cols[col_idx]:
                    current_value = ratio_data[stock][ratio]

                    # Always show input fields for all ratios
                    current_input = st.session_state.manual_values[stock].get(ratio, "")

                    # Show the current value (if any)
                    if current_value is not None and isinstance(current_value, float):
                        if ratio == "Dividend Yield" and current_value <= 1:
                            display_value = f"Current: {current_value * 100:.2f}%"
                        elif ratio in ["DER", "P/E", "P/B", "P/S", "Current Ratio", "PEG Ratio"]:
                            display_value = f"Current: {current_value:.2f}"
                        else:
                            display_value = f"Current: {current_value:.2f}%"
                    else:
                        display_value = "Current: N/A"
                        has_na_values = True

                    st.text(display_value)

                    # Create the input field with a unique key
                    new_value = st.text_input(
                        f"Input {ratio}",
                        value=current_input,
                        key=f"manual_input_{stock}_{ratio}_{i}"  # Added index to ensure uniqueness
                    )

                    # Store the value directly in session_state
                    if new_value != current_input:
                        st.session_state.manual_values[stock][ratio] = new_value

            if not has_na_values:
                st.info("Semua nilai rasio sudah tersedia. Input manual akan menggantikan nilai yang ada.")

    # Add "Analisa Kembali" button here (moved from main app logic)
    if st.button("Analisa Kembali", key="reanalyze_button_inside"):
        if not stocks:
            st.error("Masukkan minimal satu kode saham untuk dianalisis.")
        else:
            with st.spinner('Menganalisis ulang data fundamental...'):
                if st.session_state.ratio_data:
                    # Use existing data but re-evaluate with updated manual inputs
                    ratio_data = st.session_state.ratio_data
                    evaluations, scores = evaluate_ratios(ratio_data)
                    st.session_state.evaluations = evaluations
                    st.session_state.scores = scores
                    # Set flag to display results
                    st.session_state.should_display_results = True
                    # Force rerun to display results
                    st.rerun()

    # Generate recommendations
    st.subheader("REKOMENDASI")

    # Filter stocks with at least 7 "Baik" ratings
    good_counts = {stock: sum(1 for val in evals.values() if val == "Baik") for stock, evals in evaluations.items()}
    qualified_stocks = {stock: scores[stock] for stock in stocks if good_counts[stock] >= 5}

    if qualified_stocks:
        # Sort by total score
        sorted_stocks = sorted(qualified_stocks.items(), key=lambda x: x[1], reverse=True)

        # Display top 3 or all if less than 3
        top_stocks = sorted_stocks[:min(3, len(sorted_stocks))]

        for i, (stock, score) in enumerate(top_stocks, 1):
            st.write(f"{i}. **{stock}** - Total Score: {score}, Kriteria Baik: {good_counts[stock]}")
    else:
        st.write("Tidak ada Rekomendasi (Minimal 7 rasio harus dengan kriteria Baik)")

    # Display current date
    current_date = dt.datetime.now().strftime("%d %B %Y")
    st.write(f"Data diambil pada tanggal {current_date}")

# Main app logic - Consolidated flow
analyze_button = st.button("Analisis Fundamental")

# Handle button clicks
if analyze_button:
    if not stocks:
        st.error("Masukkan minimal satu kode saham untuk dianalisis.")
    else:
        with st.spinner('Menganalisis data fundamental...'):
            # Get fresh data
            ratio_data = get_ratio_data(stocks)
            # Store in session state
            st.session_state.ratio_data = ratio_data
            # Evaluate with any existing manual inputs
            evaluations, scores = evaluate_ratios(ratio_data)
            st.session_state.evaluations = evaluations
            st.session_state.scores = scores
            # Set flag to display results
            st.session_state.should_display_results = True
            # Force rerun to display results
            st.rerun()

# Display results if needed
if st.session_state.should_display_results and st.session_state.ratio_data and stocks:
    display_results(
        st.session_state.ratio_data,
        st.session_state.evaluations,
        st.session_state.scores
    )
