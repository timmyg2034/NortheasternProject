import streamlit as st
import pandas as pd
import os
import re
import io
import ast
import contextlib
from langchain_google_genai import ChatGoogleGenerativeAI

LOGO_PATH = "nu_husky_logo.png"
HAS_LOGO = os.path.exists(LOGO_PATH)

# 1. Page Configuration
st.set_page_config(
    page_title="NU Hockey Stats Explorer",
    page_icon=LOGO_PATH if HAS_LOGO else "🏒",
    layout="centered",
)

col_logo, col_title = st.columns([1, 5], vertical_alignment="center") if "vertical_alignment" in st.columns.__code__.co_varnames else st.columns([1, 5])
with col_logo:
    if HAS_LOGO:
        st.image(LOGO_PATH, width=95)
with col_title:
    st.title("Northeastern Men's Hockey Stats Explorer")
    st.write("Ask any question about historical skater or goalie statistics, game box scores, or opponent leaderboards.")

# 2. Securely Load the Gemini API Key
api_key = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")

if not api_key:
    st.warning("Please configure your GEMINI_API_KEY in the application secrets to enable the AI agent.")
    st.stop()


def clean_opponent_name(name):
    name = str(name).strip()
    name = re.sub(r'^(?:#|No\.\s*)\d+(?:/(?:\d+|rv|RV))?(?:\s+\[\d+\])?\s+', '', name, flags=re.IGNORECASE)
    name = re.sub(r'^\[\d+\]\s+', '', name)
    name = re.sub(r'\s*\(exh\.?\)\s*$', ' (Exh)', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*\(Championship Game\)\s*$', '', name, flags=re.IGNORECASE)
    name = name.replace('UMass Lowell', 'Massachusetts Lowell')
    name = name.replace('UMASS LOWELL', 'Massachusetts Lowell')
    name = name.replace('UMass-Lowell', 'Massachusetts Lowell')
    name = name.replace('UMass', 'Massachusetts')
    name = name.replace('UConn', 'Connecticut')
    name = name.replace('UNH', 'New Hampshire')
    name = name.replace('Rpi', 'Rensselaer')
    name = name.replace('RPI', 'Rensselaer')
    name = name.title()
    name = name.replace('Aic', 'AIC').replace('Rit', 'RIT')
    replacements = {
        'University Of Maine': 'Maine',
        'Univ. Of Maine': 'Maine',
        'Rv Maine': 'Maine',
        'University Of Connecticut': 'Connecticut',
        'University Of Massachusetts Lowell': 'Massachusetts Lowell',
        'Massachusetts-Amherst': 'Massachusetts',
        'University Of Massachusetts': 'Massachusetts',
        'University Of New Hampshire': 'New Hampshire',
        'U. Of New Hampshire': 'New Hampshire',
        'University Of Denver': 'Denver',
        'University Of Vermont': 'Vermont',
        'Providence College': 'Providence',
        'Merrimack College': 'Merrimack',
        'Quinnipiac University': 'Quinnipiac',
        'Quinnipiac University (Exh)': 'Quinnipiac',
        'Stonehill College': 'Stonehill',
        'Union College': 'Union',
        'Bentley University': 'Bentley',
        'Brown University': 'Brown',
        'Colgate University': 'Colgate',
        'Harvard University': 'Harvard',
        'Alabama-Huntsville': 'Alabama Huntsville',
        'Alaska-Anchorage': 'Alaska Anchorage',
        'University Of Alaska Anchorage': 'Alaska Anchorage',
        'Minnesota-Duluth': 'Minnesota Duluth',
        'Army West Point': 'Army',
        'Harvard (Exh)': 'Harvard',
        'Harvard (Championship Game)': 'Harvard',
        'Quinnipiac (Exh)': 'Quinnipiac',
        'Simon Fraser (Exh)': 'Simon Fraser',
        'Prince Edward Island (Exh)': 'Prince Edward Island',
        'Dalhousie University (Exh)': 'Dalhousie University',
        'Acadia (Exh)': 'Acadia',
    }
    return replacements.get(name, name)


def clean_person_name(name):
    name = str(name).strip()
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            return f"{parts[1]} {parts[0]}"
    return name


# 3. Load Both Datasets into Memory
@st.cache_data
def load_data():
    skater_df = pd.read_csv("northeastern_hockey_stats_mcp.csv")
    goalie_df = pd.read_csv("northeastern_goalie_stats.csv")

    if "opponent" in skater_df.columns:
        skater_df["opponent"] = skater_df["opponent"].fillna("").apply(clean_opponent_name)
    if "player_name" in skater_df.columns:
        skater_df["player_name"] = skater_df["player_name"].fillna("").apply(clean_person_name)
    for col in ["nu_goals", "opp_goals", "goals", "assists", "points", "shots", "plus_minus"]:
        if col in skater_df.columns:
            skater_df[col] = pd.to_numeric(skater_df[col], errors="coerce").fillna(0)

    if "opponent" in goalie_df.columns:
        goalie_df["opponent"] = goalie_df["opponent"].fillna("").apply(clean_opponent_name)
    if "goalie_name" in goalie_df.columns:
        goalie_df["goalie_name"] = goalie_df["goalie_name"].fillna("").apply(clean_person_name)
    for col in ["nu_goals", "opp_goals", "goals_against", "empty_net_goals", "saves", "shots_against", "save_pct"]:
        if col in goalie_df.columns:
            goalie_df[col] = pd.to_numeric(goalie_df[col], errors="coerce").fillna(0)

    return skater_df, goalie_df


try:
    df_skaters, df_goalies = load_data()
except FileNotFoundError:
    st.error("Datasets not found. Please ensure both 'northeastern_hockey_stats_mcp.csv' and 'northeastern_goalie_stats.csv' are uploaded to the repository.")
    st.stop()

# 4. Initialize the Gemini LLM
llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash-lite",
    google_api_key=api_key,
    temperature=0,
)


