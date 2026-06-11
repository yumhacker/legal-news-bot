"""Голос: распознавание (через ai.transcribe) и озвучка (edge-tts).

Требует системный ffmpeg и pip-пакет edge-tts.
"""
import asyncio
import os
import tempfile

import edge_tts

import ai

# Нейронные голоса Microsoft (бесплатные, без ключа)
VOICES = {
    "ru": "ru-RU-SvetlanaNeural",
    "he": "he-IL-HilaNeural",
}


async def _run(*args: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg: {err.decode()[:200]}")


async def transcribe_ogg(ogg_path: str) -> str:
    """Telegram-голосовое (.oga/ogg-opus) -> текст."""
    mp3_path = ogg_path + ".mp3"
    try:
        await _run("ffmpeg", "-y", "-i", ogg_path, "-ar", "16000", "-ac", "1", mp3_path)
        with open(mp3_path, "rb") as f:
            mp3 = f.read()
        return await ai.transcribe(mp3)
    finally:
        if os.path.exists(mp3_path):
            os.remove(mp3_path)


def detect_lang(text: str) -> str:
    """Грубое определение: если много ивритских букв — he, иначе ru."""
    heb = sum(1 for c in text if "֐" <= c <= "׿")
    return "he" if heb > len(text) * 0.3 else "ru"


async def synthesize(text: str, lang: str = "ru") -> str:
    """Текст -> путь к ogg/opus (готов для отправки как голосовое).

    Вызывающий обязан удалить файл после отправки."""
    if lang not in VOICES:
        lang = "ru"
    # edge-tts ограничим по длине, чтобы голосовое не было гигантским
    snippet = text.strip()[:2500]
    fd, mp3_path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    ogg_path = mp3_path + ".ogg"
    try:
        communicate = edge_tts.Communicate(snippet, VOICES[lang])
        await communicate.save(mp3_path)
        await _run(
            "ffmpeg", "-y", "-i", mp3_path,
            "-c:a", "libopus", "-b:a", "32k", ogg_path,
        )
        return ogg_path
    finally:
        if os.path.exists(mp3_path):
            os.remove(mp3_path)
