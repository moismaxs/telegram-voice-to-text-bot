"""Точка входа: polling aiogram."""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import settings
from app.db import init_db
from app.handlers import router
from app.stt import get_model

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("voices")


async def main() -> None:
    if not settings.BOT_TOKEN or ":" not in settings.BOT_TOKEN:
        log.error("BOT_TOKEN не задан! Скопируй .env.example в .env и вставь токен от @BotFather.")
        raise SystemExit(1)

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    # TeleAds: статистика + рекламный флоу. Внутренние апдейты платформы
    # middleware отфильтровывает сам — хендлеры их не увидят.
    # Без ключа или при ошибке импорта бот работает как раньше, без рекламы.
    if settings.TELEADS_API_KEY:
        try:
            from teleads.aiogram3 import BapMiddleware

            dp.update.middleware(BapMiddleware(settings.TELEADS_API_KEY))
        except Exception:
            log.exception("Не удалось подключить TeleAds, работаем без рекламы")
        else:
            log.info("TeleAds подключён")
    else:
        log.info("TELEADS_API_KEY не задан, реклама отключена")

    # Прогрев локальной модели до polling имеет смысл только для local:
    # в режиме groq веса не нужны, а грузить 500МБ в RAM зря — вредно.
    if settings.STT_PROVIDER == "local":
        try:
            await asyncio.to_thread(get_model)
        except Exception:
            log.exception(
                "Не удалось загрузить Whisper-модель %s. Проверь сеть/кэш.",
                settings.MODEL_SIZE,
            )
            await bot.session.close()
            raise SystemExit(2)
    else:
        log.info("STT через %s, локальная модель не грузится", settings.STT_PROVIDER)

    try:
        db = await asyncio.to_thread(init_db)
    except Exception:
        log.exception("Не удалось открыть SQLite, аналитики не будет")
    else:
        log.info("Аналитика: %s", db)

    me = await bot.get_me()
    log.info(
        "Бот @%s запущен. STT=%s, max=%sс", me.username, settings.STT_PROVIDER, settings.MAX_DURATION_SEC,
    )
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
