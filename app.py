import streamlit as st
from pathlib import Path
from config import config
from ui.styles import inject_styles
from ui.sidebar import render_sidebar
from orchestrator import route  # Import moved to top to prevent cold start latency

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

# Render Sidebar
render_sidebar()

# --- Main Empty State (AIVerse Style) ----------------------------------------
if len(st.session_state.messages) == 0:
    st.markdown('<div class="aiverse-header">Tous vos outils favoris au même endroit</div>', unsafe_allow_html=True)
    st.markdown('<div class="aiverse-subheader">Si aucune option n\'est sélectionnée, l\'orchestrateur LangGraph choisira automatiquement le meilleur agent en fonction de votre requête.</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Agent Email", use_container_width=True, type="secondary"):
            st.session_state.messages.append({
                "role": "assistant",
                "content": "**Agent Email**\nJe suis spécialisé dans la rédaction et l'envoi de courriers électroniques. Donnez-moi l'adresse du destinataire et le contexte de votre message, et je me chargerai de rédiger un email professionnel et de l'envoyer pour vous.\n\n*Essayez : \"Envoie un email à direction@entreprise.com pour demander une réunion demain.\"*",
                "agent": "EMAIL"
            })
            st.rerun()
    with col2:
        if st.button("Agent RAG", use_container_width=True, type="secondary"):
            st.session_state.messages.append({
                "role": "assistant",
                "content": "**Agent RAG (Analyse Documentaire)**\nJe peux lire, comprendre et analyser vos documents (PDF, images, textes). Téléchargez un fichier via le trombone dans la barre de saisie, puis posez-moi n'importe quelle question sur son contenu. Je chercherai intelligemment la réponse dans vos données.\n\n*Essayez d'uploader un PDF puis demandez : \"Fais-moi un résumé des 3 points clés de ce document.\"*",
                "agent": "RAG"
            })
            st.rerun()
        if st.button("Agent Chat", use_container_width=True, type="secondary"):
            st.session_state.messages.append({
                "role": "assistant",
                "content": "**Agent Chat**\nJe suis le cerveau principal de l'Orchestrateur. Je suis là pour discuter, répondre à vos questions générales, faire de la traduction ou de la rédaction, et surtout, comprendre vos intentions pour passer le relais aux autres agents si nécessaire.\n\n*Essayez : \"Explique-moi comment fonctionne l'architecture LangGraph.\"*",
                "agent": "CHAT"
            })
            st.rerun()
    
    st.markdown("<br><br>", unsafe_allow_html=True)

# --- Historique du chat ------------------------------------------------------
for msg in st.session_state.messages:
    role = msg["role"]
    with st.chat_message(role):
        if role == "user":
            st.markdown(f'<span class="user-msg-marker"></span>\n\n{msg["content"]}', unsafe_allow_html=True)
        else:
            agent_badge = ""
            if "agent" in msg and msg["agent"] != "CHAT":
                agent_badge = f'<span class="agent-badge">Agent {msg["agent"]}</span><br><br>'
            st.markdown(f'<span class="assistant-msg-marker"></span>\n\n{agent_badge}{msg["content"]}', unsafe_allow_html=True)

# Afficher l'indicateur de document actif
if st.session_state.indexed_file:
    st.caption(f"**Document actif :** {st.session_state.indexed_file}")

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
                history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]]
                result = route(user_text, history)
            
            agent         = result["agent"]
            response_text = result["response"]
            explanation   = result.get("explanation", "")

            agent_badge = ""
            if agent != "CHAT":
                agent_badge = f'<span class="agent-badge">Agent {agent}</span><br><br>'

            st.markdown(f'<span class="assistant-msg-marker"></span>\n\n{agent_badge}{response_text}', unsafe_allow_html=True)

    st.session_state.messages.append({
        "role":    "assistant",
        "content": response_text,
        "agent":   agent if "agent" in dir() else "CHAT"
    })
