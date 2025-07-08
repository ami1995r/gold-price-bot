import requests
from datetime import datetime
import jdatetime
import time
import os
import logging
try:
    from importlib.metadata import distribution
except ImportError:
    logging.error("❌ ماژول importlib.metadata پیدا نشد. لطفاً از پایتون 3.8 یا بالاتر استفاده کنید.")
    distribution = None

# تنظیم لاگ‌گذاری
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== تنظیمات ایمن ====================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
API_KEY = os.getenv('API_KEY')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')
WHATSAPP_TOKEN = os.getenv('WHATSAPP_TOKEN', 'K4KIIXCfnPrp9pu6rCb8crIo87LYSVyv')
WHATSAPP_PHONE = os.getenv('WHATSAPP_PHONE')
UPDATE_INTERVAL = 1800  # هر 30 دقیقه
CHECK_INTERVAL = 300    # هر 5 دقیقه
START_HOUR = 11         # ساعت 11 صبح تهران
END_HOUR = 20           # ساعت 8 شب تهران
TIME_OFFSET = 3.5       # اختلاف ساعت تهران با UTC (در ساعت)
CHANGE_THRESHOLD = 3.0  # آستانه تغییر قیمت (3٪)
MIN_EMERGENCY_INTERVAL = 300  # حداقل فاصله آپدیت فوری
TRIAL_CHECK_INTERVAL = 21600  # هر 6 ساعت (6 * 60 * 60)
# =====================================================

# لاگ نسخه‌های پکیج‌ها
if distribution:
    try:
        jdatetime_version = distribution('jdatetime').version
        logger.info(f"📦 نسخه پکیج‌ها: jdatetime={jdatetime_version}")
    except Exception as e:
        logger.error(f"❌ خطا در بررسی نسخه پکیج‌ها: {e}")
else:
    logger.warning("⚠️ importlib.metadata در دسترس نیست، نسخه پکیج‌ها بررسی نشد")

# چک کردن متغیرهای محیطی
if not all([API_KEY, ADMIN_CHAT_ID]):
    missing_vars = [var for var, val in [('API_KEY', API_KEY), ('ADMIN_CHAT_ID', ADMIN_CHAT_ID)] if not val]
    error_message = f"❌ متغیرهای الزامی تنظیم نشده‌اند: {', '.join(missing_vars)}"
    logger.error(error_message)
    raise EnvironmentError(error_message)

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
last_trial_check_time = 0
trial_alert_sent = False

def get_tehran_time():
    """محاسبه ساعت و دقیقه تهران با اعمال TIME_OFFSET"""
    current_time = datetime.now()
    total_minutes = current_time.hour * 60 + current_time.minute + int(TIME_OFFSET * 60)
    tehran_hour = total_minutes // 60 % 24
    tehran_minute = total_minutes % 60
    logger.info(f"⏰ زمان سرور: {current_time.strftime('%H:%M')} | زمان تهران: {tehran_hour:02d}:{tehran_minute:02d}")
    return tehran_hour, tehran_minute

def send_message(text, chat_id=None):
    """ارسال پیام به تلگرام و واتس‌اپ به صورت همزمان"""
    success = False
    
    # ارسال به تلگرام (اگه توکن تنظیم شده باشه)
    if TELEGRAM_TOKEN and CHANNEL_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {
                'chat_id': CHANNEL_ID if not chat_id else chat_id,
                'text': text,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True
            }
            logger.info(f"📤 در حال ارسال پیام به تلگرام: {CHANNEL_ID if not chat_id else chat_id}")
            response = requests.post(url, json=payload, timeout=10)
            logger.info(f"📥 پاسخ تلگرام: {response.text}")
            response.raise_for_status()
            logger.info("✅ پیام به تلگرام ارسال شد")
            success = True
        except Exception as e:
            logger.error(f"❌ ارسال پیام به تلگرام ناموفق: {e}")
    
    # ارسال به واتس‌اپ (اگه توکن و شماره تنظیم شده باشه)
    if WHATSAPP_TOKEN and WHATSAPP_PHONE:
        try:
            url = f"https://api.whapi.cloud/messages/text"
            headers = {
                "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                "Content-Type": "application/json"
            }
            payload = {
                "to": WHATSAPP_PHONE if not chat_id else chat_id,
                "body": text  # واتس‌اپ از HTML پشتیبانی نمی‌کنه، متن ساده می‌فرسته
            }
            logger.info(f"📤 در حال ارسال پیام به واتس‌اپ: {WHATSAPP_PHONE if not chat_id else chat_id}")
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            logger.info(f"📥 پاسخ واتس‌اپ: {response.text}")
            response.raise_for_status()
            logger.info("✅ پیام به واتس‌اپ ارسال شد")
            success = True
        except Exception as e:
            logger.error(f"❌ ارسال پیام به واتس‌اپ ناموفق: {e}")
    
    return success

