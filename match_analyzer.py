"""
Deep match analysis orchestrator.

Combines live HLTV scraping + DB data into a structured AnalysisResult
for the /analyze Telegram command.

Usage:
    result = await analyze("NiP", "Liquid", is_lan=True)
    text = format_deep_analysis(result)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import database as db
from config import CS2_MAPS, H2H_WINDOW_DAYS
from feature_engineer import _form, _map_win_rate
from predictor import resolve_team, calculate_value_bet, ValueBet
from hltv_live import scrape_map_pool, scrape_player_stats, scrape_bo3gg

logger = logging.getLogger(__name__)

# Active CS2 map pool for veto analysis
VETO_MAPS = ["Mirage", "Inferno", "Nuke", "Ancient", "Anubis", "Dust2", "Vertigo"]
ROLE_LABELS = ["AWP/Звезда", "Энтри", "Рифлер", "Поддержка", "IGL"]


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class MapComparison:
    map_name: str
    t1_wr: float
    t1_maps: int
    t2_wr: float
    t2_maps: int
    edge: str          # "T1 EDGE", "T2 EDGE", "even", "no_data"
    is_t1_perma: bool  # team1 likely permabans this
    is_t2_perma: bool


@dataclass
class PlayerDuel:
    role: str
    t1_name: str
    t1_rating: float
    t2_name: str
    t2_rating: float
    edge: str          # "T1", "T2", "even"


@dataclass
class AnalysisResult:
    t1_name: str
    t2_name: str
    t1_id: int
    t2_id: int
    is_lan: bool
    event_tier: str

    # Form
    t1_form_90d: float
    t2_form_90d: float
    t1_lan_form: float
    t2_lan_form: float
    t1_rank: Optional[int]
    t2_rank: Optional[int]

    # Maps
    map_comparison: list = field(default_factory=list)   # list[MapComparison]
    veto_prediction: str = ""

    # Players
    player_comparison: list = field(default_factory=list)  # list[PlayerDuel]

    # H2H
    h2h_t1_wins: int = 0
    h2h_t2_wins: int = 0
    h2h_total: int = 0
    h2h_recent: list = field(default_factory=list)

    # External
    bo3gg_t1_pct: float = 0.0
    bo3gg_t2_pct: float = 0.0
    bo3gg_analysis: str = ""

    # Model
    model_t1_prob: float = 0.5
    model_t2_prob: float = 0.5
    model_confidence: float = 0.0
    model_version: str = "?"
    value_bet: Optional[ValueBet] = None
    data_warning: str = ""


# ── Core helpers ──────────────────────────────────────────────────────────────

def _map_edge(t1_wr: float, t1_n: int, t2_wr: float, t2_n: int) -> str:
    if t1_n < 3 and t2_n < 3:
        return "no_data"
    if t1_n < 3:
        return "no_data_t1"
    if t2_n < 3:
        return "no_data_t2"
    diff = t1_wr - t2_wr
    if diff > 0.12:
        return "T1 EDGE"
    if diff < -0.12:
        return "T2 EDGE"
    return "even"


def _is_perma(times_played: int, threshold: int = 2) -> bool:
    """Treat map as permaban if team played it < threshold times in 90 days."""
    return times_played < threshold


def _predict_veto(
    t1_name: str, t2_name: str,
    t1_maps: dict, t2_maps: dict,
    t1_permbans: list, t2_permbans: list,
) -> str:
    """
    Predict veto outcome for a BO3:
    - T1 picks their best map not permabanned by T2
    - T2 picks their best map not permabanned by T1
    - Decider = highest combined WR map among remaining
    Returns human-readable prediction string.
    """
    def best_pick(player_maps: dict, opponent_permbans: list) -> Optional[str]:
        playable = {k: v for k, v in player_maps.items() if k not in opponent_permbans and v["n"] >= 3}
        if not playable:
            return None
        return max(playable, key=lambda m: playable[m]["wr"])

    t1_pick = best_pick(t1_maps, t2_permbans)
    t2_pick = best_pick(t2_maps, t1_permbans)

    # Decider: remove picks + permbans, find highest combined WR
    excluded = set(t1_permbans + t2_permbans)
    if t1_pick:
        excluded.add(t1_pick)
    if t2_pick:
        excluded.add(t2_pick)

    remaining = {
        m: (t1_maps.get(m, {}).get("wr", 0.5) + t2_maps.get(m, {}).get("wr", 0.5)) / 2
        for m in VETO_MAPS if m not in excluded
    }
    decider = max(remaining, key=remaining.get) if remaining else "неизвестно"

    lines = []
    if t1_pick:
        wr = t1_maps[t1_pick]["wr"]
        lines.append(f"  {t1_name} пикнет: {t1_pick} ({wr:.0%} WR)")
    if t2_pick:
        wr = t2_maps[t2_pick]["wr"]
        lines.append(f"  {t2_name} пикнет: {t2_pick} ({wr:.0%} WR)")
    if decider != "неизвестно":
        t1_wr = t1_maps.get(decider, {}).get("wr", 0)
        t2_wr = t2_maps.get(decider, {}).get("wr", 0)
        edge_t = t1_name if t1_wr > t2_wr + 0.05 else (t2_name if t2_wr > t1_wr + 0.05 else "равно")
        lines.append(f"  Дека: {decider} (edge: {edge_t})")

    return "\n".join(lines) if lines else "  недостаточно данных"


def _build_player_duels(t1_players: list, t2_players: list,
                        t1_name: str, t2_name: str) -> list:
    """
    Pair up to 5 players per team by position (sorted by rating desc).
    Assign roles: AWP/Звезда, Энтри, Рифлер, Поддержка, IGL.
    """
    duels = []
    max_players = min(5, max(len(t1_players), len(t2_players)))

    for i in range(max_players):
        role = ROLE_LABELS[i] if i < len(ROLE_LABELS) else f"Игрок {i+1}"
        p1 = t1_players[i] if i < len(t1_players) else None
        p2 = t2_players[i] if i < len(t2_players) else None

        p1_name = p1["name"] if p1 else "—"
        p1_rat  = p1["rating"] if p1 else 0.0
        p2_name = p2["name"] if p2 else "—"
        p2_rat  = p2["rating"] if p2 else 0.0

        diff = p1_rat - p2_rat
        if diff > 0.05:
            edge = "T1"
        elif diff < -0.05:
            edge = "T2"
        else:
            edge = "even"

        duels.append(PlayerDuel(
            role=role,
            t1_name=p1_name, t1_rating=p1_rat,
            t2_name=p2_name, t2_rating=p2_rat,
            edge=edge,
        ))
    return duels


# ── Main analyze function ─────────────────────────────────────────────────────

async def analyze(
    t1_name: str,
    t2_name: str,
    is_lan: bool = False,
    event_tier: str = "A",
    odds1: Optional[float] = None,
    odds2: Optional[float] = None,
    match_date: Optional[datetime] = None,
) -> tuple:
    """
    Run full deep analysis for t1 vs t2.
    Returns (AnalysisResult, error_str).  error_str is None on success.
    """
    from predictor import get_match_prediction  # avoid circular at module level

    # ── 1. Team lookup ────────────────────────────────────────────────────────
    t1 = resolve_team(t1_name)
    t2 = resolve_team(t2_name)
    if not t1:
        return None, f"Команда не найдена: '{t1_name}'"
    if not t2:
        return None, f"Команда не найдена: '{t2_name}'"

    t1_id, t2_id = t1["id"], t2["id"]
    t1_hltv_id = t1.get("hltv_id")
    t2_hltv_id = t2.get("hltv_id")

    result = AnalysisResult(
        t1_name=t1["name"], t2_name=t2["name"],
        t1_id=t1_id, t2_id=t2_id,
        is_lan=is_lan, event_tier=event_tier,
        t1_form_90d=0.5, t2_form_90d=0.5,
        t1_lan_form=0.5, t2_lan_form=0.5,
        t1_rank=t1.get("ranking"), t2_rank=t2.get("ranking"),
    )

    # ── 2. Form from DB ───────────────────────────────────────────────────────
    result.t1_form_90d = _form(t1_id, n=15)
    result.t2_form_90d = _form(t2_id, n=15)
    result.t1_lan_form = _form(t1_id, n=10, lan_only=True)
    result.t2_lan_form = _form(t2_id, n=10, lan_only=True)

    # ── 3. H2H from DB ───────────────────────────────────────────────────────
    h2h_matches = db.get_matches_between(t1_id, t2_id, days=365)
    result.h2h_t1_wins = sum(1 for m in h2h_matches if m["winner_id"] == t1_id)
    result.h2h_t2_wins = len(h2h_matches) - result.h2h_t1_wins
    result.h2h_total   = len(h2h_matches)

    recent_h2h = []
    for m in h2h_matches[:5]:
        winner_name = t1["name"] if m["winner_id"] == t1_id else t2["name"]
        recent_h2h.append({
            "date":    (m.get("date") or "")[:10],
            "winner":  winner_name,
            "event":   m.get("event") or "",
        })
    result.h2h_recent = recent_h2h

    # ── 4. Model prediction ───────────────────────────────────────────────────
    pred, err = get_match_prediction(t1["name"], t2["name"], is_lan=is_lan, event_tier=event_tier)
    if pred:
        result.model_t1_prob   = pred.team1_prob
        result.model_t2_prob   = pred.team2_prob
        result.model_confidence = pred.confidence
        result.model_version   = pred.model_version
    else:
        result.data_warning = err or "недостаточно данных для модели"

    # ── 5. Value bet (if odds provided) ──────────────────────────────────────
    if odds1 and odds2:
        vb1, vb2, verr = calculate_value_bet(t1["name"], t2["name"], odds1, odds2,
                                             is_lan=is_lan, event_tier=event_tier)
        if vb1 and vb2:
            result.value_bet = vb1 if (vb1.is_value and vb1.edge >= vb2.edge) else (vb2 if vb2.is_value else None)

    # ── 6. Live scraping (parallel) ──────────────────────────────────────────
    # We need hltv_id for live scraping; skip if not available
    scrape_tasks = {}
    if t1_hltv_id:
        scrape_tasks["t1_maps"]    = scrape_map_pool(t1_hltv_id, t1["name"])
        scrape_tasks["t1_players"] = scrape_player_stats(t1_hltv_id, t1["name"])
    if t2_hltv_id:
        scrape_tasks["t2_maps"]    = scrape_map_pool(t2_hltv_id, t2["name"])
        scrape_tasks["t2_players"] = scrape_player_stats(t2_hltv_id, t2["name"])

    scrape_tasks["bo3gg"] = scrape_bo3gg(t1["name"], t2["name"], match_date)

    keys = list(scrape_tasks.keys())
    gathered = await asyncio.gather(*[scrape_tasks[k] for k in keys], return_exceptions=True)
    live = {k: (v if not isinstance(v, Exception) else []) for k, v in zip(keys, gathered)}

    # ── 7. Map comparison ─────────────────────────────────────────────────────
    # Build dict: map_name → {wr, n} from live data (fallback to DB)
    def _map_dict(live_list: list, team_id: int) -> dict:
        d = {}
        for entry in live_list:
            d[entry["map_name"]] = {"wr": entry["win_pct"], "n": entry["times_played"]}
        # Fill missing maps from DB
        for m in VETO_MAPS:
            if m not in d:
                rows = db.get_map_results_for_team(team_id, m, limit=20)
                if rows:
                    wins = sum(1 for r in rows if r["winner_id"] == team_id)
                    d[m] = {"wr": wins / len(rows), "n": len(rows)}
        return d

    t1_mdict = _map_dict(live.get("t1_maps", []), t1_id)
    t2_mdict = _map_dict(live.get("t2_maps", []), t2_id)

    comparisons = []
    t1_permbans, t2_permbans = [], []

    for map_name in VETO_MAPS:
        t1_data = t1_mdict.get(map_name, {"wr": 0.5, "n": 0})
        t2_data = t2_mdict.get(map_name, {"wr": 0.5, "n": 0})
        t1_wr, t1_n = t1_data["wr"], t1_data["n"]
        t2_wr, t2_n = t2_data["wr"], t2_data["n"]

        is_t1_perma = _is_perma(t1_n)
        is_t2_perma = _is_perma(t2_n)
        if is_t1_perma:
            t1_permbans.append(map_name)
        if is_t2_perma:
            t2_permbans.append(map_name)

        edge = _map_edge(t1_wr, t1_n, t2_wr, t2_n)
        comparisons.append(MapComparison(
            map_name=map_name,
            t1_wr=t1_wr, t1_maps=t1_n,
            t2_wr=t2_wr, t2_maps=t2_n,
            edge=edge,
            is_t1_perma=is_t1_perma,
            is_t2_perma=is_t2_perma,
        ))

    result.map_comparison = comparisons
    result.veto_prediction = _predict_veto(
        t1["name"], t2["name"], t1_mdict, t2_mdict, t1_permbans, t2_permbans
    )

    # ── 8. Player comparison ──────────────────────────────────────────────────
    t1_players = live.get("t1_players", [])
    t2_players = live.get("t2_players", [])

    # Fallback to DB players if live scraping returned nothing
    if not t1_players:
        db_players = db.get_active_players(t1_id)
        t1_players = [{"name": p["name"], "rating": p.get("rating3") or 1.0,
                       "kast": p.get("kast") or 0.0, "kd": p.get("kd") or 1.0,
                       "adr": p.get("adr") or 0.0, "maps_played": 0}
                      for p in db_players]
        t1_players.sort(key=lambda x: -x["rating"])

    if not t2_players:
        db_players = db.get_active_players(t2_id)
        t2_players = [{"name": p["name"], "rating": p.get("rating3") or 1.0,
                       "kast": p.get("kast") or 0.0, "kd": p.get("kd") or 1.0,
                       "adr": p.get("adr") or 0.0, "maps_played": 0}
                      for p in db_players]
        t2_players.sort(key=lambda x: -x["rating"])

    result.player_comparison = _build_player_duels(t1_players, t2_players,
                                                    t1["name"], t2["name"])

    # ── 9. bo3.gg ────────────────────────────────────────────────────────────
    bo3 = live.get("bo3gg", {})
    if isinstance(bo3, dict):
        result.bo3gg_t1_pct   = bo3.get("t1_win_pct", 0.0)
        result.bo3gg_t2_pct   = bo3.get("t2_win_pct", 0.0)
        result.bo3gg_analysis = bo3.get("analysis_text", "нет данных")

    return result, None
