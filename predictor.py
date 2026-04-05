"""
High-level prediction interface for CS2 bot.

Combines match + map predictions with value bet calculation.
Main entry point for Telegram bot commands.
"""

import logging
from typing import Optional
from dataclasses import dataclass, field

import database as db
from model import predict_match, predict_map, get_model_meta
from config import (VALUE_EDGE_THRESHOLD, KELLY_FRACTION,
                    MIN_BET_PROB, MIN_ODDS_THRESHOLD, MAX_ODDS_THRESHOLD, MAX_BET_BANKROLL_PCT)

logger = logging.getLogger(__name__)


@dataclass
class MatchPrediction:
    team1_name: str
    team2_name: str
    team1_prob: float
    team2_prob: float
    confidence: float
    favorite: str
    favorite_prob: float
    model_version: str
    maps: list = field(default_factory=list)   # list of MapPrediction
    data_warning: str = ""


@dataclass
class MapPrediction:
    map_name: str
    map_order: int
    team1_prob: float
    team2_prob: float
    confidence: float
    favorite: str


@dataclass
class ValueBet:
    team1_name: str
    team2_name: str
    bet_on: str        # team name to bet on
    model_prob: float
    bookmaker_prob: float
    edge: float
    odds: float
    kelly_full: float
    kelly_safe: float  # 1/4 Kelly, capped at MAX_BET_BANKROLL_PCT
    ev_pct: float      # expected value % = (model_prob * odds - 1) * 100
    is_value: bool


# ── Team resolution ───────────────────────────────────────────────────────────

def resolve_team(name: str) -> Optional[dict]:
    """Fuzzy-find team by name. Returns team dict or None."""
    team = db.get_team_by_name(name)
    return team


def _teams_or_error(t1_name: str, t2_name: str):
    t1 = resolve_team(t1_name)
    t2 = resolve_team(t2_name)
    errors = []
    if not t1:
        errors.append(f"Team not found: '{t1_name}'")
    if not t2:
        errors.append(f"Team not found: '{t2_name}'")
    return t1, t2, errors


# ── Core prediction ───────────────────────────────────────────────────────────

def get_match_prediction(t1_name: str, t2_name: str,
                         is_lan: bool = False,
                         event_tier: str = "A",
                         map_names: list = None) -> tuple:
    """
    Returns (MatchPrediction, error_str).
    error_str is None on success.
    """
    t1, t2, errors = _teams_or_error(t1_name, t2_name)
    if errors:
        return None, "\n".join(errors)

    result = predict_match(t1["id"], t2["id"], is_lan, event_tier)
    if result is None:
        return None, (
            f"Not enough data to predict. One or both teams need at least 5 matches in the database.\n"
            f"Run /bootstrap to collect HLTV data first."
        )

    p1, p2 = result["team1_prob"], result["team2_prob"]
    fav = t1["name"] if p1 >= p2 else t2["name"]
    fav_prob = max(p1, p2)

    # Map predictions
    map_preds = []
    if map_names:
        for i, mn in enumerate(map_names):
            mp = predict_map(t1["id"], t2["id"], mn, is_lan, event_tier)
            if mp:
                mfav = t1["name"] if mp["team1_prob"] >= mp["team2_prob"] else t2["name"]
                map_preds.append(MapPrediction(
                    map_name=mn,
                    map_order=i + 1,
                    team1_prob=mp["team1_prob"],
                    team2_prob=mp["team2_prob"],
                    confidence=mp["confidence"],
                    favorite=mfav,
                ))

    pred = MatchPrediction(
        team1_name=t1["name"],
        team2_name=t2["name"],
        team1_prob=p1,
        team2_prob=p2,
        confidence=result["confidence"],
        favorite=fav,
        favorite_prob=fav_prob,
        model_version=result["model_version"],
        maps=map_preds,
    )
    return pred, None


