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
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    username = update.effective_user.username or "Аноним"
    add_subscriber(chat_id, username)
    await update.message.reply_text(
        "✅ Вы подписаны на уведомления!\n"
        "Как только появятся билеты на любой спектакль — я сразу сообщу. 🎭\n"
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
            await application.bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML')
            logger.info(f"Сообщение отправлено: {chat_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки {chat_id}: {e}")
            if "Forbidden" in str(e):
                # Удаляем пользователя, если он заблокировал бота
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

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    try:
        logger.info("Проверка наличия билетов...")
        driver.get(THEATER_URL)
        time.sleep(5)  # Ждём загрузки страницы

        # 🔍 Ищем ВСЕ оранжевые кнопки (активные сеансы)
        # Селекторы подобраны под quicktickets.ru
        event_blocks = driver.find_elements(By.CSS_SELECTOR, "div.event")

        new_events_found = False

        for block in event_blocks:
            try:
                # Пытаемся найти оранжевую кнопку внутри блока
                date_link = block.find_element(By.CSS_SELECTOR, "a.btn-orange, a.btn-primary")
                event_time = date_link.text.strip()

                # Пытаемся найти название спектакля
                try:
                    title_element = block.find_element(By.CSS_SELECTOR, "h3, .event-title, strong")
                    event_title = title_element.text.strip()
                except:
                    event_title = "Спектакль"

                # Формируем сообщение
                message = f"🎉 <b>Появились билеты!</b>\n\n🎭 {event_title}\n⏰ {event_time}\n🔗 {THEATER_URL}"

                # Отправляем ВСЕМ подписчикам
                await broadcast_message(application, message)
                new_events_found = True
                logger.info(f"Обнаружен новый сеанс: {event_title} в {event_time}")

            except Exception:
                # Если внутри блока нет оранжевой кнопки — пропускаем его (билетов нет)
                continue

        if not new_events_found:
            logger.info("Новых сеансов с билетами не обнаружено.")

    except Exception as e:
        logger.error(f"Ошибка при проверке: {e}")
    finally:
        driver.quit()

# === Бесконечный цикл мониторинга ===
async def monitoring_loop(application):
    while True:
        try:
            await check_new_events(application)
        except Exception as e:
            logger.error(f"Ошибка в цикле: {e}")
        logger.info("Следующая проверка через 5 минут...")
        await asyncio.sleep(300)  # 5 минут

# === Запуск бота ===
async def main():
    init_db()
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stop", stop_command))

    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    logger.info("Бот запущен и ожидает команд...")
    await monitoring_loop(application)

if __name__ == "__main__":
    asyncio.run(main())
