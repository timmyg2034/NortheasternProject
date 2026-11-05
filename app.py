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


def message_to_text(msg) -> str:
    content = msg.content if hasattr(msg, "content") else msg
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "thinking":
                    continue
                if "text" in item:
                    parts.append(str(item["text"]))
            elif hasattr(item, "text"):
                parts.append(str(item.text))
        return "\n".join(parts).strip()
    return str(content)


def extract_python_code(text: str) -> str:
    if not isinstance(text, str):
        text = message_to_text(text)
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


def format_chat_history(messages: list, max_turns: int = 8) -> str:
    if not messages:
        return "None"
    recent = messages[-max_turns:]
    lines = []
    for m in recent:
        role = "User" if m.get("role") == "user" else "Assistant"
        lines.append(f"{role}: {m.get('content', '')}")
    return "\n".join(lines)


def answer_question(question: str, df1: pd.DataFrame, df2: pd.DataFrame, chat_history: list = None) -> str:
    all_opponents = sorted(set(df1["opponent"].dropna().unique()) | set(df2["opponent"].dropna().unique()))
    history_text = format_chat_history(chat_history or [])
    code_prompt = (
        "You are a Python data analyst for Northeastern Men's Hockey.\n"
        "Two pandas DataFrames are already loaded in memory as `df1` and `df2`:\n"
        "1. `df1` (skater game-by-game box scores): columns = ['date', 'opponent', 'nu_goals', 'opp_goals', 'player_name', 'goals', 'assists', 'points', 'shots', 'plus_minus']\n"
        "2. `df2` (goalie game-by-game box scores): columns = ['date', 'opponent', 'nu_goals', 'opp_goals', 'goalie_name', 'decision', 'minutes', 'goals_against', 'empty_net_goals', 'saves', 'shots_against', 'save_pct']\n\n"
        f"Valid standardized `opponent` names in the dataset: {all_opponents}\n\n"
        "Important conventions:\n"
        "- `player_name` and `goalie_name` are formatted as 'First Last' (e.g., 'Devon Levi', 'Adam Gaudette'). Always filter names with `.str.contains(..., case=False, na=False)`.\n"
        "- `opponent` uses the standardized school names listed above (e.g., 'Boston University' for BU, 'Boston College' for BC, 'Massachusetts' for UMass, 'Massachusetts Lowell' for UMass Lowell / UML, 'Connecticut' for UConn, 'New Hampshire' for UNH, 'Rensselaer' for RPI).\n"
        "- In `df2`, `decision` is 'W' for a win, 'L' for a loss, and 'T' for a tie.\n"
        "- CONVERSATION CONTEXT: Use the Recent Conversation History below to resolve pronouns or omitted context in follow-up questions (e.g., 'How many goals did he have?', 'What about against BU?', 'In that season?').\n"
        "- CRITICAL EXISTENCE CHECK: Never blindly run `.sum()` on a filtered DataFrame without checking if the player and opponent actually exist! If the user asks about a specific player/goalie and/or opponent:\n"
        "  1. First check if the player/goalie name appears ANYWHERE in `df1['player_name']` or `df2['goalie_name']`. Print `player_exists: True/False` (and matching names).\n"
        "  2. Check if the opponent appears ANYWHERE in `df1['opponent']` or `df2['opponent']`. Print `opponent_exists: True/False` (and matching opponent name).\n"
        "  3. Only if both exist, filter for their matchup, print the number of games found, and print the requested stats.\n\n"
        f"Recent Conversation History:\n{history_text}\n\n"
        "Write ONLY a single ```python ... ``` code block that performs these checks and uses `print()` to output the results.\n\n"
        f"Current User Question: {question}"
    )

    msg = llm.invoke(code_prompt)
    code = extract_python_code(message_to_text(msg))

    try:
        execution_output = run_python_code(code, df1, df2)
    except Exception as err:
        retry_prompt = (
            f"{code_prompt}\n\nYour previous code:\n```python\n{code}\n```\n"
            f"raised this error: {err}\n"
            "Please output ONLY the corrected ```python ... ``` code block."
        )
        msg_retry = llm.invoke(retry_prompt)
        code = extract_python_code(message_to_text(msg_retry))
        execution_output = run_python_code(code, df1, df2)

    final_prompt = (
        "You are a friendly, knowledgeable Northeastern Men's Hockey statistics assistant speaking to hockey fans.\n"
        f"Recent Conversation History:\n{history_text}\n\n"
        f"Current User Message: {question}\n\n"
        f"Computed Result from Historical Dataset (1999–present):\n{execution_output}\n\n"
        "Instructions:\n"
        "- Provide a clear, accurate, and conversational answer based strictly on the computed result above, taking into account the conversation history.\n"
        "- If no records exist for the requested player, opponent, or matchup (e.g., `player_exists: False`, `opponent_exists: False`, or 0 matching games), NEVER claim the player recorded 0 saves/goals/points in that matchup. Instead, clearly state that you didn't find any records for that player and/or against that school in the historical dataset (1999–present), and ask the user to confirm the player or school name.\n"
        "- NEVER mention internal variable names like `df1`, `df2`, `player_exists`, `opponent_exists`, pandas DataFrames, CSV files, or Python code.\n"
        "- Instead, refer naturally to 'skater statistics', 'goalie statistics', 'game box scores', or 'opponent leaderboards'.\n"
        "- If the user is just saying hello or asking what you can do, greet them warmly and suggest a few example questions (e.g., 'Who has the most career goals against Boston College?', 'How many saves did Devon Levi record against Boston University?', or 'What are Adam Gaudette's career stats against Maine?')."
    )
    final_msg = llm.invoke(final_prompt)
    return message_to_text(final_msg)


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
    prior_history = list(st.session_state.messages)
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar=assistant_avatar):
        with st.spinner("Querying the historical box scores..."):
            try:
                response = answer_question(prompt, df_skaters, df_goalies, chat_history=prior_history)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
            except Exception as e:
                error_msg = f"Sorry, I encountered an error running that calculation: {e}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