def get_jalali_date():
    """گرفتن تاریخ شمسی بدون منطقه زمانی"""
    return jdatetime.datetime.now().strftime("%Y/%m/%d")

def is_holiday():
    """چک کردن اینکه امروز تعطیل است یا نه"""
    today = jdatetime.datetime.now()
    month_day = today.strftime("%m/%d")
    gregorian_date = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"📅 تاریخ شمسی: {get_jalali_date()} | تاریخ میلادی: {gregorian_date}")

    if month_day in NON_HOLIDAYS:
        logger.info(f"📅 {month_day} در لیست استثناها - تعطیل نیست")
        return False
    
    if month_day in HOLIDAYS:
        logger.info(f"📅 {month_day} در لیست تعطیلات یافت شد")
        send_suspicious_holiday_alert(today)
        return True
    
    logger.info(f"📅 {month_day} تعطیل نیست")
    return False

def send_suspicious_holiday_alert(today):
    """ارسال اعلان برای تعطیلات مشکوک به ادمین"""
    global last_suspicious_holiday_alert
    if not ADMIN_CHAT_ID:
        logger.warning("⚠️ ADMIN_CHAT_ID تنظیم نشده، اعلان تعطیلات مشکوک ارسال نشد")
        return
    
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
        "04/14": "تاسوعا", "04/15": "عاشورا",
        "05/03": "جمعه", "05/10": "جمعه", "05/17": "جمعه", "05/24": "جمعه", "05/31": "رحلت رسول و شهادت امام حسن",
        "05/23": "اربعین",
        "06/02": "شهادت امام رضا",
        "06/07": "جمعه", "06/14": "جمعه", "06/21": "جمعه", "06/28": "جمعه",
        "06/10": "شهادت امام حسن عسکری", "06/19": "میلاد رسول اکرم و امام جعفر صادق",
        "07/05": "جمعه", "07/12": "جمعه", "07/19": "جمعه", "07/26": "جمعه",
        "08/03": "جمعه", "08/10": "جمعه", "08/17": "جمعه", "08/24": "جمعه",
        "09/01": "جمعه", "09/08": "جمعه", "09/15": "جمعه", "09/22": "جمعه", "09/29": "جمعه",
        "09/03": "شهادت حضرت فاطمه",
        "10/06": "جمعه", "10/13": "ولادت امام علی", "10/20": "جمعه", "10/27": "مبعث",
        "11/04": "جمعه", "11/11": "جمعه", "11/18": "جمعه", "11/25": "جمعه",
        "11/15": "ولادت حضرت قائم", "11/22": "پیروزی انقلاب اسلامی",
        "12/02": "جمعه", "12/09": "جمعه", "12/16": "جمعه", "12/23": "جمعه",
        "12/20": "شهادت امام علی", "12/29": "روز ملی شدن صنعت نفت"
    }.get(month_day, "نامشخص")
    
    message = f"""
⚠️ هشدار تعطیلات مشکوک!
📅 تاریخ: {get_jalali_date()}
🔔 روز {today.strftime('%Y/%m/%d')} به عنوان تعطیل تشخیص داده شد
مناسبت: {event_text}
لطفاً بررسی کنید که آیا این روز واقعاً تعطیل است!
▫️ {CHANNEL_ID if CHANNEL_ID else WHATSAPP_PHONE}
"""
    logger.info(f"📤 در حال ارسال اعلان تعطیلات مشکوک به ADMIN_CHAT_ID={ADMIN_CHAT_ID}")
    send_message(message, chat_id=ADMIN_CHAT_ID)
    last_suspicious_holiday_alert = today
    logger.info("✅ اعلان تعطیلات مشکوک ارسال شد")

