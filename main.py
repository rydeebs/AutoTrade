from flask import Flask, render_template, jsonify, send_file, make_response, g, request, send_from_directory
import logging
import os
import sys
from datetime import datetime, time, timedelta
import time as time_module
import pytz
from zero_dte_strategy import ZeroDTEStrategy
import pandas as pd
from threading import Thread
import alpaca_trade_api as tradeapi
from werkzeug.exceptions import HTTPException
import traceback
import imaplib
import json
import threading
import secrets
from google.cloud import logging as cloud_logging

# Configure basic logging first
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Initialize Cloud Logging
client = cloud_logging.Client()
client.setup_logging()

# Verify template directory and files
template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
template_file = os.path.join(template_dir, 'index.html')
if not os.path.exists(template_dir):
    logger.error(f"Template directory not found: {template_dir}")
if not os.path.exists(template_file):
    logger.error(f"Template file not found: {template_file}")

# Initialize global variables
strategy = None
strategy_thread = None
strategy_running = False

# Helper function for verifying connections
def verify_alpaca_connection():
    """Verify Alpaca API connection"""
    try:
        api = tradeapi.REST(
            ALPACA_API_KEY,
            ALPACA_SECRET_KEY,
            base_url='https://api.alpaca.markets'
        )
        account = api.get_account()
        logger.info("Successfully connected to Alpaca API")
        return True
    except Exception as e:
        logger.error(f"Alpaca connection failed: {str(e)}")
        return False

def verify_gmail_connection():
    """Verify Gmail connection"""
    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(GMAIL_USER, GMAIL_PASSWORD)
        mail.logout()
        logger.info("Successfully connected to Gmail")
        return True
    except Exception as e:
        logger.error(f"Gmail connection failed: {str(e)}")
        return False

# Only initialize Google Cloud Logging if in production environment
if os.getenv('GAE_ENV', '').startswith('standard'):
    try:
        import google.cloud.logging
        from google.cloud import secretmanager
        client = google.cloud.logging.Client()
        
        # Add cloud logging handler while keeping stdout logging
        client.setup_logging(log_level=logging.INFO)
        logger.info("Running in Google Cloud environment")

        # Access secrets in cloud
        def access_secret_version(project_id, secret_id, version_id="latest"):
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
            response = client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8")

        project_id = "rtrade-bot-2024"
        ALPACA_API_KEY = access_secret_version(project_id, "alpaca-api-key")
        ALPACA_SECRET_KEY = access_secret_version(project_id, "alpaca-secret-key")
        GMAIL_USER = access_secret_version(project_id, "gmail-user")
        GMAIL_PASSWORD = access_secret_version(project_id, "gmail-password")
    except Exception as e:
        logger.error(f"Error setting up cloud environment: {str(e)}")
        raise
else:
    logger.info("Running in local environment")
    # Use environment variables locally
    ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
    ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')
    GMAIL_USER = os.getenv('GMAIL_USER')
    GMAIL_PASSWORD = os.getenv('GMAIL_PASSWORD')

# Initialize Flask app
app = Flask(__name__, 
    static_folder='static',
    template_folder='templates'
)

def register_debug_routes(app):
    """Register debug routes and enhance logging"""
    
    @app.route('/debug/routes')
    def list_routes():
        routes = []
        for rule in app.url_map.iter_rules():
            routes.append({
                'endpoint': rule.endpoint,
                'methods': list(rule.methods),
                'path': str(rule)
            })
        return jsonify(routes)

    @app.errorhandler(404)
    def handle_404(e):
        error_info = {
            'error': '404 Not Found',
            'requested_url': request.url,
            'method': request.method,
            'headers': dict(request.headers),
            'timestamp': datetime.now().isoformat(),
            'available_routes': [str(rule) for rule in app.url_map.iter_rules()]
        }
        logger.error(f"404 Error: {json.dumps(error_info, indent=2)}")
        return jsonify(error_info), 404

    @app.route('/debug/templates')
    def check_templates():
        template_info = {
            'template_folder': app.template_folder,
            'exists': os.path.exists(app.template_folder),
            'contents': os.listdir(app.template_folder) if os.path.exists(app.template_folder) else [],
            'index_exists': os.path.exists(os.path.join(app.template_folder, 'index.html')) if os.path.exists(app.template_folder) else False
        }
        return jsonify(template_info)

    @app.route('/debug/static')
    def check_static():
        static_info = {
            'static_folder': app.static_folder,
            'exists': os.path.exists(app.static_folder),
            'contents': os.listdir(app.static_folder) if os.path.exists(app.static_folder) else [],
        }
        return jsonify(static_info)

