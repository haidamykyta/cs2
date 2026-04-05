import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
HLTV_DELAY_MS = int(os.getenv("HLTV_DELAY_MS", "2500"))
DB_PATH = os.getenv("DB_PATH", "data/cs2_matches.db")
MODELS_DIR = os.getenv("MODELS_DIR", "data/models")
VALUE_EDGE_THRESHOLD = float(os.getenv("VALUE_EDGE_THRESHOLD", "0.05"))
KELLY_FRACTION = float(os.getenv("KELLY_FRACTION", "0.25"))
MIN_BET_PROB = float(os.getenv("MIN_BET_PROB", "0.20"))          # min model prob to bet
MIN_ODDS_THRESHOLD = float(os.getenv("MIN_ODDS_THRESHOLD", "1.40"))  # min decimal odds
MAX_ODDS_THRESHOLD = float(os.getenv("MAX_ODDS_THRESHOLD", "2.50"))   # max decimal odds — lowered from 3.00 (backtest: 2.50-3.00 = -13.7% ROI)
MAX_BET_BANKROLL_PCT = float(os.getenv("MAX_BET_BANKROLL_PCT", "0.03"))  # 3% max per bet
MAX_MARGIN_THRESHOLD = float(os.getenv("MAX_MARGIN_THRESHOLD", "0.07"))  # skip bets where bookmaker margin > 7%
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Glicko-2 defaults
GLICKO_INITIAL_RATING = 1500.0
GLICKO_INITIAL_RD = 350.0
GLICKO_INITIAL_VOLATILITY = 0.06
GLICKO_TAU = 0.5           # system constant, controls volatility change
GLICKO_RATING_PERIOD_DAYS = 7

# Model params
MATCH_MODEL_VERSION = "1.0"
MAP_MODEL_VERSION = "1.0"
MIN_MATCHES_FOR_PREDICTION = 5   # min matches a team needs before we predict
FORM_WINDOW = 10                  # last N matches for rolling form
MAP_FORM_WINDOW = 20              # last N map plays for map-specific stats
H2H_WINDOW_DAYS = 180             # 6 months for head-to-head

# Event tier mapping (HLTV event tier names)
EVENT_TIERS = {
    "S": 4,   # Major
    "A": 3,
    "B": 2,
    "C": 1,
    "D": 0,
}

CS2_MAPS = [
    "Mirage", "Inferno", "Nuke", "Ancient", "Anubis",
    "Dust2", "Vertigo", "Train", "Overpass", "Cache"
]
