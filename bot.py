"""Telegram-бот: мониторинг МВД Израиля (новости, процедуры) и законов Кнессета.

Доступ только для ID из ALLOWED_USER_IDS (.env). Остальным — отказ.
Кнопки: последние 5 элементов каждого источника со ссылками.
Фон: раз в WATCH_INTERVAL_MIN минут проверяет обновления и шлёт их
в Telegram (всем разрешённым) и на email.

Запуск: python bot.py
"""
import asyncio
import html
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config
import sources
import storage
from notifier import email_enabled, send_email

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("bot")

# --- Источники: ключ -> (название, функция) ---
SOURCES = {
    "news": ("🗞 Новости МВД", sources.fetch_news),
    "procedures": ("📋 Процедуры МВД (נהלים)", sources.fetch_procedures),
    "laws": ("⚖️ Принятые законы Кнессета", sources.fetch_laws),
}

# --- Доступ: свои пользователи в личке ИЛИ в разрешённой группе ---

def _chat_ok(chat) -> bool:
    return chat.type == "private" or storage.is_chat_allowed(chat.id)


def _msg_allowed(m: Message) -> bool:
    return (
        m.from_user is not None
        and m.from_user.id in config.ALLOWED_USER_IDS
        and _chat_ok(m.chat)
    )


def _cb_allowed(cb: CallbackQuery) -> bool:
    return (
        cb.from_user.id in config.ALLOWED_USER_IDS
        and cb.message is not None
        and _chat_ok(cb.message.chat)
    )


# admin_router — только команды управления группами (только Марина)
admin_router = Router()
admin_router.message.filter(
    lambda m: m.from_user is not None and m.from_user.id == config.ADMIN_ID
)

main_router = Router()
main_router.message.filter(_msg_allowed)
main_router.callback_query.filter(_cb_allowed)

denied_router = Router()


