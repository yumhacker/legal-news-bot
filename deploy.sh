#!/usr/bin/env bash
# Деплой Legal News Bot на сервер. Запускать НА СЕРВЕРЕ от root:
#   bash /opt/legal_news_bot/deploy.sh
# Идемпотентный: можно запускать повторно при обновлении кода.
# Старых ботов на сервере не трогает.
set -euo pipefail

DIR=/opt/legal_news_bot
SERVICE=legal-news-bot

echo "== Legal News Bot: деплой в $DIR =="

if [ ! -f "$DIR/bot.py" ]; then
  echo "ОШИБКА: файлы бота не найдены в $DIR (сначала scp)" >&2
  exit 1
fi

echo "-- Swap (защита от Out of memory: на сервере замечены OOM-киллы python)"
if ! swapon --show 2>/dev/null | grep -q '^'; then
  fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "   swap 2G создан и включён"
else
  echo "   swap уже есть"
fi

echo "-- Пакеты системы (python3-venv + ffmpeg для голоса)"
apt-get update -qq
apt-get install -y -qq python3-venv ffmpeg >/dev/null

echo "-- Пользователь botuser"
id -u botuser >/dev/null 2>&1 || useradd -r -m botuser

echo "-- Виртуальное окружение и зависимости"
cd "$DIR"
[ -d venv ] || python3 -m venv venv
venv/bin/pip install --quiet --upgrade pip
venv/bin/pip install --quiet -r requirements.txt

echo "-- Права"
chown -R botuser:botuser "$DIR"
chmod 600 "$DIR/.env"

echo "-- Сервис systemd"
cp "$DIR/$SERVICE.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null
systemctl restart "$SERVICE"

sleep 3
echo
systemctl --no-pager --full status "$SERVICE" | head -12 || true
echo
if systemctl is-active --quiet "$SERVICE"; then
  echo "== ГОТОВО: бот запущен. Логи: journalctl -u $SERVICE -f =="
else
  echo "== ПРОБЛЕМА: сервис не стартовал. Логи: journalctl -u $SERVICE -n 50 =="
  exit 1
fi
