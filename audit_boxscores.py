import asyncio
import csv
import json
import urllib.parse
import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

async def check_url(client_strict: httpx.AsyncClient, client_loose: httpx.AsyncClient, sem: asyncio.Semaphore, url: str):
    async with sem:
        res = {
            "url": url,
            "strict_ok": False,
            "strict_status": None,
            "strict_error": None,
            "strict_final_url": None,
            "loose_ok": False,
            "loose_status": None,
            "loose_final_url": None,
            "length": 0,
            "title": "",
            "has_boxscore_content": False,
        }
        try:
            r = await client_strict.get(url, timeout=10.0)
            res["strict_status"] = r.status_code
            res["strict_final_url"] = str(r.url)
            res["length"] = len(r.text)
            soup = BeautifulSoup(r.text, "html.parser")
            res["title"] = soup.title.get_text(strip=True) if soup.title else ""
            txt_lower = r.text.lower()
            has_content = (
                r.status_code == 200
                and len(r.text) > 800
                and ("scoring summary" in txt_lower or "penalty summary" in txt_lower or "box score" in txt_lower or "goals by period" in txt_lower)
                and "page not found" not in txt_lower
                and "404 - file or directory not found" not in txt_lower
            )
            res["has_boxscore_content"] = has_content
            res["strict_ok"] = has_content
            res["loose_ok"] = has_content
            res["loose_status"] = r.status_code
            res["loose_final_url"] = str(r.url)
            return res
        except Exception as e:
            res["strict_error"] = f"{type(e).__name__}: {str(e)[:120]}"

        try:
            r2 = await client_loose.get(url, timeout=10.0)
            res["loose_status"] = r2.status_code
            res["loose_final_url"] = str(r2.url)
            res["length"] = len(r2.text)
            soup = BeautifulSoup(r2.text, "html.parser")
            res["title"] = soup.title.get_text(strip=True) if soup.title else ""
            txt_lower = r2.text.lower()
            has_content = (
                r2.status_code == 200
                and len(r2.text) > 800
                and ("scoring summary" in txt_lower or "penalty summary" in txt_lower or "box score" in txt_lower or "goals by period" in txt_lower)
                and "page not found" not in txt_lower
                and "404 - file or directory not found" not in txt_lower
            )
            res["has_boxscore_content"] = has_content
            res["loose_ok"] = has_content
        except Exception as e2:
            res["loose_error"] = f"{type(e2).__name__}: {str(e2)[:120]}"
        return res

