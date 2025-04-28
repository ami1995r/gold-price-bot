def get_prices():
    try:
        url = f'https://brsapi.ir/Api/Market/Gold_Currency.php?key={API_KEY}'
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        def find_item(symbol):
            return next((item for item in data['gold'] if item['symbol'] == symbol), {'price': 'N/A', 'change_percent': 0})

        update_time = data['gold'][0]['time'] if data['gold'] else datetime.now().strftime("%H:%M")
        
        return {
            'update_time': update_time,
            'gold_ounce': find_item('XAUUSD'),
            'gold_18k': find_item('G18K'),  # اینجا نماد درست باید باشه
            'gold_24k': find_item('G24K'),
            'coin_new': find_item('NEW_COIN'),
            'coin_old': find_item('OLD_COIN'),
            'half_coin': find_item('HALF_COIN'),
            'quarter_coin': find_item('QUARTER_COIN'),
            'gram_coin': find_item('GRAM_COIN'),
            'usd': find_item('USD'),
            'eur': find_item('EUR'),
            'gbp': find_item('GBP'),
            'aed': find_item('AED'),
            'usdt': find_item('USDT')
        }
    except Exception as e:
        print(f"❌ خطا در دریافت داده: {e}")
        return None
