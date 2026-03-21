"""
CS2 Analytics Telegram Bot (@cs2analisbot)

Commands:
  /start         — welcome message
  /today         — upcoming matches with predictions
  /match         — detailed match prediction
  /value         — value bet calculator (manual odds input)
  /maps          — team map pool analysis
  /h2h           — head-to-head history
  /history       — prediction accuracy tracking
  /model         — model stats (accuracy, brier score)
  /bootstrap     — start HLTV data collection (admin)
  /train         — retrain model (admin)
"""

import asyncio
import logging
import re
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, BotCommand
from aiogram.filters import Command, CommandStart
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

import database as db
import predictor as pred
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from model import get_model_meta

logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_admin(message: Message) -> bool:
    return message.chat.id == TELEGRAM_CHAT_ID or message.from_user.id == TELEGRAM_CHAT_ID


def _safe_send(text: str) -> str:
    """Escape markdown special chars for Telegram MarkdownV1."""
    # Limit length
    if len(text) > 4096:
        text = text[:4090] + "\n..."
    return text


# ── Command handlers ──────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(msg: Message):
    await msg.answer(
        "👋 *CS2 Analytics Bot*\n\n"
        "Прогнозы на матчи и карты CS2 на основе ML-модели.\n\n"
        "Команды:\n"
        "• /today — матчи на сегодня\n"
        "• /match NaVi vs G2 — прогноз на матч\n"
        "• /value NaVi vs G2 1.85 2.10 — value ставка\n"
        "• /maps NaVi — пул карт команды\n"
        "• /h2h NaVi G2 — история встреч\n"
        "• /analyze NaVi vs G2 — глубокий анализ матча\n"
        "• /history — моя точность\n"
        "• /model — статистика модели"
    )


@dp.message(Command("today"))
async def cmd_today(msg: Message):
    await msg.answer("🔍 Загружаю матчи...")
    upcoming = db.get_upcoming_matches(hours_ahead=36)
    text = pred.format_today_matches(upcoming)
    await msg.answer(_safe_send(text))


@dp.message(Command("match"))
async def cmd_match(msg: Message):
    """
    /match NaVi vs G2
    /match NaVi vs G2 Mirage Inferno Nuke
    """
    args = (msg.text or "").strip()
    # Remove /match command
    args = re.sub(r"^/match\s*", "", args, flags=re.IGNORECASE).strip()
    if not args:
        await msg.answer(
            "Использование:\n"
            "`/match Team1 vs Team2`\n"
            "`/match Team1 vs Team2 Mirage Inferno Nuke`"
        )
        return

    # Parse: "Team1 vs Team2 [map1 map2 ...]"
    vs_match = re.split(r"\s+vs\s+", args, maxsplit=1, flags=re.IGNORECASE)
    if len(vs_match) < 2:
        await msg.answer("Формат: `/match Team1 vs Team2`")
        return

    t1_name = vs_match[0].strip()
    rest = vs_match[1].strip()

    # Extract map names (known maps at end of string)
    from config import CS2_MAPS
    maps_found = []
    words = rest.split()
    team2_words = []
    for w in words:
        if w.capitalize() in CS2_MAPS:
            maps_found.append(w.capitalize())
        else:
            team2_words.append(w)
    t2_name = " ".join(team2_words).strip()

    if not t2_name:
        await msg.answer("Не удалось определить вторую команду.")
        return

    await msg.answer(f"⏳ Анализирую {t1_name} vs {t2_name}...")
    prediction, error = pred.get_match_prediction(t1_name, t2_name, map_names=maps_found or None)
    if error:
        await msg.answer(f"❌ {error}")
        return

    text = pred.format_match_prediction(prediction)
    await msg.answer(_safe_send(text))

    # Save prediction to DB if match exists
    m = _find_upcoming_match(prediction.team1_name, prediction.team2_name)
    if m:
        db.insert_prediction(
            match_id=m["id"],
            team1_prob=prediction.team1_prob,
            team2_prob=prediction.team2_prob,
            confidence=prediction.confidence,
            model_version=prediction.model_version,
        )


