"""
Meridian Health Systems - Document Assistant
(built with Streamlit + LlamaIndex + Chroma + Ollama)

Install / upgrade the UI dependencies first (streamlit >= 1.42 is required for st.feedback):
    pip install -U streamlit plotly pandas altair

CHANGE 8: calculations & statistics support needs one more package:
    pip install -U llama-index-experimental

Run:
    streamlit run app.py
"""

import ast
import csv
import html
import operator
import os
import re
import threading
import time
from datetime import datetime

import altair as alt
import chromadb
import pandas as pd
import plotly.express as px
import streamlit as st
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.core.postprocessor import SentenceTransformerRerank

# CHANGE 8: PandasQueryEngine lets the assistant run real pandas computations
# (totals, averages, comparisons) over indexed spreadsheets instead of the
# LLM estimating numbers from text. It ships in a separate package, and it
# works by having the LLM generate and execute pandas code against the
# DataFrame, so only point it at data you trust (see load_structured_datasets
# below) and keep it off files it shouldn't touch.
try:
    from llama_index.experimental.query_engine import PandasQueryEngine
    PANDAS_QUERY_ENGINE_AVAILABLE = True
except ImportError:
    PandasQueryEngine = None
    PANDAS_QUERY_ENGINE_AVAILABLE = False

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------
COMPANY_NAME = "Meridian Health Systems"
APP_TITLE = "Document Assistant"
CHROMA_DIR = "chroma_db"
COLLECTION_NAME = "org_docs"
DEPARTMENTS = ["All", "HR", "Finance", "Legal", "Customer_Service", "IT"]

# CHANGE 8: drop CSV/XLSX files here to make them queryable for calculations
# and statistics. Filename convention: <department>__<description>.csv
# (e.g. finance__q1_expenses.csv) - the part before "__" tags the department.
STRUCTURED_DATA_DIR = "structured_data"

FEEDBACK_FILE = "feedback_log.csv"
FEEDBACK_FIELDS = [
    "timestamp", "message_id", "department_filter", "question",
    "answer", "sources", "rating", "comment",
]

# CHANGE 4/6: real usage logs, persisted to disk so the dashboard shows
# genuine activity instead of hardcoded sample data.
QUERY_LOG_FILE = "query_log.csv"
QUERY_LOG_FIELDS = ["timestamp", "question", "department"]

METRICS_FILE = "query_metrics.csv"
METRICS_FIELDS = ["timestamp", "department", "retrieval_s", "llm_s", "avg_relevance"]

# CHANGE 1: system prompt for the LLM. This is the fix for incomplete answers
# (e.g. only one row of a multi-row leave-policy table being returned) and
# for reducing hallucination on out-of-scope questions.
SYSTEM_PROMPT = (
    "You are a helpful internal assistant for Meridian Health Systems employees. "
    "Answer using ONLY the retrieved document context provided to you. "
    "If a question relates to a table, list, or set of categories (for example, leave types, "
    "expense categories, or asset types), include ALL relevant rows or categories from that "
    "table in your answer, not just the first or best match. "
    "If the context does not contain the answer, do not guess or invent details. Instead: "
    "(1) say in one sentence that the specific information isn't in the available documents, "
    "(2) briefly mention any closely related information that IS in the context, if there is any, "
    "and (3) suggest which department (HR, Finance, Legal, IT, or Customer Service) the employee "
    "should contact. Keep this short and friendly."
)


# Relevance badge thresholds (tune these to your embedding model's score range)
SCORE_STRONG = 0.50
SCORE_OK = 0.35
CARDS_PER_ROW = 3

# Corporate department palette (muted, print-safe colours)
DEPT_COLORS = {
    "HR": "#0F6E5C",
    "Finance": "#1D4ED8",
    "Legal": "#B45309",
    "Customer_Service": "#4C51BF",
    "IT": "#9F1239",
}
FALLBACK_COLOR = "#64748B"

# Simple line-art icons shown on source cards, one per department, in the
# style of a corporate site rather than emoji. "{size}" is filled in at
# render time so the same icon works small (card header) or large (banner).
DEPT_ICONS = {
    "HR": """<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" stroke="#FFFFFF"
              stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="9" cy="8" r="3"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/>
              <circle cx="17" cy="7" r="2.4"/><path d="M15.5 20c.2-2.6 2-4.7 4.5-5.2"/>
            </svg>""",
    "Finance": """<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" stroke="#FFFFFF"
              stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>
            </svg>""",
    "Legal": """<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" stroke="#FFFFFF"
              stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 3v18M5 7l-3 6a3 3 0 0 0 6 0l-3-6ZM19 7l-3 6a3 3 0 0 0 6 0l-3-6Z"/>
              <path d="M4 7h5M15 7h5M8 21h8"/>
            </svg>""",
    "Customer_Service": """<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" stroke="#FFFFFF"
              stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 13v-1a8 8 0 0 1 16 0v1"/>
              <rect x="2.5" y="13" width="4" height="6" rx="1.3"/>
              <rect x="17.5" y="13" width="4" height="6" rx="1.3"/>
              <path d="M19.5 19v.5a3 3 0 0 1-3 3H13"/>
            </svg>""",
    "IT": """<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" stroke="#FFFFFF"
              stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 3l7 3v5c0 4.5-3 7.7-7 10-4-2.3-7-5.5-7-10V6l7-3Z"/>
              <path d="m9 12 2 2 4-4"/>
            </svg>""",
}
DEPT_ICON_FALLBACK = """<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" stroke="#FFFFFF"
              stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
              <path d="M6 3h9l4 4v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z"/>
              <path d="M14 3v4h4M8 12h7M8 16h7"/>
            </svg>"""

# Quick starter prompts: {button label: question that is sent}
STARTERS = {
    "👔 View dress code policy": "What is the dress code policy?",
    "🏖️ How do I request leave?": "How do I request annual leave?",
    "💳 Expense reimbursement": "What is the process for expense reimbursement?",
    "🔐 Password requirements": "What are the password and security requirements?",
}

# Footer "Quick Links" -> the question asked when a link is clicked
FOOTER_TOPICS = {
    "Employee Handbook": "Can you give me a summary of what's in the Employee Handbook?",
    "Code of Conduct": "What does the Code of Conduct cover?",
    "IT Security Policy": "What is the IT security and password policy?",
    "Benefits & Leave": "What benefits and leave am I entitled to?",
}

# Sample data used only when the vector store has no metadata yet
DEMO_INVENTORY = pd.DataFrame(
    [
        ("hr_employee_handbook.md", "HR", 42),
        ("hr_code_of_conduct.md", "HR", 18),
        ("finance_expense_policy.md", "Finance", 25),
        ("finance_budget_guidelines.md", "Finance", 14),
        ("legal_data_privacy.md", "Legal", 21),
        ("it_security_policy.md", "IT", 30),
        ("it_acceptable_use.md", "IT", 12),
        ("cs_service_standards.md", "Customer_Service", 20),
    ],
    columns=["file", "department", "chunks"],
)

st.set_page_config(page_title=f"{COMPANY_NAME} | {APP_TITLE}", page_icon="🏥", layout="wide")

