"""
Kaggle CS2 HLTV dataset importer — specific to griffindesroches dataset.

Dataset: cs2_newestcombinedmatches.csv
Rows:    7,033 | Period: May 2024 - Oct 2025 | All BO3
Columns: 140 (match info + player stats for all 10 players + pre-computed features)

Usage:
    python kaggle_importer.py                              # from D:/archive.zip (default)
    python kaggle_importer.py --csv path/to/file.csv      # from extracted CSV
    python kaggle_importer.py --zip D:/archive.zip        # from ZIP
    python kaggle_importer.py --dry-run                   # show stats, don't import
"""

import sys
import argparse
import logging
import sqlite3
import zipfile
import io
from pathlib import Path

import pandas as pd

import database as db
from config import DB_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def load_df(zip_path: str = None, csv_path: str = None) -> pd.DataFrame:
    """Load the main CSV from ZIP or direct path."""
    if zip_path:
        logger.info(f"Reading from ZIP: {zip_path}")
        z = zipfile.ZipFile(zip_path)
        # Find the main combined matches file
        candidates = [n for n in z.namelist() if "combinedmatches" in n.lower() and n.endswith(".csv")]
        if not candidates:
            candidates = [n for n in z.namelist() if n.endswith(".csv")]
        if not candidates:
            raise FileNotFoundError(f"No CSV found in {zip_path}")
        target = candidates[0]
        logger.info(f"Found CSV: {target}")
        with z.open(target) as f:
            return pd.read_csv(f)
    elif csv_path:
        logger.info(f"Reading CSV: {csv_path}")
        return pd.read_csv(csv_path)
    else:
        raise ValueError("Provide either --zip or --csv")


def get_or_create_team(conn: sqlite3.Connection, name: str, team_cache: dict) -> int:
    """Return DB team id, creating if not exists."""
    name = str(name).strip()
    if name in team_cache:
        return team_cache[name]

    # Try existing by name
    row = conn.execute(
        "SELECT id FROM teams WHERE LOWER(name) = LOWER(?)", (name,)
    ).fetchone()
    if row:
        team_cache[name] = row[0]
        return row[0]

    # Insert new — use synthetic hltv_id (negative hash to avoid real HLTV ID conflicts)
    synthetic_id = -(abs(hash(name)) % 10_000_000)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO teams (name, hltv_id, updated_at) VALUES (?, ?, datetime('now'))",
            (name, synthetic_id)
        )
        row = conn.execute("SELECT id FROM teams WHERE hltv_id=?", (synthetic_id,)).fetchone()
        if row:
            team_cache[name] = row[0]
            return row[0]
    except Exception:
        pass

    # Fallback: fetch after conflict
    row = conn.execute("SELECT id FROM teams WHERE LOWER(name) = LOWER(?)", (name,)).fetchone()
    if row:
        team_cache[name] = row[0]
        return row[0]
    raise RuntimeError(f"Cannot resolve team: {name}")


def get_or_create_player(conn: sqlite3.Connection, name: str,
                          team_id: int, player_cache: dict) -> int:
    """Return DB player id, creating if not exists."""
    key = name.strip().lower()
    if key in player_cache:
        return player_cache[key]

    row = conn.execute(
        "SELECT id FROM players WHERE LOWER(name) = LOWER(?)", (name,)
    ).fetchone()
    if row:
        player_cache[key] = row[0]
        return row[0]

    synthetic_id = -(abs(hash(name)) % 10_000_000)
    conn.execute("""
        INSERT OR IGNORE INTO players (name, hltv_id, team_id, updated_at)
        VALUES (?, ?, ?, datetime('now'))
    """, (name.strip(), synthetic_id, team_id))
    row = conn.execute("SELECT id FROM players WHERE hltv_id=?", (synthetic_id,)).fetchone()
    if row:
        player_cache[key] = row[0]
        return row[0]

    row = conn.execute("SELECT id FROM players WHERE LOWER(name) = LOWER(?)", (name,)).fetchone()
    if row:
        player_cache[key] = row[0]
        return row[0]
    return 0


def parse_is_lan(val) -> bool:
    if val is None:
        return False
    return str(val).strip().upper() in ("LAN", "1", "TRUE", "YES")


