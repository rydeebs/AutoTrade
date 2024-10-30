from flask import Flask, render_template, jsonify, send_file
import logging
import google.cloud.logging
from datetime import datetime, time, timedelta
import time as time_module
import pytz
import os
from zero_dte_strategy import ZeroDTEStrategy
import pandas as pd
from config import ALPACA_API_KEY, ALPACA_SECRET_KEY, GMAIL_USER, GMAIL_PASSWORD
import sys
from threading import Thread
import alpaca_trade_api as tradeapi

# Setup Google Cloud Logging
client = google.cloud.logging.Client()
client.setup_logging()

app = Flask(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Global strategy instance
strategy = None
strategy_thread = None

def is_trading_hours():
    """Check if current time is during trading hours (9:30 AM - 4:00 PM EST)"""
    est = pytz.timezone('US/Eastern')
    now = datetime.now(est)
    current_time = now.time()
    
    # Check if it's a weekday (Monday = 0, Sunday = 6)
    if now.weekday() >= 5:  # Weekend
        return False
    
    market_open = time(9, 30)
    market_close = time(16, 0)
    
    return market_open <= current_time <= market_close

def initialize_strategy():
    """Initialize the trading strategy"""
    global strategy, strategy_thread
    try:
        if strategy is None:
            logger.info("Initializing trading strategy...")
            logger.info(f"Checking API Keys - ALPACA_API_KEY: {ALPACA_API_KEY[:5]}... ALPACA_SECRET_KEY: {ALPACA_SECRET_KEY[:5]}...")
            
            # Test Alpaca API connection first
            test_api = tradeapi.REST(ALPACA_API_KEY, ALPACA_SECRET_KEY, base_url='https://api.alpaca.markets')
            try:
                account = test_api.get_account()
                logger.info(f"Successfully connected to Alpaca. Account Status: {account.status}")
            except Exception as api_error:
                logger.error(f"Failed to connect to Alpaca API: {str(api_error)}")
                return False

            # Initialize strategy if API connection successful
            strategy = ZeroDTEStrategy(ALPACA_API_KEY, ALPACA_SECRET_KEY, GMAIL_USER, GMAIL_PASSWORD)
            strategy_thread = Thread(target=strategy.run)
            strategy_thread.daemon = True
            strategy_thread.start()
            logger.info("Strategy initialized and running")
            return True
    except Exception as e:
        logger.error(f"Error initializing strategy: {str(e)}", exc_info=True)
        return False

@app.before_first_request
def startup():
    """Initialize the strategy before the first request"""
    initialize_strategy()

@app.route('/_ah/warmup')
def warmup():
    """App Engine warmup handler"""
    logger.info("Warmup request received")
    return '', 200

@app.route('/start')
def start_strategy():
    """Start the trading strategy"""
    if initialize_strategy():
        return jsonify({"status": "Strategy started successfully"})
    return jsonify({"error": "Failed to start strategy"}), 500

@app.route('/stop')
def stop_strategy():
    """Stop the trading strategy"""
    global strategy, strategy_thread
    try:
        if strategy is not None:
            strategy = None
            strategy_thread = None
            return jsonify({"status": "Strategy stopped successfully"})
        return jsonify({"status": "Strategy was not running"})
    except Exception as e:
        logger.error(f"Error stopping strategy: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/')
def home():
    """Render the main dashboard"""
    logger.info("Home page accessed")
    return render_template('index.html')

@app.route('/health')
def health():
    """Health check endpoint"""
    logger.info("Health check endpoint accessed")
    return jsonify({"status": "healthy"})

@app.route('/debug')
def get_debug_info():
    """Get debug information about the trading system"""
    return jsonify({
        'strategy_running': strategy is not None,
        'trading_hours': is_trading_hours(),
        'current_symbols': strategy.symbols if strategy else [],
        'has_api_connection': bool(strategy.alpaca_api) if strategy else False,
        'last_check_time': datetime.now(pytz.timezone('US/Eastern')).strftime('%Y-%m-%d %H:%M:%S %Z')
    })

@app.route('/status')
def get_status():
    """Get current bot status"""
    logger.info("Status endpoint accessed")
    est = pytz.timezone('US/Eastern')
    current_time = datetime.now(est)
    
    return jsonify({
        'is_trading_hours': is_trading_hours(),
        'strategy_running': strategy is not None,
        'current_time': current_time.strftime('%Y-%m-%d %H:%M:%S %Z'),
        'next_market_open': get_next_market_open(),
        'next_market_close': get_next_market_close(),
        'symbols_tracked': strategy.symbols if strategy else []
    })

@app.route('/market-conditions')
def get_market_conditions():
    """Get current market conditions"""
    if not strategy:
        return jsonify({'error': 'Strategy not running'}), 400
    
    try:
        conditions = {}
        for symbol in strategy.symbols:
            if symbol in strategy.data:
                conditions[symbol] = {
                    'current_price': strategy.data[symbol].get('current_price'),
                    'volume': strategy.data[symbol].get('volume'),
                    'tradeability': strategy.data[symbol].get('tradeability'),
                    'ps': strategy.data[symbol].get('ps'),
                    'blue_line_relation': strategy.data[symbol].get('blue_line_relation')
                }
        return jsonify(conditions)
    except Exception as e:
        logger.error(f"Error getting market conditions: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/test-buy')
def test_buy():
    """Test buying functionality"""
    if not strategy:
        return jsonify({'error': 'Strategy not running'}), 400
    
    try:
        # Test buy for SPY
        strategy.enter_trade('SPY', 'buy')
        return jsonify({'message': 'Test buy order submitted successfully'})
    except Exception as e:
        logger.error(f"Test buy failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/positions')
def get_positions():
    """Get current positions"""
    logger.info("Positions endpoint accessed")
    if strategy and strategy.alpaca_api:
        try:
            positions = strategy.alpaca_api.list_positions()
            return jsonify({
                'positions': [{
                    'symbol': p.symbol,
                    'qty': p.qty,
                    'current_price': float(p.current_price),
                    'entry_price': float(p.avg_entry_price),
                    'pl_day': float(p.unrealized_plpc),
                    'market_value': float(p.market_value)
                } for p in positions]
            })
        except Exception as e:
            logger.error(f"Error getting positions: {str(e)}")
            return jsonify({'error': str(e)})
    return jsonify({'positions': []})

@app.route('/trades')
def get_trades():
    """Get trade history"""
    logger.info("Trades endpoint accessed")
    try:
        logging_client = google.cloud.logging.Client()
        logger = logging_client.logger('trades')
        
        entries = logger.list_entries(
            order_by=google.cloud.logging.DESCENDING,
            page_size=100
        )
        return jsonify({'trades': [entry.payload for entry in entries]})
    except Exception as e:
        logger.error(f"Error getting trades: {str(e)}")
        return jsonify({'error': str(e)})

@app.route('/logs')
def get_logs():
    """Get application logs"""
    logger.info("Logs endpoint accessed")
    try:
        logging_client = google.cloud.logging.Client()
        log_logger = logging_client.logger('app')
        
        entries = log_logger.list_entries(
            order_by=google.cloud.logging.DESCENDING,
            page_size=100
        )
        return jsonify({'logs': [entry.payload for entry in entries]})
    except Exception as e:
        logger.error(f"Error getting logs: {str(e)}")
        return jsonify({'error': str(e)})

@app.route('/account')
def get_account():
    """Get account information"""
    logger.info("Account endpoint accessed")
    if strategy and strategy.alpaca_api:
        try:
            account = strategy.alpaca_api.get_account()
            return jsonify({
                'equity': float(account.equity),
                'buying_power': float(account.buying_power),
                'cash': float(account.cash),
                'day_trade_count': int(account.daytrade_count),
                'last_equity': float(account.last_equity)
            })
        except Exception as e:
            logger.error(f"Error getting account info: {str(e)}")
            return jsonify({'error': str(e)})
    return jsonify({'error': 'Strategy not running'})

def get_next_market_open():
    """Get the next market open time"""
    est = pytz.timezone('US/Eastern')
    now = datetime.now(est)
    current_time = now.time()
    market_open = time(9, 30)
    
    # If it's before market open today, return today's market open
    if current_time < market_open and now.weekday() < 5:
        next_open = datetime.combine(now.date(), market_open)
        return est.localize(next_open).strftime('%Y-%m-%d %H:%M:%S %Z')
    
    # Otherwise, find the next weekday
    days_ahead = 1
    while True:
        next_date = now.date() + timedelta(days=days_ahead)
        if next_date.weekday() < 5:  # Monday-Friday
            next_open = datetime.combine(next_date, market_open)
            return est.localize(next_open).strftime('%Y-%m-%d %H:%M:%S %Z')
        days_ahead += 1

def get_next_market_close():
    """Get the next market close time"""
    est = pytz.timezone('US/Eastern')
    now = datetime.now(est)
    current_time = now.time()
    market_close = time(16, 0)
    
    # If it's before market close today, return today's market close
    if current_time < market_close and now.weekday() < 5:
        next_close = datetime.combine(now.date(), market_close)
        return est.localize(next_close).strftime('%Y-%m-%d %H:%M:%S %Z')
    
    # Otherwise, find the next weekday
    days_ahead = 1
    while True:
        next_date = now.date() + timedelta(days=days_ahead)
        if next_date.weekday() < 5:  # Monday-Friday
            next_close = datetime.combine(next_date, market_close)
            return est.localize(next_close).strftime('%Y-%m-%d %H:%M:%S %Z')
        days_ahead += 1

@app.route('/performance')
def get_performance():
    """Get performance metrics"""
    logger.info("Performance endpoint accessed")
    try:
        logging_client = google.cloud.logging.Client()
        trades_logger = logging_client.logger('trades')
        
        entries = trades_logger.list_entries(
            order_by=google.cloud.logging.DESCENDING
        )
        
        trades_data = []
        for entry in entries:
            if 'profit_loss' in entry.payload:
                trades_data.append(entry.payload)
        
        if trades_data:
            total_trades = len(trades_data)
            winning_trades = sum(1 for trade in trades_data if trade['profit_loss'] > 0)
            total_profit = sum(trade['profit_loss'] for trade in trades_data)
            win_rate = winning_trades / total_trades if total_trades > 0 else 0
            
            return jsonify({
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'win_rate': f"{win_rate:.2%}",
                'total_profit': f"${total_profit:.2f}"
            })
        
        return jsonify({
            'total_trades': 0,
            'winning_trades': 0,
            'win_rate': "0.00%",
            'total_profit': "$0.00"
        })
        
    except Exception as e:
        logger.error(f"Error calculating performance: {str(e)}")
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    # Run the Flask app
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

@app.route('/test-connection')
def test_connection():
    """Test Alpaca API connection"""
    try:
        test_api = tradeapi.REST(ALPACA_API_KEY, ALPACA_SECRET_KEY, base_url='https://api.alpaca.markets')
        account = test_api.get_account()
        return jsonify({
            'status': 'success',
            'account_status': account.status,
            'buying_power': account.buying_power,
            'cash': account.cash
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'api_key_present': bool(ALPACA_API_KEY),
            'secret_key_present': bool(ALPACA_SECRET_KEY)
        }), 500