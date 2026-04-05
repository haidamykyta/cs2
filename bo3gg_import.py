"""
bo3.gg → SQLite importer
Collects CS2 matches from bo3.gg API and saves them into the existing DB schema.

DB_PATH is taken from config.py, which reads the DB_PATH environment variable.
On Windows, set it in your .env file:
    DB_PATH=C:\Users\you\projects\cs2\data\cs2_matches.db

Usage:
    python bo3gg_import.py --months 6 --tiers s,a --delay 0.4
    python bo3gg_import.py --months 3 --tiers s     (quick test, ~600 matches)
    python bo3gg_import.py --months 6 --tiers b     (Tier B, ~1500 matches)
    python bo3gg_import.py --months 12 --tiers s,a  (full year Tier S+A)
"""

import asyncio
import aiohttp
import sqlite3
import json
import logging
import sys
import os
import argparse
from datetime import datetime, timedelta, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "bo3gg_import.log")),
    ]
)
logger = logging.getLogger(__name__)

BASE     = "https://api.bo3.gg/api/v1"
HEADERS  = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://bo3.gg/ru/",
    "Origin": "https://bo3.gg",
}
# DB_PATH comes from config.py → reads DB_PATH env var, defaults to "data/cs2_matches.db"
# Set on Windows via .env: DB_PATH=C:\path\to\your\data\cs2_matches.db
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DB_PATH

# Map tier names
TIER_MAP = {"s": "S", "a": "A", "b": "B", "c": "C"}
# CS2 map name normalizer
MAP_NAME_MAP = {
    "de_inferno": "Inferno", "de_mirage": "Mirage", "de_nuke": "Nuke",
    "de_ancient": "Ancient", "de_anubis": "Anubis", "de_dust2": "Dust2",
    "de_vertigo": "Vertigo", "de_train": "Train", "de_overpass": "Overpass",
    "de_cache": "Cache",
}

# ─── DB helpers ───────────────────────────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def upsert_team(conn, name: str, rank: int = None) -> int:
    """Insert or update team, return internal id."""
    existing = conn.execute("SELECT id FROM teams WHERE name=?", (name,)).fetchone()
    if existing:
        if rank:
            conn.execute("UPDATE teams SET ranking=?, updated_at=datetime('now') WHERE id=?",
                         (rank, existing['id']))
        return existing['id']
    conn.execute("INSERT INTO teams (name, ranking) VALUES (?,?)", (name, rank))
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

def match_exists(conn, bo3_id: str) -> bool:
    """Check by source field storing bo3.gg slug."""
    row = conn.execute("SELECT id FROM matches WHERE source=?", (f"bo3:{bo3_id}",)).fetchone()
    return row is not None

