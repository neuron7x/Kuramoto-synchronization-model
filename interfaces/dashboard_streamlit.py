# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import os
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit_authenticator as stauth

from core.indicators.entropy import delta_entropy, entropy
from core.indicators.kuramoto import compute_phase, kuramoto_order

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
    window_size = st.sidebar.slider("Analysis Window", min_value=50, max_value=500, value=200, step=50)

    # Tabs for different sections
    tab1, tab2, tab3 = st.tabs(["📈 Data Upload", "📊 Indicators", "ℹ️ Info"])

    with tab1:
        st.header("Data Upload & Preview")
        uploaded = st.file_uploader(
            "Upload CSV with columns: ts, price, volume", type=["csv"]
        )

        if uploaded:
            df = pd.read_csv(uploaded)
            st.write("### Data Preview")
            st.dataframe(df.head(10), use_container_width=True)
            st.write(f"**Total rows:** {len(df)}")

            # Validate required columns
            required_cols = ["price"]
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                st.error(f"Missing required columns: {', '.join(missing_cols)}")
            else:
                st.success("Data validated successfully!")

    with tab2:
        st.header("Indicator Analysis")
        if uploaded and 'price' in df.columns:
            # Compute indicators
            prices = df["price"].to_numpy()

            if len(prices) < window_size:
                st.warning(f"Data has {len(prices)} rows but window size is {window_size}. Using all available data.")
                analysis_window = len(prices)
            else:
                analysis_window = window_size

            # Calculate indicators
            phases = compute_phase(prices)
            R = kuramoto_order(phases[-analysis_window:])
            H = entropy(prices[-analysis_window:])
            dH = delta_entropy(prices, window=analysis_window)

            # Display metrics in columns
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(
                    "Kuramoto Order (R)",
                    f"{R:.4f}",
                    help="Measures phase synchronization. Higher values indicate stronger coherence."
                )
            with col2:
                st.metric(
                    f"Entropy H({analysis_window})",
                    f"{H:.4f}",
                    help="Shannon entropy of price distribution. Higher values indicate more uncertainty."
                )
            with col3:
                st.metric(
                    f"Delta Entropy ΔH({analysis_window})",
                    f"{dH:.4f}",
                    help="Change in entropy over the window. Indicates shifting market dynamics."
                )

            # Visualization
            st.write("### Price Series")
            st.line_chart(df["price"], use_container_width=True)

            if "volume" in df.columns:
                st.write("### Volume")
                st.bar_chart(df["volume"], use_container_width=True)

            # Market regime interpretation
            st.write("### Market Regime Analysis")
            if R > 0.7:
                regime = "🟢 High Coherence - Strong trend or pattern detected"
            elif R > 0.4:
                regime = "🟡 Moderate Coherence - Mixed signals"
            else:
                regime = "🔴 Low Coherence - Noisy or random behavior"
            st.info(regime)

        else:
            st.info("Upload data in the 'Data Upload' tab to see indicator analysis.")

    with tab3:
        st.header("About TradePulse Indicators")
        st.markdown("""
        ### Kuramoto Order Parameter
        The Kuramoto model describes synchronization of coupled oscillators. In trading:
        - **R ≈ 1**: Strong phase synchronization (trending market)
        - **R ≈ 0**: No synchronization (random walk)

        ### Shannon Entropy
        Measures the information content and uncertainty in price distribution:
        - **High H**: More unpredictable, diverse outcomes
        - **Low H**: More concentrated, predictable distribution

        ### Delta Entropy
        Tracks the change in entropy over time:
        - **Positive ΔH**: Increasing uncertainty
        - **Negative ΔH**: Decreasing uncertainty, potential regime shift

        ---

        **TradePulse** combines geometric indicators with traditional technical analysis
        for robust market regime detection and signal generation.
        """)

        st.write("### Quick Tips")
        st.markdown("""
        1. **Upload** your price/volume CSV data
        2. **Adjust** the analysis window using the sidebar slider
        3. **Interpret** the indicators in context of your strategy
        4. Use **multiple timeframes** for confirmation
        """)

