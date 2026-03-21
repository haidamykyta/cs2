# CS2 Match Prediction Model

XGBoost + Glicko-2 rating system for CS2 match prediction with HLTV scraping and Telegram bot delivery.

## Architecture

```
data_collector.py    — Playwright-based HLTV scraper (bootstrap + incremental)
database.py          — SQLite storage (teams, matches, map_results)
glicko2.py           — Pure Python Glicko-2 rating system
feature_engineer.py  — Feature extraction (form, H2H, map WR, rank delta)
model.py             — XGBoost + CalibratedClassifierCV training
predictor.py         — Prediction engine + value bet calculator
hltv_live.py         — Live HLTV scraping (map pool, player stats, bo3.gg)
match_analyzer.py    — Deep analysis orchestrator (async, parallel scraping)
telegram_bot.py      — aiogram v3 Telegram bot (@cs2analisbot)
scheduler.py         — Background data refresh
config.py            — Constants (CS2_MAPS, thresholds, etc.)
main.py              — Entry point
```

## Model

- **Match model:** XGBoost binary classifier + CalibratedClassifierCV (isotonic)
- **Map model:** Same architecture, per-map training
- **Features:** rank_delta, glicko_diff, form_t1/t2, lan_form, h2h_rate, map_wr, event_tier
- **Rating:** Glicko-2 with 30-day RD decay, per-map separate ratings
- **Value bet:** edge = model_prob - 1/bookmaker_odds; threshold 5%; sizing = 0.25 Kelly

## Deep Analysis (`/analyze`)

```
/analyze NiP vs Liquid
/analyze NiP vs Liquid 1.75 2.10 lan
```

Produces 3-message breakdown:
1. Form + map pool comparison + veto prediction
2. Player duels + H2H + bo3.gg analyst view
3. Model probability + value bet recommendation

## Methodology (Manual Analysis)

When automated scraping hits Cloudflare blocks, use manual workflow:
1. Paste HLTV lineups + map stats (with pick%/ban%/win%/played)
2. Paste bo3.gg page content
3. Model outputs: veto prediction + map probabilities + BO3 win% + Kelly bets

### Key signals (priority order)
1. **Veto math** — pick/ban rates + map WR → most reliable for BO3 outcome
2. **Event ratings** — player performance AT THIS EVENT vs 3-month baseline
3. **Form last 90 days** — overall team trajectory
4. **H2H** — recent matchup history (last 6 months > all-time)
5. **Glicko-2 delta** — rank/rating difference
6. **bo3.gg** — sanity check only, not primary signal

## Predictions Log

See [PREDICTIONS.md](PREDICTIONS.md) for all recorded predictions with results.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env  # add TELEGRAM_TOKEN
python main.py bootstrap
python main.py bot
```
