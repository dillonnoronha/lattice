"""Presentation styles that inherit the user's native Streamlit theme."""
import streamlit as st


def inject_styles() -> None:
    st.markdown("""<style>
    .stMainBlockContainer { max-width:1280px; padding-top:2.5rem; padding-bottom:4rem; }
    h1,h2,h3 { letter-spacing:-.035em; }
    h1 {font-size:2.2rem!important; line-height:1.18!important;}
    [data-testid="stSidebar"] {border-right:1px solid color-mix(in srgb,currentColor 10%,transparent);}
    [data-testid="stMetric"] {padding:1.25rem; border:1px solid color-mix(in srgb,currentColor 14%,transparent); border-radius:16px; background:color-mix(in srgb,#9c6d50 5%,transparent);}
    [data-testid="stMetricValue"] {font-weight:700; letter-spacing:-.04em;}
    [data-testid="stExpander"] details {border-radius:12px;}
    [data-testid="stForm"], [data-testid="stVerticalBlockBorderWrapper"] {border-radius:16px;}
    [data-testid="stButton"] button, [data-testid="stDownloadButton"] button, [data-testid="stFormSubmitButton"] button {border-radius:10px; min-height:2.6rem;}
    [data-testid="stDataFrame"] {border-radius:12px; overflow:hidden;}
    button:focus-visible,input:focus-visible,textarea:focus-visible {outline:3px solid #a56e4c!important;outline-offset:3px;}
    .formula {font-family:ui-monospace,monospace; font-weight:650;}
    @media (max-width:640px) {.stMainBlockContainer {padding-top:1.5rem;}h1 {font-size:1.7rem!important;}}
    @media (prefers-reduced-motion:reduce) {*,*::before,*::after {animation:none!important;transition:none!important;scroll-behavior:auto!important;}}
    </style>""", unsafe_allow_html=True)
