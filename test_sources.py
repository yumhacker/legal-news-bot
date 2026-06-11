"""Проверка всех трёх источников с сервера: venv/bin/python test_sources.py"""
import asyncio

import sources


async def main() -> None:
    checks = [
        ("news", sources.fetch_news),
        ("procedures", sources.fetch_procedures),
        ("laws", sources.fetch_laws),
    ]
    for name, fn in checks:
        try:
            items = await fn(limit=3)
            first = items[0]["title"][:40] if items else "(пусто)"
            print(f"{name}: OK, {len(items)} шт. | {first}")
        except Exception as exc:  # noqa: BLE001
            print(f"{name}: FAIL {type(exc).__name__}: {str(exc)[:120]}")


asyncio.run(main())
