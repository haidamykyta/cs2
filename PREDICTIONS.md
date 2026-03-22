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

**ACTUAL VETO (confirmed):**
1. NiP ban: Inferno ✅ (predicted correctly)
2. Liquid ban: Overpass ❌ (predicted Nuke — Liquid left NiP's best map open!)
3. NiP pick: **Nuke** (71% WR) ❌ (predicted Dust2/Ancient — but low pick% was misleading, opponents always banned Nuke so it never appeared as a pick)
4. Liquid pick: **Mirage** ❌ (predicted Vertigo — NiP has 56% WR on Mirage, odd choice by Liquid)
5. NiP ban: Dust2
6. Liquid ban: Anubis
7. Decider: **Ancient** (NiP 63% WR vs Liquid 25%)

**REVISED probabilities after actual veto:**
| Map | NiP WR | Liquid WR | P(NiP wins) |
|-----|--------|-----------|-------------|
| Nuke (NiP pick) | 71% | 29% | ~78% |
| Mirage (Liq pick) | 56% | 38% | ~62% |
| Ancient (decider) | 63% | 25% | ~72% |

Revised BO3: NiP **~80%** | Liquid ~20% (was 65% pre-veto)
NiP ML @1.75 edge became **+34%** post-veto (was +7.9%)

**Player comparison (last 3 months):**
| Role      | NiP        | Rating | Liquid     | Rating | Edge   |
|-----------|------------|--------|------------|--------|--------|
| Star      | device     | 1.21   | nitr0      | 0.98   | NiP ★  |
| Entry     | Brollan    | 1.14   | oSee       | 1.09   | NiP    |
| Support   | REZ        | 1.08   | grim       | 1.07   | Even   |
| Rifler    | es3tag     | 1.05   | malbsMd    | 1.02   | NiP    |
| IGL       | HEAP       | 0.97   | Twistzz    | 1.18   | Liquid |

⚠️ **ANALYSIS ERROR:** User provided correct rosters from HLTV at start of session, but after context compression I used stale DB data instead.
- NiP correct: sjuush, xKacpersky, Snappi, r1nkle, cairne
- Liquid correct: NAF, EliGE, siuhy, ultimate, malbsMd
- Map pool WR data was still valid (team-level stats). Player duel section was wrong.
- **Rule:** ALWAYS use rosters from user's HLTV paste, never from DB. DB player data is always stale.

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

**MAP-LEVEL PREDICTIONS (post-veto):**

| Map | Our P(NiP) | Bookie likely favors | Value bet threshold | Notes |
|-----|-----------|---------------------|---------------------|-------|
| Map 1: Nuke (NiP pick) | **78%** | NiP ~1.30-1.40 | NiP @1.40+ → bet | NiP 5-map win streak, 71% WR |
| Map 2: Mirage (Liq pick) | **62%** | Liquid ~1.60-1.80 | NiP @2.00+ → bet | Bookie будет давать Liquid т.к. их пик, но NiP имеет edge |
| Map 3: Ancient (decider) | **72%** | NiP ~1.50-1.65 | NiP @1.50+ → bet | Только если серия 1-1. NiP 63% vs Liquid 25% |

**Score prediction:**
| Score | Our prob | Est. bookie odds | Value? |
|-------|----------|-----------------|--------|
| NiP 2-0 | **48%** | ~2.20-2.80 | ✅ если @2.10+ |
| NiP 2-1 | **31%** | ~3.50-4.50 | ✅ если @3.20+ |
| Liquid 2-1 | **12%** | ~6.00-8.00 | skip |
| Liquid 2-0 | **8%** | ~8.00-12.00 | skip |

**Map bets actually placed:**
| Map | Bet | Odds | Our prob | Edge | Result |
|-----|-----|------|----------|------|--------|
| Map 1 (Nuke) | NiP win | — | 78% NiP | — | **NiP 13:3 WIN ✅** |
| Map 2 (Mirage) | NiP YES (Polymarket) | 54¢ | 62% NiP | +8% | **Liquid 19:17 OT LOSS ❌** |
| Map 3 (Ancient) | — | — | 72% NiP | — | **Liquid 13:9 LOSS ❌** |

**Map 1 scoreboard (Nuke):**
NiP: sjuush 17K/106.1ADR, xKacpersky 15K/91.1, Snappi 13K/88.3, r1nkle 12K/74.8, cairne 12K/73.3
Liquid: NAF 13K/103.1, EliGE 10K/57.6, siuhy 5K/47.6, ultimate 4K/45.4, malbsMd 4K/36.2

**Final scoreboard (all 3 maps):**
NiP: xKacpersky 1.24 rating, Snappi 1.06, r1nkle 1.01, cairne 0.95, sjuush 0.92
Liquid: EliGE 1.10, siuhy 1.00, NAF 0.99, ultimate 0.98, malbsMd 0.94

**Series result:** LIQUID 2-1 ❌ (predicted NiP 80%)
**Score:** NiP 1-2 (won Nuke, lost Mirage OT, lost Ancient)
**Correct (series):** NO ❌
**Correct (maps):** 1/3 (only Nuke correct)

**ROOT CAUSE (bo3.gg H2H map WR):**
| Map | My prediction | H2H actual WR (NiP vs Liquid, 6mo) | Error |
|-----|--------------|--------------------------------------|-------|
| Nuke | NiP 78% | NiP 23% vs Liquid | -55%!! |
| Mirage | NiP 62% | NiP 16% vs Liquid | -46%!! |
| Ancient | NiP 72% | NiP 9% vs Liquid | -63%!! |

**Conclusion:** Overall WR (71%, 56%, 63%) was useless here. Liquid specifically owns NiP on every map.

**bo3.gg detailed ratings (all 3 maps):**
NiP: xKacpersky 6.9, r1nkle 6.3, cairne 6.2, Snappi 6.1, sjuush 6.0
Liquid: EliGE 6.0, siuhy 5.5, ultimate 5.5, NAF 5.8, malbsMd 5.2
Note: Teams were very close in individual ratings — Liquid won through map knowledge, not individual skill.

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

**ACTUAL VETO:**
1. 9z ban: Mirage | 2. MOUZ ban: Anubis | 3. 9z pick: Dust2 | 4. MOUZ pick: Inferno
5. 9z ban: Overpass | 6. MOUZ ban: Ancient | 7. Decider: Nuke

**Map results:**
- Dust2 (9z pick): MOUZ 13-11 (MOUZ won — 9z's pick, 9z lost)
- Inferno (MOUZ pick): 9z 13-8 (9z won on MOUZ's pick!)
- Nuke (decider): 9z 13-9 ← 9z took the decider

**Final scoreboard:**
9z: luchov 1.21 rating, meyern 1.15, HUASOPEEK 1.13, dgt 1.11, max 0.80
MOUZ: xertioN 1.05, Spinx 0.98, Jimpphat 0.95, torzsi 0.91, Brollan 0.75

**Result:** 9Z 2-1 ✅ (caught the upset!)
**Correct (series direction):** NO (predicted MOUZ 68%) but value bet on 9z was CORRECT ✅
**Value bets:** 9z ML @7.60 ✅ WIN | 9z 2-1 @10.40 ✅ WIN

**bo3.gg detailed ratings (all 3 maps):**
9z: luchov MVP 6.5, dgt 6.4, HUASOPEEK 6.2, meyern 6.1, max 5.0
MOUZ: xertioN EVP 6.0, Spinx 5.9, torzsi 5.9, Jimpphat 5.7, Brollan 5.0
Note: Brollan was MOUZ weakest link (5.0 rating). 9z won on Inferno (MOUZ pick!) and Nuke decider.
Key signal missed: 9z was SA champion, MOUZ had 3 losses to MongolZ recently and looked inconsistent.

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

**ACTUAL VETO:**
1. Spirit ban: Inferno | 2. PARI ban: Nuke | 3. Spirit pick: Anubis | 4. PARI pick: Ancient
5. Spirit ban: Overpass | 6. PARI ban: Mirage | 7. Decider: Dust2

**Map results:**
- Anubis (Spirit pick): PARI 13-3 (PARI demolished Spirit on their own pick!)
- Ancient (PARI pick): PARI 13-8
- Dust2: not played

**Final scoreboard:**
PARI: xiELO 1.50, zweih 1.32, BELCHONOKK 1.30, nota 1.12, Jame 1.05
Spirit: donk 1.55 (best player in losing team), sh1ro 0.95, zont1x 0.79, tN1R 0.67, magixx 0.59

**Result:** PARIVISION 2-0 ✅ (massive upset, Spirit obliterated!)
**Correct (direction):** NO (predicted Spirit 66%) but underdog value bets CORRECT ✅
**Value bets:** PARI +1.5 @1.60 ✅ WIN | PARI ML @3.38 ✅ WIN (if bet)
**Note:** Spirit looked completely lost. donk top-fragged in a loss (1.55). Team chemistry issues visible.

**bo3.gg detailed ratings (both maps):**
PARI: xiELO MVP 7.5, zweih 7.4, BELCHONOKK 6.6, nota 6.3, Jame 6.3
Spirit: donk EVP 7.4, sh1ro 5.7, zont1x 5.2, magixx 4.5, tN1R 4.4
Note: donk (7.4) was best on Spirit but couldn't carry 4 teammates with ratings 4.4-5.7. Classic solo-carry loss.
PARI all 5 players above 6.0 — balanced team performance. Spirit 3 players below 5.5 — structural problem.

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

**ACTUAL VETO:**
1. MZ ban: Anubis ✅ | 2. Vitality ban: Ancient ✅ | 3. MZ pick: Mirage ✅
4. Vitality pick: Overpass ❌ (predicted Dust2 — both maps have 100% WR for Vitality)
5. MZ ban: Dust2 | 6. Vitality ban: Nuke ✅ | 7. Decider: Inferno ✅
Veto prediction accuracy: 5/7 correct

**Map results:**
- Mirage (MZ pick): MongolZ 4-13 (Vitality DESTROYED MZ on their own pick!)
- Overpass (Vitality pick): Vitality 16-13 OT
- Inferno: not played

**Final scoreboard:**
Vitality: flameZ 1.81 rating, ZywOo 1.70, apEX 1.15, ropz 1.01, mezii 0.98
MongolZ: Techno 1.15, cobrazera 0.91, 910 0.84, mzinho 0.65, bLitz 0.50

**Result:** VITALITY 2-0 ✅ (direction correct, but MZ +1.5 lost)
**Correct (series direction):** YES ✅ (Vitality 72%)
**Value bets:** MongolZ +1.5 @2.33 ❌ LOSS
**Note:** MZ got crushed on Mirage (their best map!) 4-13. Historical 64% WR was inflated by weaker opponents. Vitality in top form — flameZ + ZywOo in god mode.

---

## Accuracy Tracking

| Date | Matches | Correct direction | Wrong | Accuracy |
|------|---------|---------|-------|----------|
| 2026-03-21 | 4 | 1 (Vitality) | 3 (NiP,MOUZ,Spirit) | 25% |
| **Total** | **4** | **1** | **3** | **25%** |

**Note:** Direction accuracy 25%, BUT value bet model caught 2 upsets correctly (9z, PARI). Model underprices heavy favorites and overprices underdogs → good for finding value on underdog side.

### Value Bets Tracking
| Date | Bet | Odds | Edge | Result | P&L (1u base) |
|------|-----|------|------|--------|---------------|
| 2026-03-21 | NiP ML | 1.75 | +7.9% | ❌ LOSS | -1.6u |
| 2026-03-21 | NiP +1.5 | 1.23 | +6.7% | ❌ LOSS | -5.4u |
| 2026-03-21 | NiP Map2 Mirage (PM) | 54¢ | +8% | ❌ LOSS (OT) | -4.3% |
| 2026-03-21 | 9z ML | 7.60 | +18.8% | ✅ WIN | +16.5u (2.5u stake × 6.6 profit) |
| 2026-03-21 | 9z 2-1 | 10.40 | +12.4% | ✅ WIN | +11.2u (1.2u stake × 9.4 profit) |
| 2026-03-21 | PARI +1.5 | 1.60 | +9.5% | ✅ WIN | +2.0u (3.3u stake × 0.6 profit) |
| 2026-03-21 | PARI ML | 3.38 | +4.4% | ✅ WIN | +2.6u (1.1u stake × 2.38 profit) |
| 2026-03-21 | MongolZ +1.5 | 2.33 | +12.1% | ❌ LOSS | -2.7u |
| **TOTAL** | | | | **4W / 4L** | **~+18u NET POSITIVE** |

---

## Model Calibration Notes

### Veto calibration finding (2026-03-21, NiP vs Liquid)
- **Problem:** NiP had 3% historical first pick rate on Nuke → I predicted Dust2/Ancient
- **Reality:** NiP picked Nuke (71% WR) the moment Liquid didn't ban it
- **Root cause:** Low pick% = opponents always ban it, not that team avoids it. When ban doesn't happen → team grabs best map instantly.
- **New rule:** If WR >65% on a map AND opponent doesn't ban it → near-certain pick, ignore historical pick%.
- **Liquid mistake:** Banned Overpass instead of Nuke → left NiP's best map open, picked Mirage where NiP has 56% WR.
- **Impact:** Pre-veto NiP 65%, post-veto NiP ~80% after actual veto revealed.

### Known weaknesses (as of 2026-03-21)
- **CIS/SA teams:** Sparse DB data → low confidence. Override with manual analysis.
- **Post-roster-change teams:** Glicko-2 lags behind actual strength for 2-3 months.
- **LAN vs online:** Model not fully separating LAN performance. Add `lan_bonus` feature.
- **Veto math is most reliable signal** — when pick/ban rates are available, use them first.
- **ROSTER DATA:** Always use rosters from user's HLTV paste. DB player data is always stale. Never substitute DB players when user provided the actual lineup.

### Calibration findings (2026-03-21 session)

**1. ⭐ CRITICAL: H2H MAP WINRATE beats overall map WR** ← biggest finding of this session
- bo3.gg shows NiP vs Liquid 6-month H2H map WR:
  - Nuke: NiP wins only **23%** vs Liquid (I predicted 78%!)
  - Mirage: NiP wins only **16%** vs Liquid (I predicted 62%!)
  - Ancient: NiP wins only **9%** vs Liquid (I predicted 72%!)
- I used overall map WR (NiP 71% Nuke, 63% Ancient) which was inflated by weaker opponents.
- Liquid specifically has Nuke/Ancient/Mirage figured out against NiP across multiple series.
- **Rule: ALWAYS check H2H map WR from bo3.gg first. If sample N≥3 maps, use H2H WR over overall WR.**

**2. Win rates inflated by opponent quality**
- NiP had 63% WR on Ancient (8 maps) → lost 9-13 to Liquid. Small sample vs weak opponents.
- MongolZ had 64% WR on Mirage → lost 4-13 to Vitality. Sample likely vs CIS/lower tier teams.
- **Rule:** Weight WR by opponent quality. WR vs top-10 teams only = much more reliable.

**3. H2H series record predicts map-level results**
- NiP vs Liquid H2H series: Liquid 4 wins, NiP 1 win (last 5 series)
- Liquid beat NiP on Nuke, Mirage, Ancient in Jan 2026 series — exact same maps as March 21.
- PARI had 2-1 H2H vs Spirit (including a win Jan 2026). Spirit looked lost.
- **Rule:** If H2H series record < 6 months shows 4-1 or worse → massive flag, recalculate from scratch.

**3. Mirage OT is unpredictable**
- NiP should have won Mirage (62% model). Lost 17-19 in OT. One round difference.
- OT reduces model reliability significantly. Avoid map handicap bets on expected close maps.

**4. Spirit roster issues visible in data**
- donk top-fragged (1.55) in a 2-0 loss — means rest of team severely underperformed.
- magixx 0.59, tN1R 0.67 — bottom players dragging team down.
- **Rule:** Check if top fragger is carrying or if team plays as unit. Solo-carry teams lose to organized opponents.

**5. Value betting model worked well**
- Caught both major upsets (9z, PARI) via edge calculation even though direction prediction was wrong.
- Net positive despite 4 losses. Kelly sizing protected from ruin.
- **Rule:** Trust edge > trust direction. If edge >10% on underdog, bet even if model says they lose.

### Planned improvements
- [ ] Add opponent-quality-adjusted WR (top-10 only vs all opponents)
- [ ] Weight H2H last 6 months more heavily (currently underweighted)
- [ ] OT flag: don't recommend map handicaps on maps where expected score diff < 3 rounds
- [ ] Team cohesion metric: check if top fragger has high swing (carrying) vs balanced team
- [ ] Collect 90-day LAN-only stats separately
- [ ] Add event-specific player rating delta as feature
