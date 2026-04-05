"""
Retroactive backtest on Jan 31 – Apr 5, 2026.
Parses match_list_raw.txt, runs calculate_value_bet() for each match,
and reports: model fav accuracy, value-bet WR, PnL (Kelly%).

Format of match_list_raw.txt (from bo3.gg betting history):
  Team1
  <T1 actual score>
   -
  <T2 actual score>
  Team2
  <pred_side: 1=T1 picked, 2=T2 picked>
  <pred_result>
  <odds for picked team>
  $<payout>
  <tournament>
"""

import sys, os, re
sys.path.insert(0, os.path.dirname(__file__))

from predictor import calculate_value_bet

# -- Team name normalisation ----------------------------------------------------
ALIASES = {
    "Natus Vincere": "Natus Vincere",
    "NAVI": "Natus Vincere",
    "NaVi": "Natus Vincere",
    "Ninjas in Pyjamas": "Ninjas in Pyjamas",
    "NiP": "Ninjas in Pyjamas",
    "The MongolZ": "The MongolZ",
    "MongolZ": "The MongolZ",
    "Gaimin Gladiators": "Gaimin Gladiators",
    "SemperFi": "SemperFi",
    "Passion UA": "Passion UA",
    "Gentle Mates": "Gentle Mates",
    "Inner Circle": "Inner Circle",
    "Voca": "Voca",
    "BC.Game": "BC.Game",
    "9INE": "9INE",
    "Nemesis": "Nemesis",
    "EYEBALLERS": "EYEBALLERS",
    "FOKUS": "FOKUS",
    "Wildcard": "Wildcard",
}

def norm(name: str) -> str:
    return ALIASES.get(name, name)


# -- Parse match_list_raw.txt ----------------------------------------------------

SKIP_LINES = {
    "Полные", "a-тир", "s-тир",
    "Время", "Данные", "Матч", "Прогноз",
    "Потенциальныи Выигрыш", "Турнир", "FF",
}

RUSSIAN_MONTHS = {
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
    "март", "апрель", "февраль", "январь",
}

def is_date_line(line: str) -> bool:
    parts = line.lower().split()
    if any(m in RUSSIAN_MONTHS for m in parts):
        return True
    if line.startswith("сегодня") or line.startswith("вчера"):
        return True
    return False

def is_time_line(line: str) -> bool:
    return bool(re.match(r'^\d{1,2}:\d{2}$', line.strip()))

def is_score(line: str) -> bool:
    return line.strip() in ("0", "1", "2", "3")

def is_separator(line: str) -> bool:
    return line.strip() == "-"

def is_pred_side(line: str) -> bool:
    return line.strip() in ("1", "2")

def is_pred_result(line: str) -> bool:
    # "2 - 0", "1 - 2", "3 - 2", "0 - 2" etc.
    return bool(re.match(r'^\d\s*-\s*\d$', line.strip()))

def is_odds(line: str) -> bool:
    try:
        v = float(line.strip())
        return 1.0 < v < 30.0
    except ValueError:
        return False

def is_payout(line: str) -> bool:
    return line.strip().startswith("$")

def is_tournament(line: str) -> bool:
    keywords = ("ESL", "BLAST", "PGL", "IEM", "Stake", "HLTV", "ESEA", "CCT",
                "FACEIT", "Katowice", "Krakow", "Cluj", "Bucharest", "Rotterdam",
                "Copenhagen", "Valencia", "Stage", "Season", "Episode", "Spring",
                "Summer", "Fall", "Winter", "Major")
    return any(k in line for k in keywords)