@dp.message(Command("value"))
async def cmd_value(msg: Message):
    """
    /value NaVi vs G2 1.85 2.10
    """
    args = re.sub(r"^/value\s*", "", msg.text or "", flags=re.IGNORECASE).strip()
    if not args:
        await msg.answer(
            "Использование:\n"
            "`/value Team1 vs Team2 коэф1 коэф2`\n\n"
            "Пример: `/value NaVi vs G2 1.85 2.10`"
        )
        return

    # Parse odds from end of string
    parts = args.split()
    try:
        odds2 = float(parts[-1])
        odds1 = float(parts[-2])
    except (ValueError, IndexError):
        await msg.answer("Не могу прочитать коэффициенты. Формат: `1.85 2.10`")
        return

    rest = " ".join(parts[:-2])
    vs_match = re.split(r"\s+vs\s+", rest, maxsplit=1, flags=re.IGNORECASE)
    if len(vs_match) < 2:
        await msg.answer("Формат: `/value Team1 vs Team2 коэф1 коэф2`")
        return

    t1_name = vs_match[0].strip()
    t2_name = vs_match[1].strip()

    await msg.answer(f"⏳ Считаю edge для {t1_name} vs {t2_name}...")
    vb1, vb2, error = pred.calculate_value_bet(t1_name, t2_name, odds1, odds2)
    if error:
        await msg.answer(f"❌ {error}")
        return

    text = pred.format_value_bet(vb1, vb2)
    await msg.answer(_safe_send(text))


@dp.message(Command("analyze"))
async def cmd_analyze(msg: Message):
    """
    /analyze NiP vs Liquid
    /analyze NiP vs Liquid 1.69 2.12     ← adds value bet section
    /analyze NiP vs Liquid lan            ← mark as LAN match
    """
    args = re.sub(r"^/analyze\s*", "", msg.text or "", flags=re.IGNORECASE).strip()
    if not args:
        await msg.answer(
            "Использование:\n"
            "`/analyze Team1 vs Team2`\n"
            "`/analyze Team1 vs Team2 коэф1 коэф2`\n\n"
            "Пример: `/analyze NiP vs Liquid 1.69 2.12`"
        )
        return

    # Parse optional odds from end (two floats like "1.85 2.10")
    parts = args.split()
    odds1 = odds2 = None
    is_lan = False

    # Check for "lan" flag
    if parts and parts[-1].lower() == "lan":
        is_lan = True
        parts = parts[:-1]

    # Check for odds (two trailing floats)
    if len(parts) >= 2:
        try:
            odds2 = float(parts[-1])
            odds1 = float(parts[-2])
            parts = parts[:-2]
        except ValueError:
            odds1 = odds2 = None

    rest = " ".join(parts)
    vs_match = re.split(r"\s+vs\s+", rest, maxsplit=1, flags=re.IGNORECASE)
    if len(vs_match) < 2:
        await msg.answer("Формат: `/analyze Team1 vs Team2`")
        return

    t1_name = vs_match[0].strip()
    t2_name = vs_match[1].strip()

    if not t1_name or not t2_name:
        await msg.answer("Не удалось распознать команды.")
        return

    odds_str = f" @ {odds1:.2f}/{odds2:.2f}" if odds1 else ""
    lan_str  = " [LAN]" if is_lan else ""
    await msg.answer(f"Анализирую {t1_name} vs {t2_name}{odds_str}{lan_str}...\n"
                     f"Загружаю данные с HLTV (~30 сек)")

    try:
        import match_analyzer as ma
        result, error = await ma.analyze(
            t1_name, t2_name,
            is_lan=is_lan,
            event_tier="A",
            odds1=odds1,
            odds2=odds2,
        )
    except Exception as e:
        logger.error("analyze error: %s", e, exc_info=True)
        await msg.answer(f"❌ Ошибка анализа: {e}")
        return

    if error:
        await msg.answer(f"❌ {error}")
        return

    messages = pred.format_deep_analysis(result)
    for text in messages:
        # Escape chars that break Telegram MarkdownV1
        safe = text.replace("*", "").replace("`", "").replace("_", " ")
        if len(safe) > 4096:
            safe = safe[:4090] + "\n..."
        await msg.answer(safe)