# ----------------------------------------------------------------------------
# Custom CSS
# ----------------------------------------------------------------------------
APP_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {
  --ink: #12283C;
  --slate: #4B5A6B;
  --muted: #8B99A8;
  --line: #E2E8EE;
  --panel: #F5F9F8;
  --brand: #0F6E5C;
  --brand-dark: #0B5445;
  --brand-soft: #E7F5F1;
  --navy: #12283C;
  --shadow: 0 1px 2px rgba(18, 40, 60, .04), 0 8px 20px -14px rgba(18, 40, 60, .18);
  --shadow-lg: 0 6px 14px rgba(18, 40, 60, .06), 0 18px 32px -18px rgba(18, 40, 60, .28);
}

.stApp, .stApp p, .stApp label, .stApp button, .stApp input, .stApp textarea {
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
}
.stApp { background: #FFFFFF; }
footer { visibility: hidden; }
.block-container { padding-top: 2rem; max-width: 1180px; }

/* ---- Header / hero ---------------------------------------------------- */
.hero {
  background: var(--panel); border: 1px solid var(--line); border-top: 4px solid var(--brand);
  border-radius: 12px; padding: 1.75rem 2rem; margin-bottom: 1.4rem;
}
.hero-eyebrow {
  display: inline-block; font-size: .72rem; font-weight: 700; letter-spacing: .08em;
  text-transform: uppercase; color: var(--brand-dark); background: var(--brand-soft);
  padding: .3rem .75rem; border-radius: 4px; margin-bottom: .8rem;
}
.hero h1 {
  font-size: 1.9rem; font-weight: 800; letter-spacing: -0.02em; color: var(--ink);
  margin: 0 0 .35rem 0; padding: 0; line-height: 1.2;
}
.hero p { color: var(--slate); margin: 0 0 .9rem 0; max-width: 64ch; line-height: 1.6; font-size: .97rem; }
.chip {
  display: inline-block; padding: .2rem .7rem; margin: 0 .4rem .35rem 0;
  border-radius: 4px; background: #FFFFFF; border: 1px solid var(--line);
  font-size: .76rem; color: var(--slate); font-weight: 600;
}
.brand {
  font-size: 1.15rem; font-weight: 800; letter-spacing: -0.01em; color: var(--ink);
  margin-bottom: .1rem;
}
.brand-sub { font-size: .74rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--brand); margin-bottom: .6rem; }
.sidebar-logo { display: flex; align-items: center; gap: .65rem; margin-bottom: .3rem; }
.sidebar-logo-badge {
  flex: none; width: 2.5rem; height: 2.5rem; border-radius: 8px; background: var(--brand);
  color: #FFFFFF; font-weight: 800; font-size: .95rem; letter-spacing: -0.02em;
  display: flex; align-items: center; justify-content: center;
}
.sidebar-logo .brand { margin-bottom: .1rem; }
.sidebar-logo .brand-sub { margin-bottom: 0; }
.sidebar-footer {
  margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid var(--line);
  font-size: .72rem; color: var(--muted); line-height: 1.6;
}
.sidebar-footer-links { color: var(--slate); font-weight: 600; margin-bottom: .4rem; }

/* ---- Tabs ----------------------------------------------------------- */
[data-baseweb="tab-list"] { border-bottom: 1px solid var(--line); gap: 1.5rem; }
button[data-baseweb="tab"] {
  font-weight: 600; font-size: .95rem; padding: .65rem .1rem; color: var(--slate);
}
button[data-baseweb="tab"][aria-selected="true"] { color: var(--brand-dark); font-weight: 700; }
[data-baseweb="tab-highlight"] { background-color: var(--brand) !important; height: 3px; border-radius: 2px; }

/* ---- Chat bubbles --------------------------------------------------- */
[data-testid="stChatMessage"] {
  background: #FFFFFF; border: 1px solid var(--line); border-radius: 12px;
  padding: 1rem 1.2rem; margin-bottom: .95rem; box-shadow: var(--shadow);
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]),
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
  background: var(--panel); border-color: var(--line);
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]),
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
  border-left: 3px solid var(--brand);
}
[data-testid="stChatMessageAvatarUser"], [data-testid="chatAvatarIcon-user"] { background: var(--navy) !important; }
[data-testid="stChatMessageAvatarAssistant"], [data-testid="chatAvatarIcon-assistant"] { background: var(--brand) !important; }
[data-testid="stChatInput"] { border-radius: 10px; box-shadow: var(--shadow); border: 1px solid var(--line) !important; }
[data-testid="stChatInput"]:focus-within { border-color: var(--brand) !important; }

/* ---- Buttons -------------------------------------------------------- */
.stButton button { border-radius: 6px; font-weight: 600; transition: background .15s, border-color .15s, color .15s; }
.stButton button[kind="primary"], .stButton button[data-testid="stBaseButton-primary"] {
  background: var(--brand); border: 1px solid var(--brand); color: #FFFFFF;
}
.stButton button[kind="primary"]:hover, .stButton button[data-testid="stBaseButton-primary"]:hover {
  background: var(--brand-dark); border-color: var(--brand-dark); color: #FFFFFF;
}
.stButton button[kind="secondary"], .stButton button[data-testid="stBaseButton-secondary"] {
  background: #FFFFFF; border: 1px solid #CBD5E1; color: var(--ink);
}
.stButton button[kind="secondary"]:hover, .stButton button[data-testid="stBaseButton-secondary"]:hover {
  border-color: var(--brand); color: var(--brand-dark); background: var(--brand-soft);
}
/* Quick-start pills */
.st-key-starters button {
  border: 1px solid var(--line) !important; color: var(--brand-dark) !important;
  background: #FFFFFF !important; padding: .5rem 1.1rem; white-space: normal; line-height: 1.35;
  box-shadow: var(--shadow); border-radius: 8px !important;
}
.st-key-starters button:hover { background: var(--brand-soft) !important; border-color: var(--brand) !important; }
.starter-hint { color: var(--slate); font-size: .9rem; font-weight: 600; margin: 1.5rem 0 .6rem 0; }

/* ---- Expanders and metrics ------------------------------------------ */
[data-testid="stExpander"] details {
  background: #FFFFFF; border: 1px solid var(--line); border-radius: 10px; box-shadow: var(--shadow);
}
[data-testid="stExpander"] summary { font-weight: 700; }
[data-testid="stMetric"] {
  background: #FFFFFF; border: 1px solid var(--line); border-radius: 10px;
  padding: .7rem .85rem; box-shadow: var(--shadow); border-top: 3px solid var(--brand);
}
[data-testid="stMetricValue"] { color: var(--ink); font-weight: 700; }
section[data-testid="stSidebar"] { background: var(--panel); border-right: 1px solid var(--line); }
section[data-testid="stSidebar"] [data-testid="stMetric"] { padding: .5rem .55rem; border-radius: 8px; }
section[data-testid="stSidebar"] [data-testid="stMetricValue"] { font-size: 1.05rem; font-weight: 700; }
section[data-testid="stSidebar"] [data-testid="stMetricLabel"] p { font-size: .72rem; color: var(--slate); font-weight: 600; }

