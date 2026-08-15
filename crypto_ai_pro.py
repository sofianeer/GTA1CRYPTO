import streamlit as st
import pandas as pd
import numpy as np
import ccxt
import talib
from scipy.signal import argrelextrema
from scipy.stats import linregress
from sklearn.cluster import DBSCAN, KMeans
from sklearn.preprocessing import StandardScaler
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
import hashlib
import os
import json
from collections import defaultdict
import sqlite3
import warnings
warnings.filterwarnings('ignore')

# ============================================
# 🔧 تحسينات الأداء الذكية
# ============================================

CACHE_DURATION_DATA = 60
CACHE_DURATION_ANALYSIS = 300
RATE_LIMIT_SECONDS = 2
MAX_CANDLES = 500

ADMIN_USERNAME = "adminSO"
ADMIN_PASSWORD = "admin25SO"
SUBSCRIPTION_PRICE = "99$"

# ============================================
# 🌐 الاتصال بـ Binance (محسن لـ Streamlit Cloud)
# ============================================

@st.cache_resource
def get_exchange():
    """إنشاء اتصال Binance مع إعدادات محسنة"""
    try:
        exchange = ccxt.binance({
            'rateLimit': 3000,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
                'adjustForTimeDifference': True,
            },
            'timeout': 60000,
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        })
        exchange.load_markets()
        return exchange
    except Exception as e:
        st.error(f"❌ خطأ في الاتصال: {str(e)}")
        return None

@st.cache_data(ttl=CACHE_DURATION_DATA)
def fetch_candles_cached(symbol, timeframe='1h', limit=500):
    """جلب البيانات مع إعادة محاولة ذكية"""
    exchange = get_exchange()
    if exchange is None:
        return None
    
    if '/' not in symbol:
        symbol = f"{symbol}/USDT"
    
    for attempt in range(5):
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if ohlcv and len(ohlcv) > 0:
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                return df
        except Exception as e:
            if attempt < 4:
                time.sleep((attempt + 1) * 2)
                continue
            else:
                st.error(f"❌ فشل جلب البيانات: {str(e)[:100]}")
                return None
    return None

@st.cache_data(ttl=CACHE_DURATION_ANALYSIS)
def calculate_indicators_cached(df):
    if df is None or df.empty:
        return df
    
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

def check_rate_limit():
    if 'last_click' not in st.session_state:
        st.session_state.last_click = 0
    current_time = time.time()
    if current_time - st.session_state.last_click < RATE_LIMIT_SECONDS:
        wait = RATE_LIMIT_SECONDS - (current_time - st.session_state.last_click)
        st.warning(f"⏳ انتظر {int(wait) + 1} ثواني")
        return False
    st.session_state.last_click = current_time
    return True