def parse_matches(filepath: str) -> list:
    with open(filepath, encoding="utf-8") as f:
        raw_lines = [ln.rstrip("\n") for ln in f.readlines()]

    # Strip, skip blank
    lines = [l.strip() for l in raw_lines]

    matches = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # Skip known header/decoration lines
        if (not line or line in SKIP_LINES or is_date_line(line)
                or is_time_line(line)):
            i += 1
            continue

        # Try to match a block: T1 / score / " - " / score / T2 / pred / pred_result
        # We need: current = T1 candidate, next = score, next+1 = "-", next+2 = score, next+3 = T2
        if (i + 4 < n
                and is_score(lines[i + 1])
                and is_separator(lines[i + 2])
                and is_score(lines[i + 3])
                and lines[i + 4].strip()
                and not is_score(lines[i + 4])
                and not is_separator(lines[i + 4])
                and not is_time_line(lines[i + 4])):

            t1 = line
            t1_score = int(lines[i + 1])
            t2_score = int(lines[i + 3])
            t2 = lines[i + 4]

            # After T2: pred_side, pred_result, odds, [$payout], tournament
            j = i + 5

            # Skip if FF or no following lines
            if j >= n:
                i += 1
                continue

            # pred_side
            pred_side = None
            if j < n and is_pred_side(lines[j]):
                pred_side = int(lines[j])
                j += 1
            else:
                i += 1
                continue

            # pred_result
            pred_result = None
            if j < n and is_pred_result(lines[j]):
                pred_result = lines[j]
                j += 1

            # odds
            odds = None
            if j < n and is_odds(lines[j]):
                odds = float(lines[j])
                j += 1

            # payout ($xxx)
            if j < n and is_payout(lines[j]):
                j += 1

            # tournament
            tournament = ""
            if j < n and lines[j]:
                tournament = lines[j]

            if odds is not None:
                matches.append({
                    "t1": norm(t1),
                    "t2": norm(t2),
                    "t1_score": t1_score,
                    "t2_score": t2_score,
                    "t1_won": t1_score > t2_score,
                    "pred_side": pred_side,   # 1 = T1 picked at these odds, 2 = T2
                    "odds_picked": odds,       # odds for the picked team
                    "tournament": tournament,
                })

            i = j + 1
        else:
            i += 1

    return matches


# -- Bookmaker margin estimate ----------------------------------------------------

def est_odds2(o1: float, margin: float = 0.055) -> float:
    """Estimate T2 odds given T1 odds and bookmaker margin."""
    denom = 1.0 + margin - 1.0 / o1
    if denom <= 0:
        return None
    return round(1.0 / denom, 3)


# -- Backtest ---------------------------------------------------------------------

def determine_tier(tournament: str) -> str:
    t = tournament.lower()
    if any(k in t for k in ("blast open spring", "esl pro league", "iem")):
        return "S"
    return "A"