def send_holiday_notification():
    """ارسال اعلان تعطیلات به ادمین"""
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
        "04/14": "تاسوعا", "04/15": "عاشورا",
        "05/03": "جمعه", "05/10": "جمعه", "05/17": "جمعه", "05/24": "جمعه", "05/31": "رحلت رسول و شهادت امام حسن",
        "05/23": "اربعین",
        "06/02": "شهادت امام رضا",
        "06/07": "جمعه", "06/14": "جمعه", "06/21": "جمعه", "06/28": "جمعه",
        "06/10": "شهادت امام حسن عسکری", "06/19": "میلاد رسول اکرم و امام جعفر صادق",
        "07/05": "جمعه", "07/12": "جمعه", "07/19": "جمعه", "07/26": "جمعه",
        "08/03": "جمعه", "08/10": "جمعه", "08/17": "جمعه", "08/24": "جمعه",
        "09/01": "جمعه", "09/08": "جمعه", "09/15": "جمعه", "09/22": "جمعه", "09/29": "جمعه",
        "09/03": "شهادت حضرت فاطمه",
        "10/06": "جمعه", "10/13": "ولادت امام علی", "10/20": "جمعه", "10/27": "مبعث",
        "11/04": "جمعه", "11/11": "جمعه", "11/18": "جمعه", "11/25": "جمعه",
        "11/15": "ولادت حضرت قائم", "11/22": "پیروزی انقلاب اسلامی",
        "12/02": "جمعه", "12/09": "جمعه", "12/16": "جمعه", "12/23": "جمعه",
        "12/20": "شهادت امام علی", "12/29": "روز ملی شدن صنعت نفت"
    }.get(month_day, "تعطیل رسمی")
    
    message = f"""
📢 امروز تعطیله!
📅 تاریخ: {get_jalali_date()}
🔔 مناسبت: {event_text}
بازار بسته‌ست و آپدیت قیمت نداریم. روز کاری بعدی ساعت 11 صبح شروع می‌کنیم!
▫️ {CHANNEL_ID if CHANNEL_ID else WHATSAPP_PHONE}
"""
    logger.info(f"📤 در حال ارسال اعلان تعطیلات به ADMIN_CHAT_ID={ADMIN_CHAT_ID}")
    send_message(message, chat_id=ADMIN_CHAT_ID)
    logger.info("✅ اعلان تعطیلات ارسال شد")

def send_immediate_test_message():
    """ارسال پیام تست فوری به ادمین"""
    if not ADMIN_CHAT_ID:
        logger.warning("⚠️ ADMIN_CHAT_ID تنظیم نشده، پیام تست فوری ارسال نشد")
        return
    
    tehran_hour, tehran_minute = get_tehran_time()
    message = f"""
🚨 پیام تست فوری
📅 تاریخ: {get_jalali_date()}
⏰ زمان: {tehran_hour:02d}:{tehran_minute:02d}
این پیام برای تست ارسال فوری فرستاده شده است.
لطفاً دریافت این پیام را تأیید کنید!
▫️ {CHANNEL_ID if CHANNEL_ID else WHATSAPP_PHONE}
"""
    logger.info(f"📤 در حال ارسال پیام تست فوری به ADMIN_CHAT_ID={ADMIN_CHAT_ID}")
    send_message(message, chat_id=ADMIN_CHAT_ID)
    logger.info("✅ پیام تست فوری به ادمین ارسال شد")