def calculate_value_bet(t1_name: str, t2_name: str,
                        odds1: float, odds2: float,
                        is_lan: bool = False,
                        event_tier: str = "A") -> tuple:
    """
    Calculate value bet given bookmaker odds.
    Returns (ValueBet for team1, ValueBet for team2, error_str).
    """
    t1, t2, errors = _teams_or_error(t1_name, t2_name)
    if errors:
        return None, None, "\n".join(errors)

    result = predict_match(t1["id"], t2["id"], is_lan, event_tier)
    if result is None:
        return None, None, "Not enough data for prediction. Collect more HLTV data first."

    p1, p2 = result["team1_prob"], result["team2_prob"]

    def _vb(team_name, model_prob, odds) -> ValueBet:
        bm_prob = 1.0 / odds if odds > 1 else 0.5
        edge = model_prob - bm_prob
        kelly = edge / (odds - 1) if odds > 1 else 0.0
        ev_pct = (model_prob * odds - 1.0) * 100.0
        is_value = (
            edge >= VALUE_EDGE_THRESHOLD
            and model_prob >= MIN_BET_PROB
            and MIN_ODDS_THRESHOLD <= odds <= MAX_ODDS_THRESHOLD
        )
        kelly_safe = min(max(kelly * KELLY_FRACTION, 0.0), MAX_BET_BANKROLL_PCT)
        return ValueBet(
            team1_name=t1["name"],
            team2_name=t2["name"],
            bet_on=team_name,
            model_prob=round(model_prob, 4),
            bookmaker_prob=round(bm_prob, 4),
            edge=round(edge, 4),
            odds=odds,
            kelly_full=round(max(kelly, 0.0), 4),
            kelly_safe=round(kelly_safe, 4),
            ev_pct=round(ev_pct, 2),
            is_value=is_value,
        )

    vb1 = _vb(t1["name"], p1, odds1)
    vb2 = _vb(t2["name"], p2, odds2)
    return vb1, vb2, None


# ── Formatting ────────────────────────────────────────────────────────────────

def _conf_bar(confidence: float) -> str:
    """Visual confidence bar: ████░░░░░░ (10 blocks)."""
    filled = round(confidence * 10)
    return "█" * filled + "░" * (10 - filled)


def format_match_prediction(pred: MatchPrediction) -> str:
    """Format MatchPrediction to Telegram-ready text."""
    lines = [
        f"⚔️ {pred.team1_name} vs {pred.team2_name}",
        f"",
        f"🏆 Фаворит: {pred.favorite} ({pred.favorite_prob:.0%})",
        f"📊 {pred.team1_name}: {pred.team1_prob:.0%} | {pred.team2_name}: {pred.team2_prob:.0%}",
        f"🎯 Уверенность: {_conf_bar(pred.confidence)} {pred.confidence:.0%}",
    ]
    if pred.data_warning:
        lines.append(f"⚠️ {pred.data_warning}")
    if pred.maps:
        lines.append("")
        lines.append("🗺️ По картам:")
        for mp in pred.maps:
            lines.append(
                f"  [{mp.map_order}] {mp.map_name}: "
                f"{pred.team1_name} {mp.team1_prob:.0%} | "
                f"{pred.team2_name} {mp.team2_prob:.0%} "
                f"→ {mp.favorite}"
            )
    lines.append(f"\n_Модель v{pred.model_version}_")
    return "\n".join(lines)


def format_value_bet(vb1: ValueBet, vb2: ValueBet) -> str:
    """Format ValueBet pair to Telegram text."""
    lines = [f"💰 Анализ ставки: {vb1.team1_name} vs {vb1.team2_name}", ""]

    for vb in (vb1, vb2):
        tag = "✅ VALUE" if vb.is_value else "❌ no edge"
        lines.append(f"{vb.bet_on} @ {vb.odds:.2f} — {tag}")
        lines.append(f"  Модель: {vb.model_prob:.0%} | Бук: {vb.bookmaker_prob:.0%} | Edge: {vb.edge:+.1%} | EV: {vb.ev_pct:+.1f}%")
        if vb.is_value:
            lines.append(f"  Kelly: {vb.kelly_full:.1%} полный | {vb.kelly_safe:.1%} безопасный (1/4 Kelly, cap 3%)")
        lines.append("")

    best = vb1 if (vb1.is_value and vb1.edge >= vb2.edge) else (vb2 if vb2.is_value else None)
    if best:
        lines.append(f"⭐ Рекомендация: {best.bet_on} @ {best.odds:.2f}")
        lines.append(f"   Ставь {best.kelly_safe:.1%} банка")
    else:
        lines.append("🚫 Нет value ставок в этом матче")
    return "\n".join(lines)


