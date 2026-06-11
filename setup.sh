#!/usr/bin/env bash
set -e
cd /opt
wget -qO main.tgz https://github.com/yumhacker/legal-news-bot/archive/refs/heads/main.tar.gz
mkdir -p legal_news_bot
tar xzf main.tgz
cp -r legal-news-bot-main/. legal_news_bot/
touch legal_news_bot/.env
bash legal_news_bot/deploy.sh || true
echo SETUP-DONE
