"""
Pure Python Glicko-2 rating system for CS2 teams.

Reference: Mark Glickman (2012) — http://www.glicko.net/glicko/glicko2.pdf

Usage:
    g = Glicko2()
    # single update: team A (rating=1500, rd=200, vol=0.06) beat team B (1400, 30)
    new_r, new_rd, new_vol = g.update(1500, 200, 0.06, [(1400, 30, 1)])
    # 0 = loss, 0.5 = draw, 1 = win
"""

import math
from typing import List, Tuple
from config import (GLICKO_INITIAL_RATING, GLICKO_INITIAL_RD,
                    GLICKO_INITIAL_VOLATILITY, GLICKO_TAU)


class Glicko2:
    def __init__(self, tau: float = GLICKO_TAU):
        self.tau = tau
        # Internal scale factor (converts from public scale to Glicko-2 internal)
        self._q = math.log(10) / 400

    # ── Public scale ↔ internal scale ───────────────────────────────────────
    def _to_internal(self, rating: float, rd: float):
        mu = (rating - GLICKO_INITIAL_RATING) / 173.7178
        phi = rd / 173.7178
        return mu, phi

    def _to_public(self, mu: float, phi: float):
        rating = mu * 173.7178 + GLICKO_INITIAL_RATING
        rd = phi * 173.7178
        return rating, rd

    # ── Core Glicko-2 functions ──────────────────────────────────────────────
    def _g(self, phi: float) -> float:
        return 1.0 / math.sqrt(1 + 3 * phi**2 / math.pi**2)

    def _E(self, mu: float, mu_j: float, phi_j: float) -> float:
        return 1.0 / (1 + math.exp(-self._g(phi_j) * (mu - mu_j)))

    def update(
        self,
        rating: float,
        rd: float,
        volatility: float,
        opponents: List[Tuple[float, float, float]],
        # opponents = list of (opp_rating, opp_rd, score) — score: 1=win, 0=loss, 0.5=draw
    ) -> Tuple[float, float, float]:
        """
        Returns updated (rating, rd, volatility) in public Glicko scale.
        If opponents is empty (no games this period), only RD increases.
        """
        mu, phi = self._to_internal(rating, rd)
        sigma = volatility

        if not opponents:
            phi_star = math.sqrt(phi**2 + sigma**2)
            new_r, new_rd = self._to_public(mu, phi_star)
            return new_r, new_rd, sigma

        # Step 3: compute v (estimated variance)
        v_inv = 0.0
        delta_sum = 0.0
        for opp_r, opp_rd, score in opponents:
            mu_j, phi_j = self._to_internal(opp_r, opp_rd)
            g_j = self._g(phi_j)
            E_j = self._E(mu, mu_j, phi_j)
            v_inv += g_j**2 * E_j * (1 - E_j)
            delta_sum += g_j * (score - E_j)

        v = 1.0 / v_inv
        delta = v * delta_sum

        # Step 5: update volatility (Illinois algorithm)
        a = math.log(sigma**2)
        A = a
        epsilon = 1e-6

        def f(x: float) -> float:
            ex = math.exp(x)
            tmp = phi**2 + v + ex
            return (ex * (delta**2 - tmp) / (2 * tmp**2)) - ((x - a) / self.tau**2)

        B = math.log(delta**2 - phi**2 - v) if delta**2 > phi**2 + v else a - self.tau
        fA, fB = f(A), f(B)

        while abs(B - A) > epsilon:
            C = A + (A - B) * fA / (fB - fA)
            fC = f(C)
            if fC * fB < 0:
                A, fA = B, fB
            else:
                fA /= 2
            B, fB = C, fC

        new_sigma = math.exp(A / 2)

        # Step 6: update RD
        phi_star = math.sqrt(phi**2 + new_sigma**2)
        phi_prime = 1.0 / math.sqrt(1.0 / phi_star**2 + 1.0 / v)

        # Step 7: update rating
        mu_prime = mu + phi_prime**2 * delta_sum

        new_rating, new_rd = self._to_public(mu_prime, phi_prime)
        return new_rating, new_rd, new_sigma

    def win_probability(self, r1: float, rd1: float, r2: float, rd2: float) -> float:
        """
        Returns P(team1 wins) based on current ratings.
        Uses the Glicko-2 expected score formula.
        """
        mu1, phi1 = self._to_internal(r1, rd1)
        mu2, phi2 = self._to_internal(r2, rd2)
        combined_phi = math.sqrt(phi1**2 + phi2**2)
        return self._E(mu1, mu2, combined_phi)


