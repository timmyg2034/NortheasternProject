"""Core data loading, cleaning, and Gemini analytics engine for Northeastern Men's Hockey."""

from __future__ import annotations

import ast
import contextlib
import io
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from langchain_google_genai import ChatGoogleGenerativeAI

ROSTER_COLUMNS = [
    "season", "jersey_number", "player_name", "captain_role", "is_captain",
    "is_alternate_captain", "is_leadership", "position", "class_year",
    "height", "height_inches", "weight", "shoots", "hometown",
    "previous_team", "previous_school", "major", "head_coach", "roster_url", "image_url",
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

MODEL_LADDER = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-3-flash",
    "gemini-2.5-flash",
]

_OPPONENT_REPLACEMENTS = {
    "University Of Maine": "Maine",
    "Univ. Of Maine": "Maine",
    "Rv Maine": "Maine",
    "University Of Connecticut": "Connecticut",
    "University Of Massachusetts Lowell": "Massachusetts Lowell",
    "Massachusetts-Amherst": "Massachusetts",
    "University Of Massachusetts": "Massachusetts",
    "University Of New Hampshire": "New Hampshire",
    "U. Of New Hampshire": "New Hampshire",
    "University Of Denver": "Denver",
    "University Of Vermont": "Vermont",
    "Providence College": "Providence",
    "Merrimack College": "Merrimack",
    "Quinnipiac University": "Quinnipiac",
    "Quinnipiac University (Exh)": "Quinnipiac",
    "Stonehill College": "Stonehill",
    "Union College": "Union",
    "Bentley University": "Bentley",
    "Brown University": "Brown",
    "Colgate University": "Colgate",
    "Harvard University": "Harvard",
    "Alabama-Huntsville": "Alabama Huntsville",
    "Alaska-Anchorage": "Alaska Anchorage",
    "University Of Alaska Anchorage": "Alaska Anchorage",
    "Minnesota-Duluth": "Minnesota Duluth",
    "Army West Point": "Army",
    "Harvard (Exh)": "Harvard",
    "Harvard (Championship Game)": "Harvard",
    "Quinnipiac (Exh)": "Quinnipiac",
    "Simon Fraser (Exh)": "Simon Fraser",
    "Prince Edward Island (Exh)": "Prince Edward Island",
    "Dalhousie University (Exh)": "Dalhousie University",
    "Acadia (Exh)": "Acadia",
}


