import time
import logging
import sqlite3
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import asyncio

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = '8286251093:AAHmfYAWQFZksTFvmKY29wG_xMTCapFmau0'
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
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    username = update.effective_user.username or "Аноним"
    add_subscriber(chat_id, username)
    await update.message.reply_text(
        "✅ Вы подписаны на мгновенные уведомления!\n"
        "Как только появятся билеты — вы получите сообщение за секунды. 🚨\n"
        "Чтобы отписаться, отправьте /stop."
    )

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    conn = sqlite3.connect('subscribers.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM subscribers WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("❌ Вы отписались от уведомлений.")

# === Отправка сообщения всем подписчикам ===
async def broadcast_message(application, text):
    subscribers = get_all_subscribers()
    for chat_id in subscribers:
        try:
            await application.bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML', disable_web_page_preview=False)
            logger.info(f"✅ Уведомление доставлено: {chat_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки {chat_id}: {e}")
            if "Forbidden" in str(e):
                # Удаляем заблокировавших бота
                conn = sqlite3.connect('subscribers.db')
                cursor = conn.cursor()
                cursor.execute('DELETE FROM subscribers WHERE chat_id = ?', (chat_id,))
                conn.commit()
                conn.close()

# === Основная функция проверки билетов ===
async def check_new_events(application):
    # Настройка Selenium в фоновом режиме
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-images")  # Отключаем изображения для скорости
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    try:
        logger.info("🚀 Запуск сверхбыстрой проверки билетов...")
        driver.get(THEATER_URL)
        time.sleep(3)  # Минимальная задержка для прогрузки

        # Находим все блоки мероприятий
        event_blocks = driver.find_elements(By.CSS_SELECTOR, "div.event")

        for block in event_blocks:
            try:
                # Ищем название спектакля (первый span.underline)
                title_spans = block.find_elements(By.CSS_SELECTOR, "span.underline")
                if len(title_spans) < 2:
                    continue

                event_title = title_spans[0].text.strip()  # Первый — название
                event_time = title_spans[1].text.strip()   # Второй — дата/время

                # Ищем ссылку на сеанс (обёрнута вокруг даты/времени)
                try:
                    date_link = title_spans[1].find_element(By.XPATH, "./ancestor::a")
                    event_url = date_link.get_attribute('href')
                except:
                    continue

                # Проверяем наличие текста "(мест нет)"
                no_seats_elements = block.find_elements(By.CSS_SELECTOR, "span[style*='color:#888888']")

                # ✅ Если "(мест нет)" НЕТ — значит, билеты есть!
                if not no_seats_elements:
                    message = (
                        f"🚨 <b>СРОЧНО! БИЛЕТЫ ПОЯВИЛИСЬ!</b>\n\n"
                        f"🎭 <b>{event_title}</b>\n"
                        f"⏰ {event_time}\n"
                        f"🔗 <a href='{event_url}'>БЫСТРО ВЫБРАТЬ!</a>"
                    )
                    await broadcast_message(application, message)
                    logger.info(f"🎉 Билеты найдены: {event_title} — {event_time}")

            except Exception as e:
                logger.error(f"Ошибка обработки блока: {e}")
                continue

    except Exception as e:
        logger.error(f"Критическая ошибка при проверке: {e}")
    finally:
        driver.quit()

# === Сверхбыстрый цикл мониторинга ===
async def monitoring_loop(application):
    while True:
        start_time = time.time()
        try:
            await check_new_events(application)
        except Exception as e:
            logger.error(f"Ошибка в цикле: {e}")
        elapsed = time.time() - start_time
        sleep_time = max(10 - elapsed, 1)  # Минимум 1 секунда, максимум 10
        logger.info(f"⏱️ Следующая проверка через {int(sleep_time)} сек...")
        await asyncio.sleep(sleep_time)

# === Запуск бота ===
async def main():
    init_db()
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stop", stop_command))

    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    logger.info("🔥 Бот запущен. Мониторинг каждые 10 секунд!")
    await monitoring_loop(application)
    
if __name__ == "__main__":
    asyncio.run(main())


