"""Точка входа: polling aiogram."""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import settings
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

    # Прогрев модели до polling: первая расшифровка не висит,
    # а ошибка скачивания видна сразу в логах, а не на первом войсе.
    try:
        await asyncio.to_thread(get_model)
    except Exception:
        log.exception(
            "Не удалось загрузить Whisper-модель %s. Проверь сеть/кэш.",
            settings.MODEL_SIZE,
        )
        await bot.session.close()
        raise SystemExit(2)

    me = await bot.get_me()
    log.info("Бот @%s запущен. Модель=%s, max=%sс", me.username, settings.MODEL_SIZE, settings.MAX_DURATION_SEC)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