def extract_python_code(text: str) -> str:
    match = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.strip()


def run_python_code(code: str, df1: pd.DataFrame, df2: pd.DataFrame) -> str:
    local_env = {"df1": df1, "df2": df2, "pd": pd}
    stdout_buf = io.StringIO()
    with contextlib.redirect_stdout(stdout_buf):
        tree = ast.parse(code, mode="exec")
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last_expr = ast.Expression(tree.body.pop().value)
            if tree.body:
                exec(compile(tree, "<ast>", "exec"), local_env, local_env)
            val = eval(compile(last_expr, "<ast>", "eval"), local_env, local_env)
            if val is not None:
                print(val)
        else:
            exec(compile(tree, "<ast>", "exec"), local_env, local_env)
    return stdout_buf.getvalue().strip()


def answer_question(question: str, df1: pd.DataFrame, df2: pd.DataFrame) -> str:
    code_prompt = (
        "You are a Python data analyst for Northeastern Men's Hockey.\n"
        "Two pandas DataFrames are already loaded in memory as `df1` and `df2`:\n"
        "1. `df1` (skater game-by-game box scores): columns = ['date', 'opponent', 'nu_goals', 'opp_goals', 'player_name', 'goals', 'assists', 'points', 'shots', 'plus_minus']\n"
        "2. `df2` (goalie game-by-game box scores): columns = ['date', 'opponent', 'nu_goals', 'opp_goals', 'goalie_name', 'decision', 'minutes', 'goals_against', 'empty_net_goals', 'saves', 'shots_against', 'save_pct']\n\n"
        "Important conventions:\n"
        "- `player_name` and `goalie_name` are formatted as 'First Last' (e.g., 'Devon Levi', 'Adam Gaudette'). Always filter names with `.str.contains(..., case=False, na=False)`.\n"
        "- `opponent` uses standardized school names: 'Boston University' (for BU), 'Boston College' (for BC), 'Massachusetts' (for UMass), 'Massachusetts Lowell' (for UMass Lowell / UML), 'Connecticut' (for UConn), 'New Hampshire' (for UNH), 'Rensselaer' (for RPI), 'Maine', 'Providence', 'Merrimack', 'Vermont', 'Harvard', 'Quinnipiac', 'Army', 'AIC', 'RIT', etc.\n"
        "- In `df2`, `decision` is 'W' for a win, 'L' for a loss, and 'T' for a tie.\n\n"
        "Write ONLY a single ```python ... ``` code block that queries `df1` and/or `df2` and uses `print()` to output the exact values needed to answer the user's question.\n\n"
        f"User Question: {question}"
    )

    msg = llm.invoke(code_prompt)
    code = extract_python_code(msg.content if hasattr(msg, "content") else str(msg))

    try:
        execution_output = run_python_code(code, df1, df2)
    except Exception as err:
        retry_prompt = (
            f"{code_prompt}\n\nYour previous code:\n```python\n{code}\n```\n"
            f"raised this error: {err}\n"
            "Please output ONLY the corrected ```python ... ``` code block."
        )
        msg_retry = llm.invoke(retry_prompt)
        code = extract_python_code(msg_retry.content if hasattr(msg_retry, "content") else str(msg_retry))
        execution_output = run_python_code(code, df1, df2)

    final_prompt = (
        "You are a helpful Northeastern Men's Hockey statistics assistant.\n"
        f"User Question: {question}\n\n"
        f"Executed Python Query:\n```python\n{code}\n```\n\n"
        f"Computed Result from Historical Dataset:\n{execution_output}\n\n"
        "Provide a clear, accurate, and concise answer to the user's question based strictly on the computed result above."
    )
    final_msg = llm.invoke(final_prompt)
    return final_msg.content if hasattr(final_msg, "content") else str(final_msg)


# 5. Initialize Chat History in Session State
if "messages" not in st.session_state:
    st.session_state.messages = []

assistant_avatar = LOGO_PATH if HAS_LOGO else None

for msg in st.session_state.messages:
    avatar = assistant_avatar if msg["role"] == "assistant" else None
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# 6. Capture User Input and Process the Query
if prompt := st.chat_input("e.g. How many saves did Devon Levi have against BU?"):

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar=assistant_avatar):
        with st.spinner("Querying the historical box scores..."):
            try:
                response = answer_question(prompt, df_skaters, df_goalies)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
            except Exception as e:
                error_msg = f"Sorry, I encountered an error running that calculation: {e}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