def send_trial_expiry_alert():
    """ارسال پیام هشدار اتمام تریال به ادمین"""
    global trial_alert_sent
    if trial_alert_sent:
        logger.info("⏭️ پیام هشدار اتمام تریال قبلاً ارسال شده، صرف‌نظر شد")
        return
    
    tehran_hour, tehran_minute = get_tehran_time()
    message = f"""
⚠️ هشدار اتمام تریال Railway!
📅 تاریخ: {get_jalali_date()}
⏰ زمان: {tehran_hour:02d}:{tehran_minute:02d}
به نظر می‌رسد اکانت تریال Railway شما به پایان رسیده است.
لطفاً به Railway مراجعه کنید و وضعیت اکانت را بررسی کنید!
"""
    logger.info(f"📤 در حال ارسال پیام هشدار اتمام تریال به ADMIN_CHAT_ID={ADMIN_CHAT_ID}")
    if send_message(message, chat_id=ADMIN_CHAT_ID):
        trial_alert_sent = True
        logger.info("✅ پیام هشدار اتمام تریال ارسال شد")
    else:
        logger.error("❌ ارسال پیام هشدار اتمام تریال ناموفق بود")

def check_trial_status():
    """چک کردن وضعیت اکانت Railway با ارسال پیام تست"""
    global last_trial_check_time
    current_time = time.time()
    
    if current_time - last_trial_check_time < TRIAL_CHECK_INTERVAL:
        logger.info("⏳ فاصله چک وضعیت اکانت کمتر از 6 ساعت است، منتظر می‌مانیم")
        return
    
    tehran_hour, tehran_minute = get_tehran_time()
    test_message = f"""
🔔 چک وضعیت اکانت Railway
📅 تاریخ: {get_jalali_date()}
⏰ زمان: {tehran_hour:02d}:{tehran_minute:02d}
این پیام برای چک کردن وضعیت سرور ارسال شده است.
"""
    logger.info(f"📤 در حال ارسال پیام تست وضعیت به ADMIN_CHAT_ID={ADMIN_CHAT_ID}")
    if not send_message(test_message, chat_id=ADMIN_CHAT_ID):
        logger.warning("⚠️ ارسال پیام تست وضعیت ناموفق بود، احتمالاً اکانت تریال تمام شده است")
        send_trial_expiry_alert()
    else:
        logger.info("✅ پیام تست وضعیت با موفقیت ارسال شد، سرور فعال است")
    
    last_trial_check_time = current_time

def send_start_notification():
    """ارسال پیام شروع به ادمین"""
    global start_notification_sent
    tehran_hour, tehran_minute = get_tehran_time()
    
    if ADMIN_CHAT_ID and not start_notification_sent:
        admin_message = f"""
✅ امروز پیام ارسال شد در روز {get_jalali_date()}
⏰ ساعت: {tehran_hour:02d}:{tehran_minute:02d}
"""
        logger.info(f"📤 در حال ارسال پیام شروع روز به ADMIN_CHAT_ID={ADMIN_CHAT_ID}")
        send_message(admin_message, chat_id=ADMIN_CHAT_ID)
        logger.info("✅ پیام شروع روز به ادمین ارسال شد")
        start_notification_sent = True

def send_test_admin_message():
    """ارسال پیام تست به ADMIN_CHAT_ID برای اطمینان از تنظیمات"""
    if not ADMIN_CHAT_ID:
        logger.warning("⚠️ ADMIN_CHAT_ID تنظیم نشده، پیام تست ارسال نشد")
        return
    
    tehran_hour, tehran_minute = get_tehran_time()
    message = f"""
🧪 پیام تست برای ADMIN_CHAT_ID
📅 تاریخ: {get_jalali_date()}
⏰ زمان: {tehran_hour:02d}:{tehran_minute:02d}
این پیام برای اطمینان از تنظیم درست ADMIN_CHAT_ID ارسال شده است.
▫️ {CHANNEL_ID if CHANNEL_ID else WHATSAPP_PHONE}
"""
    logger.info(f"📤 در حال ارسال پیام تست به ADMIN_CHAT_ID={ADMIN_CHAT_ID}")
    send_message(message, chat_id=ADMIN_CHAT_ID)
    logger.info("✅ پیام تست به ادمین ارسال شد")

