import streamlit as st
import pandas as pd
import numpy as np
import ccxt
import talib
from scipy.signal import argrelextrema
from sklearn.cluster import DBSCAN, KMeans
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
import hashlib
import sqlite3
import warnings
warnings.filterwarnings('ignore')

# ============================================
# 🔧 Settings
# ============================================

CACHE_DURATION_DATA = 120  # 2 دقائق
CACHE_DURATION_ANALYSIS = 300
MAX_CANDLES = 500
RATE_LIMIT_DELAY = 0.5

ADMIN_USERNAME = "adminSO"
ADMIN_PASSWORD = "admin25SO"

# قائمة الرموز التي هي فيوتشر فقط على Bybit
FUTURE_ONLY_SYMBOLS = ['XAU/USDT', 'XAG/USDT', 'BTC/USDT:USDT', 'ETH/USDT:USDT']

# ============================================
# 🏦 Bybit Exchange (Spot + Futures)
# ============================================

@st.cache_resource
def get_exchange_spot():
    """Bybit Spot"""
    try:
        exchange = ccxt.bybit({
            'rateLimit': 3000,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
                'adjustForTimeDifference': True
            }
        })
        exchange.fetch_ohlcv('BTC/USDT', '1h', limit=1)
        return exchange
    except Exception as e:
        st.error(f"❌ Bybit Spot connection error: {str(e)}")
        return None

@st.cache_resource
def get_exchange_future():
    """Bybit Futures (Perpetual)"""
    try:
        exchange = ccxt.bybit({
            'rateLimit': 3000,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
                'adjustForTimeDifference': True
            }
        })
        exchange.fetch_ohlcv('BTC/USDT:USDT', '1h', limit=1)
        return exchange
    except Exception as e:
        st.error(f"❌ Bybit Futures connection error: {str(e)}")
        return None

# ============================================
# 📊 Data Fetcher - مع إدارة الطلبات
# ============================================

def fetch_with_retry(exchange, symbol, timeframe, limit, max_retries=3):
    """جلب البيانات مع إعادة المحاولة"""
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                time.sleep(RATE_LIMIT_DELAY * attempt)
            
            if timeframe:
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            else:
                ohlcv = exchange.fetch_trades(symbol, limit=limit)
            
            if ohlcv and len(ohlcv) > 0:
                return ohlcv
        except ccxt.RateLimitExceeded:
            if attempt == max_retries - 1:
                st.warning(f"⏳ Rate limit exceeded. Retrying...")
                time.sleep(5)
            else:
                time.sleep(RATE_LIMIT_DELAY * 2)
        except ccxt.BadSymbol as e:
            st.error(f"❌ Symbol {symbol} not found on Bybit")
            return None
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            time.sleep(RATE_LIMIT_DELAY)
    
    return None

def detect_market_type(symbol):
    """كشف نوع السوق (سبوت أو فيوتشر)"""
    clean_symbol = symbol.upper().strip()
    
    # 1. كشف من الصيغة
    if ':' in clean_symbol:
        return 'future'
    if clean_symbol.endswith('-PERP') or clean_symbol.endswith('-SWAP'):
        return 'future'
    
    # 2. المعادن الثمينة دائماً فيوتشر
    if clean_symbol.startswith('XAU') or clean_symbol.startswith('XAG'):
        return 'future'
    
    # 3. قائمة الرموز فيوتشر فقط
    if clean_symbol in ['BTC/USDT:USDT', 'ETH/USDT:USDT']:
        return 'future'
    
    return 'spot'

def convert_symbol_for_exchange(symbol, market_type):
    """تحويل الصيغة حسب نوع السوق"""
    clean_symbol = symbol.upper().strip()
    
    if market_type == 'future':
        if '/' in clean_symbol and ':' not in clean_symbol:
            return clean_symbol.replace('/', '/') + ':USDT'
    return clean_symbol

@st.cache_data(ttl=CACHE_DURATION_DATA)
def fetch_candles_cached(symbol, timeframe='1h', limit=500):
    """
    جلب البيانات من Bybit مع دعم XAU/USDT (فيوتشر فقط)
    """
    clean_symbol = symbol.upper().strip()
    
    # كشف نوع السوق
    market_type = detect_market_type(clean_symbol)
    
    # اختيار الـ Exchange المناسب
    if market_type == 'future':
        exchange = get_exchange_future()
        clean_symbol = convert_symbol_for_exchange(clean_symbol, market_type)
    else:
        exchange = get_exchange_spot()
    
    if not exchange:
        st.error(f"❌ Cannot connect to Bybit")
        return None
    
    try:
        ohlcv = fetch_with_retry(exchange, clean_symbol, timeframe, min(limit, 1000))
        
        if not ohlcv:
            st.error(f"❌ No data received for {clean_symbol}")
            return None
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        return df
        
    except ccxt.BadSymbol as e:
        st.error(f"❌ Symbol {clean_symbol} not found on Bybit. Try: XAU/USDT:USDT")
        return None
    except Exception as e:
        st.error(f"❌ Failed to fetch {clean_symbol}: {str(e)}")
        return None

@st.cache_data(ttl=CACHE_DURATION_DATA)
def fetch_trades_cached(symbol, limit=500):
    """جلب الصفقات الأخيرة من Bybit"""
    try:
        clean_symbol = symbol.upper().strip()
        market_type = detect_market_type(clean_symbol)
        
        if market_type == 'future':
            exchange = get_exchange_future()
            clean_symbol = convert_symbol_for_exchange(clean_symbol, market_type)
        else:
            exchange = get_exchange_spot()
        
        if not exchange:
            return None
        
        # استخدام fetch_with_retry مع timeframe=None
        trades = fetch_with_retry(exchange, clean_symbol, None, limit)
        
        if not trades:
            return None
        
        trades_data = []
        for trade in trades:
            trades_data.append({
                'timestamp': pd.to_datetime(trade['timestamp'], unit='ms'),
                'price': trade['price'],
                'amount': trade['amount'],
                'cost': trade['cost'],
                'side': trade['side'],
                'datetime': trade['datetime']
            })
        
        return pd.DataFrame(trades_data)
    except Exception as e:
        st.warning(f"⚠️ Trades fetch warning (不影响分析): {str(e)}")
        return None

@st.cache_data(ttl=CACHE_DURATION_ANALYSIS)
def calculate_indicators_cached(df):
    """حساب المؤشرات الفنية"""
    if df is None or df.empty:
        return df
    
    try:
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        
        df['RSI'] = talib.RSI(close, timeperiod=14)
        df['MACD'], df['MACD_signal'], df['MACD_hist'] = talib.MACD(close)
        df['SMA_20'] = talib.SMA(close, timeperiod=20)
        df['SMA_50'] = talib.SMA(close, timeperiod=50)
        df['EMA_100'] = talib.EMA(close, timeperiod=100)
        df['ATR'] = talib.ATR(high, low, close, timeperiod=14)
        df['ADX'] = talib.ADX(high, low, close, timeperiod=14)
        
        df['BB_upper'], df['BB_middle'], df['BB_lower'] = talib.BBANDS(
            close, timeperiod=20, nbdevup=2, nbdevdn=2
        )
        
        df['volume_ma'] = talib.SMA(df['volume'], timeperiod=20)
        df['OBV'] = talib.OBV(df['close'], df['volume'])
        
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        df['VWAP'] = (df['volume'] * typical_price).cumsum() / df['volume'].cumsum()
        
        return df.dropna()
    except Exception as e:
        st.error(f"❌ Error calculating indicators: {str(e)}")
        return df

# ============================================
# 🗄️ User Management
# ============================================

class UserManager:
    def __init__(self, db_file="users.db"):
        self.db_file = db_file
        self._init_db()
        self._ensure_admin()
        
    def _init_db(self):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password TEXT NOT NULL,
                    email TEXT,
                    active INTEGER DEFAULT 0,
                    created_at TEXT,
                    last_login TEXT,
                    is_admin INTEGER DEFAULT 0,
                    payment_status TEXT DEFAULT 'pending',
                    payment_date TEXT,
                    expiry_date TEXT
                )
            ''')
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ DB error: {e}")
    
    def _ensure_admin(self):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username=?", (ADMIN_USERNAME,))
            if not cursor.fetchone():
                cursor.execute('''
                    INSERT INTO users 
                    (username, password, email, active, created_at, is_admin, payment_status, payment_date, expiry_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    ADMIN_USERNAME,
                    self._hash_password(ADMIN_PASSWORD),
                    "admin@example.com",
                    1,
                    datetime.now().isoformat(),
                    1,
                    "paid",
                    datetime.now().isoformat(),
                    (datetime.now() + timedelta(days=365)).isoformat()
                ))
                conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ Admin error: {e}")
    
    def _hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()
    
    def register_user(self, username, password, email=""):
        if len(username) < 3:
            return False, "❌ Username must be at least 3 characters!"
        if len(password) < 4:
            return False, "❌ Password must be at least 4 characters!"
        
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username=?", (username,))
            if cursor.fetchone():
                conn.close()
                return False, "❌ Username already exists!"
            
            cursor.execute('''
                INSERT INTO users 
                (username, password, email, active, created_at, is_admin, payment_status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                username,
                self._hash_password(password),
                email,
                0,
                datetime.now().isoformat(),
                0,
                "pending"
            ))
            conn.commit()
            conn.close()
            return True, "✅ Registration successful! Wait for admin activation."
        except Exception as e:
            return False, f"❌ Error: {str(e)}"
    
    def login_user(self, username, password):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username=?", (username,))
            user = cursor.fetchone()
            
            if not user:
                conn.close()
                return False, "❌ Username not found!"
            
            if user[3] == 0:
                conn.close()
                return False, "⛔ Account not activated! Contact admin."
            
            if user[1] != self._hash_password(password):
                conn.close()
                return False, "❌ Incorrect password!"
            
            cursor.execute("UPDATE users SET last_login=? WHERE username=?", 
                         (datetime.now().isoformat(), username))
            conn.commit()
            conn.close()
            return True, "✅ Login successful!"
        except Exception as e:
            return False, f"❌ Error: {str(e)}"
    
    def activate_user(self, username):
        if username == ADMIN_USERNAME:
            return False, "❌ Admin is already activated!"
        
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username=?", (username,))
            user = cursor.fetchone()
            if not user:
                conn.close()
                return False, "❌ User not found!"
            
            if user[3] == 1:
                conn.close()
                return False, f"✅ {username} is already active!"
            
            expiry = datetime.now() + timedelta(days=30)
            cursor.execute('''
                UPDATE users 
                SET active=1, payment_status='paid', payment_date=?, expiry_date=?
                WHERE username=?
            ''', (datetime.now().isoformat(), expiry.isoformat(), username))
            conn.commit()
            conn.close()
            return True, f"✅ Account {username} activated! (Expires: {expiry.strftime('%Y-%m-%d')})"
        except Exception as e:
            return False, f"❌ Error: {str(e)}"
    
    def deactivate_user(self, username):
        if username == ADMIN_USERNAME:
            return False, "❌ Cannot deactivate admin!"
        
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username=?", (username,))
            user = cursor.fetchone()
            if not user:
                conn.close()
                return False, "❌ User not found!"
            
            if user[3] == 0:
                conn.close()
                return False, f"⚠️ {username} is already deactivated!"
            
            cursor.execute('''
                UPDATE users 
                SET active=0, payment_status='expired'
                WHERE username=?
            ''', (username,))
            conn.commit()
            conn.close()
            return True, f"✅ Account {username} deactivated!"
        except Exception as e:
            return False, f"❌ Error: {str(e)}"
    
    def delete_user(self, username):
        if username == ADMIN_USERNAME:
            return False, "❌ Cannot delete admin!"
        
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username=?", (username,))
            if not cursor.fetchone():
                conn.close()
                return False, "❌ User not found!"
            
            cursor.execute("DELETE FROM users WHERE username=?", (username,))
            conn.commit()
            conn.close()
            return True, f"✅ User {username} deleted permanently!"
        except Exception as e:
            return False, f"❌ Error: {str(e)}"
    
    def extend_subscription(self, username, days=30):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT expiry_date, active FROM users WHERE username=?", (username,))
            result = cursor.fetchone()
            
            if not result:
                conn.close()
                return False, "❌ User not found!"
            
            if result[1] == 0:
                cursor.execute('''
                    UPDATE users 
                    SET active=1, payment_status='paid'
                    WHERE username=?
                ''', (username,))
            
            if result[0]:
                current_expiry = datetime.fromisoformat(result[0])
                if current_expiry < datetime.now():
                    new_expiry = datetime.now() + timedelta(days=days)
                else:
                    new_expiry = current_expiry + timedelta(days=days)
            else:
                new_expiry = datetime.now() + timedelta(days=days)
            
            cursor.execute('''
                UPDATE users 
                SET expiry_date=?, payment_status='paid', active=1
                WHERE username=?
            ''', (new_expiry.isoformat(), username))
            conn.commit()
            conn.close()
            return True, f"✅ Subscription extended for {username} (+{days} days)"
        except Exception as e:
            return False, f"❌ Error: {str(e)}"
    
    def get_pending_users(self):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT username, email, created_at 
                FROM users 
                WHERE active=0 AND is_admin=0
            ''')
            users = cursor.fetchall()
            conn.close()
            result = {}
            for user in users:
                result[user[0]] = {"email": user[1], "created_at": user[2]}
            return result
        except:
            return {}
    
    def get_all_users(self):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT username, email, active, created_at, last_login, is_admin, payment_status, payment_date, expiry_date
                FROM users
            ''')
            users = cursor.fetchall()
            conn.close()
            result = {}
            for user in users:
                result[user[0]] = {
                    "email": user[1],
                    "active": bool(user[2]),
                    "created_at": user[3],
                    "last_login": user[4],
                    "is_admin": bool(user[5]),
                    "payment_status": user[6],
                    "payment_date": user[7],
                    "expiry_date": user[8]
                }
            return result
        except:
            return {}
    
    def is_admin(self, username):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT is_admin FROM users WHERE username=?", (username,))
            result = cursor.fetchone()
            conn.close()
            return result and result[0] == 1
        except:
            return False
    
    def get_user_data(self, username):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT username, email, active, created_at, last_login, is_admin, payment_status, payment_date, expiry_date
                FROM users WHERE username=?
            ''', (username,))
            user = cursor.fetchone()
            conn.close()
            if user:
                return {
                    "username": user[0],
                    "email": user[1],
                    "active": bool(user[2]),
                    "created_at": user[3],
                    "last_login": user[4],
                    "is_admin": bool(user[5]),
                    "payment_status": user[6],
                    "payment_date": user[7],
                    "expiry_date": user[8]
                }
            return None
        except:
            return None
    
    def get_users_count(self):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            total = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            active = cursor.execute("SELECT COUNT(*) FROM users WHERE active=1").fetchone()[0]
            pending = cursor.execute("SELECT COUNT(*) FROM users WHERE active=0 AND is_admin=0").fetchone()[0]
            admin = cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin=1").fetchone()[0]
            conn.close()
            return total, active, pending, admin
        except:
            return 0, 0, 0, 0

