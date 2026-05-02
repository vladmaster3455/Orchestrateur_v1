import streamlit as st
import re
from pathlib import Path
from config import config
from ui.styles import inject_styles
from ui.sidebar import render_sidebar
from orchestrator import route, continue_pending_email, continue_pending_rag  # Import moved to top to prevent cold start latency

# --- Page config -------------------------------------------------------------
st.set_page_config(
    page_title="AIVerse Orchestrator",
    layout="centered",
    initial_sidebar_state="expanded",
)

# --- Point d'entrée léger pour Cron Jobs (Keep-Alive) ---
# URL à utiliser sur cron-job.org : https://votre-app.streamlit.app/?ping=1
if st.query_params.get("ping") == "1":
    st.write("OK - Serveur éveillé")
    st.stop()

# Inject custom CSS
inject_styles()

# --- Session state -----------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []
if "indexed_file" not in st.session_state:
    st.session_state.indexed_file = None
if "suggestion_prompt" not in st.session_state:
    st.session_state.suggestion_prompt = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "next_history_id" not in st.session_state:
    st.session_state.next_history_id = 1
if "pending_action" not in st.session_state:
    st.session_state.pending_action = None
if "active_agent" not in st.session_state:
    st.session_state.active_agent = "CHAT"


SYMBOL_FILTER_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA70-\U0001FAFF"
    "\u2600-\u26FF"
    "\u2700-\u27BF"
    "]",
    flags=re.UNICODE,
)


def sanitize_text(text: str) -> str:
    return SYMBOL_FILTER_PATTERN.sub("", text or "").strip()

def save_current_conversation():
    if not st.session_state.messages:
        return

    first_user_message = next(
        (m.get("content", "") for m in st.session_state.messages if m.get("role") == "user" and m.get("content")),
        "",
    )
    title = first_user_message.strip()[:40] if first_user_message else "Conversation sans titre"
    if not title:
        title = "Conversation sans titre"

    st.session_state.chat_history.append({
        "id": st.session_state.next_history_id,
        "title": title,
        "messages": [dict(m) for m in st.session_state.messages],
        "indexed_file": st.session_state.indexed_file,
        "pending_action": st.session_state.pending_action,
    })
    st.session_state.next_history_id += 1

# Render Sidebar
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
    selected = next((item for item in st.session_state.chat_history if item.get("id") == history_to_load), None)
    if selected:
        st.session_state.messages = [dict(m) for m in selected.get("messages", [])]
        st.session_state.indexed_file = selected.get("indexed_file")
        st.session_state.pending_action = selected.get("pending_action")
        st.rerun()

# --- Agent shortcuts ----------------------------------------------------------
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("Agent Email", use_container_width=True, type="secondary", key="agent_email_shortcut"):
        st.session_state.active_agent = "EMAIL"
        st.session_state.pending_action = {"agent": "EMAIL", "context": {}}
        st.session_state.messages.append({
            "role": "assistant",
            "content": "**Agent Email**\nJe suis specialise dans la redaction et l'envoi de courriers electroniques. Donnez-moi l'adresse du destinataire et le contexte de votre message, et je me chargerai de rediger un email professionnel et de l'envoyer pour vous.\n\n*Essayez : \"Envoie un email a direction@entreprise.com pour demander une reunion demain.\"*",
            "agent": "EMAIL"
        })
        st.rerun()
with col2:
    if st.button("Agent RAG", use_container_width=True, type="secondary", key="agent_rag_shortcut"):
        st.session_state.active_agent = "RAG"
        st.session_state.pending_action = {"agent": "RAG", "context": {}}
        st.session_state.messages.append({
            "role": "assistant",
            "content": "**Agent RAG (Analyse Documentaire)**\nJe peux lire, comprendre et analyser vos documents (PDF, images, textes). Telechargez un fichier via le trombone dans la barre de saisie, puis posez-moi n'importe quelle question sur son contenu. Je chercherai intelligemment la reponse dans vos donnees.\n\n*Essayez d'uploader un PDF puis demandez : \"Fais-moi un resume des 3 points cles de ce document.\"*",
            "agent": "RAG"
        })
        st.rerun()
with col3:
    if st.button("Agent Chat", use_container_width=True, type="secondary", key="agent_chat_shortcut"):
        st.session_state.active_agent = "CHAT"
        st.session_state.pending_action = None
        st.session_state.messages.append({
            "role": "assistant",
            "content": "**Agent Chat**\nJe suis le cerveau principal de l'Orchestrateur. Je suis la pour discuter, repondre a vos questions generales, faire de la traduction ou de la redaction, et surtout, comprendre vos intentions pour passer le relais aux autres agents si necessaire.\n\n*Essayez : \"Explique-moi comment fonctionne l'architecture LangGraph.\"*",
            "agent": "CHAT"
        })
        st.rerun()

