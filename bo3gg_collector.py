"""
bo3.gg API Collector for CS2 Betting Bot
=========================================
Public API at api.bo3.gg — no auth required.

Endpoints discovered:
  GET /api/v1/matches                           — match list (filter, sort, paginate)
  GET /api/v1/matches/{slug}                    — match detail + bet_updates (odds)
  GET /api/v1/matches/{slug}/players_stats      — all-match player stats (10 players)
  GET /api/v1/matches/{slug}/clutches_stats     — clutch moments
  GET /api/v1/games?filter[games.match_id][eq]= — per-map game list for a match
  GET /api/v1/games/{game_id}/players_stats     — per-map player stats
  GET /api/v1/games/{game_id}/short_players_stats  — lighter per-map stats
  GET /api/v1/games/{game_id}/kills_matrix      — kill matrix (who killed whom)

Data available per match:
  - result, score, format, tier, stars, start_date, LAN/Online
  - bet_updates: team1_odds, team2_odds + 14 markets (handicaps, totals, scores)
  - per player (match-level): kills, deaths, assists, ADR, KAST, rating (bo3.gg scale),
    headshots, first_kills, first_deaths, trade_kills, trade_deaths, multikills,
    clutches, utility_value, money_spent
  - per player (per-map): same fields but isolated to one map

CS2 data: 68,639 total matches (Tier S: 3503, Tier A: 2630, Tier B: 16,513)
No rate limit observed (5+ req/sec without issues). Add 0.5s delay to be safe.

Usage:
    python bo3gg_collector.py --months 6 --tiers s,a --output data/bo3gg_matches.json
    python bo3gg_collector.py --slug vitality-vs-natus-vincere-29-03-2026
"""

import asyncio
import aiohttp
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

BASE = "https://api.bo3.gg/api/v1"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://bo3.gg/ru/",
    "Origin": "https://bo3.gg",
}
DELAY = 0.5  # seconds between requests