# ============================================
# 🗄️ نظام إدارة المستخدمين
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
            print(f"❌ خطأ: {e}")
    
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
            print(f"❌ خطأ: {e}")
    
    def _hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()
    
    def register_user(self, username, password, email=""):
        if len(username) < 3:
            return False, "❌ اسم المستخدم 3 أحرف على الأقل"
        if len(password) < 4:
            return False, "❌ كلمة المرور 4 أحرف على الأقل"
        
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username=?", (username,))
            if cursor.fetchone():
                conn.close()
                return False, "❌ اسم المستخدم موجود"
            
            cursor.execute('''
                INSERT INTO users 
                (username, password, email, active, created_at, is_admin, payment_status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (username, self._hash_password(password), email, 0, datetime.now().isoformat(), 0, "pending"))
            conn.commit()
            conn.close()
            return True, "✅ تم التسجيل! انتظر التفعيل"
        except Exception as e:
            return False, f"❌ خطأ: {str(e)}"
    
    def login_user(self, username, password):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username=?", (username,))
            user = cursor.fetchone()
            
            if not user:
                conn.close()
                return False, "❌ اسم المستخدم غير موجود"
            if user[3] == 0:
                conn.close()
                return False, "⛔ حسابك غير مفعل"
            if user[1] != self._hash_password(password):
                conn.close()
                return False, "❌ كلمة مرور خاطئة"
            
            cursor.execute("UPDATE users SET last_login=? WHERE username=?", (datetime.now().isoformat(), username))
            conn.commit()
            conn.close()
            return True, "✅ تم تسجيل الدخول"
        except Exception as e:
            return False, f"❌ خطأ: {str(e)}"
    
    def activate_user(self, username):
        if username == ADMIN_USERNAME:
            return False, "❌ المسؤول مفعل تلقائياً"
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            expiry = datetime.now() + timedelta(days=30)
            cursor.execute('''
                UPDATE users SET active=1, payment_status='paid', payment_date=?, expiry_date=?
                WHERE username=?
            ''', (datetime.now().isoformat(), expiry.isoformat(), username))
            conn.commit()
            conn.close()
            return True, f"✅ تم تفعيل {username}"
        except Exception as e:
            return False, f"❌ خطأ: {str(e)}"
    
    def deactivate_user(self, username):
        if username == ADMIN_USERNAME:
            return False, "❌ لا يمكن تعطيل المسؤول"
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET active=0, payment_status='expired' WHERE username=?", (username,))
            conn.commit()
            conn.close()
            return True, f"✅ تم تعطيل {username}"
        except Exception as e:
            return False, f"❌ خطأ: {str(e)}"
    
    def get_pending_users(self):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT username, email, created_at FROM users WHERE active=0 AND is_admin=0")
            users = cursor.fetchall()
            conn.close()
            return {u[0]: {"email": u[1], "created_at": u[2]} for u in users}
        except:
            return {}
    
    def get_active_users(self):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT username, email, expiry_date FROM users WHERE active=1 AND is_admin=0")
            users = cursor.fetchall()
            conn.close()
            return {u[0]: {"email": u[1], "expiry_date": u[2]} for u in users}
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
            for u in users:
                result[u[0]] = {
                    "email": u[1],
                    "active": bool(u[2]),
                    "created_at": u[3],
                    "last_login": u[4],
                    "is_admin": bool(u[5]),
                    "payment_status": u[6],
                    "payment_date": u[7],
                    "expiry_date": u[8]
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
            u = cursor.fetchone()
            conn.close()
            if u:
                return {
                    "username": u[0],
                    "email": u[1],
                    "active": bool(u[2]),
                    "created_at": u[3],
                    "last_login": u[4],
                    "is_admin": bool(u[5]),
                    "payment_status": u[6],
                    "payment_date": u[7],
                    "expiry_date": u[8]
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

    def make_admin(self, username):
        if username == ADMIN_USERNAME:
            return False, "❌ هذا حساب المسؤول الرئيسي"
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_admin=1 WHERE username=?", (username,))
            conn.commit()
            conn.close()
            return True, f"✅ تم ترقية {username} إلى مسؤول"
        except Exception as e:
            return False, f"❌ خطأ: {str(e)}"
    
    def remove_admin(self, username):
        if username == ADMIN_USERNAME:
            return False, "❌ لا يمكن إلغاء صلاحية المسؤول الرئيسي"
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_admin=0 WHERE username=?", (username,))
            conn.commit()
            conn.close()
            return True, f"✅ تم إلغاء صلاحية المسؤول عن {username}"
        except Exception as e:
            return False, f"❌ خطأ: {str(e)}"
    
    def extend_subscription(self, username, days=30):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT expiry_date FROM users WHERE username=?", (username,))
            result = cursor.fetchone()
            if result and result[0]:
                current_expiry = datetime.fromisoformat(result[0])
                new_expiry = current_expiry + timedelta(days=days)
            else:
                new_expiry = datetime.now() + timedelta(days=days)
            cursor.execute('''
                UPDATE users SET expiry_date=?, payment_status='paid', active=1
                WHERE username=?
            ''', (new_expiry.isoformat(), username))
            conn.commit()
            conn.close()
            return True, f"✅ تم تمديد اشتراك {username} لـ {days} يوماً"
        except Exception as e:
            return False, f"❌ خطأ: {str(e)}"

# ============================================
# 🎯 كاشف مناطق التصفية الصفراء
# ============================================

class LiquidationZonesDetector:
    def __init__(self):
        self.liquidation_zones = {}
    
    def detect_liquidation_zones(self, df, timeframe='1h'):
        if df is None or len(df) < 50:
            return []
        
        zones = []
        for i in range(2, len(df)-2):
            current = df.iloc[i]
            prev = df.iloc[i-1]
            next_candle = df.iloc[i+1]
            next_next = df.iloc[i+2]
            
            upper_wick = current['high'] - max(current['open'], current['close'])
            lower_wick = min(current['open'], current['close']) - current['low']
            body_size = abs(current['close'] - current['open'])
            candle_range = current['high'] - current['low']
            
            avg_volume = df['volume'].iloc[max(0, i-20):i].mean()
            volume_ratio = current['volume'] / avg_volume if avg_volume > 0 else 1
            
            if (current['volume'] > avg_volume * 2 and lower_wick > candle_range * 0.4 and
                current['close'] > current['open'] and current['low'] < prev['low'] and
                next_candle['close'] > current['high']):
                
                confirmed = next_next['close'] > next_candle['high']
                zone = {
                    'price': current['low'],
                    'type': 'bullish',
                    'strength': volume_ratio,
                    'confirmed': confirmed,
                    'timeframe': timeframe,
                    'color': '#FFFF00',
                    'width': 2,
                    'dash': 'dash',
                    'description': '🟢 منطقة تصفية صاعدة'
                }
                zones.append(zone)
            
            elif (current['volume'] > avg_volume * 2 and upper_wick > candle_range * 0.4 and
                  current['close'] < current['open'] and current['high'] > prev['high'] and
                  next_candle['close'] < current['low']):
                
                confirmed = next_next['close'] < next_candle['low']
                zone = {
                    'price': current['high'],
                    'type': 'bearish',
                    'strength': volume_ratio,
                    'confirmed': confirmed,
                    'timeframe': timeframe,
                    'color': '#FFFF00',
                    'width': 2,
                    'dash': 'dash',
                    'description': '🔴 منطقة تصفية هابطة'
                }
                zones.append(zone)
        
        zones.sort(key=lambda x: x['strength'], reverse=True)
        self.liquidation_zones[timeframe] = zones
        return zones

# ============================================
# 📊 فئة التحليل التقني - جميع الأطر الزمنية مع الخطوط
# ============================================

class CryptoAnalyzer:
    def __init__(self):
        self.exchange = get_exchange()
        self.liquidation_detector = LiquidationZonesDetector()
        self.blue_liquidity_lines = {}
        self.white_liquidity_levels = {}
        self.yellow_liquidation_zones = {}
        self.orange_magnetic_zones = {}
        self.blue_liquidity_lines_15m = {}
        self.white_liquidity_levels_15m = {}
        self.yellow_liquidation_zones_15m = {}
        self.blue_liquidity_lines_5m = {}
        self.white_liquidity_levels_5m = {}
        self.yellow_liquidation_zones_5m = {}
        self.blue_liquidity_lines_1m = {}
        self.white_liquidity_levels_1m = {}
        self.yellow_liquidation_zones_1m = {}
        self.blue_liquidity_lines_4h = {}
        self.white_liquidity_levels_4h = {}
        self.yellow_liquidation_zones_4h = {}
        self.orange_magnetic_zones_15m = {}
        self.orange_magnetic_zones_5m = {}
        self.orange_magnetic_zones_1m = {}
        self.orange_magnetic_zones_4h = {}
    
    def fetch_data(self, symbol):
        try:
            df_1h = fetch_candles_cached(symbol, '1h', MAX_CANDLES)
            df_4h = fetch_candles_cached(symbol, '4h', MAX_CANDLES // 2)
            df_15m = fetch_candles_cached(symbol, '15m', MAX_CANDLES)
            df_5m = fetch_candles_cached(symbol, '5m', MAX_CANDLES)
            df_1m = fetch_candles_cached(symbol, '1m', MAX_CANDLES)
            
            if df_1h is not None:
                df_1h = calculate_indicators_cached(df_1h)
            if df_4h is not None:
                df_4h = calculate_indicators_cached(df_4h)
            if df_15m is not None:
                df_15m = calculate_indicators_cached(df_15m)
            if df_5m is not None:
                df_5m = calculate_indicators_cached(df_5m)
            if df_1m is not None:
                df_1m = calculate_indicators_cached(df_1m)
            
            # حساب المؤشرات لكل إطار
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
            
            if df_15m is not None:
                current_price_15m = df_15m['close'].iloc[-1]
                self.calculate_blue_liquidity_lines_15m(df_15m, current_price_15m, symbol)
                self.calculate_white_liquidity_levels_15m(df_15m, current_price_15m, symbol)
                self.calculate_yellow_liquidation_zones_15m(df_15m, symbol)
                self.calculate_orange_magnetic_zones_15m(df_15m, current_price_15m, symbol)
            
            if df_5m is not None:
                current_price_5m = df_5m['close'].iloc[-1]
                self.calculate_blue_liquidity_lines_5m(df_5m, current_price_5m, symbol)
                self.calculate_white_liquidity_levels_5m(df_5m, current_price_5m, symbol)
                self.calculate_yellow_liquidation_zones_5m(df_5m, symbol)
                self.calculate_orange_magnetic_zones_5m(df_5m, current_price_5m, symbol)
            
            if df_1m is not None:
                current_price_1m = df_1m['close'].iloc[-1]
                self.calculate_blue_liquidity_lines_1m(df_1m, current_price_1m, symbol)
                self.calculate_white_liquidity_levels_1m(df_1m, current_price_1m, symbol)
                self.calculate_yellow_liquidation_zones_1m(df_1m, symbol)
                self.calculate_orange_magnetic_zones_1m(df_1m, current_price_1m, symbol)
            
            return {
                '1h': df_1h,
                '4h': df_4h,
                '15m': df_15m,
                '5m': df_5m,
                '1m': df_1m
            }
        except Exception as e:
            st.error(f"❌ خطأ: {str(e)}")
            return None
    
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
    
    def calculate_blue_liquidity_lines(self, df, current_price, symbol):
        lines = []
        if df is None or len(df) < 20:
            self.blue_liquidity_lines[symbol] = lines
            return
        
        for i in range(max(0, len(df)-20), len(df)-1):
            candle = df.iloc[i]
            next_candle = df.iloc[i+1]
            upper_wick = candle['high'] - max(candle['open'], candle['close'])
            lower_wick = min(candle['open'], candle['close']) - candle['low']
            body_size = abs(candle['close'] - candle['open'])
            total_range = candle['high'] - candle['low']
            if total_range == 0:
                continue
            
            if lower_wick > body_size * 2 and upper_wick < body_size * 0.5 and next_candle['close'] > candle['close']:
                lines.append({
                    'price': candle['low'],
                    'type': 'buy_liquidity',
                    'strength': min(0.8 + (lower_wick/total_range), 0.95),
                    'description': '🔵 رفض شرائي قوي',
                    'color': '#1E90FF',
                    'width': 2,
                    'dash': 'solid'
                })
            
            if upper_wick > body_size * 2 and lower_wick < body_size * 0.5 and next_candle['close'] < candle['close']:
                lines.append({
                    'price': candle['high'],
                    'type': 'sell_liquidity',
                    'strength': min(0.8 + (upper_wick/total_range), 0.95),
                    'description': '🔵 رفض بيعي قوي',
                    'color': '#1E90FF',
                    'width': 2,
                    'dash': 'solid'
                })
        
        self.blue_liquidity_lines[symbol] = lines[:10]
    
    def calculate_blue_liquidity_lines_15m(self, df, current_price, symbol):
        lines = []
        if df is None or len(df) < 20:
            self.blue_liquidity_lines_15m[symbol] = lines
            return
        for i in range(max(0, len(df)-30), len(df)-1):
            candle = df.iloc[i]
            next_candle = df.iloc[i+1]
            upper_wick = candle['high'] - max(candle['open'], candle['close'])
            lower_wick = min(candle['open'], candle['close']) - candle['low']
            body_size = abs(candle['close'] - candle['open'])
            total_range = candle['high'] - candle['low']
            if total_range == 0:
                continue
            if lower_wick > body_size * 2 and upper_wick < body_size * 0.3 and next_candle['close'] > candle['close']:
                lines.append({
                    'price': candle['low'],
                    'type': 'buy_liquidity_15m',
                    'strength': min(0.8 + (lower_wick/total_range), 0.95),
                    'description': '🔵 رفض شرائي 15m',
                    'color': '#1E90FF',
                    'width': 2,
                    'dash': 'solid'
                })
            if upper_wick > body_size * 2 and lower_wick < body_size * 0.3 and next_candle['close'] < candle['close']:
                lines.append({
                    'price': candle['high'],
                    'type': 'sell_liquidity_15m',
                    'strength': min(0.8 + (upper_wick/total_range), 0.95),
                    'description': '🔵 رفض بيعي 15m',
                    'color': '#1E90FF',
                    'width': 2,
                    'dash': 'solid'
                })
        self.blue_liquidity_lines_15m[symbol] = lines[:10]
    
    def calculate_blue_liquidity_lines_5m(self, df, current_price, symbol):
        lines = []
        if df is None or len(df) < 20:
            self.blue_liquidity_lines_5m[symbol] = lines
            return
        for i in range(max(0, len(df)-40), len(df)-1):
            candle = df.iloc[i]
            next_candle = df.iloc[i+1]
            upper_wick = candle['high'] - max(candle['open'], candle['close'])
            lower_wick = min(candle['open'], candle['close']) - candle['low']
            body_size = abs(candle['close'] - candle['open'])
            total_range = candle['high'] - candle['low']
            if total_range == 0:
                continue
            if lower_wick > body_size * 1.8 and upper_wick < body_size * 0.4 and next_candle['close'] > candle['close']:
                lines.append({
                    'price': candle['low'],
                    'type': 'buy_liquidity_5m',
                    'strength': min(0.8 + (lower_wick/total_range), 0.95),
                    'description': '🔵 رفض شرائي 5m',
                    'color': '#1E90FF',
                    'width': 2,
                    'dash': 'solid'
                })
            if upper_wick > body_size * 1.8 and lower_wick < body_size * 0.4 and next_candle['close'] < candle['close']:
                lines.append({
                    'price': candle['high'],
                    'type': 'sell_liquidity_5m',
                    'strength': min(0.8 + (upper_wick/total_range), 0.95),
                    'description': '🔵 رفض بيعي 5m',
                    'color': '#1E90FF',
                    'width': 2,
                    'dash': 'solid'
                })
        self.blue_liquidity_lines_5m[symbol] = lines[:10]
    
    def calculate_blue_liquidity_lines_1m(self, df, current_price, symbol):
        lines = []
        if df is None or len(df) < 20:
            self.blue_liquidity_lines_1m[symbol] = lines
            return
        for i in range(max(0, len(df)-50), len(df)-1):
            candle = df.iloc[i]
            next_candle = df.iloc[i+1]
            upper_wick = candle['high'] - max(candle['open'], candle['close'])
            lower_wick = min(candle['open'], candle['close']) - candle['low']
            body_size = abs(candle['close'] - candle['open'])
            total_range = candle['high'] - candle['low']
            if total_range == 0:
                continue
            if lower_wick > body_size * 1.5 and upper_wick < body_size * 0.5 and next_candle['close'] > candle['close']:
                lines.append({
                    'price': candle['low'],
                    'type': 'buy_liquidity_1m',
                    'strength': min(0.7 + (lower_wick/total_range), 0.9),
                    'description': '🔵 رفض شرائي 1m',
                    'color': '#1E90FF',
                    'width': 1.5,
                    'dash': 'solid'
                })
            if upper_wick > body_size * 1.5 and lower_wick < body_size * 0.5 and next_candle['close'] < candle['close']:
                lines.append({
                    'price': candle['high'],
                    'type': 'sell_liquidity_1m',
                    'strength': min(0.7 + (upper_wick/total_range), 0.9),
                    'description': '🔵 رفض بيعي 1m',
                    'color': '#1E90FF',
                    'width': 1.5,
                    'dash': 'solid'
                })
        self.blue_liquidity_lines_1m[symbol] = lines[:10]
    
    def calculate_blue_liquidity_lines_4h(self, df, current_price, symbol):
        lines = []
        if df is None or len(df) < 20:
            self.blue_liquidity_lines_4h[symbol] = lines
            return
        for i in range(max(0, len(df)-15), len(df)-1):
            candle = df.iloc[i]
            next_candle = df.iloc[i+1]
            upper_wick = candle['high'] - max(candle['open'], candle['close'])
            lower_wick = min(candle['open'], candle['close']) - candle['low']
            body_size = abs(candle['close'] - candle['open'])
            total_range = candle['high'] - candle['low']
            if total_range == 0:
                continue
            if lower_wick > body_size * 2 and upper_wick < body_size * 0.5 and next_candle['close'] > candle['close']:
                lines.append({
                    'price': candle['low'],
                    'type': 'buy_liquidity_4h',
                    'strength': min(0.8 + (lower_wick/total_range), 0.95),
                    'description': '🔵 رفض شرائي 4H',
                    'color': '#1E90FF',
                    'width': 2,
                    'dash': 'solid'
                })
            if upper_wick > body_size * 2 and lower_wick < body_size * 0.5 and next_candle['close'] < candle['close']:
                lines.append({
                    'price': candle['high'],
                    'type': 'sell_liquidity_4h',
                    'strength': min(0.8 + (upper_wick/total_range), 0.95),
                    'description': '🔵 رفض بيعي 4H',
                    'color': '#1E90FF',
                    'width': 2,
                    'dash': 'solid'
                })
        self.blue_liquidity_lines_4h[symbol] = lines[:10]
    
    def calculate_white_liquidity_levels(self, df, current_price, symbol):
        levels = []
        if df is None or len(df) < 50:
            self.white_liquidity_levels[symbol] = levels
            return
        high_idx = argrelextrema(df['high'].values, np.greater, order=10)[0]
        low_idx = argrelextrema(df['low'].values, np.less, order=10)[0]
        for idx in high_idx[-5:]:
            price = df['high'].iloc[idx]
            distance_pct = abs(price - current_price) / current_price * 100
            if distance_pct < 5:
                levels.append({
                    'price': price,
                    'type': 'resistance',
                    'strength': 0.8,
                    'description': '⚪ مقاومة قوية',
                    'color': 'white',
                    'width': 1.5,
                    'dash': 'dash'
                })
        for idx in low_idx[-5:]:
            price = df['low'].iloc[idx]
            distance_pct = abs(price - current_price) / current_price * 100
            if distance_pct < 5:
                levels.append({
                    'price': price,
                    'type': 'support',
                    'strength': 0.8,
                    'description': '⚪ دعم قوي',
                    'color': 'white',
                    'width': 1.5,
                    'dash': 'dash'
                })
        self.white_liquidity_levels[symbol] = levels[:5]
    
    def calculate_white_liquidity_levels_15m(self, df, current_price, symbol):
        levels = []
        if df is None or len(df) < 50:
            self.white_liquidity_levels_15m[symbol] = levels
            return
        high_idx = argrelextrema(df['high'].values, np.greater, order=8)[0]
        low_idx = argrelextrema(df['low'].values, np.less, order=8)[0]
        for idx in high_idx[-5:]:
            price = df['high'].iloc[idx]
            distance_pct = abs(price - current_price) / current_price * 100
            if distance_pct < 3:
                levels.append({
                    'price': price,
                    'type': 'resistance_15m',
                    'strength': 0.7,
                    'description': '⚪ مقاومة 15m',
                    'color': 'white',
                    'width': 1.5,
                    'dash': 'dash'
                })
        for idx in low_idx[-5:]:
            price = df['low'].iloc[idx]
            distance_pct = abs(price - current_price) / current_price * 100
            if distance_pct < 3:
                levels.append({
                    'price': price,
                    'type': 'support_15m',
                    'strength': 0.7,
                    'description': '⚪ دعم 15m',
                    'color': 'white',
                    'width': 1.5,
                    'dash': 'dash'
                })
        self.white_liquidity_levels_15m[symbol] = levels[:5]
    
    def calculate_white_liquidity_levels_5m(self, df, current_price, symbol):
        levels = []
        if df is None or len(df) < 50:
            self.white_liquidity_levels_5m[symbol] = levels
            return
        high_idx = argrelextrema(df['high'].values, np.greater, order=5)[0]
        low_idx = argrelextrema(df['low'].values, np.less, order=5)[0]
        for idx in high_idx[-5:]:
            price = df['high'].iloc[idx]
            distance_pct = abs(price - current_price) / current_price * 100
            if distance_pct < 2:
                levels.append({
                    'price': price,
                    'type': 'resistance_5m',
                    'strength': 0.6,
                    'description': '⚪ مقاومة 5m',
                    'color': 'white',
                    'width': 1.5,
                    'dash': 'dash'
                })
        for idx in low_idx[-5:]:
            price = df['low'].iloc[idx]
            distance_pct = abs(price - current_price) / current_price * 100
            if distance_pct < 2:
                levels.append({
                    'price': price,
                    'type': 'support_5m',
                    'strength': 0.6,
                    'description': '⚪ دعم 5m',
                    'color': 'white',
                    'width': 1.5,
                    'dash': 'dash'
                })
        self.white_liquidity_levels_5m[symbol] = levels[:5]
    
    def calculate_white_liquidity_levels_1m(self, df, current_price, symbol):
        levels = []
        if df is None or len(df) < 50:
            self.white_liquidity_levels_1m[symbol] = levels
            return
        high_idx = argrelextrema(df['high'].values, np.greater, order=3)[0]
        low_idx = argrelextrema(df['low'].values, np.less, order=3)[0]
        for idx in high_idx[-5:]:
            price = df['high'].iloc[idx]
            distance_pct = abs(price - current_price) / current_price * 100
            if distance_pct < 1.5:
                levels.append({
                    'price': price,
                    'type': 'resistance_1m',
                    'strength': 0.5,
                    'description': '⚪ مقاومة 1m',
                    'color': 'white',
                    'width': 1,
                    'dash': 'dash'
                })
        for idx in low_idx[-5:]:
            price = df['low'].iloc[idx]
            distance_pct = abs(price - current_price) / current_price * 100
            if distance_pct < 1.5:
                levels.append({
                    'price': price,
                    'type': 'support_1m',
                    'strength': 0.5,
                    'description': '⚪ دعم 1m',
                    'color': 'white',
                    'width': 1,
                    'dash': 'dash'
                })
        self.white_liquidity_levels_1m[symbol] = levels[:5]
    
    def calculate_white_liquidity_levels_4h(self, df, current_price, symbol):
        levels = []
        if df is None or len(df) < 50:
            self.white_liquidity_levels_4h[symbol] = levels
            return
        high_idx = argrelextrema(df['high'].values, np.greater, order=15)[0]
        low_idx = argrelextrema(df['low'].values, np.less, order=15)[0]
        for idx in high_idx[-5:]:
            price = df['high'].iloc[idx]
            distance_pct = abs(price - current_price) / current_price * 100
            if distance_pct < 8:
                levels.append({
                    'price': price,
                    'type': 'resistance_4h',
                    'strength': 0.8,
                    'description': '⚪ مقاومة 4H',
                    'color': 'white',
                    'width': 2,
                    'dash': 'dash'
                })
        for idx in low_idx[-5:]:
            price = df['low'].iloc[idx]
            distance_pct = abs(price - current_price) / current_price * 100
            if distance_pct < 8:
                levels.append({
                    'price': price,
                    'type': 'support_4h',
                    'strength': 0.8,
                    'description': '⚪ دعم 4H',
                    'color': 'white',
                    'width': 2,
                    'dash': 'dash'
                })
        self.white_liquidity_levels_4h[symbol] = levels[:5]
    
    def calculate_yellow_liquidation_zones(self, df, symbol):
        zones = self.liquidation_detector.detect_liquidation_zones(df, '1h')
        self.yellow_liquidation_zones[symbol] = zones[:5]
    
    def calculate_yellow_liquidation_zones_15m(self, df, symbol):
        zones = self.liquidation_detector.detect_liquidation_zones(df, '15m')
        self.yellow_liquidation_zones_15m[symbol] = zones[:5]
    
    def calculate_yellow_liquidation_zones_5m(self, df, symbol):
        zones = self.liquidation_detector.detect_liquidation_zones(df, '5m')
        self.yellow_liquidation_zones_5m[symbol] = zones[:5]
    
    def calculate_yellow_liquidation_zones_1m(self, df, symbol):
        zones = self.liquidation_detector.detect_liquidation_zones(df, '1m')
        self.yellow_liquidation_zones_1m[symbol] = zones[:5]
    
    def calculate_yellow_liquidation_zones_4h(self, df, symbol):
        zones = self.liquidation_detector.detect_liquidation_zones(df, '4h')
        self.yellow_liquidation_zones_4h[symbol] = zones[:5]
    
    def calculate_orange_magnetic_zones(self, df, current_price, symbol):
        zones = []
        if df is None or len(df) < 50:
            self.orange_magnetic_zones[symbol] = zones
            return
        for i in range(10, len(df)-10):
            if (df['high'].iloc[i] > df['high'].iloc[i-1] and df['high'].iloc[i] > df['high'].iloc[i+1] and
                df['high'].iloc[i] > df['high'].iloc[i-2] and df['high'].iloc[i] > df['high'].iloc[i+2]):
                price = df['high'].iloc[i]
                distance_pct = abs(price - current_price) / current_price * 100
                if distance_pct < 5:
                    zones.append({
                        'price': price,
                        'type': 'magnetic_resistance',
                        'strength': 0.7,
                        'distance_pct': distance_pct,
                        'description': '🧲 جذب (مقاومة)',
                        'color': 'rgba(255, 165, 0, 0.7)',
                        'width': 2,
                        'dash': 'dot'
                    })
            if (df['low'].iloc[i] < df['low'].iloc[i-1] and df['low'].iloc[i] < df['low'].iloc[i+1] and
                df['low'].iloc[i] < df['low'].iloc[i-2] and df['low'].iloc[i] < df['low'].iloc[i+2]):
                price = df['low'].iloc[i]
                distance_pct = abs(price - current_price) / current_price * 100
                if distance_pct < 5:
                    zones.append({
                        'price': price,
                        'type': 'magnetic_support',
                        'strength': 0.7,
                        'distance_pct': distance_pct,
                        'description': '🧲 جذب (دعم)',
                        'color': 'rgba(255, 165, 0, 0.7)',
                        'width': 2,
                        'dash': 'dot'
                    })
        self.orange_magnetic_zones[symbol] = zones[:5]
    
    def calculate_orange_magnetic_zones_15m(self, df, current_price, symbol):
        zones = []
        if df is None or len(df) < 50:
            self.orange_magnetic_zones_15m[symbol] = zones
            return
        for i in range(10, len(df)-10):
            if (df['high'].iloc[i] > df['high'].iloc[i-1] and df['high'].iloc[i] > df['high'].iloc[i+1]):
                price = df['high'].iloc[i]
                distance_pct = abs(price - current_price) / current_price * 100
                if distance_pct < 3:
                    zones.append({
                        'price': price,
                        'type': 'magnetic_resistance_15m',
                        'strength': 0.6,
                        'distance_pct': distance_pct,
                        'description': '🧲 جذب 15m',
                        'color': 'rgba(255, 165, 0, 0.7)',
                        'width': 2,
                        'dash': 'dot'
                    })
            if (df['low'].iloc[i] < df['low'].iloc[i-1] and df['low'].iloc[i] < df['low'].iloc[i+1]):
                price = df['low'].iloc[i]
                distance_pct = abs(price - current_price) / current_price * 100
                if distance_pct < 3:
                    zones.append({
                        'price': price,
                        'type': 'magnetic_support_15m',
                        'strength': 0.6,
                        'distance_pct': distance_pct,
                        'description': '🧲 جذب 15m',
                        'color': 'rgba(255, 165, 0, 0.7)',
                        'width': 2,
                        'dash': 'dot'
                    })
        self.orange_magnetic_zones_15m[symbol] = zones[:5]
    
    def calculate_orange_magnetic_zones_5m(self, df, current_price, symbol):
        zones = []
        if df is None or len(df) < 50:
            self.orange_magnetic_zones_5m[symbol] = zones
            return
        for i in range(5, len(df)-5):
            if (df['high'].iloc[i] > df['high'].iloc[i-1] and df['high'].iloc[i] > df['high'].iloc[i+1]):
                price = df['high'].iloc[i]
                distance_pct = abs(price - current_price) / current_price * 100
                if distance_pct < 2:
                    zones.append({
                        'price': price,
                        'type': 'magnetic_resistance_5m',
                        'strength': 0.5,
                        'distance_pct': distance_pct,
                        'description': '🧲 جذب 5m',
                        'color': 'rgba(255, 165, 0, 0.7)',
                        'width': 1.5,
                        'dash': 'dot'
                    })
            if (df['low'].iloc[i] < df['low'].iloc[i-1] and df['low'].iloc[i] < df['low'].iloc[i+1]):
                price = df['low'].iloc[i]
                distance_pct = abs(price - current_price) / current_price * 100
                if distance_pct < 2:
                    zones.append({
                        'price': price,
                        'type': 'magnetic_support_5m',
                        'strength': 0.5,
                        'distance_pct': distance_pct,
                        'description': '🧲 جذب 5m',
                        'color': 'rgba(255, 165, 0, 0.7)',
                        'width': 1.5,
                        'dash': 'dot'
                    })
        self.orange_magnetic_zones_5m[symbol] = zones[:5]
    
    def calculate_orange_magnetic_zones_1m(self, df, current_price, symbol):
        zones = []
        if df is None or len(df) < 30:
            self.orange_magnetic_zones_1m[symbol] = zones
            return
        for i in range(3, len(df)-3):
            if (df['high'].iloc[i] > df['high'].iloc[i-1] and df['high'].iloc[i] > df['high'].iloc[i+1]):
                price = df['high'].iloc[i]
                distance_pct = abs(price - current_price) / current_price * 100
                if distance_pct < 1.5:
                    zones.append({
                        'price': price,
                        'type': 'magnetic_resistance_1m',
                        'strength': 0.4,
                        'distance_pct': distance_pct,
                        'description': '🧲 جذب 1m',
                        'color': 'rgba(255, 165, 0, 0.7)',
                        'width': 1,
                        'dash': 'dot'
                    })
            if (df['low'].iloc[i] < df['low'].iloc[i-1] and df['low'].iloc[i] < df['low'].iloc[i+1]):
                price = df['low'].iloc[i]
                distance_pct = abs(price - current_price) / current_price * 100
                if distance_pct < 1.5:
                    zones.append({
                        'price': price,
                        'type': 'magnetic_support_1m',
                        'strength': 0.4,
                        'distance_pct': distance_pct,
                        'description': '🧲 جذب 1m',
                        'color': 'rgba(255, 165, 0, 0.7)',
                        'width': 1,
                        'dash': 'dot'
                    })
        self.orange_magnetic_zones_1m[symbol] = zones[:5]
    
    def calculate_orange_magnetic_zones_4h(self, df, current_price, symbol):
        zones = []
        if df is None or len(df) < 30:
            self.orange_magnetic_zones_4h[symbol] = zones
            return
        for i in range(5, len(df)-5):
            if (df['high'].iloc[i] > df['high'].iloc[i-1] and df['high'].iloc[i] > df['high'].iloc[i+1]):
                price = df['high'].iloc[i]
                distance_pct = abs(price - current_price) / current_price * 100
                if distance_pct < 8:
                    zones.append({
                        'price': price,
                        'type': 'magnetic_resistance_4h',
                        'strength': 0.7,
                        'distance_pct': distance_pct,
                        'description': '🧲 جذب 4H',
                        'color': 'rgba(255, 165, 0, 0.7)',
                        'width': 2,
                        'dash': 'dot'
                    })
            if (df['low'].iloc[i] < df['low'].iloc[i-1] and df['low'].iloc[i] < df['low'].iloc[i+1]):
                price = df['low'].iloc[i]
                distance_pct = abs(price - current_price) / current_price * 100
                if distance_pct < 8:
                    zones.append({
                        'price': price,
                        'type': 'magnetic_support_4h',
                        'strength': 0.7,
                        'distance_pct': distance_pct,
                        'description': '🧲 جذب 4H',
                        'color': 'rgba(255, 165, 0, 0.7)',
                        'width': 2,
                        'dash': 'dot'
                    })
        self.orange_magnetic_zones_4h[symbol] = zones[:5]
    
    def create_chart(self, df, symbol, timeframe):
        """إنشاء رسم بياني متقدم مع جميع الخطوط"""
        if df is None or df.empty:
            return go.Figure()
        
        current_price = df['close'].iloc[-1]
        
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.6, 0.2, 0.2],
            subplot_titles=(f"{symbol} - {timeframe}", "الحجم", "RSI")
        )
        
        # الشموع
        fig.add_trace(go.Candlestick(
            x=df['timestamp'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='السعر',
            increasing_line_color='#00ff88',
            decreasing_line_color='#ff0066'
        ), row=1, col=1)
        
        # إضافة المتوسطات المتحركة
        if 'SMA_20' in df.columns:
            fig.add_trace(go.Scatter(
                x=df['timestamp'],
                y=df['SMA_20'],
                name='SMA 20',
                line=dict(color='orange', width=1)
            ), row=1, col=1)
        if 'SMA_50' in df.columns:
            fig.add_trace(go.Scatter(
                x=df['timestamp'],
                y=df['SMA_50'],
                name='SMA 50',
                line=dict(color='blue', width=1)
            ), row=1, col=1)
        if 'EMA_100' in df.columns:
            fig.add_trace(go.Scatter(
                x=df['timestamp'],
                y=df['EMA_100'],
                name='EMA 100',
                line=dict(color='purple', width=1)
            ), row=1, col=1)
        
        # تحديد أي إطار زمني
        if timeframe == '4 ساعات':
            blue_lines = self.blue_liquidity_lines_4h.get(symbol, [])
            white_levels = self.white_liquidity_levels_4h.get(symbol, [])
            yellow_zones = self.yellow_liquidation_zones_4h.get(symbol, [])
            orange_zones = self.orange_magnetic_zones_4h.get(symbol, [])
        elif timeframe == '15 دقيقة':
            blue_lines = self.blue_liquidity_lines_15m.get(symbol, [])
            white_levels = self.white_liquidity_levels_15m.get(symbol, [])
            yellow_zones = self.yellow_liquidation_zones_15m.get(symbol, [])
            orange_zones = self.orange_magnetic_zones_15m.get(symbol, [])
        elif timeframe == '5 دقائق':
            blue_lines = self.blue_liquidity_lines_5m.get(symbol, [])
            white_levels = self.white_liquidity_levels_5m.get(symbol, [])
            yellow_zones = self.yellow_liquidation_zones_5m.get(symbol, [])
            orange_zones = self.orange_magnetic_zones_5m.get(symbol, [])
        elif timeframe == '1 دقيقة':
            blue_lines = self.blue_liquidity_lines_1m.get(symbol, [])
            white_levels = self.white_liquidity_levels_1m.get(symbol, [])
            yellow_zones = self.yellow_liquidation_zones_1m.get(symbol, [])
            orange_zones = self.orange_magnetic_zones_1m.get(symbol, [])
        else:  # 1 ساعة
            blue_lines = self.blue_liquidity_lines.get(symbol, [])
            white_levels = self.white_liquidity_levels.get(symbol, [])
            yellow_zones = self.yellow_liquidation_zones.get(symbol, [])
            orange_zones = self.orange_magnetic_zones.get(symbol, [])
        
        # الخطوط الزرقاء
        for line in blue_lines:
            fig.add_shape(
                type='line',
                x0=df['timestamp'].iloc[0],
                x1=df['timestamp'].iloc[-1],
                y0=line['price'],
                y1=line['price'],
                line=dict(color=line['color'], width=line['width'], dash=line['dash']),
                name=line['description'],
                row=1, col=1
            )
            fig.add_annotation(
                x=df['timestamp'].iloc[-1],
                y=line['price'],
                text=line['description'],
                showarrow=True,
                arrowhead=1,
                ax=30,
                ay=0,
                bgcolor='rgba(30, 144, 255, 0.8)',
                font=dict(color='white', size=8),
                row=1, col=1
            )
        
        # المستويات البيضاء
        for level in white_levels:
            fig.add_shape(
                type='line',
                x0=df['timestamp'].iloc[0],
                x1=df['timestamp'].iloc[-1],
                y0=level['price'],
                y1=level['price'],
                line=dict(color='white', width=level['width'], dash='dash'),
                name=level['description'],
                row=1, col=1
            )
            fig.add_annotation(
                x=df['timestamp'].iloc[-1],
                y=level['price'],
                text=level['description'],
                showarrow=True,
                arrowhead=1,
                ax=30,
                ay=0,
                bgcolor='rgba(255, 255, 255, 0.3)',
                font=dict(color='white', size=8),
                row=1, col=1
            )
        
        # المناطق الصفراء
        for zone in yellow_zones:
            fig.add_shape(
                type='line',
                x0=df['timestamp'].iloc[0],
                x1=df['timestamp'].iloc[-1],
                y0=zone['price'],
                y1=zone['price'],
                line=dict(color='#FFFF00', width=2, dash='dash'),
                name=zone['description'],
                row=1, col=1
            )
            fig.add_annotation(
                x=df['timestamp'].iloc[-1],
                y=zone['price'],
                text=zone['description'],
                showarrow=True,
                arrowhead=1,
                ax=30,
                ay=0,
                bgcolor='rgba(255, 255, 0, 0.5)',
                font=dict(color='black', size=8),
                row=1, col=1
            )
        
        # المناطق البرتقالية
        for zone in orange_zones:
            fig.add_shape(
                type='line',
                x0=df['timestamp'].iloc[0],
                x1=df['timestamp'].iloc[-1],
                y0=zone['price'],
                y1=zone['price'],
                line=dict(color='rgba(255, 165, 0, 0.7)', width=zone['width'], dash='dot'),
                name=zone['description'],
                row=1, col=1
            )
            fig.add_annotation(
                x=df['timestamp'].iloc[-1],
                y=zone['price'],
                text=zone['description'],
                showarrow=True,
                arrowhead=1,
                ax=30,
                ay=0,
                bgcolor='rgba(255, 165, 0, 0.5)',
                font=dict(color='white', size=8),
                row=1, col=1
            )
        
        # الحجم
        fig.add_trace(go.Bar(
            x=df['timestamp'],
            y=df['volume'],
            name='الحجم',
            marker_color='#7f8c8d',
            opacity=0.7
        ), row=2, col=1)
        
        # RSI
        if 'RSI' in df.columns:
            fig.add_trace(go.Scatter(
                x=df['timestamp'],
                y=df['RSI'],
                name='RSI',
                line=dict(color='#ff00ff', width=1.5)
            ), row=3, col=1)
            
            fig.add_shape(
                type='rect',
                x0=df['timestamp'].iloc[0],
                x1=df['timestamp'].iloc[-1],
                y0=70,
                y1=100,
                fillcolor='rgba(255, 0, 0, 0.2)',
                line=dict(width=0),
                row=3, col=1
            )
            fig.add_shape(
                type='rect',
                x0=df['timestamp'].iloc[0],
                x1=df['timestamp'].iloc[-1],
                y0=0,
                y1=30,
                fillcolor='rgba(0, 255, 0, 0.2)',
                line=dict(width=0),
                row=3, col=1
            )
        
        fig.update_layout(
            height=800,
            showlegend=True,
            hovermode="x unified",
            plot_bgcolor='rgba(10, 10, 30, 0.9)',
            paper_bgcolor='rgba(10, 10, 30, 0.9)',
            font=dict(color='#e0f0ff'),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        fig.update_xaxes(rangeslider_visible=False, row=1, col=1)
        
        return fig

# ============================================
# 🔐 صفحات تسجيل الدخول والإدارة
# ============================================

def login_page(user_manager):
    st.markdown("""
    <div style="text-align: center; padding: 30px;">
        <h1 style="font-size: 3em;">🔐 تسجيل الدخول</h1>
        <p style="font-size: 1.2em; color: #888;">قم بتسجيل الدخول للوصول إلى منصة التحليل المتقدم</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab1, tab2 = st.tabs(["🔑 تسجيل الدخول", "📝 إنشاء حساب جديد"])
        
        with tab1:
            with st.form("login_form"):
                username = st.text_input("👤 اسم المستخدم")
                password = st.text_input("🔒 كلمة المرور", type="password")
                if st.form_submit_button("🚀 تسجيل الدخول", use_container_width=True):
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
        
        with tab2:
            with st.form("register_form"):
                new_username = st.text_input("👤 اسم المستخدم", placeholder="3 أحرف على الأقل")
                new_password = st.text_input("🔒 كلمة المرور", type="password", placeholder="4 أحرف على الأقل")
                new_email = st.text_input("📧 البريد الإلكتروني (اختياري)")
                if st.form_submit_button("📝 إنشاء حساب", use_container_width=True):
                    if new_username and new_password:
                        success, message = user_manager.register_user(new_username, new_password, new_email)
                        if success:
                            st.success(message)
                        else:
                            st.error(message)

def admin_panel(user_manager):
    st.markdown("""
    <div style="background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
                padding: 20px; border-radius: 10px; margin-bottom: 20px;">
        <h2 style="color: white; text-align: center;">🛡️ لوحة تحكم المسؤول</h2>
    </div>
    """, unsafe_allow_html=True)
    
    total, active, pending, admin_count = user_manager.get_users_count()
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("👥 إجمالي المستخدمين", total)
    with col2:
        st.metric("🟢 نشطين", active)
    with col3:
        st.metric("🟡 في انتظار التفعيل", pending)
    with col4:
        st.metric("👑 مسؤولين", admin_count)
    
    st.markdown("### 🟡 المستخدمين المنتظرين للتفعيل")
    pending_users = user_manager.get_pending_users()
    if pending_users:
        for username, data in pending_users.items():
            col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
            with col1:
                st.write(f"**👤 {username}**")
                st.caption(f"📧 {data.get('email', 'لا يوجد')}")
            with col2:
                st.write("💰 في انتظار الدفع")
            with col3:
                if st.button(f"✅ تفعيل", key=f"activate_{username}"):
                    success, message = user_manager.activate_user(username)
                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
            with col4:
                if st.button(f"🗑️ حذف", key=f"delete_{username}"):
                    success, message = user_manager.delete_user(username)
                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
    else:
        st.info("✅ لا يوجد مستخدمين في انتظار التفعيل")
    
    st.markdown("### 🟢 المستخدمين النشطين")
    active_users = user_manager.get_active_users()
    if active_users:
        for username, data in active_users.items():
            col1, col2, col3, col4, col5 = st.columns([2, 2, 1, 1, 1])
            with col1:
                st.write(f"**👤 {username}**")
                st.caption(f"📧 {data.get('email', 'لا يوجد')}")
            with col2:
                if data.get('expiry_date'):
                    st.caption(f"📅 ينتهي: {data['expiry_date'][:10]}")
            with col3:
                if st.button(f"🔴 تعطيل", key=f"deactivate_{username}"):
                    success, message = user_manager.deactivate_user(username)
                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
            with col4:
                if st.button(f"👑 ترقية", key=f"make_admin_{username}"):
                    success, message = user_manager.make_admin(username)
                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
            with col5:
                if st.button(f"📅 تمديد", key=f"extend_{username}"):
                    success, message = user_manager.extend_subscription(username, 30)
                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)

def payment_page(user_manager):
    st.markdown("""
    <div style="text-align: center; padding: 30px; background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
                border-radius: 15px; margin-bottom: 30px;">
        <h1 style="color: white;">💎 تفعيل الحساب</h1>
        <p style="color: #e0f0ff;">للوصول إلى جميع ميزات المنصة، يرجى تفعيل حسابك</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown("""
        <div style="background: rgba(30, 60, 114, 0.3); padding: 20px; border-radius: 10px; border: 2px solid #00ff88;">
            <h3 style="color: #00ff88;">📋 مميزات الاشتراك</h3>
            <ul style="color: #e0f0ff;">
                <li>📊 شموع 5 أطر زمنية</li>
                <li>🔵 خطوط سيولة زرقاء</li>
                <li>⚪ مستويات قوية بيضاء</li>
                <li>🟡 مناطق تصفية صفراء</li>
                <li>🟠 مناطق جذب برتقالية</li>
                <li>📈 تحديثات لحظية</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div style="background: rgba(30, 60, 114, 0.3); padding: 20px; border-radius: 10px;">
            <h3 style="color: #ffaa00;">💰 طريقة الدفع</h3>
            <p style="color: #e0f0ff;">
                1️⃣ تواصل معي على تلغرام:<br>
                <a href="https://t.me/SOFIAN232" target="_blank" 
                   style="color: #00ff88; font-size: 1.2em;">
                    @SOFIAN232
                </a>
            </p>
            <p style="color: #e0f0ff;">
                2️⃣ أرسل مبلغ الاشتراك:<br>
                <span style="color: #ffaa00; font-size: 1.5em;">💵 99$</span>
                <span style="color: #888;">(شهرياً)</span>
            </p>
            <p style="color: #e0f0ff;">
                3️⃣ أرسل لي اسم المستخدم الخاص بك:<br>
                <span style="color: #00ff88;">📝 username: {your_username}</span>
            </p>
            <div style="background: rgba(255, 165, 0, 0.1); padding: 15px; border-radius: 10px;
                        border: 1px solid #ffaa00; margin-top: 15px;">
                <p style="color: #ffaa00; text-align: center;">
                    ⏳ بعد الدفع، سيتم تفعيل حسابك خلال 24 ساعة
                </p>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.session_state.get('username'):
            username = st.session_state['username']
            user_data = user_manager.get_user_data(username)
            if user_data:
                if user_data.get('payment_status') == 'pending':
                    st.warning("⏳ حسابك في انتظار التفعيل من قبل المسؤول")
                elif user_data.get('payment_status') == 'paid':
                    st.success("✅ حسابك مفعل! يمكنك استخدام جميع الميزات")
                    if user_data.get('expiry_date'):
                        st.info(f"📅 تنتهي الصلاحية: {user_data['expiry_date'][:10]}")

# ============================================
# 🎯 واجهة التحليل الرئيسية
# ============================================

def analysis_interface():
    st.markdown("""
    <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); 
                border-radius: 15px; margin-bottom: 30px;">
        <h1 style="color: white;">🧠 محلل السيولة المتقدم</h1>
        <p style="color: #e0f0ff;">شموع + خطوط سيولة + مناطق تصفية + جذب مغناطيسي</p>
    </div>
    """, unsafe_allow_html=True)
    
    exchange = get_exchange()
    if exchange:
        st.sidebar.success(f"✅ متصل بـ {exchange.name}")
    else:
        st.sidebar.error("❌ غير متصل")
    
    analyzer = CryptoAnalyzer()
    
    col1, col2 = st.columns([3, 1])
    with col1:
        symbol = st.text_input("💰 أدخل زوج العملات:", "BTC/USDT").upper()
    with col2:
        if st.button("🚀 تحليل", type="primary", use_container_width=True):
            if check_rate_limit():
                st.session_state['run_analysis'] = True
    
    if st.session_state.get('run_analysis', False):
        st.session_state['run_analysis'] = False
        
        with st.spinner(f"🔄 جاري تحليل {symbol}..."):
            data = analyzer.fetch_data(symbol)
            
            if data:
                timeframes = {
                    '4 ساعات': data.get('4h'),
                    '1 ساعة': data.get('1h'),
                    '15 دقيقة': data.get('15m'),
                    '5 دقائق': data.get('5m'),
                    '1 دقيقة': data.get('1m')
                }
                
                tabs = st.tabs(list(timeframes.keys()))
                
                for tab, (tf_name, df) in zip(tabs, timeframes.items()):
                    with tab:
                        if df is not None and not df.empty:
                            fig = analyzer.create_chart(df, symbol, tf_name)
                            st.plotly_chart(fig, use_container_width=True)
                            
                            current_price = df['close'].iloc[-1]
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("💰 السعر", f"${current_price:,.2f}")
                            with col2:
                                if len(df) > 1:
                                    change = ((df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2]) * 100
                                    st.metric("📈 التغير", f"{change:.2f}%")
                            with col3:
                                st.metric("📊 الشموع", len(df))
                            
                            with st.expander("📊 المؤشرات الفنية"):
                                if 'RSI' in df.columns:
                                    st.write(f"**RSI:** {df['RSI'].iloc[-1]:.2f}")
                                if 'MACD' in df.columns:
                                    st.write(f"**MACD:** {df['MACD'].iloc[-1]:.4f}")
                                if 'SMA_20' in df.columns:
                                    st.write(f"**SMA 20:** ${df['SMA_20'].iloc[-1]:,.2f}")
                                if 'SMA_50' in df.columns:
                                    st.write(f"**SMA 50:** ${df['SMA_50'].iloc[-1]:,.2f}")
                                if 'ATR' in df.columns:
                                    st.write(f"**ATR:** ${df['ATR'].iloc[-1]:,.2f}")
                        else:
                            st.error(f"❌ لا توجد بيانات لـ {tf_name}")

# ============================================
# 🚀 الدالة الرئيسية
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
        st.markdown("""
        <div style="text-align: center; padding: 10px;">
            <h2>🧠 المحلل المتقدم</h2>
            <hr>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown(f"""
        <div style="background: rgba(30, 60, 114, 0.3); padding: 15px; border-radius: 10px; margin-bottom: 20px;">
            <p>👤 **المستخدم:** {username}</p>
            <p>🔑 **الصلاحية:** {"👑 مسؤول" if is_admin else "👤 مستخدم"}</p>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("🚪 تسجيل الخروج", use_container_width=True):
            st.session_state['logged_in'] = False
            st.session_state['username'] = None
            st.session_state['is_admin'] = False
            st.rerun()
        
        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown("### 📊 القائمة")
    
    if is_admin:
        tab_admin, tab_analysis = st.tabs(["🛡️ لوحة تحكم المسؤول", "📊 التحليل"])
        with tab_admin:
            admin_panel(user_manager)
        with tab_analysis:
            analysis_interface()
    else:
        analysis_interface()

if __name__ == "__main__":
    main()