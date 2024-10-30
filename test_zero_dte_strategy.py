import unittest
from unittest.mock import patch, MagicMock
from zero_dte_strategy import ZeroDTEStrategy
from config import ALPACA_API_KEY, ALPACA_SECRET_KEY, GMAIL_USER, GMAIL_PASSWORD
import os
import pandas as pd

class TestZeroDTEStrategy(unittest.TestCase):

    def setUp(self):
        self.mock_api = MagicMock()
        with patch('alpaca_trade_api.REST', return_value=self.mock_api):
            self.strategy = ZeroDTEStrategy(ALPACA_API_KEY, ALPACA_SECRET_KEY, GMAIL_USER, GMAIL_PASSWORD)

    def test_api_connection(self):