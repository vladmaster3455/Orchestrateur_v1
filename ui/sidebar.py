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
        




