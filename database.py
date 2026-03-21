"""
SQLite database layer for CS2 predictor.
Schema: teams, players, matches, map_results, player_match_stats, glicko_ratings, predictions
"""

import sqlite3
import os
from datetime import datetime
from config import DB_PATH


def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS teams (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            hltv_id     INTEGER UNIQUE,
            ranking     INTEGER,
            country     TEXT,
            updated_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS players (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            hltv_id     INTEGER UNIQUE,
            team_id     INTEGER REFERENCES teams(id),
            rating3     REAL,
            kast        REAL,
            kd          REAL,
            adr         REAL,
            is_active   INTEGER DEFAULT 1,
            updated_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS matches (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            hltv_id     INTEGER UNIQUE,
            team1_id    INTEGER REFERENCES teams(id),
            team2_id    INTEGER REFERENCES teams(id),
            date        TEXT,
            format      TEXT,
            event       TEXT,
            event_tier  TEXT,
            is_lan      INTEGER DEFAULT 0,
            winner_id   INTEGER REFERENCES teams(id),
            source      TEXT DEFAULT 'hltv',
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS map_results (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id        INTEGER REFERENCES matches(id),
            map_name        TEXT,
            map_order       INTEGER,
            team1_score     INTEGER,
            team2_score     INTEGER,
            winner_id       INTEGER REFERENCES teams(id),
            team1_ct_first  INTEGER DEFAULT 0,
            overtime        INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS player_match_stats (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id    INTEGER REFERENCES matches(id),
            player_id   INTEGER REFERENCES players(id),
            map_name    TEXT,
            kills       INTEGER,
            deaths      INTEGER,
            assists     INTEGER,
            rating      REAL,
            kast        REAL,
            adr         REAL,
            opening_kills INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS glicko_ratings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id         INTEGER REFERENCES teams(id),
            context         TEXT DEFAULT 'overall',
            rating          REAL DEFAULT 1500.0,
            rd              REAL DEFAULT 350.0,
            volatility      REAL DEFAULT 0.06,
            matches_played  INTEGER DEFAULT 0,
            calculated_at   TEXT DEFAULT (datetime('now')),
            UNIQUE(team_id, context)
        );

        CREATE TABLE IF NOT EXISTS predictions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id        INTEGER REFERENCES matches(id),
            team1_prob      REAL,
            team2_prob      REAL,
            confidence      REAL,
            model_version   TEXT,
            predicted_at    TEXT DEFAULT (datetime('now')),
            correct         INTEGER,
            resolved_at     TEXT
        );

        CREATE TABLE IF NOT EXISTS map_predictions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id        INTEGER REFERENCES matches(id),
            map_name        TEXT,
            map_order       INTEGER,
            team1_prob      REAL,
            team2_prob      REAL,
            model_version   TEXT,
            predicted_at    TEXT DEFAULT (datetime('now')),
            correct         INTEGER,
            resolved_at     TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date);
        CREATE INDEX IF NOT EXISTS idx_map_results_match ON map_results(match_id);
        CREATE INDEX IF NOT EXISTS idx_glicko_team_ctx ON glicko_ratings(team_id, context);
        """)


# ── Teams ────────────────────────────────────────────────────────────────────

def upsert_team(name: str, hltv_id: int, ranking: int = None, country: str = None) -> int:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO teams (name, hltv_id, ranking, country, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(hltv_id) DO UPDATE SET
                name=excluded.name,
                ranking=excluded.ranking,
                country=excluded.country,
                updated_at=excluded.updated_at
        """, (name, hltv_id, ranking, country))
        row = conn.execute("SELECT id FROM teams WHERE hltv_id=?", (hltv_id,)).fetchone()
        return row["id"]


def get_team_by_name(name: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM teams WHERE LOWER(name) LIKE LOWER(?)", (f"%{name}%",)
        ).fetchone()
        return dict(row) if row else None


def get_team_by_id(team_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM teams WHERE id=?", (team_id,)).fetchone()
        return dict(row) if row else None


def get_all_teams():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM teams ORDER BY ranking NULLS LAST").fetchall()
        return [dict(r) for r in rows]


# ── Players ──────────────────────────────────────────────────────────────────

def upsert_player(name: str, hltv_id: int, team_id: int,
                  rating3: float = None, kast: float = None,
                  kd: float = None, adr: float = None) -> int:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO players (name, hltv_id, team_id, rating3, kast, kd, adr, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(hltv_id) DO UPDATE SET
                name=excluded.name,
                team_id=excluded.team_id,
                rating3=excluded.rating3,
                kast=excluded.kast,
                kd=excluded.kd,
                adr=excluded.adr,
                updated_at=excluded.updated_at
        """, (name, hltv_id, team_id, rating3, kast, kd, adr))
        row = conn.execute("SELECT id FROM players WHERE hltv_id=?", (hltv_id,)).fetchone()
        return row["id"]


def get_active_players(team_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM players WHERE team_id=? AND is_active=1", (team_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Matches ──────────────────────────────────────────────────────────────────

def insert_match(hltv_id: int, team1_id: int, team2_id: int, date: str,
                 fmt: str, event: str, event_tier: str, is_lan: bool,
                 winner_id: int = None) -> int:
    with get_conn() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO matches
              (hltv_id, team1_id, team2_id, date, format, event, event_tier, is_lan, winner_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (hltv_id, team1_id, team2_id, date, fmt, event, event_tier, int(is_lan), winner_id))
        row = conn.execute("SELECT id FROM matches WHERE hltv_id=?", (hltv_id,)).fetchone()
        return row["id"] if row else None


def update_match_winner(hltv_id: int, winner_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE matches SET winner_id=? WHERE hltv_id=?", (winner_id, hltv_id)
        )


def get_matches_between(team1_id: int, team2_id: int, days: int = 180):
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM matches
            WHERE ((team1_id=? AND team2_id=?) OR (team1_id=? AND team2_id=?))
              AND date >= datetime('now', ?)
              AND winner_id IS NOT NULL
            ORDER BY date DESC
        """, (team1_id, team2_id, team2_id, team1_id, f"-{days} days")).fetchall()
        return [dict(r) for r in rows]


def get_recent_matches(team_id: int, limit: int = 20, lan_only: bool = False):
    with get_conn() as conn:
        lan_filter = "AND is_lan=1" if lan_only else ""
        rows = conn.execute(f"""
            SELECT * FROM matches
            WHERE (team1_id=? OR team2_id=?) AND winner_id IS NOT NULL
            {lan_filter}
            ORDER BY date DESC LIMIT ?
        """, (team_id, team_id, limit)).fetchall()
        return [dict(r) for r in rows]


def get_upcoming_matches(hours_ahead: int = 48):
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT m.*, t1.name as team1_name, t2.name as team2_name
            FROM matches m
            JOIN teams t1 ON m.team1_id = t1.id
            JOIN teams t2 ON m.team2_id = t2.id
            WHERE m.winner_id IS NULL
              AND m.date >= datetime('now', '-1 hour')
              AND m.date <= datetime('now', ? || ' hours')
            ORDER BY m.date ASC
        """, (str(hours_ahead),)).fetchall()
        return [dict(r) for r in rows]


# ── Map Results ──────────────────────────────────────────────────────────────

def insert_map_result(match_id: int, map_name: str, map_order: int,
                      team1_score: int, team2_score: int,
                      winner_id: int, team1_ct_first: bool = False,
                      overtime: bool = False):
    with get_conn() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO map_results
              (match_id, map_name, map_order, team1_score, team2_score,
               winner_id, team1_ct_first, overtime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (match_id, map_name, map_order, team1_score, team2_score,
              winner_id, int(team1_ct_first), int(overtime)))


def get_map_results_for_team(team_id: int, map_name: str, limit: int = 30):
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT mr.*, m.team1_id, m.team2_id, m.date
            FROM map_results mr
            JOIN matches m ON mr.match_id = m.id
            WHERE (m.team1_id=? OR m.team2_id=?)
              AND mr.map_name=?
            ORDER BY m.date DESC LIMIT ?
        """, (team_id, team_id, map_name, limit)).fetchall()
        return [dict(r) for r in rows]


def get_maps_for_match(match_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM map_results WHERE match_id=? ORDER BY map_order",
            (match_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Glicko Ratings ───────────────────────────────────────────────────────────

def upsert_glicko(team_id: int, context: str, rating: float, rd: float,
                  volatility: float, matches_played: int):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO glicko_ratings (team_id, context, rating, rd, volatility, matches_played, calculated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(team_id, context) DO UPDATE SET
                rating=excluded.rating,
                rd=excluded.rd,
                volatility=excluded.volatility,
                matches_played=excluded.matches_played,
                calculated_at=excluded.calculated_at
        """, (team_id, context, rating, rd, volatility, matches_played))


def get_glicko(team_id: int, context: str = "overall"):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM glicko_ratings WHERE team_id=? AND context=?",
            (team_id, context)
        ).fetchone()
        return dict(row) if row else None


# ── Predictions ───────────────────────────────────────────────────────────────

def insert_prediction(match_id: int, team1_prob: float, team2_prob: float,
                      confidence: float, model_version: str) -> int:
    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO predictions
              (match_id, team1_prob, team2_prob, confidence, model_version)
            VALUES (?, ?, ?, ?, ?)
        """, (match_id, team1_prob, team2_prob, confidence, model_version))
        row = conn.execute(
            "SELECT id FROM predictions WHERE match_id=? ORDER BY predicted_at DESC LIMIT 1",
            (match_id,)
        ).fetchone()
        return row["id"]


def resolve_prediction(match_id: int, actual_winner_id: int, team1_id: int):
    correct = 1 if actual_winner_id == team1_id else 0
    with get_conn() as conn:
        pred = conn.execute(
            "SELECT id, team1_prob FROM predictions WHERE match_id=?", (match_id,)
        ).fetchone()
        if pred:
            predicted_team1_wins = pred["team1_prob"] > 0.5
            correct = 1 if (predicted_team1_wins and actual_winner_id == team1_id) or \
                           (not predicted_team1_wins and actual_winner_id != team1_id) else 0
            conn.execute(
                "UPDATE predictions SET correct=?, resolved_at=datetime('now') WHERE id=?",
                (correct, pred["id"])
            )


def get_prediction_history(limit: int = 20):
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT p.*, t1.name as team1_name, t2.name as team2_name,
                   m.date, m.event
            FROM predictions p
            JOIN matches m ON p.match_id = m.id
            JOIN teams t1 ON m.team1_id = t1.id
            JOIN teams t2 ON m.team2_id = t2.id
            WHERE p.correct IS NOT NULL
            ORDER BY p.predicted_at DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


def get_prediction_stats():
    with get_conn() as conn:
        row = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(correct) as wins,
                ROUND(100.0 * SUM(correct) / COUNT(*), 1) as accuracy
            FROM predictions
            WHERE correct IS NOT NULL
        """).fetchone()
        return dict(row) if row else {"total": 0, "wins": 0, "accuracy": 0.0}
