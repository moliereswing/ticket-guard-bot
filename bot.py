import asyncio
import time
import requests
from bs4 import BeautifulSoup
from telegram import Bot
from telegram.error import TelegramError
import os
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '8286251093:AAHmfYAWQFZksTFvmKY29wG_xMTCapFmau0')
CHAT_ID = os.getenv('CHAT_ID', '8286251093')

MAIN_URL = 'https://quicktickets.ru/orel-teatr-svobodnoe-prostranstvo'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
}

notified_events = set()

async def send_alert(bot, event_name, booking_url):
    message = (
        f"🎫 *ПОЯВИЛИСЬ БИЛЕТЫ!* \n\n"
        f"🎭 *Спектакль:* {event_name}\n"
        f"🔗 [Перейти к выбору мест]({booking_url})\n\n"
        f"⏳ Бронируй скорее — ажиотаж большой!"
    )
    try:
        await bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode='Markdown',
            disable_web_page_preview=False
        )
        print(f"✅ Отправлено: {event_name}")
    except TelegramError as e:
        print(f"❌ Ошибка Telegram: {e}")
    except Exception as e:
        print(f"❌ Неизвестная ошибка: {e}")

def check_events():
    try:
        response = requests.get(MAIN_URL, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'lxml')

        events = soup.select('.event-item')

        for event in events:
            title_elem = event.select_one('.event-title, h3, .title a')
            if not title_elem:
                continue
            title = title_elem.get_text(strip=True)

            link_elem = event.select_one('a[href*="/event/"]')
            if not link_elem or not link_elem.get('href'):
                continue

            event_url = link_elem['href']
            if not event_url.startswith('http'):
                event_url = 'https://quicktickets.ru' + event_url

            event_page = requests.get(event_url, headers=HEADERS, timeout=10)
            event_soup = BeautifulSoup(event_page.text, 'lxml')

            buy_button = event_soup.select_one('.buy-btn, .btn-buy, a[href*="/booking/"]')
            if not buy_button:
                continue

            booking_url = buy_button['href'] if buy_button.name == 'a' else event_url
            if not booking_url.startswith('http'):
                booking_url = 'https://quicktickets.ru' + booking_url

            event_id = f"{title}|{booking_url}"

            if event_id not in notified_events:
                return title, booking_url

        return None, None

    except Exception as e:
        print(f"❌ Ошибка при проверке: {e}")
        return None, None

async def main_bot():
    bot = Bot(token=TELEGRAM_TOKEN)
    print("🚀 Бот запущен. Мониторим билеты...")

    while True:
        title, booking_url = check_events()
        if title and booking_url:
            await send_alert(bot, title, booking_url)
            notified_events.add(f"{title}|{booking_url}")

        print("💤 Сплю 30 секунд...")
        await asyncio.sleep(30)

# 🌐 Фиктивный веб-сервер для Render (чтобы не было ошибки "No open ports")
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"🌐 Health server running on port {port}")
    server.serve_forever()

if __name__ == '__main__':
    # Запускаем веб-сервер в фоновом потоке
    Thread(target=run_health_server, daemon=True).start()
    # Запускаем основной бот
    asyncio.run(main_bot())