def run_backtest(matches: list):
    total = 0
    fav_correct = 0
    fav_total = 0

    vb_total = 0
    vb_correct = 0
    vb_pnl = 0.0  # Kelly% PnL (fraction of bankroll)

    errors = []
    skipped = 0

    print(f"\n{'='*70}")
    print(f"RETROACTIVE BACKTEST — Jan 31 – Apr 5, 2026")
    print(f"{'='*70}\n")

    tournament_stats: dict[str, dict] = {}

    for m in matches:
        t1, t2 = m["t1"], m["t2"]
        pred_side = m["pred_side"]
        odds_picked = m["odds_picked"]
        t1_won = m["t1_won"]
        tournament = m["tournament"]
        tier = determine_tier(tournament)
        is_lan = True  # all these are LAN events

        # Build odds1, odds2
        if pred_side == 1:
            odds1 = odds_picked
            odds2 = est_odds2(odds1)
        else:
            odds2 = odds_picked
            odds1 = est_odds2(odds2)

        if odds1 is None or odds2 is None:
            skipped += 1
            continue

        vb1, vb2, err = calculate_value_bet(t1, t2, odds1, odds2, is_lan=is_lan, event_tier=tier)
        if err:
            errors.append(f"  [{t1} vs {t2}] {err}")
            skipped += 1
            continue

        total += 1

        # Track by tournament
        if tournament not in tournament_stats:
            tournament_stats[tournament] = {"total": 0, "fav_c": 0, "fav_t": 0,
                                             "vb_t": 0, "vb_c": 0, "pnl": 0.0}
        ts = tournament_stats[tournament]
        ts["total"] += 1

        # Model favourite accuracy
        model_fav_t1 = vb1.model_prob >= vb2.model_prob
        model_fav_won = (model_fav_t1 and t1_won) or (not model_fav_t1 and not t1_won)
        fav_total += 1
        ts["fav_t"] += 1
        if model_fav_won:
            fav_correct += 1
            ts["fav_c"] += 1

        # Value bet tracking
        for vb in (vb1, vb2):
            if not vb.is_value:
                continue

            bet_on_t1 = (vb.bet_on == t1)
            bet_won = (bet_on_t1 and t1_won) or (not bet_on_t1 and not t1_won)

            vb_total += 1
            ts["vb_t"] += 1
            pnl_this = vb.kelly_safe * (vb.odds - 1) if bet_won else -vb.kelly_safe
            vb_pnl += pnl_this
            ts["pnl"] += pnl_this

            result_str = "WIN " if bet_won else "LOSS"
            if vb_total <= 50:  # print first 50 value bets detail
                print(f"  {result_str} | {vb.bet_on:25s} @{vb.odds:.2f} "
                      f"edge={vb.edge:+.1%} kelly={vb.kelly_safe:.1%} "
                      f"pnl={pnl_this:+.2%} | {t1} vs {t2} | {tournament}")
            if bet_won:
                vb_correct += 1
                ts["vb_c"] += 1

    # -- Summary ----------------------------------------------------------------
    print(f"\n{'='*70}")
    print(f"OVERALL RESULTS  [NOTE: may overlap with training data - see warning]")
    print(f"{'='*70}")
    print(f"Matches processed:  {total}  (skipped: {skipped})")
    print(f"Model fav accuracy: {fav_correct}/{fav_total} = "
          f"{fav_correct/fav_total:.1%}" if fav_total else "Model fav accuracy: n/a")
    print(f"Value bets:         {vb_correct}/{vb_total} = "
          f"{vb_correct/vb_total:.1%}" if vb_total else "Value bets: 0")
    print(f"PnL (Kelly%):       {vb_pnl:+.2%}")

    print(f"\n{'-'*70}")
    print(f"BY TOURNAMENT")
    print(f"{'-'*70}")
    lines_out = []
    for tn, ts in sorted(tournament_stats.items(), key=lambda x: -x[1]["total"]):
        fav_str = (f"{ts['fav_c']}/{ts['fav_t']}={ts['fav_c']/ts['fav_t']:.0%}"
                   if ts["fav_t"] else "n/a")
        vb_c_val = ts.get("vb_c", 0)
        vb_t_val = ts.get("vb_t", 0)
        vb_str2 = (f"VB {vb_c_val}/{vb_t_val}={vb_c_val/vb_t_val:.0%} PnL={ts['pnl']:+.2%}"
                   if vb_t_val else "VB 0")
        tn_safe = tn.encode("ascii", "replace").decode("ascii")
        lines_out.append(f"  {tn_safe:<45s} | fav {fav_str} | {vb_str2}")
    for line in lines_out:
        print(line)

    if errors:
        print(f"\n{'-'*70}")
        print(f"TEAM LOOKUP ERRORS ({len(errors)}):")
        for e in errors[:20]:
            print(e)
        if len(errors) > 20:
            print(f"  ... and {len(errors)-20} more")

    return {
        "total": total,
        "fav_accuracy": fav_correct / fav_total if fav_total else None,
        "vb_wr": vb_correct / vb_total if vb_total else None,
        "vb_pnl": vb_pnl,
        "vb_count": vb_total,
    }


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.WARNING)  # suppress INFO spam

    base = os.path.dirname(__file__)
    raw_files = [
        os.path.join(base, "match_list_raw.txt"),
        os.path.join(base, "match_list_raw2.txt"),
    ]

    all_matches_raw = []
    for f in raw_files:
        if os.path.exists(f):
            all_matches_raw.extend(parse_matches(f))

    # Deduplicate by (t1, t2, t1_score, t2_score, tournament[:20])
    seen = set()
    matches = []
    for m in all_matches_raw:
        key = (m["t1"], m["t2"], m["t1_score"], m["t2_score"], m["tournament"][:25])
        if key not in seen:
            seen.add(key)
            matches.append(m)

    print(f"Parsed {len(matches)} unique matches (from {len(all_matches_raw)} total across {len(raw_files)} files)")

    # Quick sanity check — show first 5
    print("\nFirst 5 matches:")
    for m in matches[:5]:
        won_str = "T1 won" if m["t1_won"] else "T2 won"
        print(f"  {m['t1']:20s} {m['t1_score']}-{m['t2_score']} {m['t2']:20s} "
              f"pred={m['pred_side']} odds={m['odds_picked']} [{won_str}]")

    results = run_backtest(matches)