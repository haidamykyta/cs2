"""
Live HLTV scraping for deep match analysis.

Fetches:
  - Map pool stats (win%, times played, 90-day window) per team
  - Player roster stats (rating, KAST, K/D, ADR) per team
  - bo3.gg match preview (analyst win%, analysis text)

Reuses the Playwright browser from data_collector to avoid double init.
All requests are rate-limited via data_collector._get().
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from bs4 import BeautifulSoup

from data_collector import _get   # Playwright fetch + rate limiting
from config import CS2_MAPS

logger = logging.getLogger(__name__)

HLTV_BASE = "https://www.hltv.org"

# Common team name → bo3.gg slug overrides
_BO3_SLUG_MAP = {
    "nip": "ninjas-in-pyjamas",
    "ninjas in pyjamas": "ninjas-in-pyjamas",
    "team liquid": "liquid",
    "team vitality": "vitality",
    "g2 esports": "g2",
    "natus vincere": "natus-vincere",
    "navi": "natus-vincere",
    "faze clan": "faze",
    "team spirit": "team-spirit",
    "spirit": "team-spirit",
    "virtus.pro": "virtus-pro",
    "mousesports": "mouz",
    "9 pandas": "9pandas",
    "big": "big",
    "ence": "ence",
    "astralis": "astralis",
    "complexity": "complexity",
    "cloud9": "cloud9",
    "heroic": "heroic",
    "apeks": "apeks",
    "3dmax": "3dmax",
    "fnatic": "fnatic",
    "pain gaming": "pain",
    "pain": "pain",
    "imperial": "imperial",
}


# ── Parse helpers ──────────────────────────────────────────────────────────────

def _parse_pct(text: str) -> float:
    """'58.3%' → 0.583,  also handles '58.3' (already decimal-ish)."""
    text = text.strip().rstrip("%")
    try:
        v = float(text)
        return v / 100.0 if v > 1.0 else v
    except ValueError:
        return 0.0


def _parse_float(text: str) -> float:
    text = re.sub(r"[^\d.\-]", "", text.strip())
    try:
        return float(text)
    except ValueError:
        return 0.0


def _parse_int(text: str) -> int:
    text = re.sub(r"[^\d]", "", text.strip())
    try:
        return int(text)
    except ValueError:
        return 0


def _days_ago(days: int) -> str:
    return (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")


def _normalize_map(name: str) -> Optional[str]:
    name = name.strip()
    for m in CS2_MAPS:
        if m.lower() == name.lower():
            return m
    # partial match (e.g. "de_dust2" → "Dust2")
    for m in CS2_MAPS:
        if m.lower() in name.lower():
            return m
    return None


def _hltv_slug(team_name: str) -> str:
    """Derive HLTV URL slug from team name: 'Team Liquid' → 'liquid'."""
    name = team_name.lower().strip()
    # Strip common prefixes
    for prefix in ("team ", "clan "):
        if name.startswith(prefix):
            name = name[len(prefix):]
    name = re.sub(r"[^a-z0-9]+", "-", name).strip("-")
    return name


# ── Map pool scraping ──────────────────────────────────────────────────────────

async def scrape_map_pool(hltv_id: int, team_name: str, days: int = 90) -> list[dict]:
    """
    Scrape map pool stats for a team from HLTV stats page.
    Returns: [{map_name, win_pct, times_played}]
    URL: /stats/teams/maps/{hltv_id}/{slug}?startDate=YYYY-MM-DD
    """
    slug = _hltv_slug(team_name)
    start_date = _days_ago(days)
    url = f"{HLTV_BASE}/stats/teams/maps/{hltv_id}/{slug}?startDate={start_date}"

    html = await _get(url)
    if not html:
        logger.warning("scrape_map_pool: empty response for %s (id=%s)", team_name, hltv_id)
        return []

    soup = BeautifulSoup(html, "html.parser")

    # Check for Cloudflare / challenge page
    if "cf-browser-verification" in html or "Checking your browser" in html:
        logger.warning("scrape_map_pool: Cloudflare challenge for %s", team_name)
        return []

    results = []

    # HLTV stats/teams/maps table: Map | Wins | Draws | Losses | Win% | KD Ratio
    # Table class is typically "stats-table"
    table = soup.select_one("table.stats-table")
    if not table:
        # Fallback: first table on page
        table = soup.select_one("table")

    if not table:
        logger.debug("scrape_map_pool: no table found for %s", team_name)
        return []

    for row in table.select("tbody tr"):
        cells = row.select("td")
        if len(cells) < 4:
            continue
        try:
            map_name = _normalize_map(cells[0].text.strip())
            if not map_name:
                continue

            wins   = _parse_int(cells[1].text)
            draws  = _parse_int(cells[2].text)
            losses = _parse_int(cells[3].text)
            total  = wins + draws + losses

            if total == 0:
                continue

            win_pct = wins / total

            results.append({
                "map_name":    map_name,
                "win_pct":     round(win_pct, 3),
                "times_played": total,
            })
        except Exception as e:
            logger.debug("map pool row parse error: %s", e)

    logger.info("scrape_map_pool: %s → %d maps", team_name, len(results))
    return results


# ── Player stats scraping ──────────────────────────────────────────────────────

async def scrape_player_stats(hltv_id: int, team_name: str, days: int = 90) -> list[dict]:
    """
    Scrape player roster stats from HLTV stats page.
    Returns: [{name, rating, kast, kd, adr, maps_played}] sorted by rating desc.
    URL: /stats/teams/players/{hltv_id}/{slug}?startDate=YYYY-MM-DD
    """
    slug = _hltv_slug(team_name)
    start_date = _days_ago(days)
    url = f"{HLTV_BASE}/stats/teams/players/{hltv_id}/{slug}?startDate={start_date}"

    html = await _get(url)
    if not html:
        logger.warning("scrape_player_stats: empty response for %s", team_name)
        return []

    if "cf-browser-verification" in html or "Checking your browser" in html:
        logger.warning("scrape_player_stats: Cloudflare challenge for %s", team_name)
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []

    # HLTV player stats table columns (approximate):
    # Player | Maps | Rds | K-D Diff | K/D | Rating 2.0
    # Some pages also include KAST column
    table = soup.select_one("table.stats-table") or soup.select_one("table")
    if not table:
        logger.debug("scrape_player_stats: no table for %s", team_name)
        return []

    header_cells = [th.text.strip().lower() for th in table.select("thead th")]

    # Detect column positions from header
    col = {
        "player": 0,
        "maps":   1,
        "kd":     -1,
        "kast":   -1,
        "adr":    -1,
        "rating": -1,
    }
    for i, h in enumerate(header_cells):
        if "rating" in h:
            col["rating"] = i
        elif "k/d" in h or "kd" in h:
            col["kd"] = i
        elif "kast" in h:
            col["kast"] = i
        elif "adr" in h:
            col["adr"] = i
        elif "maps" in h:
            col["maps"] = i

    # Default positions if header detection fails
    if col["rating"] == -1:
        col["rating"] = len(header_cells) - 1   # last column usually
    if col["kd"] == -1:
        col["kd"] = 4

    for row in table.select("tbody tr"):
        cells = row.select("td")
        if len(cells) < 4:
            continue
        try:
            name_el = cells[col["player"]].select_one("a") or cells[col["player"]]
            name = name_el.text.strip()
            if not name:
                continue

            maps_played = _parse_int(cells[col["maps"]].text) if col["maps"] < len(cells) else 0
            rating = _parse_float(cells[col["rating"]].text) if col["rating"] < len(cells) else 1.0
            kd     = _parse_float(cells[col["kd"]].text)     if col["kd"]     < len(cells) else 1.0
            kast   = _parse_pct(cells[col["kast"]].text)     if col["kast"] != -1 and col["kast"] < len(cells) else 0.0
            adr    = _parse_float(cells[col["adr"]].text)    if col["adr"]  != -1 and col["adr"]  < len(cells) else 0.0

            if rating < 0.1 or rating > 3.0:   # sanity check
                rating = 1.0

            results.append({
                "name":        name,
                "rating":      round(rating, 2),
                "kast":        round(kast, 3),
                "kd":          round(kd, 2),
                "adr":         round(adr, 1),
                "maps_played": maps_played,
            })
        except Exception as e:
            logger.debug("player row parse error: %s", e)

    results.sort(key=lambda x: -x["rating"])
    logger.info("scrape_player_stats: %s → %d players", team_name, len(results))
    return results


# ── bo3.gg scraping ────────────────────────────────────────────────────────────

async def scrape_bo3gg(t1_name: str, t2_name: str,
                       match_date: Optional[datetime] = None) -> dict:
    """
    Scrape bo3.gg match preview for community analyst predictions.
    Returns: {t1_win_pct, t2_win_pct, analysis_text}
    Falls back gracefully if page not found or parsing fails.
    """
    if match_date is None:
        match_date = datetime.utcnow()

    slug = _build_bo3_slug(t1_name, t2_name, match_date)
    url = f"https://bo3.gg/ru/matches/{slug}"

    html = await _get(url)
    if not html:
        return {"t1_win_pct": 0.0, "t2_win_pct": 0.0, "analysis_text": "нет данных"}

    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True)

    # Check for 404 / not found
    if "404" in (soup.title.text if soup.title else "") or "не найден" in page_text.lower():
        return {"t1_win_pct": 0.0, "t2_win_pct": 0.0, "analysis_text": "матч не найден на bo3.gg"}

    t1_pct = 0.0
    t2_pct = 0.0

    # Try structured selectors first
    pct_els = soup.select(".match-winner__percent, .prediction__percent, [class*='percent']")
    if len(pct_els) >= 2:
        t1_pct = _parse_pct(pct_els[0].text)
        t2_pct = _parse_pct(pct_els[1].text)

    # Fallback: find all "XX%" patterns in the text near team names
    if t1_pct == 0.0 and t2_pct == 0.0:
        pcts = re.findall(r"(\d{1,3})%", page_text)
        # Filter out unlikely values (only 0-100)
        valid = [float(p) for p in pcts if 0 < float(p) < 100]
        if len(valid) >= 2:
            t1_pct = valid[0] / 100.0
            t2_pct = valid[1] / 100.0

    # Analysis text — grab from preview/prediction section
    analysis = ""
    for sel in (".match-preview__text", ".prediction__text", "article .text", ".match-analysis"):
        el = soup.select_one(sel)
        if el:
            analysis = el.get_text(" ", strip=True)[:600]
            break

    # Fallback: grab biggest text block
    if not analysis:
        paragraphs = soup.select("p")
        for p in paragraphs:
            txt = p.get_text(" ", strip=True)
            if len(txt) > 100:
                analysis = txt[:600]
                break

    return {
        "t1_win_pct":    round(t1_pct, 3),
        "t2_win_pct":    round(t2_pct, 3),
        "analysis_text": analysis or "нет данных",
    }


def _build_bo3_slug(t1_name: str, t2_name: str, match_date: datetime) -> str:
    """Build bo3.gg match slug like 'ninjas-in-pyjamas-vs-liquid-21-03-2026'."""
    def slugify(name: str) -> str:
        n = name.lower().strip()
        if n in _BO3_SLUG_MAP:
            return _BO3_SLUG_MAP[n]
        # Strip "team " prefix
        if n.startswith("team "):
            n = n[5:]
        n = re.sub(r"[^a-z0-9]+", "-", n).strip("-")
        return n

    date_str = match_date.strftime("%d-%m-%Y")
    return f"{slugify(t1_name)}-vs-{slugify(t2_name)}-{date_str}"
