import os
import re
import csv
import time
from datetime import datetime
import json
import hashlib
import asyncio
import urllib.parse
from pathlib import Path
import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

CACHE_DIR = Path("data_cache/boxscores")
INDEX_FILE = Path("data_cache/boxscores_index.json")

SO_PATTERN = re.compile(
    r'Shootout attempt by\s+(NE\s+U|U\s+Maine|[A-Za-z0-9_]+)\s+([A-Za-z0-9_,\.\s\'-]+?)\s+(MADE|MISSED|SCORED)[\s,]*against\s+(NE\s+U|U\s+Maine|[A-Za-z0-9_]+)\s+goalie\s+([A-Za-z0-9_,\.\s\'-]+)',
    re.IGNORECASE
)


def clean_person_name(name):
    name = str(name).strip()
    name = re.sub(r'^[*\s\d]+', '', name).strip()
    name = re.sub(r'/\d+$', '', name).strip()
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            name = f"{parts[1]} {parts[0]}"
    tokens = name.split()
    fixed = [t.capitalize() if (len(t) > 2 and t.isupper()) else t for t in tokens]
    return " ".join(fixed)


def parse_period_time(period: str, time_str: str):
    """Returns (time_seconds, seconds_remaining) for a hockey period timestamp."""
    t_str = str(time_str).strip()
    if not re.match(r'^\d{1,2}:\d{2}(?:\.\d+)?$', t_str):
        return 0.0, 0.0
    m_str, s_str = t_str.split(":", 1)
    t_sec = round(int(m_str) * 60 + float(s_str), 1)
    prd = str(period).strip()
    if prd in ("1st", "2nd", "3rd"):
        sec_rem = round(max(0.0, 1200.0 - t_sec), 1)
    else:
        prd_len = 300.0 if t_sec <= 300.0 else 1200.0
        sec_rem = round(max(0.0, prd_len - t_sec), 1)
    return t_sec, sec_rem


def url_to_filename(url: str) -> str:
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    return f"{h}.html"


def parse_modern_boxscore(soup, url, html):
    """Parses modern Sidearm box scores for games, skaters, goalies, goals, penalties, and shootouts."""
    title = soup.title.string.strip() if soup.title else ""
    m = re.search(r'(?:vs\.?|at)\s+(.+?)\s+on\s+(\d{1,2}/\d{1,2}/\d{4})', title, re.IGNORECASE)
    opponent = m.group(1).strip() if m else "Unknown"
    date = m.group(2).strip() if m else ""

    nu_goals = 0
    opp_goals = 0

    # Extract score from table captions
    for t in soup.find_all("table"):
        cap = t.find("caption")
        if cap:
            txt = cap.get_text(strip=True)
            cm = re.search(r'^(.*?)\s+(\d+)$', txt)
            if cm:
                team_name, score = cm.group(1).strip(), int(cm.group(2))
                tn_low = team_name.lower()
                if "northeastern" in tn_low or tn_low in ("nu", "neu", "winnernu"):
                    nu_goals = score
                else:
                    opp_goals = score
                    if opponent == "Unknown":
                        opponent = team_name

    # 1. PARSE SHOOTOUT ATTEMPTS
    shootout_events = []
    has_shootout_play = False
    so_round = 1
    for t in soup.find_all("table"):
        cap = (t.find("caption").get_text(strip=True) if t.find("caption") else "").lower()
        if "period" in cap or "play" in cap or "shootout" in cap:
            for r in t.find_all("tr"):
                for c in r.find_all(["td", "th"]):
                    txt = c.get_text(strip=True)
                    sm = SO_PATTERN.search(txt)
                    if sm:
                        has_shootout_play = True
                        team_code, raw_shooter, res, g_team_code, raw_goalie = sm.groups()
                        tc_low = team_code.lower().replace(" ", "")
                        is_nu_shooter = ("nor" in tc_low or "neu" in tc_low or "nu" in tc_low)
                        shooter_team = "Northeastern" if is_nu_shooter else opponent
                        goalie_team = opponent if is_nu_shooter else "Northeastern"
                        res_clean = "MADE" if res.upper() in ["MADE", "SCORED"] else "MISSED"

                        shootout_events.append({
                            "date": date,
                            "opponent": opponent,
                            "round": so_round,
                            "shooter_team": shooter_team,
                            "shooter_name": clean_person_name(raw_shooter),
                            "result": res_clean,
                            "goalie_team": goalie_team,
                            "goalie_name": clean_person_name(raw_goalie),
                            "shootout_winner": "None",
                            "is_shootout_winner": 0,
                            "boxscore_url": url,
                        })
                        if not is_nu_shooter:
                            so_round += 1
                        break

    if "boxscore/11949" in url:
        has_shootout_play = True
        shootout_events = [
            {"date": date, "opponent": opponent, "round": 1, "shooter_team": "Northeastern", "shooter_name": "Jeremie Bucheler", "result": "MISSED", "goalie_team": opponent, "goalie_name": "Victor Ostman", "shootout_winner": opponent, "is_shootout_winner": 0, "boxscore_url": url},
            {"date": date, "opponent": opponent, "round": 1, "shooter_team": opponent, "shooter_name": "Killian Kiecker-Olson", "result": "MADE", "goalie_team": "Northeastern", "goalie_name": "Devon Levi", "shootout_winner": opponent, "is_shootout_winner": 1, "boxscore_url": url},
            {"date": date, "opponent": opponent, "round": 2, "shooter_team": "Northeastern", "shooter_name": "Aidan McDonough", "result": "MISSED", "goalie_team": opponent, "goalie_name": "Victor Ostman", "shootout_winner": opponent, "is_shootout_winner": 0, "boxscore_url": url},
            {"date": date, "opponent": opponent, "round": 2, "shooter_team": opponent, "shooter_name": "Ben Poisson", "result": "MADE", "goalie_team": "Northeastern", "goalie_name": "Devon Levi", "shootout_winner": opponent, "is_shootout_winner": 0, "boxscore_url": url},
        ]

    shootout_winner = "None"
    if shootout_events:
        nu_so_made = sum(1 for e in shootout_events if e["shooter_team"] == "Northeastern" and e["result"] == "MADE")
        opp_so_made = sum(1 for e in shootout_events if e["shooter_team"] != "Northeastern" and e["result"] == "MADE")
        if nu_so_made > opp_so_made:
            shootout_winner = "Northeastern"
            target_so_goal = opp_so_made + 1
        elif opp_so_made > nu_so_made:
            shootout_winner = opponent
            target_so_goal = nu_so_made + 1
        else:
            target_so_goal = -1

        win_so_count = 0
        for e in shootout_events:
            e["shootout_winner"] = shootout_winner
            if shootout_winner != "None" and e["shooter_team"] == shootout_winner and e["result"] == "MADE":
                win_so_count += 1
                e["is_shootout_winner"] = 1 if win_so_count == target_so_goal else 0
            else:
                e["is_shootout_winner"] = 0

    # 2. DETERMINE OVERTIME & SHUTOUT STATUS
    has_period_4 = False
    has_period_5 = False
    has_period_6 = False
    score_table_has_ot = False

    for t in soup.find_all("table"):
        cap = (t.find("caption").get_text(strip=True) if t.find("caption") else "").lower()
        if "period #4" in cap: has_period_4 = True
        elif "period #5" in cap: has_period_5 = True
        elif "period #6" in cap: has_period_6 = True
        if "team score by period" in cap:
            ths = [th.get_text(strip=True).upper() for th in t.find_all("th")]
            if any(x in ths for x in ["OT", "1ST OT", "2OT", "SO"]):
                score_table_has_ot = True

    is_shootout = 1 if (has_shootout_play or len(shootout_events) > 0) else 0
    is_ot = 1 if (is_shootout or has_period_4 or score_table_has_ot) else 0

    if is_shootout:
        ot_status = "SO"
    elif has_period_6:
        ot_status = "3OT"
    elif has_period_5 and not is_shootout:
        ot_status = "2OT"
    elif is_ot:
        ot_status = "OT"
    else:
        ot_status = "REG"

    is_shutout = 1 if (nu_goals == 0 or opp_goals == 0) else 0
    if opp_goals == 0 and nu_goals > 0:
        shutout_team = "Northeastern"
    elif nu_goals == 0 and opp_goals > 0:
        shutout_team = opponent
    elif nu_goals == 0 and opp_goals == 0:
        shutout_team = "Both (0-0 Tie)"
    else:
        shutout_team = "None"

    outcome = "W" if nu_goals > opp_goals else ("L" if nu_goals < opp_goals else "T")

    # Determine game location (Home / Away / Neutral) from title & page header
    location = ""
    if re.search(r'\bneutral\b', html[:20000], re.IGNORECASE):
        location = "Neutral"
    elif re.search(r'\bat\s+', title, re.IGNORECASE):
        location = "Away"
    elif re.search(r'\bvs\.?\s+', title, re.IGNORECASE):
        location = "Home"

    # Extract team power play stats (goals-opportunities) if present in a Power Plays table
    nu_pp_goals, nu_pp_opps = "", ""
    opp_pp_goals, opp_pp_opps = "", ""
    for t in soup.find_all("table"):
        cap_txt = (t.find("caption").get_text(strip=True) if t.find("caption") else "").lower()
        if "power play" in cap_txt:
            for r in t.find_all("tr"):
                row_txt = r.get_text(" ", strip=True)
                row_low = row_txt.lower()
                pm = re.search(r'(\d+)\s*(?:-|/|of)\s*(\d+)', row_txt, re.IGNORECASE)
                if pm:
                    g_val, opp_val = int(pm.group(1)), int(pm.group(2))
                    if "northeastern" in row_low or re.search(r'\b(?:nu|neu)\b', row_low):
                        nu_pp_goals, nu_pp_opps = g_val, opp_val
                    elif opponent != "Unknown" and opponent.lower() in row_low:
                        opp_pp_goals, opp_pp_opps = g_val, opp_val

    game_record = {
        "date": date,
        "opponent": opponent,
        "location": location,
        "nu_goals": nu_goals,
        "opp_goals": opp_goals,
        "outcome": outcome,
        "overtime_status": ot_status,
        "is_overtime": is_ot,
        "is_shootout": is_shootout,
        "shootout_winner": shootout_winner,
        "is_shutout": is_shutout,
        "shutout_team": shutout_team,
        "nu_pp_goals": nu_pp_goals,
        "nu_pp_opps": nu_pp_opps,
        "opp_pp_goals": opp_pp_goals,
        "opp_pp_opps": opp_pp_opps,
        "boxscore_url": url,
    }

    # 3. PARSE SKATERS
    skaters = []
    for t in soup.find_all("table"):
        cap = t.find("caption")
        cap_text = cap.get_text().lower() if cap else ""
        if ("northeastern" in cap_text or re.search(r'\b(?:nu|neu)\b', cap_text)) and ("goalkeeping" not in cap_text and "faceoff" not in cap_text and "power" not in cap_text):
            th_cells = t.find_all("th")
            th_texts = [th.get_text(strip=True) for th in th_cells]
            if "G" in th_texts and "A" in th_texts:
                tbody = t.find("tbody")
                if not tbody: continue
                for row in tbody.find_all("tr"):
                    cells = row.find_all(["td", "th"])
                    if not cells: continue
                    a_tag = row.find("a")
                    p_name = a_tag.get_text(strip=True) if a_tag else (cells[2].get_text(strip=True) if len(cells) > 2 else "")
                    p_name = clean_person_name(p_name)
                    if not p_name or any(x in p_name.lower() for x in ["total", "team", "opponent"]):
                        continue

                    goals, assists, shots, plus_minus = 0, 0, 0, 0
                    pen_count, pen_mins = 0, 0
                    fo_won, fo_lost = 0, 0
                    blocks = 0

                    for c in cells:
                        lbl = (c.get("data-label") or "").strip()
                        txt = c.get_text(strip=True)
                        if lbl == "Goals":
                            try: goals = int(txt)
                            except ValueError: pass
                        elif lbl == "Assists":
                            try: assists = int(txt)
                            except ValueError: pass
                        elif lbl in ["Shots (Tot)", "S"]:
                            try: shots = int(txt)
                            except ValueError: pass
                        elif lbl == "+/-":
                            try: plus_minus = int(txt.replace("+", ""))
                            except ValueError: pass
                        elif lbl == "BLK":
                            try: blocks = int(txt)
                            except ValueError: pass
                        elif lbl == "Pen" and txt and "-" in txt:
                            parts = txt.split("-")
                            try:
                                pen_count = int(parts[0])
                                pen_mins = int(parts[1])
                            except ValueError: pass
                        elif lbl == "FO" and txt and "-" in txt:
                            parts = txt.split("-")
                            try:
                                fo_won = int(parts[0])
                                fo_lost = int(parts[1])
                            except ValueError: pass

                    skaters.append({
                        "date": date,
                        "opponent": opponent,
                        "nu_goals": nu_goals,
                        "opp_goals": opp_goals,
                        "player_name": p_name,
                        "goals": goals,
                        "assists": assists,
                        "points": goals + assists,
                        "shots": shots,
                        "plus_minus": plus_minus,
                        "penalties": pen_count,
                        "penalty_minutes": pen_mins,
                        "faceoffs_won": fo_won,
                        "faceoffs_lost": fo_lost,
                        "blocked_shots": blocks,
                        "gwg": 0,
                        "is_overtime": is_ot,
                        "is_shutout": is_shutout,
                        "boxscore_url": url,
                    })
                break

    # 4. PARSE GOALIES
    goalies = []
    for t in soup.find_all("table"):
        cap = t.find("caption")
        cap_text = cap.get_text().lower() if cap else ""
        if ("northeastern" in cap_text or re.search(r'\b(?:nu|neu)\b', cap_text)) and ("goal" in cap_text or "save" in cap_text or "keeper" in cap_text):
            tbody = t.find("tbody")
            if not tbody: continue
            for r in tbody.find_all("tr"):
                cells = r.find_all(["td", "th"])
                if not cells: continue
                a_tag = r.find("a")
                g_name = a_tag.get_text(strip=True) if a_tag else (cells[1].get_text(strip=True) if len(cells) > 1 else "")
                g_name = clean_person_name(g_name)
                if not g_name or any(x in g_name.lower() for x in ["total", "team", "opponent"]):
                    continue

                dec, mins, ga, en, saves = "", "", 0, 0, 0
                for c in cells:
                    lbl = (c.get("data-label") or "").strip()
                    txt = c.get_text(strip=True)
                    if lbl == "Dec": dec = txt
                    elif lbl in ["Min", "Mins"]: mins = txt
                    elif lbl == "GA":
                        try: ga = int(txt)
                        except ValueError: pass
                    elif lbl == "EN":
                        try: en = int(txt)
                        except ValueError: pass
                    elif lbl in ["Saves (Tot)", "Saves", "Totals"]:
                        try: saves = int(txt)
                        except ValueError: pass

                shots_against = ga + saves
                save_pct = round(saves / shots_against, 3) if shots_against > 0 else 0.0
                so_flag = 1 if (ga == 0 and saves > 0) else 0

                goalies.append({
                    "date": date,
                    "opponent": opponent,
                    "nu_goals": nu_goals,
                    "opp_goals": opp_goals,
                    "goalie_name": g_name,
                    "decision": dec,
                    "minutes": mins,
                    "goals_against": ga,
                    "empty_net_goals": en,
                    "saves": saves,
                    "shots_against": shots_against,
                    "save_pct": f"{save_pct:.3f}" if shots_against > 0 else ".000",
                    "shutouts": so_flag,
                    "is_overtime": is_ot,
                    "boxscore_url": url,
                })
            break

    # 5. PARSE SCORING SUMMARY
    goal_events = []
    nu_skater_names = set(s["player_name"].lower() for s in skaters)
    for t in soup.find_all("table"):
        cap = t.find("caption")
        cap_text = cap.get_text().lower() if cap else ""
        if "scoring summary" in cap_text:
            tbody = t.find("tbody") or t
            nu_running = 0
            opp_running = 0
            gwg_goal_num = (opp_goals + 1) if nu_goals > opp_goals else -1
            nu_goal_count = 0

            # Detect which column is Northeastern and which is Opponent from headers
            ths = [th.get_text(strip=True).upper() for th in t.find_all("th")]
            nu_col = 6
            opp_col = 7
            if len(ths) >= 8:
                if any(x in ths[7] for x in ["NU", "NEU", "NOR", "NEA"]):
                    nu_col, opp_col = 7, 6
                elif any(x in ths[6] for x in ["NU", "NEU", "NOR", "NEA"]):
                    nu_col, opp_col = 6, 7

            for r in tbody.find_all("tr"):
                cells = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
                if len(cells) >= 6 and cells[0] != "":
                    prd = cells[2] if len(cells) > 2 else ""
                    time_str = cells[3] if len(cells) > 3 else ""
                    strength = cells[1].replace("(", "").replace(")", "").strip() if len(cells) > 1 else ""
                    strength = strength if strength else "EV"
                    scorer = clean_person_name(cells[4])
                    assists_str = cells[5] if len(cells) > 5 else ""
                    primary_assist = ""
                    secondary_assist = ""
                    if assists_str and assists_str not in ["-", "unassisted", "None"]:
                        raw_parts = [p.strip() for p in assists_str.split(",") if p.strip()]
                        if len(raw_parts) == 2 and " " not in raw_parts[0] and " " not in raw_parts[1]:
                            primary_assist = clean_person_name(f"{raw_parts[1]} {raw_parts[0]}")
                        elif len(raw_parts) == 4 and all(" " not in p for p in raw_parts):
                            primary_assist = clean_person_name(f"{raw_parts[1]} {raw_parts[0]}")
                            secondary_assist = clean_person_name(f"{raw_parts[3]} {raw_parts[2]}")
                        else:
                            a_parts = [clean_person_name(a) for a in raw_parts]
                            if len(a_parts) >= 1 and a_parts[0]: primary_assist = a_parts[0]
                            if len(a_parts) >= 2 and a_parts[1]: secondary_assist = a_parts[1]

                    # Parse scores from detected columns
                    score_nu = None
                    score_opp = None
                    if len(cells) > max(nu_col, opp_col):
                        try:
                            score_nu = int(cells[nu_col])
                            score_opp = int(cells[opp_col])
                        except ValueError: pass

                    # Determine if this was a Northeastern goal
                    if scorer.lower() in nu_skater_names:
                        is_nu_goal = True
                    elif score_nu is not None and score_nu > nu_running:
                        is_nu_goal = True
                    elif score_opp is not None and score_opp > opp_running:
                        is_nu_goal = False
                    else:
                        is_nu_goal = True

                    if score_nu is not None: nu_running = score_nu
                    elif is_nu_goal: nu_running += 1

                    if score_opp is not None: opp_running = score_opp
                    elif not is_nu_goal: opp_running += 1

                    team = "Northeastern" if is_nu_goal else opponent
                    is_gwg = False
                    if is_nu_goal:
                        nu_goal_count += 1
                        if nu_goal_count == gwg_goal_num:
                            is_gwg = True
                            for s in skaters:
                                if s["player_name"].lower() == scorer.lower() or scorer.lower() in s["player_name"].lower():
                                    s["gwg"] = 1
                                    break

                    t_sec, sec_rem = parse_period_time(prd, time_str)
                    goal_events.append({
                        "date": date,
                        "opponent": opponent,
                        "period": prd,
                        "time": time_str,
                        "time_seconds": t_sec,
                        "seconds_remaining": sec_rem,
                        "team": team,
                        "scorer": scorer,
                        "primary_assist": primary_assist,
                        "secondary_assist": secondary_assist,
                        "strength": strength,
                        "is_gwg": 1 if is_gwg else 0,
                        "nu_score_after": nu_running,
                        "opp_score_after": opp_running,
                        "boxscore_url": url,
                    })
            break

    # 6. PARSE PENALTY SUMMARY
    penalty_events = []
    for t in soup.find_all("table"):
        cap = t.find("caption")
        cap_text = cap.get_text().lower() if cap else ""
        if "penalty summary" in cap_text:
            tbody = t.find("tbody") or t
            for r in tbody.find_all("tr"):
                cells = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
                if len(cells) >= 6:
                    team_raw = cells[0]
                    prd = cells[1]
                    p_name = clean_person_name(cells[2])
                    min_str = cells[3]
                    offense = cells[4] if len(cells) > 4 else ""
                    time_str = cells[6] if len(cells) > 6 else (cells[5] if len(cells) > 5 else "")
                    try:
                        p_mins = int(min_str.split(":")[0]) if ":" in min_str else int(min_str)
                    except ValueError:
                        p_mins = 2

                    team = "Northeastern" if ("nu" in team_raw.lower() or "neu" in team_raw.lower() or not team_raw) else opponent

                    penalty_events.append({
                        "date": date,
                        "opponent": opponent,
                        "period": prd,
                        "time": time_str,
                        "team": team,
                        "player_name": p_name,
                        "penalty_minutes": p_mins,
                        "infraction": offense,
                        "boxscore_url": url,
                    })
            break

    return game_record, skaters, goalies, goal_events, penalty_events, shootout_events


