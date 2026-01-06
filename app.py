"""
🚀 اسکنر حرفه‌ای حجم، دلتا و معاملات نهنگ - نسخه کامل برای Streamlit Cloud
"""

try:
    import ccxt
except ImportError as e:
    st.error(f"خطا در بارگیری ccxt: {e}")
    st.stop()
import pandas as pd
import numpy as np
import warnings
from datetime import datetime, timedelta
import time
from typing import Dict, List, Tuple, Optional, Any
import streamlit as st
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import traceback
from dataclasses import dataclass
from enum import Enum
import plotly.graph_objects as go
import asyncio

warnings.filterwarnings('ignore')

# ==================== CONFIGURATION ====================
class Config:
    """کلاس پیکربندی اسکنر - نسخه بهینه برای Cloud"""
    
    # 50 ارز برتر برای اجرای سریع‌تر
    ALL_SYMBOLS = [
        'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT',
        'ADA/USDT', 'AVAX/USDT', 'DOGE/USDT', 'DOT/USDT', 'TRX/USDT',
        'LINK/USDT', 'MATIC/USDT', 'SHIB/USDT', 'LTC/USDT', 'BCH/USDT',
        'UNI/USDT', 'ATOM/USDT', 'XLM/USDT', 'ETC/USDT', 'FIL/USDT',
        'APT/USDT', 'ARB/USDT', 'NEAR/USDT', 'VET/USDT', 'OP/USDT',
        'AAVE/USDT', 'ALGO/USDT', 'QNT/USDT', 'GRT/USDT', 'EGLD/USDT',
        'SAND/USDT', 'MANA/USDT', 'AXS/USDT', 'THETA/USDT', 'XTZ/USDT',
        'EOS/USDT', 'SNX/USDT', 'RUNE/USDT', 'FTM/USDT', 'KAVA/USDT',
        'CRV/USDT', 'ZEC/USDT', 'DASH/USDT', 'ENJ/USDT', 'COMP/USDT',
        'MKR/USDT', 'YFI/USDT', 'SUSHI/USDT', 'CELO/USDT', 'ONE/USDT'
    ]
    
    # صرافی‌ها
    EXCHANGES = {
        'binance': {'name': 'بایننس', 'color': '#F0B90B', 'weight': 1.2},
        'bybit': {'name': 'بایبیت', 'color': '#FF6B35', 'weight': 1.1},
        'kucoin': {'name': 'کوکوین', 'color': '#24C4A5', 'weight': 1.0}
    }
    
    # پارامترهای امتیازدهی
    SCORING_PARAMS = {
        'VOLUME_SCORE': {
            'base_weight': 40,
            'thresholds': {'strong_spike': 3.0, 'medium_spike': 2.0, 'weak_spike': 1.5},
            'scores': {'strong': 25, 'medium': 15, 'weak': 8, 'none': 0}
        },
        'CONSISTENCY_SCORE': {
            'base_weight': 45,
            'min_exchanges_for_consistency': 2,
            'score_per_aligned_exchange': 15,
            'max_consistency_score': 45
        },
        'DELTA_SCORE': {
            'base_weight': 30,
            'strong_threshold': 0.6,
            'medium_threshold': 0.3,
            'scores': {'strong': 20, 'medium': 10, 'weak': 5, 'none': 0}
        },
        'WHALE_SCORE': {
            'base_weight': 15,
            'min_trade_value': 100000,
            'score_per_whale_trade': 3,
            'max_whale_score': 15
        },
        'ANALYSIS_PARAMS': {
            'volume_spike_threshold': 2.5,
            'lookback_period': 20,
            'min_avg_volume': 1000,
            'delta_lookback_minutes': 5,
            'whale_lookback_minutes': 10,
            'max_trades_per_request': 200
        }
    }
    
    COLORS = {
        'primary': '#2563EB',
        'success': '#059669',
        'danger': '#DC2626',
        'warning': '#D97706',
        'info': '#0EA5E9',
        'volume_spike': '#EA580C',
        'whale_buy': '#10B981',
        'whale_sell': '#EF4444',
        'neutral': '#6B7280'
    }

# ==================== ENUMS & DATA CLASSES ====================
class SignalType(Enum):
    """انواع سیگنال‌های تحلیل"""
    VOLUME_SPIKE = "اسپایک حجم"
    STRONG_BUY_DELTA = "دلتای خرید قوی"
    STRONG_SELL_DELTA = "دلتای فروش قوی"
    WHALE_BUY = "خرید نهنگ"
    WHALE_SELL = "فروش نهنگ"
    CONSISTENT_TREND = "روند همسو"

@dataclass
class ExchangeAnalysis:
    """نتایج تحلیل یک صرافی"""
    exchange_id: str
    symbol: str
    price: float
    volume_ratio: float
    delta: float
    delta_direction: str
    buy_volume: float
    sell_volume: float
    total_volume: float
    whale_trades: List
    signals: List[SignalType]

@dataclass
class SymbolAnalysis:
    """نتایج تحلیل کامل یک نماد"""
    symbol: str
    timestamp: datetime
    exchange_analyses: Dict[str, ExchangeAnalysis]
    consistency_score: float
    volume_score: float
    final_score: float
    aggregated_signals: List[SignalType]
    exchange_count: int

# ==================== WHALE TRACKER ====================
class WhaleTracker:
    """ردیاب معاملات نهنگ - نسخه بهینه برای Cloud"""
    
    def __init__(self):
        self.exchanges = self._init_exchanges()
        self.whale_trades = defaultdict(list)
        self.rate_limit_delay = 0.2
        
    def _init_exchanges(self):
        """راه‌اندازی صرافی‌ها"""
        exchanges = {}
        for exchange_id, config in Config.EXCHANGES.items():
            try:
                exchange_class = getattr(ccxt, exchange_id)
                exchange = exchange_class({
                    'timeout': 30000,
                    'enableRateLimit': True,
                    'options': {'defaultType': 'spot'}
                })
                exchange.load_markets()
                exchanges[exchange_id] = exchange
            except Exception as e:
                print(f"⚠️ خطا در اتصال به {config['name']}: {str(e)[:50]}")
        return exchanges

    
