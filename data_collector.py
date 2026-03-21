"""
HLTV data collector for CS2 predictor.

Uses hltv-async-api as primary source.
Falls back to direct BeautifulSoup scraping if API fails.

Bootstrap: run collect_history(months=12) once to fill the DB.
Live updates: run collect_upcoming() + collect_recent_results() on schedule.
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext
from bs4 import BeautifulSoup

import database as db
from config import HLTV_DELAY_MS

logger = logging.getLogger(__name__)

HLTV_BASE = "https://www.hltv.org"
DELAY = HLTV_DELAY_MS / 1000.0   # seconds between requests

EVENT_TIER_MAP = {
    "s-tier": "S",
    "a-tier": "A",
    "b-tier": "B",
    "c-tier": "C",
    "d-tier": "D",
}

# Playwright browser instance (shared, fresh context per request)
_playwright = None
_browser: Optional[Browser] = None


async def _ensure_browser():
    global _playwright, _browser
    if _browser is None:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        logger.info("Playwright browser started")


async def _get(url: str) -> Optional[str]:
    """
    Fetch URL via Playwright with a fresh browser context per request.
    Fresh context = fresh cookies/fingerprint = bypasses Cloudflare per-session tracking.
    Rate-limited by DELAY.
    """
    await asyncio.sleep(DELAY)
    await _ensure_browser()
    ctx = None
    page = None
    try:
        ctx = await _browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0.0.0 Safari/537.36",
            locale="en-US",
            viewport={"width": 1280, "height": 800},
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        page = await ctx.new_page()
        # Remove navigator.webdriver property (bot detection evasion)
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        html = await page.content()
        return html
    except Exception as e:
        logger.error("Playwright error for %s: %s", url, e)
        return None
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass
        if ctx:
            try:
                await ctx.close()
            except Exception:
                pass


async def close_browser():
    global _browser, _playwright
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None


# ── Parsing helpers ──────────────────────────────────────────────────────────

def _parse_team_ranking(soup: BeautifulSoup):
    """Parse team ranking page → list of {name, hltv_id, ranking, country}"""
    teams = []
    for item in soup.select(".ranked-team"):
        try:
            # Rank: <span class="position wide-position">#1</span>
            rank_el = item.select_one(".position") or item.select_one(".wide-position")
            name_el = item.select_one(".teamLine .name")
            # Team link: first <a> with /team/ in href
            link_el = next(
                (a for a in item.select("a") if "/team/" in a.get("href", "")),
                None
            )
            if not (rank_el and name_el and link_el):
                continue
            rank_text = rank_el.text.strip().lstrip("#")
            if not rank_text.isdigit():
                continue
            hltv_id_m = re.search(r"/team/(\d+)/", link_el["href"])
            if not hltv_id_m:
                continue
            hltv_id = int(hltv_id_m.group(1))
            teams.append({
                "name": name_el.text.strip(),
                "hltv_id": hltv_id,
                "ranking": int(rank_text),
                "country": None,
            })
        except Exception as e:
            logger.debug("Skipping team parse: %s", e)
    return teams


def _parse_results_page(soup: BeautifulSoup):
    """
    Parse /results page → list of complete match dicts.
    Extracts winner, format, event directly — no individual page needed.
    """
    matches = []
    for row in soup.select(".result-con a.a-reset"):
        try:
            href = row["href"]
            m = re.search(r"/matches/(\d+)/", href)
            if not m:
                continue
            hltv_id = int(m.group(1))

            t1_el = row.select_one(".team1 .team")
            t2_el = row.select_one(".team2 .team")
            if not (t1_el and t2_el):
                continue

            t1_name = t1_el.text.strip()
            t2_name = t2_el.text.strip()

            # Scores: score-won and score-lost
            score_els = row.select(".result-score span")
            score1 = score2 = None
            if len(score_els) >= 2:
                try:
                    score1 = int(score_els[0].text.strip())
                    score2 = int(score_els[1].text.strip())
                except ValueError:
                    pass

            # Winner: team with .team-won class
            t1_won = bool(row.select_one(".team1 .team-won"))
            t2_won = bool(row.select_one(".team2 .team-won"))

            # Format: bo1/bo3 in .map-text
            fmt_el = row.select_one(".map-text")
            fmt = fmt_el.text.strip().lower() if fmt_el else "bo3"

            # Event name
            event_el = row.select_one(".event-name")
            event = event_el.text.strip() if event_el else "Unknown"

            # Star count → event tier (3 stars = major, 2 = A, 1 = B)
            stars = len(row.select(".star"))
            event_tier = {3: "S", 2: "A", 1: "B"}.get(stars, "C")

            matches.append({
                "hltv_id": hltv_id,
                "team1_name": t1_name,
                "team2_name": t2_name,
                "score1": score1,
                "score2": score2,
                "winner": "team1" if t1_won else ("team2" if t2_won else None),
                "format": fmt,
                "event": event,
                "event_tier": event_tier,
                "href": href,
            })
        except Exception as e:
            logger.debug("Skip result row: %s", e)
    return matches


def _parse_match_page(hltv_id: int, soup: BeautifulSoup):
    """Parse single match page → full match info + map results."""
    try:
        # Teams
        teams_el = soup.select(".teamsBox .team")
        if len(teams_el) < 2:
            return None
        t1_name = teams_el[0].select_one(".teamName")
        t2_name = teams_el[1].select_one(".teamName")
        t1_link = teams_el[0].select_one("a")
        t2_link = teams_el[1].select_one("a")
        if not (t1_name and t2_name and t1_link and t2_link):
            return None

        t1_name = t1_name.text.strip()
        t2_name = t2_name.text.strip()
        t1_id_m = re.search(r"/team/(\d+)/", t1_link["href"])
        t2_id_m = re.search(r"/team/(\d+)/", t2_link["href"])
        t1_hltv = int(t1_id_m.group(1)) if t1_id_m else None
        t2_hltv = int(t2_id_m.group(1)) if t2_id_m else None

        # Winner
        won_el = soup.select_one(".team1-gradient .won") or soup.select_one(".team2-gradient .won")
        winner_team = None
        if soup.select_one(".team1-gradient .won"):
            winner_team = "team1"
        elif soup.select_one(".team2-gradient .won"):
            winner_team = "team2"

        # Date
        date_el = soup.select_one(".time")
        match_date = None
        if date_el and date_el.get("data-unix"):
            ts = int(date_el["data-unix"]) / 1000
            match_date = datetime.utcfromtimestamp(ts).isoformat()

        # Event
        event_el = soup.select_one(".event a")
        event_name = event_el.text.strip() if event_el else "Unknown"

        # Event tier
        tier_el = soup.select_one(".event .gtSmartphone-only")
        tier_text = tier_el.text.strip().lower() if tier_el else ""
        event_tier = "C"
        for k, v in EVENT_TIER_MAP.items():
            if k in tier_text:
                event_tier = v
                break
        # Majors have special class
        if soup.select_one(".event .major"):
            event_tier = "S"

        # Format (bo1/bo3/bo5)
        fmt_el = soup.select_one(".preformatted-text")
        fmt = "bo3"
        if fmt_el:
            ft = fmt_el.text.lower()
            if "best of 1" in ft or "bo1" in ft:
                fmt = "bo1"
            elif "best of 5" in ft or "bo5" in ft:
                fmt = "bo5"

        # LAN flag
        is_lan = bool(soup.select_one(".event-world-icon") or
                      soup.select_one("[title*='LAN']"))

        # Map results
        maps = []
        for i, mapscore in enumerate(soup.select(".mapholder")):
            map_name_el = mapscore.select_one(".mapname")
            map_name = map_name_el.text.strip() if map_name_el else "Unknown"
            if map_name.lower() in ("tba", "knife"):
                continue
            scores = mapscore.select(".results-team-score")
            if len(scores) < 2:
                continue
            try:
                s1 = int(scores[0].text.strip())
                s2 = int(scores[1].text.strip())
            except ValueError:
                continue
            # Determine map winner
            map_winner = "team1" if s1 > s2 else ("team2" if s2 > s1 else None)
            maps.append({
                "map_name": map_name,
                "map_order": i + 1,
                "score1": s1,
                "score2": s2,
                "winner": map_winner,
            })

        return {
            "hltv_id": hltv_id,
            "team1": {"name": t1_name, "hltv_id": t1_hltv},
            "team2": {"name": t2_name, "hltv_id": t2_hltv},
            "winner_team": winner_team,
            "date": match_date,
            "event": event_name,
            "event_tier": event_tier,
            "format": fmt,
            "is_lan": is_lan,
            "maps": maps,
        }
    except Exception as e:
        logger.error("Match parse error hltv_id=%s: %s", hltv_id, e)
        return None


def _parse_upcoming_page(soup: BeautifulSoup):
    """Parse /matches page → list of upcoming match stubs."""
    matches = []
    for row in soup.select(".upcomingMatchesSection .upcomingMatch a.match"):
        try:
            href = row["href"]
            m = re.search(r"/matches/(\d+)/", href)
            if not m:
                continue
            hltv_id = int(m.group(1))
            t1 = row.select_one(".team1 .name")
            t2 = row.select_one(".team2 .name")
            date_el = row.select_one(".time")
            ts = int(date_el["data-unix"]) / 1000 if date_el and date_el.get("data-unix") else None
            match_date = datetime.utcfromtimestamp(ts).isoformat() if ts else None
            event_el = row.select_one(".matchEventName")
            matches.append({
                "hltv_id": hltv_id,
                "team1_name": t1.text.strip() if t1 else "TBA",
                "team2_name": t2.text.strip() if t2 else "TBA",
                "date": match_date,
                "event": event_el.text.strip() if event_el else "Unknown",
                "href": href,
            })
        except Exception as e:
            logger.debug("Skip upcoming row: %s", e)
    return matches


# ── DB helpers ───────────────────────────────────────────────────────────────

def _ensure_team(name: str, hltv_id: int, ranking: int = None) -> int:
    """Get or create team in DB, return internal id."""
    existing = db.get_team_by_name(name)
    if existing and existing.get("hltv_id") == hltv_id:
        return existing["id"]
    return db.upsert_team(name, hltv_id, ranking)


def _store_match(parsed: dict) -> Optional[int]:
    """Store parsed match dict into DB. Returns match internal id."""
    t1 = parsed["team1"]
    t2 = parsed["team2"]
    if not (t1["hltv_id"] and t2["hltv_id"]):
        return None

    t1_id = _ensure_team(t1["name"], t1["hltv_id"])
    t2_id = _ensure_team(t2["name"], t2["hltv_id"])

    winner_id = None
    if parsed["winner_team"] == "team1":
        winner_id = t1_id
    elif parsed["winner_team"] == "team2":
        winner_id = t2_id

    match_id = db.insert_match(
        hltv_id=parsed["hltv_id"],
        team1_id=t1_id,
        team2_id=t2_id,
        date=parsed["date"],
        fmt=parsed["format"],
        event=parsed["event"],
        event_tier=parsed["event_tier"],
        is_lan=parsed["is_lan"],
        winner_id=winner_id,
    )
    if not match_id:
        return None

    for mp in parsed.get("maps", []):
        mw_id = None
        if mp["winner"] == "team1":
            mw_id = t1_id
        elif mp["winner"] == "team2":
            mw_id = t2_id
        db.insert_map_result(
            match_id=match_id,
            map_name=mp["map_name"],
            map_order=mp["map_order"],
            team1_score=mp["score1"],
            team2_score=mp["score2"],
            winner_id=mw_id,
        )

    return match_id


# ── Public API ───────────────────────────────────────────────────────────────

async def collect_top_teams():
    """Fetch and store top 30 ranked teams."""
    html = await _get(f"{HLTV_BASE}/ranking/teams")
    if not html:
        logger.error("Failed to fetch team rankings")
        return
    soup = BeautifulSoup(html, "html.parser")
    teams = _parse_team_ranking(soup)
    for t in teams:
        db.upsert_team(t["name"], t["hltv_id"], t["ranking"], t.get("country"))
    logger.info("Stored %d ranked teams", len(teams))


async def collect_match_detail(hltv_id: int, href: str) -> bool:
    """Fetch and store a single match page. Returns True if stored."""
    url = f"{HLTV_BASE}{href}"
    html = await _get(url)
    if not html:
        return False
    soup = BeautifulSoup(html, "html.parser")
    parsed = _parse_match_page(hltv_id, soup)
    if not parsed:
        return False
    _store_match(parsed)
    return True


async def collect_recent_results(pages: int = 5, fetch_map_details: int = 50):
    """
    Scrape /results pages.
    - Match-level data (winner, scores) extracted from listing page (fast).
    - Map-level data fetched for first `fetch_map_details` matches only (individual pages).

    pages=48 → ~5000 matches in ~20 min (vs 6+ hours loading each page).
    """
    stored = 0
    map_detail_fetched = 0
    all_stubs = []

    for page in range(pages):
        offset = page * 100
        url = f"{HLTV_BASE}/results?offset={offset}"
        html = await _get(url)
        if not html:
            break
        soup = BeautifulSoup(html, "html.parser")
        stubs = _parse_results_page(soup)
        if not stubs:
            logger.warning("No results on page %d — stopping", page + 1)
            break

        # Store match-level data immediately (no individual page fetch)
        for stub in stubs:
            t1 = db.get_team_by_name(stub["team1_name"])
            t2 = db.get_team_by_name(stub["team2_name"])
            if not (t1 and t2):
                continue
            winner_id = None
            if stub["winner"] == "team1":
                winner_id = t1["id"]
            elif stub["winner"] == "team2":
                winner_id = t2["id"]
            mid = db.insert_match(
                hltv_id=stub["hltv_id"],
                team1_id=t1["id"],
                team2_id=t2["id"],
                date=None,   # will be filled by individual page fetch
                fmt=stub["format"],
                event=stub["event"],
                event_tier=stub["event_tier"],
                is_lan=False,
                winner_id=winner_id,
            )
            if mid:
                stored += 1
                all_stubs.append(stub)

        logger.info("Results page %d/%d — %d matches stored", page + 1, pages, stored)

    # Fetch map details for the most recent N matches (for better predictions)
    for stub in all_stubs[:fetch_map_details]:
        try:
            await collect_match_detail(stub["hltv_id"], stub["href"])
            map_detail_fetched += 1
        except Exception as e:
            logger.debug("Map detail for %s failed: %s", stub["hltv_id"], e)

    logger.info("collect_recent_results done: %d matches, %d with map details",
                stored, map_detail_fetched)
    return stored


async def collect_upcoming():
    """Fetch upcoming matches and store them (without winner)."""
    html = await _get(f"{HLTV_BASE}/matches")
    if not html:
        return
    soup = BeautifulSoup(html, "html.parser")
    stubs = _parse_upcoming_page(soup)
    for stub in stubs:
        t1_name, t2_name = stub["team1_name"], stub["team2_name"]
        if "TBA" in (t1_name, t2_name):
            continue
        t1 = db.get_team_by_name(t1_name)
        t2 = db.get_team_by_name(t2_name)
        if not (t1 and t2):
            continue
        db.insert_match(
            hltv_id=stub["hltv_id"],
            team1_id=t1["id"],
            team2_id=t2["id"],
            date=stub["date"],
            fmt="bo3",
            event=stub["event"],
            event_tier="A",
            is_lan=False,
            winner_id=None,
        )
    logger.info("Upcoming: stored %d match stubs", len(stubs))


async def bootstrap(months: int = 12):
    """
    Full bootstrap: collect team rankings + last N months of results.
    Run once. Takes 1-2 hours due to rate limiting.
    """
    db.init_db()
    logger.info("Bootstrap started — collecting %d months of history", months)
    try:
        await collect_top_teams()
        # pages ≈ months * 4 (roughly 80 matches/month at 20/page)
        pages = months * 4
        await collect_recent_results(pages=pages)
    finally:
        await close_browser()
    logger.info("Bootstrap complete.")


async def update_live():
    """
    Incremental update: fetch upcoming matches + last 2 pages of results.
    Run every 30 minutes via scheduler.
    """
    try:
        await collect_upcoming()
        await collect_recent_results(pages=2)
    finally:
        await close_browser()
    logger.info("Live update complete.")


# ── CLI entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    mode = sys.argv[1] if len(sys.argv) > 1 else "update"
    if mode == "bootstrap":
        months = int(sys.argv[2]) if len(sys.argv) > 2 else 12
        asyncio.run(bootstrap(months))
    else:
        asyncio.run(update_live())
