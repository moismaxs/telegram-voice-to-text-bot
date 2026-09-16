# Telegram Voice-to-Text Bot 🎙

[![CI](https://github.com/moismaxs/telegram-voice-to-text-bot/actions/workflows/ci/badge.svg)](https://github.com/moismaxs/telegram-voice-to-text-bot/actions)
![Python 3.11](https://img.shields.io/badge/python-3.11-blue)
![License MIT](https://img.shields.io/badge/license-MIT-green)

Телеграм-бот, который расшифровывает голосовые, аудио и видеосообщения-кружки **прямо в чате**. Живой бот: [@vois_v_tekst_bot](https://t.me/vois_v_tekst_bot).

Отправляешь войс — получаешь текст ответом. Работает и в личке, и в группах. Всё распознавание — **локально, бесплатно, без внешних API**.

> 🎬 Демо-гифка появится здесь после запуска на хосте.

## Возможности

- 🎙 Голосовые, аудио (mp3/m4a) и кружки — ответ текстом в тот же чат
- 👥 Группы: добавь бота — расшифровка приходит ответом на сообщение, `/start` участникам не нужен
- ↪️ Понимает пересланные сообщения, подписывает источник
- 🇷🇺 Русский язык, войсы до 5 минут (настраивается)
- ⏳ Честный статус «расшифровываю» для длинных сообщений
- 🔒 Приватность: файлы удаляются сразу, текст нигде не хранится, базы нет

## Стек

- **aiogram 3.x** — Telegram Bot API (polling)
- **faster-whisper** (`small`, int8, CPU) — локальный STT
- **FFmpeg** — конвертация ogg/mp4/mp3 → wav 16k mono
- **Docker + Compose** — запуск одной командой

## Как это работает

```
войс (ogg) / кружок (mp4) / аудио (mp3)
        │  bot.get_file + download
        ▼
   ffmpeg → wav 16k mono
        │  faster-whisper, beam_size=5, vad_filter, lang=ru
        ▼
   текст → reply в тот же чат (до 3900 символов)
```

Параллельных расшифровок не больше трёх (семафор), чтобы CPU не умирал на длинных войсах.

## Быстрый старт (Docker)

1. Токен от [@BotFather](https://t.me/BotFather).
2. Настройка:
   ```bash
   cp .env.example .env
   # вставь BOT_TOKEN в .env
   # MODEL_SIZE=small (быстро) или medium (точнее для RU, ~1.5GB, медленнее)
   ```
3. Запуск:
   ```bash
   docker compose up --build -d && docker compose logs -f
   ```
   Первая загрузка модели `small` (~500MB) занимает несколько минут — это нормально.

## Добавление в группу

1. У BotFather: Bot Settings → Group Privacy → **OFF** (иначе бот не увидит войсы), Allow Groups → **ON**.
2. В группе: добавить участников → найти бота. Админка не нужна, хватает чтения сообщений.
3. ⚠️ Настройка приватности применяется в момент добавления: если менял её после — **удали бота из группы и добавь заново**.
4. Команды для `/setcommands` (каждая с новой строки):
   ```
   start - запуск бота
   help - помощь
   privacy - приватность
   ```

## Проверка

1. Личка: `/start` → войс 10с на русском → текст ответом.
2. Группа: войс → статус «⏳ Расшифровываю...» → ответ с текстом в чат.
3. Войс длиннее лимита → вежливый отказ.

## Локальный запуск без Docker

Нужны Python 3.11+ и `ffmpeg`:
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.main
```

## Настройки (`.env`)

| Переменная | Дефолт | Что значит |
|---|---|---|
| `BOT_TOKEN` | — | токен от BotFather |
| `MODEL_SIZE` | `small` | tiny / base / small / medium |
| `COMPUTE_TYPE` | `int8` | int8 для CPU |
| `MAX_DURATION_SEC` | `300` | отказ, если длиннее |
| `TMP_DIR` | `/tmp/voices` | временные файлы (чистятся сами) |
| `HF_HUB_CACHE` | авто | куда качать веса: `/data/hf_cache`, если есть персистентное хранилище (нужно на хостингах с маленьким эфемерным диском) |

## Структура

```
app/
  main.py      # polling, прогрев модели, graceful shutdown
  handlers.py  # /start /help /privacy + voice/audio/video_note
  stt.py       # faster-whisper + ffmpeg
  config.py    # pydantic-settings, всё из .env
Dockerfile
docker-compose.yml   # healthcheck, лимит памяти, кэш модели
.github/workflows/ci.yml
```

## Лицензия

MIT — см. [LICENSE](LICENSE).