@dp.message(Command("maps"))
async def cmd_maps(msg: Message):
    """
    /maps NaVi
    """
    team_name = re.sub(r"^/maps\s*", "", msg.text or "", flags=re.IGNORECASE).strip()
    if not team_name:
        await msg.answer("Использование: `/maps Team`")
        return

    team = pred.resolve_team(team_name)
    if not team:
        await msg.answer(f"Команда не найдена: '{team_name}'")
        return

    text = pred.format_map_pool(team["name"], team["id"])
    await msg.answer(_safe_send(text))


@dp.message(Command("h2h"))
async def cmd_h2h(msg: Message):
    """
    /h2h NaVi G2
    /h2h NaVi vs G2
    """
    args = re.sub(r"^/h2h\s*", "", msg.text or "", flags=re.IGNORECASE).strip()
    # Support both "T1 vs T2" and "T1 T2"
    if " vs " in args.lower():
        parts = re.split(r"\s+vs\s+", args, 1, re.IGNORECASE)
    else:
        # Split on first occurrence of multiple spaces or middle of string
        mid = len(args) // 2
        # Try to find a space near the middle
        space_idx = args.find(" ", mid - 10)
        if space_idx == -1:
            space_idx = args.find(" ")
        if space_idx == -1:
            await msg.answer("Использование: `/h2h Team1 vs Team2`")
            return
        parts = [args[:space_idx], args[space_idx + 1:]]

    if len(parts) < 2:
        await msg.answer("Использование: `/h2h Team1 vs Team2`")
        return

    t1_name, t2_name = parts[0].strip(), parts[1].strip()
    t1 = pred.resolve_team(t1_name)
    t2 = pred.resolve_team(t2_name)

    if not t1:
        await msg.answer(f"Команда не найдена: '{t1_name}'")
        return
    if not t2:
        await msg.answer(f"Команда не найдена: '{t2_name}'")
        return

    matches = db.get_matches_between(t1["id"], t2["id"], days=365)
    if not matches:
        await msg.answer(f"Нет данных о встречах {t1['name']} vs {t2['name']} за последний год.")
        return

    t1_wins = sum(1 for m in matches if m["winner_id"] == t1["id"])
    t2_wins = len(matches) - t1_wins
    lines = [
        f"🔄 H2H: {t1['name']} vs {t2['name']}",
        f"Счёт: {t1_wins} - {t2_wins} (последние {len(matches)} матчей)",
        "",
    ]
    for m in matches[:10]:
        winner = t1["name"] if m["winner_id"] == t1["id"] else t2["name"]
        date = (m.get("date") or "")[:10]
        lines.append(f"• {date} — {winner} ({m.get('event', '')})")

    await msg.answer(_safe_send("\n".join(lines)))


@dp.message(Command("history"))
async def cmd_history(msg: Message):
    history = db.get_prediction_history(limit=20)
    stats = db.get_prediction_stats()
    text = pred.format_history(history, stats)
    await msg.answer(_safe_send(text))


@dp.message(Command("model"))
async def cmd_model(msg: Message):
    match_meta = get_model_meta("match")
    map_meta = get_model_meta("map")
    if not match_meta:
        await msg.answer("Модель ещё не обучена. Запусти `/train` (admin).")
        return
    lines = [
        "🤖 *Статистика модели*",
        "",
        f"Match model v{match_meta.get('version', '?')}:",
        f"  Выборка: {match_meta.get('samples', '?')} матчей",
        f"  CV точность: {match_meta.get('cv_accuracy_mean', 0):.1%} ± {match_meta.get('cv_accuracy_std', 0):.1%}",
        f"  Brier score: {match_meta.get('brier_score', '?')}",
        f"  Обучена: {(match_meta.get('trained_at') or '')[:10]}",
    ]
    if map_meta:
        lines += [
            "",
            f"Map model v{map_meta.get('version', '?')}:",
            f"  Выборка: {map_meta.get('samples', '?')} карт",
            f"  CV точность: {map_meta.get('cv_accuracy_mean', 0):.1%}",
        ]
    stats = db.get_prediction_stats()
    if stats["total"]:
        lines += [
            "",
            f"Live точность: {stats['accuracy']}% ({stats['wins']}/{stats['total']})",
        ]
    await msg.answer(_safe_send("\n".join(lines)))