def clean_opponent_name(name: Any) -> str:
    """Standardize opponent school names across legacy and modern box scores."""
    text = str(name).strip()
    text = re.sub(r"^(?:#|No\.\s*)\d+(?:/(?:\d+|rv|RV))?(?:\s+\[\d+\])?\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\[\d+\]\s+", "", text)
    text = re.sub(r"\s*\(exh\.?\)\s*$", " (Exh)", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\(Championship Game\)\s*$", "", text, flags=re.IGNORECASE)
    text = text.replace("UMass Lowell", "Massachusetts Lowell")
    text = text.replace("UMASS LOWELL", "Massachusetts Lowell")
    text = text.replace("UMass-Lowell", "Massachusetts Lowell")
    text = text.replace("UMass", "Massachusetts")
    text = text.replace("UConn", "Connecticut")
    text = text.replace("UNH", "New Hampshire")
    text = text.replace("Rpi", "Rensselaer")
    text = text.replace("RPI", "Rensselaer")
    text = text.title()
    text = text.replace("Aic", "AIC").replace("Rit", "RIT")
    return _OPPONENT_REPLACEMENTS.get(text, text)


def clean_person_name(name: Any) -> str:
    """Normalize 'Last, First' or prefixed player names into 'First Last'."""
    text = str(name).strip()
    text = re.sub(r"^[*\s\d]+", "", text).strip()
    if "," in text:
        parts = [p.strip() for p in text.split(",", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            return f"{parts[1]} {parts[0]}"
    return text


def clean_jersey_number(val: Any) -> str:
    """Strip trailing .0 from numeric jersey numbers while preserving blanks."""
    if val is None or pd.isna(val):
        return ""
    text = str(val).strip()
    if not text or text.lower() == "nan":
        return ""
    if re.fullmatch(r"\d+\.0+", text):
        return text.split(".", 1)[0]
    return text


def standardize_date(value: Any) -> str:
    """Convert raw box score date strings into ISO YYYY-MM-DD."""
    if not value or pd.isna(value):
        return ""
    text = str(value).strip()
    if text == "Dec. 29, 200":
        return "2000-12-29"
    if text.startswith("Oct.27,"):
        text = text.replace("Oct.27,", "Oct. 27,")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y", "%b. %d, %Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return text


def date_to_season(date_str: str) -> str:
    """Map an ISO date string to its NCAA hockey season string (e.g., '2025-26')."""
    if not date_str or len(str(date_str)) < 7:
        return ""
    try:
        yr = int(str(date_str)[:4])
        mo = int(str(date_str)[5:7])
        if mo >= 8:
            return f"{yr}-{str(yr + 1)[-2:]}"
        return f"{yr - 1}-{str(yr)[-2:]}"
    except Exception:
        return ""


@dataclass
class HockeyDatasets:
    """Container for all 8 cleaned Northeastern Men's Hockey DataFrames."""

    skaters: pd.DataFrame
    goalies: pd.DataFrame
    goals: pd.DataFrame
    penalties: pd.DataFrame
    games: pd.DataFrame
    shootouts: pd.DataFrame
    rosters: pd.DataFrame
    season_stats: pd.DataFrame
    all_opponents: list[str]
    available_seasons: list[str]


def _read_csv_if_exists(path: Path, default_columns: list[str] | None = None) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path)
    if default_columns is not None:
        return pd.DataFrame(columns=default_columns)
    return pd.DataFrame()


def load_datasets(data_dir: Path | str = ".") -> HockeyDatasets:
    """Load, clean, and standardize all 8 Northeastern hockey CSV datasets."""
    root = Path(data_dir)
    skater_df = pd.read_csv(root / "northeastern_hockey_stats_mcp.csv")
    goalie_df = pd.read_csv(root / "northeastern_goalie_stats.csv")
    goals_df = _read_csv_if_exists(root / "northeastern_goal_events.csv")
    penalties_df = _read_csv_if_exists(root / "northeastern_penalty_events.csv")
    games_df = _read_csv_if_exists(root / "northeastern_game_results.csv")
    shootouts_df = _read_csv_if_exists(root / "northeastern_shootout_events.csv")
    rosters_df = _read_csv_if_exists(root / "northeastern_rosters.csv", ROSTER_COLUMNS)
    season_stats_df = _read_csv_if_exists(root / "northeastern_season_stats.csv", SEASON_STATS_COLUMNS)

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
    for col in [
        "nu_goals", "opp_goals", "goals", "assists", "points", "shots", "plus_minus",
        "penalties", "penalty_minutes", "faceoffs_won", "faceoffs_lost", "blocked_shots", "gwg",
    ]:
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
            goals_df["team"] = goals_df["team"].fillna("").apply(
                lambda x: clean_opponent_name(x) if x != "Northeastern" else x
            )
        for col in ["scorer", "primary_assist", "secondary_assist"]:
            if col in goals_df.columns:
                goals_df[col] = goals_df[col].fillna("").apply(clean_person_name)
        for col in ["time_seconds", "seconds_remaining", "is_gwg", "nu_score_after", "opp_score_after"]:
            if col in goals_df.columns:
                goals_df[col] = pd.to_numeric(goals_df[col], errors="coerce").fillna(0)

    # Clean penalties
    if not penalties_df.empty:
        if "opponent" in penalties_df.columns:
            penalties_df["opponent"] = penalties_df["opponent"].fillna("").apply(clean_opponent_name)
        if "team" in penalties_df.columns:
            penalties_df["team"] = penalties_df["team"].fillna("").apply(
                lambda x: clean_opponent_name(x) if x != "Northeastern" else x
            )
        if "player_name" in penalties_df.columns:
            penalties_df["player_name"] = penalties_df["player_name"].fillna("").apply(clean_person_name)
        penalties_df = penalties_df[
            ~penalties_df["player_name"].str.upper().isin(["TEAM", "TM", "BENCH", "TEAM BENCH", "TEAM PENALTY"])
            & ~penalties_df["player_name"].str.startswith(":")
            & (penalties_df["player_name"] != "st")
        ].copy()
        if "penalty_minutes" in penalties_df.columns:
            penalties_df["penalty_minutes"] = pd.to_numeric(penalties_df["penalty_minutes"], errors="coerce").fillna(2)
        if "infraction" in penalties_df.columns:
            penalties_df["infraction"] = (
                penalties_df["infraction"].fillna("").astype(str).str.strip().str.upper()
                .str.replace("CROSS CHECKING", "CROSS-CHECKING")
            )

    # Clean game results
    if not games_df.empty:
        games_df = games_df[
            games_df["opponent"].astype(str).str.strip().ne("Unknown")
            & games_df["date"].astype(str).str.strip().ne("")
        ].copy()
        if "opponent" in games_df.columns:
            games_df["opponent"] = games_df["opponent"].fillna("").apply(clean_opponent_name)
        if "shutout_team" in games_df.columns:
            games_df["shutout_team"] = games_df["shutout_team"].fillna("").apply(
                lambda x: clean_opponent_name(x) if x not in ["Northeastern", "None", "Both (0-0 Tie)"] else x
            )
        if "shootout_winner" in games_df.columns:
            games_df["shootout_winner"] = games_df["shootout_winner"].fillna("None").apply(
                lambda x: clean_opponent_name(x) if x not in ["Northeastern", "None"] else x
            )
        for col in ["nu_goals", "opp_goals", "is_overtime", "is_shootout", "is_shutout"]:
            if col in games_df.columns:
                games_df[col] = pd.to_numeric(games_df[col], errors="coerce").fillna(0)

    # Clean shootout events
    if not shootouts_df.empty:
        if "opponent" in shootouts_df.columns:
            shootouts_df["opponent"] = shootouts_df["opponent"].fillna("").apply(clean_opponent_name)
        if "shooter_team" in shootouts_df.columns:
            shootouts_df["shooter_team"] = shootouts_df["shooter_team"].fillna("").apply(
                lambda x: clean_opponent_name(x) if x != "Northeastern" else x
            )
        if "goalie_team" in shootouts_df.columns:
            shootouts_df["goalie_team"] = shootouts_df["goalie_team"].fillna("").apply(
                lambda x: clean_opponent_name(x) if x != "Northeastern" else x
            )
        if "shootout_winner" in shootouts_df.columns:
            shootouts_df["shootout_winner"] = shootouts_df["shootout_winner"].fillna("None").apply(
                lambda x: clean_opponent_name(x) if x not in ["Northeastern", "None"] else x
            )
        for col in ["shooter_name", "goalie_name"]:
            if col in shootouts_df.columns:
                shootouts_df[col] = shootouts_df[col].fillna("").apply(clean_person_name)
        if "round" in shootouts_df.columns:
            shootouts_df["round"] = pd.to_numeric(shootouts_df["round"], errors="coerce").fillna(1)
        if "is_shootout_winner" in shootouts_df.columns:
            shootouts_df["is_shootout_winner"] = pd.to_numeric(
                shootouts_df["is_shootout_winner"], errors="coerce"
            ).fillna(0)

    # Clean rosters
    if not rosters_df.empty:
        if "player_name" in rosters_df.columns:
            rosters_df["player_name"] = rosters_df["player_name"].fillna("").apply(clean_person_name)
        if "jersey_number" in rosters_df.columns:
            rosters_df["jersey_number"] = rosters_df["jersey_number"].apply(clean_jersey_number)
        for col in [
            "season", "captain_role", "position", "class_year", "height",
            "shoots", "hometown", "previous_team", "previous_school", "major", "head_coach", "roster_url", "image_url",
        ]:
            if col in rosters_df.columns:
                rosters_df[col] = rosters_df[col].fillna("None" if col == "captain_role" else "").astype(str)
        for col in ["is_captain", "is_alternate_captain", "is_leadership", "height_inches", "weight"]:
            if col in rosters_df.columns:
                rosters_df[col] = pd.to_numeric(rosters_df[col], errors="coerce").fillna(0)

    # Clean cumulative season stats
    if not season_stats_df.empty:
        if "player_name" in season_stats_df.columns:
            season_stats_df["player_name"] = season_stats_df["player_name"].fillna("").apply(clean_person_name)
        if "jersey_number" in season_stats_df.columns:
            season_stats_df["jersey_number"] = season_stats_df["jersey_number"].apply(clean_jersey_number)
        for col in [
            "season", "captain_role", "position", "class_year", "height",
            "shoots", "hometown", "previous_team", "major", "head_coach",
            "goalie_minutes", "conf_goalie_minutes", "stats_url",
        ]:
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

    # Standardize dates and sort chronologically
    for df in [skater_df, goalie_df, goals_df, penalties_df, games_df, shootouts_df]:
        if not df.empty and "date" in df.columns:
            df["date"] = df["date"].apply(standardize_date)
            if "season" not in df.columns:
                df["season"] = df["date"].apply(date_to_season)
            df.sort_values("date", kind="mergesort", inplace=True)
            df.reset_index(drop=True, inplace=True)

    all_opponents = sorted(
        set(skater_df["opponent"].dropna().unique())
        | set(goalie_df["opponent"].dropna().unique())
        | (set(games_df["opponent"].dropna().unique()) if not games_df.empty else set())
    )
    all_opponents = [opp for opp in all_opponents if opp]

    seasons_set = set()
    for df in [games_df, rosters_df, season_stats_df]:
        if not df.empty and "season" in df.columns:
            seasons_set.update(s for s in df["season"].dropna().unique() if s)
    available_seasons = sorted(seasons_set, reverse=True)

    return HockeyDatasets(
        skaters=skater_df,
        goalies=goalie_df,
        goals=goals_df,
        penalties=penalties_df,
        games=games_df,
        shootouts=shootouts_df,
        rosters=rosters_df,
        season_stats=season_stats_df,
        all_opponents=all_opponents,
        available_seasons=available_seasons,
    )


def build_llm(api_key: str):
    """Initialize Gemini LLM with the multi-model fallback ladder."""
    primary = ChatGoogleGenerativeAI(
        model=MODEL_LADDER[0],
        google_api_key=api_key,
        temperature=0,
    )
    fallbacks = [
        ChatGoogleGenerativeAI(model=m, google_api_key=api_key, temperature=0)
        for m in MODEL_LADDER[1:]
    ]
    return primary.with_fallbacks(fallbacks)


def message_to_text(msg: Any) -> str:
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


def extract_python_code(text: Any) -> str:
    if not isinstance(text, str):
        text = message_to_text(text)
    match = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.strip()


_ALLOWED_IMPORTS = {"pandas": pd, "re": re}

_FORBIDDEN_CALL_NAMES = {
    "eval", "exec", "compile", "open", "input", "breakpoint", "help",
    "globals", "locals", "vars", "dir", "getattr", "setattr", "delattr",
    "__import__", "memoryview", "classmethod", "staticmethod", "property", "super",
}

_FORBIDDEN_ATTR_NAMES = {
    "to_csv", "to_excel", "to_parquet", "to_pickle", "to_sql", "to_feather",
    "to_hdf", "to_orc", "to_stata", "read_csv", "read_excel", "read_parquet",
    "read_pickle", "read_sql", "read_sql_table", "read_sql_query", "read_table",
    "read_fwf", "read_clipboard", "read_gbq", "read_hdf", "read_html",
    "read_json", "read_orc", "read_sas", "read_spss", "read_stata", "read_xml",
    "eval", "query", "system", "popen", "remove", "unlink", "rmdir",
}


def _safe_import(name: str, globals: Any = None, locals: Any = None, fromlist: Any = (), level: int = 0) -> Any:
    root_mod = str(name).split(".")[0]
    if root_mod in _ALLOWED_IMPORTS:
        return _ALLOWED_IMPORTS[root_mod]
    raise ImportError(f"Import of '{name}' is not permitted in the analytics sandbox.")


_SAFE_BUILTINS = {
    "__import__": _safe_import,
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "format": format,
    "frozenset": frozenset,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "print": print,
    "range": range,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "True": True,
    "False": False,
    "None": None,
    "Exception": Exception,
    "ValueError": ValueError,
    "KeyError": KeyError,
    "IndexError": IndexError,
    "TypeError": TypeError,
    "ZeroDivisionError": ZeroDivisionError,
}


def _validate_safe_ast(tree: ast.AST) -> None:
    """Validate that generated Python AST contains only safe data-query operations."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            else:
                names = [(node.module or "").split(".")[0]]
            for mod_name in names:
                if mod_name not in _ALLOWED_IMPORTS:
                    raise ValueError(f"Disallowed module import: {mod_name}")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("_") or node.attr in _FORBIDDEN_ATTR_NAMES:
                raise ValueError(f"Disallowed attribute access: {node.attr}")
        elif isinstance(node, ast.Name):
            if node.id.startswith("__") or node.id in _FORBIDDEN_CALL_NAMES:
                raise ValueError(f"Disallowed identifier: {node.id}")


def run_python_code(code: str, datasets: HockeyDatasets) -> str:
    """Execute generated pandas query code inside a restricted AST & builtins sandbox."""
    if len(code) > 8000:
        raise ValueError("Generated code exceeds maximum allowed length.")

    pd.set_option("display.max_colwidth", None)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 1000)
    pd.set_option("display.max_rows", 200)

    tree = ast.parse(code, mode="exec")
    _validate_safe_ast(tree)

    local_env = {
        "__builtins__": _SAFE_BUILTINS,
        "df1": datasets.skaters.copy(deep=False),
        "df2": datasets.goalies.copy(deep=False),
        "df3": datasets.goals.copy(deep=False),
        "df4": datasets.penalties.copy(deep=False),
        "df5": datasets.games.copy(deep=False),
        "df6": datasets.shootouts.copy(deep=False),
        "df7": datasets.rosters.copy(deep=False),
        "df8": datasets.season_stats.copy(deep=False),
        "pd": pd,
        "re": re,
    }
    stdout_buf = io.StringIO()
    with contextlib.redirect_stdout(stdout_buf):
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last_expr = ast.Expression(tree.body.pop().value)
            if tree.body:
                exec(compile(tree, "<ast>", "exec"), local_env, local_env)
            val = eval(compile(last_expr, "<ast>", "eval"), local_env, local_env)
            if val is not None:
                print(val)
        else:
            exec(compile(tree, "<ast>", "exec"), local_env, local_env)
    output = stdout_buf.getvalue().strip()
    if len(output) > 12000:
        output = output[:12000] + "\n...[truncated]"
    return output



def format_chat_history(messages: list[dict[str, str]], max_turns: int = 8) -> str:
    if not messages:
        return "None"
    recent = messages[-max_turns:]
    lines = []
    for m in recent:
        role = "User" if m.get("role") == "user" else "Assistant"
        lines.append(f"{role}: {m.get('content', '')}")
    return "\n".join(lines)


def classify_api_error(err: Exception) -> tuple[str, str]:
    """
    Classify an API exception into ('per_minute', msg), ('daily', msg), or ('generic', msg).
    Provides actionable, clear user messages for chat banners.
    """
    msg = str(err)
    msg_lower = msg.lower()

    is_exhausted = any(k in msg_lower for k in [
        "429",
        "resourceexhausted",
        "resource_exhausted",
        "quota",
        "rate limit",
        "ratelimit",
        "too many requests",
        "exhausted",
    ])

    if not is_exhausted:
        return "generic", f"Sorry, I encountered an error running that calculation: {err}"

    # Explicit daily quota indicators
    is_daily = any(k in msg_lower for k in [
        "per day",
        "per_day",
        "requests per day",
        "requestsperday",
        "daily",
        "day limit",
        "rpd",
        "free tier limit",
    ])

    # Per-minute rate limit indicators
    is_per_minute = any(k in msg_lower for k in [
        "per minute",
        "per_minute",
        "requests per minute",
        "requestsperminute",
        "tokens per minute",
        "tokensperminute",
        "rpm",
        "tpm",
        "rate limit",
        "ratelimit",
        "retry after",
        "retry_after",
    ])

    if is_per_minute and not is_daily:
        friendly = (
            "⏳ **High Traffic Alert — Per-Minute Rate Limit Reached**\n\n"
            "The assistant has temporarily reached Google Gemini's per-minute request rate limit across our AI models.\n\n"
            "⏱️ **What to do:** Please wait **30 to 60 seconds** and ask your question again — it will resume automatically!"
        )
        return "per_minute", friendly

    # Daily / general quota limit
    friendly = (
        "🏒 **Daily API Quota Limit Reached**\n\n"
        "The Northeastern Men's Hockey assistant has reached its free daily Google Gemini API quota across all fallback models.\n\n"
        "🌅 **What to do:** The shared daily quota resets automatically every day at midnight Pacific Time (3:00 AM Eastern Time). Please check back then!"
    )
    return "daily", friendly


class ResponseCache:
    """Thread-safe TTL cache for standalone (no-history) chat questions."""

    def __init__(self, ttl_seconds: int = 86400, max_entries: int = 1000) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._store: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _normalize(question: str) -> str:
        p = question.strip().lower()
        p = re.sub(r"[?!.,;:]+$", "", p).strip()
        return re.sub(r"\s+", " ", p)

    def get(self, question: str) -> str | None:
        key = self._normalize(question)
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            expires_at, answer = entry
            if time.time() > expires_at:
                self._store.pop(key, None)
                return None
            return answer

    def set(self, question: str, answer: str) -> None:
        key = self._normalize(question)
        with self._lock:
            if len(self._store) >= self._max_entries:
                oldest_key = min(self._store, key=lambda k: self._store[k][0])
                self._store.pop(oldest_key, None)
            self._store[key] = (time.time() + self._ttl, answer)



def answer_question(
    question: str,
    datasets: HockeyDatasets,
    llm: Any,
    chat_history: list[dict[str, str]] | None = None,
    cache: ResponseCache | None = None,
    page_context: str | None = None,
) -> tuple[str, bool]:
    """Run the two-turn Gemini + pandas code-execution loop.

    Returns (answer_markdown, from_cache).
    """
    use_cache = cache is not None and not chat_history and not page_context
    if use_cache:
        cached = cache.get(question)
        if cached is not None:
            return cached, True

    history_text = format_chat_history(chat_history or [])
    context_line = f"Current Page Context: {page_context}\n\n" if page_context else ""
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
        "3. `df3` (scoring events & timeline — BOTH teams): columns = ['date', 'season', 'opponent', 'period', 'time', 'time_seconds', 'seconds_remaining', 'team', 'scorer', 'primary_assist', 'secondary_assist', 'strength', 'is_gwg', 'nu_score_after', 'opp_score_after', 'boxscore_url']\n"
        "   - `team`: 'Northeastern' for NU goals, or the opponent school name for opponent goals. ALWAYS filter `team == 'Northeastern'` unless the user explicitly asks about opponent scorers!\n"
        "   - `period`: Formatted as strings '1st', '2nd', '3rd', 'OT'. For third period, filter with `'3rd'`.\n"
        "   - `time`: Official box score timestamp showing TIME ELAPSED in the period ('MM:SS' like '19:59', or 'MM:SS.t' with tenths of a second in the final minute of modern games like '19:59.8', '19:59.7', '19:59.4').\n"
        "   - `time_seconds`: Float of seconds elapsed in the period (0.0 to 1200.0 in regulation periods '1st'/'2nd'/'3rd'; 0.0 to 300.0 in regular-season 'OT', or up to 1200.0 in 20-minute playoff 'OT'). E.g. '19:59' = 1199.0, '19:59.8' = 1199.8.\n"
        "   - `seconds_remaining`: Float of seconds remaining on the game clock in that period (e.g. 1.0 for '19:59', 0.2 for '19:59.8', 0.3 for '19:59.7', 0.6 for '19:59.4').\n"
        "   - `strength`: 'EV', 'PP', 'SH', 'EN', 'EX'\n"
        "   - `is_gwg`: 1 if this specific goal was the official Game-Winning Goal, 0 otherwise\n"
        "4. `df4` (penalty events & infractions — BOTH teams): columns = ['date', 'season', 'opponent', 'period', 'time', 'team', 'player_name', 'penalty_minutes', 'infraction', 'boxscore_url']\n"
        "   - `team`: 'Northeastern' for NU penalties, or the opponent school name for opponent penalties. ALWAYS filter `team == 'Northeastern'` unless the user explicitly asks about opponent penalties!\n"
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
        f"Valid standardized `opponent` names in the dataset: {datasets.all_opponents}\n\n"
        "Important conventions:\n"
        "- All player names are formatted as 'First Last' (e.g., 'Devon Levi', 'Adam Gaudette', 'Hunter McDonald', 'Aidan McDonough'). Always filter with `.str.contains(..., case=False, na=False)`.\n"
        "- `opponent` uses standardized school names (e.g., 'Boston University' for BU, 'Boston College' for BC, 'Massachusetts' for UMass, 'Massachusetts Lowell' for UMass Lowell / UML, 'Connecticut' for UConn, 'New Hampshire' for UNH, 'Rensselaer' for RPI).\n"
        "- ALL 8 DATAFRAMES HAVE A `season` COLUMN: `season` is available on `df1`, `df2`, `df3`, `df4`, `df5`, `df6`, `df7`, and `df8`! Season values are standardized 7-character strings formatted as `'YYYY-YY'` (e.g. `'2015-16'`, `'2023-24'`, `'1999-00'`).\n"
        "- SEASON STRINGS & YEAR NORMALIZATION: If a user asks about `'2015-2016'`, `'2015-2016 season'`, `'2015'`, or `'2016'`, ALWAYS normalize the input to `'YYYY-YY'` (e.g., `'2015-2016'` -> `'2015-16'`) or use `.str.startswith('2015')` or `.isin(['2015-16', '2015-2016'])`. Never assume exact string equality against `'YYYY-YYYY'`!\n"
        "- SINGLE-YEAR SEASON CONVENTION (e.g. '2015 season', 'in 2015', '2015 captains'):\n"
        "  - Most users mean the season STARTING in that year (e.g., '2015' means the 2015-16 season; '2023' means the 2023-24 season). Treat `primary_season = f'{yr}-{str(yr+1)[-2:]}'` (e.g. '2015-16') as the main season.\n"
        "  - Also retrieve the prior season ending in that year: `prior_season = f'{yr-1}-{str(yr)[-2:]}'` (e.g. '2014-15') so the synthesis can present the primary season first and mention the alternate season.\n"
        "  - In your python code, print results for `primary_season` first clearly labeled, followed by `prior_season` labeled.\n"
        "- CAPTAINS (`C`) & ALTERNATE / ASSISTANT CAPTAINS (`A`):\n"
        "  - Use `df7` (rosters) and `df8` (cumulative season stats) for season-level or career captain/alternate captain questions.\n"
        "  - Filter Captains with `captain_role == 'C'` (or `is_captain == 1`), Alternate/Assistant Captains with `captain_role == 'A'` (or `is_alternate_captain == 1`), and all Leadership (Captains + Alternate Captains) with `captain_role.isin(['C', 'A'])` (or `is_leadership == 1`).\n"
        "  - For single-game or opponent-specific captain/alternate captain questions, use `df1`.\n"
        "- CUMULATIVE SEASON STATS vs GAME-BY-GAME LOGS:\n"
        "  - Prefer `df8` for full-season totals, career totals across seasons, Hockey East conference stats (`conf_*`), games played (`gp`), games started (`goalie_gs`), shooting percentage (`shot_pct`), power-play/shorthanded/first/game-tying/overtime/unassisted goals, hat tricks, GAA, and stats broken down by position, class year, or head coach.\n"
        "  - Prefer `df1`–`df6` when filtering by a specific `opponent`, `date`, game outcome, period, timestamp, penalty infraction, or shootout.\n"
        "- ROSTER & BIOGRAPHICAL QUERIES (`df7`):\n"
        "  - Use `df7` for jersey numbers, height, weight, shooting/catching hand, hometown, previous team/school, academic major, and head coach.\n"
        "- In `df2`, `decision` is 'W' for win, 'L' for loss, 'T' for tie.\n"
        "- In `df3` and `df4`, `period` values are strings: `'1st'`, `'2nd'`, `'3rd'`, `'OT'`.\n"
        "- TIMED GOALS & LAST-SECOND / BUZZER-BEATER GOALS: NEVER use exact equality `df3['time'] == '19:59'` or `int()` on split time strings. Always use `seconds_remaining` and `time_seconds` (or `.str.startswith()`).\n"
        "- NORTHEASTERN PLAYERS ONLY BY DEFAULT (`df3`, `df4`, `df6`): `df3` (`team`), `df4` (`team`), and `df6` (`shooter_team`) contain events for BOTH Northeastern AND the opponent. Unless the user explicitly asks about opponent players or goals/penalties *against* Northeastern, ALWAYS filter `df3['team'] == 'Northeastern'`, `df4['team'] == 'Northeastern'`, and `df6['shooter_team'] == 'Northeastern'`. Never present opponent players as Northeastern players!\n"
        "- PENALTIES & BENCH MINORS: Never include 'TEAM', 'Team', or 'TM' as a player.\n"
        "- SHOOTOUT WINNERS & GOALIE SHOOTOUT SV%: Always filter `df6['is_shootout_winner'] == 1` for deciding shootout goals (never `result == 'MADE'` alone). For Northeastern goalie shootout save percentage, filter `df6[df6['goalie_team'] == 'Northeastern']` where `result == 'MISSED'` is a save and `result == 'MADE'` is a goal allowed.\n"
        "- MULTI-GOAL, HAT TRICK & MULTI-POINT GAMES: From `df1`, use `df1['goals'] >= 2` for multi-goal games, `df1['goals'] >= 3` for hat tricks, and `df1['points'] >= 2` for multi-point games (or `>= 3` for 3+ point games).\n"
        "- STREAKS & CONSECUTIVE GAMES: Sort `df1` (player streaks) or `df5` (team win/unbeaten streaks) ascending by `date` (`YYYY-MM-DD`) and compute consecutive runs in Python.\n"
        "- SITUATIONAL TEAM RECORDS: For 1-goal games, use `abs(df5['nu_goals'] - df5['opp_goals']) == 1`. For record when scoring first, sort `df3` by `['date', 'period', 'time_seconds']` (using period order 1st < 2nd < 3rd < OT) to find the first goal of each game (`team == 'Northeastern'`), then join with `df5`.\n"
        "- DATES & CHRONOLOGICAL ORDERING: `date` is standardized in ISO format `'YYYY-MM-DD'` and pre-sorted ascending (1999 to present).\n"
        "- CONVERSATION CONTEXT: Use the Recent Conversation History below to resolve pronouns or omitted context.\n"
        "- CRITICAL EXISTENCE CHECK: Always check if a requested player and/or opponent actually exists (`player_exists: True/False`, `opponent_exists: True/False`) before summing/counting.\n"
        "- STRICT TOPIC SCOPE RULE (NORTHEASTERN MEN'S HOCKEY ONLY): You ONLY answer questions about Northeastern Men's Hockey (games, players, goalies, coaches, rosters, captains, stats, box scores, penalties, shootouts, Hockey East/Beanpot/NCAA matchups, or what this assistant can do) and brief greetings. If the user asks for anything unrelated to Northeastern Men's Hockey — such as writing a Python script or code, general programming help, math homework, recipes, politics, or unrelated trivia — do NOT fulfill the request. Simply output:\n"
        "```python\nprint('OFF_TOPIC_REQUEST')\n```\n\n"
        f"{context_line}"
        f"Recent Conversation History:\n{history_text}\n\n"
        "Write ONLY a single ```python ... ``` code block that performs these checks and uses `print()` to output the results.\n\n"
        f"Current User Question: {question}"
    )

    try:
        msg = llm.invoke(code_prompt)
    except Exception as llm_err:
        _, friendly_msg = classify_api_error(llm_err)
        return friendly_msg, False

    code = extract_python_code(message_to_text(msg))

    try:
        execution_output = run_python_code(code, datasets)
    except Exception as err:
        retry_prompt = (
            f"{code_prompt}\n\nYour previous code:\n```python\n{code}\n```\n"
            f"raised this error: {err}\n"
            "Please output ONLY the corrected ```python ... ``` code block with valid Python syntax."
        )
        try:
            msg_retry = llm.invoke(retry_prompt)
            code = extract_python_code(message_to_text(msg_retry))
            try:
                execution_output = run_python_code(code, datasets)
            except Exception as retry_err:
                execution_output = f"Execution error: {retry_err}"
        except Exception as retry_llm_err:
            err_type, friendly_msg = classify_api_error(retry_llm_err)
            if err_type in ("per_minute", "daily"):
                return friendly_msg, False
            execution_output = f"Execution error: {err}"

    if execution_output.strip() == "OFF_TOPIC_REQUEST":
        off_topic_msg = (
            "🐾 I'm **Ask Paws**, and I'm strictly dedicated to **Northeastern Men's Hockey** statistics, "
            "rosters, game results, and team history (1999–present)!\n\n"
            "I can't help with general coding scripts or unrelated topics, but feel free to ask me something like:\n"
            "- *Who were the captains in 2025-26, and how many points did they score?*\n"
            "- *Who scored the most recent game-winning goal against Boston University?*\n"
            "- *How many shutouts did Devon Levi record?*"
        )
        if use_cache:
            cache.set(question, off_topic_msg)
        return off_topic_msg, False

    final_prompt = (
        "You are a friendly, knowledgeable Northeastern Men's Hockey statistics assistant speaking to hockey fans.\n"
        f"{context_line}"
        f"Recent Conversation History:\n{history_text}\n\n"
        f"Current User Message: {question}\n\n"
        f"Computed Result from Historical Dataset (1999–present):\n{execution_output}\n\n"
        "Instructions:\n"
        "- STRICT TOPIC SCOPE RULE: You ONLY answer questions about Northeastern Men's Hockey (players, goalies, rosters, coaches, games, stats, box scores, rivalries, and what this assistant can do). NEVER write general-purpose code/Python scripts, answer homework, or fulfill off-topic requests. If the user's message is not about Northeastern Men's Hockey, politely decline and suggest a Northeastern Hockey question instead.\n"
        "- Provide a clear, accurate, and conversational answer based strictly on the computed result above, taking into account the conversation history.\n"
        "- SINGLE-YEAR SEASON CONVENTION (e.g. '2015'): Present results for the season STARTING in that year (e.g., 2015–16) first, then add a polite follow-up note offering the prior season (e.g., 2014–15).\n"
        "- STRICT ANTI-HALLUCINATION & FACTUAL GROUNDING RULE: Answer ONLY using facts present in 'Computed Result from Historical Dataset'. NEVER fabricate player names, jersey numbers, captaincy roles, tournament titles, or game results.\n"
        "- If the computed result indicates an execution error, apologize politely and invite the user to clarify or rephrase. NEVER show raw Python errors or variable names like df1-df8.\n"
        "- If a box score URL, roster URL, or season stats URL is available, provide it as a markdown link.\n"
        "- If asked about blocked shots or faceoffs prior to 2012–13, explain they were not officially recorded prior to 2012–13.\n"
        "- If asked about game-by-game stats prior to October 1999, clarify archives begin in 1999–00.\n"
        "- If no records exist (`player_exists: False`, `opponent_exists: False`, or 0 matching games), state clearly that no records were found.\n"
        "- NEVER mention internal variable names like `df1`–`df8`, `player_exists`, `opponent_exists`, pandas DataFrames, CSV files, or Python code.\n"
        "- If the user is just saying hello or asking what you can do, greet them warmly and suggest a few example questions."
    )
    try:
        final_msg = llm.invoke(final_prompt)
        answer = message_to_text(final_msg)
    except Exception as final_err:
        _, friendly_msg = classify_api_error(final_err)
        return friendly_msg, False

    is_quota_exhausted = (
        "Daily API Quota" in answer
        or "High Traffic Alert" in answer
        or "Execution error" in execution_output
    )
    if use_cache and answer and not is_quota_exhausted:
        cache.set(question, answer)

    return answer, False


