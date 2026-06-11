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

import ai
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
    # «Решения судов» (spokmanship_court): www.gov.il блокирует серверные IP
    # даже через прокси — источник отключён до решения проблемы доступа.
}

LAWYER_SYSTEM = (
    "Ты — ассистент израильского адвоката Далера Юсупова "
    "(иммиграционное право Израиля, статус, гражданство, процедуры МВД). "
    "Отвечай по-русски, юридически аккуратно, без выдумок: если данных не "
    "хватает или не уверен — прямо скажи. Иврит цитируй с переводом."
)

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
        "/start — меню с кнопками (последние обновления)\n\n"
        "🤖 ИИ:\n"
        "/ai вопрос — спросить ИИ (или ответом на новость)\n"
        "/post — ответь этим на новость → готовый пост; "
        "<code>/post для инстаграма</code>\n"
        "/idea тема — идеи постов и видео\n"
        "/model — выбрать Claude/GPT и включить интернет-поиск\n\n"
        "✍️ Стиль Далера:\n"
        "/style_add — добавить пример текста (ответом или после команды)\n"
        "/style — что сохранено · /style_clear — очистить (админ)\n\n"
        "⚙️ Прочее:\n"
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


# ============================ ИИ-команды ============================

def _arg(message: Message) -> str:
    """Текст после команды."""
    parts = (message.text or "").split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""

def _material(message: Message) -> str:
    """Текст сообщения, на которое ответили командой."""
    r = message.reply_to_message
    if not r:
        return ""
    try:
        return r.html_text or r.text or r.caption or ""
    except Exception:  # noqa: BLE001
        return r.text or r.caption or ""

def _style_block() -> str:
    s = storage.get_style()
    if not s:
        return ""
    return (
        "\n\nНиже — информация о практике Далера и примеры его текстов. "
        "Пиши посты, подражая этому стилю:\n" + s
    )

