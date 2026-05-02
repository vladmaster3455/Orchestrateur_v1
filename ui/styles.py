import streamlit as st

def inject_styles():
    st.markdown("""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

      * { font-family: 'Inter', sans-serif; }

      /* App Background: Minimalist Dark */
      .stApp {
        background: #171717 !important;
        color: #ececec;
      }

      /* Sidebar Background */
      [data-testid="stSidebar"] {
        background-color: #0f0f0f !important;
        border-right: 1px solid #2a2a2a;
      }
      
      [data-testid="stSidebar"] * {
        color: #b0bec5;
      }

      /* Big Header */
      .aiverse-header {
        text-align: center;
        font-size: 3rem;
        font-weight: 700;
        margin-top: 10vh;
        margin-bottom: 1rem;
        background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
      }
      .aiverse-subheader {
        text-align: center;
        font-size: 1.1rem;
        color: #8da4ac;
        margin-bottom: 3rem;
      }

      /* Glowing Buttons (New Discussion) */
      button[kind="primary"] {
        background: linear-gradient(90deg, #00d2ff 0%, #3a7bd5 100%) !important;
        border: none !important;
        color: white !important;
        border-radius: 20px !important;
        font-weight: 700 !important;
        box-shadow: 0 4px 15px rgba(0, 210, 255, 0.4) !important;
        transition: all 0.3s ease !important;
      }
      button[kind="primary"] * {
        color: #ffffff !important;
      }
      button[kind="primary"]:hover {
        box-shadow: 0 6px 20px rgba(0, 210, 255, 0.6) !important;
        transform: translateY(-1px);
      }

      /* Secondary Buttons (Options) */
      button[kind="secondary"] {
        background: #212121 !important;
        border: 1px solid #333333 !important;
        color: #ececec !important;
        border-radius: 20px !important;
        transition: all 0.3s ease !important;
      }
      button[kind="secondary"]:hover {
        background: #2f2f2f !important;
        border-color: #444444 !important;
      }

      /* Chat Messages (Minimalist AI Style) */
      .stChatMessage {
        background-color: transparent !important;
        border: none !important;
        padding: 0.5rem 0 !important;
      }

      /* Hide ALL Avatars perfectly (Avatar is always the first child) */
      div[data-testid="stChatMessage"] > div:first-child {
          display: none !important;
          width: 0 !important;
          margin: 0 !important;
          padding: 0 !important;
      }

      /* User Message Container (Left aligned as requested) */
      div[data-testid="stChatMessage"]:has(.user-msg-marker) {
          display: flex !important;
          flex-direction: row !important;
      }
      
      div[data-testid="stChatMessage"]:has(.user-msg-marker) > div:nth-child(2) {
          display: flex !important;
          justify-content: flex-start !important;
          width: 100% !important;
      }

      /* User Bubble (Dark Grey) */
      div[data-testid="stChatMessage"]:has(.user-msg-marker) .stMarkdown {
          background-color: #2f2f2f !important;
          color: #ffffff !important;
          padding: 12px 18px !important;
          border-radius: 20px !important;
          display: inline-block !important;
          max-width: 80% !important;
          box-shadow: none !important;
          border: none !important;
          text-align: left !important;
      }

      /* Assistant Message Container (Left aligned) */
      div[data-testid="stChatMessage"]:has(.assistant-msg-marker) {
          display: flex !important;
          flex-direction: row !important;
      }

      /* Assistant Text (No Bubble, Plain text) */
      div[data-testid="stChatMessage"]:has(.assistant-msg-marker) .stMarkdown {
          background-color: transparent !important;
          color: #ececec !important;
          padding: 5px 10px !important;
          border-radius: 0 !important;
          display: inline-block !important;
          max-width: 90% !important;
          box-shadow: none !important;
          border: none !important;
      }

      /* Agent badges in chat */
      .agent-badge {
        display: inline-block;
        padding: 0.2rem 0.8rem;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
        background: rgba(0, 242, 254, 0.1);
        color: #00f2fe;
        border: 1px solid rgba(0, 242, 254, 0.3);
      }

      /* Chat Input */
      [data-testid="stChatInput"] {
        border: 1px solid #333333 !important;
        background-color: #212121 !important;
        border-radius: 20px !important;
      }
      [data-testid="stChatInput"]:focus-within {
        border-color: #555555 !important;
        box-shadow: 0 0 10px rgba(255, 255, 255, 0.05) !important;
      }

      /* Expander / Details */
      .streamlit-expanderHeader {
        background-color: transparent !important;
        color: #00f2fe !important;
        border: 1px solid #1c4b57 !important;
        border-radius: 12px !important;
      }

      /* Sidebar History Mock */
      .history-date {
        font-size: 0.75rem;
        color: #546e7a;
        margin-top: 1.5rem;
        margin-bottom: 0.5rem;
        text-transform: uppercase;
        letter-spacing: 1px;
      }
      .history-item {
        font-size: 0.85rem;
        color: #b0bec5;
        padding: 0.5rem 0;
        border-bottom: 1px solid #142a33;
        cursor: pointer;
        transition: color 0.2s ease;
      }
      .history-item:hover {
        color: #00f2fe;
      }

      /* Hide main menu and footer */
      #MainMenu {visibility: hidden;}
      footer {visibility: hidden;}

      /* --- Responsive Mobile Design --- */
      @media (max-width: 768px) {
        /* Reduce header size */
        .aiverse-header {
          font-size: 2.2rem !important;
          margin-top: 5vh !important;
        }
        .aiverse-subheader {
          font-size: 0.95rem !important;
          margin-bottom: 2rem !important;
        }

        /* Enlarge message bubbles slightly to use screen space better */
        div[data-testid="stChatMessage"]:has(.user-msg-marker) .stMarkdown {
          max-width: 95% !important;
          padding: 10px 14px !important;
        }

        div[data-testid="stChatMessage"]:has(.assistant-msg-marker) .stMarkdown {
          max-width: 100% !important;
        }

        /* Optimize chat input for small screens */
        [data-testid="stChatInput"] {
            border-radius: 15px !important;
            padding: 0.5rem !important;
        }
      }
    </style>
    """, unsafe_allow_html=True)
