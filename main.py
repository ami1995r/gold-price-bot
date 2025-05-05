import requests
from datetime import datetime
import jdatetime
import time
import os
import logging
try:
    import pkg_resources
except ImportError:
    logging.error("❌ ماژول pkg_resources پیدا نشد. لطفاً مطمئن شوید که setuptools نصب شده است.")
    pkg_resources = None

# تنظیم لاگ‌گذاری
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== تنظیمات ایمن ====================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
API_KEY = os.getenv('API_KEY')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')
UPDATE_INTERVAL = 1800  # هر 30 دقیقه
CHECK_INTERVAL = 300    # هر 5 دقیقه
START_HOUR = 7          # ساعت 07:30 صبح UTC (معادل 11:00 تهران)
END_HOUR = 16           # ساعت 16:30 عصر UTC (معادل 20:00 تهران)
TIME_OFFSET = 3.5       # اختلاف ساعت تهران با UTC (در ساعت)
CHANGE_THRESHOLD = 2.0  # آستانه تغییر قیمت
MIN_EMERGENCY_INTERVAL = 300  # حداقل فاصله آپدیت فوری
# =====================================================

# لاگ نسخه‌های پکیج‌ها
if pkg_resources:
    try:
        jdatetime_version = pkg_resources.get_distribution("jdatetime").version
        logger.info(f"📦 نسخه پکیج‌ها: jdatetime={jdatetime_version}")
    except Exception as e:
        logger.error(f"❌ خطا در بررسی نسخه پکیج‌ها: {e}")
else:
    logger.warning("⚠️ pkg_resources در دسترس نیست، نسخه پکیج‌ها بررسی نشد")

# چک کردن متغیرهای محیطی
if not all([TELEGRAM_TOKEN, CHANNEL_ID, API_KEY, ADMIN_CHAT_ID]):
    missing_vars = [var for var, val in [('TELEGRAM_TOKEN', TELEGRAM_TOKEN), ('CHANNEL_ID', CHANNEL_ID), 
                                         ('API_KEY', API_KEY), ('ADMIN_CHAT_ID', ADMIN_CHAT_ID)] if not val]
    error_message = f"❌ متغیرهای محیطی تنظیم نشده‌اند: {', '.join(missing_vars)}"
    logger.error(error_message)

# لیست تعطیلات 1404 (جمعه‌ها + تعطیلات رسمی)
HOLIDAYS = [
    "01/01", "01/02", "01/03", "01/04",  # نوروز
    "01/07", "01/14", "01/21", "01/28",  # جمعه‌ها
    "01/12",  # روز جمهوری اسلامی
    "01/13",  # سیزده‌به‌در
    "02/03", "02/04",  # عید فطر
    "02/05", "02/12", "02/19", "02/26",  # جمعه‌ها
    "03/02", "03/09", "03/16", "03/23", "03/30",  # جمعه‌ها (03/16 عید قربان هم هست)
    "03/14",  # رحلت امام خمینی
    "03/15",  # قیام 15 خرداد
    "03/24",  # عید غدیر خم
    "04/06", "04/13", "04/20", "04/27",  # جمعه‌ها
    "04/14",  # تاسوعا
    "04/15",  # عاشورا
    "05/03", "05/10", "05/17", "05/24", "05/31",  # جمعه‌ها (05/31 رحلت رسول و شهادت امام حسن هم هست)
    "05/23",  # اربعین
    "06/02",  # شهادت امام رضا
    "06/07", "06/14", "06/21", "06/28",  # جمعه‌ها
    "06/10",  # شهادت امام حسن عسکری
    "06/19",  # میلاد رسول اکرم و امام جعفر صادق
    "07/05", "07/12", "07/19", "07/26",  # جمعه‌ها
    "08/03", "08/10", "08/17", "08/24",  # جمعه‌ها
    "09/01", "09/08", "09/15", "09/22", "09/29",  # جمعه‌ها
    "09/03",  # شهادت حضرت فاطمه
    "10/06", "10/13", "10/20", "10/27",  # جمعه‌ها (10/13 ولادت امام علی، 10/27 مبعث هم هست)
    "11/04", "11/11", "11/18", "11/25",  # جمعه‌ها
    "11/15",  # ولادت حضرت قائم
    "11/22",  # پیروزی انقلاب اسلامی
    "12/02", "12/09", "12/16", "12/23",  # جمعه‌ها
    "12/20",  # شهادت امام علی
    "12/29",  # روز ملی شدن صنعت نفت
]