register_debug_routes(app)

def is_trading_hours():
    """Check if current time is during trading hours"""
    est = pytz.timezone('US/Eastern')
    now = datetime.now(est)
    current_time = now.time()
    
    if now.weekday() >= 5:  # Weekend
        return False
    
    market_open = time(9, 30)
    market_close = time(16, 0)
    
    return market_open <= current_time <= market_close

@app.route('/')
def index():
    try:
        # Generate a secure nonce
        nonce = secrets.token_urlsafe(32)
        
        # Create response with template
        response = make_response(render_template('index.html', nonce=nonce))
        
        # Add Content Security Policy header with both unsafe-eval and nonce
        csp_directives = [
            "default-src 'self'",
            f"script-src 'self' 'unsafe-eval' 'nonce-{nonce}' https://unpkg.com",
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data:",
            "connect-src 'self'",
            "base-uri 'self'",
            "form-action 'self'"
        ]
        
        response.headers['Content-Security-Policy'] = "; ".join(csp_directives)
        
        # Add additional security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        return response
        
    except Exception as e:
        logger.error(f"Error in index route: {str(e)}")
        raise

def get_trade_statistics():
    """Helper function to calculate trade statistics"""
    try:
        logger.info("Starting trade statistics calculation...")
        
        if not strategy:
            logger.info("No strategy instance found")
            return {"won": 0, "lost": 0}

        # Primary method: Use completed trades counter if available
        if hasattr(strategy, 'completed_trades'):
            logger.info(f"Using completed trades counter: {strategy.completed_trades}")
            return strategy.completed_trades

        # Fallback method: Calculate from active trades
        trades_won = 0
        trades_lost = 0
        
        if not hasattr(strategy, 'active_trades'):
            logger.info("No active trades attribute found")
            return {"won": 0, "lost": 0}

        logger.info(f"Calculating statistics for {len(strategy.active_trades)} active trades")
        
        for symbol, trade_info in strategy.active_trades.items():
            try:
                # Get current market data
                current_quote = strategy.alpaca_api.get_latest_trade(symbol)
                current_price = float(current_quote.price)
                entry_price = float(trade_info.get('entry_price', 0))
                direction = trade_info.get('direction', '')
                
                # Log trade details for debugging
                logger.debug(f"Trade details for {symbol}:")
                logger.debug(f"Entry price: ${entry_price}")
                logger.debug(f"Current price: ${current_price}")
                logger.debug(f"Direction: {direction}")
                
                # Skip invalid trades
                if entry_price <= 0 or not direction:
                    logger.warning(f"Invalid trade data for {symbol}: price={entry_price}, direction={direction}")
                    continue

                # Calculate profit/loss
                price_change = current_price - entry_price
                price_change_pct = (price_change / entry_price) * 100

                # Determine if trade is profitable based on direction
                is_profitable = False
                if direction == 'BULL':
                    is_profitable = price_change > 0
                elif direction == 'BEAR':
                    is_profitable = price_change < 0
                else:
                    logger.warning(f"Unknown trade direction for {symbol}: {direction}")
                    continue
                
                # Update counters
                if is_profitable:
                    trades_won += 1
                    logger.debug(f"{symbol} counted as winning trade: {price_change_pct:.2f}%")
                else:
                    trades_lost += 1
                    logger.debug(f"{symbol} counted as losing trade: {price_change_pct:.2f}%")

            except Exception as e:
                logger.error(f"Error processing trade for {symbol}: {str(e)}")
                logger.error(traceback.format_exc())
                continue

        # Check trade history if available
        if hasattr(strategy, 'trade_history'):
            logger.info("Processing trade history...")
            for trade in strategy.trade_history:
                try:
                    if trade.get('result') == 'won':
                        trades_won += 1
                    elif trade.get('result') == 'lost':
                        trades_lost += 1
                except Exception as e:
                    logger.error(f"Error processing historical trade: {str(e)}")
                    continue

        results = {"won": trades_won, "lost": trades_lost}
        logger.info(f"Final trade statistics: {results}")
        return results

    except Exception as e:
        logger.error(f"Error calculating trade statistics: {str(e)}")
        logger.error(traceback.format_exc())
        return {"won": 0, "lost": 0}