def format_today_matches(upcoming: list) -> str:
    """Format list of upcoming match dicts with predictions."""
    if not upcoming:
        return "Сегодня матчей нет."
    lines = ["📅 Матчи на сегодня:", ""]
    for m in upcoming:
        t1_id = m["team1_id"]
        t2_id = m["team2_id"]
        result = predict_match(t1_id, t2_id, bool(m.get("is_lan")),
                               m.get("event_tier", "A") or "A")
        date_str = (m.get("date") or "")[:16].replace("T", " ")
        if result:
            fav = m["team1_name"] if result["team1_prob"] >= 0.5 else m["team2_name"]
            fav_p = max(result["team1_prob"], result["team2_prob"])
            lines.append(
                f"• {m['team1_name']} vs {m['team2_name']} [{date_str}]\n"
                f"  → {fav} {fav_p:.0%} | уверенность {result['confidence']:.0%}"
            )
        else:
            lines.append(
                f"• {m['team1_name']} vs {m['team2_name']} [{date_str}]\n"
                f"  → нет данных для прогноза"
            )
        lines.append("")
    return "\n".join(lines)


def format_history(history: list, stats: dict) -> str:
    """Format prediction history."""
    lines = [
        f"📈 История прогнозов",
        f"Точность: {stats['accuracy']}% ({stats['wins']}/{stats['total']})",
        "",
    ]
    for p in history[:15]:
        result_icon = "✅" if p["correct"] == 1 else "❌"
        lines.append(
            f"{result_icon} {p['team1_name']} vs {p['team2_name']} — "
            f"{p['team1_name']} {p['team1_prob']:.0%}"
        )
    return "\n".join(lines)