# لیست استثناها (روزهایی که نباید تعطیل باشند)
NON_HOLIDAYS = [
    "02/10",  # 10 اردیبهشت
    "02/14",  # 14 اردیبهشت
]

# ذخیره قیمت‌ها و متغیرهای جهانی
last_prices = None
last_emergency_update = 0
last_holiday_notification = None
start_notification_sent = False
end_notification_sent = False
last_suspicious_holiday_alert = None
last_update_time = 0

def send_message(text, chat_id=None):
    """ارسال پیام به کانال یا ادمین"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        target_chat_id = chat_id or CHANNEL_ID
        logger.info(f"📤 در حال ارسال پیام به chat_id={target_chat_id}")
        response = requests.post(url, json={
            'chat_id': target_chat_id,
            'text': text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        })
        logger.info(f"📥 پاسخ تلگرام: {response.text}")
        response.raise_for_status()
        logger.info("✅ پیام با موفقیت ارسال شد")
    except Exception as e:
        logger.error(f"❌ ارسال پیام ناموفق به chat_id={target_chat_id}: {e}")

def get_jalali_date():
    """گرفتن تاریخ شمسی بدون منطقه زمانی"""
    return jdatetime.datetime.now().strftime("%Y/%m/%d")

def is_holiday():
    """چک کردن اینکه امروز تعطیل است یا نه"""
    today = jdatetime.datetime.now()
    month_day = today.strftime("%m/%d")
    gregorian_date = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"📅 تاریخ شمسی: {get_jalali_date()} | تاریخ میلادی: {gregorian_date}")

    # چک کردن استثناها
    if month_day in NON_HOLIDAYS:
        logger.info(f"📅 {month_day} در لیست استثناها - تعطیل نیست")
        return False
    
    # چک کردن لیست تعطیلات
    if month_day in HOLIDAYS:
        logger.info(f"📅 {month_day} در لیست تعطیلات یافت شد")
        send_suspicious_holiday_alert(today)
        return True
    
    logger.info(f"📅 {month_day} تعطیل نیست")
    return False

def send_suspicious_holiday_alert(today):
    """ارسال اعلان برای تعطیلات مشکوک"""
    global last_suspicious_holiday_alert
    if not ADMIN_CHAT_ID:
        logger.warning("⚠️ ADMIN_CHAT_ID تنظیم نشده، اعلان تعطیلات مشکوک ارسال نشد")
        return
    
    # فقط یک بار در روز اعلان بفرست
    current_date = today.date()
    if last_suspicious_holiday_alert and last_suspicious_holiday_alert.date() == current_date:
        logger.info("⏭️ اعلان تعطیلات مشکوک قبلاً امروز ارسال شده، صرف‌نظر شد")
        return
    
    month_day = today.strftime("%m/%d")
    event_text = {
        "01/01": "نوروز", "01/02": "نوروز", "01/03": "نوروز", "01/04": "نوروز",
        "01/07": "جمعه", "01/14": "جمعه", "01/21": "جمعه", "01/28": "جمعه",
        "01/12": "روز جمهوری اسلامی", "01/13": "سیزده‌به‌در",
        "02/03": "عید فطر", "02/04": "عید فطر",
        "02/05": "جمعه", "02/12": "جمعه", "02/19": "جمعه", "02/26": "جمعه",
        "03/02": "جمعه", "03/09": "جمعه", "03/16": "عید قربان", "03/23": "جمعه", "03/30": "جمعه",
        "03/14": "رحلت امام خمینی", "03/15": "قیام 15 خرداد", "03/24": "عید غدیر خم",
        "04/06": "جمعه", "04/13": "جمعه", "04/20": "جمعه", "04/27": "جمعه",
        "04/14": "تاسوعای حسینی", "04/15": "عاشورای حسینی",
        "05/03": "جمعه", "05/10": "جمعه", "05/17": "جمعه", "05/24": "جمعه", "05/31": "رحلت رسول اکرم و شهادت امام حسن",
        "05/23": "اربعین حسینی",
        "06/02": "شهادت امام رضا",
        "06/07": "جمعه", "06/14": "جمعه", "06/21": "جمعه", "06/28": "جمعه",
        "06/10": "شهادت امام حسن عسکری", "06/19": "میلاد رسول اکرم و امام جعفر صادق",
        "07/05": "جمعه", "07/12": "جمعه", "07/19": "جمعه", "07/26": "جمعه",
        "08/03": "جمعه", "08/10": "جمعه", "08/17": "جمعه", "08/24": "جمعه",
        "09/01": "جمعه", "09/08": "جمعه", "09/15": "جمعه", "09/22": "جمعه", "09/29": "جمعه",
        "09/03": "شهادت حضرت فاطمه",
        "10/06": "جمعه", "10/13": "ولادت امام علی", "10/20": "جمعه", "10/27": "مبعث رسول اکرم",
        "11/04": "جمعه", "11/11": "جمعه", "11/18": "جمعه", "11/25": "جمعه",
        "11/15": "ولادت حضرت قائم", "11/22": "پیروزی انقلاب اسلامی",
        "12/02": "جمعه", "12/09": "جمعه", "12/16": "جمعه", "12/23": "جمعه",
        "12/20": "شهادت امام علی", "12/29": "روز ملی شدن صنعت نفت"
    }.get(month_day, "نامشخص")
    
    message = f"""
