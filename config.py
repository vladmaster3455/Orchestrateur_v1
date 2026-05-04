import os
from dotenv import load_dotenv

load_dotenv(override=True)

def get_secret(key: str, default: str = "") -> str:
    """
    Get secret from environment or Streamlit secrets.
    1. Try Streamlit secrets (if available)
    2. Fall back to environment variables
    """
    try:
        import streamlit as st
        return st.secrets.get(key) or os.getenv(key, default)
    except Exception:
        return os.getenv(key, default)

class Config:
    ANTHROPIC_API_KEY = get_secret("ANTHROPIC_API_KEY")
    GROQ_API_KEY      = get_secret("GROQ_API_KEY")
    BREVO_API_KEY     = get_secret("BREVO_API_KEY")
    EMAIL_FROM        = get_secret("EMAIL_FROM", "votre-email@example.com")

config = Config()