async def _run_ai(message: Message, user_prompt: str, use_style: bool) -> None:
    chat_id = message.chat.id
    model_key = storage.get_setting(chat_id, "model", ai.DEFAULT_MODEL_KEY)
    if model_key not in ai.MODELS:
        model_key = ai.DEFAULT_MODEL_KEY
    online = storage.get_setting(chat_id, "web", "0") == "1"
    system = LAWYER_SYSTEM + (_style_block() if use_style else "")
    note = await message.answer(
        f"⏳ {ai.MODELS[model_key][0]}{' 🌐' if online else ''} думает…"
    )
    try:
        text = await ai.ask(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            model_key,
            online,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("Ошибка ИИ")
        await note.edit_text(f"⚠️ Ошибка ИИ: {exc}")
        return
    try:
        await note.delete()
    except Exception:  # noqa: BLE001
        pass
    for i in range(0, len(text), 3800):
        await message.answer(
            text[i : i + 3800], parse_mode=None, disable_web_page_preview=True
        )

@main_router.message(Command("ai"))
async def cmd_ai(message: Message) -> None:
    q, mat = _arg(message), _material(message)
    if not q and not mat:
        await message.answer(
            "Напиши вопрос после команды: <code>/ai твой вопрос</code>\n"
            "Или ответь командой /ai на сообщение с новостью."
        )
        return
    prompt = (f"Материал:\n{mat}\n\n" if mat else "") + (
        q or "Прочитай материал и кратко объясни суть и значение для клиентов."
    )
    await _run_ai(message, prompt, use_style=False)

@main_router.message(Command("post"))
async def cmd_post(message: Message) -> None:
    mat, spec = _material(message), _arg(message)
    if not mat and not spec:
        await message.answer(
            "Как пользоваться:\n"
            "• ответь командой /post на сообщение с новостью — напишу пост по ней;\n"
            "• можно уточнить: <code>/post для инстаграма, коротко</code>\n"
            "• или без reply: <code>/post тема поста</code>"
        )
        return
    target = spec or "Telegram-канала"
    prompt = (
        (f"Материал (новость/решение/тема):\n{mat}\n\n" if mat else "")
        + f"Задание: напиши пост для {target}. "
        "Пиши на русском, в стиле Далера (если примеры приложены), с цепляющим "
        "началом и практическим выводом для людей, которых это касается. "
        "Если в материале есть ссылка и у тебя есть доступ в интернет — изучи её. "
        "В конце уместен короткий дисклеймер, что пост не заменяет консультацию."
    )
    await _run_ai(message, prompt, use_style=True)

@main_router.message(Command("idea"))
async def cmd_idea(message: Message) -> None:
    topic = _arg(message) or _material(message)
    if not topic:
        await message.answer("Укажи тему: <code>/idea выдворение и статус</code>")
        return
    prompt = (
        f"Тема/материал:\n{topic}\n\n"
        "Предложи 5 идей постов или коротких видео для соцсетей адвоката: "
        "для каждой — рабочий заголовок и 2–3 тезиса. Идеи практичные, "
        "из жизни клиентов (статус, МВД, суды), без воды."
    )
    await _run_ai(message, prompt, use_style=True)

@main_router.message(Command("style"))
async def cmd_style(message: Message) -> None:
    n = storage.style_count()
    s = storage.get_style(1500)
    if not n:
        await message.answer(
            "Стиль пока пуст. Добавь примеры текстов Далера:\n"
            "• ответь командой /style_add на сообщение с текстом поста,\n"
            "• или <code>/style_add текст…</code>\n"
            "Туда же можно добавить описание: какими делами занимается Далер."
        )
        return
    await message.answer(
        f"Сохранено фрагментов: {n}. Последние:\n\n{html.escape(s[-1500:])}",
        parse_mode=None,
    )

@main_router.message(Command("style_add"))
async def cmd_style_add(message: Message) -> None:
    text = _arg(message) or _material(message)
    if not text:
        await message.answer(
            "Ответь командой /style_add на сообщение с текстом "
            "или напиши текст после команды."
        )
        return
    n = storage.add_style(text)
    await message.answer(f"✅ Добавлено в стиль. Всего фрагментов: {n}.")

@main_router.message(Command("style_clear"))
async def cmd_style_clear(message: Message) -> None:
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("Очищать стиль может только админ.")
        return
    storage.clear_style()
    await message.answer("Стиль очищен.")

def _model_kb(chat_id: int) -> InlineKeyboardMarkup:
    current = storage.get_setting(chat_id, "model", ai.DEFAULT_MODEL_KEY)
    online = storage.get_setting(chat_id, "web", "0") == "1"
    rows = [
        [
            InlineKeyboardButton(
                text=("✅ " if key == current else "") + label,
                callback_data=f"mdl:{key}",
            )
        ]
        for key, (label, _) in ai.MODELS.items()
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=f"🌐 Интернет-поиск: {'ВКЛ' if online else 'выкл'}",
                callback_data="mdl:web",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)

@main_router.message(Command("model"))
async def cmd_model(message: Message) -> None:
    await message.answer(
        "Какая модель отвечает на /ai, /post, /idea в этом чате:",
        reply_markup=_model_kb(message.chat.id),
    )

@main_router.callback_query(F.data.startswith("mdl:"))
async def on_model_button(cb: CallbackQuery) -> None:
    chat_id = cb.message.chat.id
    val = cb.data.split(":", 1)[1]
    if val == "web":
        cur = storage.get_setting(chat_id, "web", "0") == "1"
        storage.set_setting(chat_id, "web", "0" if cur else "1")
    elif val in ai.MODELS:
        storage.set_setting(chat_id, "model", val)
    try:
        await cb.message.edit_reply_markup(reply_markup=_model_kb(chat_id))
    except Exception:  # noqa: BLE001
        pass
    await cb.answer("Сохранено")


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