⚠️ <b>هشدار تعطیلات مشکوک!</b>
📅 تاریخ: {get_jalali_date()}
🔔 روز {today.strftime('%Y/%m/%d')} به عنوان تعطیل تشخیص داده شد
مناسبت: {event_text}
لطفاً بررسی کنید که آیا این روز واقعاً تعطیل است!
▫️ @{CHANNEL_ID.replace('@', '')}
"""
    logger.info(f"📤 در حال ارسال اعلان تعطیلات مشکوک به ADMIN_CHAT_ID={ADMIN_CHAT_ID}")
    send_message(message, chat_id=ADMIN_CHAT_ID)
    last_suspicious_holiday_alert = today
    logger.info("✅ اعلان تعطیلات مشکوک ارسال شد")

def send_holiday_notification():
    """ارسال اعلان تعطیلات"""
    today = jdatetime.datetime.now()
    month_day = today.strftime("%m/%d")
    event_text = {
        "01/01": "نوروز", "01/02": "نوروز", "01/03": "نوروز", "01/04": "نوروز",
        "01/07": "جمعه", "01/14": "جمعه", "01/21": "جمعه", "01/28": "جمعه",
        "01/12": "روز جمهوری اسلامی", "01/13": "سیزده‌به‌در",
        "02/03": "عید فطر", "02/04": "عید فطر",
        "02/05": "جمعه", "02/12": "جمعه", "02/19": "جمعه", "02/26": "جمعه",
        "03/02": "جمعه", "03/09": "جمعه", "03/16": "عید قربان", "03/23": "جمعه", "03/30": "جمعه",
        "03/14": "رحلت امام خمینی", "03/15": "قیام 15 خرداد", "03/24": "عید غدیر خم",
        "04/06": "جمعه", "04/13": "جمعه", "04/20": "جمعه", "04/27": "جمعه",
        "04/14": "تاسوعای حسینی", "04/15": "عاشورای حسینی",
        "05/03": "جمعه", "05/10": "جمعه", "05/17": "جمعه", "05/24": "جمعه", "05/31": "رحلت رسول اکرم و شهادت امام حسن",
        "05/23": "اربعین حسینی",
        "06/02": "شهادت امام رضا",
        "06/07": "جمعه", "06/14": "جمعه", "06/21": "جمعه", "06/28": "جمعه",
        "06/10": "شهادت امام حسن عسکری", "06/19": "میلاد رسول اکرم و امام جعفر صادق",
        "07/05": "جمعه", "07/12": "جمعه", "07/19": "جمعه", "07/26": "جمعه",
        "08/03": "جمعه", "08/10": "جمعه", "08/17": "جمعه", "08/24": "جمعه",
        "09/01": "جمعه", "09/08": "جمعه", "09/15": "جمعه", "09/22": "جمعه", "09/29": "جمعه",
        "09/03": "شهادت حضرت فاطمه",
        "10/06": "جمعه", "10/13": "ولادت امام علی", "10/20": "جمعه", "10/27": "مبعث رسول اکرم",
        "11/04": "جمعه", "11/11": "جمعه", "11/18": "جمعه", "11/25": "جمعه",
        "11/15": "ولادت حضرت قائم", "11/22": "پیروزی انقلاب اسلامی",
        "12/02": "جمعه", "12/09": "جمعه", "12/16": "جمعه", "12/23": "جمعه",
        "12/20": "شهادت امام علی", "12/29": "روز ملی شدن صنعت نفت"
    }.get(month_day, "تعطیل رسمی")
    
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
    """ارسال اعلان شروع روز کاری و پیام به ادمین"""
    message = f"""
