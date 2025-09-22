import time
import requests
from bs4 import BeautifulSoup
from telegram import Bot, ParseMode

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = '8286251093:AAHmfYAWQFZksTFvmKY29wG_xMTCapFmau0'
CHAT_ID = '8286251093'

MAIN_URL = 'https://quicktickets.ru/orel-teatr-svobodnoe-prostranstvo'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
}

bot = Bot(token=TELEGRAM_TOKEN)
session = requests.Session()
session.headers.update(HEADERS)

notified_events = set()  # чтобы не дублировать уведомления

def send_alert(event_name, booking_url):
    message = (
        f"🎫 *ПОЯВИЛИСЬ БИЛЕТЫ!* \n\n"
        f"🎭 *Спектакль:* {event_name}\n"
        f"🔗 [Перейти к выбору мест]({booking_url})\n\n"
        f"⏳ Бронируй скорее — ажиотаж большой!"
    )
    try:
        bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=False
        )
        print(f"✅ Отправлено: {event_name}")
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")

def check_events():
    try:
        response = session.get(MAIN_URL, timeout=10)
        soup = BeautifulSoup(response.text, 'lxml')

        # Находим все блоки мероприятий
        events = soup.select('.event-item')  # стандартный класс на QuickTickets

        for event in events:
            # Ищем название
            title_elem = event.select_one('.event-title, h3, .title a')
            if not title_elem:
                continue
            title = title_elem.get_text(strip=True)

            # Ищем ссылку на страницу мероприятия (не сразу на бронирование!)
            link_elem = event.select_one('a[href*="/event/"]')
            if not link_elem or not link_elem.get('href'):
                continue

            event_url = link_elem['href']
            if not event_url.startswith('http'):
                event_url = 'https://quicktickets.ru' + event_url

            # Переходим на страницу мероприятия, чтобы найти кнопку бронирования
            event_page = session.get(event_url, timeout=10)
            event_soup = BeautifulSoup(event_page.text, 'lxml')

            # Ищем кнопку "Купить билеты" или "Выбрать места"
            buy_button = event_soup.select_one('.buy-btn, .btn-buy, a[href*="/booking/"]')
            if not buy_button:
                continue  # билеты ещё не в продаже

            booking_url = buy_button['href'] if buy_button.name == 'a' else event_url
            if not booking_url.startswith('http'):
                booking_url = 'https://quicktickets.ru' + booking_url

            event_id = f"{title}|{booking_url}"

            if event_id not in notified_events:
                send_alert(title, booking_url)
                notified_events.add(event_id)

    except Exception as e:
        print(f"❌ Ошибка при проверке: {e}")

# === ОСНОВНОЙ ЦИКЛ ===
if __name__ == '__main__':
    print("🚀 Бот запущен. Мониторим билеты...")
    while True:
        check_events()
        print("💤 Сплю 30 секунд...")

        time.sleep(30)
