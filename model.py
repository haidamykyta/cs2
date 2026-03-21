"""
XGBoost models for CS2 match and map prediction.

Two models:
  - match_model: predicts P(team1 wins match)
  - map_model:   predicts P(team1 wins individual map)

Both use calibrated XGBoost classifiers.
Models are saved as .joblib files with versioned metadata JSON.
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional

import numpy as np
import joblib
from xgboost import XGBClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.metrics import accuracy_score, brier_score_loss

import database as db
from feature_engineer import (build_match_features, build_map_features,
                               features_to_vector, get_feature_names)
from glicko2 import compute_ratings_from_history
from config import MODELS_DIR, MATCH_MODEL_VERSION, MAP_MODEL_VERSION

logger = logging.getLogger(__name__)

MATCH_MODEL_PATH = os.path.join(MODELS_DIR, "match_model.joblib")
MAP_MODEL_PATH   = os.path.join(MODELS_DIR, "map_model.joblib")
MATCH_META_PATH  = os.path.join(MODELS_DIR, "match_model_meta.json")
MAP_META_PATH    = os.path.join(MODELS_DIR, "map_model_meta.json")

os.makedirs(MODELS_DIR, exist_ok=True)


# ── XGBoost config ────────────────────────────────────────────────────────────

def _make_xgb() -> XGBClassifier:
    return XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=3,
        reg_alpha=0.1,
        reg_lambda=1.0,
        use_label_encoder=False,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )


# ── Data preparation ──────────────────────────────────────────────────────────

def _prepare_match_dataset():
    """
    Build training dataset from all completed matches in DB.
    Returns (X, y, match_ids) sorted by date.
    """
    # First compute Glicko-2 ratings from scratch and store them
    _refresh_glicko_ratings()

    matches = db.get_recent_matches.__func__ if False else None
    # Get all completed matches
    import sqlite3
    from config import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT m.*, t1.name as t1_name, t2.name as t2_name
        FROM matches m
        JOIN teams t1 ON m.team1_id = t1.id
        JOIN teams t2 ON m.team2_id = t2.id
        WHERE m.winner_id IS NOT NULL
        ORDER BY m.date ASC
    """).fetchall()
    conn.close()

    X, y, ids = [], [], []
    skipped = 0
    for row in rows:
        row = dict(row)
        feats = build_match_features(
            team1_id=row["team1_id"],
            team2_id=row["team2_id"],
            is_lan=bool(row.get("is_lan")),
            event_tier=row.get("event_tier", "A") or "A",
        )
        if feats is None:
            skipped += 1
            continue
        label = 1 if row["winner_id"] == row["team1_id"] else 0
        X.append(features_to_vector(feats, include_map=False))
        y.append(label)
        ids.append(row["id"])

    logger.info("Match dataset: %d samples (%d skipped)", len(X), skipped)
    return np.array(X, dtype=np.float32), np.array(y), ids