📢 <b>شروع آپدیت قیمت‌ها!</b>
📅 تاریخ: {get_jalali_date()}
⏰ ساعت: {datetime.now().strftime('%H:%M')}
هر 30 دقیقه قیمت‌های جدید طلا، سکه و ارز رو می‌فرستیم!
▫️ @{CHANNEL_ID.replace('@', '')}
"""
    send_message(message)
    logger.info("✅ اعلان شروع روز کاری ارسال شد")
    
    if ADMIN_CHAT_ID:
        admin_message = f"""
✅ امروز پیام ارسال شد در روز {get_jalali_date()}
"""
        logger.info(f"📤 در حال ارسال پیام شروع روز به ADMIN_CHAT_ID={ADMIN_CHAT_ID}")
        send_message(admin_message, chat_id=ADMIN_CHAT_ID)
        logger.info("✅ پیام شروع روز به ادمین ارسال شد")

def send_test_admin_message():
    """ارسال پیام تست به ADMIN_CHAT_ID برای اطمینان از تنظیمات"""
    if not ADMIN_CHAT_ID:
        logger.warning("⚠️ ADMIN_CHAT_ID تنظیم نشده، پیام تست ارسال نشد")
        return
    
    message = f"""
🧪 <b>پیام تست برای ADMIN_CHAT_ID</b>
📅 تاریخ: {get_jalali_date()}
⏰ زمان: {datetime.now().strftime('%H:%M')}
این پیام برای اطمینان از تنظیم درست ADMIN_CHAT_ID ارسال شده است.
▫️ @{CHANNEL_ID.replace('@', '')}
"""
    logger.info(f"📤 در حال ارسال پیام تست به ADMIN_CHAT_ID={ADMIN_CHAT_ID}")
    send_message(message, chat_id=ADMIN_CHAT_ID)
    logger.info("✅ پیام تست به ادمین ارسال شد")

def send_end_notification():
    """ارسال اعلان پایان روز کاری"""
    message = f"""
