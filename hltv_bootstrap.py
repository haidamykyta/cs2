"""
HLTV historical bootstrap using hltv-async-api.

Fetches match results from HLTV for a given period and saves to DB.
Use this to fill the gap between Kaggle dataset (ends Oct 2025) and now.

Install:  pip install hltv-async-api
Usage:
    python hltv_bootstrap.py               # last 6 months
    python hltv_bootstrap.py --months 3    # last 3 months
    python hltv_bootstrap.py --months 12   # full year

Note: HLTV rate-limits aggressively. Expect 2-4 hours for 6 months.
      Run overnight. Use --proxy if getting blocked.
"""

import asyncio
import argparse
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

import database as db
from config import DB_PATH

logger = logging.getLogger(__name__)

# Tier mapping from hltv-async-api tier values
HLTV_TIER_MAP = {
    "S": "S",
    "A": "A",
    "B": "B",
    "C": "C",
    "D": "D",
    1: "S", 2: "A", 3: "B", 4: "C", 5: "D",
}


async def bootstrap_hltv(months: int = 6, proxy_list: list = None,
                          tiers: list = None, min_delay: float = 3.0):
    """
    Fetch HLTV match history and insert into DB.

    Args:
        months: Number of months back to fetch.
        proxy_list: List of proxy strings (optional, helps with rate limiting).
        tiers: List of tier letters to filter by (e.g. ["S", "A"]). None = S+A+B.
        min_delay: Minimum delay between requests in seconds.
    """
    try:
        from hltv_async_api import Hltv
    except ImportError:
        logger.error("hltv-async-api not installed. Run: pip install hltv-async-api")
        return

    tiers = tiers or ["S", "A", "B"]
    end_date = datetime.now()
    start_date = end_date - timedelta(days=months * 30)

    logger.info(
        f"Bootstrapping HLTV: {start_date:%Y-%m-%d} → {end_date:%Y-%m-%d}, "
        f"tiers={tiers}, delay={min_delay}s"
    )

    db.init_db()

    kwargs = {"max_delay": min_delay}
    if proxy_list:
        # hltv-async-api proxy support (check library docs for exact param name)
        kwargs["proxy_list"] = proxy_list

    hltv = Hltv(**kwargs)

    imported = 0
    errors = 0
    page = 0
    team_cache: dict[int, int] = {}  # hltv_team_id → db_team_id

    def get_or_create_team(team_data: dict) -> Optional[int]:
        """Get or create team in DB from HLTV team dict."""
        if not team_data:
            return None
        hltv_id = team_data.get("id")
        if hltv_id in team_cache:
            return team_cache[hltv_id]

        name = team_data.get("name", "Unknown")
        ranking = team_data.get("ranking")
        country = team_data.get("country")

        if hltv_id:
            try:
                tid = db.upsert_team(
                    name=name,
                    hltv_id=int(hltv_id),
                    ranking=int(ranking) if ranking else None,
                    country=country,
                )
                team_cache[int(hltv_id)] = tid
                return tid
            except Exception as e:
                logger.warning(f"Team upsert failed for {name}: {e}")
                existing = db.get_team_by_name(name)
                if existing:
                    team_cache[int(hltv_id)] = existing["id"]
                    return existing["id"]
        return None

    try:
        # hltv-async-api get_results fetches paginated match results
        # The exact API may vary by library version — check README
        logger.info("Fetching results from HLTV (this will take a while)...")

        results = await hltv.get_results(
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
        )

        logger.info(f"Received {len(results)} raw results from HLTV API")

        for match_data in results:
            try:
                tier_raw = match_data.get("tier") or match_data.get("event_tier", "B")
                tier = HLTV_TIER_MAP.get(tier_raw, "B")
                if tiers and tier not in tiers:
                    continue

                t1_data = match_data.get("team1") or {}
                t2_data = match_data.get("team2") or {}

                t1_id = get_or_create_team(t1_data)
                t2_id = get_or_create_team(t2_data)
                if not t1_id or not t2_id:
                    continue

                # Date handling
                raw_date = match_data.get("date") or match_data.get("match_date")
                if raw_date is None:
                    continue
                if isinstance(raw_date, datetime):
                    date_str = raw_date.isoformat()
                else:
                    try:
                        from dateutil import parser as dp
                        date_str = dp.parse(str(raw_date)).isoformat()
                    except Exception:
                        date_str = str(raw_date)

                # Scores / winner
                t1_score = match_data.get("result1") or match_data.get("t1_score") or 0
                t2_score = match_data.get("result2") or match_data.get("t2_score") or 0
                winner_id = None
                try:
                    if int(t1_score) > int(t2_score):
                        winner_id = t1_id
                    elif int(t2_score) > int(t1_score):
                        winner_id = t2_id
                except (ValueError, TypeError):
                    pass

                # Format / event
                format_raw = match_data.get("format") or match_data.get("best_of", 3)
                try:
                    best_of = int(str(format_raw).replace("bo", "").replace("BO", "").strip())
                except (ValueError, AttributeError):
                    best_of = 3
                fmt = f"bo{best_of}"

                event_name = (
                    (match_data.get("event") or {}).get("name", "")
                    or match_data.get("event_name", "Unknown")
                )
                is_lan = bool(
                    (match_data.get("event") or {}).get("location") or
                    match_data.get("lan") or
                    match_data.get("is_lan")
                )

                hltv_match_id = match_data.get("id") or match_data.get("match_id")
                if not hltv_match_id:
                    hltv_match_id = -(abs(hash(f"{t1_id}{t2_id}{date_str}")) % 100_000_000)

                match_id = db.insert_match(
                    hltv_id=int(hltv_match_id),
                    team1_id=t1_id,
                    team2_id=t2_id,
                    date=date_str,
                    fmt=fmt,
                    event=event_name,
                    event_tier=tier,
                    is_lan=is_lan,
                    winner_id=winner_id,
                )
                if match_id is None:
                    continue  # duplicate

                # Map results (if provided in match_data)
                maps = match_data.get("maps") or []
                for order, map_data in enumerate(maps, 1):
                    map_name = map_data.get("name") or map_data.get("map_name", "")
                    if not map_name:
                        continue
                    m_t1s = map_data.get("t1_score", 0) or 0
                    m_t2s = map_data.get("t2_score", 0) or 0
                    m_winner = t1_id if int(m_t1s) > int(m_t2s) else t2_id
                    try:
                        db.insert_map_result(
                            match_id=match_id,
                            map_name=str(map_name).strip(),
                            map_order=order,
                            team1_score=int(m_t1s),
                            team2_score=int(m_t2s),
                            winner_id=m_winner,
                        )
                    except Exception:
                        pass

                imported += 1
                if imported % 100 == 0:
                    logger.info(f"  Imported {imported} matches so far...")

            except Exception as e:
                errors += 1
                if errors <= 10:
                    logger.warning(f"Match processing error: {e}")

    except Exception as e:
        logger.error(f"HLTV API error: {e}")
        logger.error("If you're being rate-limited, try adding proxies or increasing min_delay.")

    finally:
        try:
            await hltv.close()
        except Exception:
            pass

    # Summary
    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    conn.close()

    logger.info(f"Bootstrap complete: {imported} new matches imported, {errors} errors")
    logger.info(f"Total matches in DB: {total}")
    return {"imported": imported, "errors": errors, "total_in_db": total}


def main():
    parser = argparse.ArgumentParser(description="Bootstrap HLTV match history")
    parser.add_argument("--months", type=int, default=6, help="Months of history to fetch (default: 6)")
    parser.add_argument("--tier", nargs="+", default=None,
                        help="Tiers to fetch (e.g. --tier S A). Default: S A B")
    parser.add_argument("--delay", type=float, default=3.0,
                        help="Min delay between requests in seconds (default: 3.0)")
    parser.add_argument("--proxy", nargs="+", default=None,
                        help="Proxy list (optional)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    asyncio.run(bootstrap_hltv(
        months=args.months,
        proxy_list=args.proxy,
        tiers=args.tier,
        min_delay=args.delay,
    ))


if __name__ == "__main__":
    main()