class Bo3GGCollector:
    def __init__(self, delay: float = DELAY):
        self.delay = delay
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers=HEADERS)
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    async def _get(self, path: str, params: dict = None) -> Optional[dict | list]:
        await asyncio.sleep(self.delay)
        url = f"{BASE}{path}"
        try:
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    return await r.json()
                logger.warning("HTTP %d: %s", r.status, url)
                return None
        except Exception as e:
            logger.error("Request failed %s: %s", url, e)
            return None

    # ── Match List ────────────────────────────────────────────────────────────

    async def get_finished_matches(
        self,
        tier: str = None,           # 's', 'a', 'b', 'c' or None for all
        months_back: int = 6,
        limit: int = 100,
        offset: int = 0,
        cs2_only: bool = True,
    ) -> Optional[dict]:
        """
        Get page of finished matches.
        Returns {total: {count, pages}, results: [...], links: {next, ...}}
        """
        start_date = (datetime.utcnow() - timedelta(days=months_back * 30)).strftime("%Y-%m-%d")

        params = {
            "filter[matches.status][eq]": "finished",
            "filter[matches.discipline_id][eq]": "1",
            "sort": "-start_date",
            "page[limit]": limit,
            "page[offset]": offset,
        }
        if cs2_only:
            params["filter[matches.game_version][eq]"] = "2"
        if tier:
            params["filter[matches.tier][eq]"] = tier.lower()
        # Note: bo3.gg API doesn't support date filter directly in matches endpoint,
        # but we can filter client-side after fetching (matches are sorted by -start_date
        # so we stop when we hit dates older than start_date)

        return await self._get("/matches", params)

    async def collect_history(
        self,
        months: int = 6,
        tiers: list = None,         # ['s', 'a'] — None = all tiers
        cs2_only: bool = True,
        max_matches: int = 5000,
    ) -> list[dict]:
        """
        Collect all finished matches for past N months.
        Returns list of match dicts (match-level only, no player stats).
        
        Call get_match_full() for each match to get player stats.
        """
        if tiers is None:
            tiers = ['s', 'a', 'b']

        cutoff = datetime.utcnow() - timedelta(days=months * 30)
        all_matches = []

        for tier in tiers:
            logger.info("Collecting Tier %s matches...", tier.upper())
            offset = 0
            page_size = 100

            while len(all_matches) < max_matches:
                data = await self.get_finished_matches(
                    tier=tier,
                    months_back=months + 1,  # slight buffer
                    limit=page_size,
                    offset=offset,
                    cs2_only=cs2_only,
                )
                if not data or not data.get('results'):
                    break

                results = data['results']
                added = 0
                for m in results:
                    match_date = datetime.fromisoformat(m['start_date'].replace('Z', '+00:00')).replace(tzinfo=None)
                    if match_date < cutoff:
                        logger.info("Reached cutoff date for Tier %s at offset %d", tier.upper(), offset)
                        results = []  # signal to stop
                        break
                    all_matches.append(m)
                    added += 1

                logger.info("Tier %s page offset=%d: +%d matches (total: %d)", tier.upper(), offset, added, len(all_matches))

                if not results or offset + page_size >= data['total']['count']:
                    break
                offset += page_size

        logger.info("History collection done: %d matches", len(all_matches))
        return all_matches

    # ── Match Detail ──────────────────────────────────────────────────────────

    async def get_match_detail(self, slug: str) -> Optional[dict]:
        """
        Full match info: teams, score, format, tier, bet_updates (odds + 14 markets).
        
        Key fields in bet_updates:
          team_1.coeff, team_2.coeff      — moneyline odds
          additional_markets[]:
            total_maps_over_2_5           — over 2.5 maps
            total_maps_under_2_5          — under 2.5 maps
            team_1_handicap_under_1_5     — team1 -1.5 maps
            team_1_handicap_over_1_5      — team1 +1.5 maps
            score_2_0, score_2_1, etc.    — exact score
        """
        return await self._get(f"/matches/{slug}")

    async def get_match_player_stats(self, slug: str) -> Optional[list]:
        """
        All-match player stats (aggregated across all maps).
        Returns list of 10 player objects (5 per team).
        
        Fields per player:
          steam_profile.player.nickname   — player name
          clan_name                       — team clan name
          kills, death, assists           — basic stats
          headshots, first_kills, first_death
          trade_kills, trade_death
          kast                            — 0-1 float (e.g. 0.769 = 76.9%)
          player_rating                   — bo3.gg rating (0-10 scale, ~6=avg, 7+=good)
          adr                             — avg damage per round
          multikills: {2, 3, 4, 5}        — count of multi-kill rounds
          clutches                        — total clutches won
          utility_value, money_spent      — economy
          team_clan.team.rank             — HLTV rank embedded
        """
        return await self._get(f"/matches/{slug}/players_stats")

    async def get_match_clutches(self, slug: str) -> Optional[list]:
        """Clutch stats per player (match-level)."""
        return await self._get(f"/matches/{slug}/clutches_stats")

    # ── Per-Map (Game) Stats ──────────────────────────────────────────────────

    async def get_match_games(self, match_id: int) -> Optional[list]:
        """
        Get list of maps (games) played in a match.
        Returns list of game objects with:
          id             — game_id (use for per-map player stats)
          map_name       — 'de_inferno', 'de_mirage', etc.
          number         — map order (1, 2, 3)
          state          — 'done', 'not_played', 'waiting'
          winner_clan_name, loser_clan_name
          winner_clan_score, loser_clan_score  — rounds (e.g. 13-7)
          rounds_count   — total rounds played
        """
        data = await self._get("/games", {
            "filter[games.match_id][eq]": match_id,
            "page[limit]": "10",
            "sort": "number",
        })
        if data and data.get('results'):
            return [g for g in data['results'] if g['state'] == 'done']
        return []

    async def get_game_player_stats(self, game_id: int) -> Optional[list]:
        """
        Per-map player stats (single map).
        Same fields as get_match_player_stats but for one map only.
        Also includes cumulative_round_damages (dict per round).
        """
        return await self._get(f"/games/{game_id}/players_stats")

    async def get_game_kills_matrix(self, game_id: int) -> Optional[list]:
        """
        Kill matrix — who killed whom. 2 team objects each with list of players.
        Useful for calculating opening duel win rate per map.
        """
        return await self._get(f"/games/{game_id}/kills_matrix")

    # ── Full Match Pipeline ───────────────────────────────────────────────────

    async def get_match_full(self, slug: str) -> Optional[dict]:
        """
        Get EVERYTHING for one match:
          - match meta (teams, score, format, tier, LAN/Online)
          - odds (moneyline + markets from bet_updates)
          - match-level player stats (all maps aggregated)
          - per-map breakdown (map name, score, player stats per map)
        
        Returns structured dict ready for DB insertion.
        """
        match = await self.get_match_detail(slug)
        if not match:
            return None

        # Skip matches without full stats
        if match.get('parsed_status') not in ('done', 'partially_done'):
            return {'_meta': 'no_stats', 'slug': slug, 'match': match}

        match_id = match['id']

        # Player stats (match-level)
        player_stats = await self.get_match_player_stats(slug)

        # Per-map breakdown
        games = await self.get_match_games(match_id)
        map_stats = []
        for game in games:
            game_stats = await self.get_game_player_stats(game['id'])
            map_stats.append({
                'game_id': game['id'],
                'map_name': game['map_name'],
                'map_number': game['number'],
                'winner_clan': game['winner_clan_name'],
                'loser_clan': game['loser_clan_name'],
                'winner_score': game['winner_clan_score'],
                'loser_score': game['loser_clan_score'],
                'rounds_count': game['rounds_count'],
                'player_stats': game_stats or [],
            })

        # Extract odds
        odds = None
        if match.get('bet_updates'):
            bu = match['bet_updates']
            odds = {
                'team1_name': bu['team_1']['name'],
                'team2_name': bu['team_2']['name'],
                'team1_odds': bu['team_1']['coeff'],
                'team2_odds': bu['team_2']['coeff'],
                'team1_win_prob_implied': round(1 / bu['team_1']['coeff'], 4) if bu['team_1']['coeff'] > 1 else None,
                'team2_win_prob_implied': round(1 / bu['team_2']['coeff'], 4) if bu['team_2']['coeff'] > 1 else None,
                'markets': {m['bet_type']: m['coeff'] for m in bu.get('additional_markets', [])},
            }

        return {
            'slug': slug,
            'match_id': match_id,
            'date': match['start_date'],
            'tournament': match.get('tournament', {}).get('name') if match.get('tournament') else None,
            'tier': match['tier'],
            'stars': match['stars'],
            'format': f"bo{match['bo_type']}",
            'is_lan': match.get('tournament', {}).get('event_type') == 'lan' if match.get('tournament') else False,
            'team1_name': match['team1']['name'],
            'team2_name': match['team2']['name'],
            'team1_rank': match['team1'].get('rank'),
            'team2_rank': match['team2'].get('rank'),
            'team1_score': match['team1_score'],
            'team2_score': match['team2_score'],
            'winner': match['winner_team']['name'] if match.get('winner_team') else None,
            'parsed_status': match['parsed_status'],
            'odds': odds,
            'player_stats': player_stats or [],   # 10 players, all-match
            'maps': map_stats,                    # per-map breakdown
        }


