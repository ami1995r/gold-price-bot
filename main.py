import requests
from datetime import datetime
import jdatetime
import time
import os
import pytz

# ==================== تنظیمات ایمن ====================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')  # از متغیرهای محیطی Railway
CHANNEL_ID = os.getenv('CHANNEL_ID')
API_KEY = os.getenv('API_KEY')
UPDATE_INTERVAL = 1800  # هر 30 دقیقه (1800 ثانیه)
CHECK_INTERVAL = 300    # هر 5 دقیقه چک کردن زمان (برای خارج از بازه)
START_HOUR = 11         # ساعت شروع آپدیت (11 صبح به وقت تهران)
END_HOUR = 20           # ساعت پایان آپدیت (8 شب به وقت تهران)
CHANGE_THRESHOLD = 2.0  # آستانه تغییر قیمت برای آپدیت فوری (2%)
MIN_EMERGENCY_INTERVAL = 300  # حداقل فاصله بین آپدیت‌های فوری (5 دقیقه)
# =====================================================

# لیست تعطیلات رسمی ثابت (به تاریخ شمسی: ماه/روز)
HOLIDAYS = [
    "01/01",  # 1 فروردین (نوروز)
    "01/02",  # 2 فروردین (نوروز)
    "01/03",  # 3 فروردین (نوروز)
    "01/04",  # 4 فروردین (نوروز)
    "01/12",  # 12 فروردین (روز جمهوری اسلامی)
    "01/13",  # 13 فروردین (سیزده‌به‌در)
    "03/14",  # 14 خرداد (رحلت امام خمینی)
    "03/15",  # 15 خرداد (قیام 15 خرداد)
    "11/22",  # 22 بهمن (پیروزی انقلاب)
]

# ذخیره قیمت‌های قبلی و زمان آخرین آپدیت فوری
last_prices = None
last_emergency_update = 0

# تنظیم منطقه زمانی تهران
TEHRAN_TZ = pytz.timezone('Asia/Tehran')

def get_jalali_date():
    return jdatetime.datetime.now().strftime("%Y/%m/%d")

def is_holiday():
    """چک کردن اینکه امروز تعطیل است یا نه"""
    today = jdatetime.datetime.now()
    if today.weekday() == 4:  # در jdatetime، 4 = جمعه
        return True
    month_day = today.strftime("%m/%d")
    if month_day in HOLIDAYS:
        return True
    return False

def get_price_change_emoji(change_percent):
    """تعیین ایموجی تغییر قیمت"""
    if change_percent > CHANGE_THRESHOLD:
        return "🚀 (+{:.2f}%)".format(change_percent)
    elif change_percent > 0:
        return "📈 (+{:.2f}%)".format(change_percent)
    elif change_percent < -CHANGE_THRESHOLD:
        return "⚠️ ({:.2f}%)".format(change_percent)
    elif change_percent < 0:
        return "📉 ({:.2f}%)".format(change_percent)
    return "⚖️ (0%)"

def find_item_by_symbol(items, symbol):
    for item in items:
        if item['symbol'] == symbol:
            return item
    return None

def get_prices():
    global last_prices, last_emergency_update
    try:
        url = f'https://brsapi.ir/Api/Market/Gold_Currency.php?key={API_KEY}'
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        print("داده‌های API:", data)

        update_time = data['gold'][0]['time'] if data['gold'] else datetime.now(TEHRAN_TZ).strftime("%H:%M")

        prices = {
            'update_time': update_time,
            'gold_ounce': find_item_by_symbol(data['gold'], 'XAUUSD') or {'price': 'N/A', 'change_percent': 0},
            'gold_18k': find_item_by_symbol(data['gold'], 'IR_GOLD_18K') or {'price': 'N/A', 'change_percent': 0},
            'coin_new': find_item_by_symbol(data['gold'], 'IR_COIN_BAHAR') or {'price': 'N/A', 'change_percent': 0},
            'coin_old': find_item_by_symbol(data['gold'], 'IR_COIN_EMAMI') or {'price': 'N/A', 'change_percent': 0},
            'half_coin': find_item_by_symbol(data['gold'], 'IR_COIN_HALF') or {'price': 'N/A', 'change_percent': 0},
            'quarter_coin': find_item_by_symbol(data['gold'], 'IR_COIN_QUARTER') or {'price': 'N/A', 'change_percent': 0},
            'gram_coin': find_item_by_symbol(data['gold'], 'IR_COIN_1G') or {'price': 'N/A', 'change_percent': 0},
            'usd': find_item_by_symbol(data['currency'], 'USD') or {'price': 'N/A', 'change_percent': 0},
            'eur': find_item_by_symbol(data['currency'], 'EUR') or {'price': 'N/A', 'change_percent': 0},
            'gbp': find_item_by_symbol(data['currency'], 'GBP') or {'price': 'N/A', 'change_percent': 0},
            'aed': find_item_by_symbol(data['currency'], 'AED') or {'price': 'N/A', 'change_percent': 0},
            'usdt': find_item_by_symbol(data['currency'], 'USDT_IRT') or {'price': 'N/A', 'change_percent': 0},
        }

        # چک کردن تغییرات بزرگ قیمت
        if last_prices:
            current_time = time.time()
            significant_changes = []
            for key in prices:
                if key == 'update_time':
                    continue
                new_price = prices[key]['price']
                old_price = last_prices[key]['price']
                if new_price != 'N/A' and old_price != 'N/A':
                    try:
                        new_price = float(new_price)
                        old_price = float(old_price)
                        change_percent = ((new_price - old_price) / old_price) * 100
                        if abs(change_percent) > CHANGE_THRESHOLD and (current_time - last_emergency_update) > MIN_EMERGENCY_INTERVAL:
                            significant_changes.append((key, change_percent, new_price))
                    except (ValueError, TypeError):
                        continue

            if significant_changes:
                # ارسال پیام فوری برای تغییرات بزرگ
                emergency_message = f"""
🚨 <b>هشدار تغییر بزرگ قیمت!</b>
📅 تاریخ: {get_jalali_date()}
⏰ زمان: {datetime.now(TEHRAN_TZ).strftime('%H:%M')}
"""
                for key, change_percent, new_price in significant_changes:
                    name = {
                        'gold_ounce': 'انس جهانی',
                        'gold_18k': 'طلای 18 عیار',
                        'coin_new': 'سکه بهار',
                        'coin_old': 'سکه امامی',
                        'half_coin': 'نیم سکه',
                        'quarter_coin': 'ربع سکه',
                        'gram_coin': 'سکه گرمی',
                        'usd': 'دلار',
                        'eur': 'یورو',
                        'gbp': 'پوند',
                        'aed': 'درهم',
                        'usdt': 'تتر'
                    }.get(key, key)
                    emergency_message += f"{get_price_change_emoji(change_percent)} {name}: {format_price(new_price)} تومان\n"
                emergency_message += f"📢 @{CHANNEL_ID.replace('@', '')}"
                send_message(emergency_message)
                last_emergency_update = current_time

        last_prices = prices
        return prices
    except Exception as e:
        print(f"❌ خطا در دریافت داده: {e}")
        return None