# --- Main Empty State (AIVerse Style) ----------------------------------------
if len(st.session_state.messages) == 0:
    st.markdown('<div class="aiverse-header">Tous vos outils favoris au même endroit</div>', unsafe_allow_html=True)
    st.markdown('<div class="aiverse-subheader">Si aucune option n\'est sélectionnée, l\'orchestrateur LangGraph choisira automatiquement le meilleur agent en fonction de votre requête.</div>', unsafe_allow_html=True)

    st.markdown("<br><br>", unsafe_allow_html=True)

# --- Historique du chat ------------------------------------------------------
for msg in st.session_state.messages:
    role = msg["role"]
    msg_content = sanitize_text(msg.get("content", ""))
    with st.chat_message(role):
        if role == "user":
            st.markdown(f'<span class="user-msg-marker"></span>\n\n{msg_content}', unsafe_allow_html=True)
        else:
            agent_badge = ""
            if "agent" in msg and msg["agent"] != "CHAT":
                agent_badge = f'<span class="agent-badge">Agent {msg["agent"]}</span><br><br>'
            st.markdown(f'<span class="assistant-msg-marker"></span>\n\n{agent_badge}{msg_content}', unsafe_allow_html=True)

# --- Input utilisateur -------------------------------------------------------
prompt = st.chat_input("Message Ai Chat...", accept_file=True, file_type=["pdf", "txt", "png", "jpg", "jpeg"])

user_text = None
uploaded_files = []

if st.session_state.suggestion_prompt:
    user_text = st.session_state.suggestion_prompt
    st.session_state.suggestion_prompt = None
elif prompt:
    if hasattr(prompt, "text"):
        user_text = prompt.text
        uploaded_files = prompt.files or []
    elif isinstance(prompt, dict):
        user_text = prompt.get("text", "")
        uploaded_files = prompt.get("files", [])
    else:
        user_text = str(prompt)

if user_text or uploaded_files:
    user_text = sanitize_text(user_text)

    lower_text = user_text.lower()
    if "agent rag" in lower_text:
        st.session_state.active_agent = "RAG"
        st.session_state.pending_action = {"agent": "RAG", "context": {}}
    elif "agent email" in lower_text or "agent mail" in lower_text:
        st.session_state.active_agent = "EMAIL"
        st.session_state.pending_action = {"agent": "EMAIL", "context": {}}
    elif "agent chat" in lower_text:
        st.session_state.active_agent = "CHAT"
        st.session_state.pending_action = None

    if uploaded_files:
        uploaded = uploaded_files[0]
        docs_dir = Path("documents")
        docs_dir.mkdir(exist_ok=True)
        file_path = docs_dir / uploaded.name
        file_path.write_bytes(uploaded.read())
        
        with st.spinner(f"Analyse de {uploaded.name} en cours..."):
            from agents.rag_agent import build_index_from_file
            result = build_index_from_file(str(file_path))
            if result["success"]:
                st.session_state.indexed_file = uploaded.name
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": result["response"],
                    "agent": "RAG"
                })
                pending = st.session_state.pending_action
                if pending and pending.get("agent") == "RAG":
                    follow_up = continue_pending_rag("", pending.get("context", {}))
                    st.session_state.pending_action = follow_up.get("pending_action")
                    st.session_state.active_agent = "RAG"
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": sanitize_text(follow_up.get("response", "")),
                        "agent": "RAG",
                    })
            else:
                st.error(result["error"])
                st.stop()
        
        if not user_text:
            st.rerun()

    st.session_state.messages.append({"role": "user", "content": user_text})
    
    with st.chat_message("user"):
        st.markdown(f'<span class="user-msg-marker"></span>\n\n{user_text}', unsafe_allow_html=True)

    with st.chat_message("assistant"):
        if not config.ANTHROPIC_API_KEY:
            st.error("**Erreur : ANTHROPIC_API_KEY non configurée.**")
        else:
            with st.spinner("Traitement via LangGraph..."):
                pending = st.session_state.pending_action
                if pending and pending.get("agent") == "EMAIL":
                    result = continue_pending_email(user_text, pending.get("context", {}))
                elif pending and pending.get("agent") == "RAG":
                    result = continue_pending_rag(user_text, pending.get("context", {}))
                elif st.session_state.active_agent == "EMAIL":
                    result = continue_pending_email(user_text, {})
                elif st.session_state.active_agent == "RAG":
                    result = continue_pending_rag(user_text, {})
                else:
                    history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]]
                    result = route(user_text, history)
            
            agent         = result["agent"]
            response_text = sanitize_text(result["response"])
            explanation   = result.get("explanation", "")
            st.session_state.pending_action = result.get("pending_action")
            if agent in ["EMAIL", "RAG", "CHAT"]:
                st.session_state.active_agent = agent

            agent_badge = ""
            if agent != "CHAT":
                agent_badge = f'<span class="agent-badge">Agent {agent}</span><br><br>'

            st.markdown(f'<span class="assistant-msg-marker"></span>\n\n{agent_badge}{response_text}', unsafe_allow_html=True)

    st.session_state.messages.append({
        "role":    "assistant",
        "content": response_text,
        "agent":   agent if "agent" in dir() else "CHAT"
    })
