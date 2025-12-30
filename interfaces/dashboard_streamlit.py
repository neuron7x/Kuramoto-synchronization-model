# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Prototype Streamlit dashboard (dev-only); canonical UI lives in ui/dashboard (TypeScript).

Enhanced TradePulse Streamlit Dashboard with comprehensive analysis features.

This module provides a web-based interface for analyzing market data using
TradePulse's geometric indicators. Features include:
- CSV data upload and validation
- Multi-indicator analysis (Kuramoto, Entropy, Ricci, Hurst)
- Interactive visualizations with time-series charts
- Export functionality for analysis results
- Historical comparison capabilities
- Configuration persistence
"""
import json
import os
from datetime import datetime
from io import StringIO
from pathlib import Path

from interfaces.streamlit_security import enforce_dev_only_dashboard

enforce_dev_only_dashboard()

import numpy as np
import pandas as pd
import streamlit as st
import streamlit_authenticator as stauth

from core.indicators.entropy import delta_entropy, entropy
from core.indicators.hurst import hurst_exponent
from core.indicators.kuramoto import compute_phase, kuramoto_order
from core.indicators.ricci import build_price_graph, mean_ricci

# Load environment variables
try:
    from dotenv import load_dotenv

    # Try to load from .env file in project root
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # dotenv is optional


# Authentication configuration from environment variables
def load_auth_config():
    """Load authentication configuration from environment variables."""
    username = os.getenv("DASHBOARD_ADMIN_USERNAME", "admin")
    password_hash = os.getenv(
        "DASHBOARD_ADMIN_PASSWORD_HASH",
        # Default hash for 'admin123' (ONLY for development/example)
        "$2b$12$EixZaYVK1fsbw1ZfbX3OXe.RKjKWbFUZYWbAKpKnvGmcPNW3OL2K6",
    )
    cookie_name = os.getenv("DASHBOARD_COOKIE_NAME", "tradepulse_auth")
    cookie_key = os.getenv(
        "DASHBOARD_COOKIE_KEY", "default_cookie_key_change_in_production"
    )
    cookie_expiry_days = int(os.getenv("DASHBOARD_COOKIE_EXPIRY_DAYS", "30"))

    return {
        "credentials": {
            "usernames": {
                username: {"name": username.capitalize(), "password": password_hash}
            }
        },
        "cookie": {
            "name": cookie_name,
            "key": cookie_key,
            "expiry_days": cookie_expiry_days,
        },
        "preauthorized": [],
    }


# Initialize authenticator
config = load_auth_config()
authenticator = stauth.Authenticate(
    config["credentials"],
    config["cookie"]["name"],
    config["cookie"]["key"],
    config["cookie"]["expiry_days"],
    config["preauthorized"],
)

# Display login form
name, authentication_status, username = authenticator.login("Login", "main")

# Handle authentication status
if authentication_status is False:
    st.error("Username/password is incorrect")
elif authentication_status is None:
    st.warning("Please enter your username and password")
else:
    # User is authenticated - show the dashboard
    authenticator.logout("Logout", "sidebar")
    st.sidebar.write(f"Welcome *{name}*")

    st.title("TradePulse — Real-time Indicators Dashboard")

    st.sidebar.header("Configuration")
    window_size = st.sidebar.slider(
        "Analysis Window", min_value=50, max_value=500, value=200, step=50
    )

    # Additional configuration options
    st.sidebar.subheader("Advanced Settings")
    ricci_delta = st.sidebar.number_input(
        "Ricci Delta",
        min_value=0.001,
        max_value=0.1,
        value=0.005,
        step=0.001,
        help="Step size for Ricci curvature calculation",
    )
    entropy_bins = st.sidebar.slider(
        "Entropy Bins",
        min_value=10,
        max_value=100,
        value=50,
        step=10,
        help="Number of bins for entropy calculation",
    )

    # Initialize session state for data persistence
    if "analysis_history" not in st.session_state:
        st.session_state.analysis_history = []
    if "uploaded_filename" not in st.session_state:
        st.session_state.uploaded_filename = None

    # Tabs for different sections
    tab1, tab2, tab3, tab4 = st.tabs(
        ["📈 Data Upload", "📊 Indicators", "📋 Export & History", "ℹ️ Info"]
    )

    with tab1:
        st.header("Data Upload & Preview")
        uploaded = st.file_uploader(
            "Upload CSV with columns: ts, price, volume", type=["csv"]
        )

        if uploaded:
            try:
                df = pd.read_csv(uploaded)
                st.session_state.uploaded_filename = uploaded.name

                st.write("### Data Preview")
                st.dataframe(df.head(10), use_container_width=True)

                # Data statistics
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total rows", len(df))
                with col2:
                    st.metric("Columns", len(df.columns))
                with col3:
                    if "price" in df.columns:
                        st.metric(
                            "Price Range",
                            f"${df['price'].min():.2f} - ${df['price'].max():.2f}",
                        )

                # Enhanced validation with detailed feedback
                st.write("### Data Validation")
                required_cols = ["price"]
                optional_cols = ["volume", "ts", "timestamp", "date"]

                validation_passed = True

                # Check required columns
                missing_cols = [col for col in required_cols if col not in df.columns]
                if missing_cols:
                    st.error(f"❌ Missing required columns: {', '.join(missing_cols)}")
                    validation_passed = False
                else:
                    st.success("✅ Required column 'price' found")

                # Check optional columns
                found_optional = [col for col in optional_cols if col in df.columns]
                if found_optional:
                    st.info(f"📊 Optional columns found: {', '.join(found_optional)}")

                # Check for missing values
                if "price" in df.columns:
                    missing_prices = df["price"].isna().sum()
                    if missing_prices > 0:
                        st.warning(
                            f"⚠️ Found {missing_prices} missing price values ({missing_prices/len(df)*100:.1f}%)"
                        )
                        if st.button("Remove rows with missing prices"):
                            df = df.dropna(subset=["price"])
                            st.success(
                                f"Removed {missing_prices} rows. New total: {len(df)}"
                            )
                    else:
                        st.success("✅ No missing price values")

                # Check data quality
                if "price" in df.columns and len(df) > 0:
                    price_stats = df["price"].describe()
                    if price_stats["std"] == 0:
                        st.error("❌ Price data has no variation (constant values)")
                        validation_passed = False
                    else:
                        st.success(
                            f"✅ Price variation detected (std: {price_stats['std']:.4f})"
                        )

                if validation_passed:
                    st.success(
                        "🎉 Data validated successfully! You can proceed to indicator analysis."
                    )

            except Exception as e:
                st.error(f"❌ Error loading CSV file: {str(e)}")
                st.info(
                    "Please ensure your CSV file is properly formatted with a 'price' column."
                )

    with tab2:
        st.header("Indicator Analysis")
        if uploaded and "price" in df.columns:
            try:
                # Compute indicators
                prices = df["price"].to_numpy()

                if len(prices) < window_size:
                    st.warning(
                        f"Data has {len(prices)} rows but window size is {window_size}. Using all available data."
                    )
                    analysis_window = len(prices)
                else:
                    analysis_window = window_size

                # Progress indicator for calculations
                with st.spinner("Computing indicators..."):
                    # Calculate all indicators
                    phases = compute_phase(prices)
                    R = kuramoto_order(phases[-analysis_window:])
                    H = entropy(prices[-analysis_window:], bins=entropy_bins)
                    dH = delta_entropy(prices, window=analysis_window)

                    # Add Ricci curvature
                    ricci_window = min(analysis_window, len(prices))
                    graph = build_price_graph(prices[-ricci_window:], delta=ricci_delta)
                    kappa = mean_ricci(graph)

                    # Add Hurst exponent
                    Hs = hurst_exponent(prices[-analysis_window:])

                # Display metrics in columns with enhanced information
                st.write("### Core Indicators")
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.metric(
                        "Kuramoto Order (R)",
                        f"{R:.4f}",
                        help="Measures phase synchronization. Higher values indicate stronger coherence.",
                    )
                with col2:
                    st.metric(
                        f"Entropy H({analysis_window})",
                        f"{H:.4f}",
                        help="Shannon entropy of price distribution. Higher values indicate more uncertainty.",
                    )
                with col3:
                    st.metric(
                        f"Delta Entropy ΔH({analysis_window})",
                        f"{dH:.4f}",
                        help="Change in entropy over the window. Indicates shifting market dynamics.",
                    )
                with col4:
                    st.metric(
                        "Hurst Exponent",
                        f"{Hs:.4f}",
                        help="Measures long-term memory. H>0.5: trending, H<0.5: mean-reverting, H≈0.5: random walk",
                    )

                # Additional metrics
                st.write("### Geometric Indicators")
                col1, col2 = st.columns(2)

                with col1:
                    st.metric(
                        "Mean Ricci Curvature (κ)",
                        f"{kappa:.6f}",
                        help="Geometric curvature of price manifold. Negative values indicate expanding regimes.",
                    )
                with col2:
                    # Market regime classification
                    if Hs > 0.6:
                        regime_type = "Trending"
                    elif Hs < 0.4:
                        regime_type = "Mean-Reverting"
                    else:
                        regime_type = "Random Walk"
                    st.metric(
                        "Regime Type",
                        regime_type,
                        help="Based on Hurst exponent classification",
                    )

                # Visualization
                st.write("### Price Series Visualization")

                # Create price chart with moving average
                price_df = pd.DataFrame(
                    {
                        "Price": prices,
                        f"MA{analysis_window}": pd.Series(prices)
                        .rolling(window=min(20, len(prices)))
                        .mean(),
                    }
                )
                st.line_chart(price_df, use_container_width=True)

                if "volume" in df.columns:
                    st.write("### Volume Analysis")
                    st.bar_chart(df["volume"], use_container_width=True)

                # Enhanced market regime interpretation
                st.write("### Market Regime Analysis")

                # Kuramoto-based regime
                if R > 0.7:
                    kuramoto_regime = (
                        "🟢 High Coherence - Strong trend or pattern detected"
                    )
                    regime_color = "green"
                elif R > 0.4:
                    kuramoto_regime = "🟡 Moderate Coherence - Mixed signals"
                    regime_color = "orange"
                else:
                    kuramoto_regime = "🔴 Low Coherence - Noisy or random behavior"
                    regime_color = "red"

                st.info(kuramoto_regime)

                # Comprehensive analysis summary
                with st.expander("📊 Detailed Analysis Summary"):
                    st.markdown(
                        f"""
                    **Analysis Window:** {analysis_window} periods
                    **Data Points Analyzed:** {len(prices)}

                    **Synchronization Analysis:**
                    - Kuramoto Order Parameter: {R:.4f}
                    - Interpretation: {'High synchronization' if R > 0.7 else 'Moderate synchronization' if R > 0.4 else 'Low synchronization'}

                    **Information Theory:**
                    - Shannon Entropy: {H:.4f}
                    - Delta Entropy: {dH:.4f}
                    - Entropy Trend: {'Increasing uncertainty' if dH > 0 else 'Decreasing uncertainty'}

                    **Long-term Memory:**
                    - Hurst Exponent: {Hs:.4f}
                    - Market Behavior: {regime_type}
                    - Predictability: {'High' if abs(Hs - 0.5) > 0.15 else 'Moderate' if abs(Hs - 0.5) > 0.05 else 'Low'}

                    **Geometric Properties:**
                    - Mean Ricci Curvature: {kappa:.6f}
                    - Price Manifold: {'Contracting' if kappa > 0 else 'Expanding' if kappa < -0.001 else 'Stable'}
                    """
                    )

                # Store analysis in history
                analysis_record = {
                    "timestamp": datetime.now().isoformat(),
                    "filename": st.session_state.uploaded_filename,
                    "window_size": analysis_window,
                    "R": float(R),
                    "H": float(H),
                    "dH": float(dH),
                    "Hs": float(Hs),
                    "kappa": float(kappa),
                    "regime": regime_type,
                }

                # Append to history (keep last 10)
                st.session_state.analysis_history.append(analysis_record)
                if len(st.session_state.analysis_history) > 10:
                    st.session_state.analysis_history.pop(0)

            except Exception as e:
                st.error(f"❌ Error during indicator computation: {str(e)}")
                st.info(
                    "This may be due to insufficient data or invalid values. Please check your dataset."
                )

        else:
            st.info(
                "📥 Upload data in the 'Data Upload' tab to see indicator analysis."
            )
            st.write("### What You'll Get:")
            st.markdown(
                """
            - **Kuramoto Order Parameter**: Phase synchronization analysis
            - **Shannon Entropy**: Information content and uncertainty measures
            - **Hurst Exponent**: Long-term memory and trend detection
            - **Ricci Curvature**: Geometric market manifold analysis
            - **Interactive Visualizations**: Price charts with moving averages
            - **Regime Classification**: Automated market state detection
            """
            )

    with tab3:
        st.header("Export & Analysis History")

        # Export current analysis
        if (
            uploaded
            and "price" in df.columns
            and len(st.session_state.analysis_history) > 0
        ):
            st.write("### Export Current Analysis")

            latest_analysis = st.session_state.analysis_history[-1]

            col1, col2 = st.columns(2)

            with col1:
                # Export as JSON
                json_str = json.dumps(latest_analysis, indent=2)
                st.download_button(
                    label="📥 Download as JSON",
                    data=json_str,
                    file_name=f"tradepulse_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                    help="Download analysis results in JSON format",
                )

            with col2:
                # Export as CSV
                analysis_df = pd.DataFrame([latest_analysis])
                csv_buffer = StringIO()
                analysis_df.to_csv(csv_buffer, index=False)
                st.download_button(
                    label="📥 Download as CSV",
                    data=csv_buffer.getvalue(),
                    file_name=f"tradepulse_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    help="Download analysis results in CSV format",
                )

            # Export price data with indicators
            if st.checkbox("Include full price data with indicators"):
                st.write("### Export Enhanced Dataset")
                st.info(
                    "This will include your original price data with computed indicator values."
                )

                try:
                    prices = df["price"].to_numpy()

                    # Compute indicator time series
                    phases = compute_phase(prices)

                    # Create enhanced dataframe
                    enhanced_df = df.copy()
                    enhanced_df["phase"] = phases

                    # Add rolling indicators
                    window = min(window_size, len(prices))
                    enhanced_df["kuramoto_order"] = pd.Series(
                        [
                            (
                                kuramoto_order(phases[max(0, i - window) : i + 1])
                                if i >= window
                                else np.nan
                            )
                            for i in range(len(phases))
                        ]
                    )

                    csv_buffer = StringIO()
                    enhanced_df.to_csv(csv_buffer, index=False)

                    st.download_button(
                        label="📥 Download Enhanced Dataset",
                        data=csv_buffer.getvalue(),
                        file_name=f"tradepulse_enhanced_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        help="Download original data with computed indicators",
                    )
                except Exception as e:
                    st.error(f"Error creating enhanced dataset: {str(e)}")

        # Analysis history
        st.write("### Analysis History")
        if len(st.session_state.analysis_history) > 0:
            st.write(f"Showing last {len(st.session_state.analysis_history)} analyses")

            # Convert history to dataframe for display
            history_df = pd.DataFrame(st.session_state.analysis_history)
            history_df["timestamp"] = pd.to_datetime(history_df["timestamp"])

            # Display history table
            st.dataframe(
                history_df[
                    ["timestamp", "filename", "R", "H", "Hs", "regime"]
                ].sort_values("timestamp", ascending=False),
                use_container_width=True,
                hide_index=True,
            )

            # Historical comparison chart
            if len(history_df) > 1:
                st.write("### Historical Trends")

                metric_choice = st.selectbox(
                    "Select metric to visualize",
                    ["R", "H", "dH", "Hs", "kappa"],
                    help="Choose which indicator to plot over analysis history",
                )

                chart_df = history_df[["timestamp", metric_choice]].set_index(
                    "timestamp"
                )
                st.line_chart(chart_df, use_container_width=True)

            # Clear history button
            if st.button("🗑️ Clear History"):
                st.session_state.analysis_history = []
                st.success("Analysis history cleared!")
                st.rerun()

            # Export all history
            history_json = json.dumps(st.session_state.analysis_history, indent=2)
            st.download_button(
                label="📥 Download All History (JSON)",
                data=history_json,
                file_name=f"tradepulse_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                help="Download complete analysis history",
            )
        else:
            st.info(
                "No analysis history yet. Analyze some data in the 'Indicators' tab to build history."
            )

    with tab4:
        st.header("About TradePulse Indicators")
        st.markdown(
            """
        ### Kuramoto Order Parameter (R)
        The Kuramoto model describes synchronization of coupled oscillators. In trading:
        - **R ≈ 1**: Strong phase synchronization (trending market)
        - **R > 0.7**: High coherence, strong patterns
        - **0.4 < R < 0.7**: Moderate coherence, mixed signals
        - **R < 0.4**: Low coherence, noisy/random behavior
        - **R ≈ 0**: No synchronization (random walk)

        ### Shannon Entropy (H)
        Measures the information content and uncertainty in price distribution:
        - **High H**: More unpredictable, diverse outcomes, high volatility
        - **Low H**: More concentrated, predictable distribution, low volatility
        - Range: 0 (perfectly predictable) to log₂(bins) (maximum uncertainty)

        ### Delta Entropy (ΔH)
        Tracks the change in entropy over time:
        - **Positive ΔH**: Increasing uncertainty, potential trend breakout
        - **Negative ΔH**: Decreasing uncertainty, potential regime shift or consolidation
        - **ΔH ≈ 0**: Stable market conditions

        ### Hurst Exponent (H)
        Measures long-term memory and trend persistence:
        - **H > 0.5**: Trending/persistent behavior (momentum strategies)
        - **H = 0.5**: Random walk (efficient market)
        - **H < 0.5**: Mean-reverting behavior (reversion strategies)
        - **H > 0.6**: Strong trending
        - **H < 0.4**: Strong mean reversion

        ### Ricci Curvature (κ)
        Geometric curvature of the price manifold:
        - **κ > 0**: Contracting regime, prices converging
        - **κ ≈ 0**: Stable/flat geometry
        - **κ < 0**: Expanding regime, prices diverging
        - Useful for detecting regime changes and phase transitions

        ---

        ### How TradePulse Works

        **TradePulse** combines geometric indicators with traditional technical analysis
        for robust market regime detection and signal generation. The platform uses:

        1. **Multi-scale Analysis**: Examines patterns at different timeframes
        2. **Phase Synchronization**: Detects coherent market behavior
        3. **Information Theory**: Quantifies uncertainty and randomness
        4. **Geometric Methods**: Analyzes market structure via manifold curvature
        5. **Fractal Analysis**: Identifies self-similar patterns and long-term memory

        ### Best Practices

        """
        )

        st.write("### Quick Tips")
        st.markdown(
            """
        1. **Upload** your price/volume CSV data with at least a 'price' column
        2. **Adjust** the analysis window using the sidebar slider (recommend 100-300 periods)
        3. **Interpret** the indicators in context of your strategy and market conditions
        4. **Use multiple timeframes** for confirmation of signals
        5. **Export results** for further analysis or record-keeping
        6. **Monitor history** to track how indicators evolve over time
        7. **Combine indicators** - No single indicator is perfect; use multiple for confirmation

        ### CSV Format Requirements

        **Required columns:**
        - `price`: Numeric price values (close, last, mid, etc.)

        **Optional columns:**
        - `volume`: Trading volume
        - `ts`, `timestamp`, or `date`: Time information
        - Any other columns will be preserved but not used in analysis

        **Example CSV:**
        ```
        timestamp,price,volume
        2024-01-01 09:00,100.5,1000000
        2024-01-01 10:00,101.2,1200000
        2024-01-01 11:00,100.8,900000
        ```

        ### Troubleshooting

        - **"Missing required columns"**: Ensure your CSV has a column named 'price'
        - **"Data has no variation"**: Check that prices are not constant
        - **"Insufficient data"**: Increase your dataset size or decrease the analysis window
        - **Computation errors**: Ensure price values are numeric and not missing

        ### Resources

        - [TradePulse Documentation](https://github.com/neuron7x/TradePulse)
        - [Indicator Theory](https://github.com/neuron7x/TradePulse/docs/indicators.md)
        - [API Reference](https://docs.tradepulse.io/api)
        """
        )

        # System info
        with st.expander("🔧 System Information"):
            st.markdown(
                f"""
            **Dashboard Version:** 2.0.0
            **Analysis Window:** {window_size} periods
            **Entropy Bins:** {entropy_bins}
            **Ricci Delta:** {ricci_delta}
            **Session Analyses:** {len(st.session_state.analysis_history)}
            **User:** {name}
            """
            )
