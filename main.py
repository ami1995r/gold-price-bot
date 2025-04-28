import requests
from datetime import datetime
import jdatetime
import time
import os

# ==================== تنظیمات ایمن ====================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')  # از متغیرهای محیطی Railway
CHANNEL_ID = os.getenv('CHANNEL_ID')
API_KEY = os.getenv('API_KEY')
UPDATE_INTERVAL = 300  # هر ۵ دقیقه
# =====================================================

def get_jalali_date():
    return jdatetime.datetime.now().strftime("%Y/%m/%d")

def get_price_change_emoji(change_percent):
    """تعیین ایموجی تغییر قیمت"""
    if change_percent > 0:
        return "🟢 (+{:.2f}%)".format(change_percent)
    elif change_percent < 0:
        return "🔴 ({:.2f}%)".format(change_percent)
    return "⚪ (0%)"

def find_item_by_symbol(items, symbol):
    for item in items:
        if item['symbol'] == symbol:
            return item
    return None

def get_prices():
    try:
        url = f'https://brsapi.ir/Api/Market/Gold_Currency.php?key={API_KEY}'
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        print("داده‌های API:", data)

        update_time = data['gold'][0]['time'] if data['gold'] else datetime.now().strftime("%H:%M")

        # گرفتن داده‌ها با نمادهای جدید
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
{get_price_change_emoji(prices['coin_new']['change_percent'])} تمام بهار: {format_price(prices['coin_new']['price'])} تومان
{get_price_change_emoji(prices['coin_old']['change_percent'])} تمام امامی: {format_price(prices['coin_old']['price'])} تومان
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

def main():
    while True:
        prices = get_prices()
        if prices:
            message = create_message(prices)
            send_message(message)
            print(f"✅ قیمت‌ها در {datetime.now().strftime('%H:%M')} ارسال شدند")
        else:
            print("❌ خطا در دریافت قیمت‌ها")
        
        time.sleep(UPDATE_INTERVAL)

if __name__ == "__main__":
    try:
        import jdatetime
    except ImportError:
        import os
        os.system("pip install jdatetime")
        import jdatetime
    
    main()
