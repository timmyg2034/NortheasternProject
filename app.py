import streamlit as st
import pandas as pd
import os
import re
import io
import ast
import contextlib
from datetime import datetime
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
    - All game-by-game records, seasonal rosters, and cumulative statistics are scraped and parsed directly from official Northeastern Athletics archives:
      - **2011–12 to Present:** Official Sidearm box scores, rosters, and cumulative stats via [nuhuskies.com](https://nuhuskies.com)
      - **1999–00 to 2010–11:** Legacy athletic archives and cumulative `teamcume.htm` reports via [static.gonu.com](https://static.gonu.com)
    - Whenever you ask about a specific game, season roster, or cumulative stat line, direct links to the official box score, roster, or stats page are provided.

    **Coverage & Metric Availability:**
    - **Rosters, Captains (`C` / `A`) & Player Bios**: Complete coverage from **1999–00 to 2026–27** including Captains (`C`), Alternate Captains (`A`), position (`F`, `D`, `G`), class year (`Fr.`, `So.`, `Jr.`, `Sr.`, `Gr.`), height, weight, shooting hand, hometown, previous team/school, academic major, and head coach.
    - **Cumulative Season & Hockey East Conference Stats**: Complete overall and conference skater & goalie stats from **1999–00 to present**, including `GP`, `GS`, `G`, `A`, `PTS`, `SH%`, `+/-`, `PPG`, `SHG`, `FG` (first goals), `GWG`, `GTG`, `OTG`, `HTG` (hat tricks), `UAG` (unassisted goals), `GAA`, `SV%`, and `W-L-T`.
    - **Game-by-Game Goals, Assists, Points, Shots, +/-**: Complete coverage across all 996+ games from **1999–00 to present** (~18,000 player game logs, enriched with season, position, class year, and captaincy role).
    - **Goalie Performance (Saves, GA, Decisions, Shutouts)**: Complete game-by-game and seasonal coverage from **1999–00 to present**.
    - **Game Outcomes, Overtime & Shutouts**: Complete game-by-game tracking including regular, overtime (OT, 2OT, 3OT), and shutout outcomes.
    - **Shootouts**: Detailed tracking of all shootout games, shootout winners, and shot-by-shot attempts (shooter name, round, MADE/MISSED result, opposing goalie, deciding shootout goal).
    - **Goal Scoring Timeline & Game-Winning Goals (GWG)**: Complete coverage from **1999–00 to present** (7,050+ goal events with exact period timestamps and seconds remaining).
    - **Penalty Infractions & Minutes**: Complete coverage from **1999–00 to present** (16,700+ penalties).
    - **Blocked Shots (`BLK`) & Faceoffs (`FO`)**: Officially tracked from **2012–13 to present** (6,956+ blocks, 15,284+ faceoff wins). The NCAA and Northeastern did not track blocked shots or faceoffs in box scores prior to 2012.
    - **Pre-1999 Note**: Digital game-by-game box scores prior to October 1999 are not published in athletic web archives.
    """)

# 2. Securely Load the Gemini API Key
api_key = None
try:
    api_key = st.secrets.get("GEMINI_API_KEY")
except Exception:
    pass
if not api_key:
    api_key = os.getenv("GEMINI_API_KEY")

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


def standardize_date(d):
    if not d or pd.isna(d):
        return ""
    d = str(d).strip()
    if d == "Dec. 29, 200":
        return "2000-12-29"
    if d.startswith("Oct.27,"):
        d = d.replace("Oct.27,", "Oct. 27,")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y", "%b. %d, %Y"):
        try:
            return datetime.strptime(d, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return d


ROSTER_COLUMNS = [
    "season", "jersey_number", "player_name", "captain_role", "is_captain",
    "is_alternate_captain", "is_leadership", "position", "class_year",
    "height", "height_inches", "weight", "shoots", "hometown",
    "previous_team", "previous_school", "major", "head_coach", "roster_url",
]

SEASON_STATS_COLUMNS = [
    "season", "jersey_number", "player_name", "captain_role", "is_captain",
    "is_alternate_captain", "is_leadership", "position", "class_year",
    "height", "weight", "shoots", "hometown", "previous_team", "major", "head_coach",
    "gp", "goals", "assists", "points", "shots", "shot_pct", "plus_minus",
    "ppg", "shg", "fg", "gwg", "gtg", "otg", "htg", "uag",
    "penalties", "pim", "minor_penalties", "major_penalties", "other_penalties", "blocked_shots",
    "conf_gp", "conf_goals", "conf_assists", "conf_points", "conf_shots", "conf_shot_pct",
    "conf_plus_minus", "conf_ppg", "conf_shg", "conf_fg", "conf_gwg", "conf_gtg",
    "conf_otg", "conf_htg", "conf_uag", "conf_penalties", "conf_pim", "conf_blocked_shots",
    "goalie_gp", "goalie_gs", "goalie_minutes", "ga", "gaa", "ppga", "shga", "enga",
    "saves", "save_pct", "wins", "losses", "ties", "shutouts",
    "conf_goalie_gp", "conf_goalie_gs", "conf_goalie_minutes", "conf_ga", "conf_gaa",
    "conf_saves", "conf_save_pct", "conf_wins", "conf_losses", "conf_ties", "conf_shutouts",
    "stats_url",
]


def date_to_season(date_str: str) -> str:
    if not date_str or len(str(date_str)) < 7:
        return ""
    try:
        yr = int(str(date_str)[:4])
        mo = int(str(date_str)[5:7])
        if mo >= 8:
            return f"{yr}-{str(yr + 1)[-2:]}"
        else:
            return f"{yr - 1}-{str(yr)[-2:]}"
    except Exception:
        return ""


# 3. Load All 8 Datasets into Memory
@st.cache_data
def load_data():
    skater_df = pd.read_csv("northeastern_hockey_stats_mcp.csv")
    goalie_df = pd.read_csv("northeastern_goalie_stats.csv")
    goals_df = pd.read_csv("northeastern_goal_events.csv") if os.path.exists("northeastern_goal_events.csv") else pd.DataFrame()
    penalties_df = pd.read_csv("northeastern_penalty_events.csv") if os.path.exists("northeastern_penalty_events.csv") else pd.DataFrame()
    games_df = pd.read_csv("northeastern_game_results.csv") if os.path.exists("northeastern_game_results.csv") else pd.DataFrame()
    shootouts_df = pd.read_csv("northeastern_shootout_events.csv") if os.path.exists("northeastern_shootout_events.csv") else pd.DataFrame()
    rosters_df = pd.read_csv("northeastern_rosters.csv") if os.path.exists("northeastern_rosters.csv") else pd.DataFrame(columns=ROSTER_COLUMNS)
    season_stats_df = pd.read_csv("northeastern_season_stats.csv") if os.path.exists("northeastern_season_stats.csv") else pd.DataFrame(columns=SEASON_STATS_COLUMNS)

    # Ensure empty rosters or season stats have full schema guaranteed
    for col in ROSTER_COLUMNS:
        if col not in rosters_df.columns:
            rosters_df[col] = ""
    for col in SEASON_STATS_COLUMNS:
        if col not in season_stats_df.columns:
            season_stats_df[col] = 0

    # Clean skaters
    if "opponent" in skater_df.columns:
        skater_df["opponent"] = skater_df["opponent"].fillna("").apply(clean_opponent_name)
    if "player_name" in skater_df.columns:
        skater_df["player_name"] = skater_df["player_name"].fillna("").apply(clean_person_name)
    for col in ["season", "position", "class_year", "captain_role"]:
        if col in skater_df.columns:
            skater_df[col] = skater_df[col].fillna("None" if col == "captain_role" else "").astype(str)
    for col in ["nu_goals", "opp_goals", "goals", "assists", "points", "shots", "plus_minus", "penalties", "penalty_minutes", "faceoffs_won", "faceoffs_lost", "blocked_shots", "gwg"]:
        if col in skater_df.columns:
            skater_df[col] = pd.to_numeric(skater_df[col], errors="coerce").fillna(0)

    # Clean goalies
    if "opponent" in goalie_df.columns:
        goalie_df["opponent"] = goalie_df["opponent"].fillna("").apply(clean_opponent_name)
    if "goalie_name" in goalie_df.columns:
        goalie_df["goalie_name"] = goalie_df["goalie_name"].fillna("").apply(clean_person_name)
    for col in ["season", "class_year", "captain_role"]:
        if col in goalie_df.columns:
            goalie_df[col] = goalie_df[col].fillna("None" if col == "captain_role" else "").astype(str)
    for col in ["nu_goals", "opp_goals", "goals_against", "empty_net_goals", "saves", "shots_against", "save_pct"]:
        if col in goalie_df.columns:
            goalie_df[col] = pd.to_numeric(goalie_df[col], errors="coerce").fillna(0)

    # Clean goals
    if not goals_df.empty:
        if "time" in goals_df.columns:
            goals_df["time"] = goals_df["time"].fillna("").astype(str).str.strip()
            goals_df = goals_df[goals_df["time"].str.match(r"^\d{1,2}:\d{2}(?:\.\d+)?$")].copy()
        if "opponent" in goals_df.columns:
            goals_df["opponent"] = goals_df["opponent"].fillna("").apply(clean_opponent_name)
        if "team" in goals_df.columns:
            goals_df["team"] = goals_df["team"].fillna("").apply(lambda x: clean_opponent_name(x) if x != "Northeastern" else x)
        for c in ["scorer", "primary_assist", "secondary_assist"]:
            if c in goals_df.columns:
                goals_df[c] = goals_df[c].fillna("").apply(clean_person_name)
        for col in ["time_seconds", "seconds_remaining", "is_gwg", "nu_score_after", "opp_score_after"]:
            if col in goals_df.columns:
                goals_df[col] = pd.to_numeric(goals_df[col], errors="coerce").fillna(0)

    # Clean penalties
    if not penalties_df.empty:
        if "opponent" in penalties_df.columns:
            penalties_df["opponent"] = penalties_df["opponent"].fillna("").apply(clean_opponent_name)
        if "team" in penalties_df.columns:
            penalties_df["team"] = penalties_df["team"].fillna("").apply(lambda x: clean_opponent_name(x) if x != "Northeastern" else x)
        if "player_name" in penalties_df.columns:
            penalties_df["player_name"] = penalties_df["player_name"].fillna("").apply(clean_person_name)
        # Exclude TEAM, TM, bench minors, and formatting artifacts from player penalties
        penalties_df = penalties_df[
            ~penalties_df["player_name"].str.upper().isin(["TEAM", "TM", "BENCH", "TEAM BENCH", "TEAM PENALTY"]) &
            ~penalties_df["player_name"].str.startswith(":") &
            (penalties_df["player_name"] != "st")
        ].copy()
        if "penalty_minutes" in penalties_df.columns:
            penalties_df["penalty_minutes"] = pd.to_numeric(penalties_df["penalty_minutes"], errors="coerce").fillna(2)
        if "infraction" in penalties_df.columns:
            penalties_df["infraction"] = penalties_df["infraction"].fillna("").astype(str).str.strip().str.upper()
            penalties_df["infraction"] = penalties_df["infraction"].str.replace("CROSS CHECKING", "CROSS-CHECKING")

    # Clean game results
    if not games_df.empty:
        games_df = games_df[games_df["opponent"].astype(str).str.strip().ne("Unknown") & games_df["date"].astype(str).str.strip().ne("")].copy()
        if "opponent" in games_df.columns:
            games_df["opponent"] = games_df["opponent"].fillna("").apply(clean_opponent_name)
        if "shutout_team" in games_df.columns:
            games_df["shutout_team"] = games_df["shutout_team"].fillna("").apply(lambda x: clean_opponent_name(x) if x not in ["Northeastern", "None", "Both (0-0 Tie)"] else x)
        if "shootout_winner" in games_df.columns:
            games_df["shootout_winner"] = games_df["shootout_winner"].fillna("None").apply(lambda x: clean_opponent_name(x) if x not in ["Northeastern", "None"] else x)
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
        if "shootout_winner" in shootouts_df.columns:
            shootouts_df["shootout_winner"] = shootouts_df["shootout_winner"].fillna("None").apply(lambda x: clean_opponent_name(x) if x not in ["Northeastern", "None"] else x)
        for c in ["shooter_name", "goalie_name"]:
            if c in shootouts_df.columns:
                shootouts_df[c] = shootouts_df[c].fillna("").apply(clean_person_name)
        if "round" in shootouts_df.columns:
            shootouts_df["round"] = pd.to_numeric(shootouts_df["round"], errors="coerce").fillna(1)
        if "is_shootout_winner" in shootouts_df.columns:
            shootouts_df["is_shootout_winner"] = pd.to_numeric(shootouts_df["is_shootout_winner"], errors="coerce").fillna(0)

    # Clean rosters
    if not rosters_df.empty:
        if "player_name" in rosters_df.columns:
            rosters_df["player_name"] = rosters_df["player_name"].fillna("").apply(clean_person_name)
        for col in ["season", "jersey_number", "captain_role", "position", "class_year", "height", "shoots", "hometown", "previous_team", "previous_school", "major", "head_coach", "roster_url"]:
            if col in rosters_df.columns:
                rosters_df[col] = rosters_df[col].fillna("None" if col == "captain_role" else "").astype(str)
        for col in ["is_captain", "is_alternate_captain", "is_leadership", "height_inches", "weight"]:
            if col in rosters_df.columns:
                rosters_df[col] = pd.to_numeric(rosters_df[col], errors="coerce").fillna(0)

    # Clean cumulative season stats
    if not season_stats_df.empty:
        if "player_name" in season_stats_df.columns:
            season_stats_df["player_name"] = season_stats_df["player_name"].fillna("").apply(clean_person_name)
        for col in ["season", "jersey_number", "captain_role", "position", "class_year", "height", "shoots", "hometown", "previous_team", "major", "head_coach", "goalie_minutes", "conf_goalie_minutes", "stats_url"]:
            if col in season_stats_df.columns:
                season_stats_df[col] = season_stats_df[col].fillna("None" if col == "captain_role" else "").astype(str)
        num_cols = [
            "is_captain", "is_alternate_captain", "is_leadership", "weight",
            "gp", "goals", "assists", "points", "shots", "shot_pct", "plus_minus",
            "ppg", "shg", "fg", "gwg", "gtg", "otg", "htg", "uag",
            "penalties", "pim", "minor_penalties", "major_penalties", "other_penalties", "blocked_shots",
            "conf_gp", "conf_goals", "conf_assists", "conf_points", "conf_shots", "conf_shot_pct",
            "conf_plus_minus", "conf_ppg", "conf_shg", "conf_fg", "conf_gwg", "conf_gtg",
            "conf_otg", "conf_htg", "conf_uag", "conf_penalties", "conf_pim", "conf_blocked_shots",
            "goalie_gp", "goalie_gs", "ga", "gaa", "ppga", "shga", "enga", "saves", "save_pct",
            "wins", "losses", "ties", "shutouts",
            "conf_goalie_gp", "conf_goalie_gs", "conf_ga", "conf_gaa", "conf_saves", "conf_save_pct",
            "conf_wins", "conf_losses", "conf_ties", "conf_shutouts",
        ]
        for col in num_cols:
            if col in season_stats_df.columns:
                season_stats_df[col] = pd.to_numeric(season_stats_df[col], errors="coerce").fillna(0)

    # Standardize dates, populate season across all game-level DataFrames, and sort chronologically
    for df in [skater_df, goalie_df, goals_df, penalties_df, games_df, shootouts_df]:
        if not df.empty and "date" in df.columns:
            df["date"] = df["date"].apply(standardize_date)
            if "season" not in df.columns:
                df["season"] = df["date"].apply(date_to_season)
            df.sort_values("date", kind="mergesort", inplace=True)
            df.reset_index(drop=True, inplace=True)

    return skater_df, goalie_df, goals_df, penalties_df, games_df, shootouts_df, rosters_df, season_stats_df


try:
    df_skaters, df_goalies, df_goals, df_penalties, df_games, df_shootouts, df_rosters, df_season_stats = load_data()
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


def run_python_code(
    code: str,
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    df3: pd.DataFrame,
    df4: pd.DataFrame,
    df5: pd.DataFrame,
    df6: pd.DataFrame,
    df7: pd.DataFrame,
    df8: pd.DataFrame,
) -> str:
    pd.set_option("display.max_colwidth", None)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 1000)
    pd.set_option("display.max_rows", 200)
    local_env = {
        "df1": df1, "df2": df2, "df3": df3, "df4": df4,
        "df5": df5, "df6": df6, "df7": df7, "df8": df8, "pd": pd,
    }
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


def answer_question(
    question: str,
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    df3: pd.DataFrame,
    df4: pd.DataFrame,
    df5: pd.DataFrame,
    df6: pd.DataFrame,
    df7: pd.DataFrame,
    df8: pd.DataFrame,
    chat_history: list = None,
) -> str:
    all_opponents = sorted(set(df1["opponent"].dropna().unique()) | set(df2["opponent"].dropna().unique()) | (set(df5["opponent"].dropna().unique()) if not df5.empty else set()))
    history_text = format_chat_history(chat_history or [])
    code_prompt = (
        "You are a Python data analyst for Northeastern Men's Hockey.\n"
        "Eight pandas DataFrames are already loaded in memory:\n"
        "1. `df1` (game-by-game skaters): columns = ['date', 'season', 'opponent', 'nu_goals', 'opp_goals', 'player_name', 'position', 'class_year', 'captain_role', 'goals', 'assists', 'points', 'shots', 'plus_minus', 'penalties', 'penalty_minutes', 'faceoffs_won', 'faceoffs_lost', 'blocked_shots', 'gwg', 'is_overtime', 'is_shutout', 'boxscore_url']\n"
        "   - `season`: Season string e.g. '2025-26', '2024-25', ..., '1999-00'\n"
        "   - `position`: 'F' (Forward), 'D' (Defenseman), 'G' (Goalie)\n"
        "   - `class_year`: 'Fr.', 'So.', 'Jr.', 'Sr.', 'Gr.'\n"
        "   - `captain_role`: 'C' (Captain), 'A' (Alternate/Assistant Captain), or 'None'\n"
        "   - `gwg`: 1 if this skater scored the official Game-Winning Goal in this game, 0 otherwise\n"
        "2. `df2` (game-by-game goalies): columns = ['date', 'season', 'opponent', 'nu_goals', 'opp_goals', 'goalie_name', 'class_year', 'captain_role', 'decision', 'minutes', 'goals_against', 'empty_net_goals', 'saves', 'shots_against', 'save_pct', 'shutouts', 'is_overtime', 'boxscore_url']\n"
        "3. `df3` (scoring events & timeline): columns = ['date', 'opponent', 'period', 'time', 'time_seconds', 'seconds_remaining', 'team', 'scorer', 'primary_assist', 'secondary_assist', 'strength', 'is_gwg', 'nu_score_after', 'opp_score_after', 'boxscore_url']\n"
        "   - `period`: Formatted as strings '1st', '2nd', '3rd', 'OT'. For third period, filter with `'3rd'`.\n"
        "   - `time`: Official box score timestamp showing TIME ELAPSED in the period ('MM:SS' like '19:59', or 'MM:SS.t' with tenths of a second in the final minute of modern games like '19:59.8', '19:59.7', '19:59.4').\n"
        "   - `time_seconds`: Float of seconds elapsed in the period (0.0 to 1200.0 in regulation periods '1st'/'2nd'/'3rd'; 0.0 to 300.0 in regular-season 'OT', or up to 1200.0 in 20-minute playoff 'OT'). E.g. '19:59' = 1199.0, '19:59.8' = 1199.8.\n"
        "   - `seconds_remaining`: Float of seconds remaining on the game clock in that period (e.g. 1.0 for '19:59', 0.2 for '19:59.8', 0.3 for '19:59.7', 0.6 for '19:59.4').\n"
        "   - `strength`: 'EV', 'PP', 'SH', 'EN', 'EX'\n"
        "   - `is_gwg`: 1 if this specific goal was the official Game-Winning Goal, 0 otherwise\n"
        "4. `df4` (penalty events & infractions): columns = ['date', 'opponent', 'period', 'time', 'team', 'player_name', 'penalty_minutes', 'infraction', 'boxscore_url']\n"
        "   - `period`: Formatted as strings '1st', '2nd', '3rd', 'OT'.\n"
        "   - `infraction`: Standardized uppercase penalty infraction/type (e.g., 'ROUGHING', 'HOOKING', 'INTERFERENCE', 'TRIPPING', 'SLASHING', 'HOLDING', 'CROSS-CHECKING', 'HIGH STICKING', 'BOARDING', 'HITTING FROM BEHIND', 'GAME MISCONDUCT', '10-MINUTE MISCONDUCT', 'UNSPORTSMANLIKE CONDUCT').\n"
        "5. `df5` (game outcomes, overtime, shutouts): columns = ['date', 'opponent', 'nu_goals', 'opp_goals', 'outcome', 'overtime_status', 'is_overtime', 'is_shootout', 'shootout_winner', 'is_shutout', 'shutout_team', 'boxscore_url']\n"
        "   - `outcome`: 'W' (win), 'L' (loss), 'T' (tie; note that NCAA officially records shootout games as 'T' in overall standings, so check `shootout_winner` to see who won a shootout)\n"
        "   - `overtime_status`: 'REG' (regulation), 'OT' (1st overtime), '2OT', '3OT', 'SO' (shootout)\n"
        "   - `is_overtime`: 1 if game reached overtime or shootout, 0 otherwise\n"
        "   - `is_shootout`: 1 if game was decided in a shootout, 0 otherwise\n"
        "   - `shootout_winner`: 'Northeastern' or opponent school name if `is_shootout == 1`, otherwise 'None'\n"
        "   - `is_shutout`: 1 if either team was held scoreless (0 goals), 0 otherwise\n"
        "   - `shutout_team`: 'Northeastern' (if NU shut out the opponent) or opponent school name (if NU was shut out)\n"
        "6. `df6` (shootout attempts & results): columns = ['date', 'opponent', 'round', 'shooter_team', 'shooter_name', 'result', 'goalie_team', 'goalie_name', 'shootout_winner', 'is_shootout_winner', 'boxscore_url']\n"
        "   - `shooter_team`: 'Northeastern' or opponent name\n"
        "3. `df3` (scoring events & timeline): columns = ['date', 'season', 'opponent', 'period', 'time', 'time_seconds', 'seconds_remaining', 'team', 'scorer', 'primary_assist', 'secondary_assist', 'strength', 'is_gwg', 'nu_score_after', 'opp_score_after', 'boxscore_url']\n"
        "   - `period`: Formatted as strings '1st', '2nd', '3rd', 'OT'. For third period, filter with `'3rd'`.\n"
        "   - `time`: Official box score timestamp showing TIME ELAPSED in the period ('MM:SS' like '19:59', or 'MM:SS.t' with tenths of a second in the final minute of modern games like '19:59.8', '19:59.7', '19:59.4').\n"
        "   - `time_seconds`: Float of seconds elapsed in the period (0.0 to 1200.0 in regulation periods '1st'/'2nd'/'3rd'; 0.0 to 300.0 in regular-season 'OT', or up to 1200.0 in 20-minute playoff 'OT'). E.g. '19:59' = 1199.0, '19:59.8' = 1199.8.\n"
        "   - `seconds_remaining`: Float of seconds remaining on the game clock in that period (e.g. 1.0 for '19:59', 0.2 for '19:59.8', 0.3 for '19:59.7', 0.6 for '19:59.4').\n"
        "   - `strength`: 'EV', 'PP', 'SH', 'EN', 'EX'\n"
        "   - `is_gwg`: 1 if this specific goal was the official Game-Winning Goal, 0 otherwise\n"
        "4. `df4` (penalty events & infractions): columns = ['date', 'season', 'opponent', 'period', 'time', 'team', 'player_name', 'penalty_minutes', 'infraction', 'boxscore_url']\n"
        "   - `period`: Formatted as strings '1st', '2nd', '3rd', 'OT'.\n"
        "   - `infraction`: Standardized uppercase penalty infraction/type (e.g., 'ROUGHING', 'HOOKING', 'INTERFERENCE', 'TRIPPING', 'SLASHING', 'HOLDING', 'CROSS-CHECKING', 'HIGH STICKING', 'BOARDING', 'HITTING FROM BEHIND', 'GAME MISCONDUCT', '10-MINUTE MISCONDUCT', 'UNSPORTSMANLIKE CONDUCT').\n"
        "5. `df5` (game outcomes, overtime, shutouts): columns = ['date', 'season', 'opponent', 'nu_goals', 'opp_goals', 'outcome', 'overtime_status', 'is_overtime', 'is_shootout', 'shootout_winner', 'is_shutout', 'shutout_team', 'boxscore_url']\n"
        "   - `outcome`: 'W' (win), 'L' (loss), 'T' (tie; note that NCAA officially records shootout games as 'T' in overall standings, so check `shootout_winner` to see who won a shootout)\n"
        "   - `overtime_status`: 'REG' (regulation), 'OT' (1st overtime), '2OT', '3OT', 'SO' (shootout)\n"
        "   - `is_overtime`: 1 if game reached overtime or shootout, 0 otherwise\n"
        "   - `is_shootout`: 1 if game was decided in a shootout, 0 otherwise\n"
        "   - `shootout_winner`: 'Northeastern' or opponent school name if `is_shootout == 1`, otherwise 'None'\n"
        "   - `is_shutout`: 1 if either team was held scoreless (0 goals), 0 otherwise\n"
        "   - `shutout_team`: 'Northeastern' (if NU shut out the opponent) or opponent school name (if NU was shut out)\n"
        "6. `df6` (shootout attempts & results): columns = ['date', 'season', 'opponent', 'round', 'shooter_team', 'shooter_name', 'result', 'goalie_team', 'goalie_name', 'shootout_winner', 'is_shootout_winner', 'boxscore_url']\n"
        "   - `shooter_team`: 'Northeastern' or opponent name\n"
        "   - `shooter_name`: player who took the shootout shot\n"
        "   - `result`: 'MADE' or 'MISSED' (whether this individual shootout attempt went in — does NOT mean it was the winning shootout goal!)\n"
        "   - `goalie_team`: team defending the shootout attempt\n"
        "   - `goalie_name`: goaltender who faced the shot\n"
        "   - `shootout_winner`: team that won the shootout ('Northeastern' or opponent name)\n"
        "   - `is_shootout_winner`: 1 if this specific attempt was the official winning/deciding shootout goal for the team that won the shootout, 0 otherwise\n"
        "7. `df7` (seasonal rosters, captains/alternates & player bios, 1999-00 to 2026-27): columns = ['season', 'jersey_number', 'player_name', 'captain_role', 'is_captain', 'is_alternate_captain', 'is_leadership', 'position', 'class_year', 'height', 'height_inches', 'weight', 'shoots', 'hometown', 'previous_team', 'previous_school', 'major', 'head_coach', 'roster_url']\n"
        "   - `captain_role`: 'C' (Captain), 'A' (Alternate/Assistant Captain), 'None' (regular roster player)\n"
        "   - `is_captain`: 1 if Captain ('C'), 0 otherwise\n"
        "   - `is_alternate_captain`: 1 if Alternate Captain ('A'), 0 otherwise\n"
        "   - `is_leadership`: 1 if Captain or Alternate Captain ('C' or 'A'), 0 otherwise\n"
        "   - `position`: 'F', 'D', 'G'; `class_year`: 'Fr.', 'So.', 'Jr.', 'Sr.', 'Gr.'\n"
        "   - `height` (e.g. '6-2'), `height_inches` (int inches, e.g. 74), `weight` (int lbs), `shoots` ('Left' or 'Right'), `hometown`, `previous_team`, `previous_school`, `major` (academic major), `head_coach` ('Bruce Crowder', 'Greg Cronin', 'Jim Madigan', 'Jerry Keefe')\n"
        "8. `df8` (cumulative season skater & goalie stats — Overall & Hockey East Conference, 1999-00 to 2026-27): columns = ['season', 'jersey_number', 'player_name', 'captain_role', 'is_captain', 'is_alternate_captain', 'is_leadership', 'position', 'class_year', 'height', 'weight', 'shoots', 'hometown', 'previous_team', 'major', 'head_coach', 'gp', 'goals', 'assists', 'points', 'shots', 'shot_pct', 'plus_minus', 'ppg', 'shg', 'fg', 'gwg', 'gtg', 'otg', 'htg', 'uag', 'penalties', 'pim', 'minor_penalties', 'major_penalties', 'other_penalties', 'blocked_shots', 'conf_gp', 'conf_goals', 'conf_assists', 'conf_points', 'conf_shots', 'conf_shot_pct', 'conf_plus_minus', 'conf_ppg', 'conf_shg', 'conf_fg', 'conf_gwg', 'conf_gtg', 'conf_otg', 'conf_htg', 'conf_uag', 'conf_penalties', 'conf_pim', 'conf_blocked_shots', 'goalie_gp', 'goalie_gs', 'goalie_minutes', 'ga', 'gaa', 'ppga', 'shga', 'enga', 'saves', 'save_pct', 'wins', 'losses', 'ties', 'shutouts', 'conf_goalie_gp', 'conf_goalie_gs', 'conf_goalie_minutes', 'conf_ga', 'conf_gaa', 'conf_saves', 'conf_save_pct', 'conf_wins', 'conf_losses', 'conf_ties', 'conf_shutouts', 'stats_url']\n"
        "   - Overall skater columns: `gp`, `goals`, `assists`, `points`, `shots`, `shot_pct`, `plus_minus`, `ppg` (power-play goals), `shg` (shorthanded goals), `fg` (first goals), `gwg` (game-winning goals), `gtg` (game-tying goals), `otg` (overtime goals), `htg` (hat tricks), `uag` (unassisted goals), `penalties`, `pim`, `minor_penalties`, `major_penalties`, `other_penalties`, `blocked_shots`\n"
        "   - Hockey East Conference skater columns: `conf_gp`, `conf_goals`, `conf_assists`, `conf_points`, `conf_shots`, `conf_shot_pct`, `conf_plus_minus`, `conf_ppg`, `conf_shg`, `conf_fg`, `conf_gwg`, `conf_gtg`, `conf_otg`, `conf_htg`, `conf_uag`, `conf_penalties`, `conf_pim`, `conf_blocked_shots`\n"
        "   - Overall goalie columns: `goalie_gp`, `goalie_gs` (games started), `goalie_minutes`, `ga`, `gaa` (goals against average), `ppga`, `shga`, `enga`, `saves`, `save_pct`, `wins`, `losses`, `ties`, `shutouts`\n"
        "   - Hockey East Conference goalie columns: `conf_goalie_gp`, `conf_goalie_gs`, `conf_goalie_minutes`, `conf_ga`, `conf_gaa`, `conf_saves`, `conf_save_pct`, `conf_wins`, `conf_losses`, `conf_ties`, `conf_shutouts`\n\n"
        f"Valid standardized `opponent` names in the dataset: {all_opponents}\n\n"
        "Important conventions:\n"
        "- All player names are formatted as 'First Last' (e.g., 'Devon Levi', 'Adam Gaudette', 'Hunter McDonald', 'Aidan McDonough'). Always filter with `.str.contains(..., case=False, na=False)`.\n"
        "- `opponent` uses standardized school names (e.g., 'Boston University' for BU, 'Boston College' for BC, 'Massachusetts' for UMass, 'Massachusetts Lowell' for UMass Lowell / UML, 'Connecticut' for UConn, 'New Hampshire' for UNH, 'Rensselaer' for RPI).\n"
        "- ALL 8 DATAFRAMES HAVE A `season` COLUMN: `season` is available on `df1`, `df2`, `df3`, `df4`, `df5`, `df6`, `df7`, and `df8`! Season values are standardized 7-character strings formatted as `'YYYY-YY'` (e.g. `'2015-16'`, `'2023-24'`, `'1999-00'`).\n"
        "- SEASON STRINGS & YEAR NORMALIZATION: If a user asks about `'2015-2016'`, `'2015-2016 season'`, `'2015'`, or `'2016'`, ALWAYS normalize the input to `'YYYY-YY'` (e.g., `'2015-2016'` -> `'2015-16'`) or use `.str.startswith('2015')` or `.isin(['2015-16', '2015-2016'])`. Never assume exact string equality against `'YYYY-YYYY'`!\n"
        "- SINGLE-YEAR OR AMBIGUOUS SEASON INPUTS (e.g. '2015 season', 'in 2015'): In college hockey, seasons span two calendar years (e.g., fall 2014 to spring 2015 is '2014-15'; fall 2015 to spring 2016 is '2015-16'). If a user provides a single 4-digit year like '2015' without specifying whether they mean the season starting in 2015 ('2015-16') or ending in 2015 ('2014-15'):\n"
        "  - Check BOTH candidate seasons: `target_seasons = ['2014-15', '2015-16']` (or `df['season'].str.contains('15')`) and output the captains / stats for BOTH seasons clearly labeled so the user gets their exact answer regardless of which season they meant!\n"
        "- CAPTAINS (`C`) & ALTERNATE / ASSISTANT CAPTAINS (`A`):\n"
        "  - Use `df7` (rosters) and `df8` (cumulative season stats) for season-level or career captain/alternate captain questions (e.g. 'Who were the captains in 2025-26?', 'Who are the captains for 2026-27?', 'Which captain scored the most points in a season?', 'How many goals did captains and alternate captains score by season?', 'Which players served as captain for multiple seasons?').\n"
        "  - Filter Captains with `captain_role == 'C'` (or `is_captain == 1`), Alternate/Assistant Captains with `captain_role == 'A'` (or `is_alternate_captain == 1`), and all Leadership (Captains + Alternate Captains) with `captain_role.isin(['C', 'A'])` (or `is_leadership == 1`).\n"
        "  - For single-game or opponent-specific captain/alternate captain questions (e.g. 'Most points in a game by a captain', 'Captain goals against BU'), use `df1` (which also has `season`, `captain_role`, `position`, and `class_year` on every game log!).\n"
        "- CUMULATIVE SEASON STATS vs GAME-BY-GAME LOGS:\n"
        "  - Prefer `df8` for full-season totals, career totals across seasons, Hockey East conference stats (`conf_*`), games played (`gp`), games started (`goalie_gs`), shooting percentage (`shot_pct`), power-play/shorthanded/first/game-tying/overtime/unassisted goals (`ppg`, `shg`, `fg`, `gtg`, `otg`, `uag`), hat tricks (`htg`), GAA (`gaa`), and stats broken down by position (`'F'`, `'D'`, `'G'`), class year (`'Fr.'`, `'So.'`, `'Jr.'`, `'Sr.'`, `'Gr.'`), or head coach.\n"
        "  - Prefer `df1`–`df6` when filtering by a specific `opponent`, `date`, game outcome, period, timestamp, penalty infraction, or shootout.\n"
        "- ROSTER & BIOGRAPHICAL QUERIES (`df7`):\n"
        "  - Use `df7` for jersey numbers (`jersey_number`), height (`height`, `height_inches`), weight (`weight`), shooting/catching hand (`shoots`), hometown (`hometown`), previous junior/prep team (`previous_team`), previous school (`previous_school`), academic major (`major`), and head coach (`head_coach`).\n"
        "- In `df2`, `decision` is 'W' for win, 'L' for loss, 'T' for tie.\n"
        "- In `df3` and `df4`, `period` values are strings: `'1st'`, `'2nd'`, `'3rd'`, `'OT'`. When the user asks for 1st/2nd/3rd period, match `'1st'`, `'2nd'`, or `'3rd'` (not numbers like `3` or words like `'third'`).\n"
        "- TIMED GOALS & LAST-SECOND / BUZZER-BEATER GOALS: In `df3`, `time` is TIME ELAPSED in the period ('00:01' is 1 second INTO the period, whereas '19:59' or '19:59.8' is the LAST SECOND of a regulation period). Because modern box scores include tenths of a second in the final minute ('19:59.4', '19:59.7', '19:59.8') while legacy box scores use '19:59', NEVER use exact equality `df3['time'] == '19:59'` or `int()` on split time strings! Instead, ALWAYS use the precomputed numeric columns `seconds_remaining` and `time_seconds` (or `.str.startswith()`):\n"
        "  - Goals in the **last second of the game (3rd period)**: filter `df3[(df3['period'] == '3rd') & (df3['seconds_remaining'] <= 1.0)]` (which captures all goals at 19:59 through 19:59.9!). Also check late overtime goals with `df3[(df3['period'] == 'OT') & (df3['seconds_remaining'] <= 5.0)]`.\n"
        "  - Goals in the **last second of ANY period**: filter `df3[df3['seconds_remaining'] <= 1.0]`.\n"
        "  - Goals in the **final N seconds / final minute**: filter `df3['seconds_remaining'] <= N` (e.g. `<= 10.0` for final 10 seconds, `<= 60.0` for final minute).\n"
        "  - **Fastest goals** to start a game or period: filter or sort by `df3['time_seconds']` ascending.\n"
        "  - Goals at a **specific timestamp** (e.g. '19:59'): use `df3['time'].str.startswith('19:59')` so both `'19:59'` and `'19:59.x'` match.\n"
        "  - When printing timed goal results, print `['date', 'opponent', 'period', 'time', 'seconds_remaining', 'team', 'scorer', 'strength', 'nu_score_after', 'opp_score_after', 'boxscore_url']` and separate Northeastern goals (`team == 'Northeastern'`) from opponent goals (`team != 'Northeastern'`) so both are clear.\n"
        "- PENALTIES & BENCH MINORS: In `df4`, `infraction` records the specific penalty type (e.g. 'ROUGHING', 'TRIPPING', 'SLASHING', 'HOOKING', 'INTERFERENCE', 'CROSS-CHECKING'). Never include 'TEAM', 'Team', or 'TM' as a player! Those are team bench minors (e.g. too many men on ice). When answering who had the most penalties or penalty minutes, only include actual human players.\n"
        "- SHOOTOUT WINNERS & WINNING SHOOTOUT GOALS: In `df6`, `result == 'MADE'` ONLY means a player made their individual shootout attempt — a player can score (`result == 'MADE'`) in a shootout that their team LOST (e.g., Dylan Hryckowian made a Round 2 attempt against Boston University on 2026-02-02, but BU won that shootout 2-1 on Cole Hutson's Round 3 goal). NEVER filter `result == 'MADE'` alone when asked for a **winning shootout goal** (or shootout winner / deciding shootout goal)! Instead, ALWAYS filter `df6['is_shootout_winner'] == 1`. When asked for the most recent winning shootout goal, print BOTH:\n"
        "  1. Most recent Northeastern winning shootout goal: `df6[(df6['is_shootout_winner'] == 1) & (df6['shooter_team'] == 'Northeastern')].tail(1)`\n"
        "  2. Most recent winning shootout goal overall (including opponents): `df6[df6['is_shootout_winner'] == 1].tail(1)` and all attempts from that shootout game so the full context is clear.\n"
        "- DATES & CHRONOLOGICAL ORDERING: In all game-level DataFrames (`df1` to `df6`), `date` is standardized in ISO format `'YYYY-MM-DD'` (e.g., `'2026-03-14'`) and pre-sorted in ascending chronological order from oldest (1999) to newest (2026).\n"
        "  - For the MOST RECENT game in the dataset, simply inspect `df5.iloc[-1]` (or `df5.tail(1)`).\n"
        "  - For the EARLIEST game in the dataset, inspect `df5.iloc[0]` (or `df5.head(1)`).\n"
        "  - For the most recent game against a specific opponent, filter and take `.tail(1)`: e.g. `df5[df5['opponent'] == 'Boston College'].tail(1)`.\n"
        "  - When filtering or sorting by date, you can compare strings directly (e.g. `df5['date'] >= '2026-01-01'`) or use `pd.to_datetime(df['date'])`.\n"
        "- CONVERSATION CONTEXT: Use the Recent Conversation History below to resolve pronouns or omitted context in follow-up questions (e.g., 'How many goals did he have?', 'What about against BU?', 'Who were the alternate captains that year?').\n"
        "- CRITICAL EXISTENCE CHECK: Never blindly run `.sum()` or `.count()` on a filtered DataFrame without checking if the player and opponent actually exist! If the user asks about a specific player/goalie and/or opponent:\n"
        "  1. Check if the player name appears in `df1['player_name']`, `df2['goalie_name']`, `df3['scorer']`, `df4['player_name']`, `df6['shooter_name']`, `df6['goalie_name']`, `df7['player_name']`, or `df8['player_name']`. Print `player_exists: True/False`.\n"
        "  2. Check if the opponent appears in `df1['opponent']`, `df2['opponent']`, or `df5['opponent']`. Print `opponent_exists: True/False`.\n"
        "  3. Only if both exist, filter and print the requested stats (include `boxscore_url`, `roster_url`, or `stats_url` if relevant).\n\n"
        f"Recent Conversation History:\n{history_text}\n\n"
        "Write ONLY a single ```python ... ``` code block that performs these checks and uses `print()` to output the results.\n\n"
        f"Current User Question: {question}"
    )

    msg = llm.invoke(code_prompt)
    code = extract_python_code(message_to_text(msg))

    try:
        execution_output = run_python_code(code, df1, df2, df3, df4, df5, df6, df7, df8)
    except Exception as err:
        retry_prompt = (
            f"{code_prompt}\n\nYour previous code:\n```python\n{code}\n```\n"
            f"raised this error: {err}\n"
            "Please output ONLY the corrected ```python ... ``` code block with valid Python syntax."
        )
        msg_retry = llm.invoke(retry_prompt)
        code = extract_python_code(message_to_text(msg_retry))
        try:
            execution_output = run_python_code(code, df1, df2, df3, df4, df5, df6, df7, df8)
        except Exception as retry_err:
            execution_output = f"Execution error: {retry_err}"

    final_prompt = (
        "You are a friendly, knowledgeable Northeastern Men's Hockey statistics assistant speaking to hockey fans.\n"
        f"Recent Conversation History:\n{history_text}\n\n"
        f"Current User Message: {question}\n\n"
        f"Computed Result from Historical Dataset (1999–present):\n{execution_output}\n\n"
        "Instructions:\n"
        "- Provide a clear, accurate, and conversational answer based strictly on the computed result above, taking into account the conversation history.\n"
        "- STRICT ANTI-HALLUCINATION & FACTUAL GROUNDING RULE: You must answer ONLY using the facts present in 'Computed Result from Historical Dataset'. NEVER fabricate, hallucinate, or draw upon general training memory for player names, jersey numbers, captaincy roles, tournament titles, or game results! If the computed result is empty, indicates no matching records, or does not answer the question, state honestly that no records were found matching that criteria in the Northeastern Athletics dataset (1999–present), and suggest checking the season format (e.g., '2015-16').\n"
        "- If the computed result indicates an execution error, apologize politely, explain that you encountered a slight hiccup running that calculation, and invite the user to clarify or rephrase their question (e.g. specifying the season as 'YYYY-YY' like '2014-15' or '2015-16'). NEVER show raw Python errors or variable names like df1-df8.\n"
        "- If a box score URL, roster URL, or season stats URL is available in the computed result for a specific lookup, provide it as a markdown link (e.g., [View Official Box Score](<url>), [View Official Roster](<url>), or [View Official Season Stats](<url>)).\n"
        "- If a user asks about blocked shots or faceoffs for seasons prior to 2012–13, politely inform them that in-game blocked shots and faceoffs were not officially recorded by the NCAA or Northeastern prior to the 2012–13 season.\n"
        "- If a user asks about game-by-game stats prior to October 1999, clarify that digital athletic box score archives begin with the 1999–00 season.\n"
        "- If no records exist for the requested player, opponent, or matchup (e.g., `player_exists: False`, `opponent_exists: False`, or 0 matching games), NEVER claim the player recorded 0 stats in that matchup. Instead, clearly state that you didn't find any records for that player and/or against that school in the historical dataset (1999–present), and ask the user to confirm the player or school name.\n"
        "- NEVER mention internal variable names like `df1`, `df2`, `df3`, `df4`, `df5`, `df6`, `df7`, `df8`, `player_exists`, `opponent_exists`, pandas DataFrames, CSV files, or Python code.\n"
        "- Instead, refer naturally to 'skater statistics', 'goalie statistics', 'scoring summary', 'penalty infractions', 'game results & overtime', 'shootout attempts', 'team rosters & captaincy history', or 'cumulative season & Hockey East statistics' from Northeastern Athletics archives.\n"
        "- If the user is just saying hello or asking what you can do, greet them warmly and suggest a few exciting example questions (e.g., 'Who were the captains and alternate captains in 2025-26, and how many points did they score?', 'Which captain had the highest-scoring season since 1999?', 'Who scored the game-winning goal against BU in the Beanpot?', 'How many Hockey East conference points did Aidan McDonough have?', or 'How many shutouts did Devon Levi record?')."
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
if prompt := st.chat_input("e.g. Who scored the most points as a captain, or who scored the GWG against BC in 2023?"):
    prior_history = list(st.session_state.messages)
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar=assistant_avatar):
        with st.spinner("Querying the historical archives..."):
            try:
                response = answer_question(
                    prompt,
                    df_skaters,
                    df_goalies,
                    df_goals,
                    df_penalties,
                    df_games,
                    df_shootouts,
                    df_rosters,
                    df_season_stats,
                    chat_history=prior_history,
                )
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
            except Exception as e:
                error_msg = f"Sorry, I encountered an error running that calculation: {e}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})

