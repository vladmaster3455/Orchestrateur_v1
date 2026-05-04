"""
Interface Streamlit de l'orchestrateur AISenghor.
Principe SOLID :
  - SRP : ce fichier gere uniquement la couche presentation.
  - DIP : depend des abstractions exposees par orchestrator.py, pas des agents directement.
"""

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from config import config
from orchestrator import continue_pending_email, continue_pending_rag, route
from ui.sidebar import render_sidebar
from ui.styles import inject_styles

# ---------------------------------------------------------------------------
# Configuration de la page
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AISenghor Orchestrateur",
    layout="centered",
    initial_sidebar_state="expanded",
)

# Point d'entree pour les cron jobs keep-alive (ex. cron-job.org)
# URL : https://votre-app.streamlit.app/?ping=1
if st.query_params.get("ping") == "1":
    st.write("OK - serveur actif")
    st.stop()

inject_styles()

# ---------------------------------------------------------------------------
# Initialisation de l'etat de session
# ---------------------------------------------------------------------------
_SESSION_DEFAULTS = {
    "messages": [],
    "indexed_file": None,
    "suggestion_prompt": None,
    "chat_history": [],
    "scroll_to_bottom_next": False,
    "next_history_id": 1,
    "pending_action": None,
    "active_agent": None,
}
for key, default in _SESSION_DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ---------------------------------------------------------------------------
# Fonctions utilitaires de presentation
# ---------------------------------------------------------------------------


def scroll_to_bottom() -> None:
    """Force le defilement vers le bas via JavaScript."""
    st.write("")
    components.html(
        """
        <script>
        function scrollDown() {
            window.scrollTo(0, document.body.scrollHeight);
            document.documentElement.scrollTop = document.documentElement.scrollHeight;
        }
        scrollDown();
        for (let i = 1; i <= 8; i++) {
            setTimeout(scrollDown, i * 120);
        }
        </script>
        """,
        height=0,
    )


def save_current_conversation() -> None:
    """Sauvegarde la conversation courante dans l'historique de session."""
    if not st.session_state.messages:
        return

    first_user = next(
        (
            m.get("content", "")
            for m in st.session_state.messages
            if m.get("role") == "user"
        ),
        "",
    )
    title = first_user.strip()[:40] or "Conversation sans titre"

    st.session_state.chat_history.append(
        {
            "id": st.session_state.next_history_id,
            "title": title,
            "messages": [dict(m) for m in st.session_state.messages],
            "indexed_file": st.session_state.indexed_file,
            "pending_action": st.session_state.pending_action,
        }
    )
    st.session_state.next_history_id += 1


# ---------------------------------------------------------------------------
# Barre laterale
# ---------------------------------------------------------------------------
sidebar_actions = render_sidebar()

if sidebar_actions.get("new_chat"):
    from agents.rag_agent import reset_index

    save_current_conversation()
    reset_index()
    st.session_state.messages = []
    st.session_state.indexed_file = None
    st.session_state.suggestion_prompt = None
    st.session_state.pending_action = None
    st.rerun()

history_to_load = sidebar_actions.get("load_history_id")
if history_to_load is not None:
    selected = next(
        (
            item
            for item in st.session_state.chat_history
            if item.get("id") == history_to_load
        ),
        None,
    )
    if selected:
        st.session_state.messages = [dict(m) for m in selected.get("messages", [])]
        st.session_state.indexed_file = selected.get("indexed_file")
        st.session_state.pending_action = selected.get("pending_action")
        st.rerun()

# ---------------------------------------------------------------------------
# Raccourcis d'agent
# ---------------------------------------------------------------------------
col1, col2 = st.columns(2)

with col1:
    if st.button(
        "Agent Email", use_container_width=True, type="secondary", key="btn_agent_email"
    ):
        st.session_state.active_agent = "EMAIL"
        st.session_state.pending_action = {"agent": "EMAIL", "context": {}}
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": (
                    "**Agent Email**\n\n"
                    "Je suis specialise dans la redaction et l'envoi d'emails professionnels. "
                    "Donnez-moi l'adresse du destinataire et le contexte de votre message, "
                    "je me chargerai de rediger un email professionnel et de l'envoyer.\n\n"
                    'Exemple : "Envoie un email a direction@entreprise.com pour demander une reunion demain."'
                ),
                "agent": "EMAIL",
            }
        )
        st.session_state.scroll_to_bottom_next = True

with col2:
    if st.button(
        "Agent RAG", use_container_width=True, type="secondary", key="btn_agent_rag"
    ):
        st.session_state.active_agent = "RAG"
        st.session_state.pending_action = {"agent": "RAG", "context": {}}
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": (
                    "**Agent RAG (Analyse Documentaire)**\n\n"
                    "Je peux lire, comprendre et analyser vos documents (PDF, images, textes). "
                    "Telechargez un fichier via le bouton trombone dans la barre de saisie, "
                    "puis posez-moi n'importe quelle question sur son contenu.\n\n"
                    "Exemple : uploadez un PDF puis demandez : "
                    '"Quels sont les trois points cles de ce document ?"'
                ),
                "agent": "RAG",
            }
        )
        st.session_state.scroll_to_bottom_next = True