@app.route('/api/status')
def get_status():
    try:
        logger.info("Fetching status...")
        current_time = datetime.now(pytz.timezone('US/Eastern'))
        is_trading = is_trading_hours()
        
        status_data = {
            "is_trading_hours": is_trading,
            "strategy_running": bool(strategy and strategy_running),
            "current_time": current_time.strftime("%Y-%m-%d %H:%M:%S %Z")
        }
        
        logger.info(f"Status data: {status_data}")
        return jsonify(status_data)
    except Exception as e:
        logger.error(f"Error fetching status: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route('/api/account')
def get_account():
    try:
        logger.info("Fetching account information...")
        
        if not strategy or not strategy.alpaca_api:
            logger.warning("Strategy or Alpaca API not initialized")
            return jsonify({
                'equity': 0,
                'buying_power': 0,
                'cash': 0
            })

        account = strategy.alpaca_api.get_account()
        account_data = {
            'equity': float(account.equity),
            'buying_power': float(account.buying_power),
            'cash': float(account.cash)
        }
        
        logger.info(f"Account data: {account_data}")
        return jsonify(account_data)
    except Exception as e:
        logger.error(f"Error fetching account: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route('/api/performance_metrics')
def get_performance_metrics():
    try:
        logger.info("Fetching performance metrics...")
        
        metrics = {
            "wow": {"percentage": 0, "dollars": 0},
            "mom": {"percentage": 0, "dollars": 0},
            "trades": {"won": 0, "lost": 0}
        }

        if not strategy or not strategy.alpaca_api:
            logger.warning("Strategy or Alpaca API not initialized")
            return jsonify(metrics)

        try:
            # Get current account value
            account = strategy.alpaca_api.get_account()
            current_equity = float(account.equity)
            logger.info(f"Current equity: ${current_equity}")

            # Calculate week over week
            try:
                week_history = strategy.alpaca_api.get_portfolio_history(
                    period="1W",
                    timeframe="1D",
                    extended_hours=False
                )
                
                logger.info(f"Week history data: {week_history.equity if week_history else 'No data'}")
                
                if week_history and week_history.equity and len(week_history.equity) > 0:
                    week_start_equity = float(week_history.equity[0])
                    logger.info(f"Week start equity: ${week_start_equity}")
                    
                    wow_change = current_equity - week_start_equity
                    wow_percentage = (wow_change / week_start_equity * 100) if week_start_equity > 0 else 0
                    
                    metrics["wow"] = {
                        "percentage": round(wow_percentage, 2),
                        "dollars": round(wow_change, 2)
                    }
                    logger.info(f"WoW metrics calculated: {metrics['wow']}")

            except Exception as e:
                logger.error(f"Error calculating WoW: {str(e)}")
                logger.error(traceback.format_exc())

            # Calculate month over month
            try:
                month_history = strategy.alpaca_api.get_portfolio_history(
                    period="1M",
                    timeframe="1D",
                    extended_hours=False
                )
                
                logger.info(f"Month history data: {month_history.equity if month_history else 'No data'}")
                
                if month_history and month_history.equity and len(month_history.equity) > 0:
                    month_start_equity = float(month_history.equity[0])
                    logger.info(f"Month start equity: ${month_start_equity}")
                    
                    mom_change = current_equity - month_start_equity
                    mom_percentage = (mom_change / month_start_equity * 100) if month_start_equity > 0 else 0
                    
                    metrics["mom"] = {
                        "percentage": round(mom_percentage, 2),
                        "dollars": round(mom_change, 2)
                    }
                    logger.info(f"MoM metrics calculated: {metrics['mom']}")

            except Exception as e:
                logger.error(f"Error calculating MoM: {str(e)}")
                logger.error(traceback.format_exc())

            # Get trade statistics
            trade_stats = get_trade_statistics()
            metrics["trades"] = trade_stats
            logger.info(f"Trade metrics: {trade_stats}")

        except Exception as e:
            logger.error(f"Error calculating metrics: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify(metrics)

        logger.info(f"Final metrics being returned: {metrics}")
        return jsonify(metrics)
        
    except Exception as e:
        logger.error(f"Error in performance metrics endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify(metrics), 500

@app.route('/api/positions')
def get_positions():
    try:
        logger.info("Fetching positions...")
        
        if not strategy or not strategy.alpaca_api:
            logger.warning("Strategy or Alpaca API not initialized")
            return jsonify({"positions": []})

        positions = strategy.alpaca_api.list_positions()
        positions_data = [{
            "symbol": pos.symbol,
            "qty": pos.qty,
            "market_value": pos.market_value,
            "unrealized_pl": pos.unrealized_pl,
            "unrealized_plpc": pos.unrealized_plpc,
            "current_price": pos.current_price,
            "entry_price": pos.avg_entry_price
        } for pos in positions]
        
        logger.info(f"Found {len(positions_data)} positions")
        return jsonify({"positions": positions_data})
    except Exception as e:
        logger.error(f"Error fetching positions: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# Add this to your main.py after the other debug endpoints

@app.route('/api/debug/trades')
def debug_trades():
    """Debug endpoint to check trade tracking"""
    try:
        debug_info = {
            "strategy_initialized": bool(strategy),
            "has_active_trades_attr": hasattr(strategy, 'active_trades') if strategy else False,
            "active_trades_count": len(strategy.active_trades) if strategy and hasattr(strategy, 'active_trades') else 0,
            "active_trades": {},
            "strategy_running": bool(strategy_running),
            "current_time": datetime.now(pytz.timezone('US/Eastern')).strftime("%Y-%m-%d %H:%M:%S %Z")
        }

        if strategy and hasattr(strategy, 'active_trades'):
            for symbol, trade_info in strategy.active_trades.items():
                try:
                    current_quote = strategy.alpaca_api.get_latest_trade(symbol)
                    current_price = float(current_quote.price)
                    entry_price = float(trade_info.get('entry_price', 0))
                    direction = trade_info.get('direction', '')

                    debug_info["active_trades"][symbol] = {
                        "trade_info": trade_info,
                        "current_price": current_price,
                        "entry_price": entry_price,
                        "direction": direction,
                        "pl_amount": (current_price - entry_price) * trade_info.get('num_contracts', 0),
                        "pl_percentage": ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
                    }
                except Exception as e:
                    debug_info["active_trades"][symbol] = {
                        "error": str(e)
                    }

        # Add trade history if available
        debug_info["trade_history"] = []
        if hasattr(strategy, 'trade_history'):
            debug_info["trade_history"] = strategy.trade_history

        logger.info(f"Debug trades info: {json.dumps(debug_info, indent=2)}")
        return jsonify(debug_info)
    except Exception as e:
        logger.error(f"Error in debug trades endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# Update the regular trades endpoint to ensure it always returns data
@app.route('/api/trades')
def get_trades():
    """Get recent trades with enhanced logging"""
    try:
        logger.info("Fetching trades information...")
        
        trades = []
        if strategy and hasattr(strategy, 'active_trades'):
            logger.info(f"Found {len(strategy.active_trades)} active trades")
            
            for symbol, trade_info in strategy.active_trades.items():
                try:
                    current_quote = strategy.alpaca_api.get_latest_trade(symbol)
                    current_price = float(current_quote.price)
                    entry_price = float(trade_info.get('entry_price', 0))
                    
                    trade_data = {
                        "timestamp": trade_info.get('entry_time', datetime.now()).isoformat(),
                        "symbol": symbol,
                        "side": trade_info.get('direction', 'UNKNOWN'),
                        "quantity": trade_info.get('num_contracts', 0),
                        "price": entry_price,
                        "current_price": current_price,
                        "pl_amount": (current_price - entry_price) * trade_info.get('num_contracts', 0),
                        "pl_percentage": ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
                    }
                    trades.append(trade_data)
                    logger.info(f"Processed trade data for {symbol}: {trade_data}")
                    
                except Exception as e:
                    logger.error(f"Error processing trade data for {symbol}: {str(e)}")
                    continue

        # Add trade history if available
        if hasattr(strategy, 'trade_history'):
            trades.extend(strategy.trade_history)

        logger.info(f"Returning {len(trades)} trades")
        return jsonify({
            "trades": trades,
            "count": len(trades),
            "strategy_running": bool(strategy_running)
        })
        
    except Exception as e:
        logger.error(f"Error in trades endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "trades": [],
            "count": 0,
            "strategy_running": bool(strategy_running),
            "error": str(e)
        })
    
class PDTTracker:
    def __init__(self, storage_path='trade_history.json'):
        self.storage_path = storage_path
        self.trades = self._load_trades()
        self._cleanup_old_trades()

    def _load_trades(self):
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    # Convert stored timestamps back to datetime objects
                    for trade in data['trades']:
                        if isinstance(trade['timestamp'], str):
                            trade['timestamp'] = datetime.fromisoformat(trade['timestamp'])
                    return data
            return {'trades': [], 'last_reset': None}
        except Exception as e:
            logger.error(f"Error loading trades: {str(e)}")
            return {'trades': [], 'last_reset': None}

    def _save_trades(self):
        try:
            # Ensure directory exists for the storage path
            os.makedirs(os.path.dirname(self.storage_path) if os.path.dirname(self.storage_path) else '.', exist_ok=True)
            
            data = {
                'trades': [
                    {
                        'timestamp': trade['timestamp'].isoformat() if isinstance(trade['timestamp'], datetime) else trade['timestamp'],
                        'info': trade['info']
                    }
                    for trade in self.trades['trades']
                ],
                'last_reset': self.trades['last_reset']
            }
            
            with open(self.storage_path, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            logger.error(f"Error saving trades: {str(e)}")

    def _cleanup_old_trades(self):
        try:
            one_week_ago = datetime.now() - timedelta(days=7)
            self.trades['trades'] = [
                trade for trade in self.trades['trades']
                if (isinstance(trade['timestamp'], datetime) and trade['timestamp'] > one_week_ago) or
                   (isinstance(trade['timestamp'], str) and datetime.fromisoformat(trade['timestamp']) > one_week_ago)
            ]
            self._save_trades()
        except Exception as e:
            logger.error(f"Error cleaning up trades: {str(e)}")

    def add_trade(self, trade_info):
        try:
            now = datetime.now()
            self.trades['trades'].append({
                'timestamp': now,
                'info': trade_info
            })
            self._save_trades()
            return self.get_trades_remaining()
        except Exception as e:
            logger.error(f"Error adding trade: {str(e)}")
            return 0

    def get_weekly_trade_count(self):
        try:
            now = datetime.now()
            week_ago = now - timedelta(days=7)
            return sum(1 for trade in self.trades['trades'] 
                      if (isinstance(trade['timestamp'], datetime) and trade['timestamp'] > week_ago) or
                         (isinstance(trade['timestamp'], str) and datetime.fromisoformat(trade['timestamp']) > week_ago))
        except Exception as e:
            logger.error(f"Error getting weekly trade count: {str(e)}")
            return 0

    def can_trade(self):
        """
        Check if trading is allowed.
        Returns tuple (can_trade, should_use_next_day)
        """
        weekly_trades = self.get_weekly_trade_count()
        if weekly_trades < 3:
            return (True, False)  # Can trade today
        elif weekly_trades == 3:
            return (True, True)   # Can trade but must be for next day
        return (False, False)     # Cannot trade at all

    def get_trades_remaining(self):
        return max(0, 3 - self.get_weekly_trade_count())

    def get_next_available_trade_date(self):
        """Get the next date when trading will be available"""
        if self.can_trade()[0]:
            return datetime.now()
        
        sorted_trades = sorted(self.trades['trades'], 
                             key=lambda x: x['timestamp'] if isinstance(x['timestamp'], datetime) 
                             else datetime.fromisoformat(x['timestamp']))
        oldest_trade = sorted_trades[0]
        oldest_timestamp = oldest_trade['timestamp'] if isinstance(oldest_trade['timestamp'], datetime) \
                          else datetime.fromisoformat(oldest_trade['timestamp'])
        return oldest_timestamp + timedelta(days=7)

# Initialize PDT Tracker
if os.getenv('GAE_ENV', '').startswith('standard'):
    pdt_tracker = PDTTracker(storage_path='/tmp/trade_history.json')
else:
    pdt_tracker = PDTTracker(storage_path='trade_history.json')


def initialize_strategy():
    """Initialize the trading strategy with detailed logging"""
    global strategy
    try:
        logger.info("Starting strategy initialization...")
        
        # Log credential status
        logger.info("Checking credentials...")
        cred_status = {
            "alpaca_key": bool(ALPACA_API_KEY),
            "alpaca_secret": bool(ALPACA_SECRET_KEY),
            "gmail_user": bool(GMAIL_USER),
            "gmail_pass": bool(GMAIL_PASSWORD)
        }
        logger.info(f"Credential status: {json.dumps(cred_status)}")
        
        if not all([ALPACA_API_KEY, ALPACA_SECRET_KEY, GMAIL_USER, GMAIL_PASSWORD]):
            missing_creds = [k for k, v in cred_status.items() if not v]
            error_msg = f"Missing credentials: {', '.join(missing_creds)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Create strategy instance
        logger.info("Creating strategy instance...")
        strategy = ZeroDTEStrategy(
            ALPACA_API_KEY,
            ALPACA_SECRET_KEY,
            GMAIL_USER,
            GMAIL_PASSWORD
        )
        
        # Verify Alpaca connection
        logger.info("Verifying Alpaca connection...")
        if not verify_alpaca_connection():
            raise Exception("Failed to verify Alpaca connection")
        logger.info("Alpaca connection verified successfully")
        
        # Verify Gmail connection
        logger.info("Verifying Gmail connection...")
        if not verify_gmail_connection():
            raise Exception("Failed to verify Gmail connection")
        logger.info("Gmail connection verified successfully")
        
        logger.info("Strategy initialization completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Strategy initialization failed: {str(e)}")
        logger.error(traceback.format_exc())
        return False

@app.route('/api/start', methods=['POST'])
def start_strategy():
    """Start the trading strategy with enhanced error handling"""
    global strategy, strategy_running, strategy_thread
    try:
        logger.info("Start strategy request received")
        
        # Check trading hours first
        if not is_trading_hours():
            error_msg = "Cannot start strategy outside trading hours"
            logger.warning(error_msg)
            return jsonify({
                "error": error_msg,
                "current_time": datetime.now(pytz.timezone('US/Eastern')).strftime("%Y-%m-%d %H:%M:%S %Z")
            }), 400
        
        # Check if strategy is already running
        if strategy_running:
            logger.info("Strategy is already running")
            return jsonify({"message": "Strategy already running"}), 200
        
        # Initialize strategy if needed
        if not strategy:
            logger.info("Strategy not initialized, attempting initialization...")
            if not initialize_strategy():
                error_msg = "Failed to initialize strategy - check logs for details"
                logger.error(error_msg)
                return jsonify({"error": error_msg}), 500
            logger.info("Strategy initialized successfully")
        
        # Start the strategy thread
        try:
            logger.info("Starting strategy thread...")
            strategy_thread = Thread(target=strategy.run)
            strategy_thread.daemon = True
            strategy_thread.start()
            
            # Give the thread a moment to start and verify it's running
            time_module.sleep(1)
            if not strategy_thread.is_alive():
                raise Exception("Strategy thread failed to start")
            
            strategy_running = True
            logger.info("Strategy started successfully")
            
            return jsonify({
                "message": "Strategy started successfully",
                "status": "running"
            }), 200
            
        except Exception as e:
            strategy_running = False
            strategy_thread = None
            error_msg = f"Failed to start strategy thread: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            return jsonify({"error": error_msg}), 500
            
    except Exception as e:
        logger.error(f"Error in start strategy endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "error": "Failed to start strategy",
            "details": str(e)
        }), 500

@app.route('/api/stop', methods=['POST'])
def stop_strategy():
    global strategy_running, strategy_thread
    try:
        if strategy_running:
            strategy_running = False
            if strategy_thread and strategy_thread.is_alive():
                strategy_thread = None
            return jsonify({"message": "Strategy stopped successfully"})
        return jsonify({"message": "Strategy not running"})
    except Exception as e:
        logger.error(f"Error in stop strategy endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route('/api/close_position/<symbol>', methods=['POST'])
def close_position(symbol):
    try:
        if not strategy:
            return jsonify({"error": "Strategy not initialized"}), 400

        positions = strategy.alpaca_api.list_positions()
        position_to_close = None
        for pos in positions:
            if pos.symbol == symbol:
                position_to_close = pos
                break

        if not position_to_close:
            return jsonify({"error": f"No position found for {symbol}"}), 404

        order = strategy.alpaca_api.submit_order(
            symbol=symbol,
            qty=position_to_close.qty,
            side='sell',
            type='market',
            time_in_force='day'
        )

        return jsonify({"message": f"Position closed for {symbol}", "order_id": order.id})
    except Exception as e:
        logger.error(f"Error in close position endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"Unhandled exception: {str(e)}")
    logger.error(traceback.format_exc())
    
    if isinstance(e, HTTPException):
        return jsonify({"error": str(e)}), e.code
    
    if not os.getenv('GAE_ENV', '').startswith('standard'):
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
    
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    try:
        # Initialize application state
        logger.info("Starting application...")
        
        is_prod = os.getenv('GAE_ENV', '').startswith('standard')
        port = int(os.environ.get('PORT', 8080 if is_prod else 5000))
        
        logger.info(f"Starting Flask app on port {port}")
        app.run(host='0.0.0.0', port=port, debug=not is_prod)
        
    except Exception as e:
        logger.error(f"Failed to start application: {str(e)}")
        sys.exit(1)

# Additional utility endpoints
@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

@app.before_request
def log_request_info():
    logger.debug(f"Request Path: {request.path}")
    logger.debug(f"Request Method: {request.method}")
    logger.debug(f"Request Headers: {dict(request.headers)}")

@app.after_request
def log_response_info(response):
    logger.debug(f"Response Status: {response.status}")
    logger.debug(f"Response Headers: {dict(response.headers)}")
    return response

# Add CORS headers to all responses
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE')
    return response

@app.after_request
def add_security_headers(response):
    if not response.headers.get('Content-Security-Policy'):
        nonce = secrets.token_urlsafe(32)
        csp = "; ".join([
            "default-src 'self'",
            f"script-src 'self' 'unsafe-eval' 'nonce-{nonce}' https://unpkg.com",
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data:",
            "connect-src 'self'"
        ])
        response.headers['Content-Security-Policy'] = csp
    return response

# App Engine warmup handler
@app.route('/_ah/warmup')
def warmup():
    """Handle App Engine warmup requests"""
    logger.info("Warmup request received")
    if is_trading_hours():
        initialize_strategy()
    else:
        logger.info("Skipping strategy initialization during warmup - outside trading hours")
    return '', 200

@app.route('/api/debug/metrics')
def debug_metrics():
    """Debug endpoint to check metrics calculation"""
    try:
        status = {
            "strategy_initialized": bool(strategy),
            "strategy_running": bool(strategy_running),
            "has_alpaca_api": bool(strategy and strategy.alpaca_api if strategy else False),
            "trading_hours": is_trading_hours(),
            "current_time": datetime.now(pytz.timezone('US/Eastern')).strftime("%Y-%m-%d %H:%M:%S %Z"),
            "credentials_configured": {
                "alpaca_key": bool(ALPACA_API_KEY),
                "alpaca_secret": bool(ALPACA_SECRET_KEY),
                "gmail_user": bool(GMAIL_USER),
                "gmail_pass": bool(GMAIL_PASSWORD)
            }
        }
        
        # Add connection test results if strategy exists
        if strategy:
            try:
                status["connections"] = {
                    "alpaca": verify_alpaca_connection(),
                    "gmail": verify_gmail_connection()
                }
            except Exception as e:
                status["connections"] = {
                    "error": str(e)
                }
        
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"Error in debug metrics endpoint: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/debug/portfolio')
def debug_portfolio():
    """Debug endpoint to check portfolio data"""
    try:
        if not strategy or not strategy.alpaca_api:
            return jsonify({"error": "Strategy or API not initialized"})

        # Get current portfolio data
        account = strategy.alpaca_api.get_account()
        
        # Get historical data
        end = datetime.now()
        start_week = end - timedelta(days=7)
        start_month = end - timedelta(days=30)
        
        portfolio_data = {
            "current": {
                "equity": float(account.equity),
                "timestamp": datetime.now().isoformat()
            },
            "history": {
                "week": None,
                "month": None
            }
        }

        try:
            week_history = strategy.alpaca_api.get_portfolio_history(
                period="1W",
                timeframe="1D",
                extended_hours=False
            )
            portfolio_data["history"]["week"] = {
                "equity": week_history.equity,
                "timestamps": week_history.timestamp
            }
        except Exception as e:
            portfolio_data["history"]["week"] = {"error": str(e)}

        try:
            month_history = strategy.alpaca_api.get_portfolio_history(
                period="1M",
                timeframe="1D",
                extended_hours=False
            )
            portfolio_data["history"]["month"] = {
                "equity": month_history.equity,
                "timestamps": month_history.timestamp
            }
        except Exception as e:
            portfolio_data["history"]["month"] = {"error": str(e)}

        return jsonify(portfolio_data)
    except Exception as e:
        logger.error(f"Error in debug portfolio endpoint: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Handle HTTP errors
@app.errorhandler(400)
def bad_request(e):
    logger.error(f"400 error: {str(e)}")
    return jsonify({"error": "Bad request"}), 400

@app.errorhandler(404)
def not_found(e):
    logger.error(f"404 error: {str(e)}")
    return jsonify({"error": "Resource not found"}), 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"500 error: {str(e)}")
    return jsonify({"error": "Internal server error"}), 500

# Request logging middleware
@app.before_request
def log_request():
    logger.info(f"Request: {request.method} {request.url}")
    if request.data:
        logger.debug(f"Request data: {request.data}")

# Response logging middleware
@app.after_request
def log_response(response):
    logger.info(f"Response: {response.status}")
    return response

if __name__ == '__main__':
    try:
        # Initialize application state
        logger.info("Starting application initialization...")
        if not app_state.initialize():
            logger.error("Failed to initialize application")
            sys.exit(1)
            
        # Start Flask app
        is_prod = os.getenv('GAE_ENV', '').startswith('standard')
        port = int(os.environ.get('PORT', 8080 if is_prod else 5000))
        
        logger.info(f"Starting Flask app on port {port}")
        app.run(host='0.0.0.0', port=port, debug=not is_prod)
        
    except Exception as e:
        logger.error(f"Fatal error starting application: {str(e)}")
        logger.error(traceback.format_exc())
        sys.exit(1)