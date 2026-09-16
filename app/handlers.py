"""Хендлеры: /start + voice/audio/video_note с ответом в тот же чат."""
import asyncio
import contextlib
import html
import logging
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from app.config import settings
from app.db import get_stats, track_event, track_user
from app.stt import RateLimitedError, convert_to_wav, transcribe_file

log = logging.getLogger(__name__)
router = Router()

# чтобы CPU не умирал на войсах по 2-5 мин — максимум 3 параллельные расшифровки
SEMAPHORE = asyncio.Semaphore(3)

HELP_TEXT = (
    "Как пользоваться 🎙\n\n"
    "• <b>Личка:</b> отправь голосовое, аудио или кружок — верну текст.\n"
    "• <b>Группа:</b> добавь меня в группу с доступом к сообщениям — "
    "расшифровку войса я пришлю <b>в тот же чат ответом</b> на сообщение.\n"
    "• Можно <b>пересылать</b> чужие войсы мне в личку.\n\n"
    f"Лимит длины: {settings.MAX_DURATION_SEC}с. Русский язык."
)

PRIVACY_TEXT = (
    "Приватность 🔒\n\n"
    "• Голосовые качаются во временную папку и <b>удаляются сразу</b> после расшифровки.\n"
    "• Текст расшифровки <b>не храним</b> — только отвечаем им в чат."
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if message.from_user and not message.from_user.is_bot:
        track_user(
            message.from_user.id,
            message.from_user.username,
            message.from_user.full_name,
        )
    await message.answer(
        "Привет! Я расшифровываю голосовые 🎙\n\n"
        "• Отправь войс <b>сюда в личку</b> — пришлю текст ответом.\n"
        "• Или добавь меня в <b>группу</b> (нужен доступ к сообщениям) — "
        "расшифровку я пришлю <b>в тот же чат ответом</b> на голосовое.\n\n"
        "/help — помощь, /privacy — про приватность."
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("privacy"))
async def cmd_privacy(message: Message) -> None:
    await message.answer(PRIVACY_TEXT)


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Только для админа (ADMIN_IDS). Не светим в /setcommands."""
    if not message.from_user or message.from_user.id not in settings.admin_ids():
        await message.answer("⛔ Нет доступа.")
        return
    s = get_stats()
    if not s:
        await message.answer("Аналитика недоступна (нет БД).")
        return
    await message.answer(
        "📊 <b>Статистика</b>\n\n"
        f"👥 Юзеров всего: <b>{s['users_total']}</b> (новых сегодня: {s['users_today']})\n"
        f"🎙 Расшифровок: сегодня <b>{s['tr_today']}</b> · "
        f"неделя {s['tr_week']} · всего {s['tr_total']}\n"
        f"⏱ Средняя длина: {s['avg_dur']}с · ошибок: {s['errors']}"
    )


def _extract_file(message: Message) -> tuple[str, int | None, str] | None:
    """Возвращает (file_id, duration, label) для voice/audio/video_note."""
    if message.voice:
        return message.voice.file_id, message.voice.duration, "голосового"
    if message.audio:
        return message.audio.file_id, message.audio.duration, "аудио"
    if message.video_note:
        return message.video_note.file_id, message.video_note.duration, "кружка"
    return None


@router.message(F.voice | F.audio | F.video_note)
async def handle_voice(message: Message, bot: Bot) -> None:
    extracted = _extract_file(message)
    if not extracted:
        return
    file_id, duration, label = extracted
    user = message.from_user
    log.info(
        "Входящее %s: chat_type=%s chat_id=%s user_id=%s duration=%s",
        label, message.chat.type, message.chat.id,
        user.id if user else None, duration,
    )
    if user is None or user.is_bot:
        return
    track_user(user.id, user.username, user.full_name)

    if duration and duration > settings.MAX_DURATION_SEC:
        track_event(user.id, message.chat.id, message.chat.type, label, duration, ok=False)
        await message.reply(
            f"⚠️ {label.capitalize()} слишком длинное ({duration}с). "
            f"Максимум — {settings.MAX_DURATION_SEC}с."
        )
        return

    is_private = message.chat.type == "private"

    if duration and duration > 60:
        status_text = f"⏳ Расшифровываю {label} (~{duration}с), это займёт ~30–60с..."
    else:
        status_text = "⏳ Расшифровываю, секунду..."
    status = await message.reply(status_text)
    ok = False
    tmp_dir = Path(settings.TMP_DIR)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    # нейтральное расширение: voice=ogg, кружок=mp4, аудио=mp3 — ffmpeg детектит сам
    src_path = tmp_dir / f"{file_id}.bin"
    wav_path = tmp_dir / f"{file_id}.wav"

    try:
        tg_file = await bot.get_file(file_id)
        assert tg_file.file_path is not None
        await bot.download_file(tg_file.file_path, destination=src_path)

        async with SEMAPHORE:
            await asyncio.to_thread(convert_to_wav, src_path, wav_path)
            text = await asyncio.to_thread(transcribe_file, wav_path)

        if not text:
            await status.edit_text("😕 Не смог распознать речь — тихо или одни шумы.")
            return

        # лимит Telegram ~4096 символов
        if len(text) > 3900:
            text = text[:3900] + "…"

        safe_text = html.escape(text)
        user_mention = html.escape(user.full_name)

        # подпись для пересланных: откуда войс
        fwd_suffix = ""
        fwd = message.forward_origin
        if fwd is not None:
            fwd_name = None
            if getattr(fwd, "sender_user", None) is not None:
                fwd_name = fwd.sender_user.full_name
            elif getattr(fwd, "chat", None) is not None:
                fwd_name = fwd.chat.title
            elif getattr(fwd, "sender_user_name", None):
                fwd_name = fwd.sender_user_name
            if fwd_name:
                fwd_suffix = f"\n\n<i>↪️ переслано от {html.escape(str(fwd_name))}</i>"

        if is_private:
            await message.reply(f"📝 <b>Расшифровка:</b>\n\n{safe_text}{fwd_suffix}")
        else:
            await message.reply(
                f"📝 <b>Расшифровка</b> от {user_mention}:\n\n{safe_text}"
            )
        ok = True
        await status.delete()
    except RateLimitedError:
        log.warning("STT rate limit, file_id=%s", file_id)
        with contextlib.suppress(Exception):
            await status.edit_text("⏳ Сервис распознавания перегружен, попробуй ещё раз через минуту.")
    except Exception:
        log.exception("Ошибка расшифровки file_id=%s", file_id)
        with contextlib.suppress(Exception):
            await status.edit_text("❌ Ошибка расшифровки, попробуй ещё раз чуть позже.")
    finally:
        track_event(user.id, message.chat.id, message.chat.type, label, duration, ok=ok)
        for p in (src_path, wav_path):
            with contextlib.suppress(OSError):
                if p.exists():
                    p.unlink()


@router.message()
async def fallback(message: Message) -> None:
    # игнорим всё кроме войсов, но подсказываем в личке (команды не трогаем)
    if message.chat.type == "private" and message.text and not message.text.startswith("/"):
        await message.answer("Пришли мне голосовое, аудио или кружок 🎙 — я верну текст.")
