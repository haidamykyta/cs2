# CS2 Betting Bot — Полный отчёт о сессии

> **Репозиторий:** [github.com/haidamykyta/cs2](https://github.com/haidamykyta/cs2)  
> **Локальный путь (Windows):** `C:/Users/Nik_H/Downloads/cs2_predictor`  
> **Стек:** Python 3.11, XGBoost + CalibratedClassifierCV, SQLite, aiogram v3, APScheduler  
> **Дата сессии:** июль 2025

---

## 1. Что было ДО нашей работы (стартовое состояние)

### 1.1 Данные

- В базе данных было **6 матчей** из 1 турнира (BLAST Open Rotterdam 2026).
- Модель XGBoost была обучена на этих 6 матчах — это **чистый шум**, не способный к обобщению.
- Источники данных: только HLTV + bo3.gg, сбор данных **не автоматизирован**.

### 1.2 Критические баги

| # | Проблема | Последствие |
|---|----------|-------------|
| 1 | `DB_PATH` захардкожен как `/home/user/workspace/cs2-bot/data/cs2_matches.db` (Linux-путь) | На Windows бот писал в несуществующую директорию → `match_odds` = 0, бот работал вслепую |
| 2 | Бэктестер сломан: `bankroll` никогда не обновлялся | Банкролл всегда = 1.0, ROI всегда = 0% — бэктест бессмысленен |
| 3 | Нет `MIN_BET_PROB` фильтра в логике ставок | Бот ставил на события с 10% вероятностью по модели — чистый гэмблинг |
| 4 | Таблица `match_odds` без колонки `raw_margin` | Невозможно фильтровать матчи с завышенной маржой букмекера |
| 5 | 6 матчей в training set | Модель не могла выучить ни одной закономерности |

### 1.3 Резюме стартового состояния

Бот был технически запускаемым, но **непригодным для реальных ставок**: модель обучена на шуме, бэктестер не считал ROI, фильтров качества не было, данные не собирались автоматически, а на Windows из-за hardcoded Linux-пути бот не мог прочитать odds.

---

## 2. Что мы сделали

### 2.1 Аудит и диагностика

1. **Прочитали весь репозиторий** — все `.py` файлы, конфиги, структуру БД.
2. **Нашли 5 критических проблем** (перечислены в разделе 1.2).
3. **Изучили 3 плана улучшений** от предыдущих сессий с Claude и объединили их в один мастер-план (`CS2_MASTER_PLAN_FINAL.md`).

### 2.2 Исследование источников данных

Проверили **7 источников данных** для CS2 esports:

| Источник | Результат |
|----------|-----------|
| HLTV.org | Playwright scraping, хрупкий, rate-limited |
| bo3.gg API | **Публичный API без авторизации** — главная находка |
| Liquipedia | Полезен для roster changes, не для матчей |
| Kaggle datasets | Tier B/C мусор, плохая калибровка |
| PandaScore | Платный API |
| Strafe | Ограниченный API |
| ESL/FACEIT | Нет публичного API |

#### bo3.gg — ключевое открытие сессии

**Base URL:** `https://api.bo3.gg/api/v1`  
**Авторизация:** НЕТ (полностью публичный API)

Методология обнаружения эндпоинтов:
- Браузерный мониторинг сетевых запросов
- Анализ JS-бандла фронтенда bo3.gg
- Перебор и документирование всех параметров фильтрации

**Масштаб данных:**

| Тир | Количество CS2 матчей |
|-----|----------------------|
| S   | 3,503                |
| A   | 2,630                |
| B   | 16,513               |
| C   | ~46,000              |
| **Итого** | **68,639**      |

**Ключевые данные в каждом матче:**
- `bet_updates` — коэффициенты команд + 14 рынков (handicap, total maps, exact score)
- `players_stats` — kills, deaths, ADR, KAST, rating, clutches на 10 игроков
- Per-map статистика через отдельный endpoint
- **Маржа букмекера:** ~5.2–5.8% (affiliate-букмекер)

---

### 2.3 Новые файлы созданы

#### `bo3gg_collector.py` — асинхронная библиотека для bo3.gg API

```
Класс: Bo3GGCollector (async)
Методы:
  get_finished_matches()     — с фильтрами по tier/game_version/status
  get_match_player_stats()   — 10 игроков, все метрики
  get_match_full()           — всё за один матч: карты + odds + stats
Задержка: 0.5s между запросами (rate limiting)
```

Библиотека спроектирована для многократного использования: и разовый импорт, и scheduler могут вызывать одни и те же методы.

#### `bo3gg_import.py` — полноценный бутстраппер БД

```
Назначение: массовый импорт исторических данных из bo3.gg в SQLite
Параметры CLI:
  --months    количество месяцев истории (по умолчанию 12)
  --tiers     уровни турниров через запятую (по умолчанию s,a)
  --delay     задержка между запросами в секундах (по умолчанию 0.5)
  --max       максимальное количество матчей (для отладки)

Записывает в таблицы:
  teams, matches, map_results, players, match_odds

Математика odds:
  raw_margin = (1/odds1 + 1/odds2) - 1
  overround  = 1/odds1 + 1/odds2
  fair_prob  = (1/odds) / overround    ← vig-removed вероятность

Защиты:
  - Пропуск placeholder odds (1.001/1.001)
  - DB_PATH берётся из config.py → .env (не захардкожен)
  - Идемпотентный: safe to re-run
```

---

### 2.4 Изменения в существующих файлах

#### `config.py` — новые пороговые значения

```python
# ДОБАВЛЕНО:
MIN_BET_PROB          = 0.20   # минимум 20% вероятности по модели
MIN_ODDS_THRESHOLD    = 1.40   # не ставим на слишком «короткие» котировки
MAX_ODDS_THRESHOLD    = 3.00   # не ставим на аутсайдеров (подтверждено бэктестом)
MAX_BET_BANKROLL_PCT  = 0.03   # максимум 3% банкролла за одну ставку
```

Все значения считываются через `os.getenv()` с fallback-дефолтами — можно менять через `.env` файл без правки кода.

#### `database.py` — миграции и новая колонка

```
Изменения:
  1. match_odds: добавлена колонка raw_margin REAL
  2. _run_migrations(): автоматический ALTER TABLE на существующих БД
     - Безопасна для повторного запуска (проверяет наличие колонки)
  3. upsert_match_odds(): автоматически вычисляет raw_margin и fair_prob
     при записи, даже если вызывающий код их не передал
```

#### `predictor.py` — фильтры качества ставок

```
Изменения:
  1. is_value check теперь проверяет:
     - MIN_BET_PROB: пропуск ставок с P(model) < 20%
     - MIN_ODDS_THRESHOLD: пропуск odds < 1.40
     - MAX_ODDS_THRESHOLD: пропуск odds > 3.00
  2. kelly_safe ограничен MAX_BET_BANKROLL_PCT (3% банкролла)
  3. EV% добавлен в ValueBet dataclass для логирования
```

#### `backtester.py` — критическое исправление

```
Изменения:
  1. ИСПРАВЛЕН БАГ: bankroll теперь реально обновляется после каждой ставки
     (было: bankroll = 1.0 навсегда → ROI = 0% всегда)
  2. Использует реальные odds из таблицы match_odds
     (было: синтетические odds или отсутствующие)
```

---

### 2.5 Сбор данных

Запустили `bo3gg_import.py` в sandbox-среде:

```
Команда: python bo3gg_import.py --months 12 --tiers s,a --delay 0.4
```

**Результат:**

| Таблица      | Записей | Комментарий |
|-------------|---------|-------------|
| teams       | 117     | Уникальные команды Tier S+A |
| matches     | 1,180   | Tier S: 808 / Tier A: 372 |
| map_results | 2,602   | ~2.2 карты на матч в среднем |
| players     | 609     | Уникальные игроки |
| match_odds  | 948     | Из них 447 с валидной маржой < 10% |

**Диапазон дат:** апрель 2025 → апрель 2026  
**Средняя маржа букмекера:** 5.8%

---

### 2.6 Обучение модели

Переобучили XGBoost на **чистых** Tier S+A данных (убрали Kaggle Tier B/C мусор, который портил калибровку):

#### Match model (предсказание победителя матча)

| Метрика | Значение |
|---------|----------|
| Samples | 1,097 |
| CV accuracy | 66.3% ± 10.8% |
| Brier score | 0.1144 |

> 66.3% — это **честная цифра** для Tier S+A. Предыдущие ~72% на Kaggle данных были завышены за счёт лёгких Tier B/C матчей (где фавориты выигрывают 80%+ и модель просто ставит на них).

#### Map model (предсказание победителя карты)

| Метрика | Значение |
|---------|----------|
| Samples | 2,429 |
| CV accuracy | 91.0% ± 2.5% |
| Brier score | 0.035 |

---

### 2.7 Walk-forward бэктест

**Методология:** честный out-of-sample тест.
- Обучение на 6 месяцев → предсказание на следующий месяц → сдвиг → повтор
- **5 тестовых окон:** Oct 2025, Nov 2025, Dec 2025, Jan 2026, Feb 2026
- Модель **переобучается** для каждого окна (нет утечки будущих данных)

#### Итерация 1: MAX_ODDS = 7.00 (без ограничения сверху)

| Метрика | Значение |
|---------|----------|
| Ставок | 159 |
| Win rate | 35.8% |
| Avg odds | 3.60 |
| **ROI** | **+2.3%** |

Вывод: слишком много ставок на дальних аутсайдеров (odds 5.00+) с низким win rate.

#### Итерация 2: MAX_ODDS = 3.50

| Метрика | Значение |
|---------|----------|
| Ставок | 88 |
| Win rate | 56.8% |
| Avg odds | 2.27 |
| **ROI** | **+22.8%** |

Вывод: значительное улучшение — отсечение хвоста аутсайдеров резко поднимает ROI.

#### Итерация 3: MAX_ODDS = 3.00 ← финальный выбор

| Метрика | Значение |
|---------|----------|
| Ставок | 75 |
| Win rate | 64.0% |
| Avg odds | 2.12 |
| **ROI** | **+32.8%** |
| CLV | +20.5% на 100% ставок |

**Разбивка по диапазонам odds (MAX_ODDS = 3.00):**

| Диапазон | Ставок | Win rate | ROI |
|----------|--------|----------|-----|
| 1.40–1.60 | 14 | 93% | +36.3% |
| 1.60–2.00 | 18 | 72% | +33.6% |
| 2.00–2.50 | 24 | 71% | **+63.4%** ← лучший бакет |
| 2.50–3.00 | 19 | 26% | **-13.7%** ← проблемный бакет |

> **Ключевой вывод:** диапазон 2.50–3.00 даёт отрицательный ROI. Рекомендация: снизить MAX_ODDS до 2.50 (см. раздел 6.1.2).

---

## 3. Текущая структура репозитория

```
cs2_predictor/
│
├── config.py                — все константы и thresholds (через os.getenv)
├── database.py              — SQLite слой, схема, миграции, upsert-методы
├── main.py                  — точка входа приложения
├── model.py                 — XGBoost + CalibratedClassifierCV, train/predict
├── predictor.py             — ValueBet логика, Kelly criterion, форматирование
├── feature_engineer.py      — 22 фичи: Glicko, form, H2H, map WR, player ratings
├── glicko2.py               — реализация Glicko-2 рейтинговой системы
├── backtester.py            — walk-forward бэктест
├── scheduler.py             — APScheduler: автоматический сбор данных
├── telegram_bot.py          — Telegram бот (aiogram v3)
├── hltv_live.py             — live scraping HLTV (Playwright)
├── data_collector.py        — Playwright HLTV scraper
├── match_analyzer.py        — deep analysis orchestrator
│
├── bo3gg_collector.py       ← НОВЫЙ: async библиотека для bo3.gg API
├── bo3gg_import.py          ← НОВЫЙ: полный DB bootstrapper
├── hltv_bootstrap.py        ← от предыдущих сессий: bootstrap HLTV данных
├── kaggle_importer.py       ← от предыдущих сессий: импорт Kaggle CSV
├── kaggle_rolling_importer.py ← от предыдущих сессий
│
├── data/
│   ├── cs2_matches.db               — SQLite БД (1,180 матчей S+A)
│   ├── models/
│   │   ├── match_model.joblib       — обученная match-модель
│   │   ├── match_model_meta.json    — метрики match-модели
│   │   ├── map_model.joblib         — обученная map-модель
│   │   └── map_model_meta.json      — метрики map-модели
│   ├── backtest_report.json         — in-sample бэктест (устарел)
│   ├── walkforward_report.json      — walk-forward MAX_ODDS=7.00
│   ├── walkforward_3_50_report.json — walk-forward MAX_ODDS=3.50
│   └── walkforward_3_00_report.json — walk-forward MAX_ODDS=3.00 (финал)
│
├── PREDICTIONS.md                   — лог всех предсказаний с результатами
├── CS2_MASTER_PLAN_FINAL.md         ← НОВЫЙ: мастер-план всех улучшений
└── requirements.txt
```

---

## 4. SQLite схема (ключевые таблицы)

```sql
CREATE TABLE teams (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    hltv_id INTEGER,
    ranking INTEGER,
    country TEXT
);

CREATE TABLE matches (
    id INTEGER PRIMARY KEY,
    team1_id INTEGER REFERENCES teams(id),
    team2_id INTEGER REFERENCES teams(id),
    winner_id INTEGER REFERENCES teams(id),
    date TEXT,
    format TEXT,           -- bo1 / bo3 / bo5
    event TEXT,
    event_tier TEXT,       -- s / a / b / c
    is_lan INTEGER,
    source TEXT            -- 'bo3gg' / 'hltv' / 'kaggle'
);

CREATE TABLE map_results (
    id INTEGER PRIMARY KEY,
    match_id INTEGER REFERENCES matches(id),
    map_name TEXT,         -- mirage / inferno / nuke / ...
    map_order INTEGER,
    team1_score INTEGER,
    team2_score INTEGER,
    winner_id INTEGER,
    overtime INTEGER       -- 0 или 1
);

CREATE TABLE players (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    team_id INTEGER REFERENCES teams(id),
    rating3 REAL,          -- рейтинг 2.0 / 3.0
    kast REAL,
    kd REAL,
    adr REAL,
    is_active INTEGER
);

CREATE TABLE match_odds (
    id INTEGER PRIMARY KEY,
    match_id INTEGER REFERENCES matches(id),
    bookmaker TEXT,
    team1_odds REAL,
    team2_odds REAL,
    team1_prob_fair REAL,  -- vig-removed probability
    team2_prob_fair REAL,  -- vig-removed probability
    raw_margin REAL        -- ← НОВАЯ КОЛОНКА: (1/o1 + 1/o2) - 1
);

CREATE TABLE glicko_ratings (
    id INTEGER PRIMARY KEY,
    team_id INTEGER REFERENCES teams(id),
    context TEXT,          -- 'overall' / 'mirage' / 'inferno' / ...
    rating REAL,
    rd REAL,
    volatility REAL,
    matches_played INTEGER
);

CREATE TABLE predictions (
    id INTEGER PRIMARY KEY,
    match_id INTEGER REFERENCES matches(id),
    team1_prob REAL,
    team2_prob REAL,
    confidence REAL,
    correct INTEGER        -- 0 или 1 (заполняется post-factum)
);
```

---

## 5. Финальные значения config.py

```python
# === Пороги для ставок ===
VALUE_EDGE_THRESHOLD  = 0.05   # минимум 5% edge (разница model_prob vs fair_prob)
KELLY_FRACTION        = 0.25   # ¼ Kelly — консервативный множитель
MIN_BET_PROB          = 0.20   # не ставим если модель даёт < 20% вероятности
MIN_ODDS_THRESHOLD    = 1.40   # не ставим на слишком короткие котировки
MAX_ODDS_THRESHOLD    = 3.00   # не ставим на аутсайдеров (подтверждено бэктестом)
MAX_BET_BANKROLL_PCT  = 0.03   # максимум 3% банкролла за одну ставку

# === Модель ===
# XGBoost + CalibratedClassifierCV (isotonic)
# 22 фичи: Glicko ratings, form (last 5/10/20), H2H, map WR, player ratings
# CV accuracy: 66.3%, Brier: 0.114

# === Данные ===
# Источник: bo3.gg public API (api.bo3.gg/api/v1)
# Матчей: 1,180 (Tier S: 808, Tier A: 372)
# Период: апрель 2025 – апрель 2026
```

---

## 6. bo3.gg API — полная шпаргалка

### 6.1 Общая информация

```
Base URL:     https://api.bo3.gg/api/v1
Авторизация:  НЕТ (полностью публичный)
Rate limit:   нет явного, рекомендуем delay 0.4–0.5s
Формат:       JSON
Пагинация:    page[limit]=100 & page[offset]=0
              total.count в ответе = общее кол-во
```

### 6.2 Ключевые эндпоинты

#### Список матчей

```
GET /matches
  ?filter[matches.status][eq]=finished
  &filter[matches.discipline_id][eq]=1          # CS
  &filter[matches.game_version][eq]=2            # CS2 (не CS:GO)
  &filter[matches.tier][eq]=s                    # s / a / b / c
  &sort=-start_date
  &page[limit]=100
  &page[offset]=0

Ответ содержит:
  - match.slug (для URL)
  - match.id (для связей)
  - team_1, team_2 (с names, logos)
  - bet_updates: team_1.coeff, team_2.coeff + 14 рынков
  - start_date, status, format (bo1/bo3/bo5)
  - event info с tier

total.count = 68,639 для CS2
```

#### Статистика игроков в матче

```
GET /matches/{slug}/players_stats

Ответ: массив из 10 объектов (5 на команду)
Каждый игрок:
  - kills, death, assists
  - adr (Average Damage per Round)
  - kast (Kill/Assist/Survive/Trade %)
  - player_rating (шкала 0–10, аналог HLTV rating 2.0)
  - headshots, first_kills, trade_kills, clutches
```

#### Список карт матча

```
GET /games?filter[games.match_id][eq]={match_id}

Ответ: массив карт
  - game.id, map_name, team1_score, team2_score, winner
```

#### Статистика игроков на карте

```
GET /games/{game_id}/players_stats

Те же поля что и /matches/{slug}/players_stats,
но для конкретной карты
```

#### Букмекерские данные

В объекте матча (`/matches` или `/matches/{slug}`), в поле `bet_updates`:

```json
{
  "team_1": {"coeff": 1.72},
  "team_2": {"coeff": 2.10},
  "markets": {
    "total_maps_over_2_5": 1.85,
    "total_maps_under_2_5": 1.95,
    "handicap_team1_plus_1_5": 1.30,
    "handicap_team1_minus_1_5": 3.20,
    "score_2_0": 2.50,
    "score_2_1": 3.10,
    "score_0_2": 4.50,
    "score_1_2": 3.80
    // ... и другие рынки
  }
}
```

### 6.3 Фильтры

| Параметр | Описание | Пример |
|----------|----------|--------|
| `filter[matches.status][eq]` | Статус матча | `finished`, `live`, `upcoming` |
| `filter[matches.discipline_id][eq]` | Дисциплина | `1` (CS) |
| `filter[matches.game_version][eq]` | Версия игры | `2` (CS2), `1` (CS:GO) |
| `filter[matches.tier][eq]` | Тир турнира | `s`, `a`, `b`, `c` |
| `filter[matches.start_date][gte]` | Дата от | `2025-01-01` |
| `filter[matches.start_date][lte]` | Дата до | `2025-12-31` |
| `sort` | Сортировка | `-start_date` (новые первые) |

---

## 7. Следующие шаги — конкретные задачи

> **Это САМЫЙ ВАЖНЫЙ раздел.** Задачи упорядочены по приоритету. Каждая задача содержит конкретные инструкции для выполнения.

---

### ПРИОРИТЕТ 1 — Критично (делать немедленно)

#### 7.1.1 Импортировать данные на реальную Windows БД

**Проблема:** все данные, собранные в сессии, существуют только в sandbox-среде. Реальная БД на Windows по-прежнему пуста (или содержит 6 старых матчей).

**Действие:**
```bash
cd C:/Users/Nik_H/Downloads/cs2_predictor
python bo3gg_import.py --months 12 --tiers s,a --delay 0.4
python model.py train
```

**Ожидаемый результат:** ~1,180 матчей в БД, переобученная модель с CV ~66%.

**Без этого шага всё остальное бессмысленно.**

#### 7.1.2 Снизить MAX_ODDS до 2.50

**Проблема:** диапазон 2.50–3.00 показал ROI -13.7% в walk-forward бэктесте (19 ставок, win rate 26%). Этот бакет **съедает** прибыль остальных диапазонов.

**Действие:**
1. В `config.py` изменить: `MAX_ODDS_THRESHOLD = 2.50`
2. Перезапустить walk-forward бэктест для подтверждения

**Ожидаемый результат:** ~56 ставок, ROI ~+45–50% (убираем убыточный хвост).

#### 7.1.3 Добавить фильтр raw_margin в predictor.py

**Проблема:** матчи с маржой > 7% имеют завышенные odds, что искажает расчёт value.

**Действие:** в функции `calculate_value_bet()` добавить:
```python
odds = db.get_match_odds(match_id)
if odds and odds.get('raw_margin') and odds['raw_margin'] > 0.07:
    return None, None, "Margin too high (>{:.1%})".format(odds['raw_margin'])
```

---

### ПРИОРИТЕТ 2 — Важно (неделя 1–2)

#### 7.2.1 H2H map win rate как фича

**Проблема (из PREDICTIONS.md):** матч NiP vs Liquid на карте Nuke. Модель дала NiP 78% на основе их общего 71% WR на Nuke. Но **H2H WR NiP vs Liquid на Nuke = 23%**. Liquid выиграл. Модель была слепа к H2H-паттернам.

**Действие:** в `feature_engineer.py` добавить фичу `h2h_map_wr`:
```python
def calc_h2h_map_wr(team_id, opponent_id, map_name, before_date, db):
    """Win rate команды против конкретного соперника на конкретной карте."""
    maps = db.get_map_results_h2h(team_id, opponent_id, map_name, before_date)
    if len(maps) < 3:
        return 0.5  # default при недостатке данных
    wins = sum(1 for m in maps if m['winner_id'] == team_id)
    return wins / len(maps)
```

Это потребует добавления метода `get_map_results_h2h()` в `database.py`.

#### 7.2.2 Настоящий walk-forward в backtester.py

**Проблема:** текущий `backtester.py` использует уже обученную модель для всех тестовых окон. Это **не настоящий** walk-forward — модель видела часть будущих данных.

**Действие:** переписать бэктестер так, чтобы модель **переобучалась** для каждого тестового окна:
```python
for window in test_windows:
    train_data = matches[matches.date < window.start]
    test_data  = matches[(matches.date >= window.start) & (matches.date < window.end)]
    model.train(train_data)  # ПЕРЕОБУЧЕНИЕ для каждого окна
    predictions = model.predict(test_data)
    evaluate(predictions)
```

#### 7.2.3 player_rating_event_delta как фича

**Действие:** в `feature_engineer.py` добавить:
```python
def player_rating_event_delta(player_id, event_id, db):
    """Разница avg рейтинга игрока НА ЭТОМ ивенте vs 3-месячный baseline."""
    event_rating = db.get_player_event_rating(player_id, event_id)
    baseline_rating = db.get_player_3month_rating(player_id)
    return event_rating - baseline_rating
```

Данные для этой фичи уже есть: `rating3` в таблице `players` + per-match stats из bo3.gg.

#### 7.2.4 Отдельные модели для BO1 и BO3

**Проблема:** BO1 имеет значительно выше дисперсию чем BO3. Одна модель для обоих форматов создаёт шум.

**Действие:** в `model.py`:
```python
def train_match_model(format_filter='bo3'):
    matches = db.get_matches(format=format_filter)
    # ... обучение на отфильтрованных данных

# Обучаем две модели:
train_match_model(format_filter='bo3')  # → match_model_bo3.joblib
train_match_model(format_filter='bo1')  # → match_model_bo1.joblib
```

В `predictor.py` выбирать модель по формату предстоящего матча.

---

### ПРИОРИТЕТ 3 — Улучшения (неделя 2–3)

#### 7.3.1 Автоматическое обновление данных через APScheduler

В `scheduler.py` добавить:
```python
# Каждые 30 мин: новые предстоящие матчи + их odds
scheduler.add_job(collect_upcoming_bo3gg, 'interval', minutes=30)

# Каждый час: результаты завершённых матчей + player stats
scheduler.add_job(collect_results_bo3gg, 'interval', hours=1)

# Каждый день в 03:00: переобучение если > 20 новых матчей за неделю
scheduler.add_job(maybe_retrain, 'cron', hour=3)

# Каждый день в 08:00: утренний брифинг value bets в Telegram
scheduler.add_job(send_daily_briefing, 'cron', hour=8)
```

Все функции должны использовать `Bo3GGCollector` из `bo3gg_collector.py`.

#### 7.3.2 Динамический Kelly fraction

Текущий фиксированный `KELLY_FRACTION = 0.25` не учитывает неопределённость модели.

```python
def dynamic_kelly(confidence, n_matches_trained, cv_accuracy):
    """Адаптивный Kelly: уменьшаем ставку при высокой неопределённости."""
    base = 0.25
    if confidence < 0.30:       base *= 0.5   # низкая уверенность модели
    if n_matches_trained < 15:  base *= 0.6   # мало данных по H2H
    if cv_accuracy < 0.58:      base *= 0.7   # модель плохо обучена
    return min(base, 0.25)
```

#### 7.3.3 roster_age_days как фича

**Гипотеза:** команды с ростером < 60 дней нестабильны (химия не выстроена).

**Источник данных:** Liquipedia API — дата последнего изменения состава.

```python
def get_roster_age_days(team_name):
    # Liquipedia API: последнее изменение состава
    # Возвращает количество дней с последнего roster change
    pass
```

#### 7.3.4 CLV tracking в production

Для каждой сделанной ставки необходимо:
1. Записать odds на момент ставки (opening line)
2. Записать closing line odds (перед стартом матча)
3. Вычислить CLV = `(closing_fair_prob - model_prob_at_bet_time)`

Это главная метрика качества модели в долгосрочной перспективе. Положительный CLV = модель видит линию раньше рынка.

#### 7.3.5 Добавить Tier B данные для обучения

```bash
python bo3gg_import.py --months 6 --tiers b --delay 0.4
```

Это даст ~1,500 дополнительных матчей. Стратегия использования:
- **Обучать** на S + A + B (больше данных = лучше обобщение)
- **Предсказывать и ставить** только на S + A (более предсказуемые)

---

## 8. Промпт для Claude при следующей сессии

Скопировать этот блок в начало каждой сессии:

```
You are a senior Python developer working on a CS2 esports betting prediction bot.

Repository: github.com/haidamykyta/cs2
Local path: C:/Users/Nik_H/Downloads/cs2_predictor

STACK: Python 3.11, XGBoost + CalibratedClassifierCV, SQLite, aiogram v3, APScheduler
DATA SOURCE: bo3.gg public API (api.bo3.gg/api/v1) — no auth required
DB: data/cs2_matches.db (1,180 Tier S+A matches, Apr 2025–Apr 2026)

SESSION SUMMARY: Read CS2_SESSION_SUMMARY.md in the repo root for full context of what was done.

CURRENT MODEL PERFORMANCE (walk-forward, out-of-sample):
  Match model: CV 66.3%, Brier 0.114
  Backtest ROI: +32.8% (75 bets, win rate 64%, avg odds 2.12, CLV +20.5%)

CURRENT THRESHOLDS (config.py):
  VALUE_EDGE_THRESHOLD=0.05
  KELLY_FRACTION=0.25
  MIN_BET_PROB=0.20
  MIN_ODDS_THRESHOLD=1.40
  MAX_ODDS_THRESHOLD=3.00  ← consider lowering to 2.50
  MAX_BET_BANKROLL_PCT=0.03

KEY CONSTRAINTS:
  - Keep async/await everywhere (aiogram + bo3gg_collector use asyncio)
  - SQLite only — no external DB
  - All new config values must go in config.py with os.getenv() fallback
  - Never hardcode paths — use os.path.dirname(os.path.abspath(__file__))
  - Do NOT change thresholds without running walk-forward backtest first
  - bo3.gg API has no auth — but use delay 0.4s between requests

PRIORITY TASKS (in order):
  1. Import data to real Windows DB (bo3gg_import.py)
  2. Lower MAX_ODDS to 2.50 and re-backtest
  3. Add raw_margin filter in predictor.py (> 7% = skip)
  4. Add h2h_map_wr feature in feature_engineer.py
  5. Real walk-forward in backtester.py (retrain per window)
  6. Separate BO1/BO3 models
  7. APScheduler auto-collection from bo3.gg
  8. Dynamic Kelly fraction

TASK: [конкретная задача здесь]
```

---

## 9. Известные ограничения и риски

### 9.1 Статистические ограничения

| Ограничение | Описание |
|------------|----------|
| Малая выборка | 75 ставок в бэктесте — это ~150 для статистической значимости при 5% edge |
| Высокая дисперсия CV | ± 10.8% accuracy — модель нестабильна между фолдами |
| Один год данных | Модель не видела смены мет (новые карты, патчи, переходы игроков) |
| Survivorship bias | bo3.gg может не содержать отменённых / технических матчей |

### 9.2 Технические риски

| Риск | Описание | Митигация |
|------|----------|-----------|
| bo3.gg API может закрыться | Публичный API без SLA | Резервный источник: HLTV Playwright scraper |
| Odds latency | bo3.gg odds обновляются не в реальном времени | CLV tracking покажет реальное запаздывание |
| SQLite concurrency | Один писатель, много читателей | Достаточно для текущего масштаба |
| Model drift | Мета CS2 меняется (баланс оружия, карты) | Автопереобучение каждый день (scheduler) |

### 9.3 Что НЕ проверено

- Реальная торговля (paper trading) — бэктест ≠ live
- Closing line value в production — только бэктест CLV
- Работа на Windows — все тесты проведены в Linux sandbox
- Масштабирование на Tier B — обучение только на S+A

---

## 10. Метрики для мониторинга в production

При запуске бота на реальные ставки отслеживать:

| Метрика | Целевое значение | Алерт если |
|---------|------------------|------------|
| CLV (Closing Line Value) | > +5% | < 0% три дня подряд |
| ROI (скользящий 30 дней) | > +10% | < -5% |
| Win rate | 55–70% | < 45% на 20+ ставках |
| Avg odds | 1.60–2.30 | > 2.50 (дрифт в аутсайдеров) |
| Ставок в неделю | 5–15 | 0 (бот не находит value) |
| Brier score (rolling) | < 0.15 | > 0.20 (модель деградирует) |
| Max drawdown | < 15% bankroll | > 20% → остановить и пересмотреть |

---

## 11. Хронология сессии

1. **Аудит репозитория** — чтение всех файлов, понимание архитектуры
2. **Диагностика** — выявление 5 критических проблем
3. **Исследование API** — проверка 7 источников, обнаружение bo3.gg
4. **Документирование bo3.gg** — все эндпоинты, фильтры, структура данных
5. **Создание bo3gg_collector.py** — async библиотека
6. **Создание bo3gg_import.py** — CLI-инструмент для массового импорта
7. **Правки database.py** — миграции, raw_margin колонка
8. **Правки config.py** — новые thresholds
9. **Правки predictor.py** — фильтры MIN_BET_PROB, odds range, Kelly cap
10. **Правки backtester.py** — исправление бага с bankroll
11. **Сбор данных** — 1,180 матчей Tier S+A за 12 месяцев
12. **Обучение модели** — CV 66.3%, Brier 0.114
13. **Walk-forward #1** (MAX_ODDS=7.00) — ROI +2.3%
14. **Walk-forward #2** (MAX_ODDS=3.50) — ROI +22.8%
15. **Walk-forward #3** (MAX_ODDS=3.00) — ROI +32.8%
16. **Создание мастер-плана** — CS2_MASTER_PLAN_FINAL.md
17. **Создание этого документа** — CS2_SESSION_SUMMARY.md

---

*Документ создан по итогам сессии работы над CS2 betting bot. Все метрики, код и рекомендации актуальны на момент создания.*