def _prepare_map_dataset():
    """
    Build training dataset from all completed map results in DB.
    """
    import sqlite3
    from config import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT mr.*, m.team1_id, m.team2_id, m.is_lan, m.event_tier, m.date
        FROM map_results mr
        JOIN matches m ON mr.match_id = m.id
        WHERE mr.winner_id IS NOT NULL
        ORDER BY m.date ASC
    """).fetchall()
    conn.close()

    X, y, ids = [], [], []
    skipped = 0
    for row in rows:
        row = dict(row)
        feats = build_map_features(
            team1_id=row["team1_id"],
            team2_id=row["team2_id"],
            map_name=row["map_name"],
            is_lan=bool(row.get("is_lan")),
            event_tier=row.get("event_tier", "A") or "A",
        )
        if feats is None:
            skipped += 1
            continue
        label = 1 if row["winner_id"] == row["team1_id"] else 0
        X.append(features_to_vector(feats, include_map=True))
        y.append(label)
        ids.append(row["id"])

    logger.info("Map dataset: %d samples (%d skipped)", len(X), skipped)
    return np.array(X, dtype=np.float32), np.array(y), ids


# ── Glicko refresh ───────────────────────────────────────────────────────────

def _refresh_glicko_ratings():
    """Recompute Glicko-2 ratings for all teams and store in DB."""
    import sqlite3
    from config import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT team1_id, team2_id, winner_id, date, is_lan
        FROM matches WHERE winner_id IS NOT NULL ORDER BY date ASC
    """).fetchall()
    conn.close()

    history = [dict(r) for r in rows]

    # Overall ratings
    overall = compute_ratings_from_history(history, "overall")
    for team_id, stats in overall.items():
        db.upsert_glicko(team_id, "overall", stats["rating"], stats["rd"],
                         stats["volatility"], stats["matches"])

    # LAN-only ratings
    lan = compute_ratings_from_history(history, "lan_only")
    for team_id, stats in lan.items():
        db.upsert_glicko(team_id, "lan_only", stats["rating"], stats["rd"],
                         stats["volatility"], stats["matches"])

    # Map-specific ratings
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    map_rows = conn.execute("""
        SELECT mr.map_name, mr.winner_id, m.team1_id, m.team2_id, m.date, m.is_lan
        FROM map_results mr
        JOIN matches m ON mr.match_id = m.id
        WHERE mr.winner_id IS NOT NULL
        ORDER BY m.date ASC
    """).fetchall()
    conn.close()

    # Group by map
    maps_history = {}
    for r in map_rows:
        r = dict(r)
        mn = r["map_name"]
        if mn not in maps_history:
            maps_history[mn] = []
        maps_history[mn].append({
            "team1_id": r["team1_id"],
            "team2_id": r["team2_id"],
            "winner_id": r["winner_id"],
            "date": r["date"],
            "is_lan": r["is_lan"],
        })

    for map_name, hist in maps_history.items():
        map_ratings = compute_ratings_from_history(hist, "overall")
        ctx = f"map_{map_name.lower()}"
        for team_id, stats in map_ratings.items():
            db.upsert_glicko(team_id, ctx, stats["rating"], stats["rd"],
                             stats["volatility"], stats["matches"])

    logger.info("Glicko-2 ratings refreshed for %d teams", len(overall))


# ── Training ──────────────────────────────────────────────────────────────────

def train_match_model() -> dict:
    """Train and save match model. Returns metrics."""
    X, y, _ = _prepare_match_dataset()
    if len(X) < 50:
        raise ValueError(f"Not enough training data: {len(X)} samples. Run bootstrap first.")

    base = _make_xgb()
    model = CalibratedClassifierCV(base, cv=5, method="sigmoid")

    # Time-series CV for validation
    tscv = TimeSeriesSplit(n_splits=5)
    cv_scores = cross_val_score(model, X, y, cv=tscv, scoring="accuracy")

    # Train on full dataset
    model.fit(X, y)
    joblib.dump(model, MATCH_MODEL_PATH)

    probs = model.predict_proba(X)[:, 1]
    brier = brier_score_loss(y, probs)
    acc = accuracy_score(y, (probs > 0.5).astype(int))

    meta = {
        "version": MATCH_MODEL_VERSION,
        "trained_at": datetime.utcnow().isoformat(),
        "samples": len(X),
        "accuracy_train": round(acc, 4),
        "cv_accuracy_mean": round(float(cv_scores.mean()), 4),
        "cv_accuracy_std": round(float(cv_scores.std()), 4),
        "brier_score": round(brier, 4),
        "features": get_feature_names(include_map=False),
    }
    with open(MATCH_META_PATH, "w") as f:
        json.dump(meta, f, indent=2)

    logger.info("Match model trained: CV acc=%.3f±%.3f, brier=%.4f",
                cv_scores.mean(), cv_scores.std(), brier)
    return meta


def train_map_model() -> dict:
    """Train and save map model. Returns metrics."""
    X, y, _ = _prepare_map_dataset()
    if len(X) < 50:
        raise ValueError(f"Not enough map data: {len(X)} samples.")

    base = _make_xgb()
    model = CalibratedClassifierCV(base, cv=5, method="sigmoid")

    tscv = TimeSeriesSplit(n_splits=5)
    cv_scores = cross_val_score(model, X, y, cv=tscv, scoring="accuracy")

    model.fit(X, y)
    joblib.dump(model, MAP_MODEL_PATH)

    probs = model.predict_proba(X)[:, 1]
    brier = brier_score_loss(y, probs)
    acc = accuracy_score(y, (probs > 0.5).astype(int))

    meta = {
        "version": MAP_MODEL_VERSION,
        "trained_at": datetime.utcnow().isoformat(),
        "samples": len(X),
        "accuracy_train": round(acc, 4),
        "cv_accuracy_mean": round(float(cv_scores.mean()), 4),
        "cv_accuracy_std": round(float(cv_scores.std()), 4),
        "brier_score": round(brier, 4),
        "features": get_feature_names(include_map=True),
    }
    with open(MAP_META_PATH, "w") as f:
        json.dump(meta, f, indent=2)

    logger.info("Map model trained: CV acc=%.3f±%.3f, brier=%.4f",
                cv_scores.mean(), cv_scores.std(), brier)
    return meta


