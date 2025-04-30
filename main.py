import requests
from datetime import datetime
import jdatetime
import time
import os
import pytz
import logging

# تنظیم لاگ‌گذاری
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== تنظیمات ایمن ====================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')  # از متغیرهای محیطی
CHANNEL_ID = os.getenv('CHANNEL_ID')
API_KEY = os.getenv('API_KEY')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')  # برای اعلان‌های خطا
UPDATE_INTERVAL = 1800  # هر 30 دقیقه
CHECK_INTERVAL = 300    # هر 5 دقیقه
START_HOUR = 11         # ساعت شروع آپدیت
END_HOUR = 20           # ساعت پایان آپدیت
CHANGE_THRESHOLD = 2.0  # آستانه تغییر قیمت
MIN_EMERGENCY_INTERVAL = 300  # حداقل فاصله آپدیت فوری
# =====================================================

# لیست تعطیلات رسمی 1404 (کامل‌تر)
HOLIDAYS = [
    "01/01", "01/02", "01/03", "01/04",  # نوروز
    "01/12",  # روز جمهوری اسلامی
    "01/13",  # سیزده‌به‌در
    "02/14",  # رحلت حضرت فاطمه
    "03/14",  # رحلت امام خمینی
    "03/15",  # قیام 15 خرداد
    "04/03",  # عید فطر
    "04/04",  # عید فطر
    "06/10",  # عید قربان
    "07/18",  # عید غدیر
    "08/15",  # تاسوعا
    "08/16",  # عاشورا
    "09/25",  # اربعین
    "10/03",  # رحلت پیامبر و شهادت امام حسن
    "10/04",  # شهادت امام رضا
    "11/22",  # پیروزی انقلاب
    "12/12",  # میلاد پیامبر
]

# لیست استثناها (روزهایی که نباید تعطیل باشند)
NON_HOLIDAYS = [
    "02/10",  # 10 اردیبهشت
]

# ذخیره قیمت‌ها و متغیرهای جهانی
last_prices = None
last_emergency_update = 0
holidays_cache = None
last_holiday_notification = None
start_notification_sent = False
end_notification_sent = False
last_cache_refresh = None

# تنظیم منطقه زمانی تهران
TEHRAN_TZ = pytz.timezone('Asia/Tehran')

def get_jalali_date():
    return jdatetime.datetime.now().strftime("%Y/%m/%d")

def load_holidays_cache():
    """گرفتن تعطیلات سال از holidayapi.ir و ذخیره در کش"""
    global holidays_cache, last_cache_refresh
    try:
        year = jdatetime.datetime.now().year
        url = f"https://holidayapi.ir/jalali/{year}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        holidays_cache = []
        for day in data:
            if day['is_holiday']:
                date = jdatetime.datetime.strptime(day['date'], "%Y/%m/%d")
                month_day = date.strftime("%m/%d")
                if month_day not in NON_HOLIDAYS:
                    holidays_cache.append({
                        'month_day': month_day,
                        'events': day['events']
                    })
        last_cache_refresh = datetime.now(TEHRAN_TZ)
        logger.info(f"✅ تعطیلات سال {year} در کش ذخیره شد: {len(holidays_cache)} تعطیلی")
    except Exception as e:
        logger.error(f"❌ خطا در گرفتن تعطیلات سال از holidayapi.ir: {e}")
        holidays_cache = []

def is_holiday():
    """چک کردن اینکه امروز تعطیل است یا نه"""
    today = jdatetime.datetime.now()
    month_day = today.strftime("%m/%d")
    
    # چک کردن استثناها
    if month_day in NON_HOLIDAYS:
        logger.info(f"📅 {month_day} در لیست استثناها - تعطیل نیست")
        return False
    
    # چک کردن اینکه امروز جمعه است
    if today.weekday() == 4:
        logger.info(f"📅 {month_day} جمعه است - تعطیل")
        return True
    
    # استفاده از کش تعطیلات
    if holidays_cache:
        for holiday in holidays_cache:
            if holiday['month_day'] == month_day:
                logger.info(f"📅 {month_day} در کش تعطیلات یافت شد: {holiday['events']}")
                # اعتبارسنجی با HOLIDAYS
                if month_day not in HOLIDAYS:
                    send_suspicious_holiday_alert(today, holiday['events'])
                return True
    
    # گرفتن تعطیلات از API
    try:
        year = today.year
        month = today.month
        day = today.day
        url = f"https://holidayapi.ir/jalali/{year}/{month}/{day}"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        logger.info(f"پاسخ API برای {year}/{month}/{day}: {data}")
        if data['is_holiday'] and month_day not in NON_HOLIDAYS:
            if month_day not in HOLIDAYS:
                send_suspicious_holiday_alert(today, data.get('events', []))
            return True
    except Exception as e:
        logger.error(f"❌ خطا در گرفتن تعطیلات از holidayapi.ir: {e}")
        if month_day in HOLIDAYS:
            logger.info(f"📅 {month_day} در لیست ثابت تعطیلات یافت شد")
            return True
    
    logger.info(f"📅 {month_day} تعطیل نیست")
    return False

