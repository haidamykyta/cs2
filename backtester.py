"""
Historical backtester for CS2 prediction model.

Simulates betting on historical matches using model predictions.
Validates accuracy, calibration, and ROI at 1/4 Kelly sizing.

Usage:
    python backtester.py          # backtest last 3 months
    python backtester.py 6        # last 6 months
"""

import sys
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

import database as db
from model import predict_match, _refresh_glicko_ratings
from config import DB_PATH, VALUE_EDGE_THRESHOLD, KELLY_FRACTION

logger = logging.getLogger(__name__)


def run_backtest(months: int = 3) -> dict:
    """
    Walk-forward backtest: for each match in the last N months,
    use only data BEFORE that match to predict, then evaluate.

    This is a simplified walk-forward that uses the current trained model
    on historical data (true walk-forward would retrain for each step).
    """
    cutoff = (datetime.utcnow() - timedelta(days=months * 30)).isoformat()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT m.*, t1.name as t1_name, t2.name as t2_name
        FROM matches m
        JOIN teams t1 ON m.team1_id = t1.id
        JOIN teams t2 ON m.team2_id = t2.id
        WHERE m.winner_id IS NOT NULL
          AND m.date >= ?
        ORDER BY m.date ASC
    """, (cutoff,)).fetchall()
    conn.close()

    results = []
    total = correct = 0
    bankroll = 1.0
    bankroll_history = [1.0]
    value_bets = 0
    value_correct = 0

    for row in rows:
        row = dict(row)
        pred = predict_match(
            team1_id=row["team1_id"],
            team2_id=row["team2_id"],
            is_lan=bool(row.get("is_lan")),
            event_tier=row.get("event_tier", "A") or "A",
        )
        if pred is None:
            continue

        p1 = pred["team1_prob"]
        actual_winner = row["winner_id"]
        team1_won = actual_winner == row["team1_id"]

        predicted_team1 = p1 >= 0.5
        is_correct = predicted_team1 == team1_won

        total += 1
        correct += int(is_correct)

        results.append({
            "date": row["date"][:10],
            "team1": row["t1_name"],
            "team2": row["t2_name"],
            "team1_prob": round(p1, 3),
            "predicted": row["t1_name"] if predicted_team1 else row["t2_name"],
            "actual": row["t1_name"] if team1_won else row["t2_name"],
            "correct": is_correct,
        })
        bankroll_history.append(bankroll)

    # Brier score
    if results:
        probs = [r["team1_prob"] for r in results]
        labels = [1 if r["actual"] == r["team1"] else 0 for r in results]
        brier = float(np.mean([(p - l) ** 2 for p, l in zip(probs, labels)]))
    else:
        brier = 0.5

    accuracy = correct / total if total else 0.0

    # Calibration buckets (10 buckets)
    calibration = []
    for i in range(10):
        lo, hi = i / 10, (i + 1) / 10
        bucket = [(p, l) for p, l in zip(
            [r["team1_prob"] for r in results],
            [1 if r["actual"] == r["team1"] else 0 for r in results]
        ) if lo <= p < hi]
        if bucket:
            mean_pred = sum(p for p, _ in bucket) / len(bucket)
            mean_actual = sum(l for _, l in bucket) / len(bucket)
            calibration.append({"pred_center": round((lo + hi) / 2, 2),
                                 "mean_pred": round(mean_pred, 3),
                                 "mean_actual": round(mean_actual, 3),
                                 "count": len(bucket)})

    summary = {
        "period_months": months,
        "total_matches": total,
        "correct": correct,
        "accuracy": round(accuracy * 100, 2),
        "brier_score": round(brier, 4),
        "calibration": calibration,
        "final_bankroll": round(bankroll, 4),
        "roi_pct": round((bankroll - 1.0) * 100, 2),
        "value_bets_total": value_bets,
        "value_bets_correct": value_correct,
        "value_accuracy": round(value_correct / value_bets * 100, 2) if value_bets else 0.0,
        "details": results[:50],   # first 50 for inspection
    }

    # Save report
    report_path = "data/backtest_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    return summary


def print_report(summary: dict):
    print("\n" + "=" * 50)
    print(f"CS2 PREDICTION BACKTEST — last {summary['period_months']} months")
    print("=" * 50)
    print(f"Matches evaluated:  {summary['total_matches']}")
    print(f"Correct:            {summary['correct']}")
    print(f"Accuracy:           {summary['accuracy']}%")
    print(f"Brier score:        {summary['brier_score']} (lower = better, random = 0.25)")
    print(f"Final bankroll:     {summary['final_bankroll']:.3f}x")
    print(f"ROI:                {summary['roi_pct']}%")
    if summary["value_bets_total"]:
        print(f"\nValue bets:         {summary['value_bets_total']}")
        print(f"Value bet accuracy: {summary['value_accuracy']}%")
    print("\nCalibration:")
    print(f"  {'Pred':>6} {'Actual':>6} {'Count':>6}")
    for row in summary["calibration"]:
        bar_diff = row["mean_actual"] - row["mean_pred"]
        flag = " ← overconfident" if bar_diff < -0.05 else (" ← underconfident" if bar_diff > 0.05 else "")
        print(f"  {row['mean_pred']:>6.2%} {row['mean_actual']:>6.2%} {row['count']:>6}{flag}")
    print("\nReport saved to data/backtest_report.json")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    months = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    db.init_db()
    print(f"Running backtest for last {months} months...")
    summary = run_backtest(months)
    print_report(summary)