# ---------------------------------------------------------------------------
# Etat initial vide
# ---------------------------------------------------------------------------
if len(st.session_state.messages) == 0:
    st.markdown(
        '<div class="aisenghor-header">Tous vos outils au meme endroit</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="aisenghor-subheader">'
        "Si aucun agent n'est selectionne, l'orchestrateur choisit automatiquement "
        "le meilleur agent en fonction de votre requete."
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<br><br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Affichage de l'historique de la conversation
# ---------------------------------------------------------------------------
for msg in st.session_state.messages:
    role = msg["role"]
    content = msg.get("content", "")
    with st.chat_message(role):
        if role == "user":
            st.markdown(
                f'<span class="user-msg-marker"></span>\n\n{content}',
                unsafe_allow_html=True,
            )
        else:
            agent_badge = ""
            msg_agent = msg.get("agent", "")
            if msg_agent in ("EMAIL", "RAG"):
                agent_badge = (
                    f'<span class="agent-badge">Agent {msg_agent}</span><br><br>'
                )
            st.markdown(
                f'<span class="assistant-msg-marker"></span>\n\n{agent_badge}{content}',
                unsafe_allow_html=True,
            )

if len(st.session_state.messages) > 0 or st.session_state.scroll_to_bottom_next:
    scroll_to_bottom()
    st.session_state.scroll_to_bottom_next = False

# ---------------------------------------------------------------------------
# Saisie utilisateur
# ---------------------------------------------------------------------------
prompt = st.chat_input(
    "Message AISenghor...",
    accept_file=True,
    file_type=["pdf", "txt", "png", "jpg", "jpeg"],
)

user_text: str = ""
uploaded_files = []

if st.session_state.suggestion_prompt:
    user_text = st.session_state.suggestion_prompt
    st.session_state.suggestion_prompt = None
elif prompt:
    if hasattr(prompt, "text"):
        user_text = prompt.text or ""
        uploaded_files = prompt.files or []
    elif isinstance(prompt, dict):
        user_text = prompt.get("text", "")
        uploaded_files = prompt.get("files", [])
    else:
        user_text = str(prompt)

# ---------------------------------------------------------------------------
# Traitement de la requete
# ---------------------------------------------------------------------------
# variables initialise avant le bloc conditionnel pour evite les unbound
response_text: str = ""
agent: str = "ORCHESTRATOR"

if user_text or uploaded_files:
    # Traitement d'un fichier uploade
    if uploaded_files:
        uploaded = uploaded_files[0]
        docs_dir = Path("data/documents")
        docs_dir.mkdir(exist_ok=True)
        file_path = docs_dir / uploaded.name
        file_path.write_bytes(uploaded.read())

        with st.spinner(f"Analyse de {uploaded.name} en cours..."):
            from agents.rag_agent import build_index_from_file

            index_result = build_index_from_file(str(file_path))

            if index_result["success"]:
                st.session_state.indexed_file = uploaded.name
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": index_result["response"],
                        "agent": "RAG",
                    }
                )
                pending = st.session_state.pending_action
                if pending and pending.get("agent") == "RAG":
                    follow_up = continue_pending_rag("", pending.get("context", {}))
                    st.session_state.pending_action = follow_up.get("pending_action")
                    st.session_state.active_agent = "RAG"
                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": follow_up.get("response", ""),
                            "agent": "RAG",
                        }
                    )
            else:
                st.error(index_result["error"])
                st.stop()

        if not user_text:
            st.rerun()

    # Ajout du message utilisateur dans l'historique
    st.session_state.messages.append({"role": "user", "content": user_text})

    with st.chat_message("user"):
        st.markdown(
            f'<span class="user-msg-marker"></span>\n\n{user_text}',
            unsafe_allow_html=True,
        )

    # Generation de la reponse
    with st.chat_message("assistant"):
        if not config.LLM_API_KEY:
            st.error("Erreur : la cle LLM n'est pas configuree. Verifiez votre .env.")
        else:
            with st.spinner("Traitement en cours..."):
                pending = st.session_state.pending_action

                if pending and pending.get("agent") == "EMAIL":
                    result = continue_pending_email(
                        user_text, pending.get("context", {})
                    )
                elif pending and pending.get("agent") == "RAG":
                    result = continue_pending_rag(user_text, pending.get("context", {}))
                else:
                    history = [
                        {"role": m["role"], "content": m["content"]}
                        for m in st.session_state.messages[:-1]
                    ]
                    result = route(user_text, history)

            agent = result.get("agent", "ORCHESTRATOR")
            response_text = result.get("response", "")
            st.session_state.pending_action = result.get("pending_action")

            if agent in ("EMAIL", "RAG"):
                st.session_state.active_agent = agent

            agent_badge = ""
            if agent in ("EMAIL", "RAG"):
                agent_badge = f'<span class="agent-badge">Agent {agent}</span><br><br>'

            st.markdown(
                f'<span class="assistant-msg-marker"></span>\n\n{agent_badge}{response_text}',
                unsafe_allow_html=True,
            )
            scroll_to_bottom()

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": response_text,
            "agent": agent,
        }
    )

# Ancre de defilement
st.markdown('<div id="scroll-anchor"></div>', unsafe_allow_html=True)