def send_suspicious_holiday_alert(today, events):
    """ارسال اعلان برای تعطیلات مشکوک"""
    if not ADMIN_CHAT_ID:
        logger.warning("⚠️ ADMIN_CHAT_ID تنظیم نشده، اعلان تعطیلات مشکوک ارسال نشد")
        return
    event_text = events[0] if events else "نامشخص"
    message = f"""
⚠️ <b>هشدار تعطیلات مشکوک!</b>
📅 تاریخ: {get_jalali_date()}
🔔 API روز {today.strftime('%Y/%m/%d')} رو تعطیل برگردوند (مناسبت: {event_text})
ولی توی لیست تعطیلات معتبر نیست. لطفاً بررسی کن!
▫️ @{CHANNEL_ID.replace('@', '')}
"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        response = requests.post(url, json={
            'chat_id': ADMIN_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        })
        response.raise_for_status()
        logger.info("✅ اعلان تعطیلات مشکوک ارسال شد")
    except Exception as e:
        logger.error(f"❌ خطا در ارسال اعلان تعطیلات مشکوک: {e}")

def send_holiday_notification():
    """ارسال اعلان تعطیلات"""
    today = jdatetime.datetime.now()
    month_day = today.strftime("%m/%d")
    events = []
    
    if holidays_cache:
        for holiday in holidays_cache:
            if holiday['month_day'] == month_day:
                events = holiday['events']
                break
    else:
        try:
            year = today.year
            month = today.month
            day = today.day
            url = f"https://holidayapi.ir/jalali/{year}/{month}/{day}"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            if data['is_holiday']:
                events = data['events']
        except Exception as e:
            logger.error(f"❌ خطا در گرفتن مناسبت‌ها از holidayapi.ir: {e}")

    event_text = events[0] if events else "تعطیل رسمی"
    message = f"""
📢 <b>امروز تعطیله!</b>
📅 تاریخ: {get_jalali_date()}
🔔 مناسبت: {event_text}
بازار بسته‌ست و آپدیت قیمت نداریم. روز کاری بعدی ساعت 11 صبح شروع می‌کنیم!
▫️ @{CHANNEL_ID.replace('@', '')}
"""
    send_message(message)
    logger.info("✅ اعلان تعطیلات ارسال شد")

def send_start_notification():
    """ارسال اعلان شروع روز کاری"""
    message = f"""
📢 <b>شروع آپدیت قیمت‌ها!</b>
📅 تاریخ: {get_jalali_date()}
⏰ ساعت: {datetime.now(TEHRAN_TZ).strftime('%H:%M')}
هر 30 دقیقه قیمت‌های جدید طلا، سکه و ارز رو می‌فرستیم!
▫️ @{CHANNEL_ID.replace('@', '')}
"""
    send_message(message)
    logger.info("✅ اعلان شروع روز کاری ارسال شد")

def send_end_notification():
    """ارسال اعلان پایان روز کاری"""
    message = f"""
📢 <b>پایان آپدیت قیمت‌ها!</b>
📅 تاریخ: {get_jalali_date()}
⏰ ساعت: {datetime.now(TEHRAN_TZ).strftime('%H:%M')}
آپدیت امروز تموم شد. فردا ساعت 11 صبح ادامه می‌دیم!
▫️ @{CHANNEL_ID.replace('@', '')}
"""
    send_message(message)
    logger.info("✅ اعلان پایان روز کاری ارسال شد")

def get_price_change_emoji(change_percent):
    """تعیین ایموجی تغییر قیمت"""
    if change_percent > 0:
        return "🔺"
    elif change_percent < 0:
        return "🔻"
    return "➖"

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
        logger.info(f"داده‌های API قیمت‌ها: {data}")

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
                emergency_message += f"▫️ @{CHANNEL_ID.replace('@', '')}"
                send_message(emergency_message)
                last_emergency_update = current_time

        last_prices = prices
        return prices
    except Exception as e:
        logger.error(f"❌ خطا در دریافت داده قیمت‌ها: {e}")
        return None

def send_message(text, chat_id=None):
    """ارسال پیام به کانال یا ادمین"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        target_chat_id = chat_id or CHANNEL_ID
        logger.info(f"در حال ارسال پیام به {target_chat_id}")
        response = requests.post(url, json={
            'chat_id': target_chat_id,
            'text': text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        })
        logger.info(f"پاسخ تلگرام: {response.text}")
        response.raise_for_status()
        logger.info("✅ پیام با موفقیت ارسال شد")
    except Exception as e:
        logger.error(f"❌ ارسال پیام ناموفق: {e}")