# ── Admin commands ────────────────────────────────────────────────────────────

@dp.message(Command("bootstrap"))
async def cmd_bootstrap(msg: Message):
    if not _is_admin(msg):
        await msg.answer("❌ Только для admin.")
        return
    args = re.sub(r"^/bootstrap\s*", "", msg.text or "").strip()
    months = int(args) if args.isdigit() else 12
    await msg.answer(
        f"🔄 Запускаю сбор данных с HLTV за {months} месяцев...\n"
        f"⏳ Это займёт 1-2 часа. Не останавливай процесс.\n"
        f"Прогресс будет в консоли."
    )
    # Run in background
    import data_collector
    asyncio.create_task(data_collector.bootstrap(months))


@dp.message(Command("train"))
async def cmd_train(msg: Message):
    if not _is_admin(msg):
        await msg.answer("❌ Только для admin.")
        return
    await msg.answer("🧠 Запускаю обучение модели...")
    try:
        import model as mdl
        meta = await asyncio.get_event_loop().run_in_executor(None, mdl.train_all)
        await msg.answer(
            f"✅ Модель обучена!\n\n"
            f"Match CV: {meta['match']['cv_accuracy_mean']:.1%}\n"
            f"Map CV: {meta['map']['cv_accuracy_mean']:.1%}"
        )
    except Exception as e:
        await msg.answer(f"❌ Ошибка обучения: {e}")


@dp.message(Command("update"))
async def cmd_update(msg: Message):
    if not _is_admin(msg):
        return
    await msg.answer("🔄 Обновляю данные с HLTV...")
    import data_collector
    asyncio.create_task(data_collector.update_live())
    await msg.answer("✅ Обновление запущено.")


# ── Alert sender (called by scheduler) ───────────────────────────────────────

async def send_daily_matches():
    """Send today's matches to the configured chat. Called by scheduler."""
    upcoming = db.get_upcoming_matches(hours_ahead=36)
    text = pred.format_today_matches(upcoming)
    try:
        await bot.send_message(TELEGRAM_CHAT_ID, text)
    except Exception as e:
        logger.error("Failed to send daily matches: %s", e)


async def send_value_alert(match_text: str):
    """Send value bet alert. Called externally."""
    try:
        await bot.send_message(TELEGRAM_CHAT_ID, f"⚠️ VALUE BET\n\n{match_text}")
    except Exception as e:
        logger.error("Failed to send alert: %s", e)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_upcoming_match(t1_name: str, t2_name: str):
    upcoming = db.get_upcoming_matches(hours_ahead=72)
    for m in upcoming:
        if (t1_name.lower() in m["team1_name"].lower() or
                t1_name.lower() in m["team2_name"].lower()):
            if (t2_name.lower() in m["team1_name"].lower() or
                    t2_name.lower() in m["team2_name"].lower()):
                return m
    return None


# ── Entry point ───────────────────────────────────────────────────────────────

async def set_commands():
    await bot.set_my_commands([
        BotCommand(command="start",     description="Старт / помощь"),
        BotCommand(command="today",     description="Матчи на сегодня"),
        BotCommand(command="match",     description="Прогноз: /match NaVi vs G2"),
        BotCommand(command="analyze",   description="Глубокий анализ: /analyze NaVi vs G2"),
        BotCommand(command="value",     description="Value bet: /value NaVi vs G2 1.85 2.10"),
        BotCommand(command="maps",      description="Пул карт: /maps NaVi"),
        BotCommand(command="h2h",       description="История встреч: /h2h NaVi vs G2"),
        BotCommand(command="history",   description="Моя точность"),
        BotCommand(command="model",     description="Статистика модели"),
    ])


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db.init_db()
    await set_commands()
    logger.info("CS2 bot starting (@cs2analisbot)...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
