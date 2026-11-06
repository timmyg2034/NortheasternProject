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

# Custom CSS to cleanly hide upper right menu, toolbar, and deploy button
st.markdown("""
<style>
    /* Hide upper-right menu buttons, deploy button, and toolbar */
    #MainMenu {visibility: hidden; display: none !important;}
    header {visibility: hidden !important;}
    [data-testid="stHeader"] {visibility: hidden !important;}
    [data-testid="stToolbar"] {visibility: hidden; display: none !important;}
    .stDeployButton {display: none !important;}
    header button {display: none !important;}
    button[title="View app in Streamlit Community Cloud"] {display: none !important;}
    div[data-testid="stDecoration"] {display: none !important;}

    /* Hide standard footer */
    footer {visibility: hidden; display: none !important;}
    [data-testid="stFooter"] {visibility: hidden; display: none !important;}
</style>
""", unsafe_allow_html=True)

col_logo, col_title = st.columns([1, 5], vertical_alignment="center") if "vertical_alignment" in st.columns.__code__.co_varnames else st.columns([1, 5])
with col_logo:
    if HAS_LOGO:
        st.image(LOGO_PATH, width=95)
with col_title:
    st.title("Northeastern Men's Hockey Stats Explorer")

with st.expander("ℹ️ Data Sources & Coverage Disclaimer"):
    st.markdown("""
    **Primary Data Sources:**
    - All game-by-game records are scraped and parsed directly from official Northeastern Athletics archives:
      - **2012–13 to Present:** Official Sidearm box scores via [nuhuskies.com](https://nuhuskies.com)
      - **1999–00 to 2011–12:** Legacy athletic archives via [static.gonu.com](https://static.gonu.com)
    - Whenever you ask about a specific game, direct links to the official box score are provided.

    **Coverage & Metric Availability:**
    - **Goals, Assists, Points, Shots, +/-**: Complete coverage across all 996 games from **1999–00 to present** (~18,000 player records).
    - **Goalie Performance (Saves, GA, Decisions, Shutouts)**: Complete coverage from **1999–00 to present** (1,040 goalie records).
    - **Game Outcomes, Overtime & Shutouts**: Complete game-by-game tracking including regular, overtime (OT, 2OT, 3OT), and shutout outcomes.
    - **Shootouts**: Detailed tracking of all shootout games and shot-by-shot attempts (shooter name, round, MADE/MISSED result, opposing goalie).
    - **Goal Scoring Timeline & Game-Winning Goals (GWG)**: Complete coverage from **1999–00 to present** (7,050+ goal events).
    - **Penalty Infractions & Minutes**: Complete coverage from **1999–00 to present** (16,700+ penalties).
    - **Blocked Shots (`BLK`) & Faceoffs (`FO`)**: Officially tracked from **2012–13 to present** (6,956 blocks, 15,284 faceoff wins). The NCAA and Northeastern did not track blocked shots or faceoffs in box scores prior to 2012.
    - **Pre-1999 Note**: Digital game-by-game box scores prior to October 1999 are not published in athletic web archives.
    """)

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
    name = re.sub(r'^[*\s\d]+', '', name).strip()
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            return f"{parts[1]} {parts[0]}"
    return name


