# Legal News Bot — деплой и использование

Telegram-бот для юридической практики: по кнопке выдаёт последние 5 обновлений
из трёх источников + сам проверяет их каждые 30 минут и присылает новое.

| Источник | Откуда |
|---|---|
| 🗞 Новости МВД | gov.il, רשות האוכלוסין וההגירה |
| 📋 Процедуры МВД (נהלים) | gov.il, раздел policies |
| ⚖️ Принятые законы | API Кнессета (OData) |

**Доступ:** только Марина (840632048) и адвокат @yusupov_daler_law (944319573).
Остальным бот отвечает «⛔ Это закрытый бот».

## Файлы

- `bot.py` — сам бот (кнопки + фоновый мониторинг)
- `sources.py` — запросы к gov.il и Кнессету
- `config.py`, `.env` — настройки (токен, ID, email)
- `storage.py` — SQLite-память «что уже видели» (создаётся сама)
- `notifier.py` — email через Gmail
- `legal-news-bot.service` — автозапуск через systemd

## Деплой на сервер (Ubuntu/Debian)

```bash
# 1. Зависимости системы
sudo apt update && sudo apt install -y python3 python3-venv

# 2. Папка и пользователь
sudo useradd -r -m botuser 2>/dev/null || true
sudo mkdir -p /opt/legal_news_bot
# скопировать сюда все файлы проекта (scp/sftp), затем:
sudo chown -R botuser:botuser /opt/legal_news_bot
sudo chmod 600 /opt/legal_news_bot/.env

# 3. Виртуальное окружение
cd /opt/legal_news_bot
sudo -u botuser python3 -m venv venv
sudo -u botuser venv/bin/pip install -r requirements.txt

# 4. Пробный запуск (Ctrl+C чтобы остановить)
sudo -u botuser venv/bin/python bot.py

# 5. Автозапуск
sudo cp legal-news-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now legal-news-bot
systemctl status legal-news-bot        # проверка
journalctl -u legal-news-bot -f        # логи
```

## Включить email-уведомления (опционально)

Бот шлёт письма на `EMAIL_TO` (ydaler@gmail.com) при каждом обновлении.
Нужен gmail-аккаунт-отправитель:

1. На аккаунте-отправителе включить двухфакторную аутентификацию.
2. Создать «пароль приложения»: https://myaccount.google.com/apppasswords
3. Вписать в `.env`: `GMAIL_FROM=адрес@gmail.com`, `GMAIL_APP_PASSWORD=пароль`.
4. `sudo systemctl restart legal-news-bot`

Пока поля пустые — email просто отключён, всё остальное работает.

## Команды бота

- `/start` — меню с кнопками
- `/help` — статус мониторинга и email
- `/id` — показать свой Telegram ID (чтобы добавить нового человека в `.env`)

Добавить человека: вписать его ID в `ALLOWED_USER_IDS` через запятую и
перезапустить сервис.

## Важно

- **Токен бота** лежит в `.env` — не выкладывать файл никуда. Если токен
  засветился, замени его у @BotFather (`/revoke`) и обнови `.env`.
- Если МВД сменит публичный ключ фронтенда (`x-client-id` в `sources.py`),
  бот начнёт писать «источник не ответил» — ключ выкавливается заново за
  5 минут через DevTools на странице новостей gov.il.
- Если в «Законах Кнессета» будет пусто или мусор — поменяй `LAW_STATUS_ID`
  в `.env` (справочник статусов: таблица KNS_Status в том же OData).
