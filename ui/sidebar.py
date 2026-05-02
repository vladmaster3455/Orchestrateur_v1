import streamlit as st
from config import config

def render_sidebar():
    with st.sidebar:
        st.markdown("<h2 style='color: white; font-weight: 700; display: flex; align-items: center; gap: 10px;'><span style='color:#00f2fe;'>◖</span> AIVerse</h2>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("Nouvelle Discussion", use_container_width=True, type="primary"):
            st.session_state.messages = []
            st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        st.text_input("Rechercher", placeholder="Rechercher...", label_visibility="collapsed")
        



        # Status des cles API
        st.markdown("<div style='margin-top: 5rem;'>", unsafe_allow_html=True)
        
        gkey = config.ANTHROPIC_API_KEY
        bkey = config.BREVO_API_KEY

        def status_html(ok, label):
            cls = "#00f2fe" if ok else "#ef4444"
            return f'<div style="margin-bottom: 5px; font-size: 0.8rem;"><span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:{cls}; margin-right:6px;"></span> {label}</div>'

        st.markdown(status_html(bool(gkey), "Claude API (LangGraph)"), unsafe_allow_html=True)
        st.markdown(status_html(bool(bkey), "Brevo API"), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
