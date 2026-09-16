"""STT на faster-whisper + конвертация ogg->wav через ffmpeg."""
import logging
import os
import subprocess
from pathlib import Path

from faster_whisper import WhisperModel

from app.config import settings

log = logging.getLogger(__name__)

_model: WhisperModel | None = None


def _cache_dir() -> str | None:
    """Куда класть веса модели.

    Приоритет: HF_HUB_CACHE/HF_HOME из окружения → /data/hf_cache если есть
    персистентное хранилище (Amvera: эфемерный слой всего ~400Mi, модель
    small ~500Mi туда не влезает) → иначе дефолт huggingface.
    """
    env = os.environ.get("HF_HUB_CACHE") or os.environ.get("HF_HOME")
    if env:
        return env
    if Path("/data").is_dir():
        return "/data/hf_cache"
    return None


def get_model() -> WhisperModel:
    global _model
    if _model is None:
        cache = _cache_dir()
        log.info(
            "Загрузка Whisper модели %s (%s), кэш=%s...",
            settings.MODEL_SIZE, settings.COMPUTE_TYPE, cache or "дефолтный",
        )
        _model = WhisperModel(
            settings.MODEL_SIZE, device="cpu",
            compute_type=settings.COMPUTE_TYPE, download_root=cache,
            # меньше потоков — ниже пиковая RAM (важно на тарифах 1 ГБ)
            cpu_threads=2, num_workers=1,
        )
        log.info("Модель загружена")
    return _model


def convert_to_wav(src: Path, dst: Path, timeout: int = 60) -> None:
    """Voice (ogg/opus), кружок (mp4), аудио (mp3/m4a) -> wav 16k mono.

    src — нейтральное имя (.bin), т.к. формат разный, ffmpeg сам детектит.
    """
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
        str(dst),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"ffmpeg timeout ({timeout}s): {e}")
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {res.stderr[-1000:]}")


def transcribe_wav(wav_path: Path, language: str = "ru") -> str:
    """Блокирующий вызов — запускать через asyncio.to_thread."""
    model = get_model()
    segments, info = model.transcribe(
        str(wav_path),
        language=language,
        # beam уже: 5 -> 3 заметно режет пик RAM, качество почти не падает;
        # greedy (1) — крайний вариант если 1 ГБ всё равно мало
        beam_size=3,
        # короткий fallback по температуре вместо длинного — меньше повторов декода
        temperature=(0.0, 0.2),
        # подсказка модели: какой текст ожидать (заметно чистит русский)
        initial_prompt="Это расшифровка голосового сообщения на русском языке.",
        condition_on_previous_text=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )
    log.info("Распознано, язык=%s prob=%.2f", info.language, info.language_probability)
    text = " ".join(s.text.strip() for s in segments).strip()
    return text