def format_deep_analysis(result) -> list[str]:
    """
    Format AnalysisResult into 1-3 Telegram messages (each ≤ 4096 chars).
    Returns a list of message strings.
    """
    t1 = result.t1_name
    t2 = result.t2_name

    # ── Message 1: Header + Form + Maps ──────────────────────────────────────
    ctx_parts = []
    if result.is_lan:
        ctx_parts.append("LAN")
    if result.event_tier:
        ctx_parts.append(f"Tier {result.event_tier}")
    ctx_str = " | ".join(ctx_parts) if ctx_parts else "Online"

    rank_t1 = f"#{result.t1_rank}" if result.t1_rank else "N/A"
    rank_t2 = f"#{result.t2_rank}" if result.t2_rank else "N/A"

    msg1 = [
        f"АНАЛИЗ: {t1} vs {t2}",
        f"{ctx_str}",
        "",
        f"ФОРМА (последние матчи)",
        f"{t1}: {result.t1_form_90d:.0%} побед | {t2}: {result.t2_form_90d:.0%} побед",
        f"Ранг HLTV: {t1} {rank_t1} | {t2} {rank_t2}",
        f"LAN форма: {t1} {result.t1_lan_form:.0%} | {t2} {result.t2_lan_form:.0%}",
        "",
        f"КАРТЫ",
    ]

    # Map table header
    msg1.append(f"{'Карта':<12} {t1[:8]:<10} {t2[:8]:<10} Итог")
    msg1.append("—" * 44)

    for mc in result.map_comparison:
        t1_str = f"{mc.t1_wr:.0%} {mc.t1_maps}м" if not mc.is_t1_perma else "бан"
        t2_str = f"{mc.t2_wr:.0%} {mc.t2_maps}м" if not mc.is_t2_perma else "бан"

        edge_str = mc.edge
        if edge_str == "T1 EDGE":
            edge_str = f"{t1[:6]} ✓"
        elif edge_str == "T2 EDGE":
            edge_str = f"{t2[:6]} ✓"
        elif edge_str in ("no_data", "no_data_t1", "no_data_t2"):
            edge_str = "—"

        if mc.is_t1_perma and mc.is_t2_perma:
            edge_str = "обе бан"
        elif mc.is_t1_perma:
            edge_str = f"{t2[:6]}"
        elif mc.is_t2_perma:
            edge_str = f"{t1[:6]}"

        msg1.append(f"{mc.map_name:<12} {t1_str:<10} {t2_str:<10} {edge_str}")

    msg1 += [
        "",
        "Прогноз вето:",
        result.veto_prediction,
    ]

    # ── Message 2: Players + H2H + bo3.gg ────────────────────────────────────
    msg2 = [f"ИГРОКИ: {t1} vs {t2}", ""]

    if result.player_comparison:
        msg2.append(f"{'Роль':<14} {t1[:10]:<12} Рейт  {t2[:10]:<12} Рейт  Итог")
        msg2.append("—" * 58)
        for pd in result.player_comparison:
            edge_icon = ("→ T1" if pd.edge == "T1" else
                         "→ T2" if pd.edge == "T2" else "→ =")
            t1_r = f"{pd.t1_rating:.2f}" if pd.t1_rating else "—"
            t2_r = f"{pd.t2_rating:.2f}" if pd.t2_rating else "—"
            msg2.append(
                f"{pd.role:<14} {pd.t1_name[:10]:<12} {t1_r:<6}"
                f"{pd.t2_name[:10]:<12} {t2_r:<6} {edge_icon}"
            )
    else:
        msg2.append("нет данных по игрокам")

    msg2 += [""]

    # H2H
    msg2.append("H2H (12 мес)")
    if result.h2h_total > 0:
        msg2.append(f"{t1} {result.h2h_t1_wins} - {result.h2h_t2_wins} {t2} ({result.h2h_total} матчей)")
        for m in result.h2h_recent[:4]:
            msg2.append(f"  {m['date']} — {m['winner']} ({m['event'][:25]})")
    else:
        msg2.append("Нет встреч за последний год")

    msg2 += [""]

    # bo3.gg
    msg2.append("АНАЛИТИКА (bo3.gg)")
    if result.bo3gg_t1_pct > 0 or result.bo3gg_t2_pct > 0:
        msg2.append(f"Прогноз: {t1} {result.bo3gg_t1_pct:.0%} | {t2} {result.bo3gg_t2_pct:.0%}")
    if result.bo3gg_analysis and result.bo3gg_analysis != "нет данных":
        # Truncate analysis text to 300 chars
        analysis = result.bo3gg_analysis[:300]
        if len(result.bo3gg_analysis) > 300:
            analysis += "..."
        msg2.append(analysis)
    else:
        msg2.append("нет данных")

    # ── Message 3: Model + Value ──────────────────────────────────────────────
    msg3 = [f"ИТОГ МОДЕЛИ: {t1} vs {t2}", ""]

    if result.data_warning:
        msg3.append(f"Предупреждение: {result.data_warning}")
        msg3.append("")

    msg3 += [
        f"{t1}: {result.model_t1_prob:.0%} | {t2}: {result.model_t2_prob:.0%}",
        f"Уверенность: {_conf_bar(result.model_confidence)} {result.model_confidence:.0%}",
        f"Ранги: {t1} {rank_t1} vs {t2} {rank_t2}",
        "",
    ]

    if result.value_bet:
        vb = result.value_bet
        tag = "VALUE" if vb.is_value else "нет edge"
        msg3 += [
            "СТАВКА",
            f"{vb.bet_on} @ {vb.odds:.2f} → edge {vb.edge:+.1%} {'✓' if vb.is_value else '✗'}  [{tag}]",
            f"Модель: {vb.model_prob:.0%} | Бук: {vb.bookmaker_prob:.0%}",
        ]
        if vb.is_value:
            msg3.append(f"Kelly безопасный: {vb.kelly_safe:.1%} банка")
    else:
        msg3.append("(введи коэффициенты для value-анализа)")

    msg3 += ["", f"Модель v{result.model_version}"]

    # Convert to strings and return
    return ["\n".join(msg1), "\n".join(msg2), "\n".join(msg3)]


def format_map_pool(team_name: str, team_id: int) -> str:
    """Format team's map pool stats."""
    from config import CS2_MAPS
    from feature_engineer import _map_win_rate
    lines = [f"🗺️ Пул карт: {team_name}", ""]
    map_stats = []
    for mn in CS2_MAPS:
        wr = _map_win_rate(team_id, mn)
        # Only show maps with at least some data (not exactly 0.5 default)
        from database import get_map_results_for_team
        played = len(get_map_results_for_team(team_id, mn, limit=5))
        if played > 0:
            map_stats.append((mn, wr, played))

    map_stats.sort(key=lambda x: -x[1])
    for mn, wr, played in map_stats:
        bar = "█" * round(wr * 10) + "░" * (10 - round(wr * 10))
        lines.append(f"  {mn:<12} {bar} {wr:.0%} ({played} plays)")

    if not map_stats:
        lines.append("Нет данных по картам.")
    return "\n".join(lines)
