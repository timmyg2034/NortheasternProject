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
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            return f"{parts[1]} {parts[0]}"
    return name


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
                if "northeastern" in team_name.lower():
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

    game_record = {
        "date": date,
        "opponent": opponent,
        "nu_goals": nu_goals,
        "opp_goals": opp_goals,
        "outcome": outcome,
        "overtime_status": ot_status,
        "is_overtime": is_ot,
        "is_shootout": is_shootout,
        "shootout_winner": shootout_winner,
        "is_shutout": is_shutout,
        "shutout_team": shutout_team,
        "boxscore_url": url,
    }

    # 3. PARSE SKATERS
    skaters = []
    for t in soup.find_all("table"):
        cap = t.find("caption")
        cap_text = cap.get_text().lower() if cap else ""
        if "northeastern" in cap_text and ("goalkeeping" not in cap_text and "faceoff" not in cap_text and "power" not in cap_text):
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
        if "northeastern" in cap_text and ("goal" in cap_text or "save" in cap_text or "keeper" in cap_text):
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
                        a_parts = [clean_person_name(a) for a in assists_str.split(",")]
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

                    goal_events.append({
                        "date": date,
                        "opponent": opponent,
                        "period": prd,
                        "time": time_str,
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


def parse_legacy_boxscore(soup, url, html):
    """Parses legacy Gonu box scores for games, skaters, goalies, goals, penalties, and shootouts."""
    title = soup.title.string.strip() if soup.title else ""
    m = re.search(r'Northeastern\s+(?:vs\.?|at)\s+(.+?)\s+\((.+?)\)', title, re.IGNORECASE)
    if not m:
        m = re.search(r'(.+?)\s+(?:vs\.?|at)\s+Northeastern\s+\((.+?)\)', title, re.IGNORECASE)
    opponent = m.group(1).strip() if m else "Unknown"
    date = m.group(2).strip() if m else ""

    if not date:
        dm = re.search(r'Date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})', html)
        if dm:
            date = dm.group(1)

    nu_goals = 0
    opp_goals = 0
    legacy_ot_col = False

    # Score from Goals by Period table
    for t in soup.find_all("table"):
        txt = t.get_text()
        if "Goals by Period" in txt:
            for r in t.find_all("tr"):
                cols = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
                if any(re.search(r'^(?:OT|2OT|3OT|SO)$', c, re.IGNORECASE) for c in cols):
                    legacy_ot_col = True
                if cols and "Northeastern" in cols[0] and len(cols) >= 5:
                    try: nu_goals = int(cols[-1])
                    except ValueError: pass
                elif cols and len(cols) >= 5 and cols[0] != "Goals by Period":
                    try:
                        opp_goals = int(cols[-1])
                        if opponent == "Unknown":
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

    game_record = {
        "date": date,
        "opponent": opponent,
        "nu_goals": nu_goals,
        "opp_goals": opp_goals,
        "outcome": outcome,
        "overtime_status": ot_status,
        "is_overtime": is_ot,
        "is_shootout": 0,
        "shootout_winner": "None",
        "is_shutout": is_shutout,
        "shutout_team": shutout_team,
        "boxscore_url": url,
    }

    # 1. PARSE SKATERS
    skaters = []
    for t in soup.find_all("table"):
        rows = t.find_all("tr")
        for i, r in enumerate(rows):
            cols = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
            if len(cols) >= 4 and cols[0] == "Northeastern" and "G" in cols and "A" in cols:
                for r2 in rows[i + 1:]:
                    c2 = [c.get_text(strip=True) for c in r2.find_all(["td", "th"])]
                    if any("total" in str(x).lower() for x in c2): break
                    if len(c2) >= 8:
                        p_name = clean_person_name(c2[2])
                        if not p_name or any(x in p_name.lower() for x in ["totals", "team"]):
                            continue
                        try:
                            goals = int(c2[3])
                            assists = int(c2[4])
                            shots = int(c2[8]) if len(c2) > 8 and c2[8].isdigit() else (int(c2[7]) if len(c2) > 7 and c2[7].isdigit() else 0)
                            pm_str = c2[9] if len(c2) > 9 else (c2[8] if len(c2) > 8 else "0")
                            plus_minus = int(pm_str.replace("+", ""))
                        except (ValueError, IndexError):
                            continue

                        pen_count, pen_mins = 0, 0
                        pen_col = c2[-1] if len(c2) >= 10 else ""
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
    for t in soup.find_all("table"):
        rows = t.find_all("tr")
        for i, r in enumerate(rows):
            cols = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
            if len(cols) >= 4 and cols[0] == "Northeastern" and "Minutes" in cols and "GA" in cols:
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
    for t in soup.find_all("table"):
        txt = t.get_text()
        if "Scoring Summary" in txt and "Scored by" in txt:
            nu_running = 0
            opp_running = 0
            gwg_goal_num = (opp_goals + 1) if nu_goals > opp_goals else -1
            nu_goal_count = 0

            for r in t.find_all("tr"):
                cols = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
                if len(cols) >= 6 and cols[0] != "#" and re.match(r'^(?:1st|2nd|3rd|ot|2ot|3ot)\b', cols[1].strip(), re.IGNORECASE):
                    prd = cols[1].strip()
                    time_str = cols[2]
                    team_code = cols[3]
                    strength = cols[4] if len(cols) > 4 else "EVEN"
                    raw_scorer = cols[5] if len(cols) > 5 else ""
                    scorer = clean_person_name(re.sub(r'/\d+', '', raw_scorer))
                    assists_str = cols[6] if len(cols) > 6 else ""

                    if re.match(r'^(?:ot|2ot|3ot)\b', prd, re.IGNORECASE):
                        game_record["is_overtime"] = 1
                        if game_record["overtime_status"] == "REG":
                            game_record["overtime_status"] = "OT"

                    primary_assist = ""
                    secondary_assist = ""
                    if assists_str and assists_str not in ["-", "unassisted", "None"]:
                        a_tokens = [clean_person_name(x) for x in re.split(r'[,;]|\s{2,}', assists_str) if x.strip()]
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

                    goal_events.append({
                        "date": date,
                        "opponent": opponent,
                        "period": prd,
                        "time": time_str,
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
    for t in soup.find_all("table"):
        txt = t.get_text()
        if "Penalty Summary" in txt and "Offense" in txt:
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
    if "sidearm" in html or "nuhuskies.com" in url:
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
                        if ("boxscore" in href or "box score" in text or "stats" in text or "/stats/" in href) and "roster" not in href and "cumulative" not in href:
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

        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)

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
        except Exception as e:
            continue

    # Export all 6 CSV datasets
    games_csv = "northeastern_game_results.csv"
    skater_csv = "northeastern_hockey_stats_mcp.csv"
    goalie_csv = "northeastern_goalie_stats.csv"
    goals_csv = "northeastern_goal_events.csv"
    penalties_csv = "northeastern_penalty_events.csv"
    shootouts_csv = "northeastern_shootout_events.csv"

    def standardize_date(d: str) -> str:
        if not d:
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

    valid_games = [g for g in all_games if g.get("date") and g.get("opponent") != "Unknown"]
    if valid_games:
        for r in valid_games:
            r["date"] = standardize_date(r.get("date", ""))
        valid_games.sort(key=lambda x: x.get("date", ""))
        gm_keys = ["date", "opponent", "nu_goals", "opp_goals", "outcome", "overtime_status", "is_overtime", "is_shootout", "shootout_winner", "is_shutout", "shutout_team", "boxscore_url"]
        with open(games_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=gm_keys)
            w.writeheader()
            w.writerows(valid_games)

    if all_skaters:
        for r in all_skaters:
            r["date"] = standardize_date(r.get("date", ""))
        all_skaters.sort(key=lambda x: x.get("date", ""))
        sk_keys = ["date", "opponent", "nu_goals", "opp_goals", "player_name", "goals", "assists", "points", "shots", "plus_minus", "penalties", "penalty_minutes", "faceoffs_won", "faceoffs_lost", "blocked_shots", "gwg", "is_overtime", "is_shutout", "boxscore_url"]
        with open(skater_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=sk_keys)
            w.writeheader()
            w.writerows(all_skaters)

    if all_goalies:
        for r in all_goalies:
            r["date"] = standardize_date(r.get("date", ""))
        all_goalies.sort(key=lambda x: x.get("date", ""))
        go_keys = ["date", "opponent", "nu_goals", "opp_goals", "goalie_name", "decision", "minutes", "goals_against", "empty_net_goals", "saves", "shots_against", "save_pct", "shutouts", "is_overtime", "boxscore_url"]
        with open(goalie_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=go_keys)
            w.writeheader()
            w.writerows(all_goalies)

    if all_goals:
        for r in all_goals:
            r["date"] = standardize_date(r.get("date", ""))
        all_goals.sort(key=lambda x: x.get("date", ""))
        goal_keys = ["date", "opponent", "period", "time", "team", "scorer", "primary_assist", "secondary_assist", "strength", "is_gwg", "nu_score_after", "opp_score_after", "boxscore_url"]
        with open(goals_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=goal_keys)
            w.writeheader()
            w.writerows(all_goals)

    if all_penalties:
        for r in all_penalties:
            r["date"] = standardize_date(r.get("date", ""))
        all_penalties.sort(key=lambda x: x.get("date", ""))
        pen_keys = ["date", "opponent", "period", "time", "team", "player_name", "penalty_minutes", "infraction", "boxscore_url"]
        with open(penalties_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=pen_keys)
            w.writeheader()
            w.writerows(all_penalties)

    if all_shootouts:
        for r in all_shootouts:
            r["date"] = standardize_date(r.get("date", ""))
        all_shootouts.sort(key=lambda x: x.get("date", ""))
        so_keys = ["date", "opponent", "round", "shooter_team", "shooter_name", "result", "goalie_team", "goalie_name", "shootout_winner", "is_shootout_winner", "boxscore_url"]
        with open(shootouts_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=so_keys)
            w.writeheader()
            w.writerows(all_shootouts)

    elapsed = time.time() - start_time
    print(f"\n==========================================")
    print(f"PIPELINE COMPLETE in {elapsed:.1f}s")
    print(f"  Game Results:     {len(all_games)} games     -> {games_csv}")
    print(f"  Skaters:          {len(all_skaters)} records   -> {skater_csv}")
    print(f"  Goalies:          {len(all_goalies)} records   -> {goalie_csv}")
    print(f"  Goals:            {len(all_goals)} events    -> {goals_csv}")
    print(f"  Penalties:        {len(all_penalties)} events    -> {penalties_csv}")
    print(f"  Shootout Attempts:{len(all_shootouts)} shots     -> {shootouts_csv}")
    print(f"==========================================\n")


if __name__ == "__main__":
    asyncio.run(run_pipeline())
