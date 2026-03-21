"""
Feature engineering for CS2 match and map prediction.

Computes a 22-feature vector for each team pair:
  - Glicko-2 ratings (overall + map-specific)
  - Rolling form (last N matches)
  - Map pool win rates + CT/T side rates
  - Head-to-head stats
  - Roster quality (player ratings)
  - Match context (LAN, event tier, ranking diff)
"""

from typing import Optional
import database as db
from glicko2 import Glicko2
from config import (FORM_WINDOW, MAP_FORM_WINDOW, H2H_WINDOW_DAYS,
                    GLICKO_INITIAL_RATING, GLICKO_INITIAL_RD,
                    MIN_MATCHES_FOR_PREDICTION)

_g = Glicko2()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_glicko(team_id: int, context: str = "overall") -> tuple:
    row = db.get_glicko(team_id, context)
    if row:
        return row["rating"], row["rd"]
    return GLICKO_INITIAL_RATING, GLICKO_INITIAL_RD


def _form(team_id: int, n: int = FORM_WINDOW, lan_only: bool = False) -> float:
    """Win rate over last N matches."""
    matches = db.get_recent_matches(team_id, limit=n, lan_only=lan_only)
    if not matches:
        return 0.5
    wins = sum(1 for m in matches if m["winner_id"] == team_id)
    return wins / len(matches)


def _form_vs_ranked(team_id: int, top_n: int = 20, n: int = FORM_WINDOW) -> float:
    """Win rate vs top-N ranked teams over last N matches."""
    matches = db.get_recent_matches(team_id, limit=n * 3)
    filtered = []
    for m in matches:
        opp_id = m["team2_id"] if m["team1_id"] == team_id else m["team1_id"]
        opp = db.get_team_by_id(opp_id)
        if opp and opp.get("ranking") and opp["ranking"] <= top_n:
            filtered.append(m)
        if len(filtered) >= n:
            break
    if not filtered:
        return 0.5
    wins = sum(1 for m in filtered if m["winner_id"] == team_id)
    return wins / len(filtered)


def _avg_player_stats(team_id: int) -> dict:
    """Average Rating 3.0, KAST, K/D for active roster."""
    players = db.get_active_players(team_id)
    if not players:
        return {"rating3": 1.0, "kast": 0.7, "kd": 1.0}
    ratings = [p["rating3"] for p in players if p.get("rating3")]
    kasts = [p["kast"] for p in players if p.get("kast")]
    kds = [p["kd"] for p in players if p.get("kd")]
    return {
        "rating3": sum(ratings) / len(ratings) if ratings else 1.0,
        "kast": sum(kasts) / len(kasts) if kasts else 0.7,
        "kd": sum(kds) / len(kds) if kds else 1.0,
    }


def _map_win_rate(team_id: int, map_name: str, n: int = MAP_FORM_WINDOW) -> float:
    """Win rate on a specific map."""
    rows = db.get_map_results_for_team(team_id, map_name, limit=n)
    if not rows:
        return 0.5
    wins = sum(1 for r in rows if r["winner_id"] == team_id)
    return wins / len(rows)


def _map_side_rates(team_id: int, map_name: str, n: int = MAP_FORM_WINDOW) -> dict:
    """CT-side and T-side win rates for this team on a map."""
    rows = db.get_map_results_for_team(team_id, map_name, limit=n)
    ct_wins, ct_total, t_wins, t_total = 0, 0, 0, 0
    for r in rows:
        is_team1 = r["team1_id"] == team_id
        ct_first = bool(r.get("team1_ct_first"))
        # First half: team started on CT if (is_team1 and ct_first) or (not is_team1 and not ct_first)
        started_ct = (is_team1 and ct_first) or (not is_team1 and not ct_first)
        # We approximate: 12 rounds per half
        s_own = r["team1_score"] if is_team1 else r["team2_score"]
        s_opp = r["team2_score"] if is_team1 else r["team1_score"]
        total_rounds = s_own + s_opp
        if total_rounds == 0:
            continue
        # Split rounds: first 12 = first half, rest = second half
        first_half = min(12, total_rounds)
        second_half = max(0, total_rounds - 12)
        if started_ct:
            ct_wins += min(s_own, first_half)
            ct_total += first_half
            t_wins += max(0, s_own - first_half)
            t_total += second_half
        else:
            t_wins += min(s_own, first_half)
            t_total += first_half
            ct_wins += max(0, s_own - first_half)
            ct_total += second_half
    return {
        "ct_rate": ct_wins / ct_total if ct_total else 0.5,
        "t_rate": t_wins / t_total if t_total else 0.5,
    }


def _h2h(team1_id: int, team2_id: int, days: int = H2H_WINDOW_DAYS) -> float:
    """Team1 win rate in direct head-to-head matches."""
    matches = db.get_matches_between(team1_id, team2_id, days=days)
    if not matches:
        return 0.5
    wins = sum(1 for m in matches if m["winner_id"] == team1_id)
    return wins / len(matches)


def _h2h_on_map(team1_id: int, team2_id: int, map_name: str, n: int = 5) -> float:
    """Team1 win rate vs team2 on a specific map."""
    rows_t1 = db.get_map_results_for_team(team1_id, map_name, limit=50)
    count = wins = 0
    for r in rows_t1:
        opp_id = r["team2_id"] if r["team1_id"] == team1_id else r["team1_id"]
        if opp_id == team2_id:
            wins += 1 if r["winner_id"] == team1_id else 0
            count += 1
        if count >= n:
            break
    return wins / count if count else 0.5


