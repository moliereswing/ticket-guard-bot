import time
import os
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram.ext import Updater, CommandHandler
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '8286251093:AAHmfYAWQFZksTFvmKY29wG_xMTCapFmau0')
SUBSCRIBERS_FILE = 'subscribers.txt'

# Создаём файл, если его нет
if not os.path.exists(SUBSCRIBERS_FILE):
    open(SUBSCRIBERS_FILE, 'w').close()

notified_events = set()

def send_alert_to_all(bot, event_name, booking_url):
    message = (
        f"🎫 *ПОЯВИЛИСЬ БИЛЕТЫ!* \n\n"
        f"🎭 *Спектакль:* {event_name}\n"
        f"🔗 [Перейти к выбору мест]({booking_url})\n\n"
        f"⏳ Бронируй скорее — ажиотаж большой!"
    )

    # Читаем всех подписчиков
    with open(SUBSCRIBERS_FILE, 'r', encoding='utf-8') as f:
        chat_ids = set(line.strip() for line in f if line.strip())

    for chat_id in chat_ids:
        try:
            bot.send_message(
                chat_id=int(chat_id),
                text=message,
                parse_mode='Markdown',
                disable_web_page_preview=False
            )
            print(f"✅ Отправлено: {event_name} → {chat_id}")
        except Exception as e:
            print(f"❌ Ошибка при отправке {chat_id}: {e}")

def start(update, context):
    chat_id = str(update.message.chat_id)
    user_name = update.message.from_user.first_name

    with open(SUBSCRIBERS_FILE, 'r', encoding='utf-8') as f:
        subscribers = set(line.strip() for line in f)

    if chat_id not in subscribers:
        subscribers.add(chat_id)
        with open(SUBSCRIBERS_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(subscribers))
        update.message.reply_text("✅ Ты подписан(а) на уведомления о билетах!")
        print(f"📩 Новый подписчик: {user_name} ({chat_id})")
    else:
        update.message.reply_text("Ты уже подписан(а) на уведомления.")

def check_events():
    try:
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--remote-debugging-port=9222')

        # ✅ Правильный импорт и использование Service
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        MAIN_URL = 'https://quicktickets.ru/orel-teatr-svobodnoe-prostranstvo'
        driver.get(MAIN_URL)

        events = driver.find_elements(By.CSS_SELECTOR, '.event-item')

        for event in events:
            try:
                title_elem = event.find_element(By.CSS_SELECTOR, '.event-title, h3, .title a')
                title = title_elem.text.strip()

                link_elem = event.find_element(By.TAG_NAME, 'a')
                event_url = link_elem.get_attribute('href')
                if not event_url.startswith('http'):
                    event_url = 'https://quicktickets.ru' + event_url

                # Переходим на страницу мероприятия
                driver.get(event_url)

                # Ждём загрузки дат
                wait = WebDriverWait(driver, 10)
                date_items = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, '.date')))

                for date_item in date_items:
                    try:
                        # Ищем элемент с датой и временем
                        date_text_elem = date_item.find_element(By.CSS_SELECTOR, '.date__text')
                        date_text = date_text_elem.text.strip()

                        # Проверяем цвет текста — если не серый, значит билеты есть
                        # Серый текст: color: #888 или opacity: 0.5 — зависит от сайта
                        style = date_text_elem.get_attribute('style') or ''
                        computed_color = driver.execute_script(
                            "return window.getComputedStyle(arguments[0]).color;", date_text_elem
                        )

                        # Если текст не серый — билеты есть
                        if 'rgb(136, 136, 136)' not in computed_color and 'opacity: 0.5' not in style:
                            print(f"🎉 Найдены билеты: {title} — {date_text}")

                            # Получаем ссылку на бронирование
                            booking_link = date_item.find_element(By.TAG_NAME, 'a')
                            booking_url = booking_link.get_attribute('href')
                            if not booking_url.startswith('http'):
                                booking_url = 'https://quicktickets.ru' + booking_url

                            event_id = f"{title}|{booking_url}"
                            if event_id not in notified_events:
                                driver.quit()
                                return title, booking_url

                    except Exception as e:
                        continue

            except Exception as e:
                continue

        driver.quit()
        return None, None

    except Exception as e:
        print(f"❌ Ошибка при проверке: {e}")
        return None, None

def monitor_tickets(updater):
    bot = updater.bot
    print("🚀 Бот запущен. Мониторим билеты...")

    while True:
        title, booking_url = check_events()
        if title and booking_url:
            send_alert_to_all(bot, title, booking_url)
            notified_events.add(f"{title}|{booking_url}")

        print("💤 Сплю 30 секунд...")
        time.sleep(30)

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
    # Создаём Telegram-бота
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))

    # Запускаем веб-сервер в фоновом потоке
    Thread(target=run_health_server, daemon=True).start()

    # Запускаем мониторинг билетов в фоновом потоке
    Thread(target=monitor_tickets, args=(updater,), daemon=True).start()

    # Запускаем Telegram-бота
    print("🤖 Telegram-бот запущен. Жду команды /start...")
    updater.start_polling()
    updater.idle()
