import os
from dotenv import load_dotenv
import streamlit as st
load_dotenv(override=True)
def get_secret(key: str, default: str = "") -> str:
    """Retrieve secret from environment variables or streamlit secrets."""
    try:
        val = os.getenv(key) or st.secrets.get(key, default)
    except Exception:
        val = os.getenv(key, default)
    return val

class Config:
    ANTHROPIC_API_KEY = get_secret("ANTHROPIC_API_KEY")
    TWILIO_ACCOUNT_SID = get_secret("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN = get_secret("TWILIO_AUTH_TOKEN")
    TWILIO_FROM_NUMBER = get_secret("TWILIO_FROM_NUMBER")
    BREVO_API_KEY = get_secret("BREVO_API_KEY")
    EMAIL_FROM = get_secret("EMAIL_FROM", "onboarding@resend.dev")

config = Config()
