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

    st.title("TradePulse — Real-time Indicators")
    uploaded = st.file_uploader(
        "Upload CSV with columns: ts, price, volume", type=["csv"]
    )
    if uploaded:
        df = pd.read_csv(uploaded)
        phases = compute_phase(df["price"].to_numpy())
        R = kuramoto_order(phases[-200:])
        H = entropy(df["price"].to_numpy()[-200:])
        dH = delta_entropy(df["price"].to_numpy(), window=200)
        st.metric("Kuramoto R", f"{R:.3f}")
        st.metric("Entropy H(200)", f"{H:.3f}")
        st.metric("ΔH(200)", f"{dH:.3f}")
        st.line_chart(df[["price"]])
