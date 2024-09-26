import alpaca_trade_api as tradeapi
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import imaplib
import email
from email.header import decode_header
import json

class ZeroDTEStrategy:
    def __init__(self, alpaca_key, alpaca_secret, gmail_user, gmail_password):
        self.alpaca_api = tradeapi.REST(alpaca_key, alpaca_secret, base_url='https://api.alpaca.markets', api_version='v2')
        self.symbols = ['SPY', 'QQQ']
        self.data = {}
        self.gmail_user = gmail_user
        self.gmail_password = gmail_password
        self.komodo_data = self.load_komodo_data()
        self.on_fire_alerts = set()
        self.rigged_alerts = []

    def load_komodo_data(self):
        with open('komodo_data.json', 'r') as f:
            return json.load(f)

    def run(self):
        while True:
            current_time = datetime.now().time()
            if current_time >= time(9, 30) and current_time <= time(16, 0):
                self.check_gmail_alerts()
                self.update_market_data()
                self.analyze_market_conditions()
                self.check_entry_conditions()
                self.manage_positions()
            time.sleep(60)  # Run every minute

    def check_gmail_alerts(self):
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(self.gmail_user, self.gmail_password)
        mail.select('inbox')
        
        _, search_data = mail.search(None, 'UNSEEN SUBJECT "RIGGED AI Alert"')
        for num in search_data[0].split():
            _, data = mail.fetch(num, '(RFC822)')
            _, bytes_data = data[0]
            email_message = email.message_from_bytes(bytes_data)
            subject = decode_header(email_message["subject"])[0][0]
            if isinstance(subject, bytes):
                subject = subject.decode()
            
            if "ON FIRE" in subject:
                self.process_on_fire_alert(subject)
            elif "Tradeability" in subject:
                self.process_tradeability_alert(subject)
            
            mail.store(num, '+FLAGS', '\\Seen')
        
        mail.close()
        mail.logout()

    def process_on_fire_alert(self, subject):
        parts = subject.split()
        symbol = parts[1]
        side = parts[2]
        gain = float(parts[4].strip('%'))
        time = int(parts[6])
        
        self.on_fire_alerts.add((symbol, side, gain, time))
        print(f"ON FIRE Alert: {symbol} {side} {gain}% in {time} minutes")

    def process_tradeability_alert(self, subject):
        parts = subject.split()
        symbol = parts[1]
        tradeability = ' '.join(parts[3:])
        
        self.data[symbol]['tradeability'] = tradeability
        print(f"Tradeability Alert: {symbol} is now {tradeability}")

    def update_market_data(self):
        for symbol in self.symbols:
            bars = self.alpaca_api.get_bars(symbol, '1Min', limit=100).df
            self.data[symbol] = {
                'bars': bars,
                'current_price': bars.close.iloc[-1],
                'open_price': bars.open.iloc[0],
                'volume': bars.volume.sum()
            }
            
            expiration = datetime.now().strftime('%Y-%m-%d')
            options_chain = self.alpaca_api.get_option_chain(symbol, expiration)
            self.data[symbol]['options'] = options_chain

    def analyze_market_conditions(self):
        for symbol in self.symbols:
            self.data[symbol]['tradeability'] = self.calculate_tradeability(symbol)
            self.data[symbol]['ps'] = self.calculate_position_score(symbol)
            self.data[symbol]['blue_line_relation'] = self.determine_blue_line_relationship(symbol)
            self.data[symbol]['komodo'] = self.perform_komodo_analysis(symbol)

    def calculate_tradeability(self, symbol):
        volume = self.data[symbol]['volume']
        avg_volume = self.data[symbol]['bars'].volume.mean() * 100
        volume_ratio = volume / avg_volume
        
        if volume_ratio > 1.2:
            return "FULL SEND"
        elif volume_ratio > 1.1:
            return "EASY MODE"
        elif volume_ratio > 1.0:
            return "NORMAL"
        elif volume_ratio > 0.9:
            return "HARD MODE"
        else:
            return "NIGHTMARE"

    def calculate_position_score(self, symbol):
        bars = self.data[symbol]['bars']
        current_price = self.data[symbol]['current_price']
        open_price = self.data[symbol]['open_price']
        high = bars.high.max()
        low = bars.low.min()
        
        ps = (current_price - open_price) + (current_price - low) + (high - current_price)
        return ps

    def determine_blue_line_relationship(self, symbol):
        current_price = self.data[symbol]['current_price']
        open_price = self.data[symbol]['open_price']
        return current_price - open_price

    def perform_komodo_analysis(self, symbol):
        ps = self.data[symbol]['ps']
        tradeability = self.data[symbol]['tradeability']
        
        key = f"{symbol}_{tradeability}_{int(ps)}"
        if key in self.komodo_data:
            return self.komodo_data[key]
        else:
            return {"win_rate": 0.5, "edge": "ZERO", "ktr": [0, 0], "dhd": 0}

    def check_entry_conditions(self):
        for symbol in self.symbols:
            tradeability = self.data[symbol]['tradeability']
            ps = self.data[symbol]['ps']
            blue_line_relation = self.data[symbol]['blue_line_relation']
            komodo = self.data[symbol]['komodo']
            
            if tradeability in ["EASY MODE", "FULL SEND"] and komodo['win_rate'] > 0.5 and komodo['edge'] in ["EDGE", "ADV"]:
                if ps > 0 and blue_line_relation > 0:
                    self.enter_trade(symbol, 'call')
                elif ps < 0 and blue_line_relation < 0:
                    self.enter_trade(symbol, 'put')

    def enter_trade(self, symbol, option_type):
        current_price = self.data[symbol]['current_price']
        options_chain = self.data[symbol]['options']
        
        if option_type == 'call':
            strike = min([float(option.strike_price) for option in options_chain if float(option.strike_price) > current_price])
        else:
            strike = max([float(option.strike_price) for option in options_chain if float(option.strike_price) < current_price])
        
        account = self.alpaca_api.get_account()
        account_value = float(account.equity)
        risk_per_trade = 0.01
        max_loss = account_value * risk_per_trade
        
        option = next(option for option in options_chain if float(option.strike_price) == strike and option.option_type == option_type.upper())
        option_price = float(option.ask_price)
        position_size = int(max_loss / (option_price * 100))
        
        self.alpaca_api.submit_order(
            symbol=option.symbol,
            qty=position_size,
            side='buy',
            type='market',
            time_in_force='day'
        )
        
        print(f"Entered trade: {symbol} {option_type} at strike {strike}, quantity {position_size}")

    def manage_positions(self):
        positions = self.alpaca_api.list_positions()
        for position in positions:
            symbol = position.symbol
            entry_price = float(position.avg_entry_price)
            current_price = float(position.current_price)
            unrealized_pl = float(position.unrealized_plpc)
            
            if unrealized_pl > 0.5:
                self.exit_trade(position)
            elif unrealized_pl < -0.2:
                self.exit_trade(position)
            
            if datetime.now().time() > time(15, 45):
                self.exit_trade(position)

    def exit_trade(self, position):
        self.alpaca_api.submit_order(
            symbol=position.symbol,
            qty=position.qty,
            side='sell',
            type='market',
            time_in_force='day'
        )
        
        print(f"Exited trade: {position.symbol}, quantity {position.qty}")

if __name__ == "__main__":
    alpaca_key = "AK7JFBTUXGCSLMT4HT1X"
    alpaca_secret = "tZ8k80tGG26amIPFw6aLz7zaOKhTdz0D0AI8F93G"
    gmail_user = "ryan.rigd@gmail.com"
    gmail_password = "Showmetherigdai3."
    
    strategy = ZeroDTEStrategy(alpaca_key, alpaca_secret, gmail_user, gmail_password)
    strategy.run()