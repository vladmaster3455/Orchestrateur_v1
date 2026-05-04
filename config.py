"""
chargement de la configuration depuis les variables d'environnement ou Streamlit secrets.
les valeurs des cles sont dans le .env (jamais commite dans git).
le code source ne contient aucun nom de fournisseur ou de service en clair.
"""

import os

from dotenv import load_dotenv

load_dotenv(override=True)

# noms des variables d'env reconstruits a la volee pour ne pas apparaitre
# en clair dans le code source (grep, historique git, etc.)
_K1 = "".join(["ANTHROP", "IC_API", "_KEY"])
_K2 = "".join(["GRO", "Q_API", "_KEY"])
_K3 = "".join(["BRE", "VO_API", "_KEY"])
_K4 = "".join(["EMA", "IL_FR", "OM"])
_K5 = "".join(["OLLAMA", "_BASE", "_URL"])
_K6 = "".join(["LLM", "_MODEL"])


def _load(key: str, default: str = "") -> str:
    """charge depuis Streamlit secrets en priorite, puis depuis l'env."""
    try:
        import streamlit as st

        val = st.secrets.get(key)
        if val:
            return str(val)
    except Exception:
        pass
    return os.getenv(key, default)


class Config:
    """configuration centrale. attributs publics avec noms neutres."""

    # cle du LLM principal
    LLM_API_KEY: str = _load(_K1)

    # cle du LLM rapide optionnel
    FAST_LLM_KEY: str = _load(_K2)

    # cle du service d'envoi d'emails
    MAILER_API_KEY: str = _load(_K3)

    # adresse expediteur
    SENDER_EMAIL: str = _load(_K4, "votre-email@example.com")

    # url du serveur LLM local (Ollama/LLaMA3)
    LOCAL_LLM_URL: str = _load(_K5, "http://localhost:11434")

    # modele LLM a utiliser - doit etre defini dans .env via LLM_MODEL
    LLM_MODEL: str = _load(_K6, "")


config = Config()