def main_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=title, callback_data=f"src:{key}")]
        for key, (title, _) in SOURCES.items()
    ]
    rows.append(
        [InlineKeyboardButton(text="🔄 Проверить все источники", callback_data="src:all")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_items(title: str, items: list[dict], header: str | None = None) -> str:
    lines = [header or f"<b>{title}</b> — последние {len(items)}:"]
    for i, it in enumerate(items, 1):
        name = html.escape(it["title"])
        link = f'<a href="{it["url"]}">{name}</a>' if it.get("url") else name
        lines.append(f"\n{i}. {link}")
        meta = " · ".join(x for x in (it.get("date", ""), it.get("extra", "")) if x)
        if meta:
            lines.append(f"<i>{html.escape(meta)}</i>")
    return "\n".join(lines)


# ===================== Управление группами (только админ) =====================

@admin_router.message(Command("allowchat"))
async def cmd_allowchat(message: Message) -> None:
    if message.chat.type == "private":
        await message.answer(
            "Эту команду нужно отправить В ГРУППЕ, которую хочешь подключить."
        )
        return
    storage.add_chat(message.chat.id)
    log.info("Группа разрешена: %s (%s)", message.chat.id, message.chat.title)
    await message.answer(
        "✅ Группа подключена. Теперь я отвечаю здесь тебе и Далеру "
        "и буду присылать сюда новые обновления.\nОтключить: /denychat"
    )


@admin_router.message(Command("denychat"))
async def cmd_denychat(message: Message) -> None:
    if message.chat.type == "private":
        await message.answer("Эту команду нужно отправить в группе.")
        return
    storage.remove_chat(message.chat.id)
    await message.answer("Группа отключена. Вернуть: /allowchat")


# ============================ Команды и кнопки ============================

@main_router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Шалом! Я слежу за обновлениями для юридической практики:\n"
        "• новости МВД (רשות האוכלוסין וההגירה)\n"
        "• процедуры МВД (נהלים)\n"
        "• принятые законы Кнессета\n\n"
        "Нажми кнопку — пришлю последние 5 со ссылками.",
        reply_markup=main_kb(),
    )


@main_router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    watch = (
        f"каждые {config.WATCH_INTERVAL_MIN} мин"
        if config.WATCH_INTERVAL_MIN > 0
        else "выключен"
    )
    await message.answer(
        "/start — меню с кнопками\n"
        "/id — показать свой Telegram ID и ID чата\n"
        "/allowchat — (админ, в группе) разрешить боту работать в группе\n"
        "/denychat — (админ, в группе) отключить группу\n\n"
        f"Автомониторинг: {watch}.\n"
        f"Email-уведомления: {'включены, ' + config.EMAIL_TO if email_enabled() else 'выключены'}.",
        reply_markup=main_kb(),
    )


@main_router.message(Command("id"))
async def cmd_id(message: Message) -> None:
    await message.answer(
        f"Твой Telegram ID: <code>{message.from_user.id}</code>\n"
        f"ID этого чата: <code>{message.chat.id}</code>"
    )


@main_router.callback_query(F.data.startswith("src:"))
async def on_source_button(cb: CallbackQuery) -> None:
    key = cb.data.split(":", 1)[1]
    await cb.answer("Проверяю…")
    keys = list(SOURCES) if key == "all" else [key]
    for k in keys:
        title, fetcher = SOURCES[k]
        try:
            items = await fetcher(limit=5)
            text = (
                format_items(title, items)
                if items
                else f"<b>{title}</b>: ничего не найдено."
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("Ошибка источника %s", k)
            text = (
                f"⚠️ <b>{title}</b>: источник не ответил "
                f"({type(exc).__name__}). Попробуй позже."
            )
        await cb.message.answer(text, disable_web_page_preview=True)


# ============================ Чужим — отказ ============================

@denied_router.my_chat_member()
async def on_added_to_chat(event: ChatMemberUpdated) -> None:
    """Бота добавили/изменили в каком-то чате."""
    chat = event.chat
    if chat.type == "private":
        return
    new_status = event.new_chat_member.status
    if new_status in ("left", "kicked"):
        storage.remove_chat(chat.id)
        return
    # Добавил кто-то чужой → сразу выходим. Свои — даём время на /allowchat.
    if event.from_user and event.from_user.id in config.ALLOWED_USER_IDS:
        log.info("Добавлена в чат %s (%s) своим — жду /allowchat", chat.id, chat.title)
        return
    if not storage.is_chat_allowed(chat.id):
        log.warning("Чужой чат %s (%s) — выхожу", chat.id, chat.title)
        await event.bot.leave_chat(chat.id)


@denied_router.message()
async def denied_message(message: Message) -> None:
    uid = message.from_user.id if message.from_user else "?"
    if message.chat.type == "private":
        log.warning("Отказ в доступе: id=%s", uid)
        await message.answer("⛔ Это закрытый бот.")
        return
    # Группа: не разрешена → выходим; разрешена, но пишет чужой → молчим
    if not storage.is_chat_allowed(message.chat.id):
        log.warning("Сообщение из чужого чата %s — выхожу", message.chat.id)
        await message.bot.leave_chat(message.chat.id)


@denied_router.callback_query()
async def denied_callback(cb: CallbackQuery) -> None:
    await cb.answer("⛔ Нет доступа", show_alert=True)


# ============================ Фоновый мониторинг ============================

async def check_updates(bot: Bot) -> None:
    for key, (title, fetcher) in SOURCES.items():
        try:
            items = await fetcher(limit=10)
        except Exception:  # noqa: BLE001
            log.exception("Мониторинг: источник %s не ответил", key)
            continue

        first_run = not storage.has_any(key)
        fresh = []
        for it in items:
            if not storage.is_seen(key, it["id"]):
                storage.mark_seen(key, it["id"])
                if not first_run:
                    fresh.append(it)

        if first_run:
            log.info("Мониторинг %s: первый прогон, запомнено %d", key, len(items))
        if not fresh:
            continue

        text = format_items(title, fresh, header=f"🔔 <b>{title}</b> — обновление!")
        recipients = list(config.ALLOWED_USER_IDS) + storage.all_chats()
        for chat_id in recipients:
            try:
                await bot.send_message(chat_id, text, disable_web_page_preview=True)
            except Exception:  # noqa: BLE001
                log.exception("Не доставлено в чат %s", chat_id)
        await asyncio.to_thread(send_email, f"Обновление: {title}", text)


async def watcher(bot: Bot) -> None:
    if config.WATCH_INTERVAL_MIN <= 0:
        log.info("Автомониторинг выключен (WATCH_INTERVAL_MIN=0)")
        return
    log.info("Автомониторинг: каждые %d мин", config.WATCH_INTERVAL_MIN)
    while True:
        try:
            await check_updates(bot)
        except Exception:  # noqa: BLE001
            log.exception("Сбой цикла мониторинга")
        await asyncio.sleep(config.WATCH_INTERVAL_MIN * 60)


# ============================ Запуск ============================

async def main() -> None:
    if not config.ALLOWED_USER_IDS:
        raise SystemExit("ALLOWED_USER_IDS пуст — заполни .env")
    storage.init()
    bot = Bot(
        config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(admin_router)
    dp.include_router(main_router)
    dp.include_router(denied_router)
    log.info("Бот запущен. Доступ: %s", sorted(config.ALLOWED_USER_IDS))
    watcher_task = asyncio.create_task(watcher(bot))
    try:
        await dp.start_polling(bot)
    finally:
        # без этого процесс не завершается по SIGTERM и systemd ждёт 90 сек
        watcher_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
