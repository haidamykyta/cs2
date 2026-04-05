"""
Kaggle CS2 HLTV dataset importer.

Dataset: griffindesroches/cs2-hltv-professional-match-statistics-dataset
Source:  https://www.kaggle.com/datasets/griffindesroches/cs2-hltv-professional-match-statistics-dataset
Matches: ~7,033 | Period: May 2024 - Oct 2025 | Columns: 116

Usage:
    python kaggle_importer.py cs2_hltv_matches.csv
    python kaggle_importer.py cs2_hltv_matches.csv --dry-run   # just show column map
    python kaggle_importer.py cs2_hltv_matches.csv --tier A S  # only S/A tier
"""

import sys
import argparse
import logging
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd

import database as db
from config import DB_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Tier mapping from HLTV tier names ──────────────────────────────────────────
TIER_MAP = {
    "s-tier": "S", "s tier": "S", "major": "S",
    "a-tier": "A", "a tier": "A",
    "b-tier": "B", "b tier": "B",
    "c-tier": "C", "c tier": "C",
    "d-tier": "D", "d tier": "D",
    "": "B",  # default
}

# ── Known column aliases from the griffindesroches dataset ─────────────────────
# Map our internal name → list of possible Kaggle column names (first match wins)
COLUMN_ALIASES = {
    "date":       ["date", "match_date", "Date"],
    "team1":      ["team1", "t1_team", "team_1", "Team1"],
    "team2":      ["team2", "t2_team", "team_2", "Team2"],
    "t1_score":   ["t1_map_score", "t1_score", "score1", "result1", "t1_maps_won"],
    "t2_score":   ["t2_map_score", "t2_score", "score2", "result2", "t2_maps_won"],
    "map":        ["map", "map_name", "Map"],
    "event":      ["event", "event_name", "tournament", "Event"],
    "tier":       ["tier", "event_tier", "Tier"],
    "best_of":    ["best_of", "format", "bo", "series_type"],
    "is_lan":     ["lan", "is_lan", "LAN"],
    "rank1":      ["rank1", "t1_rank", "ranking1", "team1_rank"],
    "rank2":      ["rank2", "t2_rank", "ranking2", "team2_rank"],
    "hltv_id":    ["match_id", "hltv_id", "match_hltv_id"],
    # Map-level detail (may be in separate rows per map)
    "t1_ct_score": ["t1_ct_score", "t1_ct"],
    "t2_ct_score": ["t2_ct_score", "t2_ct"],
    "t1_t_score":  ["t1_t_score", "t1_t"],
    "t2_t_score":  ["t2_t_score", "t2_t"],
}


def resolve_col(df: pd.DataFrame, key: str) -> Optional[str]:
    """Return the first matching column name in df, or None."""
    for alias in COLUMN_ALIASES.get(key, []):
        if alias in df.columns:
            return alias
    return None


def detect_column_map(df: pd.DataFrame) -> dict:
    """Build a mapping of internal key → actual column name (or None)."""
    mapping = {}
    for key in COLUMN_ALIASES:
        mapping[key] = resolve_col(df, key)
    return mapping


def get(row, col: Optional[str], default=None):
    """Safely get a value from a row dict."""
    if col is None:
        return default
    val = row.get(col, default)
    if pd.isna(val) if val is not None else False:
        return default
    return val


def parse_tier(raw) -> str:
    if raw is None:
        return "B"
    return TIER_MAP.get(str(raw).lower().strip(), "B")


def parse_best_of(raw) -> int:
    if raw is None:
        return 3
    try:
        val = str(raw).lower().replace("bo", "").replace("best of", "").strip()
        return int(val)
    except (ValueError, AttributeError):
        return 3


def parse_bool(raw, default: bool = False) -> bool:
    if raw is None:
        return default
    return str(raw).lower() in ("1", "true", "yes", "lan")


def infer_winner(team1_id: int, team2_id: int, t1_score, t2_score) -> Optional[int]:
    """Determine winner from scores."""
    try:
        s1, s2 = int(t1_score), int(t2_score)
    except (TypeError, ValueError):
        return None
    if s1 > s2:
        return team1_id
    if s2 > s1:
        return team2_id
    return None


