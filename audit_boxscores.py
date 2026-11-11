import asyncio
import json
import urllib.parse
import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

async def main():
    report = {}
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, verify=False, timeout=15.0) as client:
        # 1. Inspect MHK1112 teamstat.htm completely
        r_ts = await client.get("https://static.gonu.com/custompages/mhockey/MHK1112/HTML/teamstat.htm")
        soup_ts = BeautifulSoup(r_ts.text, "html.parser")
        ts_links = []
        for a in soup_ts.find_all("a", href=True):
            parent_tr = a.find_parent("tr")
            row_txt = parent_tr.get_text(" | ", strip=True) if parent_tr else a.parent.get_text(" | ", strip=True)
            ts_links.append({"text": a.get_text(strip=True), "href": a["href"], "row": row_txt[:200]})
        report["mhk1112_teamstat_all_a"] = ts_links

        # Also dump all rows of teamstat.htm table that look like game results
        ts_rows = []
        for tr in soup_ts.find_all("tr"):
            txt = tr.get_text(" | ", strip=True)
            if any(m in txt for m in ["Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "10/", "11/", "12/", "1/", "2/", "3/"]):
                hrefs = [a["href"] for a in tr.find_all("a", href=True)]
                ts_rows.append({"text": txt[:200], "hrefs": hrefs})
        report["mhk1112_teamstat_game_rows"] = ts_rows

        # 2. Inspect 2011-12 schedule page on nuhuskies.com and every Box Score / Box score link on it
        r_sched = await client.get("https://nuhuskies.com/sports/mens-ice-hockey/schedule/2011-12")
        soup_sched = BeautifulSoup(r_sched.text, "html.parser")
        sched_box_urls = []
        seen_u = set()
        for a in soup_sched.find_all("a", href=True):
            txt = a.get_text(" ", strip=True)
            href = urllib.parse.urljoin("https://nuhuskies.com/sports/mens-ice-hockey/schedule/2011-12", a["href"])
            if "box" in txt.lower() or "boxscore" in href.lower():
                if (txt, href) not in seen_u:
                    seen_u.add((txt, href))
                    sched_box_urls.append({"text": txt, "url": href})

        # Fetch all 2011-12 schedule box score URLs and inspect their content!
        box_details = []
        for item in sched_box_urls:
            u = item["url"]
            try:
                rb = await client.get(u)
                sb = BeautifulSoup(rb.text, "html.parser")
                title = sb.title.get_text(strip=True) if sb.title else ""
                tables_info = []
                for t in sb.find_all("table"):
                    rows = t.find_all("tr")
                    first_rows = [[c.get_text(strip=True) for c in r.find_all(["td", "th"])][:8] for r in rows[:3]]
                    tables_info.append({"row_count": len(rows), "sample": first_rows})
                # Check if there are any links or iframes to static.gonu.com or custompages or .htm
                inner_links = []
                for a in sb.find_all(["a", "iframe"], href=True):
                    if any(k in a["href"].lower() for k in ["gonu", "custompages", ".htm", "boxscore", "mhk"]):
                        inner_links.append(a["href"])
                for ifr in sb.find_all("iframe", src=True):
                    inner_links.append(ifr["src"])
                body_text = sb.get_text(" ", strip=True)
                has_scoring = "scoring summary" in body_text.lower() or "goals by period" in body_text.lower()
                box_details.append({
                    "link_text": item["text"],
                    "url": u,
                    "final_url": str(rb.url),
                    "status": rb.status_code,
                    "title": title,
                    "table_count": len(tables_info),
                    "has_scoring_summary": has_scoring,
                    "inner_links": inner_links[:10],
                    "tables_sample": tables_info[:6],
                })
            except Exception as e:
                box_details.append({"link_text": item["text"], "url": u, "error": str(e)})
        report["sched_2011_12_box_details"] = box_details

        # 3. Inspect one 2009-10 game (nu-cc1.htm) and 2004-05 (game01.htm) and 2014-15 (5064) to see why skaters/goalies were 0
        sample_missing = [
            "https://static.gonu.com/custompages/mhockey/MHK0910/HTML/nu-cc1.htm",
            "https://static.gonu.com/custompages/mhockey/MHK0405/HTML/game01.htm",
            "https://nuhuskies.com/sports/mens-ice-hockey/stats/2014-15/maine/boxscore/5064",
        ]
        missing_debug = {}
        for mu in sample_missing:
            rm = await client.get(mu)
            sm = BeautifulSoup(rm.text, "html.parser")
            tbls = []
            for t in sm.find_all("table"):
                rows = t.find_all("tr")
                first_rows = [[c.get_text(strip=True) for c in r.find_all(["td", "th"])][:10] for r in rows[:4]]
                tbls.append({"row_count": len(rows), "first_rows": first_rows})
            missing_debug[mu] = {"title": sm.title.get_text(strip=True) if sm.title else "", "tables": tbls}
        report["missing_skaters_debug"] = missing_debug

    with open("docs/boxscore_audit.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print("Saved detailed 2011-12 & missing games audit to docs/boxscore_audit.json")

if __name__ == "__main__":
    asyncio.run(main())
