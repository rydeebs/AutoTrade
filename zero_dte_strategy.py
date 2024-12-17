import requests
import alpaca_trade_api as tradeapi
import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta
import time as time_module
import imaplib
import email
from email.header import decode_header
import logging
import pytz
import re
import traceback
import json

logger = logging.getLogger(__name__)

class ZeroDTEStrategy:
    def __init__(self, alpaca_key, alpaca_secret, gmail_user, gmail_password):
        # Regular API for trading
        self.alpaca_api = tradeapi.REST(
            alpaca_key, 
            alpaca_secret, 
            base_url='https://api.alpaca.markets',  # Live trading URL
            api_version='v2'
        )

        # Options API for market data
        self.options_api = tradeapi.REST(
            alpaca_key,
            alpaca_secret,
            base_url='https://data.alpaca.markets/v2',  # Live options data URL
            api_version='v2'
        )

        # Add trading API for options orders
        self.trading_api = tradeapi.REST(
            alpaca_key,
            alpaca_secret,
            base_url='https://api.alpaca.markets/v2',  # Live options trading URL
            api_version='v2'
        )

        self.symbols = ['SPY', 'QQQ', 'TSLA', 'NVDA', 'AMD', 'AAPL', 'SMCI', 'IWM', 'COIN']
        self.data = {}
        self.gmail_user = gmail_user
        self.gmail_password = gmail_password
        self.active_trades = {}
        logger.info(f"ZeroDTEStrategy initialized with symbols: {', '.join(self.symbols)}")
        self.trade_history = []  # Add this line
        self.completed_trades = {'won': 0, 'lost': 0}  # Add this line

    def exit_full_position(self, position):
        try:
            symbol = position.symbol
            remaining_qty = self.active_trades[symbol].get('current_quantity', position.qty)
            pl_percentage = float(position.unrealized_plpc)
            
            # Record trade result before closing
            is_win = pl_percentage > 0
            self.completed_trades['won' if is_win else 'lost'] += 1
            
            # Add to trade history
            self.trade_history.append({
                'symbol': symbol,
                'exit_time': datetime.now(),
                'pl_percentage': pl_percentage,
                'result': 'won' if is_win else 'lost'
            })

            # Submit sell order
            order = self.alpaca_api.submit_order(
                symbol=symbol,
                qty=remaining_qty,
                side='sell',
                type='market',
                time_in_force='day'
            )
            
            logger.info(f"Exit order submitted: {order.id}")
            
            # Remove from active trades
            if symbol in self.active_trades:
                trade_info = self.active_trades[symbol]
                time_in_trade = datetime.now() - trade_info['first_check_time']
                
                logger.info(f"=== TRADE SUMMARY ===")
                logger.info(f"Symbol: {symbol}")
                logger.info(f"Time in trade: {time_in_trade.total_seconds() / 60:.2f} minutes")
                logger.info(f"Final P/L: {pl_percentage:.2%}")
                logger.info(f"Initial quantity: {trade_info.get('initial_quantity')}")
                
                # Cleanup
                del self.active_trades[symbol]
            
            return True
            
        except Exception as e:
            logger.error(f"Error exiting full position: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    def verify_connections(self):
        """Verify all connections are working"""
        try:
            # Test the API connection
            account = self.alpaca_api.get_account()
            logger.info(f"Successfully connected to Alpaca. Account status: {account.status}")
            
            # Test Gmail credentials
            try:
                mail = imaplib.IMAP4_SSL('imap.gmail.com')
                mail.login(self.gmail_user, self.gmail_password)
                logger.info("Successfully connected to Gmail")
                mail.logout()
                return True
            except Exception as e:
                logger.error(f"Gmail authentication failed: {str(e)}")
                return False
                
        except Exception as e:
            logger.error(f"Strategy connection verification failed: {str(e)}")
            return False
    
    def run(self):
        """Main strategy loop"""
        logger.info("Strategy starting...")
        
        # Test initial connections
        try:
            # Test Alpaca connection
            logger.info("Testing Alpaca connection...")
            account = self.alpaca_api.get_account()
            logger.info(f"Successfully connected to Alpaca. Account Status: {account.status}")
            logger.info(f"Current buying power: ${account.buying_power}")
            
            # Test Gmail monitoring
            if not self.test_gmail_monitor():
                logger.error("Gmail monitoring test failed")
                return
                
            logger.info("All initial tests passed, starting main loop")
            
        except Exception as e:
            logger.error(f"Failed initial connection tests: {str(e)}")
            return

        while True:
            try:
                current_time = datetime.now(pytz.timezone('US/Eastern'))
                if self.is_trading_hours():
                    logger.info(f"Market is open at {current_time}. Checking for signals...")
                    
                    # Check Gmail for new alerts
                    logger.info("Checking Gmail for new alerts...")
                    self.check_gmail_alerts()
                    
                    # Manage existing positions
                    self.manage_positions()
                    
                else:
                    logger.info(f"Market is closed at {current_time}. Sleeping...")
                
                time_module.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Strategy error: {str(e)}")
                time_module.sleep(300)  # Wait 5 minutes before retrying

    def test_gmail_monitor(self):
        """Test Gmail connection and monitoring capabilities"""
        try:
            logger.info("Testing Gmail connection...")
            mail = imaplib.IMAP4_SSL('imap.gmail.com')
            status = mail.login(self.gmail_user, self.gmail_password)[0]
            logger.info(f"Gmail login successful: {status}")
            
            # Select inbox
            mail.select('inbox')
            logger.info("Successfully selected inbox")
            
            # Try to search for messages (simple test)
            _, messages = mail.search(None, 'ALL')
            logger.info("Successfully tested mail search")
            
            # Clean up
            mail.close()
            mail.logout()
            logger.info("Gmail test completed successfully")
            
            return True
            
        except Exception as e:
            logger.error(f"Gmail monitor test failed: {str(e)}")
            return False

    def is_trading_hours(self):
        """Check if current time is during trading hours"""
        est = pytz.timezone('US/Eastern')
        now = datetime.now(est)
        current_time = now.time()
        
        if now.weekday() >= 5:  # Weekend
            logger.info(f"Market closed: Weekend (day {now.weekday()})")
            return False
        
        market_open = time(9, 30)
        market_close = time(16, 0)
        
        is_trading = market_open <= current_time <= market_close
        
        if not is_trading:
            if current_time < market_open:
                logger.info(f"Market closed: Before market open ({current_time} < {market_open} EST)")
            elif current_time > market_close:
                logger.info(f"Market closed: After market close ({current_time} > {market_close} EST)")
        else:
            logger.info(f"Market open: {current_time} EST")
        
        return is_trading

    def process_alert(self, subject, body):
        """Process alerts and handle existing positions"""
        try:
            logger.info("==== PROCESSING ALERT ====")
            logger.info(f"Alert Subject: {subject}")
            logger.info(f"Alert Body: {body}")

            # Only handle WR alerts
            if "WR" in subject:
                try:
                    parts = subject.split(' - ')
                    symbol = parts[1].split()[1]  # Expects format: "XX% WR - SYMBOL BULL/BEAR"
                    direction = 'BULL' if 'BULL' in subject else 'BEAR'
                    
                    if symbol not in self.symbols:
                        logger.error(f"Symbol {symbol} not in tracked list")
                        return False

                    logger.info(f"WR Alert - Symbol: {symbol}, Direction: {direction}")

                    # Check if we have an existing position
                    if symbol in self.active_trades:
                        current_position = self.active_trades[symbol]
                        current_direction = current_position['direction']
                        
                        logger.info(f"Found existing position for {symbol}")
                        logger.info(f"Current position direction: {current_direction}")
                        logger.info(f"New alert direction: {direction}")
                        
                        # If directions match, keep the position
                        if current_direction == direction:
                            logger.info(f"New alert matches current position direction. Keeping position.")
                            return True
                        else:
                            # Directions don't match, exit the position
                            logger.info(f"New alert opposite to current position direction. Exiting position.")
                            positions = self.alpaca_api.list_positions()
                            for pos in positions:
                                if pos.symbol == symbol:
                                    return self.exit_full_position(pos)
                            return False

                    # No existing position, execute new trade
                    return self.execute_trade({'symbol': symbol, 'direction': direction, 'alert_type': 'WR'})

                except Exception as e:
                    logger.error(f"Error parsing WR alert: {str(e)}")
                    logger.error(traceback.format_exc())  # Added full traceback for better debugging
                    return False
            else:
                logger.info("Ignoring non-WR alert")
                return False

        except Exception as e:
            logger.error(f"Error processing alert: {str(e)}", exc_info=True)
            return False

    def execute_trade(self, trade_details):
        """Execute trade based on alert information"""
        try:
            logger.info("=== TRADE EXECUTION START ===")
            logger.info(f"Trade details received: {json.dumps(trade_details, indent=2)}")
            
            # Check PDT limit
            try:
                from main import pdt_tracker
                can_trade, use_next_day = pdt_tracker.can_trade()
                if not can_trade:
                    next_date = pdt_tracker.get_next_available_trade_date()
                    logger.warning(f"Cannot execute trade: Weekly trade limit (3) reached. Next available trade date: {next_date}")
                    return False
            except ImportError:
                logger.warning("PDT tracker not available - continuing without trade tracking")
                can_trade, use_next_day = True, False
            
            if not self.is_trading_hours():
                logger.error("Cannot execute trade outside trading hours")
                return False

            symbol = trade_details['symbol']
            direction = trade_details.get('direction')
            strike = trade_details.get('strike')

            logger.info(f"Processing trade for {symbol} direction: {direction} strike: {strike}")

            if symbol not in self.symbols:
                logger.error(f"Symbol {symbol} not in tracked list: {self.symbols}")
                return False

            # Get account info
            account = self.alpaca_api.get_account()
            buying_power = float(account.buying_power)
            logger.info(f"Account Status: {account.status}")
            logger.info(f"Account Buying Power: ${buying_power}")

            # Get current price for ATM strike selection
            try:
                latest_trade = self.alpaca_api.get_latest_trade(symbol)
                current_price = float(latest_trade.price)
                # Round to nearest $1
                atm_strike = round(current_price)
                
                # Select strike based on direction
                if direction == 'BULL':
                    strike = atm_strike - 1  # One strike below current price
                    logger.info(f"BULL trade: Using strike {strike} (below current price {current_price})")
                else:  # BEAR
                    strike = atm_strike + 1  # One strike above current price
                    logger.info(f"BEAR trade: Using strike {strike} (above current price {current_price})")
                
                logger.info(f"Current price: ${current_price}, ATM strike: ${atm_strike}, Selected strike: ${strike}")
            except Exception as e:
                logger.error(f"Failed to get strike price: {str(e)}")
                logger.error(traceback.format_exc())
                return False

            # Get expiration date based on PDT status
            today = datetime.now()
            if use_next_day:
                if today.weekday() == 4:  # Friday
                    expiration_date = (today + timedelta(days=3)).strftime('%Y-%m-%d')
                    logger.info(f"At PDT limit on Friday, using Monday expiration: {expiration_date}")
                else:
                    expiration_date = (today + timedelta(days=1)).strftime('%Y-%m-%d')
                    logger.info(f"At PDT limit, using next day expiration: {expiration_date}")
            else:
                expiration_date = today.strftime('%Y-%m-%d')
                logger.info(f"Using same day expiration: {expiration_date}")

            # Get options chain
            options_url = f"https://data.alpaca.markets/v1beta1/options/snapshots/{symbol}?expiration_date={expiration_date}"
            headers = {
                'APCA-API-KEY-ID': self.alpaca_api._key_id,
                'APCA-API-SECRET-KEY': self.alpaca_api._secret_key
            }

            logger.info(f"Fetching options chain...")
            
            try:
                all_strikes = []
                options_response = requests.get(options_url, headers=headers)
                
                if options_response.status_code != 200:
                    logger.error(f"Failed to get options chain: {options_response.text}")
                    return False

                options_data = options_response.json()
                snapshots = options_data.get('snapshots', {})
                
                for symbol, data in snapshots.items():
                    try:
                        # Determine if call or put
                        is_call = 'C' in symbol
                        
                        # Skip if option type doesn't match direction
                        if (direction == 'BULL' and not is_call) or (direction == 'BEAR' and is_call):
                            continue
                        
                        strike_price = float(symbol[-8:]) / 1000
                        
                        # Get quote data
                        quote = data.get('latestQuote', {})
                        ask_price = float(quote.get('askPrice', quote.get('ap', 0)))
                        bid_price = float(quote.get('bidPrice', quote.get('bp', 0)))
                        
                        # Validate quotes
                        if ask_price <= 0 or bid_price <= 0:
                            continue
                        
                        if ask_price < bid_price:
                            continue
                        
                        spread_percentage = (ask_price - bid_price) / ask_price
                        if spread_percentage > 0.20:  # Skip if spread > 20%
                            continue
                        
                        # Only add if it matches our target strike
                        if strike_price == strike:
                            all_strikes.append({
                                'symbol': symbol,
                                'strike': strike_price,
                                'ask': ask_price,
                                'bid': bid_price,
                                'spread': spread_percentage
                            })
                            logger.info(f"Found matching contract: {symbol} at strike {strike_price}")
                            
                    except Exception as e:
                        logger.error(f"Error processing option {symbol}: {str(e)}")
                        continue

                if not all_strikes:
                    logger.error(f"No valid contracts found for strike ${strike}")
                    return False

                # Select the contract
                contract = all_strikes[0]
                logger.info(f"Selected contract: {contract}")

                # Calculate number of contracts to buy
                contract_price = (contract['ask'] + contract['bid']) / 2
                min_cost = contract_price * 100

                if buying_power < min_cost:
                    logger.error(f"Insufficient buying power (${buying_power}) for minimum contract cost (${min_cost})")
                    return False

                # Use 90% of buying power, max 10 contracts
                max_contracts = min(int((buying_power * 0.90) / min_cost), 10)
                num_contracts = max(1, max_contracts)

                # Submit the order
                order = self.alpaca_api.submit_order(
                    symbol=contract['symbol'],
                    qty=num_contracts,
                    side='buy',
                    type='limit',
                    time_in_force='day',
                    limit_price=contract['ask']
                )

                logger.info(f"Order submitted: {order.id}")

                # Record the trade
                try:
                    if 'pdt_tracker' in locals():
                        trades_remaining = pdt_tracker.add_trade({
                            'symbol': symbol,
                            'type': 'entry',
                            'direction': direction,
                            'quantity': num_contracts,
                            'price': contract_price,
                            'strike': strike
                        })
                        logger.info(f"Trade recorded in PDT tracker. {trades_remaining} trades remaining this week.")
                except Exception as e:
                    logger.warning(f"Failed to record trade in PDT tracker: {str(e)}")

                # Track the trade
                self.active_trades[symbol] = {
                    'order_id': order.id,
                    'entry_time': datetime.now(),
                    'direction': direction,
                    'strike': strike,
                    'option_symbol': contract['symbol'],
                    'num_contracts': num_contracts,
                    'contract_cost': min_cost,
                    'entry_price': contract_price,
                    'initial_quantity': num_contracts,
                    'current_quantity': num_contracts,
                    'profit_stages_taken': [],
                    'last_profit_level': 0,
                    'alert_type': trade_details['alert_type']
                }

                logger.info("Trade execution completed successfully")
                return True

            except Exception as e:
                logger.error(f"❌ Trade execution error: {str(e)}")
                logger.error(traceback.format_exc())
                return False

        except Exception as e:
            logger.error(f"❌ Trade execution error: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    def get_email_body(self, email_message):
        """Extract email body with better handling of multipart messages"""
        try:
            if email_message.is_multipart():
                # Handle multipart messages
                for part in email_message.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            # Try UTF-8 first
                            return part.get_payload(decode=True).decode('utf-8')
                        except UnicodeDecodeError:
                            # Fall back to other encodings
                            try:
                                return part.get_payload(decode=True).decode('iso-8859-1')
                            except:
                                return part.get_payload(decode=True).decode('ascii', errors='ignore')
            else:
                # Handle single part messages
                try:
                    return email_message.get_payload(decode=True).decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        return email_message.get_payload(decode=True).decode('iso-8859-1')
                    except:
                        return email_message.get_payload(decode=True).decode('ascii', errors='ignore')
        except Exception as e:
            logger.error(f"Error extracting email body: {str(e)}")
            return ""

    def check_gmail_alerts(self):
        """Check Gmail for trading alerts"""
        mail = None
        try:
            logger.info("🔍 Starting Gmail check for alerts...")
            mail = imaplib.IMAP4_SSL('imap.gmail.com')
            status, _ = mail.login(self.gmail_user, self.gmail_password)
            logger.info(f"📧 Gmail login status: {status}")
            
            if status != 'OK':
                logger.error("❌ Failed to login to Gmail")
                return
                
            mail.select('inbox')
            
            # Only search for WR alerts
            try:
                # Search for unread emails with "WR" in subject
                _, search_data = mail.search(None, 'UNSEEN SUBJECT "WR"')
                email_ids = search_data[0].split()
                logger.info(f"📨 Found {len(email_ids)} new WR alerts")
                
                for num in email_ids:
                    try:
                        _, data = mail.fetch(num, '(RFC822)')
                        email_body = data[0][1]
                        email_message = email.message_from_bytes(email_body)
                        
                        # Get and decode subject
                        subject = decode_header(email_message["subject"])[0][0]
                        if isinstance(subject, bytes):
                            subject = subject.decode()
                        
                        body = self.get_email_body(email_message)
                        
                        logger.info(f"Processing WR alert - Subject: {subject}")
                        logger.info(f"Alert body preview: {body[:200]}...")
                        
                        # Process the alert
                        result = self.process_alert(subject, body)
                        if result:
                            mail.store(num, '+FLAGS', '\\Seen')
                            logger.info("✅ WR Alert processed and marked as read")
                        else:
                            logger.warning("⚠️ WR Alert processing failed, leaving unread")
                        
                    except Exception as e:
                        logger.error(f"❌ Error processing individual WR alert: {str(e)}")
                        logger.error(traceback.format_exc())
                        continue
                        
            except Exception as e:
                logger.error(f"❌ Error in WR alerts section: {str(e)}")
                logger.error(traceback.format_exc())
            
        except Exception as e:
            logger.error(f"❌ Error checking Gmail alerts: {str(e)}", exc_info=True)
        finally:
            if mail:
                try:
                    if mail.state != 'NONAUTH':
                        mail.close()
                    mail.logout()
                    logger.info("📭 Gmail connection closed")
                except Exception as e:
                    logger.error(f"❌ Error closing Gmail connection: {str(e)}")

    def process_wr_alert(self, subject, body):
        """Process WR alerts with improved parsing"""
        try:
            # Log full alert details for debugging
            logger.info(f"Processing WR alert - Subject: {subject}")
            logger.info(f"Alert body: {body}")
            
            # Check for BULL/BEAR in both subject and body
            alert_text = f"{subject} {body}".upper()
            
            # Determine direction
            if 'BULL' in alert_text:
                direction = 'BULL'
            elif 'BEAR' in alert_text:
                direction = 'BEAR'
            else:
                logger.error(f"❌ No direction (BULL/BEAR) found in WR alert text: {alert_text}")
                return False
                
            logger.info(f"Found direction: {direction}")
                
            # Look for any symbol from our tracked list
            found_symbol = None
            for symbol in self.symbols:
                if symbol in alert_text:
                    found_symbol = symbol
                    break
                    
            if not found_symbol:
                logger.error(f"❌ No valid symbol found in WR alert text: {alert_text}")
                return False
                    
            logger.info(f"Found symbol: {found_symbol}")
                
            # Try to extract WR percentage
            wr_match = re.search(r'(\d+(?:\.\d+)?)\s*%', alert_text)
            wr_percent = float(wr_match.group(1)) if wr_match else None
                
            if wr_percent is not None:
                logger.info(f"Found WR percentage: {wr_percent}%")
                    
                # Apply WR filters
                if direction == 'BULL' and wr_percent < 50:
                    logger.info(f"Skipping BULL trade - WR {wr_percent}% below 50% threshold")
                    return False
                elif direction == 'BEAR' and wr_percent < 70:
                    logger.info(f"Skipping BEAR trade - WR {wr_percent}% below 70% threshold")
                    return False
            
            # Look for strike price in alert
            strike_match = re.search(r'STRIKE[:\s]+(\d+(?:\.\d+)?)', alert_text)
            strike = float(strike_match.group(1)) if strike_match else None
                
            if strike:
                logger.info(f"Found strike price: {strike}")
                    
            logger.info(f"🎯 Parsed WR alert - Symbol: {found_symbol}, Direction: {direction}" + 
                       (f", WR: {wr_percent}%" if wr_percent else "") +
                       (f", Strike: {strike}" if strike else ""))
                
            trade_details = {
                'symbol': found_symbol,
                'direction': direction,
                'alert_type': 'WR',
                'wr_percent': wr_percent,
                'strike': strike
            }
                
            return self.execute_trade(trade_details)
                    
        except Exception as e:
            logger.error(f"❌ Error processing WR alert: {str(e)}")
            traceback.print_exc()  # Print full traceback for debugging
            return False

    def manage_positions(self):
        """Manage existing positions with multi-stage profit taking"""
        try:
            if not self.is_trading_hours():
                logger.info("Skipping position management outside trading hours")
                return
                
            positions = self.alpaca_api.list_positions()
            for position in positions:
                if position.symbol in self.active_trades:
                    self.check_exit_conditions(position)
        except Exception as e:
            logger.error(f"Error managing positions: {str(e)}", exc_info=True)

    def check_exit_conditions(self, position):
        """
        Exit conditions:
        1. Take profit at +10% any time
        2. Take any profit after 45 minutes
        3. Take loss at -5% only after 20 minutes
        """
        try:
            symbol = position.symbol
            trade_info = self.active_trades[symbol]
            current_pl = float(position.unrealized_plpc)
            
            logger.info(f"=== CHECKING EXIT CONDITIONS ===")
            logger.info(f"Symbol: {symbol}")
            logger.info(f"Current P/L: {current_pl:.2%}")

            # Initialize first_check_time if not present
            if 'first_check_time' not in trade_info:
                trade_info['first_check_time'] = datetime.now()
                logger.info("Initialized position tracking time")
                return False

            # Calculate time in position
            time_in_position = datetime.now() - trade_info['first_check_time']
            minutes_in_position = time_in_position.total_seconds() / 60

            logger.info(f"Time in position: {minutes_in_position:.2f} minutes")

            # Exit condition 1: Take profit at +10% any time
            if current_pl >= 0.10:
                logger.info(f"Taking profit at {current_pl:.2%} (≥10% target reached)")
                return self.exit_full_position(position)

            # Exit condition 2: Take any profit after 45 minutes
            if minutes_in_position >= 45 and current_pl > 0:
                logger.info(f"Taking profit at {current_pl:.2%} (Position held for {minutes_in_position:.2f} minutes)")
                return self.exit_full_position(position)

            # Exit condition 3: Take loss at -5% only after 20 minutes
            if minutes_in_position >= 20 and current_pl <= -0.05:
                logger.info(f"Taking loss at {current_pl:.2%} (Position held for {minutes_in_position:.2f} minutes)")
                return self.exit_full_position(position)

            # Log if no exit conditions met
            logger.info("No exit conditions met, holding position")
            return False

        except Exception as e:
            logger.error(f"Error checking exit conditions: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    def exit_partial_position(self, position, qty_to_sell):
        """Exit a portion of a position"""
        try:
            symbol = position.symbol
            logger.info(f"Executing partial exit for {symbol}: {qty_to_sell} contracts")
            
            order = self.alpaca_api.submit_order(
                symbol=symbol,
                qty=qty_to_sell,
                side='sell',
                type='market',
                time_in_force='day'
            )
            
            logger.info(f"Partial exit order submitted: {order.id}")
            return True
            
        except Exception as e:
            logger.error(f"Error executing partial exit: {str(e)}")
            return False