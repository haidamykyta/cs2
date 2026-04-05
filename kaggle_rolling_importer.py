"""
Import griffindesroches rolling stats dataset into match_rolling_features table.

Dataset: updated_ts_cs_data.csv (archive (1).zip)
Rows:    8,226 | Cols: 52
Contains: per-match + rolling-5 stats (ADR, KAST, rating3, opening kills, etc.)

Usage:
    python kaggle_rolling_importer.py
    python kaggle_rolling_importer.py --zip "D:/archive (1).zip"
"""

import argparse
import logging
import sqlite3
import zipfile

import pandas as pd

import database as db
from config import DB_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def fv(row, col, default=None):
    """Safe float extraction."""
    val = row.get(col, default)
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def import_rolling(zip_path: str = "D:/archive (1).zip", csv_path: str = None):
    if zip_path:
        z = zipfile.ZipFile(zip_path)
        candidates = [n for n in z.namelist() if n.endswith(".csv")]
        with z.open(candidates[0]) as f:
            df = pd.read_csv(f)
    else:
        df = pd.read_csv(csv_path)

    logger.info(f"Loaded {len(df):,} rows")

    db.init_db()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    n_inserted = 0
    n_dup = 0
    n_errors = 0

    for i, row in df.iterrows():
        try:
            raw_date = str(row.get("date", "")).replace("Z", "+00:00")
            date_str = pd.to_datetime(raw_date).isoformat()
            t1 = str(row.get("team1_name", "")).strip()
            t2 = str(row.get("team2_name", "")).strip()
            if not t1 or not t2:
                continue

            # Try to find matching match_id from matches table
            match_row = conn.execute("""
                SELECT m.id FROM matches m
                JOIN teams t1 ON m.team1_id = t1.id
                JOIN teams t2 ON m.team2_id = t2.id
                WHERE DATE(m.date) = DATE(?)
                  AND (LOWER(t1.name) = LOWER(?) OR LOWER(t2.name) = LOWER(?))
                  AND (LOWER(t1.name) = LOWER(?) OR LOWER(t2.name) = LOWER(?))
                LIMIT 1
            """, (date_str, t1, t1, t2, t2)).fetchone()
            match_id = match_row[0] if match_row else None

            conn.execute("""
                INSERT OR IGNORE INTO match_rolling_features (
                    match_id, date, t1_name, t2_name,
                    t1_opening_kills, t1_opening_deaths, t1_multi_kill_rounds,
                    t1_kast_pct, t1_clutches_won, t1_kills, t1_deaths,
                    t1_adr, t1_swing_pct, t1_rating3,
                    t2_opening_kills, t2_opening_deaths, t2_multi_kill_rounds,
                    t2_kast_pct, t2_clutches_won, t2_kills, t2_deaths,
                    t2_adr, t2_swing_pct, t2_rating3,
                    t1_roll5_adr, t1_roll5_kills, t1_roll5_kast,
                    t1_roll5_rating3, t1_roll5_opening_kills,
                    t1_roll5_swing_pct, t1_roll5_multi_kills,
                    t2_roll5_adr, t2_roll5_kills, t2_roll5_kast,
                    t2_roll5_rating3, t2_roll5_opening_kills,
                    t2_roll5_swing_pct, t2_roll5_multi_kills
                ) VALUES (
                    ?,?,?,?,  ?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?
                )
            """, (
                match_id, date_str, t1, t2,
                fv(row,"team1_opening_kills"), fv(row,"team1_opening_deaths"),
                fv(row,"team1_multi_kill_rounds"), fv(row,"team1_kast_pct"),
                fv(row,"team1_clutches_won"), fv(row,"team1_kills"),
                fv(row,"team1_deaths"), fv(row,"team1_adr"),
                fv(row,"team1_swing_pct"), fv(row,"team1_rating_3"),
                fv(row,"team2_opening_kills"), fv(row,"team2_opening_deaths"),
                fv(row,"team2_multi_kill_rounds"), fv(row,"team2_kast_pct"),
                fv(row,"team2_clutches_won"), fv(row,"team2_kills"),
                fv(row,"team2_deaths"), fv(row,"team2_adr"),
                fv(row,"team2_swing_pct"), fv(row,"team2_rating_3"),
                fv(row,"team1_roll5_adr"), fv(row,"team1_roll5_kills"),
                fv(row,"team1_roll5_kast_pct"), fv(row,"team1_roll5_rating_3"),
                fv(row,"team1_roll5_opening_kills"), fv(row,"team1_roll5_swing_pct"),
                fv(row,"team1_roll5_multi_kill_rounds"),
                fv(row,"team2_roll5_adr"), fv(row,"team2_roll5_kills"),
                fv(row,"team2_roll5_kast_pct"), fv(row,"team2_roll5_rating_3"),
                fv(row,"team2_roll5_opening_kills"), fv(row,"team2_roll5_swing_pct"),
                fv(row,"team2_roll5_multi_kill_rounds"),
            ))

            if conn.execute("SELECT changes()").fetchone()[0] > 0:
                n_inserted += 1
            else:
                n_dup += 1

        except Exception as e:
            n_errors += 1
            if n_errors <= 5:
                logger.warning(f"Row {i}: {e}")

    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM match_rolling_features").fetchone()[0]
    linked = conn.execute(
        "SELECT COUNT(*) FROM match_rolling_features WHERE match_id IS NOT NULL"
    ).fetchone()[0]
    conn.close()

    print("\n=== ROLLING STATS IMPORT ===")
    print(f"  Inserted:  {n_inserted:,}")
    print(f"  Dups:      {n_dup:,}")
    print(f"  Errors:    {n_errors:,}")
    print(f"  DB total:  {total:,}")
    print(f"  Linked to match: {linked:,} ({linked/total*100:.0f}%)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", default="D:/archive (1).zip")
    parser.add_argument("--csv", default=None)
    args = parser.parse_args()
    import_rolling(zip_path=args.zip if not args.csv else None, csv_path=args.csv)


if __name__ == "__main__":
    main()