async def main():
    limits = httpx.Limits(max_keepalive_connections=30, max_connections=50)
    sem = asyncio.Semaphore(30)
    report = {
        "schedule_2011_12_games": [],
        "all_schedule_seasons": {},
        "teamstat_2011_12_links": [],
        "csv_urls_summary": {},
        "broken_csv_urls": [],
        "url_checks": {},
    }

    async with httpx.AsyncClient(headers=HEADERS, limits=limits, follow_redirects=True, verify=True) as client_strict, \
               httpx.AsyncClient(headers=HEADERS, limits=limits, follow_redirects=True, verify=False) as client_loose:

        candidate_urls = set()

        # Read current CSV URLs
        with open("northeastern_game_results.csv", "r", encoding="utf-8") as f:
            csv_games = list(csv.DictReader(f))
        for g in csv_games:
            if g.get("boxscore_url"):
                candidate_urls.add(g["boxscore_url"])

        # Inspect schedule pages for 1999-2027, with detailed extraction for 2008-2014
        for year in range(1999, 2027):
            season_str = f"{year}-{str(year+1)[-2:]}"
            sched_url = f"https://nuhuskies.com/sports/mens-ice-hockey/schedule/{season_str}"
            legacy_url = f"https://static.gonu.com/custompages/mhockey/MHK{str(year)[-2:]}{str(year+1)[-2:]}/HTML/teamstat.htm"

            sched_links = []
            try:
                r = await client_loose.get(sched_url, timeout=10.0)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, "html.parser")
                    # Find game containers or links
                    if year in (2010, 2011, 2012):
                        games_detail = []
                        for item in soup.select(".sidearm-schedule-game"):
                            opp_el = item.select_one(".sidearm-schedule-game-opponent-name")
                            date_el = item.select_one(".sidearm-schedule-game-opponent-date")
                            opp_txt = opp_el.get_text(" ", strip=True) if opp_el else ""
                            date_txt = date_el.get_text(" ", strip=True) if date_el else ""
                            links = []
                            for a in item.find_all("a", href=True):
                                txt = a.get_text(" ", strip=True)
                                href = urllib.parse.urljoin(sched_url, a["href"])
                                links.append({"text": txt, "href": href, "raw_href": a["href"]})
                                if "box" in txt.lower() or "boxscore" in href.lower() or ".htm" in href.lower() or "stats" in href.lower():
                                    candidate_urls.add(href)
                            games_detail.append({
                                "date_text": date_txt,
                                "opponent": opp_txt,
                                "links": links,
                            })
                        if year == 2011:
                            report["schedule_2011_12_games"] = games_detail
                            all_a = []
                            for a in soup.find_all("a", href=True):
                                txt = a.get_text(" ", strip=True)
                                href = urllib.parse.urljoin(sched_url, a["href"])
                                if any(k in (txt + " " + href).lower() for k in ["box", "recap", "htm", "stats", "umass", "massachusetts"]):
                                    li = a.find_parent("li", class_=lambda c: c and "sidearm-schedule-game" in c) or a.find_parent("li") or a.parent
                                    parent_txt = li.get_text(" ", strip=True)[:250] if li else ""
                                    all_a.append({"text": txt, "href": href, "raw_href": a["href"], "context": parent_txt})
                                    candidate_urls.add(href)
                            report["schedule_2011_12_all_links"] = all_a
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        txt = a.get_text(strip=True)
                        full_u = urllib.parse.urljoin(sched_url, href)
                        if any(k in (txt + " " + href).lower() for k in ["boxscore", "box score", "/stats/", ".htm"]) and "roster" not in href.lower() and "cumulative" not in href.lower():
                            sched_links.append({"text": txt, "url": full_u})
                            candidate_urls.add(full_u)
            except Exception as e:
                sched_links.append({"error": str(e)})

            leg_links = []
            try:
                rl = await client_loose.get(legacy_url, timeout=10.0)
                if rl.status_code == 200:
                    soup = BeautifulSoup(rl.text, "html.parser")
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if href.lower().endswith(".htm") and not any(x in href.lower() for x in ["teamcume", "teamgbg", "confstat", "plystat", "teamstat"]):
                            full_u = urllib.parse.urljoin(legacy_url, href)
                            leg_links.append({"text": a.get_text(strip=True), "raw_href": href, "url": full_u})
                            candidate_urls.add(full_u)
            except Exception as e:
                pass

            if year == 2011:
                report["teamstat_2011_12_links"] = leg_links

            report["all_schedule_seasons"][season_str] = {
                "sched_link_count": len(sched_links),
                "legacy_link_count": len(leg_links),
                "sample_sched_links": sched_links[:10],
            }

        # Check all candidate URLs
        print(f"Testing {len(candidate_urls)} unique candidate URLs...")
        tasks = [check_url(client_strict, client_loose, sem, u) for u in sorted(candidate_urls)]
        results = await asyncio.gather(*tasks)
        url_map = {r["url"]: r for r in results}
        report["url_checks"] = url_map

        # Summarize CSV URLs
        strict_pass = 0
        loose_pass = 0
        broken = []
        for g in csv_games:
            u = g.get("boxscore_url", "")
            chk = url_map.get(u, {})
            if chk.get("strict_ok"):
                strict_pass += 1
            if chk.get("loose_ok"):
                loose_pass += 1
            if not chk.get("strict_ok") or not chk.get("loose_ok"):
                broken.append({
                    "date": g["date"],
                    "opponent": g["opponent"],
                    "url": u,
                    "check": chk,
                })
        report["csv_urls_summary"] = {
            "total_csv_games": len(csv_games),
            "strict_pass": strict_pass,
            "loose_pass": loose_pass,
            "broken_or_non_strict_count": len(broken),
        }
        report["broken_csv_urls"] = broken

    with open("docs/boxscore_audit.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print("Saved docs/boxscore_audit.json")

if __name__ == "__main__":
    asyncio.run(main())