def _ranking_diff(team1_id: int, team2_id: int) -> float:
    """team2_rank - team1_rank (positive = team1 is better ranked)."""
    t1 = db.get_team_by_id(team1_id)
    t2 = db.get_team_by_id(team2_id)
    r1 = t1.get("ranking") if t1 else None
    r2 = t2.get("ranking") if t2 else None
    if r1 is None and r2 is None:
        return 0.0
    if r1 is None:
        return -50.0
    if r2 is None:
        return 50.0
    return float(r2 - r1)


def _event_tier_num(tier: str) -> float:
    """S=4, A=3, B=2, C=1, D/unknown=0"""
    return {"S": 4.0, "A": 3.0, "B": 2.0, "C": 1.0, "D": 0.0}.get(tier.upper(), 0.0)


# ── Main feature builders ─────────────────────────────────────────────────────

def build_match_features(team1_id: int, team2_id: int,
                         is_lan: bool = False, event_tier: str = "A") -> Optional[dict]:
    """
    Build 22-feature dict for match-level prediction.
    Returns None if either team doesn't have enough data.
    """
    matches1 = db.get_recent_matches(team1_id, limit=MIN_MATCHES_FOR_PREDICTION)
    matches2 = db.get_recent_matches(team2_id, limit=MIN_MATCHES_FOR_PREDICTION)
    if len(matches1) < MIN_MATCHES_FOR_PREDICTION or len(matches2) < MIN_MATCHES_FOR_PREDICTION:
        return None

    r1, rd1 = _get_glicko(team1_id)
    r2, rd2 = _get_glicko(team2_id)
    glicko_prob = _g.win_probability(r1, rd1, r2, rd2)

    stats1 = _avg_player_stats(team1_id)
    stats2 = _avg_player_stats(team2_id)

    return {
        # Glicko
        "glicko_diff": r1 - r2,
        "glicko_prob": glicko_prob,
        "rd1": rd1,
        "rd2": rd2,
        # Form
        "form1": _form(team1_id),
        "form2": _form(team2_id),
        "form1_vs_top20": _form_vs_ranked(team1_id),
        "form2_vs_top20": _form_vs_ranked(team2_id),
        "lan_form1": _form(team1_id, lan_only=True),
        "lan_form2": _form(team2_id, lan_only=True),
        # Player quality
        "avg_rating1": stats1["rating3"],
        "avg_rating2": stats2["rating3"],
        "avg_kast1": stats1["kast"],
        "avg_kast2": stats2["kast"],
        "avg_kd1": stats1["kd"],
        "avg_kd2": stats2["kd"],
        # H2H
        "h2h_t1_winrate": _h2h(team1_id, team2_id),
        # Context
        "ranking_diff": _ranking_diff(team1_id, team2_id),
        "is_lan": float(is_lan),
        "event_tier": _event_tier_num(event_tier),
        # Delta features
        "form_delta": _form(team1_id) - _form(team2_id),
        "rating_delta": stats1["rating3"] - stats2["rating3"],
    }


def build_map_features(team1_id: int, team2_id: int, map_name: str,
                       is_lan: bool = False, event_tier: str = "A") -> Optional[dict]:
    """
    Build feature dict for map-level prediction.
    Extends match features with map-specific stats.
    """
    base = build_match_features(team1_id, team2_id, is_lan, event_tier)
    if base is None:
        return None

    sides1 = _map_side_rates(team1_id, map_name)
    sides2 = _map_side_rates(team2_id, map_name)
    map_r1, map_rd1 = _get_glicko(team1_id, f"map_{map_name.lower()}")
    map_r2, map_rd2 = _get_glicko(team2_id, f"map_{map_name.lower()}")
    map_glicko_prob = _g.win_probability(map_r1, map_rd1, map_r2, map_rd2)

    map_feats = {
        "map_wr1": _map_win_rate(team1_id, map_name),
        "map_wr2": _map_win_rate(team2_id, map_name),
        "map_wr_delta": _map_win_rate(team1_id, map_name) - _map_win_rate(team2_id, map_name),
        "ct_rate1": sides1["ct_rate"],
        "t_rate1": sides1["t_rate"],
        "ct_rate2": sides2["ct_rate"],
        "t_rate2": sides2["t_rate"],
        "map_glicko_prob": map_glicko_prob,
        "h2h_on_map": _h2h_on_map(team1_id, team2_id, map_name),
    }
    return {**base, **map_feats}


def get_feature_names(include_map: bool = False) -> list:
    """Return ordered list of feature names (matches column order for XGBoost)."""
    base = [
        "glicko_diff", "glicko_prob", "rd1", "rd2",
        "form1", "form2", "form1_vs_top20", "form2_vs_top20",
        "lan_form1", "lan_form2",
        "avg_rating1", "avg_rating2", "avg_kast1", "avg_kast2",
        "avg_kd1", "avg_kd2",
        "h2h_t1_winrate",
        "ranking_diff", "is_lan", "event_tier",
        "form_delta", "rating_delta",
    ]
    if include_map:
        base += [
            "map_wr1", "map_wr2", "map_wr_delta",
            "ct_rate1", "t_rate1", "ct_rate2", "t_rate2",
            "map_glicko_prob", "h2h_on_map",
        ]
    return base


def features_to_vector(feats: dict, include_map: bool = False) -> list:
    """Convert feature dict to ordered list for model input."""
    names = get_feature_names(include_map)
    return [feats.get(n, 0.5) for n in names]