def create_message(prices):
    """ایجاد پیام قیمت‌ها"""
    return f"""
📅 <b>تاریخ: {get_jalali_date()}</b>
⏰ <b>آخرین آپدیت: {prices['update_time']}</b>

📊 <b>قیمت‌های لحظه‌ای بازار</b>

<b>طلا</b>
{get_price_change_emoji(prices['gold_ounce']['change_percent'])} انس جهانی: {prices['gold_ounce']['price']}
{get_price_change_emoji(prices['gold_18k']['change_percent'])} 18 عیار: {format_price(prices['gold_18k']['price'])} تومان

<b>سکه</b>
{get_price_change_emoji(prices['coin_old']['change_percent'])} تمام امامی: {format_price(prices['coin_old']['price'])} تومان
{get_price_change_emoji(prices['coin_new']['change_percent'])} تمام بهار: {format_price(prices['coin_new']['price'])} تومان
{get_price_change_emoji(prices['half_coin']['change_percent'])} نیم سکه: {format_price(prices['half_coin']['price'])} تومان
{get_price_change_emoji(prices['quarter_coin']['change_percent'])} ربع سکه: {format_price(prices['quarter_coin']['price'])} تومان
{get_price_change_emoji(prices['gram_coin']['change_percent'])} سکه گرمی: {format_price(prices['gram_coin']['price'])} تومان

<b>ارزها</b>
{get_price_change_emoji(prices['usd']['change_percent'])} دلار: {format_price(prices['usd']['price'])} تومان
{get_price_change_emoji(prices['usdt']['change_percent'])} تتر: {format_price(prices['usdt']['price'])} تومان
{get_price_change_emoji(prices['eur']['change_percent'])} یورو: {format_price(prices['eur']['price'])} تومان
{get_price_change_emoji(prices['gbp']['change_percent'])} پوند: {format_price(prices['gbp']['price'])} تومان
{get_price_change_emoji(prices['aed']['change_percent'])} درهم: {format_price(prices['aed']['price'])} تومان

▫️ @{CHANNEL_ID.replace('@', '')}
"""

def format_price(price):
    try:
        return f"{int(float(price)):,}"
    except:
        return "نامشخص"

def is_within_update_hours():
    """چک کردن بازه آپدیت"""
    current_time = datetime.now(TEHRAN_TZ)
    current_hour = current_time.hour
    return START_HOUR <= current_hour < END_HOUR

def main():
    global last_holiday_notification, start_notification_sent, end_notification_sent, last_cache_refresh
    
    # بارگذاری تعطیلات
    load_holidays_cache()
    
    while True:
        current_time = datetime.now(TEHRAN_TZ)
        current_hour = current_time.hour
        current_minute = current_time.minute
        today = jdatetime.datetime.now()
        
        # ریست پرچم‌ها در شروع روز
        if current_hour == 0 and current_minute == 0:
            start_notification_sent = False
            end_notification_sent = False
            last_holiday_notification = None
        
        # رفرش کش اول هر ماه
        if today.day == 1 and (last_cache_refresh is None or last_cache_refresh.month != today.month):
            logger.info("🔄 رفرش کش تعطیلات در ابتدای ماه")
            load_holidays_cache()
        
        if is_holiday():
            if (current_hour == START_HOUR and current_minute == 0 and 
                (last_holiday_notification is None or 
                 last_holiday_notification.date() != current_time.date())):
                send_holiday_notification()
                last_holiday_notification = current_time
            logger.info(f"📅 امروز: {get_jalali_date()} - روز تعطیل، آپدیت انجام نمی‌شود")
            time.sleep(CHECK_INTERVAL)
        elif is_within_update_hours():
            if current_hour == START_HOUR and current_minute == 0 and not start_notification_sent:
                send_start_notification()
                start_notification_sent = True
            
            logger.info(f"⏰ زمان فعلی (تهران): {current_time.strftime('%H:%M')} - در بازه آپدیت")
            prices = get_prices()
            if prices:
                message = create_message(prices)
                send_message(message)
                logger.info(f"✅ قیمت‌ها در {current_time.strftime('%H:%M')} ارسال شدند")
            else:
                logger.error("❌ خطا در دریافت قیمت‌ها")
            time.sleep(UPDATE_INTERVAL)
        else:
            if current_hour == END_HOUR and current_minute == 0 and not end_notification_sent:
                send_end_notification()
                end_notification_sent = True
            
            logger.info(f"⏰ زمان فعلی (تهران): {current_time.strftime('%H:%M')} - خارج از بازه آپدیت")
            time.sleep(CHECK_INTERVAL)

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