# ── CLI / Quick Test ──────────────────────────────────────────────────────────

async def main():
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    async with Bo3GGCollector(delay=0.3) as collector:
        if len(sys.argv) > 1 and sys.argv[1] == '--slug':
            slug = sys.argv[2]
            print(f"Fetching: {slug}")
            result = await collector.get_match_full(slug)
            print(json.dumps(result, indent=2, default=str)[:3000])

        elif len(sys.argv) > 1 and sys.argv[1] == '--bootstrap':
            months = int(sys.argv[2]) if len(sys.argv) > 2 else 6
            tiers = sys.argv[3].split(',') if len(sys.argv) > 3 else ['s', 'a']
            print(f"Bootstrap: {months} months, tiers {tiers}")
            matches = await collector.collect_history(months=months, tiers=tiers)
            with open('data/bo3gg_matches_list.json', 'w') as f:
                json.dump(matches, f, default=str)
            print(f"Saved {len(matches)} matches to data/bo3gg_matches_list.json")

        else:
            # Quick test
            print("=== Quick test: Tier S matches ===")
            data = await collector.get_finished_matches(tier='s', months_back=1, limit=5)
            print(f"Total Tier S: {data['total']['count']}")
            for m in data['results']:
                print(f"  {m['start_date'][:10]} | {m['slug']} | stars={m['stars']} | parsed={m['parsed_status']}")

            print("\n=== Full match with player stats ===")
            slug = data['results'][0]['slug']
            full = await collector.get_match_full(slug)
            if full:
                print(f"Match: {full['team1_name']} vs {full['team2_name']}")
                print(f"Score: {full['team1_score']}-{full['team2_score']} | Tier: {full['tier']} | Stars: {full['stars']}")
                if full['odds']:
                    print(f"Odds: {full['odds']['team1_name']} @ {full['odds']['team1_odds']} | {full['odds']['team2_name']} @ {full['odds']['team2_odds']}")
                print(f"Maps played: {len(full['maps'])}")
                for m in full['maps']:
                    print(f"  Map {m['map_number']}: {m['map_name']} | {m['winner_clan']} {m['winner_score']}-{m['loser_score']} {m['loser_clan']}")
                print(f"Player stats (match-level): {len(full['player_stats'])} players")
                if full['player_stats']:
                    p = full['player_stats'][0]
                    name = p.get('steam_profile', {}).get('nickname', 'unknown')
                    print(f"  Top player: {name} | kills={p['kills']} adr={p['adr']:.1f} rating={p['player_rating']:.2f} kast={p['kast']:.1%}")


if __name__ == "__main__":
    asyncio.run(main())