# ============================================
# 📊 Main Analyzer - Bybit Version
# ============================================

class CryptoAnalyzer:
    def __init__(self):
        self.blue_liquidity_lines = {}
        self.blue_liquidity_lines_15m = {}
        self.blue_liquidity_lines_5m = {}
        self.blue_liquidity_lines_1m = {}
        self.blue_liquidity_lines_4h = {}
        
        self.white_liquidity_levels = {}
        self.white_liquidity_levels_15m = {}
        self.white_liquidity_levels_5m = {}
        self.white_liquidity_levels_1m = {}
        self.white_liquidity_levels_4h = {}
        
        self.yellow_liquidation_zones = {}
        self.yellow_liquidation_zones_15m = {}
        self.yellow_liquidation_zones_5m = {}
        self.yellow_liquidation_zones_1m = {}
        self.yellow_liquidation_zones_4h = {}
        
        self.orange_magnetic_zones = {}
        self.orange_magnetic_zones_15m = {}
        self.orange_magnetic_zones_5m = {}
        self.orange_magnetic_zones_1m = {}
        self.orange_magnetic_zones_4h = {}
        
        self.trades_data = {}
        self.last_fetch_time = {}
        
    def _should_refresh(self, symbol):
        """التحقق إذا كان يجب تحديث البيانات (كل 2 دقيقة)"""
        now = time.time()
        if symbol not in self.last_fetch_time:
            self.last_fetch_time[symbol] = 0
        return (now - self.last_fetch_time[symbol]) > CACHE_DURATION_DATA
        
    def fetch_data(self, symbol):
        try:
            df_1h = fetch_candles_cached(symbol, '1h', MAX_CANDLES)
            time.sleep(0.3)
            df_4h = fetch_candles_cached(symbol, '4h', MAX_CANDLES // 2)
            
            if df_1h is not None:
                df_1h = calculate_indicators_cached(df_1h)
            if df_4h is not None:
                df_4h = calculate_indicators_cached(df_4h)
            
            # جلب بيانات الصفقات (حتى لو فشلت لا تؤثر)
            self.fetch_trades_data(symbol)
            
            if df_1h is not None:
                current_price = df_1h['close'].iloc[-1]
                self.calculate_blue_liquidity_lines(df_1h, current_price, symbol)
                self.calculate_white_liquidity_levels(df_1h, current_price, symbol)
                self.calculate_yellow_liquidation_zones(df_1h, symbol)
                self.calculate_orange_magnetic_zones(df_1h, current_price, symbol)
            
            if df_4h is not None:
                current_price_4h = df_4h['close'].iloc[-1]
                self.calculate_blue_liquidity_lines_4h(df_4h, current_price_4h, symbol)
                self.calculate_white_liquidity_levels_4h(df_4h, current_price_4h, symbol)
                self.calculate_yellow_liquidation_zones_4h(df_4h, symbol)
                self.calculate_orange_magnetic_zones_4h(df_4h, current_price_4h, symbol)
            
            self.last_fetch_time[symbol] = time.time()
            return df_1h, df_4h
            
        except Exception as e:
            st.error(f"Error fetching {symbol}: {str(e)}")
            return None, None
    
    def fetch_data_15m(self, symbol):
        try:
            df_15m = fetch_candles_cached(symbol, '15m', MAX_CANDLES)
            
            if df_15m is not None:
                df_15m = self.calculate_indicators_15m(df_15m)
                current_price_15m = df_15m['close'].iloc[-1]
                self.calculate_blue_liquidity_lines_15m(df_15m, current_price_15m, symbol)
                self.calculate_white_liquidity_levels_15m(df_15m, current_price_15m, symbol)
                self.calculate_yellow_liquidation_zones_15m(df_15m, symbol)
                self.calculate_orange_magnetic_zones_15m(df_15m, current_price_15m, symbol)
            
            return df_15m
            
        except Exception as e:
            st.error(f"Error fetching 15m for {symbol}: {str(e)}")
            return None
    
    def fetch_data_5m(self, symbol):
        try:
            df_5m = fetch_candles_cached(symbol, '5m', MAX_CANDLES)
            
            if df_5m is not None:
                df_5m = self.calculate_indicators_5m(df_5m)
                current_price_5m = df_5m['close'].iloc[-1]
                self.calculate_blue_liquidity_lines_5m(df_5m, current_price_5m, symbol)
                self.calculate_white_liquidity_levels_5m(df_5m, current_price_5m, symbol)
                self.calculate_yellow_liquidation_zones_5m(df_5m, symbol)
                self.calculate_orange_magnetic_zones_5m(df_5m, current_price_5m, symbol)
            
            return df_5m
            
        except Exception as e:
            st.error(f"Error fetching 5m for {symbol}: {str(e)}")
            return None
    
    def fetch_data_1m(self, symbol):
        try:
            df_1m = fetch_candles_cached(symbol, '1m', MAX_CANDLES)
            
            if df_1m is not None:
                df_1m = self.calculate_indicators_1m(df_1m)
                current_price_1m = df_1m['close'].iloc[-1]
                self.calculate_blue_liquidity_lines_1m(df_1m, current_price_1m, symbol)
                self.calculate_white_liquidity_levels_1m(df_1m, current_price_1m, symbol)
                self.calculate_yellow_liquidation_zones_1m(df_1m, symbol)
                self.calculate_orange_magnetic_zones_1m(df_1m, current_price_1m, symbol)
            
            return df_1m
            
        except Exception as e:
            st.error(f"Error fetching 1m for {symbol}: {str(e)}")
            return None
    
    def fetch_trades_data(self, symbol, limit=500):
        try:
            trades_df = fetch_trades_cached(symbol, limit)
            if trades_df is not None and not trades_df.empty:
                self.trades_data[symbol] = trades_df
        except Exception as e:
            # لا نعرض خطأ هنا لأنه لا يؤثر على التحليل الرئيسي
            pass
    
    def calculate_indicators_15m(self, df):
        if df.empty:
            return df
        
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        
        df['RSI'] = talib.RSI(close, timeperiod=14)
        df['MACD'], df['MACD_signal'], df['MACD_hist'] = talib.MACD(close)
        df['SMA_20'] = talib.SMA(close, timeperiod=20)
        df['EMA_50'] = talib.EMA(close, timeperiod=50)
        df['ATR'] = talib.ATR(high, low, close, timeperiod=14)
        df['BB_upper'], df['BB_middle'], df['BB_lower'] = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2)
        
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        df['VWAP'] = (df['volume'] * typical_price).cumsum() / df['volume'].cumsum()
        
        return df.dropna()
    
    def calculate_indicators_5m(self, df):
        if df.empty:
            return df
        
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        
        df['RSI'] = talib.RSI(close, timeperiod=14)
        df['MACD'], df['MACD_signal'], df['MACD_hist'] = talib.MACD(close)
        df['SMA_10'] = talib.SMA(close, timeperiod=10)
        df['SMA_20'] = talib.SMA(close, timeperiod=20)
        df['EMA_30'] = talib.EMA(close, timeperiod=30)
        df['ATR'] = talib.ATR(high, low, close, timeperiod=10)
        df['BB_upper'], df['BB_middle'], df['BB_lower'] = talib.BBANDS(close, timeperiod=20, nbdevup=1.5, nbdevdn=1.5)
        
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        df['VWAP'] = (df['volume'] * typical_price).cumsum() / df['volume'].cumsum()
        
        return df.dropna()
    
    def calculate_indicators_1m(self, df):
        if df.empty:
            return df
        
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        
        df['RSI'] = talib.RSI(close, timeperiod=7)
        df['MACD'], df['MACD_signal'], df['MACD_hist'] = talib.MACD(close, fastperiod=5, slowperiod=13, signalperiod=5)
        df['SMA_5'] = talib.SMA(close, timeperiod=5)
        df['SMA_10'] = talib.SMA(close, timeperiod=10)
        df['EMA_15'] = talib.EMA(close, timeperiod=15)
        df['ATR'] = talib.ATR(high, low, close, timeperiod=5)
        df['BB_upper'], df['BB_middle'], df['BB_lower'] = talib.BBANDS(close, timeperiod=20, nbdevup=1.2, nbdevdn=1.2)
        
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        df['VWAP'] = (df['volume'] * typical_price).cumsum() / df['volume'].cumsum()
        
        return df.dropna()
    
    # ======================
    # Orange Magnetic Zones
    # ======================
    def calculate_orange_magnetic_zones(self, df, current_price, symbol):
        orange_zones = []
        
        if df is None or len(df) < 100:
            self.orange_magnetic_zones[symbol] = orange_zones
            return
        
        try:
            close_prices = df['close'].values
            returns = np.diff(close_prices) / close_prices[:-1]
            price_velocity = np.mean(np.abs(returns[-20:])) * 100 if len(returns) >= 20 else 1
            
            turning_points = []
            for i in range(2, len(df)-2):
                if (df['high'].iloc[i] > df['high'].iloc[i-1] and 
                    df['high'].iloc[i] > df['high'].iloc[i+1] and
                    df['close'].iloc[i] > df['open'].iloc[i]):
                    turning_points.append(df['high'].iloc[i])
                
                if (df['low'].iloc[i] < df['low'].iloc[i-1] and 
                    df['low'].iloc[i] < df['low'].iloc[i+1] and
                    df['close'].iloc[i] < df['open'].iloc[i]):
                    turning_points.append(df['low'].iloc[i])
            
            if len(turning_points) < 5:
                self.orange_magnetic_zones[symbol] = orange_zones
                return
            
            turning_points = np.array(turning_points[-30:]).reshape(-1, 1) if len(turning_points) >= 30 else np.array(turning_points).reshape(-1, 1)
            
            if len(turning_points) >= 3:
                n_clusters = min(3, len(turning_points)//3)
                if n_clusters >= 1:
                    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
                    clusters = kmeans.fit_predict(turning_points)
                    
                    unique_clusters = np.unique(clusters)
                    for cluster_id in unique_clusters:
                        cluster_points = turning_points[clusters == cluster_id]
                        if len(cluster_points) >= 2:
                            center_price = np.mean(cluster_points)
                            points_density = len(cluster_points) / (np.std(cluster_points) + 1)
                            distance_pct = abs(center_price - current_price) / current_price * 100
                            strength = min(points_density / 10, 1.0) * (1 - distance_pct / 10)
                            
                            if center_price > current_price:
                                attraction_direction = "↑"
                            else:
                                attraction_direction = "↓"
                            
                            if distance_pct < price_velocity * 2:
                                orange_zones.append({
                                    'price': float(center_price),
                                    'type': 'magnetic_zone',
                                    'strength': float(strength),
                                    'distance_pct': distance_pct,
                                    'points_count': len(cluster_points),
                                    'attraction_direction': attraction_direction,
                                    'description': f'🧲 {attraction_direction}',
                                    'color': 'rgba(255, 165, 0, 0.5)',
                                    'width': 2 + strength * 2,
                                    'dash': 'dot' if strength < 0.5 else 'solid'
                                })
        except Exception as e:
            pass
        
        orange_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.orange_magnetic_zones[symbol] = orange_zones[:5]
    
    def calculate_orange_magnetic_zones_15m(self, df, current_price, symbol):
        orange_zones = []
        
        if df is None or len(df) < 100:
            self.orange_magnetic_zones_15m[symbol] = orange_zones
            return
        
        try:
            close_prices = df['close'].values
            returns = np.diff(close_prices) / close_prices[:-1]
            price_velocity = np.mean(np.abs(returns[-30:])) * 100 if len(returns) >= 30 else 1
            
            turning_points = []
            for i in range(2, len(df)-2):
                if (df['high'].iloc[i] > df['high'].iloc[i-1] and 
                    df['high'].iloc[i] > df['high'].iloc[i+1] and
                    df['close'].iloc[i] > df['open'].iloc[i]):
                    turning_points.append(df['high'].iloc[i])
                
                if (df['low'].iloc[i] < df['low'].iloc[i-1] and 
                    df['low'].iloc[i] < df['low'].iloc[i+1] and
                    df['close'].iloc[i] < df['open'].iloc[i]):
                    turning_points.append(df['low'].iloc[i])
            
            if len(turning_points) < 5:
                self.orange_magnetic_zones_15m[symbol] = orange_zones
                return
            
            turning_points = np.array(turning_points[-40:]).reshape(-1, 1) if len(turning_points) >= 40 else np.array(turning_points).reshape(-1, 1)
            
            if len(turning_points) >= 3:
                n_clusters = min(4, len(turning_points)//3)
                if n_clusters >= 1:
                    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
                    clusters = kmeans.fit_predict(turning_points)
                    
                    unique_clusters = np.unique(clusters)
                    for cluster_id in unique_clusters:
                        cluster_points = turning_points[clusters == cluster_id]
                        if len(cluster_points) >= 2:
                            center_price = np.mean(cluster_points)
                            points_density = len(cluster_points) / (np.std(cluster_points) + 1)
                            distance_pct = abs(center_price - current_price) / current_price * 100
                            strength = min(points_density / 10, 1.0) * (1 - distance_pct / 8)
                            
                            if center_price > current_price:
                                attraction_direction = "↑"
                            else:
                                attraction_direction = "↓"
                            
                            if distance_pct < price_velocity * 2:
                                orange_zones.append({
                                    'price': float(center_price),
                                    'type': 'magnetic_zone_15m',
                                    'strength': float(strength),
                                    'distance_pct': distance_pct,
                                    'points_count': len(cluster_points),
                                    'attraction_direction': attraction_direction,
                                    'description': f'🧲{attraction_direction}',
                                    'color': 'rgba(255, 165, 0, 0.5)',
                                    'width': 2 + strength * 2,
                                    'dash': 'dot' if strength < 0.5 else 'solid'
                                })
        except Exception as e:
            pass
        
        orange_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.orange_magnetic_zones_15m[symbol] = orange_zones[:5]
    
    def calculate_orange_magnetic_zones_5m(self, df, current_price, symbol):
        orange_zones = []
        
        if df is None or len(df) < 80:
            self.orange_magnetic_zones_5m[symbol] = orange_zones
            return
        
        try:
            close_prices = df['close'].values
            returns = np.diff(close_prices) / close_prices[:-1]
            price_velocity = np.mean(np.abs(returns[-40:])) * 100 if len(returns) >= 40 else 1
            
            turning_points = []
            for i in range(2, len(df)-2):
                if (df['high'].iloc[i] > df['high'].iloc[i-1] and 
                    df['high'].iloc[i] > df['high'].iloc[i+1] and
                    df['close'].iloc[i] > df['open'].iloc[i]):
                    turning_points.append(df['high'].iloc[i])
                
                if (df['low'].iloc[i] < df['low'].iloc[i-1] and 
                    df['low'].iloc[i] < df['low'].iloc[i+1] and
                    df['close'].iloc[i] < df['open'].iloc[i]):
                    turning_points.append(df['low'].iloc[i])
            
            if len(turning_points) < 5:
                self.orange_magnetic_zones_5m[symbol] = orange_zones
                return
            
            turning_points = np.array(turning_points[-50:]).reshape(-1, 1) if len(turning_points) >= 50 else np.array(turning_points).reshape(-1, 1)
            
            if len(turning_points) >= 3:
                n_clusters = min(5, len(turning_points)//3)
                if n_clusters >= 1:
                    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
                    clusters = kmeans.fit_predict(turning_points)
                    
                    unique_clusters = np.unique(clusters)
                    for cluster_id in unique_clusters:
                        cluster_points = turning_points[clusters == cluster_id]
                        if len(cluster_points) >= 2:
                            center_price = np.mean(cluster_points)
                            points_density = len(cluster_points) / (np.std(cluster_points) + 1)
                            distance_pct = abs(center_price - current_price) / current_price * 100
                            strength = min(points_density / 10, 1.0) * (1 - distance_pct / 5)
                            
                            if center_price > current_price:
                                attraction_direction = "↑"
                            else:
                                attraction_direction = "↓"
                            
                            if distance_pct < price_velocity * 2:
                                orange_zones.append({
                                    'price': float(center_price),
                                    'type': 'magnetic_zone_5m',
                                    'strength': float(strength),
                                    'distance_pct': distance_pct,
                                    'points_count': len(cluster_points),
                                    'attraction_direction': attraction_direction,
                                    'description': f'🧲{attraction_direction}',
                                    'color': 'rgba(255, 165, 0, 0.5)',
                                    'width': 2 + strength * 2,
                                    'dash': 'dot' if strength < 0.5 else 'solid'
                                })
        except Exception as e:
            pass
        
        orange_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.orange_magnetic_zones_5m[symbol] = orange_zones[:6]
    
    def calculate_orange_magnetic_zones_1m(self, df, current_price, symbol):
        orange_zones = []
        
        if df is None or len(df) < 60:
            self.orange_magnetic_zones_1m[symbol] = orange_zones
            return
        
        try:
            close_prices = df['close'].values
            returns = np.diff(close_prices) / close_prices[:-1]
            price_velocity = np.mean(np.abs(returns[-50:])) * 100 if len(returns) >= 50 else 1
            
            turning_points = []
            for i in range(2, len(df)-2):
                if (df['high'].iloc[i] > df['high'].iloc[i-1] and 
                    df['high'].iloc[i] > df['high'].iloc[i+1] and
                    df['close'].iloc[i] > df['open'].iloc[i]):
                    turning_points.append(df['high'].iloc[i])
                
                if (df['low'].iloc[i] < df['low'].iloc[i-1] and 
                    df['low'].iloc[i] < df['low'].iloc[i+1] and
                    df['close'].iloc[i] < df['open'].iloc[i]):
                    turning_points.append(df['low'].iloc[i])
            
            if len(turning_points) < 5:
                self.orange_magnetic_zones_1m[symbol] = orange_zones
                return
            
            turning_points = np.array(turning_points[-60:]).reshape(-1, 1) if len(turning_points) >= 60 else np.array(turning_points).reshape(-1, 1)
            
            if len(turning_points) >= 3:
                n_clusters = min(6, len(turning_points)//3)
                if n_clusters >= 1:
                    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
                    clusters = kmeans.fit_predict(turning_points)
                    
                    unique_clusters = np.unique(clusters)
                    for cluster_id in unique_clusters:
                        cluster_points = turning_points[clusters == cluster_id]
                        if len(cluster_points) >= 2:
                            center_price = np.mean(cluster_points)
                            points_density = len(cluster_points) / (np.std(cluster_points) + 1)
                            distance_pct = abs(center_price - current_price) / current_price * 100
                            strength = min(points_density / 10, 1.0) * (1 - distance_pct / 3)
                            
                            if center_price > current_price:
                                attraction_direction = "↑"
                            else:
                                attraction_direction = "↓"
                            
                            if distance_pct < price_velocity * 1.5:
                                orange_zones.append({
                                    'price': float(center_price),
                                    'type': 'magnetic_zone_1m',
                                    'strength': float(strength),
                                    'distance_pct': distance_pct,
                                    'points_count': len(cluster_points),
                                    'attraction_direction': attraction_direction,
                                    'description': f'🧲{attraction_direction}',
                                    'color': 'rgba(255, 165, 0, 0.5)',
                                    'width': 1.5 + strength * 2,
                                    'dash': 'dot' if strength < 0.5 else 'solid'
                                })
        except Exception as e:
            pass
        
        orange_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.orange_magnetic_zones_1m[symbol] = orange_zones[:7]
    
    def calculate_orange_magnetic_zones_4h(self, df, current_price, symbol):
        orange_zones = []
        
        if df is None or len(df) < 50:
            self.orange_magnetic_zones_4h[symbol] = orange_zones
            return
        
        try:
            close_prices = df['close'].values
            returns = np.diff(close_prices) / close_prices[:-1]
            price_velocity = np.mean(np.abs(returns[-15:])) * 100 if len(returns) >= 15 else 1
            
            turning_points = []
            for i in range(2, len(df)-2):
                if (df['high'].iloc[i] > df['high'].iloc[i-1] and 
                    df['high'].iloc[i] > df['high'].iloc[i+1] and
                    df['close'].iloc[i] > df['open'].iloc[i]):
                    turning_points.append(df['high'].iloc[i])
                
                if (df['low'].iloc[i] < df['low'].iloc[i-1] and 
                    df['low'].iloc[i] < df['low'].iloc[i+1] and
                    df['close'].iloc[i] < df['open'].iloc[i]):
                    turning_points.append(df['low'].iloc[i])
            
            if len(turning_points) < 5:
                self.orange_magnetic_zones_4h[symbol] = orange_zones
                return
            
            turning_points = np.array(turning_points[-20:]).reshape(-1, 1) if len(turning_points) >= 20 else np.array(turning_points).reshape(-1, 1)
            
            if len(turning_points) >= 3:
                n_clusters = min(3, len(turning_points)//3)
                if n_clusters >= 1:
                    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
                    clusters = kmeans.fit_predict(turning_points)
                    
                    unique_clusters = np.unique(clusters)
                    for cluster_id in unique_clusters:
                        cluster_points = turning_points[clusters == cluster_id]
                        if len(cluster_points) >= 2:
                            center_price = np.mean(cluster_points)
                            points_density = len(cluster_points) / (np.std(cluster_points) + 1)
                            distance_pct = abs(center_price - current_price) / current_price * 100
                            strength = min(points_density / 10, 1.0) * (1 - distance_pct / 15)
                            
                            if center_price > current_price:
                                attraction_direction = "↑"
                            else:
                                attraction_direction = "↓"
                            
                            if distance_pct < price_velocity * 2:
                                orange_zones.append({
                                    'price': float(center_price),
                                    'type': 'magnetic_zone_4h',
                                    'strength': float(strength),
                                    'distance_pct': distance_pct,
                                    'points_count': len(cluster_points),
                                    'attraction_direction': attraction_direction,
                                    'description': f'🧲{attraction_direction}',
                                    'color': 'rgba(255, 165, 0, 0.5)',
                                    'width': 2 + strength * 2,
                                    'dash': 'dot' if strength < 0.5 else 'solid'
                                })
        except Exception as e:
            pass
        
        orange_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.orange_magnetic_zones_4h[symbol] = orange_zones[:4]
    
    # ======================
    # Yellow Liquidation Zones
    # ======================
    def calculate_yellow_liquidation_zones(self, df, symbol):
        yellow_zones = []
        
        if df is None or len(df) < 50:
            self.yellow_liquidation_zones[symbol] = yellow_zones
            return
        
        try:
            current_price = df['close'].iloc[-1]
            
            if len(df) >= 100:
                high_idx = argrelextrema(df['high'].values, np.greater, order=10)[0]
                low_idx = argrelextrema(df['low'].values, np.less, order=10)[0]
                
                support_levels = []
                for idx in low_idx[-10:]:
                    price = df['low'].iloc[idx]
                    distance_pct = abs(price - current_price) / current_price * 100
                    if distance_pct <= 5:
                        touches = 0
                        for i in range(max(0, idx-5), min(len(df), idx+5)):
                            if abs(df['low'].iloc[i] - price) <= price * 0.005:
                                touches += 1
                        
                        strength = min(touches / 5, 1.0)
                        support_levels.append((price, strength))
                
                resistance_levels = []
                for idx in high_idx[-10:]:
                    price = df['high'].iloc[idx]
                    distance_pct = abs(price - current_price) / current_price * 100
                    if distance_pct <= 5:
                        touches = 0
                        for i in range(max(0, idx-5), min(len(df), idx+5)):
                            if abs(df['high'].iloc[i] - price) <= price * 0.005:
                                touches += 1
                        
                        strength = min(touches / 5, 1.0)
                        resistance_levels.append((price, strength))
                
                for price, strength in support_levels[:3]:
                    yellow_zones.append({
                        'price': price,
                        'type': 'support_zone',
                        'strength': strength,
                        'description': f'🟡 S ({strength:.2f})',
                        'color': '#FFFF00',
                        'width': 1 + (strength * 2),
                        'dash': 'dash',
                        'distance_pct': abs(price - current_price) / current_price * 100
                    })
                
                for price, strength in resistance_levels[:3]:
                    yellow_zones.append({
                        'price': price,
                        'type': 'resistance_zone',
                        'strength': strength,
                        'description': f'🟡 R ({strength:.2f})',
                        'color': '#FFFF00',
                        'width': 1 + (strength * 2),
                        'dash': 'dash',
                        'distance_pct': abs(price - current_price) / current_price * 100
                    })
        except Exception as e:
            pass
        
        yellow_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.yellow_liquidation_zones[symbol] = yellow_zones[:5]
    
    def calculate_yellow_liquidation_zones_15m(self, df, symbol):
        yellow_zones = []
        
        if df is None or len(df) < 50:
            self.yellow_liquidation_zones_15m[symbol] = yellow_zones
            return
        
        try:
            current_price = df['close'].iloc[-1]
            
            if len(df) >= 100:
                high_idx = argrelextrema(df['high'].values, np.greater, order=8)[0]
                low_idx = argrelextrema(df['low'].values, np.less, order=8)[0]
                
                support_levels = []
                for idx in low_idx[-15:]:
                    price = df['low'].iloc[idx]
                    distance_pct = abs(price - current_price) / current_price * 100
                    if distance_pct <= 3:
                        touches = 0
                        for i in range(max(0, idx-3), min(len(df), idx+3)):
                            if abs(df['low'].iloc[i] - price) <= price * 0.003:
                                touches += 1
                        
                        strength = min(touches / 3, 1.0)
                        support_levels.append((price, strength))
                
                resistance_levels = []
                for idx in high_idx[-15:]:
                    price = df['high'].iloc[idx]
                    distance_pct = abs(price - current_price) / current_price * 100
                    if distance_pct <= 3:
                        touches = 0
                        for i in range(max(0, idx-3), min(len(df), idx+3)):
                            if abs(df['high'].iloc[i] - price) <= price * 0.003:
                                touches += 1
                        
                        strength = min(touches / 3, 1.0)
                        resistance_levels.append((price, strength))
                
                for price, strength in support_levels[:4]:
                    yellow_zones.append({
                        'price': price,
                        'type': 'support_zone_15m',
                        'strength': strength,
                        'description': f'🟡 S15 ({strength:.2f})',
                        'color': '#FFFF00',
                        'width': 1 + (strength * 2),
                        'dash': 'dash',
                        'distance_pct': abs(price - current_price) / current_price * 100
                    })
                
                for price, strength in resistance_levels[:4]:
                    yellow_zones.append({
                        'price': price,
                        'type': 'resistance_zone_15m',
                        'strength': strength,
                        'description': f'🟡 R15 ({strength:.2f})',
                        'color': '#FFFF00',
                        'width': 1 + (strength * 2),
                        'dash': 'dash',
                        'distance_pct': abs(price - current_price) / current_price * 100
                    })
        except Exception as e:
            pass
        
        yellow_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.yellow_liquidation_zones_15m[symbol] = yellow_zones[:5]
    
    def calculate_yellow_liquidation_zones_5m(self, df, symbol):
        yellow_zones = []
        
        if df is None or len(df) < 30:
            self.yellow_liquidation_zones_5m[symbol] = yellow_zones
            return
        
        try:
            current_price = df['close'].iloc[-1]
            
            if len(df) >= 80:
                high_idx = argrelextrema(df['high'].values, np.greater, order=5)[0]
                low_idx = argrelextrema(df['low'].values, np.less, order=5)[0]
                
                support_levels = []
                for idx in low_idx[-20:]:
                    price = df['low'].iloc[idx]
                    distance_pct = abs(price - current_price) / current_price * 100
                    if distance_pct <= 2:
                        touches = 0
                        for i in range(max(0, idx-2), min(len(df), idx+2)):
                            if abs(df['low'].iloc[i] - price) <= price * 0.002:
                                touches += 1
                        
                        strength = min(touches / 2, 1.0)
                        support_levels.append((price, strength))
                
                resistance_levels = []
                for idx in high_idx[-20:]:
                    price = df['high'].iloc[idx]
                    distance_pct = abs(price - current_price) / current_price * 100
                    if distance_pct <= 2:
                        touches = 0
                        for i in range(max(0, idx-2), min(len(df), idx+2)):
                            if abs(df['high'].iloc[i] - price) <= price * 0.002:
                                touches += 1
                        
                        strength = min(touches / 2, 1.0)
                        resistance_levels.append((price, strength))
                
                for price, strength in support_levels[:5]:
                    yellow_zones.append({
                        'price': price,
                        'type': 'support_zone_5m',
                        'strength': strength,
                        'description': f'🟡 S5 ({strength:.2f})',
                        'color': '#FFFF00',
                        'width': 1 + (strength * 2),
                        'dash': 'dash',
                        'distance_pct': abs(price - current_price) / current_price * 100
                    })
                
                for price, strength in resistance_levels[:5]:
                    yellow_zones.append({
                        'price': price,
                        'type': 'resistance_zone_5m',
                        'strength': strength,
                        'description': f'🟡 R5 ({strength:.2f})',
                        'color': '#FFFF00',
                        'width': 1 + (strength * 2),
                        'dash': 'dash',
                        'distance_pct': abs(price - current_price) / current_price * 100
                    })
        except Exception as e:
            pass
        
        yellow_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.yellow_liquidation_zones_5m[symbol] = yellow_zones[:6]
    
    def calculate_yellow_liquidation_zones_1m(self, df, symbol):
        yellow_zones = []
        
        if df is None or len(df) < 30:
            self.yellow_liquidation_zones_1m[symbol] = yellow_zones
            return
        
        try:
            current_price = df['close'].iloc[-1]
            
            if len(df) >= 60:
                high_idx = argrelextrema(df['high'].values, np.greater, order=3)[0]
                low_idx = argrelextrema(df['low'].values, np.less, order=3)[0]
                
                support_levels = []
                for idx in low_idx[-25:]:
                    price = df['low'].iloc[idx]
                    distance_pct = abs(price - current_price) / current_price * 100
                    if distance_pct <= 1.5:
                        touches = 0
                        for i in range(max(0, idx-1), min(len(df), idx+2)):
                            if abs(df['low'].iloc[i] - price) <= price * 0.0015:
                                touches += 1
                        
                        strength = min(touches / 2, 1.0)
                        support_levels.append((price, strength))
                
                resistance_levels = []
                for idx in high_idx[-25:]:
                    price = df['high'].iloc[idx]
                    distance_pct = abs(price - current_price) / current_price * 100
                    if distance_pct <= 1.5:
                        touches = 0
                        for i in range(max(0, idx-1), min(len(df), idx+2)):
                            if abs(df['high'].iloc[i] - price) <= price * 0.0015:
                                touches += 1
                        
                        strength = min(touches / 2, 1.0)
                        resistance_levels.append((price, strength))
                
                for price, strength in support_levels[:6]:
                    yellow_zones.append({
                        'price': price,
                        'type': 'support_zone_1m',
                        'strength': strength,
                        'description': f'🟡 S1 ({strength:.2f})',
                        'color': '#FFFF00',
                        'width': 1 + (strength * 1.5),
                        'dash': 'dash',
                        'distance_pct': abs(price - current_price) / current_price * 100
                    })
                
                for price, strength in resistance_levels[:6]:
                    yellow_zones.append({
                        'price': price,
                        'type': 'resistance_zone_1m',
                        'strength': strength,
                        'description': f'🟡 R1 ({strength:.2f})',
                        'color': '#FFFF00',
                        'width': 1 + (strength * 1.5),
                        'dash': 'dash',
                        'distance_pct': abs(price - current_price) / current_price * 100
                    })
        except Exception as e:
            pass
        
        yellow_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.yellow_liquidation_zones_1m[symbol] = yellow_zones[:8]
    
    def calculate_yellow_liquidation_zones_4h(self, df, symbol):
        yellow_zones = []
        
        if df is None or len(df) < 50:
            self.yellow_liquidation_zones_4h[symbol] = yellow_zones
            return
        
        try:
            current_price = df['close'].iloc[-1]
            
            if len(df) >= 100:
                high_idx = argrelextrema(df['high'].values, np.greater, order=15)[0]
                low_idx = argrelextrema(df['low'].values, np.less, order=15)[0]
                
                support_levels = []
                for idx in low_idx[-8:]:
                    price = df['low'].iloc[idx]
                    distance_pct = abs(price - current_price) / current_price * 100
                    if distance_pct <= 8:
                        touches = 0
                        for i in range(max(0, idx-3), min(len(df), idx+3)):
                            if abs(df['low'].iloc[i] - price) <= price * 0.008:
                                touches += 1
                        
                        strength = min(touches / 3, 1.0)
                        support_levels.append((price, strength))
                
                resistance_levels = []
                for idx in high_idx[-8:]:
                    price = df['high'].iloc[idx]
                    distance_pct = abs(price - current_price) / current_price * 100
                    if distance_pct <= 8:
                        touches = 0
                        for i in range(max(0, idx-3), min(len(df), idx+3)):
                            if abs(df['high'].iloc[i] - price) <= price * 0.008:
                                touches += 1
                        
                        strength = min(touches / 3, 1.0)
                        resistance_levels.append((price, strength))
                
                for price, strength in support_levels[:3]:
                    yellow_zones.append({
                        'price': price,
                        'type': 'support_zone_4h',
                        'strength': strength,
                        'description': f'🟡 S4h ({strength:.2f})',
                        'color': '#FFFF00',
                        'width': 1 + (strength * 2),
                        'dash': 'dash',
                        'distance_pct': abs(price - current_price) / current_price * 100
                    })
                
                for price, strength in resistance_levels[:3]:
                    yellow_zones.append({
                        'price': price,
                        'type': 'resistance_zone_4h',
                        'strength': strength,
                        'description': f'🟡 R4h ({strength:.2f})',
                        'color': '#FFFF00',
                        'width': 1 + (strength * 2),
                        'dash': 'dash',
                        'distance_pct': abs(price - current_price) / current_price * 100
                    })
        except Exception as e:
            pass
        
        yellow_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.yellow_liquidation_zones_4h[symbol] = yellow_zones[:5]
    
    # ======================
    # Blue Liquidity Lines
    # ======================
    def calculate_blue_liquidity_lines(self, df_1h, current_price, symbol):
        blue_lines = []
        
        if df_1h is None or len(df_1h) < 50:
            self.blue_liquidity_lines[symbol] = blue_lines
            return
        
        try:
            for i in range(max(0, len(df_1h)-20), len(df_1h)-1):
                candle = df_1h.iloc[i]
                next_candle = df_1h.iloc[i+1]
                
                upper_wick = candle['high'] - max(candle['open'], candle['close'])
                lower_wick = min(candle['open'], candle['close']) - candle['low']
                body_size = abs(candle['close'] - candle['open'])
                total_range = candle['high'] - candle['low']
                
                if total_range == 0:
                    continue
                
                if (lower_wick > body_size * 2 and 
                    upper_wick < body_size * 0.5 and
                    next_candle['close'] > candle['close']):
                    
                    blue_lines.append({
                        'price': candle['low'],
                        'type': 'buy_liquidity',
                        'strength': min(0.8 + (lower_wick/total_range), 0.95),
                        'timeframe': 'immediate',
                        'description': '🔵 B',
                        'color': '#1E90FF',
                        'width': 2 + (lower_wick/total_range * 3),
                        'dash': 'solid'
                    })
                
                if (upper_wick > body_size * 2 and 
                    lower_wick < body_size * 0.5 and
                    next_candle['close'] < candle['close']):
                    
                    blue_lines.append({
                        'price': candle['high'],
                        'type': 'sell_liquidity',
                        'strength': min(0.8 + (upper_wick/total_range), 0.95),
                        'timeframe': 'immediate',
                        'description': '🔵 S',
                        'color': '#1E90FF',
                        'width': 2 + (upper_wick/total_range * 3),
                        'dash': 'solid'
                    })
            
            lookback = min(50, len(df_1h))
            price_tolerance = current_price * 0.02
            
            local_highs = []
            for i in range(1, lookback-1):
                if (df_1h['high'].iloc[i] > df_1h['high'].iloc[i-1] and 
                    df_1h['high'].iloc[i] > df_1h['high'].iloc[i+1]):
                    local_highs.append(df_1h['high'].iloc[i])
            
            local_lows = []
            for i in range(1, lookback-1):
                if (df_1h['low'].iloc[i] < df_1h['low'].iloc[i-1] and 
                    df_1h['low'].iloc[i] < df_1h['low'].iloc[i+1]):
                    local_lows.append(df_1h['low'].iloc[i])
            
            for high_price in local_highs[:5]:
                if abs(high_price - current_price) <= price_tolerance:
                    blue_lines.append({
                        'price': high_price,
                        'type': 'sell_liquidity',
                        'strength': 0.7,
                        'timeframe': 'near',
                        'description': '🔵 R',
                        'color': '#00BFFF',
                        'width': 2,
                        'dash': 'dash'
                    })
            
            for low_price in local_lows[:5]:
                if abs(low_price - current_price) <= price_tolerance:
                    blue_lines.append({
                        'price': low_price,
                        'type': 'buy_liquidity',
                        'strength': 0.7,
                        'timeframe': 'near',
                        'description': '🔵 S',
                        'color': '#00BFFF',
                        'width': 2,
                        'dash': 'dash'
                    })
        except Exception as e:
            pass
        
        unique_lines = []
        seen_prices = set()
        for line in blue_lines:
            if line['price'] not in seen_prices:
                seen_prices.add(line['price'])
                unique_lines.append(line)
        
        self.blue_liquidity_lines[symbol] = unique_lines
    
    def calculate_blue_liquidity_lines_15m(self, df_15m, current_price, symbol):
        blue_lines = []
        
        if df_15m is None or len(df_15m) < 50:
            self.blue_liquidity_lines_15m[symbol] = blue_lines
            return
        
        try:
            for i in range(max(0, len(df_15m)-30), len(df_15m)-1):
                candle = df_15m.iloc[i]
                next_candle = df_15m.iloc[i+1]
                
                upper_wick = candle['high'] - max(candle['open'], candle['close'])
                lower_wick = min(candle['open'], candle['close']) - candle['low']
                body_size = abs(candle['close'] - candle['open'])
                total_range = candle['high'] - candle['low']
                
                if total_range == 0:
                    continue
                
                if (lower_wick > body_size * 2 and 
                    upper_wick < body_size * 0.3 and
                    next_candle['close'] > candle['close']):
                    
                    blue_lines.append({
                        'price': candle['low'],
                        'type': 'buy_liquidity_15m',
                        'strength': min(0.8 + (lower_wick/total_range), 0.95),
                        'timeframe': 'immediate_15m',
                        'description': '🔵 B15',
                        'color': '#1E90FF',
                        'width': 2 + (lower_wick/total_range * 3),
                        'dash': 'solid'
                    })
                
                if (upper_wick > body_size * 2 and 
                    lower_wick < body_size * 0.3 and
                    next_candle['close'] < candle['close']):
                    
                    blue_lines.append({
                        'price': candle['high'],
                        'type': 'sell_liquidity_15m',
                        'strength': min(0.8 + (upper_wick/total_range), 0.95),
                        'timeframe': 'immediate_15m',
                        'description': '🔵 S15',
                        'color': '#1E90FF',
                        'width': 2 + (upper_wick/total_range * 3),
                        'dash': 'solid'
                    })
            
            lookback = min(80, len(df_15m))
            price_tolerance = current_price * 0.01
            
            local_highs = []
            for i in range(1, lookback-1):
                if (df_15m['high'].iloc[i] > df_15m['high'].iloc[i-1] and 
                    df_15m['high'].iloc[i] > df_15m['high'].iloc[i+1]):
                    local_highs.append(df_15m['high'].iloc[i])
            
            local_lows = []
            for i in range(1, lookback-1):
                if (df_15m['low'].iloc[i] < df_15m['low'].iloc[i-1] and 
                    df_15m['low'].iloc[i] < df_15m['low'].iloc[i+1]):
                    local_lows.append(df_15m['low'].iloc[i])
            
            for high_price in local_highs[:8]:
                if abs(high_price - current_price) <= price_tolerance:
                    blue_lines.append({
                        'price': high_price,
                        'type': 'sell_liquidity_15m',
                        'strength': 0.7,
                        'timeframe': 'near_15m',
                        'description': '🔵 R15',
                        'color': '#00BFFF',
                        'width': 2,
                        'dash': 'dash'
                    })
            
            for low_price in local_lows[:8]:
                if abs(low_price - current_price) <= price_tolerance:
                    blue_lines.append({
                        'price': low_price,
                        'type': 'buy_liquidity_15m',
                        'strength': 0.7,
                        'timeframe': 'near_15m',
                        'description': '🔵 S15',
                        'color': '#00BFFF',
                        'width': 2,
                        'dash': 'dash'
                    })
        except Exception as e:
            pass
        
        unique_lines = []
        seen_prices = set()
        for line in blue_lines:
            if line['price'] not in seen_prices:
                seen_prices.add(line['price'])
                unique_lines.append(line)
        
        self.blue_liquidity_lines_15m[symbol] = unique_lines
    
    def calculate_blue_liquidity_lines_5m(self, df_5m, current_price, symbol):
        blue_lines = []
        
        if df_5m is None or len(df_5m) < 30:
            self.blue_liquidity_lines_5m[symbol] = blue_lines
            return
        
        try:
            for i in range(max(0, len(df_5m)-40), len(df_5m)-1):
                candle = df_5m.iloc[i]
                next_candle = df_5m.iloc[i+1]
                
                upper_wick = candle['high'] - max(candle['open'], candle['close'])
                lower_wick = min(candle['open'], candle['close']) - candle['low']
                body_size = abs(candle['close'] - candle['open'])
                total_range = candle['high'] - candle['low']
                
                if total_range == 0:
                    continue
                
                if (lower_wick > body_size * 1.8 and 
                    upper_wick < body_size * 0.4 and
                    next_candle['close'] > candle['close']):
                    
                    blue_lines.append({
                        'price': candle['low'],
                        'type': 'buy_liquidity_5m',
                        'strength': min(0.8 + (lower_wick/total_range), 0.95),
                        'timeframe': 'immediate_5m',
                        'description': '🔵 B5',
                        'color': '#1E90FF',
                        'width': 2 + (lower_wick/total_range * 3),
                        'dash': 'solid'
                    })
                
                if (upper_wick > body_size * 1.8 and 
                    lower_wick < body_size * 0.4 and
                    next_candle['close'] < candle['close']):
                    
                    blue_lines.append({
                        'price': candle['high'],
                        'type': 'sell_liquidity_5m',
                        'strength': min(0.8 + (upper_wick/total_range), 0.95),
                        'timeframe': 'immediate_5m',
                        'description': '🔵 S5',
                        'color': '#1E90FF',
                        'width': 2 + (upper_wick/total_range * 3),
                        'dash': 'solid'
                    })
            
            lookback = min(100, len(df_5m))
            price_tolerance = current_price * 0.005
            
            local_highs = []
            for i in range(2, lookback-2):
                if (df_5m['high'].iloc[i] > df_5m['high'].iloc[i-1] and 
                    df_5m['high'].iloc[i] > df_5m['high'].iloc[i-2] and
                    df_5m['high'].iloc[i] > df_5m['high'].iloc[i+1] and
                    df_5m['high'].iloc[i] > df_5m['high'].iloc[i+2]):
                    local_highs.append(df_5m['high'].iloc[i])
            
            local_lows = []
            for i in range(2, lookback-2):
                if (df_5m['low'].iloc[i] < df_5m['low'].iloc[i-1] and 
                    df_5m['low'].iloc[i] < df_5m['low'].iloc[i-2] and
                    df_5m['low'].iloc[i] < df_5m['low'].iloc[i+1] and
                    df_5m['low'].iloc[i] < df_5m['low'].iloc[i+2]):
                    local_lows.append(df_5m['low'].iloc[i])
            
            for high_price in local_highs[:10]:
                if abs(high_price - current_price) <= price_tolerance:
                    blue_lines.append({
                        'price': high_price,
                        'type': 'sell_liquidity_5m',
                        'strength': 0.7,
                        'timeframe': 'near_5m',
                        'description': '🔵 R5',
                        'color': '#00BFFF',
                        'width': 2,
                        'dash': 'dash'
                    })
            
            for low_price in local_lows[:10]:
                if abs(low_price - current_price) <= price_tolerance:
                    blue_lines.append({
                        'price': low_price,
                        'type': 'buy_liquidity_5m',
                        'strength': 0.7,
                        'timeframe': 'near_5m',
                        'description': '🔵 S5',
                        'color': '#00BFFF',
                        'width': 2,
                        'dash': 'dash'
                    })
        except Exception as e:
            pass
        
        unique_lines = []
        seen_prices = set()
        for line in blue_lines:
            if line['price'] not in seen_prices:
                seen_prices.add(line['price'])
                unique_lines.append(line)
        
        self.blue_liquidity_lines_5m[symbol] = unique_lines
    
    def calculate_blue_liquidity_lines_1m(self, df_1m, current_price, symbol):
        blue_lines = []
        
        if df_1m is None or len(df_1m) < 30:
            self.blue_liquidity_lines_1m[symbol] = blue_lines
            return
        
        try:
            for i in range(max(0, len(df_1m)-50), len(df_1m)-1):
                candle = df_1m.iloc[i]
                next_candle = df_1m.iloc[i+1]
                
                upper_wick = candle['high'] - max(candle['open'], candle['close'])
                lower_wick = min(candle['open'], candle['close']) - candle['low']
                body_size = abs(candle['close'] - candle['open'])
                total_range = candle['high'] - candle['low']
                
                if total_range == 0:
                    continue
                
                if (lower_wick > body_size * 1.5 and 
                    upper_wick < body_size * 0.5 and
                    next_candle['close'] > candle['close']):
                    
                    blue_lines.append({
                        'price': candle['low'],
                        'type': 'buy_liquidity_1m',
                        'strength': min(0.7 + (lower_wick/total_range), 0.9),
                        'timeframe': 'immediate_1m',
                        'description': '🔵 B1',
                        'color': '#1E90FF',
                        'width': 1.5 + (lower_wick/total_range * 2),
                        'dash': 'solid'
                    })
                
                if (upper_wick > body_size * 1.5 and 
                    lower_wick < body_size * 0.5 and
                    next_candle['close'] < candle['close']):
                    
                    blue_lines.append({
                        'price': candle['high'],
                        'type': 'sell_liquidity_1m',
                        'strength': min(0.7 + (upper_wick/total_range), 0.9),
                        'timeframe': 'immediate_1m',
                        'description': '🔵 S1',
                        'color': '#1E90FF',
                        'width': 1.5 + (upper_wick/total_range * 2),
                        'dash': 'solid'
                    })
            
            lookback = min(120, len(df_1m))
            price_tolerance = current_price * 0.0025
            
            local_highs = []
            for i in range(2, lookback-2):
                if (df_1m['high'].iloc[i] > df_1m['high'].iloc[i-1] and 
                    df_1m['high'].iloc[i] > df_1m['high'].iloc[i+1]):
                    local_highs.append(df_1m['high'].iloc[i])
            
            local_lows = []
            for i in range(2, lookback-2):
                if (df_1m['low'].iloc[i] < df_1m['low'].iloc[i-1] and 
                    df_1m['low'].iloc[i] < df_1m['low'].iloc[i+1]):
                    local_lows.append(df_1m['low'].iloc[i])
            
            for high_price in local_highs[:12]:
                if abs(high_price - current_price) <= price_tolerance:
                    blue_lines.append({
                        'price': high_price,
                        'type': 'sell_liquidity_1m',
                        'strength': 0.65,
                        'timeframe': 'near_1m',
                        'description': '🔵 R1',
                        'color': '#00BFFF',
                        'width': 1.8,
                        'dash': 'dash'
                    })
            
            for low_price in local_lows[:12]:
                if abs(low_price - current_price) <= price_tolerance:
                    blue_lines.append({
                        'price': low_price,
                        'type': 'buy_liquidity_1m',
                        'strength': 0.65,
                        'timeframe': 'near_1m',
                        'description': '🔵 S1',
                        'color': '#00BFFF',
                        'width': 1.8,
                        'dash': 'dash'
                    })
        except Exception as e:
            pass
        
        unique_lines = []
        seen_prices = set()
        for line in blue_lines:
            if line['price'] not in seen_prices:
                seen_prices.add(line['price'])
                unique_lines.append(line)
        
        self.blue_liquidity_lines_1m[symbol] = unique_lines
    
    def calculate_blue_liquidity_lines_4h(self, df_4h, current_price, symbol):
        blue_lines = []
        
        if df_4h is None or len(df_4h) < 30:
            self.blue_liquidity_lines_4h[symbol] = blue_lines
            return
        
        try:
            for i in range(max(0, len(df_4h)-15), len(df_4h)-1):
                candle = df_4h.iloc[i]
                next_candle = df_4h.iloc[i+1]
                
                upper_wick = candle['high'] - max(candle['open'], candle['close'])
                lower_wick = min(candle['open'], candle['close']) - candle['low']
                body_size = abs(candle['close'] - candle['open'])
                total_range = candle['high'] - candle['low']
                
                if total_range == 0:
                    continue
                
                if (lower_wick > body_size * 2 and 
                    upper_wick < body_size * 0.5 and
                    next_candle['close'] > candle['close']):
                    
                    blue_lines.append({
                        'price': candle['low'],
                        'type': 'buy_liquidity_4h',
                        'strength': min(0.8 + (lower_wick/total_range), 0.95),
                        'timeframe': 'immediate_4h',
                        'description': '🔵 B4h',
                        'color': '#1E90FF',
                        'width': 2 + (lower_wick/total_range * 3),
                        'dash': 'solid'
                    })
                
                if (upper_wick > body_size * 2 and 
                    lower_wick < body_size * 0.5 and
                    next_candle['close'] < candle['close']):
                    
                    blue_lines.append({
                        'price': candle['high'],
                        'type': 'sell_liquidity_4h',
                        'strength': min(0.8 + (upper_wick/total_range), 0.95),
                        'timeframe': 'immediate_4h',
                        'description': '🔵 S4h',
                        'color': '#1E90FF',
                        'width': 2 + (upper_wick/total_range * 3),
                        'dash': 'solid'
                    })
            
            lookback = min(30, len(df_4h))
            price_tolerance = current_price * 0.03
            
            local_highs = []
            for i in range(1, lookback-1):
                if (df_4h['high'].iloc[i] > df_4h['high'].iloc[i-1] and 
                    df_4h['high'].iloc[i] > df_4h['high'].iloc[i+1]):
                    local_highs.append(df_4h['high'].iloc[i])
            
            local_lows = []
            for i in range(1, lookback-1):
                if (df_4h['low'].iloc[i] < df_4h['low'].iloc[i-1] and 
                    df_4h['low'].iloc[i] < df_4h['low'].iloc[i+1]):
                    local_lows.append(df_4h['low'].iloc[i])
            
            for high_price in local_highs[:5]:
                if abs(high_price - current_price) <= price_tolerance:
                    blue_lines.append({
                        'price': high_price,
                        'type': 'sell_liquidity_4h',
                        'strength': 0.7,
                        'timeframe': 'near_4h',
                        'description': '🔵 R4h',
                        'color': '#00BFFF',
                        'width': 2,
                        'dash': 'dash'
                    })
            
            for low_price in local_lows[:5]:
                if abs(low_price - current_price) <= price_tolerance:
                    blue_lines.append({
                        'price': low_price,
                        'type': 'buy_liquidity_4h',
                        'strength': 0.7,
                        'timeframe': 'near_4h',
                        'description': '🔵 S4h',
                        'color': '#00BFFF',
                        'width': 2,
                        'dash': 'dash'
                    })
        except Exception as e:
            pass
        
        unique_lines = []
        seen_prices = set()
        for line in blue_lines:
            if line['price'] not in seen_prices:
                seen_prices.add(line['price'])
                unique_lines.append(line)
        
        self.blue_liquidity_lines_4h[symbol] = unique_lines
    
    # ======================
    # White Liquidity Levels
    # ======================
    def calculate_white_liquidity_levels(self, df_1h, current_price, symbol):
        white_levels = []
        
        if df_1h is None:
            self.white_liquidity_levels[symbol] = white_levels
            return
        
        try:
            support, resistance = self.find_strong_support_resistance(df_1h, window=12)
            
            for price, strength in support[:3]:
                if strength > 0.7:
                    distance_pct = abs(price - current_price) / current_price * 100
                    if distance_pct <= 5:
                        white_levels.append({
                            'price': price,
                            'type': 'strong_support',
                            'strength': strength,
                            'description': f'⚪ S ({strength:.2f})',
                            'color': 'white',
                            'width': 1 + (strength * 2),
                            'dash': 'dash'
                        })
            
            for price, strength in resistance[:3]:
                if strength > 0.7:
                    distance_pct = abs(price - current_price) / current_price * 100
                    if distance_pct <= 5:
                        white_levels.append({
                            'price': price,
                            'type': 'strong_resistance',
                            'strength': strength,
                            'description': f'⚪ R ({strength:.2f})',
                            'color': 'white',
                            'width': 1 + (strength * 2),
                            'dash': 'dash'
                        })
        except Exception as e:
            pass
        
        self.white_liquidity_levels[symbol] = white_levels
    
    def calculate_white_liquidity_levels_15m(self, df_15m, current_price, symbol):
        white_levels = []
        
        if df_15m is None:
            self.white_liquidity_levels_15m[symbol] = white_levels
            return
        
        try:
            support, resistance = self.find_strong_support_resistance_15m(df_15m, window=15)
            
            for price, strength in support[:4]:
                if strength > 0.6:
                    distance_pct = abs(price - current_price) / current_price * 100
                    if distance_pct <= 3:
                        white_levels.append({
                            'price': price,
                            'type': 'strong_support_15m',
                            'strength': strength,
                            'description': f'⚪ S15 ({strength:.2f})',
                            'color': 'white',
                            'width': 1 + (strength * 2),
                            'dash': 'dash'
                        })
            
            for price, strength in resistance[:4]:
                if strength > 0.6:
                    distance_pct = abs(price - current_price) / current_price * 100
                    if distance_pct <= 3:
                        white_levels.append({
                            'price': price,
                            'type': 'strong_resistance_15m',
                            'strength': strength,
                            'description': f'⚪ R15 ({strength:.2f})',
                            'color': 'white',
                            'width': 1 + (strength * 2),
                            'dash': 'dash'
                        })
        except Exception as e:
            pass
        
        self.white_liquidity_levels_15m[symbol] = white_levels
    
    def calculate_white_liquidity_levels_5m(self, df_5m, current_price, symbol):
        white_levels = []
        
        if df_5m is None:
            self.white_liquidity_levels_5m[symbol] = white_levels
            return
        
        try:
            support, resistance = self.find_strong_support_resistance_5m(df_5m, window=10)
            
            for price, strength in support[:5]:
                if strength > 0.55:
                    distance_pct = abs(price - current_price) / current_price * 100
                    if distance_pct <= 2:
                        white_levels.append({
                            'price': price,
                            'type': 'strong_support_5m',
                            'strength': strength,
                            'description': f'⚪ S5 ({strength:.2f})',
                            'color': 'white',
                            'width': 1 + (strength * 2),
                            'dash': 'dash'
                        })
            
            for price, strength in resistance[:5]:
                if strength > 0.55:
                    distance_pct = abs(price - current_price) / current_price * 100
                    if distance_pct <= 2:
                        white_levels.append({
                            'price': price,
                            'type': 'strong_resistance_5m',
                            'strength': strength,
                            'description': f'⚪ R5 ({strength:.2f})',
                            'color': 'white',
                            'width': 1 + (strength * 2),
                            'dash': 'dash'
                        })
        except Exception as e:
            pass
        
        self.white_liquidity_levels_5m[symbol] = white_levels
    
    def calculate_white_liquidity_levels_1m(self, df_1m, current_price, symbol):
        white_levels = []
        
        if df_1m is None:
            self.white_liquidity_levels_1m[symbol] = white_levels
            return
        
        try:
            support, resistance = self.find_strong_support_resistance_1m(df_1m, window=7)
            
            for price, strength in support[:6]:
                if strength > 0.5:
                    distance_pct = abs(price - current_price) / current_price * 100
                    if distance_pct <= 1.5:
                        white_levels.append({
                            'price': price,
                            'type': 'strong_support_1m',
                            'strength': strength,
                            'description': f'⚪ S1 ({strength:.2f})',
                            'color': 'white',
                            'width': 1 + (strength * 1.5),
                            'dash': 'dash'
                        })
            
            for price, strength in resistance[:6]:
                if strength > 0.5:
                    distance_pct = abs(price - current_price) / current_price * 100
                    if distance_pct <= 1.5:
                        white_levels.append({
                            'price': price,
                            'type': 'strong_resistance_1m',
                            'strength': strength,
                            'description': f'⚪ R1 ({strength:.2f})',
                            'color': 'white',
                            'width': 1 + (strength * 1.5),
                            'dash': 'dash'
                        })
        except Exception as e:
            pass
        
        self.white_liquidity_levels_1m[symbol] = white_levels
    
    def calculate_white_liquidity_levels_4h(self, df_4h, current_price, symbol):
        white_levels = []
        
        if df_4h is None:
            self.white_liquidity_levels_4h[symbol] = white_levels
            return
        
        try:
            support, resistance = self.find_strong_support_resistance(df_4h, window=20)
            
            for price, strength in support[:3]:
                if strength > 0.7:
                    distance_pct = abs(price - current_price) / current_price * 100
                    if distance_pct <= 8:
                        white_levels.append({
                            'price': price,
                            'type': 'strong_support_4h',
                            'strength': strength,
                            'description': f'⚪ S4h ({strength:.2f})',
                            'color': 'white',
                            'width': 1 + (strength * 2),
                            'dash': 'dash'
                        })
            
            for price, strength in resistance[:3]:
                if strength > 0.7:
                    distance_pct = abs(price - current_price) / current_price * 100
                    if distance_pct <= 8:
                        white_levels.append({
                            'price': price,
                            'type': 'strong_resistance_4h',
                            'strength': strength,
                            'description': f'⚪ R4h ({strength:.2f})',
                            'color': 'white',
                            'width': 1 + (strength * 2),
                            'dash': 'dash'
                        })
        except Exception as e:
            pass
        
        self.white_liquidity_levels_4h[symbol] = white_levels
    
    # ======================
    # Find Support/Resistance
    # ======================
    def find_strong_support_resistance(self, df, window=20):
        if len(df) < window * 2:
            return [], []
        
        try:
            high_idx = argrelextrema(df['high'].values, np.greater, order=window)[0]
            low_idx = argrelextrema(df['low'].values, np.less, order=window)[0]
            
            def cluster_and_score(levels, price_data, is_support=True):
                if len(levels) == 0:
                    return []
                
                eps_value = np.std(levels) * 0.5
                if eps_value <= 0:
                    eps_value = np.mean(levels) * 0.005
                eps_value = max(eps_value, np.mean(levels) * 0.001)
                
                levels_array = np.array(levels).reshape(-1, 1)
                
                try:
                    db = DBSCAN(eps=float(eps_value), min_samples=2).fit(levels_array)
                    labels = db.labels_
                except Exception as e:
                    labels = np.zeros(len(levels))
                
                clusters = {}
                for i, label in enumerate(labels):
                    if label not in clusters:
                        clusters[label] = []
                    clusters[label].append(levels[i])
                
                scored_clusters = []
                for label, cluster in clusters.items():
                    if label != -1:
                        avg_price = np.mean(cluster)
                        
                        if is_support:
                            touches = len(price_data[
                                (price_data['low'] <= avg_price * 1.005) & 
                                (price_data['low'] >= avg_price * 0.995)
                            ])
                        else:
                            touches = len(price_data[
                                (price_data['high'] >= avg_price * 0.995) & 
                                (price_data['high'] <= avg_price * 1.005)
                            ])
                        
                        volume_mask = (price_data['close'] >= avg_price * 0.99) & (price_data['close'] <= avg_price * 1.01)
                        volume_score = price_data.loc[volume_mask, 'volume'].mean() / price_data['volume'].mean() if not price_data['volume'].mean() == 0 else 1
                        
                        strength = min((touches * 0.4) + (volume_score * 0.6), 1.0)
                        scored_clusters.append((avg_price, strength, len(cluster)))
                
                scored_clusters.sort(key=lambda x: x[1], reverse=True)
                return [(price, strength) for price, strength, _ in scored_clusters]
            
            support_levels = df.iloc[low_idx]['low'].values if len(low_idx) > 0 else []
            resistance_levels = df.iloc[high_idx]['high'].values if len(high_idx) > 0 else []
            
            support = cluster_and_score(support_levels, df, is_support=True)
            resistance = cluster_and_score(resistance_levels, df, is_support=False)
            
            return support[:5], resistance[:5]
        except Exception as e:
            return [], []
    
    def find_strong_support_resistance_15m(self, df, window=15):
        if len(df) < window * 2:
            return [], []
        
        try:
            high_idx = argrelextrema(df['high'].values, np.greater, order=window)[0]
            low_idx = argrelextrema(df['low'].values, np.less, order=window)[0]
            
            def cluster_and_score(levels, price_data, is_support=True):
                if len(levels) == 0:
                    return []
                
                eps_value = np.std(levels) * 0.3
                if eps_value <= 0:
                    eps_value = np.mean(levels) * 0.003
                eps_value = max(eps_value, np.mean(levels) * 0.001)
                
                levels_array = np.array(levels).reshape(-1, 1)
                
                try:
                    db = DBSCAN(eps=float(eps_value), min_samples=2).fit(levels_array)
                    labels = db.labels_
                except:
                    labels = np.zeros(len(levels))
                
                clusters = {}
                for i, label in enumerate(labels):
                    if label not in clusters:
                        clusters[label] = []
                    clusters[label].append(levels[i])
                
                scored_clusters = []
                for label, cluster in clusters.items():
                    if label != -1:
                        avg_price = np.mean(cluster)
                        
                        if is_support:
                            touches = len(price_data[
                                (price_data['low'] <= avg_price * 1.003) & 
                                (price_data['low'] >= avg_price * 0.997)
                            ])
                        else:
                            touches = len(price_data[
                                (price_data['high'] >= avg_price * 0.997) & 
                                (price_data['high'] <= avg_price * 1.003)
                            ])
                        
                        volume_mask = (price_data['close'] >= avg_price * 0.995) & (price_data['close'] <= avg_price * 1.005)
                        volume_score = price_data.loc[volume_mask, 'volume'].mean() / price_data['volume'].mean() if not price_data['volume'].mean() == 0 else 1
                        
                        strength = min((touches * 0.4) + (volume_score * 0.6), 1.0)
                        scored_clusters.append((avg_price, strength, len(cluster)))
                
                scored_clusters.sort(key=lambda x: x[1], reverse=True)
                return [(price, strength) for price, strength, _ in scored_clusters]
            
            support_levels = df.iloc[low_idx]['low'].values if len(low_idx) > 0 else []
            resistance_levels = df.iloc[high_idx]['high'].values if len(high_idx) > 0 else []
            
            support = cluster_and_score(support_levels, df, is_support=True)
            resistance = cluster_and_score(resistance_levels, df, is_support=False)
            
            return support[:6], resistance[:6]
        except Exception as e:
            return [], []
    
    def find_strong_support_resistance_5m(self, df, window=10):
        if len(df) < window * 2:
            return [], []
        
        try:
            high_idx = argrelextrema(df['high'].values, np.greater, order=window)[0]
            low_idx = argrelextrema(df['low'].values, np.less, order=window)[0]
            
            def cluster_and_score(levels, price_data, is_support=True):
                if len(levels) == 0:
                    return []
                
                eps_value = np.std(levels) * 0.2
                if eps_value <= 0:
                    eps_value = np.mean(levels) * 0.002
                eps_value = max(eps_value, np.mean(levels) * 0.0005)
                
                levels_array = np.array(levels).reshape(-1, 1)
                
                try:
                    db = DBSCAN(eps=float(eps_value), min_samples=2).fit(levels_array)
                    labels = db.labels_
                except:
                    labels = np.zeros(len(levels))
                
                clusters = {}
                for i, label in enumerate(labels):
                    if label not in clusters:
                        clusters[label] = []
                    clusters[label].append(levels[i])
                
                scored_clusters = []
                for label, cluster in clusters.items():
                    if label != -1:
                        avg_price = np.mean(cluster)
                        
                        if is_support:
                            touches = len(price_data[
                                (price_data['low'] <= avg_price * 1.002) & 
                                (price_data['low'] >= avg_price * 0.998)
                            ])
                        else:
                            touches = len(price_data[
                                (price_data['high'] >= avg_price * 0.998) & 
                                (price_data['high'] <= avg_price * 1.002)
                            ])
                        
                        volume_mask = (price_data['close'] >= avg_price * 0.997) & (price_data['close'] <= avg_price * 1.003)
                        volume_score = price_data.loc[volume_mask, 'volume'].mean() / price_data['volume'].mean() if not price_data['volume'].mean() == 0 else 1
                        
                        strength = min((touches * 0.3) + (volume_score * 0.7), 1.0)
                        scored_clusters.append((avg_price, strength, len(cluster)))
                
                scored_clusters.sort(key=lambda x: x[1], reverse=True)
                return [(price, strength) for price, strength, _ in scored_clusters]
            
            support_levels = df.iloc[low_idx]['low'].values if len(low_idx) > 0 else []
            resistance_levels = df.iloc[high_idx]['high'].values if len(high_idx) > 0 else []
            
            support = cluster_and_score(support_levels, df, is_support=True)
            resistance = cluster_and_score(resistance_levels, df, is_support=False)
            
            return support[:8], resistance[:8]
        except Exception as e:
            return [], []
    
    def find_strong_support_resistance_1m(self, df, window=7):
        if len(df) < window * 2:
            return [], []
        
        try:
            high_idx = argrelextrema(df['high'].values, np.greater, order=window)[0]
            low_idx = argrelextrema(df['low'].values, np.less, order=window)[0]
            
            def cluster_and_score(levels, price_data, is_support=True):
                if len(levels) == 0:
                    return []
                
                eps_value = np.std(levels) * 0.15
                if eps_value <= 0:
                    eps_value = np.mean(levels) * 0.0015
                eps_value = max(eps_value, np.mean(levels) * 0.0003)
                
                levels_array = np.array(levels).reshape(-1, 1)
                
                try:
                    db = DBSCAN(eps=float(eps_value), min_samples=2).fit(levels_array)
                    labels = db.labels_
                except:
                    labels = np.zeros(len(levels))
                
                clusters = {}
                for i, label in enumerate(labels):
                    if label not in clusters:
                        clusters[label] = []
                    clusters[label].append(levels[i])
                
                scored_clusters = []
                for label, cluster in clusters.items():
                    if label != -1:
                        avg_price = np.mean(cluster)
                        
                        if is_support:
                            touches = len(price_data[
                                (price_data['low'] <= avg_price * 1.0015) & 
                                (price_data['low'] >= avg_price * 0.9985)
                            ])
                        else:
                            touches = len(price_data[
                                (price_data['high'] >= avg_price * 0.9985) & 
                                (price_data['high'] <= avg_price * 1.0015)
                            ])
                        
                        volume_mask = (price_data['close'] >= avg_price * 0.998) & (price_data['close'] <= avg_price * 1.002)
                        volume_score = price_data.loc[volume_mask, 'volume'].mean() / price_data['volume'].mean() if not price_data['volume'].mean() == 0 else 1
                        
                        strength = min((touches * 0.25) + (volume_score * 0.75), 1.0)
                        scored_clusters.append((avg_price, strength, len(cluster)))
                
                scored_clusters.sort(key=lambda x: x[1], reverse=True)
                return [(price, strength) for price, strength, _ in scored_clusters]
            
            support_levels = df.iloc[low_idx]['low'].values if len(low_idx) > 0 else []
            resistance_levels = df.iloc[high_idx]['high'].values if len(high_idx) > 0 else []
            
            support = cluster_and_score(support_levels, df, is_support=True)
            resistance = cluster_and_score(resistance_levels, df, is_support=False)
            
            return support[:10], resistance[:10]
        except Exception as e:
            return [], []
    
    # ======================
    # Chart Creation Methods
    # ======================
    def create_main_chart(self, df_1h, symbol):
        if df_1h is None or df_1h.empty:
            return go.Figure()
        
        fig = make_subplots(rows=1, cols=1)
        
        fig.add_trace(go.Candlestick(
            x=df_1h['timestamp'],
            open=df_1h['open'],
            high=df_1h['high'],
            low=df_1h['low'],
            close=df_1h['close'],
            name='Price',
            increasing_line_color='#00ff88',
            decreasing_line_color='#ff0066'
        ), row=1, col=1)
        
        # Blue Lines
        if symbol in self.blue_liquidity_lines:
            for line in self.blue_liquidity_lines[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_1h['timestamp'].iloc[0],
                    x1=df_1h['timestamp'].iloc[-1],
                    y0=line['price'],
                    y1=line['price'],
                    line=dict(color=line['color'], width=line['width'], dash=line['dash']),
                    row=1, col=1
                )
                fig.add_annotation(
                    x=df_1h['timestamp'].iloc[-1],
                    y=line['price'],
                    text=line['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=35,
                    ay=0,
                    bgcolor='rgba(30, 144, 255, 0.6)',
                    bordercolor='#1E90FF',
                    borderwidth=1,
                    font=dict(color='white', size=7),
                    row=1, col=1
                )
        
        # White Levels
        if symbol in self.white_liquidity_levels:
            for level in self.white_liquidity_levels[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_1h['timestamp'].iloc[0],
                    x1=df_1h['timestamp'].iloc[-1],
                    y0=level['price'],
                    y1=level['price'],
                    line=dict(color=level['color'], width=level['width'], dash=level['dash']),
                    row=1, col=1
                )
                fig.add_annotation(
                    x=df_1h['timestamp'].iloc[-1],
                    y=level['price'],
                    text=level['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=35,
                    ay=0,
                    bgcolor='rgba(255, 255, 255, 0.6)',
                    bordercolor='white',
                    borderwidth=1,
                    font=dict(color='black', size=7),
                    row=1, col=1
                )
        
        # Yellow Zones
        if symbol in self.yellow_liquidation_zones:
            for zone in self.yellow_liquidation_zones[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_1h['timestamp'].iloc[0],
                    x1=df_1h['timestamp'].iloc[-1],
                    y0=zone['price'],
                    y1=zone['price'],
                    line=dict(color=zone['color'], width=zone['width'], dash=zone['dash']),
                    row=1, col=1
                )
                fig.add_annotation(
                    x=df_1h['timestamp'].iloc[-1],
                    y=zone['price'],
                    text=zone['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=35,
                    ay=0,
                    bgcolor='rgba(255, 255, 0, 0.6)',
                    bordercolor='#FFFF00',
                    borderwidth=1,
                    font=dict(color='black', size=7),
                    row=1, col=1
                )
        
        # Orange Zones
        if symbol in self.orange_magnetic_zones:
            for zone in self.orange_magnetic_zones[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_1h['timestamp'].iloc[0],
                    x1=df_1h['timestamp'].iloc[-1],
                    y0=zone['price'],
                    y1=zone['price'],
                    line=dict(color=zone['color'], width=zone['width'], dash=zone['dash']),
                    row=1, col=1
                )
                fig.add_annotation(
                    x=df_1h['timestamp'].iloc[-1],
                    y=zone['price'],
                    text=zone['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=35,
                    ay=0,
                    bgcolor='rgba(255, 165, 0, 0.6)',
                    bordercolor='#FFA500',
                    borderwidth=1,
                    font=dict(color='white', size=7),
                    row=1, col=1
                )
        
        fig.update_layout(
            title=f"📊 {symbol} - 1h",
            height=800,
            showlegend=False,
            hovermode="x unified",
            plot_bgcolor='rgba(10, 10, 30, 0.5)',
            paper_bgcolor='rgba(10, 10, 30, 0.5)',
            margin=dict(l=20, r=20, t=60, b=20),
            font=dict(color='#e0f0ff', size=10)
        )
        
        fig.update_xaxes(rangeslider_visible=False, row=1, col=1)
        return fig
    
    def create_15m_chart(self, df_15m, symbol):
        if df_15m is None or df_15m.empty:
            return go.Figure()
        
        fig = make_subplots(rows=1, cols=1)
        
        fig.add_trace(go.Candlestick(
            x=df_15m['timestamp'],
            open=df_15m['open'],
            high=df_15m['high'],
            low=df_15m['low'],
            close=df_15m['close'],
            name='Price',
            increasing_line_color='#00ff88',
            decreasing_line_color='#ff0066'
        ), row=1, col=1)
        
        if symbol in self.blue_liquidity_lines_15m:
            for line in self.blue_liquidity_lines_15m[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_15m['timestamp'].iloc[0],
                    x1=df_15m['timestamp'].iloc[-1],
                    y0=line['price'],
                    y1=line['price'],
                    line=dict(color=line['color'], width=line['width'], dash=line['dash']),
                    row=1, col=1
                )
                fig.add_annotation(
                    x=df_15m['timestamp'].iloc[-1],
                    y=line['price'],
                    text=line['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=25,
                    ay=0,
                    bgcolor='rgba(30, 144, 255, 0.5)',
                    bordercolor='#1E90FF',
                    borderwidth=1,
                    font=dict(color='white', size=6),
                    row=1, col=1
                )
        
        if symbol in self.white_liquidity_levels_15m:
            for level in self.white_liquidity_levels_15m[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_15m['timestamp'].iloc[0],
                    x1=df_15m['timestamp'].iloc[-1],
                    y0=level['price'],
                    y1=level['price'],
                    line=dict(color=level['color'], width=level['width'], dash=level['dash']),
                    row=1, col=1
                )
                fig.add_annotation(
                    x=df_15m['timestamp'].iloc[-1],
                    y=level['price'],
                    text=level['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=25,
                    ay=0,
                    bgcolor='rgba(255, 255, 255, 0.5)',
                    bordercolor='white',
                    borderwidth=1,
                    font=dict(color='black', size=6),
                    row=1, col=1
                )
        
        if symbol in self.yellow_liquidation_zones_15m:
            for zone in self.yellow_liquidation_zones_15m[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_15m['timestamp'].iloc[0],
                    x1=df_15m['timestamp'].iloc[-1],
                    y0=zone['price'],
                    y1=zone['price'],
                    line=dict(color=zone['color'], width=zone['width'], dash=zone['dash']),
                    row=1, col=1
                )
                fig.add_annotation(
                    x=df_15m['timestamp'].iloc[-1],
                    y=zone['price'],
                    text=zone['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=25,
                    ay=0,
                    bgcolor='rgba(255, 255, 0, 0.5)',
                    bordercolor='#FFFF00',
                    borderwidth=1,
                    font=dict(color='black', size=6),
                    row=1, col=1
                )
        
        if symbol in self.orange_magnetic_zones_15m:
            for zone in self.orange_magnetic_zones_15m[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_15m['timestamp'].iloc[0],
                    x1=df_15m['timestamp'].iloc[-1],
                    y0=zone['price'],
                    y1=zone['price'],
                    line=dict(color=zone['color'], width=zone['width'], dash=zone['dash']),
                    row=1, col=1
                )
                fig.add_annotation(
                    x=df_15m['timestamp'].iloc[-1],
                    y=zone['price'],
                    text=zone['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=25,
                    ay=0,
                    bgcolor='rgba(255, 165, 0, 0.5)',
                    bordercolor='#FFA500',
                    borderwidth=1,
                    font=dict(color='white', size=6),
                    row=1, col=1
                )
        
        fig.update_layout(
            title=f"📊 {symbol} - 15m",
            height=800,
            showlegend=False,
            hovermode="x unified",
            plot_bgcolor='rgba(10, 10, 30, 0.5)',
            paper_bgcolor='rgba(10, 10, 30, 0.5)',
            margin=dict(l=20, r=20, t=60, b=20),
            font=dict(color='#e0f0ff', size=10)
        )
        return fig
    
    def create_5m_chart(self, df_5m, symbol):
        if df_5m is None or df_5m.empty:
            return go.Figure()
        
        fig = make_subplots(rows=1, cols=1)
        
        fig.add_trace(go.Candlestick(
            x=df_5m['timestamp'],
            open=df_5m['open'],
            high=df_5m['high'],
            low=df_5m['low'],
            close=df_5m['close'],
            name='Price',
            increasing_line_color='#00ff88',
            decreasing_line_color='#ff0066'
        ), row=1, col=1)
        
        if symbol in self.blue_liquidity_lines_5m:
            for line in self.blue_liquidity_lines_5m[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_5m['timestamp'].iloc[0],
                    x1=df_5m['timestamp'].iloc[-1],
                    y0=line['price'],
                    y1=line['price'],
                    line=dict(color=line['color'], width=line['width'], dash=line['dash']),
                    row=1, col=1
                )
                fig.add_annotation(
                    x=df_5m['timestamp'].iloc[-1],
                    y=line['price'],
                    text=line['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=20,
                    ay=0,
                    bgcolor='rgba(30, 144, 255, 0.5)',
                    bordercolor='#1E90FF',
                    borderwidth=1,
                    font=dict(color='white', size=6),
                    row=1, col=1
                )
        
        if symbol in self.white_liquidity_levels_5m:
            for level in self.white_liquidity_levels_5m[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_5m['timestamp'].iloc[0],
                    x1=df_5m['timestamp'].iloc[-1],
                    y0=level['price'],
                    y1=level['price'],
                    line=dict(color=level['color'], width=level['width'], dash=level['dash']),
                    row=1, col=1
                )
                fig.add_annotation(
                    x=df_5m['timestamp'].iloc[-1],
                    y=level['price'],
                    text=level['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=20,
                    ay=0,
                    bgcolor='rgba(255, 255, 255, 0.5)',
                    bordercolor='white',
                    borderwidth=1,
                    font=dict(color='black', size=6),
                    row=1, col=1
                )
        
        if symbol in self.yellow_liquidation_zones_5m:
            for zone in self.yellow_liquidation_zones_5m[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_5m['timestamp'].iloc[0],
                    x1=df_5m['timestamp'].iloc[-1],
                    y0=zone['price'],
                    y1=zone['price'],
                    line=dict(color=zone['color'], width=zone['width'], dash=zone['dash']),
                    row=1, col=1
                )
                fig.add_annotation(
                    x=df_5m['timestamp'].iloc[-1],
                    y=zone['price'],
                    text=zone['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=20,
                    ay=0,
                    bgcolor='rgba(255, 255, 0, 0.5)',
                    bordercolor='#FFFF00',
                    borderwidth=1,
                    font=dict(color='black', size=6),
                    row=1, col=1
                )
        
        if symbol in self.orange_magnetic_zones_5m:
            for zone in self.orange_magnetic_zones_5m[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_5m['timestamp'].iloc[0],
                    x1=df_5m['timestamp'].iloc[-1],
                    y0=zone['price'],
                    y1=zone['price'],
                    line=dict(color=zone['color'], width=zone['width'], dash=zone['dash']),
                    row=1, col=1
                )
                fig.add_annotation(
                    x=df_5m['timestamp'].iloc[-1],
                    y=zone['price'],
                    text=zone['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=20,
                    ay=0,
                    bgcolor='rgba(255, 165, 0, 0.5)',
                    bordercolor='#FFA500',
                    borderwidth=1,
                    font=dict(color='white', size=6),
                    row=1, col=1
                )
        
        fig.update_layout(
            title=f"📊 {symbol} - 5m",
            height=800,
            showlegend=False,
            hovermode="x unified",
            plot_bgcolor='rgba(10, 10, 30, 0.5)',
            paper_bgcolor='rgba(10, 10, 30, 0.5)',
            margin=dict(l=20, r=20, t=60, b=20),
            font=dict(color='#e0f0ff', size=10)
        )
        return fig
    
    def create_1m_chart(self, df_1m, symbol):
        if df_1m is None or df_1m.empty:
            return go.Figure()
        
        fig = make_subplots(rows=1, cols=1)
        
        fig.add_trace(go.Candlestick(
            x=df_1m['timestamp'],
            open=df_1m['open'],
            high=df_1m['high'],
            low=df_1m['low'],
            close=df_1m['close'],
            name='Price',
            increasing_line_color='#00ff88',
            decreasing_line_color='#ff0066'
        ), row=1, col=1)
        
        if symbol in self.blue_liquidity_lines_1m:
            for line in self.blue_liquidity_lines_1m[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_1m['timestamp'].iloc[0],
                    x1=df_1m['timestamp'].iloc[-1],
                    y0=line['price'],
                    y1=line['price'],
                    line=dict(color=line['color'], width=line['width'], dash=line['dash']),
                    row=1, col=1
                )
                fig.add_annotation(
                    x=df_1m['timestamp'].iloc[-1],
                    y=line['price'],
                    text=line['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=15,
                    ay=0,
                    bgcolor='rgba(30, 144, 255, 0.5)',
                    bordercolor='#1E90FF',
                    borderwidth=1,
                    font=dict(color='white', size=5),
                    row=1, col=1
                )
        
        if symbol in self.white_liquidity_levels_1m:
            for level in self.white_liquidity_levels_1m[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_1m['timestamp'].iloc[0],
                    x1=df_1m['timestamp'].iloc[-1],
                    y0=level['price'],
                    y1=level['price'],
                    line=dict(color=level['color'], width=level['width'], dash=level['dash']),
                    row=1, col=1
                )
                fig.add_annotation(
                    x=df_1m['timestamp'].iloc[-1],
                    y=level['price'],
                    text=level['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=15,
                    ay=0,
                    bgcolor='rgba(255, 255, 255, 0.5)',
                    bordercolor='white',
                    borderwidth=1,
                    font=dict(color='black', size=5),
                    row=1, col=1
                )
        
        if symbol in self.yellow_liquidation_zones_1m:
            for zone in self.yellow_liquidation_zones_1m[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_1m['timestamp'].iloc[0],
                    x1=df_1m['timestamp'].iloc[-1],
                    y0=zone['price'],
                    y1=zone['price'],
                    line=dict(color=zone['color'], width=zone['width'], dash=zone['dash']),
                    row=1, col=1
                )
                fig.add_annotation(
                    x=df_1m['timestamp'].iloc[-1],
                    y=zone['price'],
                    text=zone['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=15,
                    ay=0,
                    bgcolor='rgba(255, 255, 0, 0.5)',
                    bordercolor='#FFFF00',
                    borderwidth=1,
                    font=dict(color='black', size=5),
                    row=1, col=1
                )
        
        if symbol in self.orange_magnetic_zones_1m:
            for zone in self.orange_magnetic_zones_1m[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_1m['timestamp'].iloc[0],
                    x1=df_1m['timestamp'].iloc[-1],
                    y0=zone['price'],
                    y1=zone['price'],
                    line=dict(color=zone['color'], width=zone['width'], dash=zone['dash']),
                    row=1, col=1
                )
                fig.add_annotation(
                    x=df_1m['timestamp'].iloc[-1],
                    y=zone['price'],
                    text=zone['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=15,
                    ay=0,
                    bgcolor='rgba(255, 165, 0, 0.5)',
                    bordercolor='#FFA500',
                    borderwidth=1,
                    font=dict(color='white', size=5),
                    row=1, col=1
                )
        
        fig.update_layout(
            title=f"📊 {symbol} - 1m",
            height=800,
            showlegend=False,
            hovermode="x unified",
            plot_bgcolor='rgba(10, 10, 30, 0.5)',
            paper_bgcolor='rgba(10, 10, 30, 0.5)',
            margin=dict(l=20, r=20, t=60, b=20),
            font=dict(color='#e0f0ff', size=8)
        )
        return fig
    
    def create_4h_chart(self, df_4h, symbol):
        if df_4h is None or df_4h.empty:
            return go.Figure()
        
        fig = make_subplots(rows=1, cols=1)
        
        fig.add_trace(go.Candlestick(
            x=df_4h['timestamp'],
            open=df_4h['open'],
            high=df_4h['high'],
            low=df_4h['low'],
            close=df_4h['close'],
            name='Price',
            increasing_line_color='#00ff88',
            decreasing_line_color='#ff0066'
        ), row=1, col=1)
        
        if symbol in self.blue_liquidity_lines_4h:
            for line in self.blue_liquidity_lines_4h[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_4h['timestamp'].iloc[0],
                    x1=df_4h['timestamp'].iloc[-1],
                    y0=line['price'],
                    y1=line['price'],
                    line=dict(color=line['color'], width=line['width'], dash=line['dash']),
                    row=1, col=1
                )
                fig.add_annotation(
                    x=df_4h['timestamp'].iloc[-1],
                    y=line['price'],
                    text=line['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=35,
                    ay=0,
                    bgcolor='rgba(30, 144, 255, 0.6)',
                    bordercolor='#1E90FF',
                    borderwidth=1,
                    font=dict(color='white', size=7),
                    row=1, col=1
                )
        
        if symbol in self.white_liquidity_levels_4h:
            for level in self.white_liquidity_levels_4h[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_4h['timestamp'].iloc[0],
                    x1=df_4h['timestamp'].iloc[-1],
                    y0=level['price'],
                    y1=level['price'],
                    line=dict(color=level['color'], width=level['width'], dash=level['dash']),
                    row=1, col=1
                )
                fig.add_annotation(
                    x=df_4h['timestamp'].iloc[-1],
                    y=level['price'],
                    text=level['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=35,
                    ay=0,
                    bgcolor='rgba(255, 255, 255, 0.6)',
                    bordercolor='white',
                    borderwidth=1,
                    font=dict(color='black', size=7),
                    row=1, col=1
                )
        
        if symbol in self.yellow_liquidation_zones_4h:
            for zone in self.yellow_liquidation_zones_4h[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_4h['timestamp'].iloc[0],
                    x1=df_4h['timestamp'].iloc[-1],
                    y0=zone['price'],
                    y1=zone['price'],
                    line=dict(color=zone['color'], width=zone['width'], dash=zone['dash']),
                    row=1, col=1
                )
                fig.add_annotation(
                    x=df_4h['timestamp'].iloc[-1],
                    y=zone['price'],
                    text=zone['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=35,
                    ay=0,
                    bgcolor='rgba(255, 255, 0, 0.6)',
                    bordercolor='#FFFF00',
                    borderwidth=1,
                    font=dict(color='black', size=7),
                    row=1, col=1
                )
        
        if symbol in self.orange_magnetic_zones_4h:
            for zone in self.orange_magnetic_zones_4h[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_4h['timestamp'].iloc[0],
                    x1=df_4h['timestamp'].iloc[-1],
                    y0=zone['price'],
                    y1=zone['price'],
                    line=dict(color=zone['color'], width=zone['width'], dash=zone['dash']),
                    row=1, col=1
                )
                fig.add_annotation(
                    x=df_4h['timestamp'].iloc[-1],
                    y=zone['price'],
                    text=zone['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=35,
                    ay=0,
                    bgcolor='rgba(255, 165, 0, 0.6)',
                    bordercolor='#FFA500',
                    borderwidth=1,
                    font=dict(color='white', size=7),
                    row=1, col=1
                )
        
        fig.update_layout(
            title=f"📊 {symbol} - 4h",
            height=800,
            showlegend=False,
            hovermode="x unified",
            plot_bgcolor='rgba(10, 10, 30, 0.5)',
            paper_bgcolor='rgba(10, 10, 30, 0.5)',
            margin=dict(l=20, r=20, t=60, b=20),
            font=dict(color='#e0f0ff', size=10)
        )
        return fig

# ============================================
# 🔐 Login & Admin Pages
# ============================================

def login_page(user_manager):
    st.markdown("""
    <div style="text-align: center; padding: 30px;">
        <h1 style="font-size: 3em;">🔐 Login</h1>
        <p style="font-size: 1.2em; color: #888;">Advanced Liquidity Analysis Platform</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        tab1, tab2 = st.tabs(["🔑 Login", "📝 Register"])
        
        with tab1:
            with st.form("login_form"):
                username = st.text_input("👤 Username")
                password = st.text_input("🔒 Password", type="password")
                
                if st.form_submit_button("🚀 Login", use_container_width=True):
                    if username and password:
                        success, message = user_manager.login_user(username, password)
                        if success:
                            st.session_state['logged_in'] = True
                            st.session_state['username'] = username
                            st.session_state['is_admin'] = user_manager.is_admin(username)
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)
                    else:
                        st.warning("⚠️ Please enter username and password")
        
        with tab2:
            with st.form("register_form"):
                new_username = st.text_input("👤 Username")
                new_password = st.text_input("🔒 Password", type="password")
                new_email = st.text_input("📧 Email (optional)")
                
                if st.form_submit_button("📝 Create Account", use_container_width=True):
                    if new_username and new_password:
                        success, message = user_manager.register_user(new_username, new_password, new_email)
                        if success:
                            st.success(message)
                            st.info("📝 Wait for admin activation")
                        else:
                            st.error(message)
                    else:
                        st.warning("⚠️ Please enter username and password")

def admin_panel(user_manager):
    st.markdown("""
    <div style="background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
                padding: 20px; border-radius: 10px; margin-bottom: 20px;">
        <h2 style="color: white; text-align: center;">🛡️ Admin Panel</h2>
    </div>
    """, unsafe_allow_html=True)
    
    total, active, pending, admin_count = user_manager.get_users_count()
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("👥 Total Users", total)
    with col2:
        st.metric("🟢 Active", active)
    with col3:
        st.metric("🟡 Pending", pending)
    with col4:
        st.metric("👑 Admins", admin_count)
    
    st.markdown("### 🟡 Pending Users")
    pending_users = user_manager.get_pending_users()
    
    if pending_users:
        for username, data in pending_users.items():
            col1, col2, col3, col4, col5 = st.columns([2, 2, 1, 1, 1])
            with col1:
                st.write(f"**👤 {username}**")
                st.caption(f"📧 {data.get('email', 'None')}")
            with col2:
                st.write("💰 Pending Payment")
            with col3:
                if st.button(f"✅ Activate", key=f"activate_{username}"):
                    success, message = user_manager.activate_user(username)
                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
            with col4:
                if st.button(f"❌ Deactivate", key=f"deact_pending_{username}"):
                    success, message = user_manager.deactivate_user(username)
                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
            with col5:
                if st.button(f"🗑️ Delete", key=f"delete_{username}"):
                    success, message = user_manager.delete_user(username)
                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
    else:
        st.info("✅ No pending users")
    
    st.markdown("---")
    st.markdown("### 📋 All Users")
    
    all_users = user_manager.get_all_users()
    
    if all_users:
        col1, col2, col3, col4, col5, col6, col7, col8 = st.columns([1.2, 1, 1.2, 1.5, 1, 1, 1, 1])
        with col1:
            st.write("**Username**")
        with col2:
            st.write("**Status**")
        with col3:
            st.write("**Email**")
        with col4:
            st.write("**Expiry**")
        with col5:
            st.write("**Activate**")
        with col6:
            st.write("**Deactivate**")
        with col7:
            st.write("**Extend**")
        with col8:
            st.write("**Delete**")
        
        st.divider()
        
        for username, data in all_users.items():
            if username == ADMIN_USERNAME:
                continue
            
            col1, col2, col3, col4, col5, col6, col7, col8 = st.columns([1.2, 1, 1.2, 1.5, 1, 1, 1, 1])
            
            with col1:
                st.write(f"**{username}**")
            with col2:
                if data.get('is_admin', False):
                    st.write("👑 Admin")
                elif data.get('active', False):
                    st.write("🟢 Active")
                else:
                    st.write("🟡 Pending")
            with col3:
                st.write(data.get('email', '-'))
            with col4:
                expiry = data.get('expiry_date', '-')
                if expiry and expiry != '-':
                    try:
                        expiry_date = datetime.fromisoformat(expiry)
                        days_left = (expiry_date - datetime.now()).days
                        if days_left > 0:
                            st.write(f"{expiry[:10]} ({days_left}d)")
                        else:
                            st.write(f"⚠️ {expiry[:10]} (Expired)")
                    except:
                        st.write(expiry[:10])
                else:
                    st.write('-')
            with col5:
                if not data.get('is_admin', False) and not data.get('active', False):
                    if st.button(f"✅ Activate", key=f"act_{username}"):
                        success, message = user_manager.activate_user(username)
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)
                elif data.get('active', False):
                    st.write("✅")
                else:
                    st.write("—")
            with col6:
                if not data.get('is_admin', False) and data.get('active', False):
                    if st.button(f"❌ Deactivate", key=f"deact_{username}"):
                        success, message = user_manager.deactivate_user(username)
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)
                elif not data.get('active', False):
                    st.write("⏳")
                else:
                    st.write("—")
            with col7:
                if not data.get('is_admin', False):
                    if st.button(f"📅 Extend", key=f"ext_{username}"):
                        success, message = user_manager.extend_subscription(username, 30)
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)
                else:
                    st.write("—")
            with col8:
                if not data.get('is_admin', False):
                    if st.button(f"🗑️ Delete", key=f"del_{username}"):
                        success, message = user_manager.delete_user(username)
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)
                else:
                    st.write("👑")
    else:
        st.info("📭 No users found")
    
    st.markdown("---")
    st.markdown("### 🔧 Admin Tools")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**📅 Extend Subscription**")
        users_list = [u for u in all_users.keys() if u != ADMIN_USERNAME] if all_users else []
        if users_list:
            selected_user = st.selectbox("Select user", users_list, key="extend_select")
            days = st.number_input("Days to extend", min_value=1, max_value=365, value=30, key="extend_days")
            if st.button("📅 Extend Subscription", key="extend_btn"):
                success, message = user_manager.extend_subscription(selected_user, days)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
        else:
            st.info("No users to extend")
    
    with col2:
        st.markdown("**📊 User Stats**")
        st.write(f"👥 Total: {total}")
        st.write(f"🟢 Active: {active}")
        st.write(f"🟡 Pending: {pending}")
        st.write(f"👑 Admins: {admin_count}")

def payment_page(user_manager):
    st.markdown("""
    <div style="text-align: center; padding: 30px; background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
                border-radius: 15px; margin-bottom: 30px;">
        <h1 style="color: white;">💎 Activate Account</h1>
    </div>
    """, unsafe_allow_html=True)
    
    st.info("""
    **💰 Subscription Details:**
    1. Contact me on Telegram: [@SOFIAN232](https://t.me/SOFIAN232)
    2. Send $99 (monthly)
    3. Send your username
    4. Account activated within 24 hours
    
    **💎 Features:**
    - 5 Timeframes (1m, 5m, 15m, 1h, 4h)
    - Blue Liquidity Lines
    - White Strong Levels
    - Yellow Liquidation Zones
    - Orange Magnetic Zones
    """)

def analysis_interface():
    st.markdown("""
    <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); 
                border-radius: 15px; margin-bottom: 30px;">
        <h1 style="color: white;">🧠 Advanced Liquidity Analyzer</h1>
        <p style="color: #e0f0ff;">Bybit | Candles + Liquidity + Liquidation + Magnetic Zones</p>
    </div>
    """, unsafe_allow_html=True)
    
    analyzer = CryptoAnalyzer()
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        symbol = st.text_input("💰 Enter Symbol:", "BTC/USDT").upper()
    
    with col2:
        st.write("")
        if st.button("🚀 Analyze", type="primary", use_container_width=True):
            st.session_state['run_analysis'] = True
    
    if st.session_state.get('run_analysis', False):
        st.session_state['run_analysis'] = False
        
        with st.spinner(f"🔄 Analyzing {symbol}..."):
            try:
                df_1h, df_4h = analyzer.fetch_data(symbol)
                df_15m = analyzer.fetch_data_15m(symbol)
                df_5m = analyzer.fetch_data_5m(symbol)
                df_1m = analyzer.fetch_data_1m(symbol)
                
                timeframes = {
                    '4h': df_4h,
                    '1h': df_1h,
                    '15m': df_15m,
                    '5m': df_5m,
                    '1m': df_1m
                }
                
                has_data = any(df is not None and not df.empty for df in timeframes.values())
                
                if has_data:
                    tabs = st.tabs(["⏰ 4h", "📈 1h", "⏱️ 15m", "⏱️ 5m", "⏱️ 1m"])
                    
                    for tab, (tf, df) in zip(tabs, timeframes.items()):
                        with tab:
                            if df is not None and not df.empty:
                                if tf == '4h':
                                    fig = analyzer.create_4h_chart(df, symbol)
                                elif tf == '1h':
                                    fig = analyzer.create_main_chart(df, symbol)
                                elif tf == '15m':
                                    fig = analyzer.create_15m_chart(df, symbol)
                                elif tf == '5m':
                                    fig = analyzer.create_5m_chart(df, symbol)
                                elif tf == '1m':
                                    fig = analyzer.create_1m_chart(df, symbol)
                                
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                st.error(f"❌ No data for {tf}")
                else:
                    st.error(f"❌ No data available for {symbol}")
            except Exception as e:
                st.error(f"❌ Analysis error: {str(e)}")

# ============================================
# 🚀 Main
# ============================================

def main():
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
    if 'username' not in st.session_state:
        st.session_state['username'] = None
    if 'is_admin' not in st.session_state:
        st.session_state['is_admin'] = False
    if 'run_analysis' not in st.session_state:
        st.session_state['run_analysis'] = False
    
    user_manager = UserManager()
    
    if not st.session_state['logged_in']:
        login_page(user_manager)
        return
    
    username = st.session_state['username']
    is_admin = st.session_state['is_admin']
    
    if not is_admin:
        user_data = user_manager.get_user_data(username)
        if not user_data or not user_data.get('active', False):
            payment_page(user_manager)
            return
    
    with st.sidebar:
        st.markdown("### 🧠 Analyzer")
        st.markdown(f"👤 **User:** {username}")
        st.markdown(f"🔑 **Role:** {'👑 Admin' if is_admin else '👤 User'}")
        
        if is_admin:
            st.markdown("---")
            st.markdown("### 📊 Quick Stats")
            total, active, pending, admin_count = user_manager.get_users_count()
            st.metric("👥 Users", total)
            st.metric("🟢 Active", active)
            st.metric("🟡 Pending", pending)
        
        st.markdown("---")
        st.markdown("### 🔗 Links")
        st.markdown("[📞 Telegram](https://t.me/SOFIAN232)")
        
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state['logged_in'] = False
            st.session_state['username'] = None
            st.session_state['is_admin'] = False
            st.rerun()
    
    if is_admin:
        tab_admin, tab_analysis = st.tabs(["🛡️ Admin Panel", "📊 Analysis"])
        with tab_admin:
            admin_panel(user_manager)
        with tab_analysis:
            analysis_interface()
    else:
        analysis_interface()

if __name__ == "__main__":
    main()