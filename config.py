import os
from dotenv import load_dotenv
import streamlit as st

load_dotenv(override=True)

def get_secret(key: str, default: str = "") -> str:
    """
    1. On essaie de prendre la clé dans st.secrets (Streamlit Cloud)
    2. Si ça n'existe pas, on cherche dans os.environ (Local .env)
    """
    try:
        return st.secrets.get(key) or os.getenv(key, default)
    except Exception:
        return os.getenv(key, default)

class Config:
    ANTHROPIC_API_KEY = get_secret("ANTHROPIC_API_KEY")
    GROQ_API_KEY      = get_secret("GROQ_API_KEY")
    BREVO_API_KEY     = get_secret("BREVO_API_KEY")
    EMAIL_FROM        = get_secret("EMAIL_FROM", "votre-email@example.com")

config = Config()