def send_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        print(f"در حال ارسال پیام به {CHANNEL_ID}")
        response = requests.post(url, json={
            'chat_id': CHANNEL_ID,
            'text': text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        })
        print(f"پاسخ تلگرام: {response.text}")
        response.raise_for_status()
        print("✅ پیام با موفقیت ارسال شد")
    except Exception as e:
        print(f"❌ ارسال پیام ناموفق: {e}")

def create_message(prices):
    return f"""
📅 <b>تاریخ: {get_jalali_date()}</b>
⏰ <b>آخرین بروزرسانی: {prices['update_time']}</b>

📊 <b>قیمت‌های لحظه‌ای بازار</b>

<b>🏆 طلا</b>
{get_price_change_emoji(prices['gold_ounce']['change_percent'])} انس جهانی: {prices['gold_ounce']['price']} دلار
{get_price_change_emoji(prices['gold_18k']['change_percent'])} 18 عیار: {format_price(prices['gold_18k']['price'])} تومان

<b>🏅 سکه</b>
{get_price_change_emoji(prices['coin_old']['change_percent'])} تمام امامی: {format_price(prices['coin_old']['price'])} تومان
{get_price_change_emoji(prices['coin_new']['change_percent'])} تمام بهار: {format_price(prices['coin_new']['price'])} تومان
{get_price_change_emoji(prices['half_coin']['change_percent'])} نیم سکه: {format_price(prices['half_coin']['price'])} تومان
{get_price_change_emoji(prices['quarter_coin']['change_percent'])} ربع سکه: {format_price(prices['quarter_coin']['price'])} تومان
{get_price_change_emoji(prices['gram_coin']['change_percent'])} سکه گرمی: {format_price(prices['gram_coin']['price'])} تومان

<b>💱 ارزها</b>
{get_price_change_emoji(prices['usd']['change_percent'])} دلار: {format_price(prices['usd']['price'])} تومان
{get_price_change_emoji(prices['eur']['change_percent'])} یورو: {format_price(prices['eur']['price'])} تومان
{get_price_change_emoji(prices['gbp']['change_percent'])} پوند: {format_price(prices['gbp']['price'])} تومان
{get_price_change_emoji(prices['aed']['change_percent'])} درهم: {format_price(prices['aed']['price'])} تومان
{get_price_change_emoji(prices['usdt']['change_percent'])} تتر: {format_price(prices['usdt']['price'])} تومان

📢 @{CHANNEL_ID.replace('@', '')}
"""

def format_price(price):
    try:
        return f"{int(float(price)):,}"
    except:
        return "نامشخص"

def is_within_update_hours():
    """چک کردن اینکه زمان فعلی در بازه آپدیت (11 صبح تا 8 شب به وقت تهران) هست یا نه"""
    current_time = datetime.now(TEHRAN_TZ)
    current_hour = current_time.hour
    return START_HOUR <= current_hour < END_HOUR

def main():
    while True:
        if is_holiday():
            print(f"📅 امروز: {get_jalali_date()} - روز تعطیل، آپدیت انجام نمی‌شود")
            time.sleep(CHECK_INTERVAL)  # صبر 5 دقیقه تا چک بعدی
        elif is_within_update_hours():
            print(f"⏰ زمان فعلی (تهران): {datetime.now(TEHRAN_TZ).strftime('%H:%M')} - در بازه آپدیت")
            prices = get_prices()
            if prices:
                message = create_message(prices)
                send_message(message)
                print(f"✅ قیمت‌ها در {datetime.now(TEHRAN_TZ).strftime('%H:%M')} ارسال شدند")
            else:
                print("❌ خطا در دریافت قیمت‌ها")
            time.sleep(UPDATE_INTERVAL)  # صبر 30 دقیقه
        else:
            print(f"⏰ زمان فعلی (تهران): {datetime.now(TEHRAN_TZ).strftime('%H:%M')} - خارج از بازه آپدیت")
            time.sleep(CHECK_INTERVAL)  # صبر 5 دقیقه تا چک بعدی

if __name__ == "__main__":
    try:
        import jdatetime
        import pytz
    except ImportError:
        import os
        os.system("pip install jdatetime pytz")
        import jdatetime
        import pytz
    
    main()
