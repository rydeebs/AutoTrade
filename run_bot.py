import logging
from zero_dte_strategy import ZeroDTEStrategy
from config import ALPACA_API_KEY, ALPACA_SECRET_KEY, GMAIL_USER, GMAIL_PASSWORD

# Set up logging to both console and file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),
        logging.StreamHandler()
    ]
)

def main():
    logger = logging.getLogger(__name__)
    logger.info("Starting trading bot...")
    
    strategy = ZeroDTEStrategy(ALPACA_API_KEY, ALPACA_SECRET_KEY, GMAIL_USER, GMAIL_PASSWORD)
    strategy.run()

if __name__ == "__main__":
    main()