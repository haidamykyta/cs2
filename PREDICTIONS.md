# CS2 Predictions Log

Tracking all predictions to measure model accuracy and calibrate future estimates.

## Format
```
DATE | MATCH | TOURNAMENT | FORMAT | OUR_PROB | BOOKMAKER_ODDS | EDGE | BET | RESULT | CORRECT
```

---

## 2026-03-21 — BLAST Open Spring 2026 (Rotterdam, LAN, Tier 1)

### Match 1: NiP vs Liquid
**Time:** 12:00 | **Format:** BO3 | **Bracket:** Lower QF

**Data used:**
- HLTV lineups + full map stats (pick%, ban%, win%, played)
- bo3.gg analyst page (Liquid 65% favourite per analysts)
- Manual veto math

**Map Pool Analysis:**
| Map     | NiP W%  | NiP N | Liquid W% | Liquid N | Edge       |
|---------|---------|-------|-----------|----------|------------|
| Nuke    | 71%     | 17    | 29%       | 7        | NiP ★★     |
| Dust2   | 58%     | 12    | 40%       | 5        | NiP        |
| Ancient | 63%     | 8     | 25%       | 4        | NiP        |
| Mirage  | 56%     | 9     | 38%       | 8        | NiP slight |
| Anubis  | 50%     | 4     | 50%       | 4        | Even       |
| Inferno | 33%     | 6     | 62%       | 13       | Liquid ★   |
| Vertigo | 33%     | 6     | 42%       | 12       | Liquid     |