def import_dataset(zip_path: str = None, csv_path: str = None, dry_run: bool = False) -> dict:
    df = load_df(zip_path=zip_path, csv_path=csv_path)

    logger.info(f"Loaded {len(df):,} rows, {len(df.columns)} columns")
    logger.info(f"Date range: {df['date'].min()} to {df['date'].max()}")
    logger.info(f"Unique teams: {pd.concat([df['team1_name'], df['team2_name']]).nunique()}")

    if dry_run:
        print("\n=== DRY RUN — no data written ===")
        print(f"Rows:    {len(df):,}")
        print(f"Columns: {len(df.columns)}")
        print(f"Dates:   {df['date'].min()} to {df['date'].max()}")
        print(f"Teams:   {pd.concat([df['team1_name'], df['team2_name']]).nunique()} unique")
        print(f"Events:  {df['tournament'].nunique()} unique tournaments")
        print(f"LAN:     {df['event_type'].str.upper().eq('LAN').sum():,} matches")
        print(f"Online:  {df['event_type'].str.upper().ne('LAN').sum():,} matches")
        return {}

    db.init_db()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    team_cache: dict[str, int] = {}
    player_cache: dict[str, int] = {}

    n_matches = 0
    n_players = 0
    n_maps = 0
    n_errors = 0
    n_dup = 0
    total = len(df)

    logger.info("Starting import...")

    for i, row in df.iterrows():
        if i % 500 == 0:
            pct = int(i / total * 100)
            logger.info(f"  {pct}% ({i:,}/{total:,}) — matches: {n_matches:,} maps: {n_maps:,}")

        try:
            # ── Teams ────────────────────────────────────────────────────────
            t1_name = str(row["team1_name"]).strip()
            t2_name = str(row["team2_name"]).strip()
            t1_id = get_or_create_team(conn, t1_name, team_cache)
            t2_id = get_or_create_team(conn, t2_name, team_cache)

            # ── Winner ────────────────────────────────────────────────────────
            winner_str = str(row.get("winner", "")).strip().lower()
            if winner_str == "team1":
                winner_id = t1_id
                loser_id = t2_id
            elif winner_str == "team2":
                winner_id = t2_id
                loser_id = t1_id
            else:
                winner_id = None
                loser_id = None

            # ── Date ─────────────────────────────────────────────────────────
            date_str = str(row["date"]).strip().replace("Z", "+00:00")
            try:
                date_str = pd.to_datetime(date_str).isoformat()
            except Exception:
                n_errors += 1
                continue

            # ── Match metadata ────────────────────────────────────────────────
            is_lan = parse_is_lan(row.get("event_type"))
            event_name = str(row.get("tournament", "Unknown")).strip()
            hltv_match_id = int(row["hltv_match_id"])
            fmt = str(row.get("match_type", "bo3")).strip().lower()

            # ── Insert match (directly via conn to avoid lock conflicts) ────────
            conn.execute("""
                INSERT OR IGNORE INTO matches
                  (hltv_id, team1_id, team2_id, date, format, event,
                   event_tier, is_lan, winner_id, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'kaggle')
            """, (hltv_match_id, t1_id, t2_id, date_str, fmt, event_name,
                  "B", int(is_lan), winner_id))

            row_db = conn.execute(
                "SELECT id FROM matches WHERE hltv_id=?", (hltv_match_id,)
            ).fetchone()
            if row_db is None:
                n_dup += 1
                continue
            match_id = row_db[0]

            # Skip if this match already had map/player data (already imported)
            existing_maps = conn.execute(
                "SELECT COUNT(*) FROM map_results WHERE match_id=?", (match_id,)
            ).fetchone()[0]
            if existing_maps > 0:
                n_dup += 1
                continue
            n_matches += 1

            # ── Map results ───────────────────────────────────────────────────
            t1_score = int(row.get("score_team1", 0) or 0)
            t2_score = int(row.get("score_team2", 0) or 0)
            is_2_1 = (t1_score == 2 and t2_score == 1) or (t1_score == 1 and t2_score == 2)

            map_order = 1
            for col, map_winner_id in [
                ("winner_map",  winner_id),       # winner's pick → winner won it
                ("loser_map",   loser_id if is_2_1 else winner_id),  # loser's pick
                ("decider_map", winner_id),        # decider → winner won it
            ]:
                map_name = row.get(col)
                if map_name and not pd.isna(map_name):
                    map_name = str(map_name).strip()
                    if map_name and map_name.lower() not in ("nan", "none", ""):
                        try:
                            conn.execute("""
                                INSERT OR IGNORE INTO map_results
                                  (match_id, map_name, map_order, team1_score,
                                   team2_score, winner_id, team1_ct_first)
                                VALUES (?, ?, ?, 0, 0, ?, 0)
                            """, (match_id, map_name, map_order, map_winner_id or winner_id))
                            n_maps += 1
                        except Exception:
                            pass
                        map_order += 1

            # ── Players ───────────────────────────────────────────────────────
            for team_prefix, team_id in [("team1", t1_id), ("team2", t2_id)]:
                for p_num in range(1, 6):
                    p_name_col = f"{team_prefix}_player_{p_num}_name"
                    p_name = row.get(p_name_col)
                    if not p_name or pd.isna(p_name):
                        continue
                    p_name = str(p_name).strip()
                    if not p_name:
                        continue

                    p_id = get_or_create_player(conn, p_name, team_id, player_cache)
                    if not p_id:
                        continue

                    rating = row.get(f"{team_prefix}_player_{p_num}_RATING")
                    kast   = row.get(f"{team_prefix}_player_{p_num}_KAST")
                    adr    = row.get(f"{team_prefix}_player_{p_num}_ADR")
                    kpr    = row.get(f"{team_prefix}_player_{p_num}_KPR")
                    dpr    = row.get(f"{team_prefix}_player_{p_num}_DPR")

                    # Update player's rolling stats in players table
                    conn.execute("""
                        UPDATE players SET
                            rating3 = ?,
                            kast    = ?,
                            kd      = ?,
                            adr     = ?,
                            team_id = ?,
                            updated_at = datetime('now')
                        WHERE id = ?
                    """, (
                        float(rating) if rating and not pd.isna(rating) else None,
                        float(kast)   if kast   and not pd.isna(kast)   else None,
                        float(kpr)    if kpr    and not pd.isna(kpr)    else None,
                        float(adr)    if adr    and not pd.isna(adr)    else None,
                        team_id,
                        p_id,
                    ))

                    # Insert per-match stats
                    try:
                        conn.execute("""
                            INSERT OR IGNORE INTO player_match_stats
                              (match_id, player_id, map_name, kills, deaths, assists,
                               rating, kast, adr)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            match_id, p_id, "overall", None, None, None,
                            float(rating) if rating and not pd.isna(rating) else None,
                            float(kast)   if kast   and not pd.isna(kast)   else None,
                            float(adr)    if adr    and not pd.isna(adr)    else None,
                        ))
                        n_players += 1
                    except Exception:
                        pass

        except Exception as e:
            n_errors += 1
            if n_errors <= 5:
                logger.warning(f"Row {i}: {e}")

    conn.commit()

    # Final DB counts
    total_db = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    total_teams = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
    total_players = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    total_maps = conn.execute("SELECT COUNT(*) FROM map_results").fetchone()[0]
    conn.close()

    print("\n=== IMPORT COMPLETE ===")
    print(f"  Imported:       {n_matches:,} new matches")
    print(f"  Duplicates:     {n_dup:,} skipped")
    print(f"  Map results:    {n_maps:,} inserted")
    print(f"  Player stats:   {n_players:,} inserted")
    print(f"  Errors:         {n_errors:,}")
    print(f"")
    print(f"  DB matches:     {total_db:,}")
    print(f"  DB teams:       {total_teams:,}")
    print(f"  DB players:     {total_players:,}")
    print(f"  DB map results: {total_maps:,}")

    return {
        "imported": n_matches, "duplicates": n_dup,
        "maps": n_maps, "players": n_players, "errors": n_errors,
        "total_matches": total_db,
    }


def main():
    parser = argparse.ArgumentParser(description="Import griffindesroches Kaggle CS2 dataset")
    parser.add_argument("--zip", default="D:/archive.zip", help="Path to archive.zip (default: D:/archive.zip)")
    parser.add_argument("--csv", default=None, help="Path to extracted CSV file")
    parser.add_argument("--dry-run", action="store_true", help="Show stats without importing")
    args = parser.parse_args()

    import_dataset(
        zip_path=args.zip if not args.csv else None,
        csv_path=args.csv,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()