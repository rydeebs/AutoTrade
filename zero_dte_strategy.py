import alpaca_trade_api as tradeapi
import pandas as pd
import numpy as np
from datetime import datetime, time
import time as time_module
import imaplib
import email
from email.header import decode_header
import json
import logging
from config import ALPACA_API_KEY, ALPACA_SECRET_KEY, GMAIL_USER, GMAIL_PASSWORD

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ZeroDTEStrategy:
    def __init__(self, alpaca_key, alpaca_secret, gmail_user, gmail_password):
        self.alpaca_api = tradeapi.REST(alpaca_key, alpaca_secret, base_url='https://paper-api.alpaca.markets', api_version='v2')
        self.symbols = ['SPY', 'QQQ']  # Initial symbols
        self.data = {}
        self.gmail_user = gmail_user
        self.gmail_password = gmail_password
        self.on_fire_alerts = set()
        self.rigged_alerts = []

    def test_api_connection(self):
        try:
            account = self.alpaca_api.get_account()
            logger.info(f"Successfully connected to Alpaca API. Account status: {account.status}")
            buying_power = float(account.buying_power)
            logger.info(f"Current buying power: ${buying_power}")
        except Exception as e:
            logger.error(f"Failed to connect to Alpaca API: {str(e)}")

    def run(self):
        self.test_api_connection()
        while True:
            try:
                current_time = datetime.now().time()
                if time(9, 30) <= current_time <= time(16, 0):
                    logger.info("Market is open, checking conditions...")
                    self.check_gmail_alerts()
                    for symbol in self.symbols:
                        self.update_market_data_for_symbol(symbol)
                        self.analyze_market_conditions_for_symbol(symbol)
                        self.check_entry_conditions_for_symbol(symbol)
                    self.manage_positions()
                else:
                    logger.info("Market is closed, waiting...")
                time_module.sleep(60)  # Run every minute
            except Exception as e:
                logger.error(f"Error in main loop: {str(e)}", exc_info=True)
                time_module.sleep(300)  # Wait 5 minutes before retrying

    def check_gmail_alerts(self):
        mail = None
        try:
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
            logger.info("Checked Gmail alerts successfully")
        except Exception as e:
            logger.error(f"Error checking Gmail alerts: {str(e)}", exc_info=True)
        finally:
            if mail and mail.state != 'NONAUTH':
                try:
                    mail.close()
                except:
                    pass
            if mail:
                try:
                    mail.logout()
                except:
                    pass

    def process_on_fire_alert(self, subject):
        try:
            parts = subject.split()
            if len(parts) < 2:
                logger.error(f"Invalid ON FIRE alert format: {subject}")
                return

            symbol = parts[1]  # Assuming the ticker is always the second word in the subject
            
            # Add the symbol to our tracked symbols if it's not already there
            if symbol not in self.symbols:
                self.symbols.append(symbol)
                logger.info(f"Added new symbol to track: {symbol}")

            # Extract other information if available
            side = parts[2] if len(parts) > 2 else "Unknown"
            gain = float(parts[4].strip('%')) if len(parts) > 4 else 0
            alert_time = int(parts[6]) if len(parts) > 6 else 0

            self.on_fire_alerts.add((symbol, side, gain, alert_time))
            logger.info(f"ON FIRE Alert: {symbol} {side} {gain}% in {alert_time} minutes")

            # Trigger immediate analysis for this symbol
            self.update_market_data_for_symbol(symbol)
            self.analyze_market_conditions_for_symbol(symbol)
            self.check_entry_conditions_for_symbol(symbol)

        except Exception as e:
            logger.error(f"Error processing ON FIRE alert: {str(e)}", exc_info=True)

    def process_tradeability_alert(self, subject):
        try:
            parts = subject.split()
            symbol = parts[1]
            tradeability = ' '.join(parts[3:])
            
            self.data[symbol]['tradeability'] = tradeability
            logger.info(f"Tradeability Alert: {symbol} is now {tradeability}")
        except Exception as e:
            logger.error(f"Error processing Tradeability alert: {str(e)}", exc_info=True)

    def update_market_data_for_symbol(self, symbol):
        try:
            bars = self.alpaca_api.get_bars(symbol, '1Min', limit=100).df
            logger.info(f"Retrieved {len(bars)} bars for {symbol}")
            self.data[symbol] = {
                'bars': bars,
                'current_price': bars.close.iloc[-1],
                'open_price': bars.open.iloc[0],
                'volume': bars.volume.sum()
            }
            logger.info(f"Updated market data for {symbol}")
            print(f"Current market conditions for {symbol}: Price={self.data[symbol]['current_price']}, Volume={self.data[symbol]['volume']}")
        except Exception as e:
            logger.error(f"Error updating market data for {symbol}: {str(e)}", exc_info=True)

    def analyze_market_conditions_for_symbol(self, symbol):
        try:
            self.data[symbol]['tradeability'] = self.calculate_tradeability(symbol)
            self.data[symbol]['ps'] = self.calculate_position_score(symbol)
            self.data[symbol]['blue_line_relation'] = self.determine_blue_line_relationship(symbol)
            logger.info(f"Analyzed market conditions for {symbol}: Tradeability={self.data[symbol]['tradeability']}, PS={self.data[symbol]['ps']}, Blue Line Relation={self.data[symbol]['blue_line_relation']}")
        except Exception as e:
            logger.error(f"Error analyzing market conditions for {symbol}: {str(e)}", exc_info=True)

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

    def check_entry_conditions_for_symbol(self, symbol):
        try:
            tradeability = self.data[symbol]['tradeability']
            ps = self.data[symbol]['ps']
            blue_line_relation = self.data[symbol]['blue_line_relation']
            
            logger.info(f"Checking entry conditions for {symbol}: Tradeability={tradeability}, PS={ps}, Blue Line Relation={blue_line_relation}")
            
            if tradeability in ["EASY MODE", "FULL SEND"]:
                if ps > 0 and blue_line_relation > 0:
                    logger.info(f"Entry conditions met for {symbol} LONG")
                    self.enter_trade(symbol, 'buy')
                elif ps < 0 and blue_line_relation < 0:
                    logger.info(f"Entry conditions met for {symbol} SHORT")
                    self.enter_trade(symbol, 'sell')
            else:
                logger.info(f"No entry conditions met for {symbol}")
        except Exception as e:
            logger.error(f"Error checking entry conditions for {symbol}: {str(e)}", exc_info=True)

    def enter_trade(self, symbol, side):
        try:
            account = self.alpaca_api.get_account()
            account_value = float(account.equity)
            risk_per_trade = 0.01
            max_loss = account_value * risk_per_trade
            
            current_price = self.data[symbol]['current_price']
            position_size = int(max_loss / current_price)
            
            self.alpaca_api.submit_order(
                symbol=symbol,
                qty=position_size,
                side=side,
                type='market',
                time_in_force='day'
            )
            
            logger.info(f"Entered trade: {symbol} {side} quantity {position_size}")
        except Exception as e:
            logger.error(f"Error entering trade for {symbol} {side}: {str(e)}", exc_info=True)

    def manage_positions(self):
        try:
            positions = self.alpaca_api.list_positions()
            for position in positions:
                symbol = position.symbol
                entry_price = float(position.avg_entry_price)
                current_price = float(position.current_price)
                unrealized_pl = float(position.unrealized_plpc)
                
                logger.info(f"Managing position: {symbol}, Entry: ${entry_price}, Current: ${current_price}, P/L: {unrealized_pl:.2%}")
                
                if unrealized_pl > 0.3:
                    logger.info(f"Exiting {symbol} for profit")
                    self.exit_trade(position)
                elif unrealized_pl < -0.15:
                    logger.info(f"Exiting {symbol} to limit loss")
                    self.exit_trade(position)
                
                if datetime.now().time() > time(15, 30):
                    logger.info(f"Exiting {symbol} due to end of day")
                    self.exit_trade(position)
        except Exception as e:
            logger.error(f"Error managing positions: {str(e)}", exc_info=True)

    def exit_trade(self, position):
        try:
            self.alpaca_api.submit_order(
                symbol=position.symbol,
                qty=position.qty,
                side='sell' if position.side == 'long' else 'buy',
                type='market',
                time_in_force='day'
            )
            
            logger.info(f"Exited trade: {position.symbol}, quantity {position.qty}")
        except Exception as e:
            logger.error(f"Error exiting trade for {position.symbol}: {str(e)}", exc_info=True)

if __name__ == "__main__":
    try:
        logger.info("Initializing ZeroDTEStrategy")
        strategy = ZeroDTEStrategy(ALPACA_API_KEY, ALPACA_SECRET_KEY, GMAIL_USER, GMAIL_PASSWORD)
        
        logger.info("Starting strategy execution")
        strategy.run()
    except Exception as e:
        logger.error(f"An error occurred in main execution: {str(e)}", exc_info=True)