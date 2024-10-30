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
import csv
import pytz
from config import ALPACA_API_KEY, ALPACA_SECRET_KEY, GMAIL_USER, GMAIL_PASSWORD

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ZeroDTEStrategy:
    def __init__(self, alpaca_key, alpaca_secret, gmail_user, gmail_password):
        # Use live trading endpoint
        self.alpaca_api = tradeapi.REST(alpaca_key, alpaca_secret, base_url='https://api.alpaca.markets', api_version='v2')
        self.symbols = ['SPY', 'QQQ']
        self.data = {}
        self.gmail_user = gmail_user
        self.gmail_password = gmail_password
        self.on_fire_alerts = set()
        self.rigged_alerts = []
        self.trade_log_file = 'trade_log.csv'
        self.max_position_value = 10000  # Maximum position size in dollars
        self.initialize_trade_log()
        
        # Verify account is setup for live trading
        account = self.alpaca_api.get_account()
        if account.status != 'ACTIVE':
            raise Exception(f"Account is not active for trading. Status: {account.status}")
        if not account.trading_enabled:
            raise Exception("Trading is not enabled on this account")
        logger.info("Live trading account verified and active")

    def initialize_trade_log(self):
        with open(self.trade_log_file, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Timestamp', 'Stock', 'Action', 'Price', 'Quantity', 'Price Sold At', 'Dollar Difference', 'Percent Change'])

    def log_trade(self, stock, action, price, quantity, price_sold_at=None, dollar_diff=None, percent_change=None):
        with open(self.trade_log_file, 'a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                stock,
                action,
                price,
                quantity,
                price_sold_at if price_sold_at is not None else '',
                f'${dollar_diff:.2f}' if dollar_diff is not None else '',
                f'{percent_change:.2f}%' if percent_change is not None else ''
            ])

    def is_trading_hours(self):
        current_time = datetime.now(pytz.timezone('US/Eastern')).time()
        return time(9, 30) <= current_time <= time(16, 0)

    def test_api_connection(self):
        try:
            account = self.alpaca_api.get_account()
            logger.info(f"Successfully connected to Alpaca API. Account status: {account.status}")
            buying_power = float(account.buying_power)
            logger.info(f"Current buying power: ${buying_power}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Alpaca API: {str(e)}")
            return False

    def run(self):
        if not self.test_api_connection():
            logger.error("Failed to establish API connection. Exiting.")
            return

        logger.info("Live trading strategy starting...")
        while True:
            try:
                current_time = datetime.now(pytz.timezone('US/Eastern'))
                logger.info(f"Strategy check at {current_time}")
                
                if self.is_trading_hours():
                    logger.info("Market is open, checking conditions...")
                    self.check_gmail_alerts()
                    for symbol in self.symbols:
                        try:
                            if self.update_market_data_for_symbol(symbol):
                                self.analyze_market_conditions_for_symbol(symbol)
                                self.check_entry_conditions_for_symbol(symbol)
                        except Exception as e:
                            logger.error(f"Error processing symbol {symbol}: {str(e)}")
                    self.manage_positions()
                else:
                    logger.info("Market is closed")
                
                time_module.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Strategy error: {str(e)}")
                time_module.sleep(300)  # Wait 5 minutes before retrying

    def check_gmail_alerts(self):
        mail = None
        try:
            mail = imaplib.IMAP4_SSL('imap.gmail.com')
            if not mail.login(self.gmail_user, self.gmail_password)[0] == 'OK':
                logger.error("Failed to login to Gmail")
                return
                
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
            if mail:
                try:
                    if mail.state != 'NONAUTH':
                        mail.close()
                    mail.logout()
                except Exception as e:
                    logger.error(f"Error closing Gmail connection: {str(e)}")

    def process_on_fire_alert(self, subject):
        try:
            parts = subject.split()
            if len(parts) < 3:
                logger.error(f"Invalid ON FIRE alert format: {subject}")
                return

            symbol = parts[2]
            if symbol not in self.data:
                self.data[symbol] = {}
            if symbol not in self.symbols:
                self.symbols.append(symbol)
                logger.info(f"Added new symbol to track: {symbol}")

            side = parts[3] if len(parts) > 3 else "Unknown"
            gain = float(parts[5].strip('%')) if len(parts) > 5 else 0
            alert_time = int(parts[7]) if len(parts) > 7 else 0

            self.on_fire_alerts.add((symbol, side, gain, alert_time))
            logger.info(f"ON FIRE Alert: {symbol} {side} {gain}% in {alert_time} minutes")

        except Exception as e:
            logger.error(f"Error processing ON FIRE alert: {str(e)}", exc_info=True)

    def process_tradeability_alert(self, subject):
        try:
            parts = subject.split()
            symbol = parts[1]
            tradeability = ' '.join(parts[3:])
            
            if symbol not in self.data:
                self.data[symbol] = {}
            
            self.data[symbol]['tradeability'] = tradeability
            logger.info(f"Tradeability Alert: {symbol} is now {tradeability}")
        except Exception as e:
            logger.error(f"Error processing Tradeability alert: {str(e)}", exc_info=True)

    def update_market_data_for_symbol(self, symbol):
        try:
            bars = self.alpaca_api.get_bars(symbol, '1Min', limit=100).df
            if bars.empty:
                logger.warning(f"No data received for {symbol}")
                return False
                
            logger.info(f"Retrieved {len(bars)} bars for {symbol}")
            self.data[symbol] = {
                'bars': bars,
                'current_price': bars.close.iloc[-1],
                'open_price': bars.open.iloc[0],
                'volume': bars.volume.sum(),
                'high': bars.high.max(),
                'low': bars.low.min()
            }
            logger.info(f"Updated market data for {symbol}: Price=${self.data[symbol]['current_price']:.2f}, Volume={self.data[symbol]['volume']}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating market data for {symbol}: {str(e)}", exc_info=True)
            return False

    def analyze_market_conditions_for_symbol(self, symbol):
        try:
            if not self.data.get(symbol):
                logger.error(f"No market data available for {symbol}")
                return False
                
            self.data[symbol]['tradeability'] = self.calculate_tradeability(symbol)
            self.data[symbol]['ps'] = self.calculate_position_score(symbol)
            self.data[symbol]['blue_line_relation'] = self.determine_blue_line_relationship(symbol)
            
            logger.info(f"Analyzed {symbol}: Tradeability={self.data[symbol]['tradeability']}, PS={self.data[symbol]['ps']:.2f}, Blue Line={self.data[symbol]['blue_line_relation']:.2f}")
            return True
            
        except Exception as e:
            logger.error(f"Error analyzing market conditions for {symbol}: {str(e)}", exc_info=True)
            return False

    def calculate_tradeability(self, symbol):
        try:
            volume = self.data[symbol]['volume']
            avg_volume = self.data[symbol]['bars'].volume.mean()
            volume_ratio = volume / avg_volume if avg_volume > 0 else 0
            
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
                
        except Exception as e:
            logger.error(f"Error calculating tradeability for {symbol}: {str(e)}")
            return "NIGHTMARE"

    def calculate_position_score(self, symbol):
        try:
            bars = self.data[symbol]['bars']
            current_price = self.data[symbol]['current_price']
            open_price = self.data[symbol]['open_price']
            high = self.data[symbol]['high']
            low = self.data[symbol]['low']
            
            ps = ((current_price - open_price) + 
                  (current_price - low) + 
                  (high - current_price))
            return ps
            
        except Exception as e:
            logger.error(f"Error calculating position score for {symbol}: {str(e)}")
            return 0

    def determine_blue_line_relationship(self, symbol):
        try:
            return self.data[symbol]['current_price'] - self.data[symbol]['open_price']
        except Exception as e:
            logger.error(f"Error determining blue line relationship for {symbol}: {str(e)}")
            return 0

    def check_entry_conditions_for_symbol(self, symbol):
        try:
            tradeability = self.data[symbol]['tradeability']
            if tradeability not in ["EASY MODE", "FULL SEND"]:
                return False
                
            ps = self.data[symbol]['ps']
            blue_line_relation = self.data[symbol]['blue_line_relation']
            
            # Check for existing position
            try:
                position = self.alpaca_api.get_position(symbol)
                logger.info(f"Already have position in {symbol}, skipping entry")
                return False
            except:
                pass  # No position exists
            
            if ps > 0 and blue_line_relation > 0:
                logger.info(f"Entry conditions met for {symbol} LONG")
                return self.enter_trade(symbol, 'buy')
            elif ps < 0 and blue_line_relation < 0:
                logger.info(f"Entry conditions met for {symbol} SHORT")
                return self.enter_trade(symbol, 'sell')
                
            return False
            
        except Exception as e:
            logger.error(f"Error checking entry conditions for {symbol}: {str(e)}", exc_info=True)
            return False

    def enter_trade(self, symbol, side):
        try:
            logger.info(f"Attempting to enter live trade: {symbol} {side}")
            
            # Check account status
            account = self.alpaca_api.get_account()
            if float(account.buying_power) < 1000:  # Minimum buying power requirement
                logger.error(f"Insufficient buying power: ${account.buying_power}")
                return False
                
            # Get current price and calculate position size
            current_price = self.data[symbol]['current_price']
            max_shares = min(
                int(self.max_position_value / current_price),
                int(float(account.buying_power) * 0.95 / current_price)  # Use 95% of buying power max
            )
            
            if max_shares < 1:
                logger.error(f"Insufficient funds to purchase minimum position")
                return False
                
            # Submit order with additional safety parameters
            order = self.alpaca_api.submit_order(
                symbol=symbol,
                qty=max_shares,
                side=side,
                type='limit',  # Use limit orders for more control
                time_in_force='day',
                limit_price=current_price * (1.01 if side == 'buy' else 0.99),  # 1% price protection
                order_class='simple'
            )
            
            logger.info(f"Live order submitted: {order}")
            self.log_trade(symbol, f'Enter {side.capitalize()}', current_price, max_shares)
            return True
            
        except Exception as e:
            logger.error(f"Error entering live trade for {symbol} {side}: {str(e)}", exc_info=True)
            return False

    def manage_positions(self):
        try:
            positions = self.alpaca_api.list_positions()
            
            for position in positions:
                symbol = position.symbol
                unrealized_pl = float(position.unrealized_plpc)
                current_value = float(position.market_value)
                
                # Exit conditions for live trading
                should_exit = (
                    unrealized_pl >= 0.02 or  # Take profit at 2%
                    unrealized_pl <= -0.01 or  # Stop loss at 1%
                    current_value > self.max_position_value * 1.1 or  # Position too large
                    datetime.now(pytz.timezone('US/Eastern')).time() > time(15, 45)  # Close near end of day
                )
                
                if should_exit:
                    self.exit_trade(position)
                    
        except Exception as e:
            logger.error(f"Error managing live positions: {str(e)}", exc_info=True)

    def exit_trade(self, position):
        try:
            symbol = position.symbol
            quantity = abs(float(position.qty))
            current_price = float(position.current_price)
            entry_price = float(position.avg_entry_price)
            
            # Additional safety checks for live trading
            if quantity < 1:
                logger.error(f"Invalid position quantity for {symbol}: {quantity}")
                return False
                
            # Submit exit order with price protection
            order = self.alpaca_api.submit_order(
                symbol=symbol,
                qty=quantity,
                side='sell' if position.side == 'long' else 'buy',
                type='limit',
                time_in_force='day',
                limit_price=current_price * (0.99 if position.side == 'long' else 1.01)
            )
            
            # Calculate P&L
            dollar_diff = (current_price - entry_price) * quantity
            percent_change = ((current_price - entry_price) / entry_price) * 100
            
            logger.info(f"Exited live trade: {symbol}, quantity {quantity}, P&L: ${dollar_diff:.2f} ({percent_change:.2f}%)")
            self.log_trade(
                symbol, 
                'Exit', 
                entry_price, 
                quantity, 
                current_price,
                dollar_diff,
                percent_change
            )
            return True
            
        except Exception as e:
            logger.error(f"Error exiting live trade for {position.symbol}: {str(e)}", exc_info=True)
            return False

    def cancel_all_orders(self):
        """Cancel all open orders."""
        try:
            self.alpaca_api.cancel_all_orders()
            logger.info("Cancelled all open orders")
        except Exception as e:
            logger.error(f"Error cancelling orders: {str(e)}")

    def liquidate_all_positions(self):
        """Liquidate all positions."""
        try:
            self.alpaca_api.close_all_positions()
            logger.info("Liquidated all positions")
        except Exception as e:
            logger.error(f"Error liquidating positions: {str(e)}")

    def cleanup(self):
        """Cleanup method to be called on shutdown."""
        try:
            logger.info("Initiating cleanup procedure...")
            self.cancel_all_orders()
            self.liquidate_all_positions()
            logger.info("Cleanup completed successfully")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")

if __name__ == "__main__":
    print("\n" + "="*50)
    print("WARNING: This script is configured for LIVE trading.")
    print("Real money will be at risk.")
    print("="*50 + "\n")
    
    confirmation = input("Type 'LIVE TRADING' to confirm you want to proceed with live trading: ")
    if confirmation.upper() != 'LIVE TRADING':
        print("Live trading cancelled. Exiting script.")
        exit()

    try:
        logger.info("Initializing ZeroDTEStrategy for LIVE trading")
        strategy = ZeroDTEStrategy(ALPACA_API_KEY, ALPACA_SECRET_KEY, GMAIL_USER, GMAIL_PASSWORD)
        
        # Register cleanup handler
        import atexit
        atexit.register(strategy.cleanup)
        
        # Start trading
        strategy.run()
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, initiating graceful shutdown...")
        strategy.cleanup()
        print("\nTrading bot shutdown complete.")
        
    except Exception as e:
        logger.error(f"Fatal error in main execution: {str(e)}", exc_info=True)
        try:
            strategy.cleanup()
        except:
            pass
        print("\nTrading bot shutdown due to error.")