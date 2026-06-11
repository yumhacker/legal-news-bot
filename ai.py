"""Клиент OpenRouter: несколько моделей Claude/GPT + интернет-поиск (:online)."""
import base64

import aiohttp

import config

API_URL = "https://openrouter.ai/api/v1/chat/completions"

# key -> (название для меню, id модели на OpenRouter)
MODELS = {
    "claude": ("Claude Opus 4.8 (умный)", "anthropic/claude-opus-4.8"),
    "claude-fast": ("Claude Opus 4.8 Fast", "anthropic/claude-opus-4.8-fast"),
    "gpt": ("GPT-5.5", "openai/gpt-5.5"),
    "gpt-mini": ("GPT-5.4 Mini (дешёвый)", "openai/gpt-5.4-mini"),
}
DEFAULT_MODEL_KEY = "claude-fast"

# Модель для распознавания речи (поддерживает аудио-вход)
STT_MODEL = "google/gemini-3.1-flash-lite"


class AIError(Exception):
    pass


async def ask(
    messages: list[dict],
    model_key: str = DEFAULT_MODEL_KEY,
    online: bool = False,
    max_tokens: int = 2500,
) -> str:
    if not config.OPENROUTER_API_KEY:
        raise AIError("OPENROUTER_API_KEY не задан в .env")
    _, model_id = MODELS.get(model_key, MODELS[DEFAULT_MODEL_KEY])
    if online:
        model_id += ":online"  # включает веб-поиск на стороне OpenRouter
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/yumhacker/legal-news-bot",
        "X-Title": "Legal News Bot",
    }
    payload = {"model": model_id, "messages": messages, "max_tokens": max_tokens}
    timeout = aiohttp.ClientTimeout(total=240)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(API_URL, json=payload, headers=headers) as resp:
            data = await resp.json(content_type=None)
    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        raise AIError(msg[:300])
    try:
        msg = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        raise AIError(f"Неожиданный ответ OpenRouter: {str(data)[:200]}")
    content = msg.get("content") or msg.get("reasoning") or ""
    if not str(content).strip():
        raise AIError("Модель вернула пустой ответ — попробуй ещё раз или /model")
    return str(content)


async def transcribe(mp3_bytes: bytes) -> str:
    """Распознать речь из mp3 через аудио-модель OpenRouter."""
    if not config.OPENROUTER_API_KEY:
        raise AIError("OPENROUTER_API_KEY не задан в .env")
    b64 = base64.b64encode(mp3_bytes).decode()
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Дословно расшифруй речь из этой аудиозаписи. "
                        "Верни ТОЛЬКО текст сказанного, без комментариев. "
                        "Язык может быть русским, ивритом или их смесью."
                    ),
                },
                {
                    "type": "input_audio",
                    "input_audio": {"data": b64, "format": "mp3"},
                },
            ],
        }
    ]
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/yumhacker/legal-news-bot",
        "X-Title": "Legal News Bot",
    }
    payload = {"model": STT_MODEL, "messages": messages, "max_tokens": 1500}
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(API_URL, json=payload, headers=headers) as resp:
            data = await resp.json(content_type=None)
    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        raise AIError(msg[:300])
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise AIError(f"Не удалось распознать: {str(data)[:200]}")
    return str(text or "").strip()