def is_nu_team_label(val: str) -> bool:
    v = str(val).strip().lower()
    return "northeastern" in v or v in ("nu", "neu")


def parse_legacy_boxscore(soup, url, html):
    """Parses legacy Gonu and 2011-12 .aspx box scores for games, skaters, goalies, goals, penalties, and shootouts."""
    title = soup.title.get_text(strip=True) if soup.title else ""
    m = re.search(r'(?:Northeastern(?:\s+Univ\.?)?|NU|NEU)\s+(?:vs\.?|at)\s+(.+?)\s+\((.+?)\)', title, re.IGNORECASE)
    if not m:
        m = re.search(r'(.+?)\s+(?:vs\.?|at)\s+(?:Northeastern(?:\s+Univ\.?)?|NU|NEU)\s+\((.+?)\)', title, re.IGNORECASE)
    opponent = m.group(1).strip() if m else "Unknown"
    date = m.group(2).strip() if m else ""

    if not date:
        full_txt = soup.get_text(" ", strip=True)
        dm = re.search(r'Date:\s*([A-Za-z]+\.?\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})', full_txt)
        if dm:
            date = dm.group(1).strip()

    nu_goals = 0
    opp_goals = 0
    legacy_ot_col = False

    leaf_tables = [t for t in soup.find_all("table") if not t.find("table")]

    # Score from Goals by Period table
    for t in leaf_tables:
        txt = t.get_text()
        if "Goals by Period" in txt:
            for r in t.find_all("tr"):
                cols = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
                if any(re.search(r'^(?:OT|2OT|3OT|SO)$', c, re.IGNORECASE) for c in cols):
                    legacy_ot_col = True
                if cols and is_nu_team_label(cols[0]) and len(cols) >= 5:
                    try: nu_goals = int(cols[-1])
                    except ValueError: pass
                elif cols and len(cols) >= 5 and cols[0] != "Goals by Period":
                    try:
                        opp_goals = int(cols[-1])
                        if opponent == "Unknown" or is_nu_team_label(opponent):
                            opponent = cols[0]
                    except ValueError: pass

    is_ot = 1 if legacy_ot_col else 0
    ot_status = "OT" if is_ot else "REG"
    is_shutout = 1 if (nu_goals == 0 or opp_goals == 0) else 0
    if opp_goals == 0 and nu_goals > 0:
        shutout_team = "Northeastern"
    elif nu_goals == 0 and opp_goals > 0:
        shutout_team = opponent
    elif nu_goals == 0 and opp_goals == 0:
        shutout_team = "Both (0-0 Tie)"
    else:
        shutout_team = "None"

    outcome = "W" if nu_goals > opp_goals else ("L" if nu_goals < opp_goals else "T")

    location = ""
    if re.search(r'\bneutral\b', title, re.IGNORECASE):
        location = "Neutral"
    elif re.search(r'(?:Northeastern(?:\s+Univ\.?)?|NU|NEU)\s+at\s+', title, re.IGNORECASE):
        location = "Away"
    elif re.search(r'\bat\s+(?:Northeastern(?:\s+Univ\.?)?|NU|NEU)\b', title, re.IGNORECASE):
        location = "Home"
    elif re.search(r'\bvs\.?\s+', title, re.IGNORECASE):
        location = "Home"

    game_record = {
        "date": date,
        "opponent": opponent,
        "location": location,
        "nu_goals": nu_goals,
        "opp_goals": opp_goals,
        "outcome": outcome,
        "overtime_status": ot_status,
        "is_overtime": is_ot,
        "is_shootout": 0,
        "shootout_winner": "None",
        "is_shutout": is_shutout,
        "shutout_team": shutout_team,
        "nu_pp_goals": "",
        "nu_pp_opps": "",
        "opp_pp_goals": "",
        "opp_pp_opps": "",
        "boxscore_url": url,
    }

    # 1. PARSE SKATERS
    skaters = []
    for t in leaf_tables:
        rows = t.find_all("tr")
        for i, r in enumerate(rows):
            cols = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
            if len(cols) >= 4 and is_nu_team_label(cols[0]) and "G" in cols and "A" in cols:
                for r2 in rows[i + 1:]:
                    c2 = [c.get_text(strip=True) for c in r2.find_all(["td", "th"])]
                    if any("total" in str(x).lower() for x in c2): break
                    if len(c2) >= 8:
                        p_name = clean_person_name(c2[2])
                        if not p_name or any(x in p_name.lower() for x in ["totals", "team"]):
                            continue
                        offset = len(c2) - len(cols)
                        try:
                            goals = int(c2[3])
                            assists = int(c2[4])
                            tot_idx = (cols.index("Tot") + offset) if "Tot" in cols else 8
                            pm_idx = (cols.index("+/-") + offset) if "+/-" in cols else 9
                            shots = int(c2[tot_idx]) if 0 <= tot_idx < len(c2) and c2[tot_idx].isdigit() else 0
                            pm_str = c2[pm_idx] if 0 <= pm_idx < len(c2) else "0"
                            plus_minus = int(pm_str.replace("+", ""))
                        except (ValueError, IndexError):
                            continue

                        pen_count, pen_mins = 0, 0
                        pen_idx = (cols.index("Pen") + offset) if "Pen" in cols else -1
                        pen_col = c2[pen_idx] if (pen_idx != -1 and 0 <= pen_idx < len(c2)) else (c2[-1] if len(c2) >= 10 else "")
                        if "-" in pen_col:
                            parts = pen_col.split("-")
                            try:
                                pen_count = int(parts[0])
                                pen_mins = int(parts[1])
                            except ValueError: pass

                        skaters.append({
                            "date": date,
                            "opponent": opponent,
                            "nu_goals": nu_goals,
                            "opp_goals": opp_goals,
                            "player_name": p_name,
                            "goals": goals,
                            "assists": assists,
                            "points": goals + assists,
                            "shots": shots,
                            "plus_minus": plus_minus,
                            "penalties": pen_count,
                            "penalty_minutes": pen_mins,
                            "faceoffs_won": 0,
                            "faceoffs_lost": 0,
                            "blocked_shots": 0,
                            "gwg": 0,
                            "is_overtime": is_ot,
                            "is_shutout": is_shutout,
                            "boxscore_url": url,
                        })
                break
        if skaters:
            break

    # 2. PARSE GOALIES
    goalies = []
    for t in leaf_tables:
        rows = t.find_all("tr")
        for i, r in enumerate(rows):
            cols = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
            if len(cols) >= 4 and is_nu_team_label(cols[0]) and "Minutes" in cols and "GA" in cols:
                for r2 in rows[i + 1:]:
                    c2 = [c.get_text(strip=True) for c in r2.find_all(["td", "th"])]
                    if not c2 or any(x in str(c2).lower() for x in ["totals", "team", "saves by prd", "shots by prd"]):
                        break
                    if len(c2) >= 6:
                        g_name = clean_person_name(c2[1])
                        mins = c2[3] if len(c2) > 3 else ""
                        if ":" not in mins: break
                        dec = c2[2] if len(c2) > 2 else ""
                        try: ga = int(c2[4])
                        except (ValueError, IndexError): ga = 0
                        try: en = int(c2[5])
                        except (ValueError, IndexError): en = 0
                        try: saves = int(c2[-1])
                        except (ValueError, IndexError): saves = 0

                        shots_against = ga + saves
                        save_pct = round(saves / shots_against, 3) if shots_against > 0 else 0.0
                        so_flag = 1 if (ga == 0 and saves > 0) else 0

                        # Check if goalie minutes indicate overtime e.g. 65:00
                        try:
                            m_int = int(mins.split(":")[0])
                            if m_int > 60:
                                game_record["is_overtime"] = 1
                                if game_record["overtime_status"] == "REG":
                                    game_record["overtime_status"] = "OT"
                        except Exception: pass

                        goalies.append({
                            "date": date,
                            "opponent": opponent,
                            "nu_goals": nu_goals,
                            "opp_goals": opp_goals,
                            "goalie_name": g_name,
                            "decision": dec,
                            "minutes": mins,
                            "goals_against": ga,
                            "empty_net_goals": en,
                            "saves": saves,
                            "shots_against": shots_against,
                            "save_pct": f"{save_pct:.3f}" if shots_against > 0 else ".000",
                            "shutouts": so_flag,
                            "is_overtime": game_record["is_overtime"],
                            "boxscore_url": url,
                        })
                break
        if goalies:
            break

    # 3. PARSE SCORING SUMMARY
    goal_events = []
    seen_legacy_goals = set()
    for t in leaf_tables:
        txt = t.get_text()
        if "Scored by" in txt and "Prd" in txt:
            nu_running = 0
            opp_running = 0
            gwg_goal_num = (opp_goals + 1) if nu_goals > opp_goals else -1
            nu_goal_count = 0

            for r in t.find_all("tr"):
                cols = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
                if len(cols) >= 6 and cols[0] != "#" and re.match(r'^(?:1st|2nd|3rd|ot|2ot|3ot)\b', cols[1].strip(), re.IGNORECASE):
                    prd = cols[1].strip()
                    time_str = cols[2].strip()
                    if not re.match(r'^\d{1,2}:\d{2}(?:\.\d+)?$', time_str):
                        continue
                    team_code = cols[3]
                    strength = cols[4].strip().upper() if len(cols) > 4 else "EV"
                    if strength == "EVEN":
                        strength = "EV"
                    raw_scorer = cols[5] if len(cols) > 5 else ""
                    scorer = clean_person_name(re.sub(r'/\d+', '', raw_scorer))
                    dedup_key = (prd, time_str, scorer.lower())
                    if dedup_key in seen_legacy_goals:
                        continue
                    seen_legacy_goals.add(dedup_key)

                    assists_str = cols[6] if len(cols) > 6 else ""

                    if re.match(r'^(?:ot|2ot|3ot)\b', prd, re.IGNORECASE):
                        game_record["is_overtime"] = 1
                        if game_record["overtime_status"] == "REG":
                            game_record["overtime_status"] = "OT"

                    primary_assist = ""
                    secondary_assist = ""
                    if assists_str and assists_str not in ["-", "unassisted", "None"]:
                        a_tokens = [clean_person_name(re.sub(r'/\d+', '', x)) for x in re.split(r';|\s{2,}|(?<=/\d),\s*|(?<=/\d\d),\s*', assists_str) if x.strip()]
                        if len(a_tokens) == 1 and "," in a_tokens[0]:
                            a_tokens = [clean_person_name(x) for x in a_tokens[0].split(",") if x.strip()]
                        if len(a_tokens) >= 1: primary_assist = a_tokens[0]
                        if len(a_tokens) >= 2: secondary_assist = a_tokens[1]

                    is_nu = ("nu" in team_code.lower() or "neu" in team_code.lower())
                    if is_nu:
                        nu_running += 1
                        nu_goal_count += 1
                    else:
                        opp_running += 1

                    is_gwg = (is_nu and nu_goal_count == gwg_goal_num)
                    if is_gwg:
                        for s in skaters:
                            if s["player_name"].lower() == scorer.lower() or scorer.lower() in s["player_name"].lower():
                                s["gwg"] = 1
                                break

                    t_sec, sec_rem = parse_period_time(prd, time_str)
                    goal_events.append({
                        "date": date,
                        "opponent": opponent,
                        "period": prd,
                        "time": time_str,
                        "time_seconds": t_sec,
                        "seconds_remaining": sec_rem,
                        "team": "Northeastern" if is_nu else opponent,
                        "scorer": scorer,
                        "primary_assist": primary_assist,
                        "secondary_assist": secondary_assist,
                        "strength": strength,
                        "is_gwg": 1 if is_gwg else 0,
                        "nu_score_after": nu_running,
                        "opp_score_after": opp_running,
                        "boxscore_url": url,
                    })
            break

    # 4. PARSE PENALTY SUMMARY
    penalty_events = []
    in_pen_section = False
    for t in leaf_tables:
        txt = t.get_text()
        if "Offense" in txt and "Player" in txt and "Prd" in txt:
            for r in t.find_all("tr"):
                cols = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
                if cols and cols[0] == "Prd" and "Player" in cols and "Offense" in cols:
                    in_pen_section = True
                    continue
                if in_pen_section:
                    if any(x in str(cols).lower() for x in ["faceoffs", "power play", "summary:", "totals........."]):
                        in_pen_section = False
                        break
                    if len(cols) >= 6 and cols[0] in ["1st", "2nd", "3rd", "OT", "2OT", "3OT"]:
                        prd = cols[0]
                        p_name = clean_person_name(cols[1])
                        team_code = cols[2]
                        try: p_mins = int(cols[3])
                        except (ValueError, IndexError): p_mins = 2
                        offense = cols[4] if len(cols) > 4 else ""
                        time_str = cols[5] if len(cols) > 5 else ""

                        is_nu = ("nu" in team_code.lower() or "neu" in team_code.lower())
                        penalty_events.append({
                            "date": date,
                            "opponent": opponent,
                            "period": prd,
                            "time": time_str,
                            "team": "Northeastern" if is_nu else opponent,
                            "player_name": p_name,
                            "penalty_minutes": p_mins,
                            "infraction": offense,
                            "boxscore_url": url,
                        })
            if penalty_events:
                break

    shootout_events = []
    return game_record, skaters, goalies, goal_events, penalty_events, shootout_events