def send_end_notification():
    """ارسال پیام پایان به ادمین"""
    global end_notification_sent
    tehran_hour, tehran_minute = get_tehran_time()
    
    if ADMIN_CHAT_ID and not end_notification_sent:
        admin_message = f"""
✅ روز کاری به پایان رسید در تاریخ {get_jalali_date()}
⏰ ساعت: {tehran_hour:02d}:{tehran_minute:02d}
"""
        logger.info(f"📤 در حال ارسال پیام پایان روز به ADMIN_CHAT_ID={ADMIN_CHAT_ID}")
        send_message(admin_message, chat_id=ADMIN_CHAT_ID)
        logger.info("✅ پیام پایان روز به ادمین ارسال شد")
        end_notification_sent = True

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
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
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
                tehran_hour, tehran_minute = get_tehran_time()
                emergency_message = f"""
📢 خبر مهم از بازار!
📅 تاریخ: {get_jalali_date()}
⏰ زمان: {tehran_hour:02d}:{tehran_minute:02d}
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
                    emergency_message += f"{get_price_change_emoji(change_percent)} {name} به {format_price(new_price)} تومان رسید\n"
                emergency_message += f"▫️ {CHANNEL_ID if CHANNEL_ID else WHATSAPP_PHONE}"
                logger.info(f"📤 در حال ارسال اعلان تغییر قیمت مهم")
                send_message(emergency_message)
                last_emergency_update = current_time

        last_prices = prices
        return prices
    except Exception as e:
        logger.error(f"❌ خطا در دریافت داده قیمت‌ها: {e}")
        return None

def create_message(prices):
    """ایجاد پیام قیمت‌ها"""
    tehran_hour, tehran_minute = get_tehran_time()
    return f"""
📅 تاریخ: {get_jalali_date()}
⏰ آخرین آپدیت: {tehran_hour:02d}:{tehran_minute:02d}

📊 قیمت‌های لحظه‌ای بازار

طلا
{get_price_change_emoji(prices['gold_ounce']['change_percent'])} انس جهانی: {prices['gold_ounce']['price']}
{get_price_change_emoji(prices['gold_18k']['change_percent'])} 18 عیار: {format_price(prices['gold_18k']['price'])} تومان

سکه
{get_price_change_emoji(prices['coin_old']['change_percent'])} تمام امامی: {format_price(prices['coin_old']['price'])} تومان
{get_price_change_emoji(prices['coin_new']['change_percent'])} تمام بهار: {format_price(prices['coin_new']['price'])} تومان
{get_price_change_emoji(prices['half_coin']['change_percent'])} نیم سکه: {format_price(prices['half_coin']['price'])} تومان
{get_price_change_emoji(prices['quarter_coin']['change_percent'])} ربع سکه: {format_price(prices['quarter_coin']['price'])} تومان
{get_price_change_emoji(prices['gram_coin']['change_percent'])} سکه گرمی: {format_price(prices['gram_coin']['price'])} تومان

ارزها
{get_price_change_emoji(prices['usd']['change_percent'])} دلار: {format_price(prices['usd']['price'])} تومان
{get_price_change_emoji(prices['usdt']['change_percent'])} تتر: {format_price(prices['usdt']['price'])} تومان
{get_price_change_emoji(prices['eur']['change_percent'])} یورو: {format_price(prices['eur']['price'])} تومان
{get_price_change_emoji(prices['gbp']['change_percent'])} پوند: {format_price(prices['gbp']['price'])} تومان
{get_price_change_emoji(prices['aed']['change_percent'])} درهم: {format_price(prices['aed']['price'])} تومان