📢 <b>پایان آپدیت قیمت‌ها!</b>
📅 تاریخ: {get_jalali_date()}
⏰ ساعت: {datetime.now().strftime('%H:%M')}
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
        logger.info(f"📡 ارسال درخواست به API: {url}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        logger.info(f"📥 داده‌های API دریافت شد: {data}")

        update_time = data['gold'][0]['time'] if data['gold'] else datetime.now().strftime("%H:%M")

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
⏰ زمان: {datetime.now().strftime('%H:%M')}
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
{get_price_change_emoji(prices['gold_18k']['change_percent'])} نیم سکه: {format_price(prices['half_coin']['price'])} تومان
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
    """چک کردن بازه آپدیت با ساعت سرور"""
    current_time = datetime.now()
    # اعمال offset برای تبدیل به ساعت تهران
    current_hour = (current_time.hour + int(TIME_OFFSET)) % 24
    current_minute = current_time.minute + (TIME_OFFSET % 1 * 60)
    if current_minute >= 60:
        current_hour = (current_hour + 1) % 24
        current_minute -= 60
    # تنظیم ساعت تهران
    tehran_time = f"{int(current_hour):02d}:{int(current_minute):02d}"
    logger.info(f"⏰ زمان سرور: {current_time.strftime('%H:%M')} | زمان تهران: {tehran_time}")
    return START_HOUR <= current_hour < END_HOUR

def test_holiday(date_str):
    """تابع تست برای چک کردن تعطیلی یک تاریخ خاص"""
    try:
        date = jdatetime.datetime.strptime(date_str, "%Y/%m/%d")
        month_day = date.strftime("%m/%d")
        gregorian_date = datetime.strptime(date_str, "%Y/%m/%d").strftime("%Y-%m-%d")
        logger.info(f"تست تعطیلی | تاریخ شمسی: {date_str} | تاریخ میلادی: {gregorian_date}")
        
        if month_day in NON_HOLIDAYS:
            logger.info(f"📅 {month_day} در لیست استثناها - تعطیل نیست")
            return False
        
        if month_day in HOLIDAYS:
            logger.info(f"📅 {month_day} در لیست تعطیلات یافت شد")
            return True
        
        logger.info(f"📅 {month_day} تعطیل نیست")
        return False
    except Exception as e:
        logger.error(f"❌ خطا در تست تعطیلی: {e}")
        return None

def main():
    global last_holiday_notification, start_notification_sent, end_notification_sent
    global last_suspicious_holiday_alert, last_update_time
    
    # ارسال پیام تست به ADMIN_CHAT_ID
    logger.info("🔍 ارسال پیام تست به ADMIN_CHAT_ID")
    send_test_admin_message()
    
    # تست تعطیلی برای 14 اردیبهشت 1404
    logger.info("🔍 تست تعطیلی برای 1404/02/14")
    is_holiday_14_may = test_holiday("1404/02/14")
    logger.info(f"نتیجه تست: 1404/02/14 {'تعطیل است' if is_holiday_14_may else 'تعطیل نیست'}")
    
    # تست تعطیلی برای یک جمعه (12 اردیبهشت 1404)
    logger.info("🔍 تست تعطیلی برای 1404/02/12")
    is_holiday_friday = test_holiday("1404/02/12")
    logger.info(f"نتیجه تست: 1404/02/12 {'تعطیل است' if is_holiday_friday else 'تعطیل نیست'}")
    
    while True:
        current_time = datetime.now()
        current_hour = (current_time.hour + int(TIME_OFFSET)) % 24
        current_minute = current_time.minute + (TIME_OFFSET % 1 * 60)
        if current_minute >= 60:
            current_hour = (current_hour + 1) % 24
            current_minute -= 60
        
        # ریست پرچم‌ها در شروع روز (ساعت 00:00 تهران)
        if current_hour == 0 and current_minute < 30:
            start_notification_sent = False
            end_notification_sent = False
            last_holiday_notification = None
            last_suspicious_holiday_alert = None
            logger.info("🔄 پرچم‌ها برای روز جدید ریست شدند")
        
        if is_holiday():
            if (current_hour == START_HOUR and current_minute < 30 and 
                (last_holiday_notification is None or 
                 last_holiday_notification.date() != current_time.date())):
                send_holiday_notification()
                last_holiday_notification = current_time
            logger.info(f"📅 امروز: {get_jalali_date()} - روز تعطیل، آپدیت انجام نمی‌شود")
            time.sleep(CHECK_INTERVAL)
        elif is_within_update_hours():
            if current_hour == START_HOUR and current_minute < 30 and not start_notification_sent:
                send_start_notification()
                start_notification_sent = True
            
            # چک کردن فاصله زمانی از آخرین آپدیت
            if time.time() - last_update_time >= UPDATE_INTERVAL:
                logger.info(f"⏰ زمان تهران: {current_hour:02d}:{int(current_minute):02d} - در بازه آپدیت")
                prices = get_prices()
                if prices:
                    message = create_message(prices)
                    send_message(message)
                    logger.info(f"✅ قیمت‌ها در {current_hour:02d}:{int(current_minute):02d} ارسال شدند")
                    last_update_time = time.time()
                else:
                    logger.error("❌ خطا در دریافت قیمت‌ها")
            else:
                logger.info(f"⏳ منتظر فاصله 30 دقیقه‌ای برای آپدیت بعدی")
            time.sleep(CHECK_INTERVAL)
        else:
            if current_hour == END_HOUR and current_minute < 30 and not end_notification_sent:
                send_end_notification()
                end_notification_sent = True
            
            logger.info(f"⏰ زمان تهران: {current_hour:02d}:{int(current_minute):02d} - خارج از بازه آپدیت")
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        import jdatetime
    except ImportError:
        import os
        os.system("pip install jdatetime")
        import jdatetime
    
    main()