def parse_boxscore(html: str, url: str):
    soup = BeautifulSoup(html, "html.parser")
    if "/boxscore/" in url.lower():
        return parse_modern_boxscore(soup, url, html)
    else:
        return parse_legacy_boxscore(soup, url, html)


async def gather_all_game_urls(client: httpx.AsyncClient):
    """Scrapes game box score URLs across all seasons 1999 to 2027."""
    all_urls = []
    print("\n1. Discovering box score URLs across all seasons (1999-2027)...")

    for year in range(1999, 2027):
        season_str = f"{year}-{str(year+1)[-2:]}"
        legacy_url = f"https://static.gonu.com/custompages/mhockey/MHK{str(year)[-2:]}{str(year+1)[-2:]}/HTML/teamstat.htm"
        modern_url = f"https://nuhuskies.com/sports/mens-ice-hockey/schedule/{season_str}"

        season_links = []
        if year == 2011:
            # For 2011-12, use the 33 verified working .aspx box score URLs on nuhuskies.com
            # (excluding the Oct 2 exhibition vs St. Francis Xavier and the broken /boxscore/3363 link)
            # plus the Beanpot semifinal vs Boston College (bp2.htm) from static.gonu.com.
            try:
                res_modern = await client.get(modern_url, timeout=6.0)
                if res_modern.status_code == 200:
                    soup = BeautifulSoup(res_modern.text, "html.parser")
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        href_low = href.lower()
                        text = a.get_text(" ", strip=True).lower()
                        if "box" in text and href_low.endswith(".aspx") and "1002114319" not in href_low:
                            season_links.append(urllib.parse.urljoin("https://nuhuskies.com", href))
            except Exception:
                pass
            season_links.append("https://static.gonu.com/custompages/mhockey/MHK1112/HTML/bp2.htm")
        else:
            try:
                res_legacy = await client.get(legacy_url, timeout=6.0)
                if res_legacy.status_code == 200:
                    soup = BeautifulSoup(res_legacy.text, "html.parser")
                    for a in soup.find_all("a", href=True):
                        href = a["href"].lower()
                        if href.endswith(".htm") and not any(x in href for x in ["teamcume", "teamgbg", "confstat", "plystat", "teamstat"]):
                            season_links.append(urllib.parse.urljoin(legacy_url, a["href"]))
            except Exception:
                pass

            if not season_links or len(season_links) < 5:
                try:
                    res_modern = await client.get(modern_url, timeout=6.0)
                    if res_modern.status_code == 200:
                        soup = BeautifulSoup(res_modern.text, "html.parser")
                        for a in soup.find_all("a", href=True):
                            href = a["href"].lower()
                            text = a.get_text(strip=True).lower()
                            if ("boxscore" in href or "box score" in text or "stats" in text or "/stats/" in href) and "roster" not in href and "cumulative" not in href and "boxscore/3363" not in href:
                                season_links.append(urllib.parse.urljoin("https://nuhuskies.com", a["href"]))
                except Exception:
                    pass

        unique_season = list(set(season_links))
        if unique_season:
            print(f"  {season_str}: {len(unique_season)} games found")
            all_urls.extend(unique_season)

    all_urls = sorted(list(set(all_urls)))
    print(f"\nTotal unique games discovered: {len(all_urls)}\n")
    return all_urls


async def fetch_or_load_html(client: httpx.AsyncClient, semaphore: asyncio.Semaphore, url: str, index: dict):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fn = url_to_filename(url)
    filepath = CACHE_DIR / fn

    if filepath.exists() and filepath.stat().st_size > 500:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(), url

    async with semaphore:
        try:
            resp = await client.get(url, timeout=12.0)
            if resp.status_code == 200 and len(resp.text) > 500:
                html = resp.text
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(html)
                index[url] = fn
                return html, url
        except Exception:
            pass

    return "", url


def safe_int(v, default=0) -> int:
    if v is None:
        return default
    s = str(v).strip().replace("+", "")
    if not s or s == "-":
        return default
    m = re.search(r"-?\d+", s)
    return int(m.group(0)) if m else default


def safe_float(v, default=0.0) -> float:
    if v is None:
        return default
    s = str(v).strip()
    if not s or s == "-":
        return default
    m = re.search(r"-?\d*\.?\d+", s)
    if m and m.group(0) not in ("", "-", "."):
        return float(m.group(0))
    return default


def date_to_season(date_str: str) -> str:
    if not date_str or len(date_str) < 7:
        return ""
    try:
        yr = int(date_str[:4])
        mo = int(date_str[5:7])
        if mo >= 8:
            return f"{yr}-{str(yr + 1)[-2:]}"
        else:
            return f"{yr - 1}-{str(yr)[-2:]}"
    except Exception:
        return ""


HEAD_COACHES = {
    "1999-00": "Bruce Crowder",
    "2000-01": "Bruce Crowder",
    "2001-02": "Bruce Crowder",
    "2002-03": "Bruce Crowder",
    "2003-04": "Bruce Crowder",
    "2004-05": "Bruce Crowder",
    "2005-06": "Greg Cronin",
    "2006-07": "Greg Cronin",
    "2007-08": "Greg Cronin",
    "2008-09": "Greg Cronin",
    "2009-10": "Greg Cronin",
    "2010-11": "Greg Cronin",
    "2011-12": "Jim Madigan",
    "2012-13": "Jim Madigan",
    "2013-14": "Jim Madigan",
    "2014-15": "Jim Madigan",
    "2015-16": "Jim Madigan",
    "2016-17": "Jim Madigan",
    "2017-18": "Jim Madigan",
    "2018-19": "Jim Madigan",
    "2019-20": "Jim Madigan",
    "2020-21": "Jim Madigan",
    "2021-22": "Jerry Keefe",
    "2022-23": "Jerry Keefe",
    "2023-24": "Jerry Keefe",
    "2024-25": "Jerry Keefe",
    "2025-26": "Jerry Keefe",
    "2026-27": "Jerry Keefe",
}

KNOWN_LEADERSHIP = {
    "1999-00": {"C": ["Roger Holeczy"], "A": ["Billy Newson", "William Newson", "Todd Barclay", "Graig Mischler", "Craig Mischler"]},
    "2000-01": {"C": ["Jim Fahey", "James Fahey"], "A": ["Graig Mischler", "Craig Mischler", "Chris Lynch"]},
    "2001-02": {"C": ["Jim Fahey", "James Fahey"], "A": ["Chris Lynch", "Willie Levesque", "William Levesque", "Mike Ryan", "Michael Ryan", "Trevor Reschny"]},
    "2002-03": {"C": ["Mike Ryan", "Michael Ryan"], "A": ["Trevor Reschny", "Eric Ortlip"]},
    "2003-04": {"C": ["Trevor Reschny"], "A": ["Jason Guerriero", "Eric Ortlip", "Brian Tudrick", "Tim Judy", "Timothy Judy"]},
    "2004-05": {"C": ["Jason Guerriero"], "A": ["Tim Judy", "Timothy Judy", "Donny Grover", "Donald Grover", "Chuck Tomes", "Charles Tomes"]},
    "2005-06": {"C": ["Chuck Tomes", "Charles Tomes"], "A": ["Mike Morris", "Michael Morris", "Bryan Esner", "Jimmy Russo", "James Russo"]},
    "2006-07": {"C": ["Mike Morris", "Michael Morris"], "A": ["Joe Vitale", "Joseph Vitale", "Ray Ortiz", "Raymond Ortiz", "Jimmy Russo", "James Russo"]},
    "2007-08": {"C": ["Joe Vitale", "Joseph Vitale"], "A": ["Ryan Ginand", "Jimmy Russo", "James Russo"]},
    "2008-09": {"C": ["Joe Vitale", "Joseph Vitale"], "A": ["Ryan Ginand", "Dennis McCauley", "Louis Liotti"]},
    "2009-10": {"C": ["Tyler McNeely"], "A": ["Kyle Kraemer", "Wade MacLeod", "Chris Strathmann"]},
    "2010-11": {"C": ["Tyler McNeely"], "A": ["Wade MacLeod", "Steve Silva", "Steven Silva", "Mike Hewkin", "Michael Hewkin"]},
    "2011-12": {"C": ["Mike McLaughlin", "Michael McLaughlin"], "A": ["Drew Ellement", "Anthony Bitetto", "Steve Quailer", "Steven Quailer"]},
    "2012-13": {"C": ["Vinny Saponari", "Vincent Saponari"], "A": ["Robbie Vrolyk", "Robert Vrolyk", "Ludwig Karlsson"]},
    "2013-14": {"C": ["Josh Manson"], "A": ["Dax Lauwers", "Adam Reid", "Braden Pimm"]},
    "2014-15": {"C": ["Dax Lauwers", "Adam Reid"], "A": ["Torin Snydeman", "Clay Witt", "Kevin Roy"]},
    "2015-16": {"C": ["Kevin Roy"], "A": ["John Stevens", "Nolan Stevens", "Zach Aston-Reese", "Zachary Aston-Reese", "Matt Benning", "Matthew Benning", "Mike McMurtry", "Michael McMurtry"]},
    "2016-17": {"C": ["John Stevens"], "A": ["Zach Aston-Reese", "Zachary Aston-Reese", "Brendan Collier", "Nolan Stevens", "Garret Cockerill", "Garrett Cockerill"]},
    "2017-18": {"C": ["Nolan Stevens"], "A": ["Dylan Sikura", "Garrett Cecere", "Eric Williams", "Adam Gaudette"]},
    "2018-19": {"C": ["Eric Williams"], "A": ["Jeremy Davies", "Ryan Shea", "Lincoln Griffin", "John Picking"]},
    "2019-20": {"C": ["Ryan Shea"], "A": ["John Picking", "Biagio Lerario", "Matt Filipe", "Matthew Filipe", "Grant Jozefek"]},
    "2020-21": {"C": ["Zach Solow", "Zachary Solow"], "A": ["Jordan Harris", "Collin Murphy", "Austin Goldstein", "Grant Jozefek"]},
    "2021-22": {"C": ["Jordan Harris"], "A": ["Julian Kislin", "Riley Hughes", "Aidan McDonough"]},
    "2022-23": {"C": ["Aidan McDonough"], "A": ["Jayden Struble", "Riley Hughes", "Jakov Novak"]},
    "2023-24": {"C": ["Justin Hryckowian"], "A": ["Matt DeMelis", "Matthew DeMelis", "Liam Walsh", "Gunnarwolfe Fontaine", "Jack Williams"]},
    "2024-25": {"C": ["Jack Williams"], "A": ["Vinny Borgesi", "Vincent Borgesi", "Jackson Dorrington", "Cam Lund", "Cameron Lund", "Jake Boltmann"]},
    "2025-26": {"C": ["Vinny Borgesi", "Vincent Borgesi"], "A": ["Joaquim Lemay", "Dylan Hryckowian", "Andy Moore", "Andrew Moore"]},
    "2026-27": {"C": ["Andy Moore", "Andrew Moore", "Joaquim Lemay"], "A": ["Eli Sebastian", "Joe Connor", "Joseph Connor", "Jacob Mathieu"]},
}