def import_csv(csv_path: str, tiers: list = None, dry_run: bool = False) -> dict:
    """
    Import Kaggle CS2 dataset into the SQLite database.

    Args:
        csv_path: Path to the downloaded CSV file.
        tiers: Filter to specific tiers (e.g. ["S", "A"]). None = all.
        dry_run: If True, just print column mapping and exit.

    Returns:
        Summary dict with counts.
    """
    path = Path(csv_path)
    if not path.exists():
        logger.error(f"File not found: {csv_path}")
        sys.exit(1)

    logger.info(f"Reading {csv_path} ...")
    df = pd.read_csv(csv_path, low_memory=False)
    logger.info(f"Loaded {len(df):,} rows, {len(df.columns)} columns")

    col_map = detect_column_map(df)

    # Print column map
    print("\n=== COLUMN MAPPING ===")
    for key, col in col_map.items():
        status = f"✓ {col}" if col else "✗ NOT FOUND"
        print(f"  {key:<18} {status}")
    print()

    if dry_run:
        print("Dry-run mode. Columns detected above. Run without --dry-run to import.")
        print(f"\nAll columns in CSV:\n  {list(df.columns)}")
        return {}

    # Validate critical columns
    missing_critical = [k for k in ("date", "team1", "team2") if col_map[k] is None]
    if missing_critical:
        logger.error(f"Missing critical columns: {missing_critical}")
        logger.error("Try --dry-run to see all available column names, then update COLUMN_ALIASES.")
        sys.exit(1)

    # Init DB
    db.init_db()

    # Stats
    n_matches = 0
    n_skipped_tier = 0
    n_skipped_nodate = 0
    n_errors = 0
    team_cache: dict[str, int] = {}  # name → db id

    def get_team_id(name: str, rank: int = None) -> int:
        name = str(name).strip()
        if name not in team_cache:
            # Use hltv_id=None for Kaggle teams (no HLTV ID in dataset)
            # Try to match existing team by name first
            existing = db.get_team_by_name(name)
            if existing:
                team_cache[name] = existing["id"]
            else:
                # Create a placeholder entry (hltv_id=None not allowed due to UNIQUE)
                # Use a negative synthetic ID based on name hash to avoid conflicts
                synthetic_hltv_id = -(abs(hash(name)) % 10_000_000)
                try:
                    tid = db.upsert_team(
                        name=name,
                        hltv_id=synthetic_hltv_id,
                        ranking=rank,
                        country=None,
                    )
                    team_cache[name] = tid
                except Exception:
                    # If duplicate, fetch by name
                    t = db.get_team_by_name(name)
                    team_cache[name] = t["id"] if t else 0
        return team_cache[name]

    rows = df.to_dict("records")
    total = len(rows)
    last_pct = -1

    for i, row in enumerate(rows):
        # Progress
        pct = int(i / total * 100)
        if pct % 10 == 0 and pct != last_pct:
            logger.info(f"  {pct}% ({i:,}/{total:,}) — imported {n_matches:,} matches")
            last_pct = pct

        try:
            raw_date = get(row, col_map["date"])
            if raw_date is None:
                n_skipped_nodate += 1
                continue

            # Normalize date to ISO string
            try:
                date_str = pd.to_datetime(raw_date).isoformat()
            except Exception:
                n_skipped_nodate += 1
                continue

            raw_tier = get(row, col_map["tier"])
            tier = parse_tier(raw_tier)
            if tiers and tier not in tiers:
                n_skipped_tier += 1
                continue

            t1_name = str(get(row, col_map["team1"], "")).strip()
            t2_name = str(get(row, col_map["team2"], "")).strip()
            if not t1_name or not t2_name or t1_name == t2_name:
                n_errors += 1
                continue

            rank1 = get(row, col_map["rank1"])
            rank2 = get(row, col_map["rank2"])
            t1_id = get_team_id(t1_name, int(rank1) if rank1 and not pd.isna(rank1) else None)
            t2_id = get_team_id(t2_name, int(rank2) if rank2 and not pd.isna(rank2) else None)

            t1_score = get(row, col_map["t1_score"])
            t2_score = get(row, col_map["t2_score"])
            winner_id = infer_winner(t1_id, t2_id, t1_score, t2_score)

            best_of = parse_best_of(get(row, col_map["best_of"], 3))
            fmt = f"bo{best_of}"
            event_name = str(get(row, col_map["event"], "")) or "Unknown"
            is_lan = parse_bool(get(row, col_map["is_lan"]))
            hltv_match_id = get(row, col_map["hltv_id"])

            # Use a synthetic HLTV ID if not present (negative, to avoid collisions)
            if hltv_match_id is None or pd.isna(hltv_match_id):
                hltv_match_id = -(abs(hash(f"{t1_name}{t2_name}{date_str}")) % 100_000_000)
            else:
                hltv_match_id = int(hltv_match_id)

            match_id = db.insert_match(
                hltv_id=hltv_match_id,
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
                continue  # duplicate (INSERT OR IGNORE)

            # Map result if map column exists
            map_name = get(row, col_map["map"])
            if map_name and not pd.isna(map_name):
                map_name = str(map_name).strip()
                try:
                    t1s = int(t1_score) if t1_score is not None else 0
                    t2s = int(t2_score) if t2_score is not None else 0
                    map_winner = infer_winner(t1_id, t2_id, t1s, t2s)
                    db.insert_map_result(
                        match_id=match_id,
                        map_name=map_name,
                        map_order=1,
                        team1_score=t1s,
                        team2_score=t2s,
                        winner_id=map_winner or t1_id,
                    )
                except Exception:
                    pass  # map insert failure is non-fatal

            n_matches += 1

        except Exception as e:
            n_errors += 1
            if n_errors <= 5:
                logger.warning(f"Row {i}: {e}")

    # Final summary
    conn = sqlite3.connect(DB_PATH)
    total_matches = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    total_teams = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
    total_maps = conn.execute("SELECT COUNT(*) FROM map_results").fetchone()[0]
    conn.close()

    summary = {
        "imported": n_matches,
        "skipped_tier": n_skipped_tier,
        "skipped_nodate": n_skipped_nodate,
        "errors": n_errors,
        "total_matches_in_db": total_matches,
        "total_teams_in_db": total_teams,
        "total_map_results_in_db": total_maps,
    }

    print("\n=== IMPORT COMPLETE ===")
    print(f"  Imported:          {n_matches:,} matches")
    print(f"  Skipped (tier):    {n_skipped_tier:,}")
    print(f"  Skipped (no date): {n_skipped_nodate:,}")
    print(f"  Errors:            {n_errors:,}")
    print(f"  DB total matches:  {total_matches:,}")
    print(f"  DB total teams:    {total_teams:,}")
    print(f"  DB map results:    {total_maps:,}")

    return summary


def main():
    parser = argparse.ArgumentParser(description="Import Kaggle CS2 dataset into SQLite")
    parser.add_argument("csv", help="Path to downloaded CSV file")
    parser.add_argument("--dry-run", action="store_true", help="Only show column mapping, don't import")
    parser.add_argument("--tier", nargs="+", default=None,
                        help="Filter by tiers (e.g. --tier S A). Default: all tiers.")
    args = parser.parse_args()

    import_csv(args.csv, tiers=args.tier, dry_run=args.dry_run)


if __name__ == "__main__":
    main()