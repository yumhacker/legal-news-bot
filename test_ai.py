"""Проверка OpenRouter с сервера: venv/bin/python test_ai.py"""
import asyncio

import ai


async def main() -> None:
    for key in ai.MODELS:
        try:
            out = await ai.ask(
                [{"role": "user", "content": "Ответь одним словом: работаю"}],
                key,
                online=False,
                max_tokens=300,
            )
            print(f"{key}: OK | {out.strip()[:40]}")
        except Exception as exc:  # noqa: BLE001
            print(f"{key}: FAIL {type(exc).__name__}: {str(exc)[:100]}")


asyncio.run(main())