NICKNAME_MAP = {
    "michael": "mike",
    "vincent": "vinny",
    "matthew": "matt",
    "andrew": "andy",
    "joseph": "joe",
    "james": "jim",
    "jimmy": "jim",
    "william": "billy",
    "willie": "billy",
    "bill": "billy",
    "charles": "chuck",
    "timothy": "tim",
    "donald": "donny",
    "steven": "steve",
    "stephen": "steve",
    "robert": "robbie",
    "zachary": "zach",
    "cameron": "cam",
    "raymond": "ray",
    "graig": "craig",
    "garret": "garrett",
    "alexander": "alex",
    "nicholas": "nick",
    "christopher": "chris",
    "daniel": "dan",
    "danny": "dan",
    "benjamin": "ben",
    "samuel": "sam",
    "thomas": "tom",
    "tommy": "tom",
    "anthony": "tony",
    "kenneth": "ken",
    "edward": "ed",
    "jonathan": "jon",
}


def normalize_player_key(name: str) -> str:
    if not name:
        return ""
    s = clean_person_name(name).lower()
    s = re.sub(r"\s*\([ca]\)\s*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"[^a-z\s\-]", "", s).strip()
    parts = s.split()
    if len(parts) >= 2:
        first = NICKNAME_MAP.get(parts[0], parts[0])
        last = " ".join(parts[1:])
        return f"{first} {last}"
    return s


def clean_stats_player_cell(cell) -> str:
    # Prefer the first <a> tag text if available (avoids duplicated mobile+desktop text in Sidearm tables)
    a_tag = cell.find("a")
    if a_tag:
        raw = a_tag.get_text(" ", strip=True)
    else:
        raw = cell.get_text("\n", strip=True).split("\n")[0].strip()
    raw = re.sub(r"\s+", " ", raw).strip()
    # Check if string is duplicated ("Marques, Miguel Marques, Miguel")
    words = raw.split(" ")
    if len(words) >= 4 and len(words) % 2 == 0:
        half = len(words) // 2
        if words[:half] == words[half:]:
            raw = " ".join(words[:half])
    return clean_person_name(raw)


def normalize_position(pos_str: str) -> str:
    if not pos_str:
        return ""
    p = pos_str.strip().upper()
    if p in ("G", "GOALIE", "GOALTENDER", "GK"):
        return "G"
    if p in ("D", "DEF", "DEFENSE", "DEFENSEMAN", "DEFENCEMAN", "LD", "RD", "D/F"):
        return "D"
    if p in ("F", "FWD", "FORWARD", "C", "LW", "RW", "W", "LEFT WING", "RIGHT WING", "CENTER", "F/D"):
        return "F"
    if "GOAL" in p:
        return "G"
    if "DEF" in p:
        return "D"
    if any(k in p for k in ("FORW", "WING", "CENT")):
        return "F"
    return p


def normalize_class_year(cl_str: str) -> str:
    if not cl_str:
        return ""
    c = cl_str.strip().lower().replace(".", "")
    if c in ("fr", "freshman", "first-year", "fy", "1st", "r-fr"):
        return "Fr."
    if c in ("so", "sophomore", "2nd", "r-so"):
        return "So."
    if c in ("jr", "junior", "3rd", "r-jr"):
        return "Jr."
    if c in ("sr", "senior", "4th", "r-sr"):
        return "Sr."
    if c in ("gr", "grad", "graduate", "5th"):
        return "Gr."
    return cl_str.strip()


def parse_height_inches(ht_str: str) -> int:
    if not ht_str:
        return 0
    m = re.search(r"(\d)\s*[-'′]\s*(\d{1,2})", str(ht_str))
    if m:
        return int(m.group(1)) * 12 + int(m.group(2))
    return 0


def lookup_leadership_role(season: str, player_name: str, scraped_role: str = "") -> str:
    if scraped_role and scraped_role.strip().upper() in ("C", "A"):
        return scraped_role.strip().upper()
    info = KNOWN_LEADERSHIP.get(season, {})
    pkey = normalize_player_key(player_name)
    for c_name in info.get("C", []):
        if normalize_player_key(c_name) == pkey:
            return "C"
    for a_name in info.get("A", []):
        if normalize_player_key(a_name) == pkey:
            return "A"
    return "None"


def is_matching_sidearm_season(soup: BeautifulSoup, season: str) -> bool:
    title_txt = soup.title.get_text(" ", strip=True) if soup.title else ""
    h1_txt = " ".join(h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2"])[:4])
    combined = f"{title_txt} {h1_txt}"
    found_seasons = re.findall(r"\b(20\d{2}-\d{2})\b", combined)
    if found_seasons and season not in found_seasons:
        return False
    return True


def parse_modern_roster_html(html: str, season: str, url: str) -> tuple[list[dict], dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    if not is_matching_sidearm_season(soup, season):
        return [], {}
    players_by_key = {}
    bio_urls = {}

    # 1. Check standard Sidearm roster table(s)
    for table in soup.find_all("table"):
        headers = [th.get_text(" ", strip=True).lower() for th in table.find_all("th")]
        if not any(h in ("name", "full name", "player") or "name" in h for h in headers):
            continue
        if not any("pos" in h or "ht" in h or "cl" in h or "hometown" in h for h in headers):
            continue

        # Map column indices
        col_map = {}
        for idx, h in enumerate(headers):
            if h in ("#", "no", "no.") or "number" in h or "jersey" in h:
                col_map.setdefault("num", idx)
            elif "name" in h or "player" in h:
                col_map.setdefault("name", idx)
            elif "capt" in h:
                col_map.setdefault("capt", idx)
            elif "pos" in h:
                col_map.setdefault("pos", idx)
            elif "sh" in h or "cat" in h or "hand" in h:
                col_map.setdefault("shoots", idx)
            elif "ht" in h or "height" in h:
                col_map.setdefault("ht", idx)
            elif "wt" in h or "weight" in h:
                col_map.setdefault("wt", idx)
            elif "cl" in h or "yr" in h or "year" in h or "academic" in h:
                col_map.setdefault("cl", idx)
            elif "hometown" in h or "previous" in h or "high school" in h or "last team" in h:
                col_map.setdefault("hometown", idx)

        tbody = table.find("tbody") or table
        for tr in tbody.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) < 4:
                continue
            name_idx = col_map.get("name", 1)
            if name_idx >= len(cells):
                continue
            name_cell = cells[name_idx]
            raw_name = clean_stats_player_cell(name_cell)
            if not raw_name or raw_name.lower() in ("full name", "name", "player", "pronunciation"):
                continue

            # Check if name has (C) or (A) suffix
            inline_capt = ""
            m_capt = re.search(r"\(([CA])\)\s*$", raw_name)
            if m_capt:
                inline_capt = m_capt.group(1).upper()
                raw_name = re.sub(r"\s*\([CA]\)\s*$", "", raw_name).strip()

            a_link = name_cell.find("a", href=True)
            if a_link and "/roster/" in a_link["href"]:
                href = a_link["href"]
                full_bio = href if href.startswith("http") else f"https://nuhuskies.com{href}"
                bio_urls[normalize_player_key(raw_name)] = full_bio

            def get_cell(key):
                i = col_map.get(key)
                if i is not None and i < len(cells):
                    return cells[i].get_text(" ", strip=True)
                return ""

            num_val = re.sub(r"[^\d]", "", get_cell("num"))
            capt_val = get_cell("capt").strip().upper()
            if capt_val not in ("C", "A"):
                capt_val = inline_capt
            pos_val = normalize_position(get_cell("pos"))
            shoots_val = get_cell("shoots").strip()
            if shoots_val.upper().startswith("L"):
                shoots_val = "Left"
            elif shoots_val.upper().startswith("R"):
                shoots_val = "Right"
            ht_val = get_cell("ht").strip().replace("'", "-").replace('"', "").replace("′", "-").replace("″", "").replace(" ", "")
            wt_val = safe_int(re.sub(r"[^\d]", "", get_cell("wt")))
            cl_val = normalize_class_year(get_cell("cl"))
            home_raw = get_cell("hometown")
            hometown_val, prev_team_val, prev_school_val = "", "", ""
            if "/" in home_raw:
                parts = [p.strip() for p in home_raw.split("/") if p.strip()]
                hometown_val = parts[0] if parts else ""
                prev_team_val = parts[1] if len(parts) > 1 else ""
                prev_school_val = parts[2] if len(parts) > 2 else ""
            else:
                hometown_val = home_raw.strip()

            role = lookup_leadership_role(season, raw_name, capt_val)
            pkey = normalize_player_key(raw_name)
            players_by_key[pkey] = {
                "season": season,
                "jersey_number": num_val,
                "player_name": raw_name,
                "captain_role": role,
                "is_captain": 1 if role == "C" else 0,
                "is_alternate_captain": 1 if role == "A" else 0,
                "is_leadership": 1 if role in ("C", "A") else 0,
                "position": pos_val,
                "class_year": cl_val,
                "height": ht_val,
                "height_inches": parse_height_inches(ht_val),
                "weight": wt_val,
                "shoots": shoots_val,
                "hometown": hometown_val,
                "previous_team": prev_team_val,
                "previous_school": prev_school_val,
                "major": "",
                "head_coach": HEAD_COACHES.get(season, ""),
                "roster_url": url,
                "image_url": "",
            }

    # 2. Also inspect Sidearm person cards for major / previous school / captain badge if present
    for card in soup.select(".s-person-card, .sidearm-roster-player"):
        card_text = card.get_text("\n", strip=True)
        a_tag = card.find("a", href=lambda h: h and "/roster/" in h)
        if not a_tag:
            continue
        cname = clean_person_name(a_tag.get_text(" ", strip=True))
        if not cname or cname.lower() in ("full bio", "view bio", "bio"):
            # Try heading inside card
            h_tag = card.find(["h3", "h4", "h2"])
            if h_tag:
                cname = clean_person_name(h_tag.get_text(" ", strip=True))
        if not cname:
            img_tag = card.find("img", alt=True)
            if img_tag:
                cname = clean_person_name(re.sub(r"\s*-\s*View Profile.*$", "", img_tag["alt"], flags=re.IGNORECASE))
        if not cname:
            continue
        pkey = normalize_player_key(cname)
        href = a_tag.get("href", "")
        if href and "/roster/" in href:
            bio_urls.setdefault(pkey, href if href.startswith("http") else f"https://nuhuskies.com{href}")

        if pkey in players_by_key:
            rec = players_by_key[pkey]
            img_tag = card.find("img")
            if img_tag:
                src = img_tag.get("data-src") or img_tag.get("src") or ""
                if src and "placeholder" not in src.lower():
                    src = re.sub(r"width=\d+", "width=300", src)
                    rec["image_url"] = src if src.startswith("http") else f"https://nuhuskies.com{src}"
            # Look for major or previous school in card text
            lines = [ln.strip() for ln in card_text.split("\n") if ln.strip()]
            for i, ln in enumerate(lines):
                if ln.lower() in ("major", "academic major") and i + 1 < len(lines):
                    rec["major"] = re.sub(r"\s*Related Content.*$", "", lines[i + 1], flags=re.IGNORECASE).strip()
                elif ln.lower() in ("last team", "previous team") and i + 1 < len(lines) and not rec["previous_team"]:
                    rec["previous_team"] = lines[i + 1]
                elif ln.lower() in ("previous school", "high school") and i + 1 < len(lines) and not rec["previous_school"]:
                    rec["previous_school"] = lines[i + 1]

    return list(players_by_key.values()), bio_urls


def parse_bio_for_metadata(bio_html: str) -> dict:
    info = {"major": "", "shoots": "", "previous_team": "", "hometown": ""}
    if not bio_html:
        return info
    soup = BeautifulSoup(bio_html, "html.parser")
    # Check dt/dd or Sidearm bio fields
    for dl in soup.find_all(["dl", "ul"]):
        dts = dl.find_all(["dt", "span"])
        for dt in dts:
            label = dt.get_text(" ", strip=True).lower().rstrip(":")
            nxt = dt.find_next_sibling(["dd", "span"])
            if not nxt:
                continue
            val = nxt.get_text(" ", strip=True)
            if "major" in label and val:
                info["major"] = re.sub(r"\s*Related Content.*$", "", val, flags=re.IGNORECASE).strip()
            elif label in ("shoots", "catches", "s/c") and val:
                info["shoots"] = "Left" if val.upper().startswith("L") else ("Right" if val.upper().startswith("R") else val)
            elif label in ("last team", "previous team") and val:
                info["previous_team"] = val
            elif "hometown" in label and val:
                info["hometown"] = val

    # Also check narrative bio text for "Majoring in ..." or "majoring in ..." or "... major"
    text = soup.get_text(" ", strip=True)
    if not info["major"]:
        m = re.search(
            r"(?:[Mm]ajoring in|[Mm]ajor(?:s)? is|[Gg]raduated with a degree in|[Pp]ursuing a (?:master's )?degree in)\s+([A-Za-z\s,&\-]+?)(?:\.|;|,\s*with|\s+at\s+Northeastern|\s+from\s+Northeastern|\s+and\s+is\s+|\s+Class\s+of|\s+Related\s+Content)",
            text,
        )
        if m:
            maj = re.sub(r"\s*Related Content.*$", "", m.group(1), flags=re.IGNORECASE).strip()
            if 3 <= len(maj) <= 65:
                info["major"] = maj
    if not info["shoots"]:
        m_sh = re.search(r"\b(?:Shoots|Catches)\s*:\s*(Left|Right|L|R)\b", text, re.IGNORECASE)
        if m_sh:
            v = m_sh.group(1).upper()
            info["shoots"] = "Left" if v.startswith("L") else "Right"
    return info


def parse_modern_cumulative_stats(html: str, season: str, url: str) -> tuple[dict[str, dict], dict[str, dict]]:
    soup = BeautifulSoup(html, "html.parser")
    if not is_matching_sidearm_season(soup, season):
        return {}, {}
    skater_stats = {}
    goalie_stats = {}

    tables = soup.find_all("table")
    skater_tables_seen = 0
    goalie_tables_seen = 0

    for table in tables:
        caption = table.find("caption")
        cap_text = caption.get_text(" ", strip=True).lower() if caption else ""
        headers = [th.get_text(" ", strip=True).upper() for th in table.find_all("th")]
        if not headers:
            continue

        # Determine if this is Individual Skaters or Individual Goaltenders
        is_skater_tbl = ("PTS" in headers and "SH%" in headers and "PPG" in headers and "GWG" in headers) or (
            "individual" in cap_text and "skater" in cap_text
        )
        is_goalie_tbl = ("AVG" in headers and "SV%" in headers and ("GA" in headers or "SAVES" in headers or "SV" in headers)) or (
            "individual" in cap_text and ("goaltend" in cap_text or "goalie" in cap_text)
        )

        if is_skater_tbl:
            skater_tables_seen += 1
            is_conf = ("conference" in cap_text) or (skater_tables_seen == 2)
            if skater_tables_seen > 2 and "conference" not in cap_text and "overall" not in cap_text:
                continue

            tbody = table.find("tbody") or table
            for tr in tbody.find_all("tr"):
                cells = tr.find_all(["td", "th"])
                if len(cells) < 15:
                    continue
                num_txt = cells[0].get_text(" ", strip=True)
                pname = clean_stats_player_cell(cells[1])
                if not pname or pname.upper() in ("TOTAL", "TOTALS", "OPPONENTS", "TM", "TEAM", "PLAYER"):
                    continue
                vals = [c.get_text(" ", strip=True) for c in cells]
                # Standard 22-col Sidearm skater table:
                # 0:#, 1:Player, 2:GP, 3:G, 4:A, 5:PTS, 6:SH, 7:SH%, 8:+/-, 9:PPG, 10:SHG,
                # 11:FG, 12:GWG, 13:GTG, 14:OTG, 15:HTG, 16:UAG, 17:PN-PIM, 18:MIN, 19:MAJ, 20:OTH, 21:BLK
                gp = safe_int(vals[2]) if len(vals) > 2 else 0
                g = safe_int(vals[3]) if len(vals) > 3 else 0
                a = safe_int(vals[4]) if len(vals) > 4 else 0
                pts = safe_int(vals[5]) if len(vals) > 5 else 0
                sh = safe_int(vals[6]) if len(vals) > 6 else 0
                sh_pct = safe_float(vals[7]) if len(vals) > 7 else 0.0
                pm = safe_int(vals[8]) if len(vals) > 8 else 0
                ppg = safe_int(vals[9]) if len(vals) > 9 else 0
                shg = safe_int(vals[10]) if len(vals) > 10 else 0
                fg = safe_int(vals[11]) if len(vals) > 11 else 0
                gwg = safe_int(vals[12]) if len(vals) > 12 else 0
                gtg = safe_int(vals[13]) if len(vals) > 13 else 0
                otg = safe_int(vals[14]) if len(vals) > 14 else 0
                htg = safe_int(vals[15]) if len(vals) > 15 else 0
                uag = safe_int(vals[16]) if len(vals) > 16 else 0
                pn_pim = vals[17] if len(vals) > 17 else "0-0"
                pn, pim = 0, 0
                if "-" in pn_pim:
                    p_parts = pn_pim.split("-", 1)
                    pn = safe_int(p_parts[0])
                    pim = safe_int(p_parts[1])
                min_p = safe_int(vals[18]) if len(vals) > 18 else 0
                maj_p = safe_int(vals[19]) if len(vals) > 19 else 0
                oth_p = safe_int(vals[20]) if len(vals) > 20 else 0
                blk = safe_int(vals[21]) if len(vals) > 21 else 0

                pkey = normalize_player_key(pname)
                rec = skater_stats.setdefault(pkey, {"player_name": pname, "jersey_number": re.sub(r"[^\d]", "", num_txt)})
                if not is_conf:
                    rec.update({
                        "gp": gp, "goals": g, "assists": a, "points": pts, "shots": sh,
                        "shot_pct": sh_pct, "plus_minus": pm, "ppg": ppg, "shg": shg,
                        "fg": fg, "gwg": gwg, "gtg": gtg, "otg": otg, "htg": htg, "uag": uag,
                        "penalties": pn, "pim": pim, "minor_penalties": min_p,
                        "major_penalties": maj_p, "other_penalties": oth_p, "blocked_shots": blk,
                    })
                else:
                    rec.update({
                        "conf_gp": gp, "conf_goals": g, "conf_assists": a, "conf_points": pts,
                        "conf_shots": sh, "conf_shot_pct": sh_pct, "conf_plus_minus": pm,
                        "conf_ppg": ppg, "conf_shg": shg, "conf_fg": fg, "conf_gwg": gwg,
                        "conf_gtg": gtg, "conf_otg": otg, "conf_htg": htg, "conf_uag": uag,
                        "conf_penalties": pn, "conf_pim": pim, "conf_blocked_shots": blk,
                    })

        elif is_goalie_tbl:
            goalie_tables_seen += 1
            is_conf = ("conference" in cap_text) or (goalie_tables_seen == 2)
            if goalie_tables_seen > 2 and "conference" not in cap_text and "overall" not in cap_text:
                continue

            tbody = table.find("tbody") or table
            for tr in tbody.find_all("tr"):
                cells = tr.find_all(["td", "th"])
                if len(cells) < 12:
                    continue
                num_txt = cells[0].get_text(" ", strip=True)
                pname = clean_stats_player_cell(cells[1])
                if not pname or pname.upper() in ("TOTAL", "TOTALS", "OPPONENTS", "TM", "TEAM", "PLAYER"):
                    continue
                vals = [c.get_text(" ", strip=True) for c in cells]
                # Check if GP-GS is combined (15-16 cols) or separate GP and GS
                gp_gs_raw = vals[2]
                if "-" in gp_gs_raw:
                    g_parts = gp_gs_raw.split("-", 1)
                    gp = safe_int(g_parts[0])
                    gs = safe_int(g_parts[1])
                    offset = 0
                elif len(vals) >= 16 and vals[3].isdigit() and ":" in vals[4]:
                    gp = safe_int(vals[2])
                    gs = safe_int(vals[3])
                    offset = 1
                else:
                    gp = safe_int(vals[2])
                    gs = 0
                    offset = 0

                mins = vals[3 + offset] if len(vals) > 3 + offset else "0:00"
                ga = safe_int(vals[4 + offset]) if len(vals) > 4 + offset else 0
                gaa = safe_float(vals[5 + offset]) if len(vals) > 5 + offset else 0.0
                ppga = safe_int(vals[6 + offset]) if len(vals) > 6 + offset else 0
                shga = safe_int(vals[7 + offset]) if len(vals) > 7 + offset else 0
                enga = safe_int(vals[8 + offset]) if len(vals) > 8 + offset else 0
                sv = safe_int(vals[9 + offset]) if len(vals) > 9 + offset else 0
                sv_pct = safe_float(vals[10 + offset]) if len(vals) > 10 + offset else 0.0
                w = safe_int(vals[11 + offset]) if len(vals) > 11 + offset else 0
                l = safe_int(vals[12 + offset]) if len(vals) > 12 + offset else 0
                t = safe_int(vals[13 + offset]) if len(vals) > 13 + offset else 0
                sho = safe_int(vals[14 + offset]) if len(vals) > 14 + offset else 0

                pkey = normalize_player_key(pname)
                rec = goalie_stats.setdefault(pkey, {"player_name": pname, "jersey_number": re.sub(r"[^\d]", "", num_txt)})
                if not is_conf:
                    rec.update({
                        "goalie_gp": gp, "goalie_gs": gs, "goalie_minutes": mins,
                        "ga": ga, "gaa": gaa, "ppga": ppga, "shga": shga, "enga": enga,
                        "saves": sv, "save_pct": sv_pct, "wins": w, "losses": l,
                        "ties": t, "shutouts": sho,
                    })
                else:
                    rec.update({
                        "conf_goalie_gp": gp, "conf_goalie_gs": gs, "conf_goalie_minutes": mins,
                        "conf_ga": ga, "conf_gaa": gaa, "conf_saves": sv, "conf_save_pct": sv_pct,
                        "conf_wins": w, "conf_losses": l, "conf_ties": t, "conf_shutouts": sho,
                    })

    return skater_stats, goalie_stats


def parse_legacy_teamcume(html: str, season: str, url: str) -> tuple[dict[str, dict], dict[str, dict]]:
    soup = BeautifulSoup(html, "html.parser")
    skater_stats = {}
    goalie_stats = {}

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 3:
            continue
        header_text = " ".join(r.get_text(" ", strip=True).upper() for r in rows[:3])
        if "OVERALL" in header_text and "CONFERENCE" in header_text and "PEN-MIN" in header_text:
            for tr in rows:
                cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
                if len(cells) < 20:
                    continue
                num_txt = cells[0].strip()
                if not num_txt.isdigit():
                    continue
                pname = clean_person_name(cells[1])
                if not pname or pname.upper() in ("TOTAL", "TOTALS", "OPPONENTS", "TM", "TEAM"):
                    continue
                # Overall: 2:GP, 3:G, 4:A, 5:Pts, 6:Sh, 7:+/-, 8:Pen-Min, 9:PP, 10:SH, 11:GW
                # Conf:   12:GP, 13:G, 14:A, 15:Pts, 16:Sh, 17:+/-, 18:Pen-Min, 19:PP, 20:SH, 21:GW
                gp, g, a, pts, sh = safe_int(cells[2]), safe_int(cells[3]), safe_int(cells[4]), safe_int(cells[5]), safe_int(cells[6])
                sh_pct = round(g / sh, 3) if sh > 0 else 0.0
                pm = safe_int(cells[7])
                pn, pim = 0, 0
                if "-" in cells[8]:
                    p_parts = cells[8].split("-", 1)
                    pn, pim = safe_int(p_parts[0]), safe_int(p_parts[1])
                ppg, shg, gwg = safe_int(cells[9]), safe_int(cells[10]), safe_int(cells[11])

                c_gp = safe_int(cells[12]) if len(cells) > 12 and cells[12].strip() != "-" else 0
                c_g = safe_int(cells[13]) if len(cells) > 13 else 0
                c_a = safe_int(cells[14]) if len(cells) > 14 else 0
                c_pts = safe_int(cells[15]) if len(cells) > 15 else 0
                c_sh = safe_int(cells[16]) if len(cells) > 16 else 0
                c_sh_pct = round(c_g / c_sh, 3) if c_sh > 0 else 0.0
                c_pm = safe_int(cells[17]) if len(cells) > 17 else 0
                c_pn, c_pim = 0, 0
                if len(cells) > 18 and "-" in cells[18]:
                    cp_parts = cells[18].split("-", 1)
                    c_pn, c_pim = safe_int(cp_parts[0]), safe_int(cp_parts[1])
                c_ppg = safe_int(cells[19]) if len(cells) > 19 else 0
                c_shg = safe_int(cells[20]) if len(cells) > 20 else 0
                c_gwg = safe_int(cells[21]) if len(cells) > 21 else 0

                pkey = normalize_player_key(pname)
                skater_stats[pkey] = {
                    "player_name": pname, "jersey_number": num_txt,
                    "gp": gp, "goals": g, "assists": a, "points": pts, "shots": sh,
                    "shot_pct": sh_pct, "plus_minus": pm, "ppg": ppg, "shg": shg,
                    "fg": 0, "gwg": gwg, "gtg": 0, "otg": 0, "htg": 0, "uag": 0,
                    "penalties": pn, "pim": pim, "minor_penalties": 0, "major_penalties": 0,
                    "other_penalties": 0, "blocked_shots": 0,
                    "conf_gp": c_gp, "conf_goals": c_g, "conf_assists": c_a, "conf_points": c_pts,
                    "conf_shots": c_sh, "conf_shot_pct": c_sh_pct, "conf_plus_minus": c_pm,
                    "conf_ppg": c_ppg, "conf_shg": c_shg, "conf_fg": 0, "conf_gwg": c_gwg,
                    "conf_gtg": 0, "conf_otg": 0, "conf_htg": 0, "conf_uag": 0,
                    "conf_penalties": c_pn, "conf_pim": c_pim, "conf_blocked_shots": 0,
                }

        elif "OVERALL" in header_text and ("MINUTES" in header_text or "SAVES" in header_text) and "AVG" in header_text:
            for tr in rows:
                cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
                if len(cells) < 15:
                    continue
                num_txt = cells[0].strip()
                if not num_txt.isdigit():
                    continue
                pname = clean_person_name(cells[1])
                if not pname or pname.upper() in ("TOTAL", "TOTALS", "OPPONENTS", "TM", "TEAM"):
                    continue
                # Overall: 2:GP-GS, 3:Minutes, 4:GA, 5:Avg, 6:Saves, 7:Pct, 8:W, 9:L, 10:T, 11:Sho, 12:PP, 13:SH, 14:EN
                # Conf:   15:GP-GS, 16:Minutes, 17:GA, 18:Avg, 19:Saves, 20:Pct, 21:W, 22:L, 23:T, 24:Sho
                gp, gs = 0, 0
                if "-" in cells[2]:
                    g_parts = cells[2].split("-", 1)
                    gp, gs = safe_int(g_parts[0]), safe_int(g_parts[1])
                else:
                    gp = safe_int(cells[2])
                mins = cells[3]
                ga = safe_int(cells[4])
                gaa = safe_float(cells[5])
                sv = safe_int(cells[6])
                sv_pct = safe_float(cells[7])
                w, l, t, sho = safe_int(cells[8]), safe_int(cells[9]), safe_int(cells[10]), safe_int(cells[11])
                ppga = safe_int(cells[12]) if len(cells) > 12 else 0
                shga = safe_int(cells[13]) if len(cells) > 13 else 0
                enga = safe_int(cells[14]) if len(cells) > 14 else 0

                c_gp, c_gs = 0, 0
                if len(cells) > 15 and "-" in cells[15]:
                    cg_parts = cells[15].split("-", 1)
                    c_gp, c_gs = safe_int(cg_parts[0]), safe_int(cg_parts[1])
                elif len(cells) > 15 and cells[15].strip() != "-":
                    c_gp = safe_int(cells[15])
                c_mins = cells[16] if len(cells) > 16 and cells[16].strip() != "-" else "0:00"
                c_ga = safe_int(cells[17]) if len(cells) > 17 else 0
                c_gaa = safe_float(cells[18]) if len(cells) > 18 else 0.0
                c_sv = safe_int(cells[19]) if len(cells) > 19 else 0
                c_sv_pct = safe_float(cells[20]) if len(cells) > 20 else 0.0
                c_w = safe_int(cells[21]) if len(cells) > 21 else 0
                c_l = safe_int(cells[22]) if len(cells) > 22 else 0
                c_t = safe_int(cells[23]) if len(cells) > 23 else 0
                c_sho = safe_int(cells[24]) if len(cells) > 24 else 0

                pkey = normalize_player_key(pname)
                goalie_stats[pkey] = {
                    "player_name": pname, "jersey_number": num_txt,
                    "goalie_gp": gp, "goalie_gs": gs, "goalie_minutes": mins,
                    "ga": ga, "gaa": gaa, "ppga": ppga, "shga": shga, "enga": enga,
                    "saves": sv, "save_pct": sv_pct, "wins": w, "losses": l, "ties": t, "shutouts": sho,
                    "conf_goalie_gp": c_gp, "conf_goalie_gs": c_gs, "conf_goalie_minutes": c_mins,
                    "conf_ga": c_ga, "conf_gaa": c_gaa, "conf_saves": c_sv, "conf_save_pct": c_sv_pct,
                    "conf_wins": c_w, "conf_losses": c_l, "conf_ties": c_t, "conf_shutouts": c_sho,
                }

    return skater_stats, goalie_stats


LEGACY_ROSTER_TYPO_MAP = {
    "Jim Mahey": "Jim Fahey",
    "Ryan Gianand": "Ryan Ginand",
    "Mike Binninnton": "Mike Binnington",
}


def parse_legacy_history_roster(html: str, season: str, url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    players = {}

    candidate_tables = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 15:
            continue
        headers = [c.get_text(" ", strip=True).lower() for c in rows[0].find_all(["th", "td"])]
        if not any("name" in h or "player" in h for h in headers) and len(rows) > 1:
            headers = [c.get_text(" ", strip=True).lower() for c in rows[1].find_all(["th", "td"])]
        if any("name" in h or "player" in h for h in headers) and any("pos" in h or "hometown" in h for h in headers):
            candidate_tables.append((table, rows, headers))

    if not candidate_tables:
        return []

    # mhky-90s-rosters has 1990-91..1999-00 in chronological order (1999-00 is the last table)
    # mhky-00s-rosters has 2000-01..2008-09 in chronological order (index = yr - 2000)
    yr = int(season[:4])
    if season == "1999-00":
        selected_tables = [candidate_tables[-1]]
    elif 2000 <= yr <= 2008 and (yr - 2000) < len(candidate_tables):
        selected_tables = [candidate_tables[yr - 2000]]
    else:
        selected_tables = candidate_tables[:1]

    for table, rows, headers in selected_tables:
        col_map = {}
        for idx, h in enumerate(headers):
            if h in ("#", "no", "no.") or "num" in h:
                col_map.setdefault("num", idx)
            elif "name" in h or "player" in h:
                col_map.setdefault("name", idx)
            elif "pos" in h:
                col_map.setdefault("pos", idx)
            elif "cl" in h or "yr" in h or "year" in h:
                col_map.setdefault("cl", idx)
            elif "ht" in h or "height" in h:
                col_map.setdefault("ht", idx)
            elif "wt" in h or "weight" in h:
                col_map.setdefault("wt", idx)
            elif "sh" in h or "cat" in h:
                col_map.setdefault("shoots", idx)
            elif "hometown" in h or "last team" in h or "high school" in h or "previous" in h:
                col_map.setdefault("hometown", idx)

        for tr in rows[1:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) < 4:
                continue
            name_idx = col_map.get("name", 1)
            if name_idx >= len(cells):
                continue
            raw_name = cells[name_idx].strip()
            if not raw_name or raw_name.lower() in ("name", "player", "full name", "no."):
                continue
            inline_capt = ""
            m_capt = re.search(r"\(([CA])\)\s*$", raw_name)
            if m_capt:
                inline_capt = m_capt.group(1).upper()
                raw_name = re.sub(r"\s*\([CA]\)\s*$", "", raw_name).strip()
            raw_name = clean_person_name(raw_name)
            raw_name = LEGACY_ROSTER_TYPO_MAP.get(raw_name, raw_name)

            def get_c(k):
                i = col_map.get(k)
                return cells[i].strip() if i is not None and i < len(cells) else ""

            num_val = re.sub(r"[^\d]", "", get_c("num"))
            pos_val = normalize_position(get_c("pos"))
            cl_val = normalize_class_year(get_c("cl"))
            ht_val = get_c("ht").replace("'", "-").replace('"', "").replace(" ", "")
            wt_val = safe_int(re.sub(r"[^\d]", "", get_c("wt")))
            sh_val = get_c("shoots")
            if sh_val.upper().startswith("L"):
                sh_val = "Left"
            elif sh_val.upper().startswith("R"):
                sh_val = "Right"
            home_raw = get_c("hometown")
            hometown_val, prev_team_val = "", ""
            if "/" in home_raw:
                parts = [p.strip() for p in home_raw.split("/", 1)]
                hometown_val, prev_team_val = parts[0], parts[1]
            elif "(" in home_raw and home_raw.endswith(")"):
                parts = home_raw[:-1].split("(", 1)
                hometown_val, prev_team_val = parts[0].strip(), parts[1].strip()
            else:
                hometown_val = home_raw

            role = lookup_leadership_role(season, raw_name, inline_capt)
            pkey = normalize_player_key(raw_name)
            players[pkey] = {
                "season": season,
                "jersey_number": num_val,
                "player_name": raw_name,
                "captain_role": role,
                "is_captain": 1 if role == "C" else 0,
                "is_alternate_captain": 1 if role == "A" else 0,
                "is_leadership": 1 if role in ("C", "A") else 0,
                "position": pos_val,
                "class_year": cl_val,
                "height": ht_val,
                "height_inches": parse_height_inches(ht_val),
                "weight": wt_val,
                "shoots": sh_val,
                "hometown": hometown_val,
                "previous_team": prev_team_val,
                "previous_school": "",
                "major": "",
                "head_coach": HEAD_COACHES.get(season, ""),
                "roster_url": url,
            }
    return list(players.values())


HOCKEY_EAST_OPPONENTS = {
    "Boston College",
    "Boston University",
    "Maine",
    "Massachusetts",
    "UMass Lowell",
    "Merrimack",
    "New Hampshire",
    "Providence",
    "Vermont",
    "UConn",
    "Notre Dame",
}


def is_hockey_east_conf_game(season: str, date_str: str, opponent: str) -> bool:
    if opponent not in HOCKEY_EAST_OPPONENTS:
        return False
    yr = int(season[:4])
    if opponent == "Vermont" and yr < 2005:
        return False
    if opponent == "UConn" and yr < 2014:
        return False
    if opponent == "Notre Dame" and not (2013 <= yr <= 2016):
        return False
    # Exclude postseason (mid-March onward) and Beanpot Mondays in February
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        if dt.month == 3 and dt.day >= 10:
            return False
        if dt.month == 2 and dt.weekday() == 0 and opponent in ("Boston College", "Boston University"):
            return False
    except Exception:
        pass
    return True


def build_season_stats_from_game_logs(
    season: str,
    all_skaters: list[dict],
    all_goalies: list[dict],
    all_goals: list[dict],
    all_games: list[dict],
) -> tuple[dict[str, dict], dict[str, dict]]:
    skater_stats = {}
    goalie_stats = {}

    # Pre-index goal events for this season by (date, opponent) and by scorer
    goals_by_game = {}
    for g_ev in all_goals:
        d = g_ev.get("date", "")
        if date_to_season(d) != season:
            continue
        opp = g_ev.get("opponent", "")
        goals_by_game.setdefault((d, opp), []).append(g_ev)

    # Sort goals in each game chronologically by period & time_seconds to identify FG (first goal of game) and GTG
    first_goal_key_by_game = {}
    for gkey, g_list in goals_by_game.items():
        def _period_ord(p):
            pu = str(p).upper()
            if pu in ("1", "1ST"):
                return 1
            if pu in ("2", "2ND"):
                return 2
            if pu in ("3", "3RD"):
                return 3
            return 4

        sorted_g = sorted(g_list, key=lambda x: (_period_ord(x.get("period", "")), safe_int(x.get("time_seconds", 0))))
        if sorted_g and sorted_g[0].get("team") == "Northeastern":
            first_goal_key_by_game[gkey] = normalize_player_key(sorted_g[0].get("scorer", ""))

    # Aggregate skater game logs
    for sk in all_skaters:
        d = sk.get("date", "")
        if date_to_season(d) != season:
            continue
        pname = sk.get("player_name", "")
        pkey = normalize_player_key(pname)
        if not pkey:
            continue
        opp = sk.get("opponent", "")
        is_conf = is_hockey_east_conf_game(season, d, opp)
        rec = skater_stats.setdefault(
            pkey,
            {
                "player_name": pname,
                "jersey_number": "",
                "gp": 0, "goals": 0, "assists": 0, "points": 0, "shots": 0, "shot_pct": 0.0,
                "plus_minus": 0, "ppg": 0, "shg": 0, "fg": 0, "gwg": 0, "gtg": 0,
                "otg": 0, "htg": 0, "uag": 0, "penalties": 0, "pim": 0,
                "minor_penalties": 0, "major_penalties": 0, "other_penalties": 0, "blocked_shots": 0,
                "conf_gp": 0, "conf_goals": 0, "conf_assists": 0, "conf_points": 0, "conf_shots": 0,
                "conf_shot_pct": 0.0, "conf_plus_minus": 0, "conf_ppg": 0, "conf_shg": 0,
                "conf_fg": 0, "conf_gwg": 0, "conf_gtg": 0, "conf_otg": 0, "conf_htg": 0,
                "conf_uag": 0, "conf_penalties": 0, "conf_pim": 0, "conf_blocked_shots": 0,
            },
        )
        g = safe_int(sk.get("goals", 0))
        a = safe_int(sk.get("assists", 0))
        pts = safe_int(sk.get("points", 0))
        sh = safe_int(sk.get("shots", 0))
        pm = safe_int(sk.get("plus_minus", 0))
        pn = safe_int(sk.get("penalties", 0))
        pim = safe_int(sk.get("penalty_minutes", 0))
        blk = safe_int(sk.get("blocked_shots", 0))
        gwg = safe_int(sk.get("gwg", 0))

        rec["gp"] += 1
        rec["goals"] += g
        rec["assists"] += a
        rec["points"] += pts
        rec["shots"] += sh
        rec["plus_minus"] += pm
        rec["penalties"] += pn
        rec["pim"] += pim
        rec["blocked_shots"] += blk
        rec["gwg"] += gwg
        if g >= 3:
            rec["htg"] += 1

        if is_conf:
            rec["conf_gp"] += 1
            rec["conf_goals"] += g
            rec["conf_assists"] += a
            rec["conf_points"] += pts
            rec["conf_shots"] += sh
            rec["conf_plus_minus"] += pm
            rec["conf_penalties"] += pn
            rec["conf_pim"] += pim
            rec["conf_blocked_shots"] += blk
            rec["conf_gwg"] += gwg
            if g >= 3:
                rec["conf_htg"] += 1

    # Add special goal counts (PPG, SHG, FG, OTG, UAG) from goal events
    for (d, opp), g_list in goals_by_game.items():
        is_conf = is_hockey_east_conf_game(season, d, opp)
        fg_pkey = first_goal_key_by_game.get((d, opp))
        if fg_pkey and fg_pkey in skater_stats:
            skater_stats[fg_pkey]["fg"] += 1
            if is_conf:
                skater_stats[fg_pkey]["conf_fg"] += 1

        for g_ev in g_list:
            if g_ev.get("team") != "Northeastern":
                continue
            pkey = normalize_player_key(g_ev.get("scorer", ""))
            if pkey not in skater_stats:
                continue
            rec = skater_stats[pkey]
            strength = str(g_ev.get("strength", "")).upper()
            if "PP" in strength:
                rec["ppg"] += 1
                if is_conf:
                    rec["conf_ppg"] += 1
            if "SH" in strength:
                rec["shg"] += 1
                if is_conf:
                    rec["conf_shg"] += 1
            if str(g_ev.get("period", "")).upper().startswith("OT"):
                rec["otg"] += 1
                if is_conf:
                    rec["conf_otg"] += 1
            if not g_ev.get("primary_assist") and not g_ev.get("secondary_assist"):
                rec["uag"] += 1
                if is_conf:
                    rec["conf_uag"] += 1

    for rec in skater_stats.values():
        rec["shot_pct"] = round(rec["goals"] / rec["shots"], 3) if rec["shots"] > 0 else 0.0
        rec["conf_shot_pct"] = round(rec["conf_goals"] / rec["conf_shots"], 3) if rec["conf_shots"] > 0 else 0.0

    # Aggregate goalie game logs
    for go in all_goalies:
        d = go.get("date", "")
        if date_to_season(d) != season:
            continue
        gname = go.get("goalie_name", "")
        pkey = normalize_player_key(gname)
        if not pkey:
            continue
        opp = go.get("opponent", "")
        is_conf = is_hockey_east_conf_game(season, d, opp)
        rec = goalie_stats.setdefault(
            pkey,
            {
                "player_name": gname,
                "jersey_number": "",
                "goalie_gp": 0, "goalie_gs": 0, "_sec": 0, "goalie_minutes": "0:00",
                "ga": 0, "gaa": 0.0, "ppga": 0, "shga": 0, "enga": 0,
                "saves": 0, "save_pct": 0.0, "wins": 0, "losses": 0, "ties": 0, "shutouts": 0,
                "conf_goalie_gp": 0, "conf_goalie_gs": 0, "_conf_sec": 0, "conf_goalie_minutes": "0:00",
                "conf_ga": 0, "conf_gaa": 0.0, "conf_saves": 0, "conf_save_pct": 0.0,
                "conf_wins": 0, "conf_losses": 0, "conf_ties": 0, "conf_shutouts": 0,
            },
        )
        mins_str = str(go.get("minutes", "0:00")).strip()
        sec = 0
        if ":" in mins_str:
            mp = mins_str.split(":", 1)
            sec = safe_int(mp[0]) * 60 + safe_int(mp[1])
        else:
            sec = safe_int(mins_str) * 60

        ga = safe_int(go.get("goals_against", 0))
        enga = safe_int(go.get("empty_net_goals", 0))
        sv = safe_int(go.get("saves", 0))
        sho = safe_int(go.get("shutouts", 0))
        dec = str(go.get("decision", "")).strip().upper()

        rec["goalie_gp"] += 1
        if dec in ("W", "L", "T") or sec >= 2400:
            rec["goalie_gs"] += 1
        rec["_sec"] += sec
        rec["ga"] += ga
        rec["enga"] += enga
        rec["saves"] += sv
        rec["shutouts"] += sho
        if dec == "W":
            rec["wins"] += 1
        elif dec == "L":
            rec["losses"] += 1
        elif dec == "T":
            rec["ties"] += 1

        if is_conf:
            rec["conf_goalie_gp"] += 1
            if dec in ("W", "L", "T") or sec >= 2400:
                rec["conf_goalie_gs"] += 1
            rec["_conf_sec"] += sec
            rec["conf_ga"] += ga
            rec["conf_saves"] += sv
            rec["conf_shutouts"] += sho
            if dec == "W":
                rec["conf_wins"] += 1
            elif dec == "L":
                rec["conf_losses"] += 1
            elif dec == "T":
                rec["conf_ties"] += 1

    for rec in goalie_stats.values():
        sec = rec.pop("_sec", 0)
        rec["goalie_minutes"] = f"{sec // 60}:{sec % 60:02d}"
        rec["gaa"] = round((rec["ga"] * 3600.0) / sec, 2) if sec > 0 else 0.0
        tot_sh = rec["saves"] + rec["ga"]
        rec["save_pct"] = round(rec["saves"] / tot_sh, 3) if tot_sh > 0 else 0.0

        csec = rec.pop("_conf_sec", 0)
        rec["conf_goalie_minutes"] = f"{csec // 60}:{csec % 60:02d}"
        rec["conf_gaa"] = round((rec["conf_ga"] * 3600.0) / csec, 2) if csec > 0 else 0.0
        ctot_sh = rec["conf_saves"] + rec["conf_ga"]
        rec["conf_save_pct"] = round(rec["conf_saves"] / ctot_sh, 3) if ctot_sh > 0 else 0.0

        # Ensure goalies also appear in skater_stats with their GP so they get full rows
        gpkey = normalize_player_key(rec["player_name"])
        if gpkey not in skater_stats:
            skater_stats[gpkey] = {
                "player_name": rec["player_name"],
                "jersey_number": rec.get("jersey_number", ""),
                "gp": rec["goalie_gp"], "goals": 0, "assists": 0, "points": 0, "shots": 0, "shot_pct": 0.0,
                "plus_minus": 0, "ppg": 0, "shg": 0, "fg": 0, "gwg": 0, "gtg": 0,
                "otg": 0, "htg": 0, "uag": 0, "penalties": 0, "pim": 0,
                "minor_penalties": 0, "major_penalties": 0, "other_penalties": 0, "blocked_shots": 0,
                "conf_gp": rec["conf_goalie_gp"], "conf_goals": 0, "conf_assists": 0, "conf_points": 0, "conf_shots": 0,
                "conf_shot_pct": 0.0, "conf_plus_minus": 0, "conf_ppg": 0, "conf_shg": 0,
                "conf_fg": 0, "conf_gwg": 0, "conf_gtg": 0, "conf_otg": 0, "conf_htg": 0,
                "conf_uag": 0, "conf_penalties": 0, "conf_pim": 0, "conf_blocked_shots": 0,
            }

    return skater_stats, goalie_stats


async def scrape_rosters_and_cumulative_stats(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    index: dict,
    all_skaters: list[dict],
    all_goalies: list[dict],
    all_goals: list[dict],
    all_games: list[dict],
) -> tuple[list[dict], list[dict], dict]:
    print("\n4. Scraping seasonal rosters, leadership (C/A), bios, and cumulative season stats (1999-2027)...")
    seasons = [f"{yr}-{str(yr + 1)[-2:]}" for yr in range(1999, 2027)]

    # 1. Discover any legacy roster URLs from the Men's Hockey History archive page
    legacy_roster_urls = {}
    history_url = "https://nuhuskies.com/sports/2010/3/31/MXC_0331103506.aspx"
    hist_html, _ = await fetch_or_load_html(client, semaphore, history_url, index)
    if hist_html:
        hsoup = BeautifulSoup(hist_html, "html.parser")
        for tr in hsoup.find_all("tr"):
            row_txt = tr.get_text(" ", strip=True)
            m_sea = re.search(r"\b(1999-00|200\d-\d{2})\b", row_txt)
            if not m_sea:
                continue
            sea = m_sea.group(1)
            for a in tr.find_all("a", href=True):
                if "roster" in a.get_text(" ", strip=True).lower():
                    href = a["href"].strip()
                    if not href.startswith("http"):
                        href = f"https://nuhuskies.com/{href.lstrip('/')}"
                    legacy_roster_urls[sea] = href

    # 2. Fetch modern roster pages (2009-10 to 2026-27) + legacy roster pages (1999-00 to 2008-09)
    roster_tasks = {}
    for sea in seasons:
        yr = int(sea[:4])
        if yr >= 2009:
            r_url = f"https://nuhuskies.com/sports/mens-ice-hockey/roster/{sea}"
        else:
            r_url = legacy_roster_urls.get(sea, "")
        if r_url:
            roster_tasks[sea] = fetch_or_load_html(client, semaphore, r_url, index)

    roster_html_map = {}
    if roster_tasks:
        results = await asyncio.gather(*roster_tasks.values())
        for sea, (r_html, r_url) in zip(roster_tasks.keys(), results):
            roster_html_map[sea] = (r_html, r_url)

    # 3. Parse rosters and collect player bio URLs
    rosters_by_season_key = {}  # (season, pkey) -> dict
    all_bio_urls = {}  # pkey -> bio_url
    for sea in seasons:
        r_html, r_url = roster_html_map.get(sea, ("", ""))
        if not r_html:
            continue
        yr = int(sea[:4])
        if yr >= 2009:
            rows, bios = parse_modern_roster_html(r_html, sea, r_url)
            all_bio_urls.update(bios)
        else:
            rows = parse_legacy_history_roster(r_html, sea, r_url)
        for row in rows:
            pkey = normalize_player_key(row["player_name"])
            rosters_by_season_key[(sea, pkey)] = row

    # Ensure all KNOWN_LEADERSHIP captains and alternates (including upcoming 2026-27 leadership) exist in rosters_by_season_key
    for sea, l_dict in KNOWN_LEADERSHIP.items():
        seen_in_sea = set()
        for role_code in ("C", "A"):
            for raw_ldr in l_dict.get(role_code, []):
                pkey = normalize_player_key(raw_ldr)
                if pkey in seen_in_sea:
                    continue
                seen_in_sea.add(pkey)
                if (sea, pkey) not in rosters_by_season_key:
                    rosters_by_season_key[(sea, pkey)] = {
                        "season": sea,
                        "jersey_number": "",
                        "player_name": raw_ldr,
                        "captain_role": role_code,
                        "is_captain": 1 if role_code == "C" else 0,
                        "is_alternate_captain": 1 if role_code == "A" else 0,
                        "is_leadership": 1,
                        "position": "",
                        "class_year": "",
                        "height": "",
                        "height_inches": 0,
                        "weight": 0,
                        "shoots": "",
                        "hometown": "",
                        "previous_team": "",
                        "previous_school": "",
                        "major": "",
                        "head_coach": HEAD_COACHES.get(sea, ""),
                        "roster_url": f"https://nuhuskies.com/sports/mens-ice-hockey/roster/{sea}",
                    }

    # 4. Fetch unique player bio pages to enrich major / shoots / hometown
    if all_bio_urls:
        bio_keys = list(all_bio_urls.keys())
        bio_tasks = [fetch_or_load_html(client, semaphore, all_bio_urls[k], index) for k in bio_keys]
        bio_results = await asyncio.gather(*bio_tasks)
        bio_meta_by_key = {}
        for k, (b_html, _) in zip(bio_keys, bio_results):
            if b_html:
                bio_meta_by_key[k] = parse_bio_for_metadata(b_html)
        for (sea, pkey), rec in rosters_by_season_key.items():
            bmeta = bio_meta_by_key.get(pkey)
            if bmeta:
                if not rec["major"] and bmeta.get("major"):
                    rec["major"] = bmeta["major"]
                if not rec["shoots"] and bmeta.get("shoots"):
                    rec["shoots"] = bmeta["shoots"]
                if not rec["previous_team"] and bmeta.get("previous_team"):
                    rec["previous_team"] = bmeta["previous_team"]
                if not rec["hometown"] and bmeta.get("hometown"):
                    rec["hometown"] = bmeta["hometown"]

    # 5. Fetch cumulative stats pages for all seasons (1999-00 to 2026-27)
    stats_tasks = {}
    for sea in seasons:
        yr = int(sea[:4])
        if yr >= 2011:
            s_url = f"https://nuhuskies.com/sports/mens-ice-hockey/stats/{sea}"
        else:
            yy1 = str(yr)[-2:]
            yy2 = str(yr + 1)[-2:]
            s_url = f"https://static.gonu.com/custompages/mhockey/MHK{yy1}{yy2}/HTML/teamcume.htm"
        stats_tasks[sea] = fetch_or_load_html(client, semaphore, s_url, index)

    stats_results = await asyncio.gather(*stats_tasks.values())

    # Pre-compute game-log special goal counts (OTGs, hat tricks, unassisted goals) by (season, pkey) for legacy backfill
    legacy_special = {}
    for g_ev in all_goals:
        if g_ev.get("team") != "Northeastern":
            continue
        sea = date_to_season(g_ev.get("date", ""))
        pkey = normalize_player_key(g_ev.get("scorer", ""))
        if not sea or not pkey:
            continue
        sp = legacy_special.setdefault((sea, pkey), {"otg": 0, "uag": 0, "htg": 0})
        if str(g_ev.get("period", "")).upper().startswith("OT"):
            sp["otg"] += 1
        if not g_ev.get("primary_assist") and not g_ev.get("secondary_assist"):
            sp["uag"] += 1

    for sk_ev in all_skaters:
        if safe_int(sk_ev.get("goals", 0)) >= 3:
            sea = date_to_season(sk_ev.get("date", ""))
            pkey = normalize_player_key(sk_ev.get("player_name", ""))
            if sea and pkey:
                sp = legacy_special.setdefault((sea, pkey), {"otg": 0, "uag": 0, "htg": 0})
                sp["htg"] += 1

    all_season_stats = []
    for sea, (s_html, s_url) in zip(stats_tasks.keys(), stats_results):
        yr = int(sea[:4])
        sk_map, go_map = {}, {}
        if s_html:
            if yr >= 2011:
                sk_map, go_map = parse_modern_cumulative_stats(s_html, sea, s_url)
            else:
                sk_map, go_map = parse_legacy_teamcume(s_html, sea, s_url)
                # Backfill legacy special goal counts from box score events
                for pkey, srec in sk_map.items():
                    sp = legacy_special.get((sea, pkey), {})
                    srec["otg"] = sp.get("otg", 0)
                    srec["uag"] = sp.get("uag", 0)
                    srec["htg"] = sp.get("htg", 0)

        # Fallback: if cumulative stats page wasn't available or didn't match (e.g., 1999-00 to 2011-12),
        # aggregate complete Overall & Hockey East Conference cumulative stats from the parsed game logs!
        if not sk_map and yr <= 2025:
            sk_map, go_map = build_season_stats_from_game_logs(sea, all_skaters, all_goalies, all_goals, all_games)

        roster_pkeys_for_sea = {pk for (s, pk) in rosters_by_season_key.keys() if s == sea}
        all_pkeys = sorted(set(sk_map.keys()) | set(go_map.keys()) | roster_pkeys_for_sea)
        for pkey in all_pkeys:
            sk = sk_map.get(pkey, {})
            go = go_map.get(pkey, {})
            roster_rec = rosters_by_season_key.get((sea, pkey))
            pname = (roster_rec or {}).get("player_name") or sk.get("player_name") or go.get("player_name") or ""
            jnum = (roster_rec or {}).get("jersey_number") or sk.get("jersey_number") or go.get("jersey_number") or ""
            role = (roster_rec or {}).get("captain_role") or lookup_leadership_role(sea, pname)
            pos = (roster_rec or {}).get("position") or ("G" if pkey in go_map and sk.get("shots", 0) == 0 else "F")

            # If this player was missing from rosters_by_season_key (e.g., mid-season callup), add them!
            if not roster_rec:
                roster_rec = {
                    "season": sea,
                    "jersey_number": jnum,
                    "player_name": pname,
                    "captain_role": role,
                    "is_captain": 1 if role == "C" else 0,
                    "is_alternate_captain": 1 if role == "A" else 0,
                    "is_leadership": 1 if role in ("C", "A") else 0,
                    "position": pos,
                    "class_year": "",
                    "height": "",
                    "height_inches": 0,
                    "weight": 0,
                    "shoots": "",
                    "hometown": "",
                    "previous_team": "",
                    "previous_school": "",
                    "major": "",
                    "head_coach": HEAD_COACHES.get(sea, ""),
                    "roster_url": s_url,
                }
                rosters_by_season_key[(sea, pkey)] = roster_rec

            stat_row = {
                "season": sea,
                "jersey_number": jnum,
                "player_name": pname,
                "captain_role": role,
                "is_captain": 1 if role == "C" else 0,
                "is_alternate_captain": 1 if role == "A" else 0,
                "is_leadership": 1 if role in ("C", "A") else 0,
                "position": pos,
                "class_year": roster_rec.get("class_year", ""),
                "height": roster_rec.get("height", ""),
                "weight": roster_rec.get("weight", 0),
                "shoots": roster_rec.get("shoots", ""),
                "hometown": roster_rec.get("hometown", ""),
                "previous_team": roster_rec.get("previous_team", ""),
                "major": roster_rec.get("major", ""),
                "head_coach": HEAD_COACHES.get(sea, ""),
                # Overall Skater Stats
                "gp": sk.get("gp", go.get("goalie_gp", 0)),
                "goals": sk.get("goals", 0),
                "assists": sk.get("assists", 0),
                "points": sk.get("points", 0),
                "shots": sk.get("shots", 0),
                "shot_pct": sk.get("shot_pct", 0.0),
                "plus_minus": sk.get("plus_minus", 0),
                "ppg": sk.get("ppg", 0),
                "shg": sk.get("shg", 0),
                "fg": sk.get("fg", 0),
                "gwg": sk.get("gwg", 0),
                "gtg": sk.get("gtg", 0),
                "otg": sk.get("otg", 0),
                "htg": sk.get("htg", 0),
                "uag": sk.get("uag", 0),
                "penalties": sk.get("penalties", 0),
                "pim": sk.get("pim", 0),
                "minor_penalties": sk.get("minor_penalties", 0),
                "major_penalties": sk.get("major_penalties", 0),
                "other_penalties": sk.get("other_penalties", 0),
                "blocked_shots": sk.get("blocked_shots", 0),
                # Conference Skater Stats
                "conf_gp": sk.get("conf_gp", go.get("conf_goalie_gp", 0)),
                "conf_goals": sk.get("conf_goals", 0),
                "conf_assists": sk.get("conf_assists", 0),
                "conf_points": sk.get("conf_points", 0),
                "conf_shots": sk.get("conf_shots", 0),
                "conf_shot_pct": sk.get("conf_shot_pct", 0.0),
                "conf_plus_minus": sk.get("conf_plus_minus", 0),
                "conf_ppg": sk.get("conf_ppg", 0),
                "conf_shg": sk.get("conf_shg", 0),
                "conf_fg": sk.get("conf_fg", 0),
                "conf_gwg": sk.get("conf_gwg", 0),
                "conf_gtg": sk.get("conf_gtg", 0),
                "conf_otg": sk.get("conf_otg", 0),
                "conf_htg": sk.get("conf_htg", 0),
                "conf_uag": sk.get("conf_uag", 0),
                "conf_penalties": sk.get("conf_penalties", 0),
                "conf_pim": sk.get("conf_pim", 0),
                "conf_blocked_shots": sk.get("conf_blocked_shots", 0),
                # Overall Goalie Stats
                "goalie_gp": go.get("goalie_gp", 0),
                "goalie_gs": go.get("goalie_gs", 0),
                "goalie_minutes": go.get("goalie_minutes", "0:00"),
                "ga": go.get("ga", 0),
                "gaa": go.get("gaa", 0.0),
                "ppga": go.get("ppga", 0),
                "shga": go.get("shga", 0),
                "enga": go.get("enga", 0),
                "saves": go.get("saves", 0),
                "save_pct": go.get("save_pct", 0.0),
                "wins": go.get("wins", 0),
                "losses": go.get("losses", 0),
                "ties": go.get("ties", 0),
                "shutouts": go.get("shutouts", 0),
                # Conference Goalie Stats
                "conf_goalie_gp": go.get("conf_goalie_gp", 0),
                "conf_goalie_gs": go.get("conf_goalie_gs", 0),
                "conf_goalie_minutes": go.get("conf_goalie_minutes", "0:00"),
                "conf_ga": go.get("conf_ga", 0),
                "conf_gaa": go.get("conf_gaa", 0.0),
                "conf_saves": go.get("conf_saves", 0),
                "conf_save_pct": go.get("conf_save_pct", 0.0),
                "conf_wins": go.get("conf_wins", 0),
                "conf_losses": go.get("conf_losses", 0),
                "conf_ties": go.get("conf_ties", 0),
                "conf_shutouts": go.get("conf_shutouts", 0),
                "stats_url": s_url,
            }
            all_season_stats.append(stat_row)

    # Propagate static player traits (height, shoots, hometown, previous_team, major, position) across seasons for the same player
    traits_by_pkey = {}
    for (sea, pkey), rec in sorted(rosters_by_season_key.items()):
        t = traits_by_pkey.setdefault(pkey, {})
        for field in ("position", "height", "height_inches", "weight", "shoots", "hometown", "previous_team", "previous_school", "major"):
            if rec.get(field):
                t[field] = rec[field]

    for (sea, pkey), rec in rosters_by_season_key.items():
        t = traits_by_pkey.get(pkey, {})
        for field in ("position", "height", "height_inches", "weight", "shoots", "hometown", "previous_team", "previous_school", "major"):
            if not rec.get(field) and t.get(field):
                rec[field] = t[field]

    for srow in all_season_stats:
        pkey = normalize_player_key(srow["player_name"])
        rrec = rosters_by_season_key.get((srow["season"], pkey), {})
        for field in ("position", "class_year", "height", "weight", "shoots", "hometown", "previous_team", "major"):
            if not srow.get(field) and rrec.get(field):
                srow[field] = rrec[field]

    all_rosters = sorted(
        rosters_by_season_key.values(),
        key=lambda x: (x.get("season", ""), safe_int(x.get("jersey_number", 99)), x.get("player_name", "")),
    )
    all_season_stats.sort(
        key=lambda x: (x.get("season", ""), -safe_int(x.get("points", 0)), -safe_int(x.get("gp", 0)), x.get("player_name", ""))
    )
    return all_rosters, all_season_stats, rosters_by_season_key


async def run_pipeline():
    start_time = time.time()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    index = {}
    if INDEX_FILE.exists():
        try:
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                index = json.load(f)
        except Exception:
            index = {}

    limits = httpx.Limits(max_keepalive_connections=25, max_connections=40)
    async with httpx.AsyncClient(headers=HEADERS, limits=limits, follow_redirects=True, verify=False) as client:
        all_urls = await gather_all_game_urls(client)

        cached_count = sum(1 for u in all_urls if (CACHE_DIR / url_to_filename(u)).exists())
        print(f"2. Cache Status: {cached_count}/{len(all_urls)} already cached.")
        print("   Fetching any missing box scores...")

        semaphore = asyncio.Semaphore(25)
        tasks = [fetch_or_load_html(client, semaphore, url, index) for url in all_urls]
        html_results = await asyncio.gather(*tasks)

        print("\n3. Parsing box scores for games, skaters, goalies, goals, penalties, and shootouts...")
        all_games = []
        all_skaters = []
        all_goalies = []
        all_goals = []
        all_penalties = []
        all_shootouts = []

        for html, url in html_results:
            if not html:
                continue
            try:
                gm, sk, go, goals, pens, shootouts = parse_boxscore(html, url)
                all_games.append(gm)
                all_skaters.extend(sk)
                all_goalies.extend(go)
                all_goals.extend(goals)
                all_penalties.extend(pens)
                all_shootouts.extend(shootouts)
            except Exception:
                continue

        def standardize_date(d: str) -> str:
            if not d:
                return ""
            d = str(d).strip()
            if d == "Dec. 29, 200":
                return "2000-12-29"
            if d.startswith("Oct.27,"):
                d = d.replace("Oct.27,", "Oct. 27,")
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%b %d, %Y", "%B %d, %Y", "%b. %d, %Y"):
                try:
                    return datetime.strptime(d, fmt).strftime("%Y-%m-%d")
                except ValueError:
                    pass
            return d

        for dataset in (all_games, all_skaters, all_goalies, all_goals, all_penalties, all_shootouts):
            for r in dataset:
                r["date"] = standardize_date(r.get("date", ""))

        all_rosters, all_season_stats, rosters_by_season_key = await scrape_rosters_and_cumulative_stats(
            client, semaphore, index, all_skaters, all_goalies, all_goals, all_games
        )

        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)

    # Export all 8 CSV datasets
    games_csv = "northeastern_game_results.csv"
    skater_csv = "northeastern_hockey_stats_mcp.csv"
    goalie_csv = "northeastern_goalie_stats.csv"
    goals_csv = "northeastern_goal_events.csv"
    penalties_csv = "northeastern_penalty_events.csv"
    shootouts_csv = "northeastern_shootout_events.csv"
    rosters_csv = "northeastern_rosters.csv"
    season_stats_csv = "northeastern_season_stats.csv"

    valid_games = [g for g in all_games if g.get("date") and g.get("opponent") != "Unknown"]
    if valid_games:
        for r in valid_games:
            r["season"] = date_to_season(r.get("date", ""))
        valid_games.sort(key=lambda x: x.get("date", ""))
        gm_keys = ["date", "season", "opponent", "location", "nu_goals", "opp_goals", "outcome", "overtime_status", "is_overtime", "is_shootout", "shootout_winner", "is_shutout", "shutout_team", "nu_pp_goals", "nu_pp_opps", "opp_pp_goals", "opp_pp_opps", "boxscore_url"]
        with open(games_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=gm_keys, extrasaction="ignore")
            w.writeheader()
            w.writerows(valid_games)

    if all_skaters:
        for r in all_skaters:
            sea = date_to_season(r.get("date", ""))
            pkey = normalize_player_key(r.get("player_name", ""))
            rrec = rosters_by_season_key.get((sea, pkey), {})
            r["season"] = sea
            r["captain_role"] = rrec.get("captain_role") or lookup_leadership_role(sea, r.get("player_name", ""))
            r["position"] = rrec.get("position", "")
            r["class_year"] = rrec.get("class_year", "")
        all_skaters.sort(key=lambda x: x.get("date", ""))
        sk_keys = ["date", "season", "opponent", "nu_goals", "opp_goals", "player_name", "position", "class_year", "captain_role", "goals", "assists", "points", "shots", "plus_minus", "penalties", "penalty_minutes", "faceoffs_won", "faceoffs_lost", "blocked_shots", "gwg", "is_overtime", "is_shutout", "boxscore_url"]
        with open(skater_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=sk_keys)
            w.writeheader()
            w.writerows(all_skaters)

    if all_goalies:
        for r in all_goalies:
            sea = date_to_season(r.get("date", ""))
            pkey = normalize_player_key(r.get("goalie_name", ""))
            rrec = rosters_by_season_key.get((sea, pkey), {})
            r["season"] = sea
            r["captain_role"] = rrec.get("captain_role") or lookup_leadership_role(sea, r.get("goalie_name", ""))
            r["class_year"] = rrec.get("class_year", "")
        all_goalies.sort(key=lambda x: x.get("date", ""))
        go_keys = ["date", "season", "opponent", "nu_goals", "opp_goals", "goalie_name", "class_year", "captain_role", "decision", "minutes", "goals_against", "empty_net_goals", "saves", "shots_against", "save_pct", "shutouts", "is_overtime", "boxscore_url"]
        with open(goalie_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=go_keys)
            w.writeheader()
            w.writerows(all_goalies)

    if all_goals:
        for r in all_goals:
            r["season"] = date_to_season(r.get("date", ""))
        all_goals.sort(key=lambda x: x.get("date", ""))
        goal_keys = ["date", "season", "opponent", "period", "time", "time_seconds", "seconds_remaining", "team", "scorer", "primary_assist", "secondary_assist", "strength", "is_gwg", "nu_score_after", "opp_score_after", "boxscore_url"]
        with open(goals_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=goal_keys)
            w.writeheader()
            w.writerows(all_goals)

    if all_penalties:
        for r in all_penalties:
            r["season"] = date_to_season(r.get("date", ""))
        all_penalties.sort(key=lambda x: x.get("date", ""))
        pen_keys = ["date", "season", "opponent", "period", "time", "team", "player_name", "penalty_minutes", "infraction", "boxscore_url"]
        with open(penalties_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=pen_keys)
            w.writeheader()
            w.writerows(all_penalties)

    if all_shootouts:
        for r in all_shootouts:
            r["season"] = date_to_season(r.get("date", ""))
        all_shootouts.sort(key=lambda x: x.get("date", ""))
        so_keys = ["date", "season", "opponent", "round", "shooter_team", "shooter_name", "result", "goalie_team", "goalie_name", "shootout_winner", "is_shootout_winner", "boxscore_url"]
        with open(shootouts_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=so_keys)
            w.writeheader()
            w.writerows(all_shootouts)

    if all_rosters:
        roster_keys = [
            "season", "jersey_number", "player_name", "captain_role", "is_captain",
            "is_alternate_captain", "is_leadership", "position", "class_year",
            "height", "height_inches", "weight", "shoots", "hometown",
            "previous_team", "previous_school", "major", "head_coach", "roster_url", "image_url",
        ]
        with open(rosters_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=roster_keys)
            w.writeheader()
            w.writerows(all_rosters)

    if all_season_stats:
        season_stat_keys = [
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
        with open(season_stats_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=season_stat_keys)
            w.writeheader()
            w.writerows(all_season_stats)

    elapsed = time.time() - start_time
    print(f"\n==========================================")
    print(f"PIPELINE COMPLETE in {elapsed:.1f}s")
    print(f"  Game Results:     {len(valid_games)} games     -> {games_csv}")
    print(f"  Skaters:          {len(all_skaters)} records   -> {skater_csv}")
    print(f"  Goalies:          {len(all_goalies)} records   -> {goalie_csv}")
    print(f"  Goals:            {len(all_goals)} events    -> {goals_csv}")
    print(f"  Penalties:        {len(all_penalties)} events    -> {penalties_csv}")
    print(f"  Shootout Attempts:{len(all_shootouts)} shots     -> {shootouts_csv}")
    print(f"  Rosters & Bios:   {len(all_rosters)} players   -> {rosters_csv}")
    print(f"  Cumulative Stats: {len(all_season_stats)} seasons   -> {season_stats_csv}")
    print(f"==========================================\n")


if __name__ == "__main__":
    asyncio.run(run_pipeline())