# ── Batch rating computation ────────────────────────────────────────────────

def compute_ratings_from_history(match_history: list, context: str = "overall") -> dict:
    """
    Computes Glicko-2 ratings for all teams from a sorted list of match dicts.

    match_history: list of dicts sorted by date ASC, each with:
        {team1_id, team2_id, winner_id, date, is_lan}
        (for lan_only context, only LAN matches are used)

    Returns: {team_id: {"rating": ..., "rd": ..., "volatility": ..., "matches": ...}}
    """
    g = Glicko2()
    ratings = {}  # team_id → {r, rd, vol, games_this_period, pending_results}

    def get_r(team_id):
        if team_id not in ratings:
            ratings[team_id] = {
                "r": GLICKO_INITIAL_RATING,
                "rd": GLICKO_INITIAL_RD,
                "vol": GLICKO_INITIAL_VOLATILITY,
                "matches": 0,
                "pending": [],   # (opp_r, opp_rd, score) within current period
                "period_start": None,
            }
        return ratings[team_id]

    from config import GLICKO_RATING_PERIOD_DAYS
    from datetime import datetime, timedelta

    def flush_period(team_id):
        """Apply all pending results and reset period."""
        r = ratings[team_id]
        if not r["pending"]:
            # No games — only RD increases
            _, new_rd, _ = g.update(r["r"], r["rd"], r["vol"], [])
            r["rd"] = new_rd
        else:
            new_r, new_rd, new_vol = g.update(r["r"], r["rd"], r["vol"], r["pending"])
            r["r"] = new_r
            r["rd"] = new_rd
            r["vol"] = new_vol
        r["pending"] = []
        r["period_start"] = None

    current_period_end = None

    for match in match_history:
        if context == "lan_only" and not match.get("is_lan"):
            continue

        t1, t2 = match["team1_id"], match["team2_id"]
        winner = match["winner_id"]
        date_str = match.get("date", "")

        try:
            match_date = datetime.fromisoformat(date_str[:10])
        except (ValueError, TypeError):
            continue

        get_r(t1)
        get_r(t2)

        # Flush periods if needed
        if current_period_end is None:
            current_period_end = match_date + timedelta(days=GLICKO_RATING_PERIOD_DAYS)

        if match_date > current_period_end:
            # Flush all teams
            for tid in list(ratings.keys()):
                flush_period(tid)
            current_period_end = match_date + timedelta(days=GLICKO_RATING_PERIOD_DAYS)

        score1 = 1.0 if winner == t1 else 0.0
        score2 = 1.0 - score1

        # Use current ratings as opponent ratings for this period
        ratings[t1]["pending"].append((ratings[t2]["r"], ratings[t2]["rd"], score1))
        ratings[t2]["pending"].append((ratings[t1]["r"], ratings[t1]["rd"], score2))
        ratings[t1]["matches"] += 1
        ratings[t2]["matches"] += 1

    # Final flush
    for tid in list(ratings.keys()):
        flush_period(tid)

    return {
        tid: {
            "rating": round(v["r"], 2),
            "rd": round(v["rd"], 2),
            "volatility": round(v["vol"], 6),
            "matches": v["matches"],
        }
        for tid, v in ratings.items()
    }
