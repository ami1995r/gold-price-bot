import requests
from datetime import datetime
import jdatetime
import time
import os
from server import keep_alive

# ==================== تنظیمات ایمن ====================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')  # از Secrets استفاده می‌کنیم
CHANNEL_ID = os.getenv('CHANNEL_ID')
API_KEY = os.getenv('API_KEY')
UPDATE_INTERVAL = 300  # 5 دقیقه (ثانیه)
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

def get_prices():
    try:
        url = f'https://brsapi.ir/Api/Market/Gold_Currency.php?key={API_KEY}'
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        update_time = data['gold'][0]['time'] if data['gold'] else datetime.now().strftime("%H:%M")
        
        return {
            'update_time': update_time,
            'gold_ounce': next((item for item in data['gold'] if item['symbol'] == 'XAUUSD'), 
                             {'price': 'N/A', 'change_percent': 0}),
            # ... (بقیه آیتم‌ها مانند کد شما)
        }
    except Exception as e:
        print(f"❌ خطا در دریافت داده: {e}")
        return None

def send_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        response = requests.post(url, json={
            'chat_id': CHANNEL_ID,
            'text': text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        })
        response.raise_for_status()
    except Exception as e:
        print(f"❌ ارسال پیام ناموفق: {e}")

def create_message(prices):
    return f"""
📅 <b>تاریخ: {get_jalali_date()}</b>
⏰ <b>آخرین بروزرسانی: {prices['update_time']}</b>

📊 <b>قیمت‌های لحظه‌ای بازار</b>

<b>🏆 طلا</b>
{get_price_change_emoji(prices['gold_ounce']['change_percent'])} انس جهانی: {prices['gold_ounce']['price']} دلار
{get_price_change_emoji(prices['gold_18k']['change_percent'])} 18 عیار: {int(prices['gold_18k']['price']):,} تومان
{get_price_change_emoji(prices['gold_24k']['change_percent'])} 24 عیار: {int(prices['gold_24k']['price']):,} تومان

<b>🏅 سکه</b>
{get_price_change_emoji(prices['coin_new']['change_percent'])} تمام بهار: {int(prices['coin_new']['price']):,} تومان
{get_price_change_emoji(prices['coin_old']['change_percent'])} تمام امامی: {int(prices['coin_old']['price']):,} تومان
{get_price_change_emoji(prices['half_coin']['change_percent'])} نیم سکه: {int(prices['half_coin']['price']):,} تومان
{get_price_change_emoji(prices['quarter_coin']['change_percent'])} ربع سکه: {int(prices['quarter_coin']['price']):,} تومان
{get_price_change_emoji(prices['gram_coin']['change_percent'])} سکه گرمی: {int(prices['gram_coin']['price']):,} تومان

<b>💱 ارزها</b>
{get_price_change_emoji(prices['usd']['change_percent'])} دلار: {int(prices['usd']['price']):,} تومان
{get_price_change_emoji(prices['eur']['change_percent'])} یورو: {int(prices['eur']['price']):,} تومان
{get_price_change_emoji(prices['gbp']['change_percent'])} پوند: {int(prices['gbp']['price']):,} تومان
{get_price_change_emoji(prices['aed']['change_percent'])} درهم: {int(prices['aed']['price']):,} تومان
{get_price_change_emoji(prices['usdt']['change_percent'])} تتر: {int(prices['usdt']['price']):,} تومان

📢 @{CHANNEL_ID.replace('@', '')}
"""

def main():
    keep_alive()  # فعال نگه داشتن بات
    
    while True:
        prices = get_prices()
        if prices:
            send_message(create_message(prices))
            print(f"✅ قیمت‌ها در {datetime.now().strftime('%H:%M')} ارسال شدند")
        else:
            print("❌ خطا در دریافت قیمت‌ها")
        
        time.sleep(UPDATE_INTERVAL)

if __name__ == "__main__":
    # نصب خودکار کتابخانه‌ها
    try:
        import jdatetime
    except ImportError:
        import os
        os.system("pip install jdatetime")
        import jdatetime
    
    main()