"""Проверка голоса с сервера: venv/bin/python test_voice.py
Создаёт озвучку, потом распознаёт её обратно — полный круг."""
import asyncio
import os

import voice


async def main() -> None:
    phrase = "Проверка связи. Новый закон о статусе вступил в силу."
    try:
        ogg = await voice.synthesize(phrase, "ru")
        size = os.path.getsize(ogg)
        print(f"TTS: OK, {size} байт -> {ogg}")
    except Exception as exc:  # noqa: BLE001
        print(f"TTS: FAIL {type(exc).__name__}: {str(exc)[:160]}")
        return
    try:
        text = await voice.transcribe_ogg(ogg)
        print(f"STT: OK | распознано: {text[:80]}")
    except Exception as exc:  # noqa: BLE001
        print(f"STT: FAIL {type(exc).__name__}: {str(exc)[:160]}")
    finally:
        if os.path.exists(ogg):
            os.remove(ogg)


asyncio.run(main())