/* ---- Source cards ---------------------------------------------------- */
div[class*="st-key-srccard_"] {
  background: #FFFFFF; border: 1px solid var(--line); border-radius: 10px;
  padding: .9rem 1rem; box-shadow: var(--shadow); transition: box-shadow .15s ease;
  overflow: hidden;
}
div[class*="st-key-srccard_"]:hover { box-shadow: var(--shadow-lg); }
.src-head { display: flex; align-items: center; gap: .6rem; margin-bottom: .5rem; }
.src-photo {
  height: 60px; margin: -.9rem -1rem .75rem -1rem; border-radius: 10px 10px 0 0;
  display: flex; align-items: center; justify-content: center;
}
.src-name { font-weight: 700; font-size: .88rem; color: var(--ink); word-break: break-all; line-height: 1.25; }
.badge { display: inline-block; padding: .16rem .65rem; border-radius: 4px; font-size: .72rem; font-weight: 700; margin: 0 0 .35rem 0; }
.src-excerpt { font-size: .78rem; color: var(--slate); line-height: 1.5; margin-top: .3rem; }

/* ---- Recolour Streamlit's own widgets to the brand colour -----------
   These override Streamlit's default theme (normally red/purple) so a
   separate .streamlit/config.toml file isn't needed. */
div[data-baseweb="slider"] div[role="slider"] {
  background-color: var(--brand) !important; border-color: var(--brand) !important;
  box-shadow: 0 0 0 .2rem var(--brand-soft) !important;
}
div[data-baseweb="slider"] > div > div > div { background: var(--brand) !important; }
div[data-baseweb="slider"] > div > div:first-child { background: var(--line) !important; }
[data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"] { color: var(--slate) !important; }
[data-testid="stThumbValue"] { color: var(--brand-dark) !important; font-weight: 700 !important; }
[data-baseweb="radio"] div:first-child, [data-baseweb="checkbox"] div:first-child { border-color: var(--muted) !important; }
[data-baseweb="radio"] div:first-child:has(input:checked), [data-baseweb="checkbox"] div:first-child:has(input:checked) {
  background-color: var(--brand) !important; border-color: var(--brand) !important;
}
[data-testid="stSpinner"] > div { border-top-color: var(--brand) !important; }
[data-testid="stProgress"] > div > div > div { background-color: var(--brand) !important; }
.stApp a { color: var(--brand-dark); }
::selection { background: var(--brand-soft); }
input:focus, textarea:focus, select:focus { outline-color: var(--brand) !important; }

/* ---- Site footer ------------------------------------------------------ */
.st-key-site_footer {
  background: var(--navy) !important; color: #E2E8F0; border-radius: 12px;
  padding: 1.9rem 2rem 1.1rem; margin-top: 2rem;
}
.footer-brand { font-weight: 800; font-size: 1.05rem; color: #FFFFFF; margin-bottom: .5rem; }
.footer-heading {
  font-weight: 700; font-size: .78rem; text-transform: uppercase; letter-spacing: .06em;
  color: #FFFFFF; opacity: .85; margin-bottom: .65rem;
}
.st-key-site_footer p { color: #B9C4D0; font-size: .84rem; line-height: 1.65; margin: 0 0 .5rem 0; }
.st-key-site_footer a { color: #B9C4D0; text-decoration: none; }
.st-key-site_footer a:hover { color: #FFFFFF; text-decoration: underline; }
/* Quick-link buttons styled to look like a footer link, not a button */
.st-key-site_footer .stButton button {
  background: transparent !important; border: none !important; box-shadow: none !important;
  color: #B9C4D0 !important; padding: 0 0 .55rem 0 !important; margin: 0 !important;
  font-weight: 500 !important; font-size: .84rem !important; text-align: left !important;
  width: auto !important; border-radius: 0 !important; display: block;
}
.st-key-site_footer .stButton button p { color: inherit !important; font-size: .84rem !important; }
.st-key-site_footer .stButton button:hover { color: #FFFFFF !important; text-decoration: underline; transform: none !important; }
.st-key-site_footer .stButton { margin-bottom: 0 !important; }
.footer-bottom {
  border-top: 1px solid rgba(255,255,255,.14); margin-top: 1.4rem; padding-top: .9rem;
  font-size: .76rem; color: #8CA0B3;
}
</style>
"""
st.markdown(APP_CSS, unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# Retrieval resources
# ----------------------------------------------------------------------------
@st.cache_resource
def load_resources():
    Settings.embed_model = OllamaEmbedding(model_name="nomic-embed-text")
    Settings.llm = Ollama(
        model="gpt-oss:20b-cloud",
        request_timeout=120.0,
        context_window=8192,
        system_prompt=SYSTEM_PROMPT,
    )

    reranker = SentenceTransformerRerank(
        model="cross-encoder/ms-marco-MiniLM-L-6-v2",
        top_n=6,
    )

    # CHANGE 8: a second LLM handle with NO system prompt. The main Settings.llm
    # above has SYSTEM_PROMPT baked in ("you are a helpful internal assistant,
    # answer using only retrieved context..."), which is wrong context for the
    # narrow, single-word/single-expression prompts the routing and calculation
    # steps below send - this keeps those two jobs from interfering with each other.
    utility_llm = Ollama(
        model="gpt-oss:20b-cloud",
        request_timeout=90.0,
        context_window=8192,
    )

    chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
    chroma_collection = chroma_client.get_or_create_collection(COLLECTION_NAME)
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
    return VectorStoreIndex.from_vector_store(vector_store), chroma_collection, reranker, utility_llm

index, chroma_collection, reranker, utility_llm = load_resources()


@st.cache_data(ttl=300, show_spinner=False)
def load_inventory(_collection) -> pd.DataFrame:
    """One row per indexed file with its department and chunk count."""
    try:
        metas = _collection.get(include=["metadatas"]).get("metadatas") or []
    except Exception:
        metas = []
    rows = [
        {"file": m.get("file_name", "unknown"), "department": m.get("department", "unknown")}
        for m in metas
        if m
    ]
    if not rows:
        return pd.DataFrame(columns=["file", "department", "chunks"])
    df = pd.DataFrame(rows)
    return df.groupby(["file", "department"], as_index=False).size().rename(columns={"size": "chunks"})


inventory = load_inventory(chroma_collection)


# CHANGE 8: structured data for calculations/statistics, kept separate from
# the Chroma text index. Anything dropped in STRUCTURED_DATA_DIR as a CSV or
# XLSX file becomes queryable with real pandas math instead of LLM guesswork.
@st.cache_resource
def load_structured_datasets():
    datasets = {}
    if not PANDAS_QUERY_ENGINE_AVAILABLE or not os.path.isdir(STRUCTURED_DATA_DIR):
        return datasets
    for fname in sorted(os.listdir(STRUCTURED_DATA_DIR)):
        path = os.path.join(STRUCTURED_DATA_DIR, fname)
        try:
            if fname.endswith(".csv"):
                df = pd.read_csv(path)
            elif fname.endswith((".xlsx", ".xls")):
                df = pd.read_excel(path)
            else:
                continue
        except Exception as exc:
            print(f"[Document Assistant] could not load structured file {fname}: {exc}")
            continue
        dept = fname.split("__")[0] if "__" in fname else "unknown"
        datasets[fname] = {"df": df, "department": dept}
    return datasets


structured_datasets = load_structured_datasets()


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def pretty(dept: str) -> str:
    return str(dept).replace("_", " ")


def dept_color(dept: str) -> str:
    return DEPT_COLORS.get(dept, FALLBACK_COLOR)


def dept_icon(dept: str, size: int = 18) -> str:
    return DEPT_ICONS.get(dept, DEPT_ICON_FALLBACK).format(size=size)


def score_style(score: float):
    """Return (label, text colour, background colour) for a relevance badge."""
    if score >= SCORE_STRONG:
        return "Strong", "#166534", "#DCFCE7"
    if score >= SCORE_OK:
        return "Moderate", "#92400E", "#FEF3C7"
    return "Weak", "#475569", "#E2E8F0"


def fmt_seconds(value) -> str:
    return "-" if value is None else f"{value:.2f}s"


def show_altair(chart, key: str):
    """Stretch an Altair chart to full width on both old and new Streamlit versions."""
    try:
        st.altair_chart(chart, width="stretch", key=key)
    except TypeError:
        st.altair_chart(chart, use_container_width=True, key=key)


@st.cache_resource
def feedback_lock():
    return threading.Lock()


def sanitize_cell(value) -> str:
    """Flatten newlines and neutralise spreadsheet formula injection before writing to CSV."""
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    if text[:1] in ("=", "+", "-", "@", "\t"):
        text = "'" + text
    return text[:2000]


def log_feedback(row: dict):
    with feedback_lock():
        is_new = not os.path.exists(FEEDBACK_FILE) or os.path.getsize(FEEDBACK_FILE) == 0
        with open(FEEDBACK_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FEEDBACK_FIELDS)
            if is_new:
                writer.writeheader()
            writer.writerow({k: sanitize_cell(row.get(k, "")) for k in FEEDBACK_FIELDS})


# CHANGE 4: persist every question asked, across restarts, so the dashboard
# can chart real usage instead of a hardcoded sample.
def log_query(question: str, dept: str):
    with feedback_lock():
        is_new = not os.path.exists(QUERY_LOG_FILE) or os.path.getsize(QUERY_LOG_FILE) == 0
        with open(QUERY_LOG_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=QUERY_LOG_FIELDS)
            if is_new:
                writer.writeheader()
            writer.writerow({
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "question": sanitize_cell(question),
                "department": dept,
            })


@st.cache_data(ttl=30, show_spinner=False)
def load_query_log() -> pd.DataFrame:
    if not os.path.exists(QUERY_LOG_FILE):
        return pd.DataFrame(columns=QUERY_LOG_FIELDS)
    try:
        return pd.read_csv(QUERY_LOG_FILE)
    except Exception:
        return pd.DataFrame(columns=QUERY_LOG_FIELDS)


# CHANGE 6: persist retrieval/LLM timing and average relevance for every
# answer, so the dashboard can show a real performance trend.
def log_metrics(dept: str, retrieval_s: float, llm_s, avg_relevance: float):
    with feedback_lock():
        is_new = not os.path.exists(METRICS_FILE) or os.path.getsize(METRICS_FILE) == 0
        with open(METRICS_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=METRICS_FIELDS)
            if is_new:
                writer.writeheader()
            writer.writerow({
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "department": dept,
                "retrieval_s": round(retrieval_s, 3) if retrieval_s is not None else "",
                "llm_s": round(llm_s, 3) if llm_s else "",
                "avg_relevance": round(avg_relevance, 3) if avg_relevance else "",
            })


# ----------------------------------------------------------------------------
# Session state
# ----------------------------------------------------------------------------
st.session_state.setdefault("messages", [])
st.session_state.setdefault("msg_counter", 0)
st.session_state.setdefault("metrics", {"retrieval": None, "llm": None})
st.session_state.setdefault("feedback_status", {})
st.session_state.setdefault("query_log", [])


def queue_prompt(question: str):
    st.session_state.pending_prompt = question


def clear_chat():
    st.session_state.messages = []


def submit_feedback(mid: int):
    comment = st.session_state.get(f"fbtext_{mid}", "").strip()
    msg = next((m for m in st.session_state.messages if m["id"] == mid), None)
    if not comment or msg is None:
        return
    try:
        log_feedback(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "message_id": mid,
                "department_filter": msg.get("department", ""),
                "question": msg.get("question", ""),
                "answer": msg.get("content", ""),
                "sources": "; ".join(s["file"] for s in msg.get("sources", [])),
                "rating": "thumbs_down",
                "comment": comment,
            }
        )
        st.session_state.feedback_status[mid] = "saved"
    except OSError:
        st.session_state.feedback_status[mid] = "error"


def render_scoreboard(slot):
    docs = 0 if inventory.empty else len(inventory)
    m = st.session_state.metrics
    with slot.container():
        c1, c2, c3 = st.columns(3)
        c1.metric("Docs", docs, help="Documents indexed in the vector store.")
        c2.metric("Search time", fmt_seconds(m["retrieval"]), help="Time spent searching your documents for the last question.")
        c3.metric("Response time", fmt_seconds(m["llm"]), help="Time spent writing the last answer.")


# ----------------------------------------------------------------------------
# Sidebar
# ----------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        "<div class='sidebar-logo'>"
        "<span class='sidebar-logo-badge'>MH</span>"
        f"<div><div class='brand'>{html.escape(APP_TITLE)}</div>"
        f"<div class='brand-sub'>{html.escape(COMPANY_NAME)}</div></div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.caption("Answers and sources drawn from your company's policy documents.")

    scoreboard_slot = st.empty()
    render_scoreboard(scoreboard_slot)

    with st.expander("🔍 Search Settings", expanded=True):
        department = st.selectbox(
            "Filter by department",
            DEPARTMENTS,
            format_func=pretty,
            help="Only search documents from this department. Choose 'All' to search everything.",
        )
        top_k = st.slider(
            "Number of sources to retrieve",
            1, 10, 5,
            help="How many document excerpts are used to write each answer. More sources can give "
                 "fuller answers but are slower and can add noise.",
        )
        # CHANGE 8: lets the assistant do arithmetic and pull totals/averages
        # from indexed spreadsheets, instead of only searching document text.
        enable_calc = st.checkbox(
            "Enable calculations & statistics",
            value=True,
            help="Let the assistant do arithmetic on numbers in your question, and compute totals, "
                 "averages, or comparisons from indexed spreadsheets. Adds a short routing step "
                 "(roughly 1-2s) before each answer.",
        )
        if enable_calc and not structured_datasets:
            st.caption("No files in structured_data/ yet - direct calculations still work, "
                       "but spreadsheet lookups won't until you add some.")

    st.button("Clear chat history", on_click=clear_chat, help="Remove all messages from this session.")

    st.markdown(
        "<div class='sidebar-footer'>"
        "<div class='sidebar-footer-links'>Employee Handbook &nbsp;·&nbsp; IT Help Desk &nbsp;·&nbsp; Contact HR</div>"
        f"<div>© 2026 {html.escape(COMPANY_NAME)}</div>"
        "<div>Confidential — internal use only</div>"
        "</div>",
        unsafe_allow_html=True,
    )


# ----------------------------------------------------------------------------
# Rendering blocks
# ----------------------------------------------------------------------------
def token_stream(response, timing: dict):
    """Yield answer text piece by piece and record how long the LLM took."""
    start = time.perf_counter()
    gen = getattr(response, "response_gen", None)
    if gen is not None:
        for token in gen:
            if "first_token" not in timing:
                timing["first_token"] = time.perf_counter() - start
            yield token
    else:  # non-streaming response: simulate typing word by word
        for word in re.findall(r"\S+\s*", str(response)):
            yield word
            time.sleep(0.02)
    timing["llm"] = time.perf_counter() - start


def source_card(mid: int, i: int, src: dict):
    label, fg, bg = score_style(src["score"])
    icon_bg = dept_color(src["dept"])
    photo_style = f"background: radial-gradient(circle at 28% 28%, rgba(255,255,255,.32), transparent 60%), {icon_bg};"
    with st.container(key=f"srccard_{mid}_{i}"):
        st.markdown(
            f"<div class='src-photo' style='{photo_style}'>{dept_icon(src['dept'], 30)}</div>"
            f"<div class='src-head'><span class='src-name'>{html.escape(src['file'])}</span></div>"
            f"<span class='chip'>{html.escape(pretty(src['dept']))}</span>"
            f"<span class='badge' style='color:{fg};background:{bg}'>{label} {src['score']:.2f}</span>",
            unsafe_allow_html=True,
        )
        st.progress(min(max(src["score"], 0.0), 1.0))
        if src.get("excerpt"):
            st.markdown(f"<div class='src-excerpt'>{html.escape(src['excerpt'])}</div>", unsafe_allow_html=True)


def relevance_chart(msg: dict):
    df = pd.DataFrame(
        [
            {"source": f"{i}. {s['file']}", "department": pretty(s["dept"]), "dept_key": s["dept"], "score": s["score"]}
            for i, s in enumerate(msg["sources"], start=1)
        ]
    )
    positive = df["score"].clip(lower=0)
    df["share"] = positive / positive.sum() if positive.sum() > 0 else 0.0

    depts = df.drop_duplicates("dept_key")
    colors = alt.Scale(domain=list(depts["department"]), range=[dept_color(k) for k in depts["dept_key"]])
    axis_max = max(df["score"].max(), 0.01) * 1.4
    base = alt.Chart(df).encode(y=alt.Y("source:N", sort=None, title=None, axis=alt.Axis(labelLimit=260, labelFontSize=11)))
    bars = base.mark_bar(cornerRadiusEnd=4, height=20).encode(
        x=alt.X(
            "score:Q", title="Relevance score", scale=alt.Scale(domain=[0, axis_max]),
            axis=alt.Axis(grid=True, gridColor="#EDF2F5", tickCount=5),
        ),
        color=alt.Color("department:N", scale=colors, legend=alt.Legend(title="Department", orient="bottom")),
        tooltip=[
            alt.Tooltip("source:N", title="Source"),
            alt.Tooltip("department:N", title="Department"),
            alt.Tooltip("score:Q", title="Score", format=".3f"),
            alt.Tooltip("share:Q", title="Share of total", format=".0%"),
        ],
    )
    labels = base.mark_text(align="left", dx=5, color="#4B5A6B", fontSize=11, fontWeight="bold").encode(
        x="score:Q", text=alt.Text("score:Q", format=".2f")
    )
    chart = (
        (bars + labels)
        .properties(height=max(120, 34 * len(df)), padding={"left": 5, "right": 25, "top": 5, "bottom": 5})
        .configure_view(strokeWidth=0)
        .configure_axis(labelFont="Inter", titleFont="Inter", labelColor="#4B5A6B", titleColor="#4B5A6B")
        .configure_legend(labelFont="Inter", titleFont="Inter", labelColor="#4B5A6B", titleColor="#12283C")
    )
    show_altair(chart, key=f"chart_{msg['id']}")


def render_sources(msg: dict, expanded: bool):
    sources = msg.get("sources") or []
    if not sources:
        st.caption("No matching sources were found. Try setting the department filter to All.")
        return
    with st.expander(f"📚 Sources ({len(sources)})", expanded=expanded):
        for start in range(0, len(sources), CARDS_PER_ROW):
            cols = st.columns(CARDS_PER_ROW)
            for offset, src in enumerate(sources[start:start + CARDS_PER_ROW]):
                with cols[offset]:
                    source_card(msg["id"], start + offset, src)
        st.markdown("**How closely each source matches your question**")
        relevance_chart(msg)


# CHANGE 5: both thumbs up and thumbs down are now logged immediately to
# feedback_log.csv (previously only thumbs-down + a typed comment was saved),
# so the dashboard's feedback summary reflects everyone who rated an answer.
def render_feedback(msg: dict):
    mid = msg["id"]
    rating = st.feedback("thumbs", key=f"fb_{mid}")  # 1 = thumbs up, 0 = thumbs down
    if rating is not None and st.session_state.feedback_status.get(mid) != "saved":
        try:
            log_feedback({
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "message_id": mid,
                "department_filter": msg.get("department", ""),
                "question": msg.get("question", ""),
                "answer": msg.get("content", ""),
                "sources": "; ".join(s["file"] for s in msg.get("sources", [])),
                "rating": "thumbs_up" if rating == 1 else "thumbs_down",
                "comment": "",
            })
            st.session_state.feedback_status[mid] = "saved"
        except OSError:
            st.session_state.feedback_status[mid] = "error"

    if rating == 1:
        st.caption("Thanks for the feedback.")
    elif rating == 0:
        status = st.session_state.feedback_status.get(mid)
        if status == "saved":
            st.success("Thanks, your note was saved and will help us improve this answer.")
        st.text_input(
            "How can we make this answer better? (optional)",
            key=f"fbtext_{mid}",
            placeholder="What was missing, unclear, or wrong? Press Enter to send.",
            on_change=submit_feedback,
            args=(mid,),
        )


# CHANGE 8: one badge per answer route, so users can see at a glance whether
# they got a document lookup, a spreadsheet computation, or a direct calculation.
ROUTE_LABELS = {
    "DOCUMENT": ("📚", "Answered from policy documents"),
    "DATA": ("📊", "Computed from indexed structured data"),
    "DERIVED": ("📐", "Figures pulled from your documents, then calculated"),
    "CALCULATION": ("🧮", "Calculated directly from the numbers in your question"),
}


def render_assistant_extras(msg: dict, expanded: bool):
    if msg.get("error"):
        return
    render_feedback(msg)
    route = msg.get("route", "DOCUMENT")
    icon, label = ROUTE_LABELS.get(route, ROUTE_LABELS["DOCUMENT"])
    t = msg.get("timing", {})
    if "retrieval" in t and "llm" in t:
        st.caption(f"{icon} {label} · {t['retrieval']:.2f}s routing/search · {t['llm']:.1f}s answer")
    else:
        st.caption(f"{icon} {label}")
    if route != "CALCULATION":
        render_sources(msg, expanded)


def render_starters():
    st.markdown("<div class='starter-hint'>Not sure where to start? Pick a question:</div>", unsafe_allow_html=True)
    with st.container(key="starters"):
        cols = st.columns(len(STARTERS))
        for i, (col, (label, question)) in enumerate(zip(cols, STARTERS.items())):
            col.button(label, key=f"starter_{i}", on_click=queue_prompt, args=(question,), help=question)


def answer_document(question: str):
    """Retrieval logic. CHANGE 2: response_mode='tree_summarize' makes the
    LLM reason across ALL retrieved chunks rather than just compacting them
    into a single prompt — this is the second half of the fix for
    incomplete multi-row answers (paired with the SYSTEM_PROMPT above)."""
    filters = None
    if department != "All":
        filters = MetadataFilters(filters=[ExactMatchFilter(key="department", value=department)])

    started = time.perf_counter()
    query_engine = index.as_query_engine(
    similarity_top_k=40,
    filters=filters,
    streaming=True,
    response_mode="tree_summarize",
    node_postprocessors=[reranker],
    )
    response = query_engine.query(question)
    retrieval_s = time.perf_counter() - started

    sources = []
    for node in response.source_nodes:
        try:
            excerpt = " ".join(node.get_content().split())
        except Exception:
            excerpt = ""
        sources.append(
            {
                "file": node.metadata.get("file_name", "unknown"),
                "dept": node.metadata.get("department", "unknown"),
                "score": float(node.score or 0.0),
                "excerpt": (excerpt[:170] + "…") if len(excerpt) > 170 else excerpt,
            }
        )
    return response, sources, retrieval_s, "DOCUMENT"


# ----------------------------------------------------------------------------
# CHANGE 8: calculations & statistics
# ----------------------------------------------------------------------------
class _SimpleResponse:
    """Minimal stand-in for a LlamaIndex Response object, so calculator/data
    answers work with the existing token_stream() and message-rendering code
    without any changes to either."""
    def __init__(self, text: str):
        self.response = text
        self.response_gen = None
        self.source_nodes = []

    def __str__(self):
        return self.response


def classify_intent(question: str) -> str:
    """Cheap routing step using utility_llm (no system prompt, so the
    assistant's persona/guardrails don't interfere with this one-word answer)."""
    prompt = (
        "Classify the question below into exactly one category and reply with "
        "ONLY that single word - no punctuation, no explanation.\n\n"
        "CALCULATION - the question already gives the numbers itself and just asks for arithmetic "
        "on them (percentages, sums, differences, unit conversions).\n"
        "DERIVED - answering needs a calculation (growth rate, margin, ratio, CAGR, trend, "
        "year-over-year change, comparison across companies or years) but the actual figures must "
        "first be looked up from company reports/documents - the question itself contains no numbers.\n"
        "DATA - the question asks for a total, average, count, or comparison that must be looked up "
        "from an indexed company SPREADSHEET (not a text report).\n"
        "DOCUMENT - anything else: policies, procedures, definitions, plain lookups with no math.\n\n"
        f"Question: {question}\nCategory:"
    )
    try:
        result = utility_llm.complete(prompt).text.strip().upper()
    except Exception:
        return "DOCUMENT"
    if "CALC" in result:
        return "CALCULATION"
    if "DERIV" in result:
        return "DERIVED"
    if "DATA" in result and structured_datasets:
        return "DATA"
    return "DOCUMENT"


# Restricted arithmetic evaluator - no builtins, no attribute/subscript access,
# no function calls - so the LLM's extracted expression can be computed
# exactly instead of the model doing mental math on it.
_SAFE_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _safe_eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_safe_eval_node(node.left), _safe_eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_safe_eval_node(node.operand))
    raise ValueError("Unsupported or unsafe expression")


def safe_calculate(expression: str) -> float:
    tree = ast.parse(expression, mode="eval")
    return _safe_eval_node(tree.body)


def answer_calculation(question: str):
    """Pure arithmetic on numbers already in the question - no document or
    spreadsheet lookup involved."""
    started = time.perf_counter()
    prompt = (
        "Extract the arithmetic in this question as a single Python expression using only "
        "numbers, + - * / % ** and parentheses (write percentages as decimals, e.g. 15% as *0.15). "
        "Reply with ONLY the expression. If there's no calculable expression, reply: NONE\n\n"
        f"Question: {question}\nExpression:"
    )
    try:
        expr = utility_llm.complete(prompt).text.strip().strip("`")
    except Exception:
        expr = "NONE"
    retrieval_s = time.perf_counter() - started

    if not expr or expr.upper() == "NONE":
        text = ("I couldn't turn that into a calculation. Could you spell out the specific "
                "numbers you'd like me to work with?")
        return _SimpleResponse(text), [], retrieval_s, "CALCULATION"

    try:
        result = safe_calculate(expr)
        result_str = f"{result:,.4f}".rstrip("0").rstrip(".")
        text = f"**{expr} = {result_str}**"
    except Exception:
        text = ("I read this as a calculation but couldn't safely evaluate it - please double-check "
                "the numbers and try rephrasing.")
    return _SimpleResponse(text), [], retrieval_s, "CALCULATION"


def answer_grounded_calculation(question: str):
    """For questions that need a calculation performed on numbers that must
    first be pulled out of the documents - growth rates, margins, CAGR,
    ratios like ROCE, cross-document/cross-year comparisons. This retrieves
    the relevant text, asks the model to extract ONLY figures explicitly
    written there (never estimate/infer), computes the requested metric from
    those exact extracted numbers with the same safe evaluator used for plain
    calculations, and is upfront when a needed figure simply isn't indexed
    rather than guessing at it."""
    started = time.perf_counter()

    filters = None
    if department != "All":
        filters = MetadataFilters(filters=[ExactMatchFilter(key="department", value=department)])

    retriever = index.as_retriever(similarity_top_k=40, filters=filters)
    nodes = retriever.retrieve(question)
    nodes = reranker.postprocess_nodes(nodes, query_str=question)

    context = "\n\n".join(
        f"[Source: {n.metadata.get('file_name', 'unknown')}]\n{n.get_content()}" for n in nodes
    )[:14000]  # stay well inside utility_llm's context window

    sources = []
    for n in nodes[:6]:
        try:
            excerpt = " ".join(n.get_content().split())
        except Exception:
            excerpt = ""
        sources.append({
            "file": n.metadata.get("file_name", "unknown"),
            "dept": n.metadata.get("department", "unknown"),
            "score": float(n.score or 0.0),
            "excerpt": (excerpt[:170] + "…") if len(excerpt) > 170 else excerpt,
        })

    extract_prompt = (
        "You are extracting numeric financial figures from the CONTEXT below to help answer "
        "the QUESTION. List ONLY figures explicitly stated in the context - never estimate, "
        "infer, or fill in a number that isn't written there.\n\n"
        "Reply with one figure per line in this exact format, nothing else:\n"
        "label | value | period_or_context\n"
        "For anything needed but not present, add a line: MISSING | <what's missing>\n\n"
        f"CONTEXT:\n{context}\n\nQUESTION: {question}\n\nFIGURES:"
    )
    try:
        extracted = utility_llm.complete(extract_prompt).text.strip()
    except Exception:
        extracted = ""

    usable_lines = [ln for ln in extracted.splitlines() if ln.strip() and "MISSING" not in ln.upper()]
    if not extracted or not usable_lines:
        text = (
            "I couldn't find the specific figures needed for that calculation in the indexed "
            "documents. Please check with the Finance department for the exact numbers, or try "
            "rephrasing if you already have some of the figures to hand."
        )
        return _SimpleResponse(text), sources, time.perf_counter() - started, "DERIVED"

    formula_prompt = (
        "Given these figures extracted from company documents:\n"
        f"{extracted}\n\n"
        f"Question: {question}\n\n"
        "Write a single Python arithmetic expression (only numbers, + - * / % ** and parentheses) "
        "using the relevant values above that computes the answer. Reply with ONLY the expression. "
        "If the figures above aren't sufficient to answer, reply: NONE"
    )
    try:
        expr = utility_llm.complete(formula_prompt).text.strip().strip("`")
    except Exception:
        expr = "NONE"

    retrieval_s = time.perf_counter() - started

    if not expr or expr.upper() == "NONE":
        text = (
            "I found some related figures in the documents, but not enough to compute that "
            f"precisely:\n\n{extracted}\n\nYou may want to confirm the exact numbers with Finance."
        )
        return _SimpleResponse(text), sources, retrieval_s, "DERIVED"

    try:
        result = safe_calculate(expr)
        result_str = f"{result:,.4f}".rstrip("0").rstrip(".")
        text = (
            f"**Result: {result_str}**\n\n"
            f"Calculated as `{expr}`, using these figures from your documents:\n\n{extracted}"
        )
    except Exception:
        text = (
            f"I extracted relevant figures but couldn't safely compute the result:\n\n{extracted}"
            "\n\nPlease double-check with Finance."
        )

    return _SimpleResponse(text), sources, retrieval_s, "DERIVED"


def answer_structured(question: str):
    """Totals/averages/comparisons computed from indexed spreadsheets in
    STRUCTURED_DATA_DIR, using real pandas execution rather than the LLM
    estimating numbers from retrieved text."""
    started = time.perf_counter()
    if not structured_datasets or not PANDAS_QUERY_ENGINE_AVAILABLE:
        text = ("I don't have any structured spreadsheet data indexed yet to calculate that from. "
                "Try asking it as a general document question, or contact the relevant department directly.")
        return _SimpleResponse(text), [], time.perf_counter() - started, "DATA"

    names = list(structured_datasets.keys())
    if len(names) == 1:
        choice = names[0]
    else:
        options = "\n".join(f"- {n} (department: {structured_datasets[n]['department']})" for n in names)
        pick_prompt = (
            "Pick the single most relevant dataset for this question. Reply with ONLY its exact "
            f"filename from the list below.\n\nDatasets:\n{options}\n\nQuestion: {question}\nFilename:"
        )
        try:
            raw_choice = utility_llm.complete(pick_prompt).text.strip()
        except Exception:
            raw_choice = names[0]
        choice = raw_choice if raw_choice in structured_datasets else names[0]

    dataset = structured_datasets[choice]
    try:
        engine = PandasQueryEngine(df=dataset["df"], llm=utility_llm, verbose=False)
        response = engine.query(question)
    except Exception as exc:
        print(f"[Document Assistant] structured-data query failed: {exc}")
        text = "I found a relevant dataset but couldn't compute an answer from it. Please try rephrasing."
        return _SimpleResponse(text), [], time.perf_counter() - started, "DATA"

    retrieval_s = time.perf_counter() - started
    sources = [{
        "file": choice,
        "dept": dataset["department"],
        "score": 1.0,
        "excerpt": f"Computed from {len(dataset['df'])} rows in this indexed spreadsheet.",
    }]
    return response, sources, retrieval_s, "DATA"


def answer_question(question: str):
    """Routes each question to document search, a structured-data lookup, or
    a direct calculation, depending on what it needs."""
    if not enable_calc:
        return answer_document(question)
    intent = classify_intent(question)
    if intent == "CALCULATION":
        return answer_calculation(question)
    if intent == "DERIVED":
        return answer_grounded_calculation(question)
    if intent == "DATA":
        return answer_structured(question)
    return answer_document(question)


def next_id() -> int:
    st.session_state.msg_counter += 1
    return st.session_state.msg_counter


# ----------------------------------------------------------------------------
# Main layout
# ----------------------------------------------------------------------------
# chat_input is created at the top level so it stays pinned to the bottom of the page
typed_prompt = st.chat_input("Ask a question about company policies, HR, finance, legal, IT, or customer service...")
prompt = typed_prompt or st.session_state.pop("pending_prompt", None)

tab1, tab2 = st.tabs(["💬 AI Assistant", "📊 Document Analytics & Visuals"])

# ---------------------------- Tab 1: assistant ------------------------------
with tab1:
    scope = pretty(department) if department != "All" else "All departments"
    st.markdown(
        "<div class='hero'>"
        f"<span class='hero-eyebrow'>{html.escape(COMPANY_NAME)}</span>"
        "<h1>Ask your company documents</h1>"
        "<p>Answers come from your indexed policies, and every reply shows the sources it was built from.</p>"
        f"<span class='chip'>Scope: {html.escape(scope)}</span>"
        f"<span class='chip'>{top_k} sources per answer</span>"
        + ("<span class='chip'>🧮 Calculations enabled</span>" if enable_calc else "")
        + "<span class='chip'>Confidential &amp; internal use only</span></div>",
        unsafe_allow_html=True,
    )

    messages = st.session_state.messages
    for idx, msg in enumerate(messages):
        with st.chat_message(msg["role"], avatar="🙋" if msg["role"] == "user" else "📄"):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                # keep only the newest answer's sources open; a new turn below takes over that spot
                render_assistant_extras(msg, expanded=(idx == len(messages) - 1 and not prompt))

    if prompt:
        st.session_state.query_log.append(
            {"question": prompt, "department": department, "time": datetime.now().isoformat(timespec="seconds")}
        )
        log_query(prompt, department)  # CHANGE 4: persist to query_log.csv for the dashboard
        st.session_state.messages.append({"id": next_id(), "role": "user", "content": prompt})
        with st.chat_message("user", avatar="🙋"):
            st.markdown(prompt)

        with st.chat_message("assistant", avatar="📄"):
            try:
                with st.spinner("Thinking..."):
                    response, sources, retrieval_s, route = answer_question(prompt)
                timing = {"retrieval": retrieval_s}
                answer = st.write_stream(token_stream(response, timing))

                assistant_msg = {
                    "id": next_id(),
                    "role": "assistant",
                    "content": answer,
                    "sources": sources,
                    "timing": timing,
                    "question": prompt,
                    "department": department,
                    "route": route,
                }
                st.session_state.messages.append(assistant_msg)
                st.session_state.metrics = {"retrieval": timing["retrieval"], "llm": timing.get("llm")}
                render_scoreboard(scoreboard_slot)

                # CHANGE 6: persist timing + average relevance for the dashboard's
                # real response-time trend chart.
                avg_rel = (sum(s["score"] for s in sources) / len(sources)) if sources else 0.0
                log_metrics(department, timing.get("retrieval"), timing.get("llm"), avg_rel)

                render_assistant_extras(assistant_msg, expanded=True)
            except Exception as exc:
                print(f"[Document Assistant] request failed: {exc}")  # full detail for the site admin, in the server log only
                error_text = (
                    "⚠️ I couldn't complete that request right now. Please try again in a moment, "
                    "or contact your IT service desk if the issue continues."
                )
                st.error(error_text)
                st.session_state.messages.append(
                    {"id": next_id(), "role": "assistant", "content": error_text, "error": True}
                )

    if not st.session_state.messages:
        render_starters()

# ---------------------------- Tab 2: analytics ------------------------------
with tab2:
    if inventory.empty:
        inv, is_demo = DEMO_INVENTORY, True
        st.info("No indexed documents were found in Chroma yet, so sample data is shown below.")
    else:
        inv, is_demo = inventory, False

    by_dept = inv.groupby("department", as_index=False).agg(documents=("file", "nunique"), chunks=("chunks", "sum"))
    by_dept["label"] = by_dept["department"].map(pretty)
    color_map = {pretty(d): dept_color(d) for d in by_dept["department"]}

    st.markdown("### Document inventory")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Documents", int(by_dept["documents"].sum()), help="Unique files in the index.")
    k2.metric("Text chunks", int(by_dept["chunks"].sum()), help="Chunks of text stored in the search index.")
    k3.metric("Departments", len(by_dept))
    k4.metric("Questions this session", len(st.session_state.query_log))

    left, right = st.columns(2)
    with left:
        st.markdown("**Documents by department**")
        pie = px.pie(
            by_dept, names="label", values="documents", hole=0.55,
            color="label", color_discrete_map=color_map,
        )
        pie.update_traces(textinfo="percent+label", textposition="outside", sort=False)
        pie.update_layout(
            showlegend=False, height=340, margin=dict(t=20, b=20, l=20, r=20),
            paper_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter, sans-serif", size=13),
            annotations=[dict(text=f"{int(by_dept['documents'].sum())}<br>docs", showarrow=False, font=dict(size=18))],
        )
        st.plotly_chart(pie, key="pie_docs_by_dept")

    with right:
        st.markdown("**Text chunks by department**")
        bar = px.bar(
            by_dept.sort_values("chunks"), x="chunks", y="label", orientation="h",
            color="label", color_discrete_map=color_map, text="chunks",
        )
        bar.update_traces(textposition="outside", cliponaxis=False)
        bar.update_layout(
            showlegend=False, height=340, margin=dict(t=20, b=20, l=10, r=30),
            xaxis_title="Chunks", yaxis_title=None,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif", size=13),
        )
        st.plotly_chart(bar, key="bar_chunks_by_dept")

    # ---- CHANGE 7: real usage data replaces the old hardcoded TOPICS_SAMPLE ----
    st.markdown("### Most frequently asked questions (real usage data)")
    qlog = load_query_log()
    if qlog.empty:
        st.info("No questions logged yet. Ask a few in the AI Assistant tab, then check back here.")
    else:
        by_topic = (
            qlog.groupby(["question", "department"], as_index=False)
            .size()
            .rename(columns={"size": "queries"})
            .sort_values("queries", ascending=False)
            .head(10)
        )
        by_topic["label"] = by_topic["department"].map(pretty)
        topic_bar = px.bar(
            by_topic.sort_values("queries"), x="queries", y="question", orientation="h",
            color="label", color_discrete_map={pretty(d): c for d, c in DEPT_COLORS.items()},
            labels={"queries": "Times asked", "question": "", "label": "Department"},
        )
        topic_bar.update_layout(
            height=380, margin=dict(t=10, b=10, l=10, r=10),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif", size=13), legend=dict(orientation="h", y=-0.15),
        )
        st.plotly_chart(topic_bar, key="bar_topics_real")
        st.caption(f"Based on {len(qlog)} real questions logged for this deployment.")

    st.markdown("### Answer quality feedback (real usage data)")
    fb = pd.read_csv(FEEDBACK_FILE) if os.path.exists(FEEDBACK_FILE) else pd.DataFrame(columns=FEEDBACK_FIELDS)
    fb_rated = fb[fb["rating"].isin(["thumbs_up", "thumbs_down"])] if not fb.empty else fb
    if fb_rated.empty:
        st.info("No feedback logged yet. Rate an answer with 👍/👎 in the AI Assistant tab.")
    else:
        total = len(fb_rated)
        positive = int((fb_rated["rating"] == "thumbs_up").sum())
        fc1, fc2, fc3 = st.columns(3)
        fc1.metric("Answers rated", total)
        fc2.metric("Positive feedback", f"{positive / total * 100:.0f}%")
        fc3.metric("Needs improvement", total - positive)

    st.markdown("### Response time trend (real usage data)")
    mdf = pd.read_csv(METRICS_FILE) if os.path.exists(METRICS_FILE) else pd.DataFrame()
    if mdf.empty:
        st.info("No performance data logged yet. Ask a question in the AI Assistant tab to start tracking this.")
    else:
        mdf = mdf.reset_index(drop=True)
        mdf["n"] = range(1, len(mdf) + 1)
        line = (
            alt.Chart(mdf)
            .transform_fold(["retrieval_s", "llm_s"], as_=["metric", "seconds"])
            .mark_line(point=True)
            .encode(
                x=alt.X("n:Q", title="Question #"),
                y=alt.Y("seconds:Q", title="Seconds"),
                color=alt.Color("metric:N", title="Stage"),
                tooltip=["n:Q", "metric:N", "seconds:Q"],
            )
            .properties(height=280)
        )
        show_altair(line, key="metrics_trend")

    if st.session_state.query_log:
        with st.expander(f"🕑 Questions asked this session ({len(st.session_state.query_log)})"):
            st.dataframe(pd.DataFrame(st.session_state.query_log), hide_index=True)

    with st.expander("🗂️ Indexed files"):
        table = inv.copy()
        table["department"] = table["department"].map(pretty)
        st.dataframe(table.sort_values(["department", "file"]), hide_index=True)
        if is_demo:
            st.caption("Sample rows shown until your documents are indexed.")

# ---------------------------- Site footer -----------------------------------
# Shown below both tabs, like the footer on the company's public website.
with st.container(key="site_footer"):
    fcol1, fcol2, fcol3 = st.columns([1.3, 1, 1])
    with fcol1:
        st.markdown(f"<div class='footer-brand'>{html.escape(COMPANY_NAME)}</div>", unsafe_allow_html=True)
        st.markdown(
            "<p>This internal assistant answers questions from indexed company policy documents. "
            "Always confirm anything critical against the official policy on the intranet.</p>",
            unsafe_allow_html=True,
        )
    with fcol2:
        st.markdown("<div class='footer-heading'>Quick Links</div>", unsafe_allow_html=True)
        for i, (label, question) in enumerate(FOOTER_TOPICS.items()):
            st.button(label, key=f"footer_link_{i}", on_click=queue_prompt, args=(question,),
                      help=f"Ask: {question}")
    with fcol3:
        st.markdown(
            "<div class='footer-heading'>Need Help?</div>"
            "<p>IT Service Desk<br>Ext. 4357 (HELP)<br>"
            "<a href='mailto:it-support@meridianhealth.example'>it-support@meridianhealth.example</a></p>"
            "<p>HR Enquiries<br><a href='mailto:hr@meridianhealth.example'>hr@meridianhealth.example</a></p>",
            unsafe_allow_html=True,
        )
    st.markdown(
        f"<div class='footer-bottom'>© 2026 {html.escape(COMPANY_NAME)}. Confidential — for internal use only.</div>",
        unsafe_allow_html=True,
    )
