import time
import logging
import sqlite3
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from telegram import Bot
from telegram.ext import Updater, CommandHandler, CallbackContext
import threading

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN'  # ⚠️ Замените на свой токен
THEATER_URL = 'https://quicktickets.ru/orel-teatr-svobodnoe-prostranstvo'

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# === Работа с базой данных подписчиков ===
def init_db():
    conn = sqlite3.connect('subscribers.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscribers (
            chat_id INTEGER PRIMARY KEY,
            username TEXT
        )
    ''')
    conn.commit()
    conn.close()

def add_subscriber(chat_id, username):
    conn = sqlite3.connect('subscribers.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO subscribers (chat_id, username) VALUES (?, ?)', (chat_id, username))
    conn.commit()
    conn.close()
    logger.info(f"Новый подписчик: {username} ({chat_id})")

def get_all_subscribers():
    conn = sqlite3.connect('subscribers.db')
    cursor = conn.cursor()
    cursor.execute('SELECT chat_id FROM subscribers')
    subscribers = [row[0] for row in cursor.fetchall()]
    conn.close()
    return subscribers

# === Команды Telegram-бота ===
def start_command(update, context):
    chat_id = update.effective_chat.id
    username = update.effective_user.username or "Аноним"
    add_subscriber(chat_id, username)
    update.message.reply_text(
        "✅ Вы подписаны на мгновенные уведомления!\n"
        "Как только появятся билеты — вы получите сообщение за секунды. 🚨\n"
        "Чтобы отписаться, отправьте /stop."
    )

def stop_command(update, context):
    chat_id = update.effective_chat.id
    conn = sqlite3.connect('subscribers.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM subscribers WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()
    update.message.reply_text("❌ Вы отписались от уведомлений.")

# === Отправка сообщения всем подписчикам ===
def broadcast_message(bot_instance, text):
    subscribers = get_all_subscribers()
    for chat_id in subscribers:
        try:
            bot_instance.send_message(chat_id=chat_id, text=text, parse_mode='HTML', disable_web_page_preview=False)
            logger.info(f"✅ Уведомление доставлено: {chat_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки {chat_id}: {e}")
            if "Forbidden" in str(e):
                conn = sqlite3.connect('subscribers.db')
                cursor = conn.cursor()
                cursor.execute('DELETE FROM subscribers WHERE chat_id = ?', (chat_id,))
                conn.commit()
                conn.close()

# === Основная функция проверки билетов ===
def check_new_events(bot_instance):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-images")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    try:
        logger.info("🚀 Запуск сверхбыстрой проверки билетов...")
        driver.get(THEATER_URL)
        time.sleep(3)

        event_blocks = driver.find_elements(By.CSS_SELECTOR, "div.event")

        for block in event_blocks:
            try:
                title_spans = block.find_elements(By.CSS_SELECTOR, "span.underline")
                if len(title_spans) < 2:
                    continue

                event_title = title_spans[0].text.strip()
                event_time = title_spans[1].text.strip()

                try:
                    date_link = title_spans[1].find_element(By.XPATH, "./ancestor::a")
                    event_url = date_link.get_attribute('href')
                except:
                    continue

                no_seats_elements = block.find_elements(By.CSS_SELECTOR, "span[style*='color:#888888']")

                if not no_seats_elements:
                    message = (
                        f"🚨 <b>СРОЧНО! БИЛЕТЫ ПОЯВИЛИСЬ!</b>\n\n"
                        f"🎭 <b>{event_title}</b>\n"
                        f"⏰ {event_time}\n"
                        f"🔗 <a href='{event_url}'>БЫСТРО ВЫБРАТЬ!</a>"
                    )
                    broadcast_message(bot_instance, message)
                    logger.info(f"🎉 Билеты найдены: {event_title} — {event_time}")

            except Exception as e:
                logger.error(f"Ошибка обработки блока: {e}")
                continue

    except Exception as e:
        logger.error(f"Критическая ошибка при проверке: {e}")
    finally:
        driver.quit()

# === Сверхбыстрый цикл мониторинга ===
def monitoring_loop(bot_instance):
    while True:
        start_time = time.time()
        try:
            check_new_events(bot_instance)
        except Exception as e:
            logger.error(f"Ошибка в цикле: {e}")
        elapsed = time.time() - start_time
        sleep_time = max(10 - elapsed, 1)
        logger.info(f"⏱️ Следующая проверка через {int(sleep_time)} сек...")
        time.sleep(sleep_time)

# === Запуск бота ===
def main():
    init_db()
    
    # Создаём экземпляр Bot и передаём его в Updater
    bot_instance = Bot(token=TELEGRAM_TOKEN)
    updater = Updater(bot=bot_instance, use_context=True)

    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("start", start_command))
    dispatcher.add_handler(CommandHandler("stop", stop_command))

    # Запускаем мониторинг в отдельном потоке
    monitor_thread = threading.Thread(target=monitoring_loop, args=(bot_instance,), daemon=True)
    monitor_thread.start()

    logger.info("🔥 Бот запущен. Мониторинг каждые 10 секунд!")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