**Veto prediction (BO3):**
- NiP bans: Inferno (Liquid's best, 62% WR)
- Liquid bans: Nuke (NiP's best, 71% WR)
- NiP picks: Dust2 or Ancient
- Liquid picks: Vertigo (NiP 33% there)
- Decider: Mirage (most likely)

**Player comparison (last 3 months):**
| Role      | NiP        | Rating | Liquid     | Rating | Edge   |
|-----------|------------|--------|------------|--------|--------|
| Star      | device     | 1.21   | nitr0      | 0.98   | NiP ★  |
| Entry     | Brollan    | 1.14   | oSee       | 1.09   | NiP    |
| Support   | REZ        | 1.08   | grim       | 1.07   | Even   |
| Rifler    | es3tag     | 1.05   | malbsMd    | 1.02   | NiP    |
| IGL       | HEAP       | 0.97   | Twistzz    | 1.18   | Liquid |

**Model output:**
- NiP win probability: **65%** (Liquid 35%)
- Confidence: Medium (limited DB data for recent Liquid roster)
- bo3.gg analysts: Liquid 65% (contradicts our model → use as contrarian signal)

**Value bets:**
| Bet              | Odds  | Implied | Our prob | Edge    | Kelly (1/4) |
|------------------|-------|---------|----------|---------|-------------|
| NiP ML           | 1.75  | 57.1%   | 65%      | +7.9% ✅ | 1.6% bankroll |
| NiP +1.5 maps    | 1.23  | 81.3%   | ~88%     | +6.7% ✅ | 5.4%        |
| Liquid ML        | 2.10  | 47.6%   | 35%      | -12.6% ❌ | skip       |

**Final recommendation:** NiP ML @1.75 (primary), NiP +1.5 @1.23 (safer)

**Result:** TBD
**Correct:** TBD

---

### Match 2: MOUZ vs 9z
**Time:** 14:30 | **Format:** BO3 | **Bracket:** Lower QF

**Data used:**
- HLTV lineups + map stats
- bo3.gg (MOUZ ~85% per analysts)
- Bookmaker odds: MOUZ @1.10, 9z @7.60

**Map Pool Analysis:**
| Map     | MOUZ W%  | MOUZ N | 9z W%    | 9z N | Edge        |
|---------|----------|--------|----------|------|-------------|
| Nuke    | 80%      | 15     | 17%      | 6    | MOUZ ★★     |
| Ancient | 75%      | 16     | 33%      | 9    | MOUZ ★      |
| Anubis  | 65%      | 17     | 44%      | 9    | MOUZ        |
| Mirage  | 53%      | 15     | 47%      | 15   | Even        |
| Dust2   | 50%      | 6      | 63%      | 8    | 9z          |
| Inferno | 58%      | 12     | 40%      | 15   | MOUZ slight |
| Vertigo | 60%      | 5      | 60%      | 5    | Even        |

**Veto prediction:**
- MOUZ bans: Dust2 (9z's best)
- 9z bans: Nuke (MOUZ 80%)
- MOUZ picks: Ancient (75%)
- 9z picks: Mirage (most balanced)
- Decider: Inferno or Anubis (MOUZ edge)

**Model output:**
- MOUZ win probability: **68%** (NOT 91% as bookmakers imply)
- Confidence: Medium-low (9z sparse in DB)
- Key insight: MOUZ @1.10 = 91% implied — massively overpriced relative to realistic 68%

**Value bets:**
| Bet              | Odds  | Implied | Our prob | Edge     | Kelly (1/4) |
|------------------|-------|---------|----------|----------|-------------|
| MOUZ ML          | 1.10  | 90.9%   | 68%      | -22.9% ❌ | skip        |
| 9z ML            | 7.60  | 13.2%   | 32%      | +18.8% ✅ | 2.5%        |
| 9z 2-1           | 10.40 | 9.6%    | ~22%     | +12.4% ✅ | 1.2%        |
| MOUZ 2-0         | 1.53  | 65.4%   | ~46%     | -19.4% ❌ | skip        |

**Final recommendation:** 9z ML @7.60 (value play, small unit), 9z 2-1 @10.40 (lottery)
> Note: 9z are SA champions — on their best maps (Dust2, Mirage) they are competitive. MOUZ odds are priced as if this is a walkover when it's not.

**Result:** TBD
**Correct:** TBD

---

### Match 3: PARIVISION vs Spirit
**Time:** 17:00 | **Format:** BO3 | **Bracket:** Upper SF

**Data used:**
- HLTV lineups + map stats
- bo3.gg (Spirit ~70% per analysts)
- Bookmaker odds: PARI @3.38, Spirit @1.32

**Map Pool Analysis:**
| Map     | PARI W%  | PARI N | Spirit W%  | Spirit N | Edge       |
|---------|----------|--------|------------|----------|------------|
| Overpass| 75%      | 8      | 33%        | 3        | PARI ★     |
| Dust2   | 63%      | 8      | 40%        | 5        | PARI       |
| Ancient | 57%      | 7      | 70%        | 20       | Spirit ★   |
| Mirage  | 50%      | 6      | 67%        | 18       | Spirit     |
| Nuke    | 43%      | 7      | 62%        | 21       | Spirit     |
| Inferno | 50%      | 4      | 58%        | 12       | Spirit     |
| Vertigo | 43%      | 7      | 55%        | 11       | Spirit     |

**Note:** Spirit's map pool data is estimated — they were world #1 in 2024, now rebuilding after roster changes (donk left). PARIVISION are CIS regional force.

**Veto prediction:**
- PARI bans: Ancient (Spirit 70%)
- Spirit bans: Overpass (PARI 75%)
- PARI picks: Dust2 (PARI 63% there)
- Spirit picks: Mirage or Nuke (Spirit edge)
- Decider: Inferno or Vertigo (Spirit slight edge)

**Player comparison:**
- Spirit still have tighter roles + higher individual ceiling despite roster rebuilding
- PARI are disciplined tactically but outgunned in firepower
- Key matchup: PARI IGL (Patsi) vs Spirit's star players

**Model output:**
- Spirit win probability: **66%** (PARI 34%)
- Confidence: Low-medium (sparse CIS data, Spirit rebuilding roster)
- bo3.gg analysts: Spirit ~70% — aligns with our model

**Value bets:**
| Bet              | Odds  | Implied | Our prob | Edge    | Kelly (1/4) |
|------------------|-------|---------|----------|---------|-------------|
| PARI ML          | 3.38  | 29.6%   | 34%      | +4.4% ✅ | 0.4%        |
| Spirit ML        | 1.32  | 75.8%   | 66%      | -9.8% ❌ | skip        |
| PARI +1.5        | 1.60  | 62.5%   | ~72%     | +9.5% ✅ | 3.3%        |

**Final recommendation:** PARI +1.5 @1.60 (primary), PARI ML @3.38 (tiny value, skip unless confident)
> Spirit are favoured but PARI can steal maps. +1.5 is the safer value bet here.

**Result:** TBD
**Correct:** TBD

---

### Match 4: The MongolZ vs Vitality
**Time:** 19:30 | **Format:** BO3 | **Bracket:** Upper SF (Group B)

**Data used:**
- HLTV full lineups + map stats (pick%, ban%, win%, played) — 3 months
- HLTV player ratings (3-month + event-specific)
- bo3.gg full H2H + 6-month map data
- Handicap data (15 MZ matches, 14 Vitality matches)

**Map Pool Analysis:**
| Map | MongolZ W% | N | Pick% | Ban% | Vitality W% | N | Pick% | Ban% | Edge |
|-----|-----------|---|-------|------|------------|---|-------|------|------|
| Mirage | 64% | 11 | 51% | 0% | 40% | 5 | 8% | 0% | MongolZ ★★ |
| Nuke | 62% | 8 | 3% | 3% | 100% | 4 | 18% | 0% | Even (low N Vit) |
| Dust2 | 43% | 7 | 0% | 3% | 100% | 9 | 31% | 0% | Vitality ★★ |
| Inferno | 40% | 5 | 11% | 3% | 75% | 8 | 26% | 0% | Vitality ★ |
| Overpass | 0% | 1 | 0% | 3% | 100% | 8 | 13% | 0% | Vitality ★★ |
| Ancient | 20% | 5 | 30% | 0% | 100% | 1 | 0% | 90% | (both ban) |
| Anubis | — | 0 | 0% | 35% | 100% | 3 | 0% | 5% | (MZ ban) |

**Predicted veto:**
- MongolZ bans: Anubis (35% ban)
- Vitality bans: Ancient (90% ban)
- MongolZ picks: Mirage (51% first pick, 64% WR) ← guaranteed
- Vitality picks: Dust2 (100% WR, 9-map win streak) ← guaranteed
- MongolZ bans: Overpass (Vitality 100% on 8 maps)
- Vitality bans: Nuke (MZ 5-map win streak)
- Decider: Inferno (Vitality 75% vs MongolZ 40%)

**Per-map probabilities:**
- Mirage (MZ pick): MongolZ 65%, Vitality 35%
- Dust2 (Vit pick): MongolZ 15%, Vitality 85%
- Inferno (decider): MongolZ 30%, Vitality 70%

**Player comparison (3-month / event rating):**
| Player (MongolZ) | 3m | Event | | Player (Vitality) | 3m | Event |
|---|---|---|---|---|---|---|
| Techno | 0.94 | 1.73 (+0.79) | | ZywOo | 1.44 | 1.91 (+0.47) |
| 910 | 1.12 | 1.44 (+0.32) | | flameZ | 1.26 | 1.57 (+0.31) |
| cobrazera | 1.02 | 1.41 (+0.39) | | ropz | 1.09 | 1.38 (+0.29) |
| mzinho | 1.02 | 0.99 (-0.03) | | apEX | 1.00 | 1.15 (+0.15) |
| bLitz | 0.88 | 0.75 (-0.13) | | mezii | 1.05 | 1.01 (-0.04) |

**H2H (recent):**
- Feb 21, 2026: Vitality 2-0 (Dust2 13-3, Mirage 16-13 OT)
- Feb 15, 2026: Vitality 2-1 (MZ won Mirage 13-10, lost Nuke+Dust2)
- Dec 11, 2025: Vitality 2-0 (Dust2 13-4, Mirage 13-5)
- Aug 23, 2025: MongolZ 2-1 (Nuke+Mirage)
- Overall: Vitality 3-0 in last 3 series

**Model output:**
- Vitality win probability: **72%** (MongolZ 28%)
- Confidence: High (both teams well-represented, clear veto pattern)
- BO3 math: MZ 2-0 = 9.8%, MZ 2-1 = 18.2%, Vit 2-1 = 42.2%, Vit 2-0 = 29.8%
- Key signal: ZywOo at 1.91 event rating — god mode. But MZ get Mirage where they have real edge.

**Value bets:**
| Bet | Odds | Implied | Our prob | Edge | Kelly (1/4) |
|-----|------|---------|----------|------|-------------|
| MongolZ +1.5 maps | 2.33 | 42.9% | ~55% | +12.1% ✅ | 2.7% bankroll |
| MongolZ ML | 5.80 | 17.2% | 28% | +10.8% ✅ | 1.1% |
| Vitality 2-0 | 1.56 | 64.1% | ~45% | -19.1% ❌ | skip |
| Vitality ML | 1.15 | 87.0% | 72% | -15% ❌ | skip |

**Final recommendation:** MongolZ +1.5 @2.33 (primary). MongolZ take Mirage (their pick, 64% WR) — Vitality 2-0 is overpriced.

**Result:** TBD
**Correct:** TBD

---

## Accuracy Tracking

| Date | Matches | Correct | Wrong | Accuracy |
|------|---------|---------|-------|----------|
| 2026-03-21 | 4 | TBD | TBD | TBD |
| **Total** | **4** | **TBD** | **TBD** | **TBD** |

### Value Bets Tracking
| Date | Bet | Odds | Edge | Stake | Result | P&L |
|------|-----|------|------|-------|--------|-----|
| 2026-03-21 | NiP ML | 1.75 | +7.9% | 1.6u | TBD | TBD |
| 2026-03-21 | NiP +1.5 | 1.23 | +6.7% | 5.4u | TBD | TBD |
| 2026-03-21 | 9z ML | 7.60 | +18.8% | 2.5u | TBD | TBD |
| 2026-03-21 | PARI +1.5 | 1.60 | +9.5% | 3.3u | TBD | TBD |
| 2026-03-21 | MongolZ +1.5 | 2.33 | +12.1% | 2.7u | TBD | TBD |
| 2026-03-21 | MongolZ ML | 5.80 | +10.8% | 1.1u | TBD | TBD |

---

## Model Calibration Notes

### Known weaknesses (as of 2026-03-21)
- **CIS/SA teams:** Sparse DB data → low confidence. Override with manual analysis.
- **Post-roster-change teams:** Glicko-2 lags behind actual strength for 2-3 months.
- **LAN vs online:** Model not fully separating LAN performance. Add `lan_bonus` feature.
- **Veto math is most reliable signal** — when pick/ban rates are available, use them first.

### Planned improvements
- [ ] Collect 90-day LAN-only stats separately
- [ ] Add event-specific player rating delta as feature
- [ ] Backtest: does veto prediction beat match prediction alone?
- [ ] Add map handicap model (e.g. NiP -3.5 rounds on Nuke)