▫️ {CHANNEL_ID if CHANNEL_ID else WHATSAPP_PHONE}
"""

def format_price(price):
    try:
        return f"{int(float(price)):,}"
    except:
        return "نامشخص"

def is_within_update_hours():
    """چک کردن بازه آپدیت با ساعت تهران"""
    tehran_hour, tehran_minute = get_tehran_time()
    is_within_hours = START_HOUR <= tehran_hour < END_HOUR
    logger.info(f"⏰ زمان تهران: {tehran_hour:02d}:{tehran_minute:02d} - {'در بازه آپدیت' if is_within_hours else 'خارج از بازه آپدیت'}")
    return is_within_hours

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
    global last_suspicious_holiday_alert, last_update_time, trial_alert_sent
    
    # ارسال پیام تست فوری به ادمین
    logger.info("🚨 ارسال پیام تست فوری به ADMIN_CHAT_ID")
    send_immediate_test_message()
    
    logger.info("🔍 ارسال پیام تست به ADMIN_CHAT_ID")
    send_test_admin_message()
    
    logger.info("🔍 تست تعطیلی برای 1404/02/14")
    is_holiday_14_may = test_holiday("1404/02/14")
    logger.info(f"نتیجه تست: 1404/02/14 {'تعطیل است' if is_holiday_14_may else 'تعطیل نیست'}")
    
    logger.info("🔍 تست تعطیلی برای 1404/02/12")
    is_holiday_friday = test_holiday("1404/02/12")
    logger.info(f"نتیجه تست: 1404/02/12 {'تعطیل است' if is_holiday_friday else 'تعطیل نیست'}")
    
    while True:
        try:
            tehran_hour, tehran_minute = get_tehran_time()
            
            # چک کردن وضعیت اکانت Railway
            check_trial_status()
            
            if tehran_hour == 0 and tehran_minute < 30:
                start_notification_sent = False
                end_notification_sent = False
                last_holiday_notification = None
                last_suspicious_holiday_alert = None
                trial_alert_sent = False
                logger.info("🔄 پرچم‌ها برای روز جدید ریست شدند")
            
            if is_holiday():
                if (tehran_hour == START_HOUR and tehran_minute < 30 and 
                    (last_holiday_notification is None or 
                     last_holiday_notification.date() != datetime.now().date())):
                    send_holiday_notification()
                    last_holiday_notification = datetime.now()
                logger.info(f"📅 امروز: {get_jalali_date()} - روز تعطیل، آپدیت انجام نمی‌شود")
                time.sleep(CHECK_INTERVAL)
            elif is_within_update_hours():
                if tehran_hour == START_HOUR and tehran_minute < 30 and not start_notification_sent:
                    send_start_notification()
                
                if time.time() - last_update_time >= UPDATE_INTERVAL:
                    logger.info(f"⏰ زمان تهران: {tehran_hour:02d}:{tehran_minute:02d} - در بازه آپدیت")
                    prices = get_prices()
                    if prices:
                        message = create_message(prices)
                        send_message(message)  # ارسال همزمان به تلگرام و واتس‌اپ
                        logger.info(f"✅ قیمت‌ها در {tehran_hour:02d}:{tehran_minute:02d} ارسال شدند")
                        last_update_time = time.time()
                    else:
                        logger.error("❌ خطا در دریافت قیمت‌ها")
                else:
                    logger.info(f"⏳ منتظر فاصله 30 دقیقه‌ای برای آپدیت بعدی")
                time.sleep(CHECK_INTERVAL)
            else:
                if tehran_hour == END_HOUR and tehran_minute < 30 and not end_notification_sent:
                    send_end_notification()
                
                logger.info(f"⏰ زمان تهران: {tehran_hour:02d}:{tehran_minute:02d} - خارج از بازه آپدیت")
                time.sleep(CHECK_INTERVAL)
        except Exception as e:
            logger.error(f"❌ خطای غیرمنتظره در حلقه اصلی: {e}")
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        import jdatetime
    except ImportError:
        import os
        os.system("pip install jdatetime")
        import jdatetime
    
    main()