# 3. Load All 6 Datasets into Memory
@st.cache_data
def load_data():
    skater_df = pd.read_csv("northeastern_hockey_stats_mcp.csv")
    goalie_df = pd.read_csv("northeastern_goalie_stats.csv")
    goals_df = pd.read_csv("northeastern_goal_events.csv") if os.path.exists("northeastern_goal_events.csv") else pd.DataFrame()
    penalties_df = pd.read_csv("northeastern_penalty_events.csv") if os.path.exists("northeastern_penalty_events.csv") else pd.DataFrame()
    games_df = pd.read_csv("northeastern_game_results.csv") if os.path.exists("northeastern_game_results.csv") else pd.DataFrame()
    shootouts_df = pd.read_csv("northeastern_shootout_events.csv") if os.path.exists("northeastern_shootout_events.csv") else pd.DataFrame()

    # Clean skaters
    if "opponent" in skater_df.columns:
        skater_df["opponent"] = skater_df["opponent"].fillna("").apply(clean_opponent_name)
    if "player_name" in skater_df.columns:
        skater_df["player_name"] = skater_df["player_name"].fillna("").apply(clean_person_name)
    for col in ["nu_goals", "opp_goals", "goals", "assists", "points", "shots", "plus_minus", "penalties", "penalty_minutes", "faceoffs_won", "faceoffs_lost", "blocked_shots"]:
        if col in skater_df.columns:
            skater_df[col] = pd.to_numeric(skater_df[col], errors="coerce").fillna(0)

    # Clean goalies
    if "opponent" in goalie_df.columns:
        goalie_df["opponent"] = goalie_df["opponent"].fillna("").apply(clean_opponent_name)
    if "goalie_name" in goalie_df.columns:
        goalie_df["goalie_name"] = goalie_df["goalie_name"].fillna("").apply(clean_person_name)
    for col in ["nu_goals", "opp_goals", "goals_against", "empty_net_goals", "saves", "shots_against", "save_pct"]:
        if col in goalie_df.columns:
            goalie_df[col] = pd.to_numeric(goalie_df[col], errors="coerce").fillna(0)

    # Clean goals
    if not goals_df.empty:
        if "opponent" in goals_df.columns:
            goals_df["opponent"] = goals_df["opponent"].fillna("").apply(clean_opponent_name)
        for c in ["scorer", "primary_assist", "secondary_assist"]:
            if c in goals_df.columns:
                goals_df[c] = goals_df[c].fillna("").apply(clean_person_name)
        for col in ["is_gwg", "nu_score_after", "opp_score_after"]:
            if col in goals_df.columns:
                goals_df[col] = pd.to_numeric(goals_df[col], errors="coerce").fillna(0)

    # Clean penalties
    if not penalties_df.empty:
        if "opponent" in penalties_df.columns:
            penalties_df["opponent"] = penalties_df["opponent"].fillna("").apply(clean_opponent_name)
        if "player_name" in penalties_df.columns:
            penalties_df["player_name"] = penalties_df["player_name"].fillna("").apply(clean_person_name)
        if "penalty_minutes" in penalties_df.columns:
            penalties_df["penalty_minutes"] = pd.to_numeric(penalties_df["penalty_minutes"], errors="coerce").fillna(2)

    # Clean game results
    if not games_df.empty:
        games_df = games_df[games_df["opponent"].astype(str).str.strip().ne("Unknown") & games_df["date"].astype(str).str.strip().ne("")].copy()
        if "opponent" in games_df.columns:
            games_df["opponent"] = games_df["opponent"].fillna("").apply(clean_opponent_name)
        if "shutout_team" in games_df.columns:
            games_df["shutout_team"] = games_df["shutout_team"].fillna("").apply(lambda x: clean_opponent_name(x) if x not in ["Northeastern", "None", "Both (0-0 Tie)"] else x)
        for col in ["nu_goals", "opp_goals", "is_overtime", "is_shootout", "is_shutout"]:
            if col in games_df.columns:
                games_df[col] = pd.to_numeric(games_df[col], errors="coerce").fillna(0)

    # Clean shootout events
    if not shootouts_df.empty:
        if "opponent" in shootouts_df.columns:
            shootouts_df["opponent"] = shootouts_df["opponent"].fillna("").apply(clean_opponent_name)
        if "shooter_team" in shootouts_df.columns:
            shootouts_df["shooter_team"] = shootouts_df["shooter_team"].fillna("").apply(lambda x: clean_opponent_name(x) if x != "Northeastern" else x)
        if "goalie_team" in shootouts_df.columns:
            shootouts_df["goalie_team"] = shootouts_df["goalie_team"].fillna("").apply(lambda x: clean_opponent_name(x) if x != "Northeastern" else x)
        for c in ["shooter_name", "goalie_name"]:
            if c in shootouts_df.columns:
                shootouts_df[c] = shootouts_df[c].fillna("").apply(clean_person_name)
        if "round" in shootouts_df.columns:
            shootouts_df["round"] = pd.to_numeric(shootouts_df["round"], errors="coerce").fillna(1)

    return skater_df, goalie_df, goals_df, penalties_df, games_df, shootouts_df


try:
    df_skaters, df_goalies, df_goals, df_penalties, df_games, df_shootouts = load_data()
except FileNotFoundError:
    st.error("Datasets not found. Please ensure CSV files are uploaded to the repository.")
    st.stop()

# 4. Initialize Gemini LLM with Model Fallback Ladder
MODEL_LADDER = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-3-flash",
    "gemini-2.5-flash",
]

primary_llm = ChatGoogleGenerativeAI(
    model=MODEL_LADDER[0],
    google_api_key=api_key,
    temperature=0,
)

fallback_llms = [
    ChatGoogleGenerativeAI(
        model=m,
        google_api_key=api_key,
        temperature=0,
    )
    for m in MODEL_LADDER[1:]
]