def train_all() -> dict:
    """Train both models and return combined metrics."""
    logger.info("Training match model...")
    match_meta = train_match_model()
    logger.info("Training map model...")
    map_meta = train_map_model()
    return {"match": match_meta, "map": map_meta}


# ── Inference ─────────────────────────────────────────────────────────────────

_match_model_cache = None
_map_model_cache = None


def _load_match_model():
    global _match_model_cache
    if _match_model_cache is None:
        if not os.path.exists(MATCH_MODEL_PATH):
            raise FileNotFoundError("Match model not trained yet. Run: python model.py train")
        _match_model_cache = joblib.load(MATCH_MODEL_PATH)
    return _match_model_cache


def _load_map_model():
    global _map_model_cache
    if _map_model_cache is None:
        if not os.path.exists(MAP_MODEL_PATH):
            raise FileNotFoundError("Map model not trained yet. Run: python model.py train")
        _map_model_cache = joblib.load(MAP_MODEL_PATH)
    return _map_model_cache


def predict_match(team1_id: int, team2_id: int,
                  is_lan: bool = False, event_tier: str = "A") -> Optional[dict]:
    """
    Predict match outcome.
    Returns: {team1_prob, team2_prob, confidence, model_version}
    Returns None if not enough data.
    """
    feats = build_match_features(team1_id, team2_id, is_lan, event_tier)
    if feats is None:
        return None

    model = _load_match_model()
    X = np.array([features_to_vector(feats)], dtype=np.float32)
    prob1 = float(model.predict_proba(X)[0][1])
    prob2 = 1.0 - prob1

    # Confidence = how far from 0.5 (0=no confidence, 0.5=max)
    confidence = abs(prob1 - 0.5) * 2

    return {
        "team1_prob": round(prob1, 4),
        "team2_prob": round(prob2, 4),
        "confidence": round(confidence, 4),
        "model_version": MATCH_MODEL_VERSION,
    }


def predict_map(team1_id: int, team2_id: int, map_name: str,
                is_lan: bool = False, event_tier: str = "A") -> Optional[dict]:
    """
    Predict single map outcome.
    Returns: {team1_prob, team2_prob, confidence, model_version}
    """
    feats = build_map_features(team1_id, team2_id, map_name, is_lan, event_tier)
    if feats is None:
        return None

    model = _load_map_model()
    X = np.array([features_to_vector(feats, include_map=True)], dtype=np.float32)
    prob1 = float(model.predict_proba(X)[0][1])
    prob2 = 1.0 - prob1
    confidence = abs(prob1 - 0.5) * 2

    return {
        "team1_prob": round(prob1, 4),
        "team2_prob": round(prob2, 4),
        "confidence": round(confidence, 4),
        "model_version": MAP_MODEL_VERSION,
    }


def get_model_meta(model_type: str = "match") -> dict:
    path = MATCH_META_PATH if model_type == "match" else MAP_META_PATH
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "train"
    if cmd == "train":
        db.init_db()
        meta = train_all()
        print("\nMatch model:")
        print(f"  CV accuracy: {meta['match']['cv_accuracy_mean']:.1%} ± {meta['match']['cv_accuracy_std']:.1%}")
        print(f"  Brier score: {meta['match']['brier_score']:.4f}")
        print(f"  Samples:     {meta['match']['samples']}")
        print("\nMap model:")
        print(f"  CV accuracy: {meta['map']['cv_accuracy_mean']:.1%} ± {meta['map']['cv_accuracy_std']:.1%}")
        print(f"  Brier score: {meta['map']['brier_score']:.4f}")
        print(f"  Samples:     {meta['map']['samples']}")
    elif cmd == "glicko":
        db.init_db()
        _refresh_glicko_ratings()
        print("Glicko-2 ratings refreshed.")
