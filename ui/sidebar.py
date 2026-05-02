import streamlit as st
from config import config

def render_sidebar():
    with st.sidebar:
        st.markdown("<h2 style='color: white; font-weight: 700;'>AIVerse</h2>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        new_chat_clicked = st.button("Nouvelle Discussion", use_container_width=True, type="primary")

        st.markdown("<br>", unsafe_allow_html=True)
        st.text_input("Rechercher", placeholder="Rechercher...", label_visibility="collapsed")
        st.markdown("<br>", unsafe_allow_html=True)

        selected_history_id = None
        history_items = st.session_state.get("chat_history", [])
        if history_items:
            st.markdown("**Historique**")
            for item in reversed(history_items):
                label = item.get("title", f"Conversation {item.get('id', '')}")
                if st.button(label, use_container_width=True, key=f"history_{item.get('id', '')}"):
                    selected_history_id = item.get("id")

    return {
        "new_chat": new_chat_clicked,
        "load_history_id": selected_history_id,
    }