def insert_match(conn, data: dict) -> int | None:
    """Insert match, return internal id (or None if already exists)."""
    source_key = f"bo3:{data['slug']}"
    if match_exists(conn, data['slug']):
        return None
    try:
        conn.execute("""
            INSERT INTO matches
              (team1_id, team2_id, winner_id, date, format, event, event_tier,
               is_lan, source)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            data['team1_id'], data['team2_id'], data['winner_id'],
            data['date'], data['format'], data['tournament'],
            TIER_MAP.get(data['tier'], data['tier']),
            1 if data['is_lan'] else 0,
            source_key,
        ))
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    except sqlite3.IntegrityError:
        return None

def insert_map_result(conn, match_id: int, map_data: dict):
    try:
        conn.execute("""
            INSERT OR IGNORE INTO map_results
              (match_id, map_name, map_order, team1_score, team2_score, winner_id, overtime)
            VALUES (?,?,?,?,?,?,?)
        """, (
            match_id, map_data['map_name'], map_data['map_order'],
            map_data['team1_score'], map_data['team2_score'],
            map_data['winner_id'], map_data.get('overtime', 0),
        ))
        conn.commit()
    except Exception as e:
        logger.debug("map_result insert error: %s", e)

def upsert_player(conn, name: str, team_id: int,
                  rating3: float = None, kast: float = None,
                  adr: float = None, kd: float = None) -> int:
    row = conn.execute("SELECT id FROM players WHERE name=?", (name,)).fetchone()
    if row:
        conn.execute("""
            UPDATE players SET team_id=?, rating3=?, kast=?, kd=?, adr=?, updated_at=datetime('now')
            WHERE id=?
        """, (team_id, rating3, kast, kd, adr, row['id']))
        return row['id']
    conn.execute("""
        INSERT INTO players (name, team_id, rating3, kast, kd, adr, is_active)
        VALUES (?,?,?,?,?,?,1)
    """, (name, team_id, rating3, kast, kd, adr))
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

def insert_match_odds(conn, match_id: int, odds: dict):
    if not odds:
        return
    try:
        conn.execute("""
            INSERT OR REPLACE INTO match_odds
              (match_id, bookmaker, team1_odds, team2_odds,
               team1_prob_fair, team2_prob_fair, recorded_at)
            VALUES (?,?,?,?,datetime('now'),0)
        """, (match_id, 'bo3gg', odds.get('team1_odds'), odds.get('team2_odds')))
        conn.commit()
    except Exception as e:
        logger.debug("odds insert error: %s", e)

# ─── API client ───────────────────────────────────────────────────────────────

class Bo3Client:
    def __init__(self, delay: float = 0.4):
        self.delay = delay
        self.session = None
        self._req_count = 0

    async def start(self):
        self.session = aiohttp.ClientSession(headers=HEADERS)

    async def close(self):
        if self.session:
            await self.session.close()

    async def get(self, path: str, params: dict = None) -> dict | list | None:
        await asyncio.sleep(self.delay)
        self._req_count += 1
        url = f"{BASE}{path}"
        try:
            async with self.session.get(url, params=params,
                                        timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 200:
                    return await r.json()
                if r.status == 429:
                    logger.warning("Rate limited, sleeping 5s")
                    await asyncio.sleep(5)
                    return await self.get(path, params)
                return None
        except asyncio.TimeoutError:
            logger.warning("Timeout: %s", url)
            return None
        except Exception as e:
            logger.error("Request error %s: %s", url, e)
            return None

    async def get_matches_page(self, tier: str, offset: int, limit: int = 100,
                                months_back: int = 7) -> dict | None:
        return await self.get("/matches", {
            "filter[matches.status][eq]": "finished",
            "filter[matches.discipline_id][eq]": "1",
            "filter[matches.game_version][eq]": "2",
            "filter[matches.tier][eq]": tier,
            "sort": "-start_date",
            "page[limit]": limit,
            "page[offset]": offset,
        })

    async def get_match_detail(self, slug: str) -> dict | None:
        return await self.get(f"/matches/{slug}")

    async def get_player_stats(self, slug: str) -> list | None:
        return await self.get(f"/matches/{slug}/players_stats")

    async def get_games(self, match_id: int) -> list:
        data = await self.get("/games", {
            "filter[games.match_id][eq]": match_id,
            "page[limit]": "10",
            "sort": "number",
        })
        if data and data.get('results'):
            return [g for g in data['results'] if g.get('state') == 'done']
        return []

    async def get_game_stats(self, game_id: int) -> list | None:
        return await self.get(f"/games/{game_id}/players_stats")

# ─── Match processing ─────────────────────────────────────────────────────────

def bo3_rating_to_hltv(rating: float) -> float:
    """bo3.gg uses 0-10 scale. Average ~6.0 ≈ HLTV 1.0. Convert roughly."""
    if not rating:
        return 1.0
    return round(rating / 6.0, 3)

async def process_match(client: Bo3Client, conn: sqlite3.Connection,
                         match_summary: dict, fetch_detail: bool = True) -> bool:
    """
    Process one match: insert into DB.
    Returns True if inserted new, False if skipped.
    """
    slug = match_summary['slug']

    if match_exists(conn, slug):
        return False

    # Fetch full detail (has bet_updates = odds)
    if fetch_detail and match_summary.get('parsed_status') in ('done', 'partially_done'):
        detail = await client.get_match_detail(slug)
    else:
        detail = match_summary

    if not detail:
        return False

    t1_name = detail.get('team1', {}).get('name') if detail.get('team1') else None
    t2_name = detail.get('team2', {}).get('name') if detail.get('team2') else None
    winner  = detail.get('winner_team', {}).get('name') if detail.get('winner_team') else None

    if not t1_name or not t2_name:
        return False

    t1_rank = detail.get('team1', {}).get('rank') if detail.get('team1') else None
    t2_rank = detail.get('team2', {}).get('rank') if detail.get('team2') else None

    t1_id = upsert_team(conn, t1_name, t1_rank)
    t2_id = upsert_team(conn, t2_name, t2_rank)
    winner_id = t1_id if winner == t1_name else (t2_id if winner == t2_name else None)

    is_lan = False
    tournament_name = None
    if detail.get('tournament'):
        tournament_name = detail['tournament'].get('name')
        is_lan = detail['tournament'].get('event_type') == 'lan'

    match_data = {
        'slug': slug,
        'team1_id': t1_id,
        'team2_id': t2_id,
        'winner_id': winner_id,
        'date': detail['start_date'],
        'format': f"bo{detail['bo_type']}",
        'tournament': tournament_name,
        'tier': detail['tier'],
        'is_lan': is_lan,
    }
    match_id = insert_match(conn, match_data)
    if not match_id:
        return False

    # Odds
    if detail.get('bet_updates'):
        bu = detail['bet_updates']
        odds = {
            'team1_odds': bu['team_1'].get('coeff'),
            'team2_odds': bu['team_2'].get('coeff'),
        }
        insert_match_odds(conn, match_id, odds)

    # Per-map results via games endpoint
    if detail.get('parsed_status') in ('done', 'partially_done'):
        games = await client.get_games(detail['id'])
        for game in games:
            map_name_raw = game.get('map_name', '')
            map_name = MAP_NAME_MAP.get(map_name_raw, map_name_raw.replace('de_', '').capitalize())
            winner_clan = game.get('winner_clan_name', '')
            loser_clan  = game.get('loser_clan_name', '')
            w_score = game.get('winner_clan_score', 0) or 0
            l_score = game.get('loser_clan_score', 0) or 0

            if winner_clan == t1_name:
                t1s, t2s, map_winner_id = w_score, l_score, t1_id
            else:
                t1s, t2s, map_winner_id = l_score, w_score, t2_id

            overtime = 1 if (w_score + l_score) > 30 else 0

            insert_map_result(conn, match_id, {
                'map_name': map_name,
                'map_order': game.get('number', 1),
                'team1_score': t1s,
                'team2_score': t2s,
                'winner_id': map_winner_id,
                'overtime': overtime,
            })

        # Player stats (match-level aggregated)
        player_stats = await client.get_player_stats(slug)
        if player_stats:
            for p in player_stats:
                sp = p.get('steam_profile', {})
                player_obj = sp.get('player', {}) if sp else {}
                nickname = sp.get('nickname') or player_obj.get('nickname', 'unknown')

                clan = p.get('clan_name', '')
                team_id = t1_id if clan == t1_name else t2_id

                # Convert bo3.gg rating (0-10) to HLTV-like (0-2 range)
                rating3 = p.get('player_rating')
                hltv_rating = bo3_rating_to_hltv(rating3) if rating3 else None
                kast = p.get('kast')  # already 0-1 float
                kills = p.get('kills', 0) or 0
                deaths = p.get('death', 1) or 1
                kd = round(kills / deaths, 3) if deaths else 1.0
                adr = p.get('adr')

                upsert_player(conn, nickname, team_id,
                              rating3=hltv_rating, kast=kast, kd=kd, adr=adr)

    return True

# ─── Main pipeline ────────────────────────────────────────────────────────────

async def run_import(months: int, tiers: list[str], delay: float, max_per_tier: int):
    client = Bo3Client(delay=delay)
    await client.start()
    conn = get_conn()

    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)
    total_new = 0
    total_skipped = 0

    try:
        for tier in tiers:
            logger.info("=" * 60)
            logger.info("Processing Tier %s ...", tier.upper())
            offset = 0
            page_size = 100
            tier_new = 0
            stop = False

            while not stop and tier_new < max_per_tier:
                page = await client.get_matches_page(tier, offset, page_size)
                if not page or not page.get('results'):
                    break

                results = page['results']
                for m in results:
                    # Date check
                    raw_date = m.get('start_date', '')
                    try:
                        match_date = datetime.fromisoformat(raw_date.replace('Z', '+00:00'))
                        if match_date < cutoff:
                            logger.info("Tier %s: reached cutoff (%s), stopping", tier.upper(), raw_date[:10])
                            stop = True
                            break
                    except Exception:
                        pass

                    inserted = await process_match(client, conn, m, fetch_detail=True)
                    if inserted:
                        tier_new += 1
                        total_new += 1
                        if tier_new % 50 == 0:
                            logger.info("Tier %s: %d new matches (API calls: %d)",
                                        tier.upper(), tier_new, client._req_count)
                    else:
                        total_skipped += 1

                offset += page_size
                total = page['total']['count']
                logger.info("Tier %s offset=%d/%d | new=%d | API calls=%d",
                            tier.upper(), offset, total, tier_new, client._req_count)

                if offset >= total:
                    break

            logger.info("Tier %s done: %d new matches", tier.upper(), tier_new)

    finally:
        await client.close()
        conn.close()

    logger.info("=" * 60)
    logger.info("IMPORT COMPLETE: %d new, %d skipped, %d API calls",
                total_new, total_skipped, client._req_count)
    return total_new


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--months",  type=int,   default=6)
    parser.add_argument("--tiers",   type=str,   default="s,a")
    parser.add_argument("--delay",   type=float, default=0.4)
    parser.add_argument("--max",     type=int,   default=10000)
    args = parser.parse_args()

    tiers = [t.strip().lower() for t in args.tiers.split(",")]
    logger.info("Starting bo3.gg import: %d months, tiers=%s, delay=%.1fs",
                args.months, tiers, args.delay)

    total = asyncio.run(run_import(args.months, tiers, args.delay, args.max))
    print(f"\nDone. {total} new matches imported.")
