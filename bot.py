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

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def check_events():
    try:
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')  # работает без окна
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')

        driver = webdriver.Chrome(options=options)
        driver.get(MAIN_URL)

        # Ищем все спектакли
        events = driver.find_elements(By.CSS_SELECTOR, '.event-item')

        for event in events:
            title_elem = event.find_element(By.CSS_SELECTOR, '.event-title, h3, .title a')
            title = title_elem.text.strip()

            link_elem = event.find_element(By.TAG_NAME, 'a')
            event_url = link_elem.get_attribute('href')

            if not event_url.startswith('http'):
                event_url = 'https://quicktickets.ru' + event_url

            # Переходим на страницу мероприятия
            driver.get(event_url)

            # Ждём, пока загрузится план зала
            try:
                wait = WebDriverWait(driver, 10)
                seat_map = wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'seat-map')))
            except:
                continue

            # Находим свободное место (например, с классом "available")
            available_seat = driver.find_element(By.CSS_SELECTOR, '.seat.available')
            if not available_seat:
                continue

            # Нажимаем на свободное место
            available_seat.click()

            # Ждём, пока появится кнопка "Купить"
            try:
                buy_button = wait.until(EC.presence_of_element_located((By.XPATH, '//button[contains(text(), "Купить")]')))
                booking_url = buy_button.get_attribute('href') or event_url
                if not booking_url.startswith('http'):
                    booking_url = 'https://quicktickets.ru' + booking_url

                event_id = f"{title}|{booking_url}"
                if event_id not in notified_events:
                    return title, booking_url
            except:
                continue

        driver.quit()
        return None, None

    except Exception as e:
        print(f"❌ Ошибка при проверке: {e}")
        return None, None
        
async def main_bot():
    bot = Bot(token=TELEGRAM_TOKEN)
    
    # Тестовое сообщение
    try:
        await bot.send_message(chat_id=CHAT_ID, text="✅ Бот успешно запущен и мониторит билеты!")
        print("📩 Тестовое сообщение отправлено")
    except Exception as e:
        print(f"❌ Не удалось отправить тестовое сообщение: {e}")

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