llm = primary_llm.with_fallbacks(fallback_llms)


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


def run_python_code(code: str, df1: pd.DataFrame, df2: pd.DataFrame, df3: pd.DataFrame, df4: pd.DataFrame, df5: pd.DataFrame, df6: pd.DataFrame) -> str:
    local_env = {"df1": df1, "df2": df2, "df3": df3, "df4": df4, "df5": df5, "df6": df6, "pd": pd}
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


def answer_question(question: str, df1: pd.DataFrame, df2: pd.DataFrame, df3: pd.DataFrame, df4: pd.DataFrame, df5: pd.DataFrame, df6: pd.DataFrame, chat_history: list = None) -> str:
    all_opponents = sorted(set(df1["opponent"].dropna().unique()) | set(df2["opponent"].dropna().unique()) | (set(df5["opponent"].dropna().unique()) if not df5.empty else set()))
    history_text = format_chat_history(chat_history or [])
    code_prompt = (
        "You are a Python data analyst for Northeastern Men's Hockey.\n"
        "Six pandas DataFrames are already loaded in memory:\n"
        "1. `df1` (skaters): columns = ['date', 'opponent', 'nu_goals', 'opp_goals', 'player_name', 'goals', 'assists', 'points', 'shots', 'plus_minus', 'penalties', 'penalty_minutes', 'faceoffs_won', 'faceoffs_lost', 'blocked_shots', 'boxscore_url']\n"
        "2. `df2` (goalies): columns = ['date', 'opponent', 'nu_goals', 'opp_goals', 'goalie_name', 'decision', 'minutes', 'goals_against', 'empty_net_goals', 'saves', 'shots_against', 'save_pct', 'boxscore_url']\n"
        "3. `df3` (scoring events & timeline): columns = ['date', 'opponent', 'period', 'time', 'team', 'scorer', 'primary_assist', 'secondary_assist', 'strength', 'is_gwg', 'nu_score_after', 'opp_score_after', 'boxscore_url']\n"
        "   - `strength`: 'EV', 'PP', 'SH', 'EN'\n"
        "   - `is_gwg`: 1 if this goal was the official Game-Winning Goal, 0 otherwise\n"
        "4. `df4` (penalty events & infractions): columns = ['date', 'opponent', 'period', 'time', 'team', 'player_name', 'penalty_minutes', 'infraction', 'boxscore_url']\n"
        "5. `df5` (game outcomes, overtime, shutouts): columns = ['date', 'opponent', 'nu_goals', 'opp_goals', 'outcome', 'overtime_status', 'is_overtime', 'is_shootout', 'is_shutout', 'shutout_team', 'boxscore_url']\n"
        "   - `outcome`: 'W' (win), 'L' (loss), 'T' (tie)\n"
        "   - `overtime_status`: 'REG' (regulation), 'OT' (1st overtime), '2OT', '3OT', 'SO' (shootout)\n"
        "   - `is_overtime`: 1 if game reached overtime or shootout, 0 otherwise\n"
        "   - `is_shootout`: 1 if game was decided in a shootout, 0 otherwise\n"
        "   - `is_shutout`: 1 if either team was held scoreless (0 goals), 0 otherwise\n"
        "   - `shutout_team`: 'Northeastern' (if NU shut out the opponent) or opponent school name (if NU was shut out)\n"
        "6. `df6` (shootout attempts & results): columns = ['date', 'opponent', 'round', 'shooter_team', 'shooter_name', 'result', 'goalie_team', 'goalie_name', 'boxscore_url']\n"
        "   - `shooter_team`: 'Northeastern' or opponent name\n"
        "   - `shooter_name`: player who took the shootout shot\n"
        "   - `result`: 'MADE' or 'MISSED'\n"
        "   - `goalie_team`: team defending the shootout attempt\n"
        "   - `goalie_name`: goaltender who faced the shot\n\n"
        f"Valid standardized `opponent` names in the dataset: {all_opponents}\n\n"
        "Important conventions:\n"
        "- All player names are formatted as 'First Last' (e.g., 'Devon Levi', 'Adam Gaudette', 'Hunter McDonald', 'Aidan McDonough'). Always filter with `.str.contains(..., case=False, na=False)`.\n"
        "- `opponent` uses standardized school names (e.g., 'Boston University' for BU, 'Boston College' for BC, 'Massachusetts' for UMass, 'Massachusetts Lowell' for UMass Lowell / UML, 'Connecticut' for UConn, 'New Hampshire' for UNH, 'Rensselaer' for RPI).\n"
        "- In `df2`, `decision` is 'W' for win, 'L' for loss, 'T' for tie.\n"
        "- CONVERSATION CONTEXT: Use the Recent Conversation History below to resolve pronouns or omitted context in follow-up questions (e.g., 'How many goals did he have?', 'What about against BU?', 'Who had the shootout winner?').\n"
        "- CRITICAL EXISTENCE CHECK: Never blindly run `.sum()` or `.count()` on a filtered DataFrame without checking if the player and opponent actually exist! If the user asks about a specific player/goalie and/or opponent:\n"
        "  1. Check if the player name appears in `df1['player_name']`, `df2['goalie_name']`, `df3['scorer']`, `df4['player_name']`, `df6['shooter_name']`, or `df6['goalie_name']`. Print `player_exists: True/False`.\n"
        "  2. Check if the opponent appears in `df1['opponent']`, `df2['opponent']`, or `df5['opponent']`. Print `opponent_exists: True/False`.\n"
        "  3. Only if both exist, filter and print the requested stats (include `boxscore_url` if relevant for game lookups).\n\n"
        f"Recent Conversation History:\n{history_text}\n\n"
        "Write ONLY a single ```python ... ``` code block that performs these checks and uses `print()` to output the results.\n\n"
        f"Current User Question: {question}"
    )

    msg = llm.invoke(code_prompt)
    code = extract_python_code(message_to_text(msg))

    try:
        execution_output = run_python_code(code, df1, df2, df3, df4, df5, df6)
    except Exception as err:
        retry_prompt = (
            f"{code_prompt}\n\nYour previous code:\n```python\n{code}\n```\n"
            f"raised this error: {err}\n"
            "Please output ONLY the corrected ```python ... ``` code block."
        )
        msg_retry = llm.invoke(retry_prompt)
        code = extract_python_code(message_to_text(msg_retry))
        execution_output = run_python_code(code, df1, df2, df3, df4, df5, df6)

    final_prompt = (
        "You are a friendly, knowledgeable Northeastern Men's Hockey statistics assistant speaking to hockey fans.\n"
        f"Recent Conversation History:\n{history_text}\n\n"
        f"Current User Message: {question}\n\n"
        f"Computed Result from Historical Dataset (1999–present):\n{execution_output}\n\n"
        "Instructions:\n"
        "- Provide a clear, accurate, and conversational answer based strictly on the computed result above, taking into account the conversation history.\n"
        "- If a box score URL is available in the computed result for a specific game lookup, provide it as a markdown link: [View Official Box Score](<url>).\n"
        "- If a user asks about blocked shots or faceoffs for seasons prior to 2012–13, politely inform them that in-game blocked shots and faceoffs were not officially recorded by the NCAA or Northeastern prior to the 2012–13 season.\n"
        "- If a user asks about game-by-game stats prior to October 1999, clarify that digital athletic box score archives begin with the 1999–00 season.\n"
        "- If no records exist for the requested player, opponent, or matchup (e.g., `player_exists: False`, `opponent_exists: False`, or 0 matching games), NEVER claim the player recorded 0 stats in that matchup. Instead, clearly state that you didn't find any records for that player and/or against that school in the historical dataset (1999–present), and ask the user to confirm the player or school name.\n"
        "- NEVER mention internal variable names like `df1`, `df2`, `df3`, `df4`, `df5`, `df6`, `player_exists`, `opponent_exists`, pandas DataFrames, CSV files, or Python code.\n"
        "- Instead, refer naturally to 'skater statistics', 'goalie statistics', 'scoring summary', 'penalty infractions', 'game results & overtime', or 'shootout attempts' from Northeastern Athletics archives.\n"
        "- If the user is just saying hello or asking what you can do, greet them warmly and suggest a few exciting example questions (e.g., 'Who scored the game-winning goal against BU in the Beanpot?', 'Which games went to overtime or shootouts?', 'How many shutouts did Devon Levi record?', 'Who made or missed shootout attempts against Boston College?', or 'Show me the team\\'s top goal scorers vs. Maine.')."
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
if prompt := st.chat_input("e.g. Who scored the game-winning goal against BC in 2023?"):
    prior_history = list(st.session_state.messages)
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar=assistant_avatar):
        with st.spinner("Querying the historical box scores..."):
            try:
                response = answer_question(prompt, df_skaters, df_goalies, df_goals, df_penalties, df_games, df_shootouts, chat_history=prior_history)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
            except Exception as e:
                error_msg = f"Sorry, I encountered an error running that calculation: {e}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
