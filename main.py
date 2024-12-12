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

def verify_alpaca_connection():
    """Verify Alpaca API connection"""
    try:
        api = tradeapi.REST(
            ALPACA_API_KEY,
            ALPACA_SECRET_KEY,
            base_url='https://api.alpaca.markets'
        )
        account = api.get_account()
        return True
    except Exception as e:
        logger.error(f"Alpaca connection failed: {str(e)}")
        return False

# Initialize global variables
strategy = None
strategy_thread = None
strategy_running = False

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

# PDT Tracker implementation (keep your existing PDTTracker class here)
class PDTTracker:
    def __init__(self, storage_path='trade_history.json'):
        self.storage_path = storage_path
        self.trades = self._load_trades()
        self._cleanup_old_trades()

    # ... (keep rest of PDTTracker implementation)

# Initialize Flask app
app = Flask(__name__)

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

@app.route('/api/status')
def get_status():
    try:
        return jsonify({
            "is_trading_hours": is_trading_hours(),
            "strategy_running": strategy_running if strategy else False,
            "current_time": datetime.now(pytz.timezone('US/Eastern')).strftime("%Y-%m-%d %H:%M:%S %Z")
        })
    except Exception as e:
        logger.error(f"Error in status endpoint: {str(e)}")
        raise

@app.route('/api/account')
def get_account():
    try:
        if not strategy or not strategy.alpaca_api:
            return jsonify({
                'equity': 0,
                'buying_power': 0,
                'cash': 0
            })

        account = strategy.alpaca_api.get_account()
        return jsonify({
            'equity': float(account.equity),
            'buying_power': float(account.buying_power),
            'cash': float(account.cash)
        })
    except Exception as e:
        logger.error(f"Error in account endpoint: {str(e)}")
        raise

@app.route('/api/performance_metrics')
def get_performance_metrics():
    """Get trading performance metrics"""
    try:
        metrics = {
            "wow": {"percentage": 0, "dollars": 0},
            "mom": {"percentage": 0, "dollars": 0},
            "trades": {"won": 0, "lost": 0}
        }

        if strategy and strategy.alpaca_api:
            try:
                # Get account history
                end = datetime.now()
                start_week = end - timedelta(days=7)
                start_month = end - timedelta(days=30)
                
                account = strategy.alpaca_api.get_account()
                current_equity = float(account.equity)

                # Week over week calculation
                try:
                    portfolio_history = strategy.alpaca_api.get_portfolio_history(
                        timeframe='1D',
                        start=start_week.strftime('%Y-%m-%d'),
                        end=end.strftime('%Y-%m-%d')
                    )
                    
                    if portfolio_history and portfolio_history.equity and len(portfolio_history.equity) > 0:
                        week_start_equity = portfolio_history.equity[0]
                        wow_change = current_equity - week_start_equity
                        metrics["wow"] = {
                            "percentage": (wow_change / week_start_equity * 100) if week_start_equity else 0,
                            "dollars": wow_change
                        }
                except Exception as e:
                    logger.error(f"Error calculating WoW metrics: {str(e)}")

                # Month over month calculation
                try:
                    portfolio_history = strategy.alpaca_api.get_portfolio_history(
                        timeframe='1D',
                        start=start_month.strftime('%Y-%m-%d'),
                        end=end.strftime('%Y-%m-%d')
                    )
                    
                    if portfolio_history and portfolio_history.equity and len(portfolio_history.equity) > 0:
                        month_start_equity = portfolio_history.equity[0]
                        mom_change = current_equity - month_start_equity
                        metrics["mom"] = {
                            "percentage": (mom_change / month_start_equity * 100) if month_start_equity else 0,
                            "dollars": mom_change
                        }
                except Exception as e:
                    logger.error(f"Error calculating MoM metrics: {str(e)}")

            except Exception as e:
                logger.error(f"Error fetching performance metrics: {str(e)}")

        return jsonify(metrics)
    except Exception as e:
        logger.error(f"Error in performance metrics endpoint: {str(e)}")
        raise

@app.route('/api/positions')
def get_positions():
    try:
        if not strategy or not strategy.alpaca_api:
            return jsonify({"positions": []})

        positions = strategy.alpaca_api.list_positions()
        return jsonify({
            "positions": [
                {
                    "symbol": pos.symbol,
                    "qty": pos.qty,
                    "market_value": pos.market_value,
                    "unrealized_pl": pos.unrealized_pl,
                    "unrealized_plpc": pos.unrealized_plpc,
                    "current_price": pos.current_price,
                    "entry_price": pos.avg_entry_price
                }
                for pos in positions
            ]
        })
    except Exception as e:
        logger.error(f"Error in positions endpoint: {str(e)}")
        raise

@app.route('/api/trades')
def get_trades():
    try:
        if not strategy:
            return jsonify({"trades": []})

        # Get recent trades from strategy
        trades = []
        if hasattr(strategy, 'active_trades'):
            for symbol, trade_info in strategy.active_trades.items():
                trades.append({
                    "symbol": symbol,
                    "entry_time": trade_info.get('entry_time', '').isoformat() if isinstance(trade_info.get('entry_time'), datetime) else trade_info.get('entry_time', ''),
                    "direction": trade_info.get('direction', ''),
                    "quantity": trade_info.get('num_contracts', 0),
                    "entry_price": trade_info.get('entry_price', 0.0)
                })

        return jsonify({"trades": trades})
    except Exception as e:
        logger.error(f"Error in trades endpoint: {str(e)}")
        raise

@app.route('/api/start', methods=['POST'])
def start_strategy():
    global strategy_running, strategy_thread
    try:
        if not strategy_running:
            strategy_running = True
            strategy_thread = Thread(target=strategy.run)
            strategy_thread.daemon = True
            strategy_thread.start()
            return jsonify({"message": "Strategy started successfully"})
        return jsonify({"message": "Strategy already running"})
    except Exception as e:
        logger.error(f"Error in start strategy endpoint: {str(e)}")
        raise

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
        raise

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
        raise

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