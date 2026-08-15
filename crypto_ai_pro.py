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

CACHE_DURATION_DATA = 300
CACHE_DURATION_ANALYSIS = 600
RATE_LIMIT_SECONDS = 3
MAX_CANDLES = 500

# ✅ بيانات المسؤول
ADMIN_USERNAME = "adminSO"
ADMIN_PASSWORD = "admin25SO"
SUBSCRIPTION_PRICE = "99$"

# ============================================
# 🏦 KuCoin بدلاً من Binance
# ============================================

@st.cache_resource
def get_exchange():
    """استخدام KuCoin بدلاً من Binance (يعمل في جميع الدول)"""
    return ccxt.kucoin({
        'rateLimit': 3000,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'spot',
            'adjustForTimeDifference': True,
        }
    })

@st.cache_data(ttl=CACHE_DURATION_DATA)
def fetch_candles_cached(symbol, timeframe='1h', limit=500):
    exchange = get_exchange()
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        st.error(f"❌ خطأ في جلب البيانات: {str(e)}")
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
        st.warning(f"⏳ انتظر {int(wait) + 1} ثواني قبل المحاولة مرة أخرى")
        return False
    st.session_state.last_click = current_time
    return True

# ============================================
# 🗄️ نظام إدارة المستخدمين باستخدام SQLite
# ============================================

class UserManager:
    def __init__(self, db_file="users.db"):
        self.db_file = db_file
        self._init_db()
        self._ensure_admin()
        
    def _init_db(self):
        """تهيئة قاعدة البيانات"""
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
            print(f"❌ خطأ في تهيئة قاعدة البيانات: {e}")
    
    def _ensure_admin(self):
        """التأكد من وجود حساب المسؤول"""
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
            print(f"❌ خطأ في التحقق من المسؤول: {e}")
    
    def _hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()
    
    def register_user(self, username, password, email=""):
        if len(username) < 3:
            return False, "❌ اسم المستخدم يجب أن يكون 3 أحرف على الأقل!"
        if len(password) < 4:
            return False, "❌ كلمة المرور يجب أن تكون 4 أحرف على الأقل!"
        
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM users WHERE username=?", (username,))
            if cursor.fetchone():
                conn.close()
                return False, "❌ اسم المستخدم موجود بالفعل!"
            
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
            return True, "✅ تم التسجيل بنجاح! انتظر تفعيل حسابك من قبل المسؤول."
            
        except Exception as e:
            return False, f"❌ خطأ في التسجيل: {str(e)}"
    
    def login_user(self, username, password):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM users WHERE username=?", (username,))
            user = cursor.fetchone()
            
            if not user:
                conn.close()
                return False, "❌ اسم المستخدم غير موجود!"
            
            if user[3] == 0:
                conn.close()
                return False, "⛔ حسابك غير مفعل! يرجى الدفع عبر تلغرام لتفعيل الحساب."
            
            if user[1] != self._hash_password(password):
                conn.close()
                return False, "❌ كلمة مرور خاطئة!"
            
            cursor.execute("UPDATE users SET last_login=? WHERE username=?", 
                         (datetime.now().isoformat(), username))
            conn.commit()
            conn.close()
            
            return True, "✅ تم تسجيل الدخول بنجاح!"
            
        except Exception as e:
            return False, f"❌ خطأ في تسجيل الدخول: {str(e)}"
    
    def activate_user(self, username):
        if username == ADMIN_USERNAME:
            return False, "❌ المسؤول مفعل تلقائياً!"
        
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM users WHERE username=?", (username,))
            if not cursor.fetchone():
                conn.close()
                return False, "❌ المستخدم غير موجود!"
            
            expiry = datetime.now() + timedelta(days=30)
            cursor.execute('''
                UPDATE users 
                SET active=1, payment_status='paid', payment_date=?, expiry_date=?
                WHERE username=?
            ''', (datetime.now().isoformat(), expiry.isoformat(), username))
            
            conn.commit()
            conn.close()
            return True, f"✅ تم تفعيل حساب {username} بنجاح!"
            
        except Exception as e:
            return False, f"❌ خطأ: {str(e)}"
    
    def deactivate_user(self, username):
        if username == ADMIN_USERNAME:
            return False, "❌ لا يمكن تعطيل المسؤول!"
        
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE users 
                SET active=0, payment_status='expired'
                WHERE username=?
            ''', (username,))
            
            conn.commit()
            conn.close()
            return True, f"✅ تم تعطيل حساب {username}!"
            
        except Exception as e:
            return False, f"❌ خطأ: {str(e)}"
    
    def delete_user(self, username):
        if username == ADMIN_USERNAME:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin=1")
            admin_count = cursor.fetchone()[0]
            conn.close()
            
            if admin_count <= 1:
                return False, "❌ لا يمكن حذف المسؤول الوحيد!"
        
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE username=?", (username,))
            conn.commit()
            conn.close()
            return True, "✅ تم حذف المستخدم بنجاح!"
            
        except Exception as e:
            return False, f"❌ خطأ: {str(e)}"
    
    def make_admin(self, username):
        if username == ADMIN_USERNAME:
            return False, "❌ هذا حساب المسؤول الرئيسي!"
        
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_admin=1 WHERE username=?", (username,))
            conn.commit()
            conn.close()
            return True, f"✅ تم ترقية {username} إلى مسؤول!"
        except Exception as e:
            return False, f"❌ خطأ: {str(e)}"
    
    def remove_admin(self, username):
        if username == ADMIN_USERNAME:
            return False, "❌ لا يمكن إلغاء صلاحية المسؤول الرئيسي!"
        
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
                UPDATE users 
                SET expiry_date=?, payment_status='paid', active=1
                WHERE username=?
            ''', (new_expiry.isoformat(), username))
            
            conn.commit()
            conn.close()
            return True, f"✅ تم تمديد اشتراك {username} لـ {days} يوماً"
        except Exception as e:
            return False, f"❌ خطأ: {str(e)}"
    
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
                result[user[0]] = {
                    "email": user[1],
                    "created_at": user[2]
                }
            return result
            
        except Exception as e:
            return {}
    
    def get_active_users(self):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT username, email, expiry_date 
                FROM users 
                WHERE active=1 AND is_admin=0
            ''')
            users = cursor.fetchall()
            conn.close()
            
            result = {}
            for user in users:
                result[user[0]] = {
                    "email": user[1],
                    "expiry_date": user[2]
                }
            return result
            
        except Exception as e:
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
            
        except Exception as e:
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
            
        except Exception as e:
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
            
        except Exception as e:
            return 0, 0, 0, 0

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
            
            if (current['volume'] > avg_volume * 2 and
                lower_wick > candle_range * 0.4 and
                current['close'] > current['open'] and
                current['low'] < prev['low'] and
                next_candle['close'] > current['high']):
                
                confirmed = next_next['close'] > next_candle['high']
                
                zone = {
                    'price': current['low'],
                    'timestamp': current.name if hasattr(current, 'name') else i,
                    'type': 'bullish',
                    'strength': volume_ratio,
                    'confirmed': confirmed,
                    'wick_ratio': lower_wick / candle_range if candle_range > 0 else 0,
                    'volume_ratio': volume_ratio,
                    'cluster_size': 1,
                    'timeframe': timeframe,
                    'color': 'rgba(255, 255, 0, 0.3)',
                    'description': '🟢 منطقة تصفية صاعدة - Bullish Liquidation'
                }
                zones.append(zone)
            
            elif (current['volume'] > avg_volume * 2 and
                  upper_wick > candle_range * 0.4 and
                  current['close'] < current['open'] and
                  current['high'] > prev['high'] and
                  next_candle['close'] < current['low']):
                
                confirmed = next_next['close'] < next_candle['low']
                
                zone = {
                    'price': current['high'],
                    'timestamp': current.name if hasattr(current, 'name') else i,
                    'type': 'bearish',
                    'strength': volume_ratio,
                    'confirmed': confirmed,
                    'wick_ratio': upper_wick / candle_range if candle_range > 0 else 0,
                    'volume_ratio': volume_ratio,
                    'cluster_size': 1,
                    'timeframe': timeframe,
                    'color': 'rgba(255, 255, 0, 0.3)',
                    'description': '🔴 منطقة تصفية هابطة - Bearish Liquidation'
                }
                zones.append(zone)
        
        zones = self._cluster_zones(zones, df)
        zones.sort(key=lambda x: x['strength'], reverse=True)
        self.liquidation_zones[timeframe] = zones
        return zones
    
    def _cluster_zones(self, zones, df):
        if len(zones) < 2:
            return zones
            
        prices = np.array([z['price'] for z in zones]).reshape(-1, 1)
        current_price = df['close'].iloc[-1] if len(df) > 0 else prices.mean()
        eps = current_price * 0.005
        
        clustering = DBSCAN(eps=eps, min_samples=2).fit(prices)
        labels = clustering.labels_
        
        clustered_zones = []
        unique_labels = set(labels)
        
        for label in unique_labels:
            if label == -1:
                for i, z in enumerate(zones):
                    if labels[i] == -1:
                        clustered_zones.append(z)
            else:
                cluster_indices = [i for i, l in enumerate(labels) if l == label]
                cluster_zones = [zones[i] for i in cluster_indices]
                
                merged_zone = {
                    'price': np.mean([z['price'] for z in cluster_zones]),
                    'timestamp': max([z['timestamp'] for z in cluster_zones]),
                    'type': max(set([z['type'] for z in cluster_zones]), key=[z['type'] for z in cluster_zones].count),
                    'strength': np.mean([z['strength'] for z in cluster_zones]),
                    'confirmed': any(z['confirmed'] for z in cluster_zones),
                    'wick_ratio': np.mean([z['wick_ratio'] for z in cluster_zones]),
                    'volume_ratio': np.mean([z['volume_ratio'] for z in cluster_zones]),
                    'cluster_size': len(cluster_zones),
                    'timeframe': cluster_zones[0]['timeframe'],
                    'color': 'rgba(255, 255, 0, 0.3)',
                    'description': f"{cluster_zones[0]['description']} (مجموعة {len(cluster_zones)} نقاط)"
                }
                clustered_zones.append(merged_zone)
        
        return clustered_zones

# ============================================
# 📊 فئة التحليل التقني
# ============================================

class CryptoAnalyzer:
    def __init__(self):
        self.exchange = get_exchange()
        self.blue_liquidity_lines = {}
        self.white_liquidity_levels = {}
        self.yellow_liquidation_zones = {}
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
        self.orange_magnetic_zones = {}
        self.orange_magnetic_zones_15m = {}
        self.orange_magnetic_zones_5m = {}
        self.orange_magnetic_zones_1m = {}
        self.orange_magnetic_zones_4h = {}
        self.liquidation_detector = LiquidationZonesDetector()
    
    def fetch_data(self, symbol):
        try:
            df_1h = fetch_candles_cached(symbol, '1h', MAX_CANDLES)
            df_4h = fetch_candles_cached(symbol, '4h', MAX_CANDLES // 2)
            
            if df_1h is not None:
                df_1h = calculate_indicators_cached(df_1h)
            if df_4h is not None:
                df_4h = calculate_indicators_cached(df_4h)
            
            if df_1h is not None:
                current_price = df_1h['close'].iloc[-1]
                self.calculate_blue_liquidity_lines(df_1h, df_4h, current_price, symbol)
                self.calculate_white_liquidity_levels(df_1h, df_4h, current_price, symbol)
                self.calculate_yellow_liquidation_zones(df_1h, symbol)
                self.calculate_orange_magnetic_zones(df_1h, current_price, symbol)
            
            if df_4h is not None:
                current_price_4h = df_4h['close'].iloc[-1]
                self.calculate_blue_liquidity_lines_4h(df_4h, current_price_4h, symbol)
                self.calculate_white_liquidity_levels_4h(df_4h, current_price_4h, symbol)
                self.calculate_yellow_liquidation_zones_4h(df_4h, symbol)
                self.calculate_orange_magnetic_zones_4h(df_4h, current_price_4h, symbol)
                
                liquidation_zones_4h = self.liquidation_detector.detect_liquidation_zones(df_4h, timeframe='4h')
                if liquidation_zones_4h:
                    if symbol not in self.yellow_liquidation_zones_4h:
                        self.yellow_liquidation_zones_4h[symbol] = []
                    for zone in liquidation_zones_4h:
                        zone['color'] = '#FFFF00'
                        zone['width'] = 2
                        zone['dash'] = 'dash'
                        self.yellow_liquidation_zones_4h[symbol].append(zone)
            
            return df_1h, df_4h
            
        except Exception as e:
            st.error(f"خطأ في جلب البيانات لـ {symbol}: {str(e)}")
            return None, None
    
    def fetch_data_15m(self, symbol):
        try:
            df_15m = fetch_candles_cached(symbol, '15m', MAX_CANDLES)
            
            if df_15m is not None:
                df_15m = self.calculate_indicators_15m(df_15m)
            
            if df_15m is not None:
                current_price_15m = df_15m['close'].iloc[-1]
                self.calculate_blue_liquidity_lines_15m(df_15m, current_price_15m, symbol)
                self.calculate_white_liquidity_levels_15m(df_15m, current_price_15m, symbol)
                self.calculate_yellow_liquidation_zones_15m(df_15m, symbol)
                self.calculate_orange_magnetic_zones_15m(df_15m, current_price_15m, symbol)
                
                liquidation_zones_15m = self.liquidation_detector.detect_liquidation_zones(df_15m, timeframe='15m')
                if liquidation_zones_15m:
                    if symbol not in self.yellow_liquidation_zones_15m:
                        self.yellow_liquidation_zones_15m[symbol] = []
                    for zone in liquidation_zones_15m:
                        zone['color'] = '#FFFF00'
                        zone['width'] = 2
                        zone['dash'] = 'dash'
                        self.yellow_liquidation_zones_15m[symbol].append(zone)
            
            return df_15m
            
        except Exception as e:
            st.error(f"خطأ في جلب البيانات 15m لـ {symbol}: {str(e)}")
            return None
    
    def fetch_data_5m(self, symbol):
        try:
            df_5m = fetch_candles_cached(symbol, '5m', MAX_CANDLES)
            
            if df_5m is not None:
                df_5m = self.calculate_indicators_5m(df_5m)
            
            if df_5m is not None:
                current_price_5m = df_5m['close'].iloc[-1]
                self.calculate_blue_liquidity_lines_5m(df_5m, current_price_5m, symbol)
                self.calculate_white_liquidity_levels_5m(df_5m, current_price_5m, symbol)
                self.calculate_yellow_liquidation_zones_5m(df_5m, symbol)
                self.calculate_orange_magnetic_zones_5m(df_5m, current_price_5m, symbol)
                
                liquidation_zones_5m = self.liquidation_detector.detect_liquidation_zones(df_5m, timeframe='5m')
                if liquidation_zones_5m:
                    if symbol not in self.yellow_liquidation_zones_5m:
                        self.yellow_liquidation_zones_5m[symbol] = []
                    for zone in liquidation_zones_5m:
                        zone['color'] = '#FFFF00'
                        zone['width'] = 2
                        zone['dash'] = 'dash'
                        self.yellow_liquidation_zones_5m[symbol].append(zone)
            
            return df_5m
            
        except Exception as e:
            st.error(f"خطأ في جلب البيانات 5m لـ {symbol}: {str(e)}")
            return None
    
    def fetch_data_1m(self, symbol):
        try:
            df_1m = fetch_candles_cached(symbol, '1m', MAX_CANDLES)
            
            if df_1m is not None:
                df_1m = self.calculate_indicators_1m(df_1m)
            
            if df_1m is not None:
                current_price_1m = df_1m['close'].iloc[-1]
                self.calculate_blue_liquidity_lines_1m(df_1m, current_price_1m, symbol)
                self.calculate_white_liquidity_levels_1m(df_1m, current_price_1m, symbol)
                self.calculate_yellow_liquidation_zones_1m(df_1m, symbol)
                self.calculate_orange_magnetic_zones_1m(df_1m, current_price_1m, symbol)
                
                liquidation_zones_1m = self.liquidation_detector.detect_liquidation_zones(df_1m, timeframe='1m')
                if liquidation_zones_1m:
                    if symbol not in self.yellow_liquidation_zones_1m:
                        self.yellow_liquidation_zones_1m[symbol] = []
                    for zone in liquidation_zones_1m:
                        zone['color'] = '#FFFF00'
                        zone['width'] = 2
                        zone['dash'] = 'dash'
                        self.yellow_liquidation_zones_1m[symbol].append(zone)
            
            return df_1m
            
        except Exception as e:
            st.error(f"خطأ في جلب البيانات 1m لـ {symbol}: {str(e)}")
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
        
        df['BB_upper'], df['BB_middle'], df['BB_lower'] = talib.BBANDS(
            close, timeperiod=20, nbdevup=2, nbdevdn=2
        )
        
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
        
        df['BB_upper'], df['BB_middle'], df['BB_lower'] = talib.BBANDS(
            close, timeperiod=20, nbdevup=1.5, nbdevdn=1.5
        )
        
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
        
        df['BB_upper'], df['BB_middle'], df['BB_lower'] = talib.BBANDS(
            close, timeperiod=20, nbdevup=1.2, nbdevdn=1.2
        )
        
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        df['VWAP'] = (df['volume'] * typical_price).cumsum() / df['volume'].cumsum()
        
        return df.dropna()
    
    def calculate_orange_magnetic_zones(self, df, current_price, symbol):
        orange_zones = []
        
        if df is None or len(df) < 100:
            self.orange_magnetic_zones[symbol] = orange_zones
            return
        
        close_prices = df['close'].values
        returns = np.diff(close_prices) / close_prices[:-1]
        price_velocity = np.mean(np.abs(returns[-20:])) * 100
        
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
        
        turning_points = np.array(turning_points[-30:]).reshape(-1, 1)
        
        if len(turning_points) >= 3:
            kmeans = KMeans(n_clusters=min(3, len(turning_points)//3), random_state=42, n_init=10)
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
                        attraction_direction = "جذب لأعلى"
                    else:
                        attraction_direction = "جذب لأسفل"
                    
                    if distance_pct < price_velocity * 2:
                        orange_zones.append({
                            'price': float(center_price),
                            'type': 'magnetic_zone',
                            'strength': float(strength),
                            'distance_pct': distance_pct,
                            'price_velocity': price_velocity,
                            'points_count': len(cluster_points),
                            'attraction_direction': attraction_direction,
                            'description': f'🧲 منطقة جذب مغناطيسي ({attraction_direction})',
                            'color': 'rgba(255, 165, 0, 0.5)',
                            'width': 2 + strength * 2,
                            'dash': 'dot' if strength < 0.5 else 'solid'
                        })
        
        orange_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.orange_magnetic_zones[symbol] = orange_zones[:5]
    
    def calculate_orange_magnetic_zones_15m(self, df, current_price, symbol):
        orange_zones = []
        
        if df is None or len(df) < 100:
            self.orange_magnetic_zones_15m[symbol] = orange_zones
            return
        
        close_prices = df['close'].values
        returns = np.diff(close_prices) / close_prices[:-1]
        price_velocity = np.mean(np.abs(returns[-30:])) * 100
        
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
        
        turning_points = np.array(turning_points[-40:]).reshape(-1, 1)
        
        if len(turning_points) >= 3:
            kmeans = KMeans(n_clusters=min(4, len(turning_points)//3), random_state=42, n_init=10)
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
                        attraction_direction = "جذب لأعلى"
                    else:
                        attraction_direction = "جذب لأسفل"
                    
                    if distance_pct < price_velocity * 2:
                        orange_zones.append({
                            'price': float(center_price),
                            'type': 'magnetic_zone_15m',
                            'strength': float(strength),
                            'distance_pct': distance_pct,
                            'price_velocity': price_velocity,
                            'points_count': len(cluster_points),
                            'attraction_direction': attraction_direction,
                            'description': f'🧲 منطقة جذب مغناطيسي 15m ({attraction_direction})',
                            'color': 'rgba(255, 165, 0, 0.5)',
                            'width': 2 + strength * 2,
                            'dash': 'dot' if strength < 0.5 else 'solid'
                        })
        
        orange_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.orange_magnetic_zones_15m[symbol] = orange_zones[:5]
    
    def calculate_orange_magnetic_zones_5m(self, df, current_price, symbol):
        orange_zones = []
        
        if df is None or len(df) < 80:
            self.orange_magnetic_zones_5m[symbol] = orange_zones
            return
        
        close_prices = df['close'].values
        returns = np.diff(close_prices) / close_prices[:-1]
        price_velocity = np.mean(np.abs(returns[-40:])) * 100
        
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
        
        turning_points = np.array(turning_points[-50:]).reshape(-1, 1)
        
        if len(turning_points) >= 3:
            kmeans = KMeans(n_clusters=min(5, len(turning_points)//3), random_state=42, n_init=10)
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
                        attraction_direction = "جذب لأعلى"
                    else:
                        attraction_direction = "جذب لأسفل"
                    
                    if distance_pct < price_velocity * 2:
                        orange_zones.append({
                            'price': float(center_price),
                            'type': 'magnetic_zone_5m',
                            'strength': float(strength),
                            'distance_pct': distance_pct,
                            'price_velocity': price_velocity,
                            'points_count': len(cluster_points),
                            'attraction_direction': attraction_direction,
                            'description': f'🧲 منطقة جذب مغناطيسي 5m ({attraction_direction})',
                            'color': 'rgba(255, 165, 0, 0.5)',
                            'width': 2 + strength * 2,
                            'dash': 'dot' if strength < 0.5 else 'solid'
                        })
        
        orange_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.orange_magnetic_zones_5m[symbol] = orange_zones[:6]
    
    def calculate_orange_magnetic_zones_1m(self, df, current_price, symbol):
        orange_zones = []
        
        if df is None or len(df) < 60:
            self.orange_magnetic_zones_1m[symbol] = orange_zones
            return
        
        close_prices = df['close'].values
        returns = np.diff(close_prices) / close_prices[:-1]
        price_velocity = np.mean(np.abs(returns[-50:])) * 100
        
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
        
        turning_points = np.array(turning_points[-60:]).reshape(-1, 1)
        
        if len(turning_points) >= 3:
            kmeans = KMeans(n_clusters=min(6, len(turning_points)//3), random_state=42, n_init=10)
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
                        attraction_direction = "جذب لأعلى"
                    else:
                        attraction_direction = "جذب لأسفل"
                    
                    if distance_pct < price_velocity * 1.5:
                        orange_zones.append({
                            'price': float(center_price),
                            'type': 'magnetic_zone_1m',
                            'strength': float(strength),
                            'distance_pct': distance_pct,
                            'price_velocity': price_velocity,
                            'points_count': len(cluster_points),
                            'attraction_direction': attraction_direction,
                            'description': f'🧲 منطقة جذب مغناطيسي 1m ({attraction_direction})',
                            'color': 'rgba(255, 165, 0, 0.5)',
                            'width': 1.5 + strength * 2,
                            'dash': 'dot' if strength < 0.5 else 'solid'
                        })
        
        orange_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.orange_magnetic_zones_1m[symbol] = orange_zones[:7]
    
    def calculate_orange_magnetic_zones_4h(self, df, current_price, symbol):
        orange_zones = []
        
        if df is None or len(df) < 50:
            self.orange_magnetic_zones_4h[symbol] = orange_zones
            return
        
        close_prices = df['close'].values
        returns = np.diff(close_prices) / close_prices[:-1]
        price_velocity = np.mean(np.abs(returns[-15:])) * 100
        
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
        
        turning_points = np.array(turning_points[-20:]).reshape(-1, 1)
        
        if len(turning_points) >= 3:
            kmeans = KMeans(n_clusters=min(3, len(turning_points)//3), random_state=42, n_init=10)
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
                        attraction_direction = "جذب لأعلى"
                    else:
                        attraction_direction = "جذب لأسفل"
                    
                    if distance_pct < price_velocity * 2:
                        orange_zones.append({
                            'price': float(center_price),
                            'type': 'magnetic_zone_4h',
                            'strength': float(strength),
                            'distance_pct': distance_pct,
                            'price_velocity': price_velocity,
                            'points_count': len(cluster_points),
                            'attraction_direction': attraction_direction,
                            'description': f'🧲 منطقة جذب مغناطيسي 4H ({attraction_direction})',
                            'color': 'rgba(255, 165, 0, 0.5)',
                            'width': 2 + strength * 2,
                            'dash': 'dot' if strength < 0.5 else 'solid'
                        })
        
        orange_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.orange_magnetic_zones_4h[symbol] = orange_zones[:4]
    
    def calculate_yellow_liquidation_zones(self, df, symbol):
        yellow_zones = []
        
        if df is None or len(df) < 50:
            self.yellow_liquidation_zones[symbol] = yellow_zones
            return
        
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
                    'volume': 0,
                    'description': f'🟡 منطقة دعم صفراء (قوة: {strength:.2f})',
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
                    'volume': 0,
                    'description': f'🟡 منطقة مقاومة صفراء (قوة: {strength:.2f})',
                    'color': '#FFFF00',
                    'width': 1 + (strength * 2),
                    'dash': 'dash',
                    'distance_pct': abs(price - current_price) / current_price * 100
                })
        
        yellow_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.yellow_liquidation_zones[symbol] = yellow_zones[:5]
    
    def calculate_yellow_liquidation_zones_15m(self, df, symbol):
        yellow_zones = []
        
        if df is None or len(df) < 50:
            self.yellow_liquidation_zones_15m[symbol] = yellow_zones
            return
        
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
                    'volume': 0,
                    'description': f'🟡 منطقة دعم 15m صفراء (قوة: {strength:.2f})',
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
                    'volume': 0,
                    'description': f'🟡 منطقة مقاومة 15m صفراء (قوة: {strength:.2f})',
                    'color': '#FFFF00',
                    'width': 1 + (strength * 2),
                    'dash': 'dash',
                    'distance_pct': abs(price - current_price) / current_price * 100
                })
        
        yellow_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.yellow_liquidation_zones_15m[symbol] = yellow_zones[:5]
    
    def calculate_yellow_liquidation_zones_5m(self, df, symbol):
        yellow_zones = []
        
        if df is None or len(df) < 30:
            self.yellow_liquidation_zones_5m[symbol] = yellow_zones
            return
        
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
                    'volume': 0,
                    'description': f'🟡 منطقة دعم 5m صفراء (قوة: {strength:.2f})',
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
                    'volume': 0,
                    'description': f'🟡 منطقة مقاومة 5m صفراء (قوة: {strength:.2f})',
                    'color': '#FFFF00',
                    'width': 1 + (strength * 2),
                    'dash': 'dash',
                    'distance_pct': abs(price - current_price) / current_price * 100
                })
        
        yellow_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.yellow_liquidation_zones_5m[symbol] = yellow_zones[:6]
    
    def calculate_yellow_liquidation_zones_1m(self, df, symbol):
        yellow_zones = []
        
        if df is None or len(df) < 30:
            self.yellow_liquidation_zones_1m[symbol] = yellow_zones
            return
        
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
                    'volume': 0,
                    'description': f'🟡 منطقة دعم 1m صفراء (قوة: {strength:.2f})',
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
                    'volume': 0,
                    'description': f'🟡 منطقة مقاومة 1m صفراء (قوة: {strength:.2f})',
                    'color': '#FFFF00',
                    'width': 1 + (strength * 1.5),
                    'dash': 'dash',
                    'distance_pct': abs(price - current_price) / current_price * 100
                })
        
        yellow_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.yellow_liquidation_zones_1m[symbol] = yellow_zones[:8]
    
    def calculate_yellow_liquidation_zones_4h(self, df, symbol):
        yellow_zones = []
        
        if df is None or len(df) < 50:
            self.yellow_liquidation_zones_4h[symbol] = yellow_zones
            return
        
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
                    'volume': 0,
                    'description': f'🟡 منطقة دعم 4H صفراء (قوة: {strength:.2f})',
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
                    'volume': 0,
                    'description': f'🟡 منطقة مقاومة 4H صفراء (قوة: {strength:.2f})',
                    'color': '#FFFF00',
                    'width': 1 + (strength * 2),
                    'dash': 'dash',
                    'distance_pct': abs(price - current_price) / current_price * 100
                })
        
        yellow_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.yellow_liquidation_zones_4h[symbol] = yellow_zones[:5]
    
    def calculate_blue_liquidity_lines(self, df_1h, df_4h, current_price, symbol):
        blue_lines = []
        
        if df_1h is None or len(df_1h) < 50:
            self.blue_liquidity_lines[symbol] = blue_lines
            return
        
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
                    'description': '🔵 رفض شرائي قوي (مطرقة)',
                    'color': '#1E90FF',
                    'width': 2 + (lower_wick/total_range * 3),
                    'dash': 'solid',
                    'wick_ratio': lower_wick/total_range
                })
            
            if (upper_wick > body_size * 2 and 
                lower_wick < body_size * 0.5 and
                next_candle['close'] < candle['close']):
                
                blue_lines.append({
                    'price': candle['high'],
                    'type': 'sell_liquidity',
                    'strength': min(0.8 + (upper_wick/total_range), 0.95),
                    'timeframe': 'immediate',
                    'description': '🔵 رفض بيعي قوي (رجل مشنوق)',
                    'color': '#1E90FF',
                    'width': 2 + (upper_wick/total_range * 3),
                    'dash': 'solid',
                    'wick_ratio': upper_wick/total_range
                })
            
            if (body_size / total_range < 0.1 and
                max(upper_wick, lower_wick) > body_size * 3):
                
                if next_candle['close'] > candle['close']:
                    blue_lines.append({
                        'price': candle['low'],
                        'type': 'buy_liquidity',
                        'strength': 0.6,
                        'timeframe': 'immediate',
                        'description': '🔵 دعم عند دوجي',
                        'color': '#1E90FF',
                        'width': 1.5,
                        'dash': 'dot'
                    })
                else:
                    blue_lines.append({
                        'price': candle['high'],
                        'type': 'sell_liquidity',
                        'strength': 0.6,
                        'timeframe': 'immediate',
                        'description': '🔵 مقاومة عند دوجي',
                        'color': '#1E90FF',
                        'width': 1.5,
                        'dash': 'dot'
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
                    'description': '🔵 مقاومة قريبة',
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
                    'description': '🔵 دعم قريب',
                    'color': '#00BFFF',
                    'width': 2,
                    'dash': 'dash'
                })
        
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
                    'description': '🔵 رفض شرائي 15m قوي (مطرقة)',
                    'color': '#1E90FF',
                    'width': 2 + (lower_wick/total_range * 3),
                    'dash': 'solid',
                    'wick_ratio': lower_wick/total_range
                })
            
            if (upper_wick > body_size * 2 and 
                lower_wick < body_size * 0.3 and
                next_candle['close'] < candle['close']):
                
                blue_lines.append({
                    'price': candle['high'],
                    'type': 'sell_liquidity_15m',
                    'strength': min(0.8 + (upper_wick/total_range), 0.95),
                    'timeframe': 'immediate_15m',
                    'description': '🔵 رفض بيعي 15m قوي (رجل مشنوق)',
                    'color': '#1E90FF',
                    'width': 2 + (upper_wick/total_range * 3),
                    'dash': 'solid',
                    'wick_ratio': upper_wick/total_range
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
                    'description': '🔵 مقاومة 15m قريبة',
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
                    'description': '🔵 دعم 15m قريب',
                    'color': '#00BFFF',
                    'width': 2,
                    'dash': 'dash'
                })
        
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
                    'description': '🔵 رفض شرائي 5m قوي (مطرقة)',
                    'color': '#1E90FF',
                    'width': 2 + (lower_wick/total_range * 3),
                    'dash': 'solid',
                    'wick_ratio': lower_wick/total_range
                })
            
            if (upper_wick > body_size * 1.8 and 
                lower_wick < body_size * 0.4 and
                next_candle['close'] < candle['close']):
                
                blue_lines.append({
                    'price': candle['high'],
                    'type': 'sell_liquidity_5m',
                    'strength': min(0.8 + (upper_wick/total_range), 0.95),
                    'timeframe': 'immediate_5m',
                    'description': '🔵 رفض بيعي 5m قوي (رجل مشنوق)',
                    'color': '#1E90FF',
                    'width': 2 + (upper_wick/total_range * 3),
                    'dash': 'solid',
                    'wick_ratio': upper_wick/total_range
                })
            
            if (body_size / total_range < 0.15 and
                max(upper_wick, lower_wick) > body_size * 2):
                
                if next_candle['close'] > candle['close']:
                    blue_lines.append({
                        'price': candle['low'],
                        'type': 'buy_liquidity_5m',
                        'strength': 0.6,
                        'timeframe': 'immediate_5m',
                        'description': '🔵 دعم 5m عند دوجي',
                        'color': '#1E90FF',
                        'width': 1.5,
                        'dash': 'dot'
                    })
                else:
                    blue_lines.append({
                        'price': candle['high'],
                        'type': 'sell_liquidity_5m',
                        'strength': 0.6,
                        'timeframe': 'immediate_5m',
                        'description': '🔵 مقاومة 5m عند دوجي',
                        'color': '#1E90FF',
                        'width': 1.5,
                        'dash': 'dot'
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
                    'description': '🔵 مقاومة 5m قريبة',
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
                    'description': '🔵 دعم 5m قريب',
                    'color': '#00BFFF',
                    'width': 2,
                    'dash': 'dash'
                })
        
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
                    'description': '🔵 رفض شرائي 1m سريع',
                    'color': '#1E90FF',
                    'width': 1.5 + (lower_wick/total_range * 2),
                    'dash': 'solid',
                    'wick_ratio': lower_wick/total_range
                })
            
            if (upper_wick > body_size * 1.5 and 
                lower_wick < body_size * 0.5 and
                next_candle['close'] < candle['close']):
                
                blue_lines.append({
                    'price': candle['high'],
                    'type': 'sell_liquidity_1m',
                    'strength': min(0.7 + (upper_wick/total_range), 0.9),
                    'timeframe': 'immediate_1m',
                    'description': '🔵 رفض بيعي 1m سريع',
                    'color': '#1E90FF',
                    'width': 1.5 + (upper_wick/total_range * 2),
                    'dash': 'solid',
                    'wick_ratio': upper_wick/total_range
                })
            
            if (body_size / total_range < 0.2 and
                max(upper_wick, lower_wick) > body_size * 1.5):
                
                if next_candle['close'] > candle['close']:
                    blue_lines.append({
                        'price': candle['low'],
                        'type': 'buy_liquidity_1m',
                        'strength': 0.55,
                        'timeframe': 'immediate_1m',
                        'description': '🔵 دعم 1m سريع',
                        'color': '#1E90FF',
                        'width': 1.2,
                        'dash': 'dot'
                    })
                else:
                    blue_lines.append({
                        'price': candle['high'],
                        'type': 'sell_liquidity_1m',
                        'strength': 0.55,
                        'timeframe': 'immediate_1m',
                        'description': '🔵 مقاومة 1m سريعة',
                        'color': '#1E90FF',
                        'width': 1.2,
                        'dash': 'dot'
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
                    'description': '🔵 مقاومة 1m قريبة',
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
                    'description': '🔵 دعم 1m قريب',
                    'color': '#00BFFF',
                    'width': 1.8,
                    'dash': 'dash'
                })
        
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
                    'description': '🔵 رفض شرائي 4H قوي (مطرقة)',
                    'color': '#1E90FF',
                    'width': 2 + (lower_wick/total_range * 3),
                    'dash': 'solid',
                    'wick_ratio': lower_wick/total_range
                })
            
            if (upper_wick > body_size * 2 and 
                lower_wick < body_size * 0.5 and
                next_candle['close'] < candle['close']):
                
                blue_lines.append({
                    'price': candle['high'],
                    'type': 'sell_liquidity_4h',
                    'strength': min(0.8 + (upper_wick/total_range), 0.95),
                    'timeframe': 'immediate_4h',
                    'description': '🔵 رفض بيعي 4H قوي (رجل مشنوق)',
                    'color': '#1E90FF',
                    'width': 2 + (upper_wick/total_range * 3),
                    'dash': 'solid',
                    'wick_ratio': upper_wick/total_range
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
                    'description': '🔵 مقاومة 4H قريبة',
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
                    'description': '🔵 دعم 4H قريب',
                    'color': '#00BFFF',
                    'width': 2,
                    'dash': 'dash'
                })
        
        unique_lines = []
        seen_prices = set()
        for line in blue_lines:
            if line['price'] not in seen_prices:
                seen_prices.add(line['price'])
                unique_lines.append(line)
        
        self.blue_liquidity_lines_4h[symbol] = unique_lines
    
    def calculate_white_liquidity_levels(self, df_1h, df_4h, current_price, symbol):
        white_levels = []
        
        if df_1h is None or df_4h is None:
            self.white_liquidity_levels[symbol] = white_levels
            return
        
        support_4h, resistance_4h = self.find_strong_support_resistance(df_4h, window=12)
        
        for price, strength in support_4h[:3]:
            if strength > 0.7:
                distance_pct = abs(price - current_price) / current_price * 100
                if distance_pct <= 5:
                    white_levels.append({
                        'price': price,
                        'type': 'strong_support',
                        'strength': strength,
                        'description': f'⚪ دعم قوي 4H (قوة: {strength:.2f})',
                        'color': 'white',
                        'width': 1 + (strength * 2),
                        'dash': 'dash'
                    })
        
        for price, strength in resistance_4h[:3]:
            if strength > 0.7:
                distance_pct = abs(price - current_price) / current_price * 100
                if distance_pct <= 5:
                    white_levels.append({
                        'price': price,
                        'type': 'strong_resistance',
                        'strength': strength,
                        'description': f'⚪ مقاومة قوي 4H (قوة: {strength:.2f})',
                        'color': 'white',
                        'width': 1 + (strength * 2),
                        'dash': 'dash'
                    })
        
        self.white_liquidity_levels[symbol] = white_levels
    
    def calculate_white_liquidity_levels_15m(self, df_15m, current_price, symbol):
        white_levels = []
        
        if df_15m is None:
            self.white_liquidity_levels_15m[symbol] = white_levels
            return
        
        support_15m, resistance_15m = self.find_strong_support_resistance_15m(df_15m, window=15)
        
        for price, strength in support_15m[:4]:
            if strength > 0.6:
                distance_pct = abs(price - current_price) / current_price * 100
                if distance_pct <= 3:
                    white_levels.append({
                        'price': price,
                        'type': 'strong_support_15m',
                        'strength': strength,
                        'description': f'⚪ دعم قوي 15m (قوة: {strength:.2f})',
                        'color': 'white',
                        'width': 1 + (strength * 2),
                        'dash': 'dash'
                    })
        
        for price, strength in resistance_15m[:4]:
            if strength > 0.6:
                distance_pct = abs(price - current_price) / current_price * 100
                if distance_pct <= 3:
                    white_levels.append({
                        'price': price,
                        'type': 'strong_resistance_15m',
                        'strength': strength,
                        'description': f'⚪ مقاومة قوي 15m (قوة: {strength:.2f})',
                        'color': 'white',
                        'width': 1 + (strength * 2),
                        'dash': 'dash'
                    })
        
        self.white_liquidity_levels_15m[symbol] = white_levels
    
    def calculate_white_liquidity_levels_5m(self, df_5m, current_price, symbol):
        white_levels = []
        
        if df_5m is None:
            self.white_liquidity_levels_5m[symbol] = white_levels
            return
        
        support_5m, resistance_5m = self.find_strong_support_resistance_5m(df_5m, window=10)
        
        for price, strength in support_5m[:5]:
            if strength > 0.55:
                distance_pct = abs(price - current_price) / current_price * 100
                if distance_pct <= 2:
                    white_levels.append({
                        'price': price,
                        'type': 'strong_support_5m',
                        'strength': strength,
                        'description': f'⚪ دعم قوي 5m (قوة: {strength:.2f})',
                        'color': 'white',
                        'width': 1 + (strength * 2),
                        'dash': 'dash'
                    })
        
        for price, strength in resistance_5m[:5]:
            if strength > 0.55:
                distance_pct = abs(price - current_price) / current_price * 100
                if distance_pct <= 2:
                    white_levels.append({
                        'price': price,
                        'type': 'strong_resistance_5m',
                        'strength': strength,
                        'description': f'⚪ مقاومة قوي 5m (قوة: {strength:.2f})',
                        'color': 'white',
                        'width': 1 + (strength * 2),
                        'dash': 'dash'
                    })
        
        self.white_liquidity_levels_5m[symbol] = white_levels
    
    def calculate_white_liquidity_levels_1m(self, df_1m, current_price, symbol):
        white_levels = []
        
        if df_1m is None:
            self.white_liquidity_levels_1m[symbol] = white_levels
            return
        
        support_1m, resistance_1m = self.find_strong_support_resistance_1m(df_1m, window=7)
        
        for price, strength in support_1m[:6]:
            if strength > 0.5:
                distance_pct = abs(price - current_price) / current_price * 100
                if distance_pct <= 1.5:
                    white_levels.append({
                        'price': price,
                        'type': 'strong_support_1m',
                        'strength': strength,
                        'description': f'⚪ دعم قوي 1m (قوة: {strength:.2f})',
                        'color': 'white',
                        'width': 1 + (strength * 1.5),
                        'dash': 'dash'
                    })
        
        for price, strength in resistance_1m[:6]:
            if strength > 0.5:
                distance_pct = abs(price - current_price) / current_price * 100
                if distance_pct <= 1.5:
                    white_levels.append({
                        'price': price,
                        'type': 'strong_resistance_1m',
                        'strength': strength,
                        'description': f'⚪ مقاومة قوي 1m (قوة: {strength:.2f})',
                        'color': 'white',
                        'width': 1 + (strength * 1.5),
                        'dash': 'dash'
                    })
        
        self.white_liquidity_levels_1m[symbol] = white_levels
    
    def calculate_white_liquidity_levels_4h(self, df_4h, current_price, symbol):
        white_levels = []
        
        if df_4h is None:
            self.white_liquidity_levels_4h[symbol] = white_levels
            return
        
        support_4h, resistance_4h = self.find_strong_support_resistance(df_4h, window=20)
        
        for price, strength in support_4h[:3]:
            if strength > 0.7:
                distance_pct = abs(price - current_price) / current_price * 100
                if distance_pct <= 8:
                    white_levels.append({
                        'price': price,
                        'type': 'strong_support_4h',
                        'strength': strength,
                        'description': f'⚪ دعم قوي 4H (قوة: {strength:.2f})',
                        'color': 'white',
                        'width': 1 + (strength * 2),
                        'dash': 'dash'
                    })
        
        for price, strength in resistance_4h[:3]:
            if strength > 0.7:
                distance_pct = abs(price - current_price) / current_price * 100
                if distance_pct <= 8:
                    white_levels.append({
                        'price': price,
                        'type': 'strong_resistance_4h',
                        'strength': strength,
                        'description': f'⚪ مقاومة قوي 4H (قوة: {strength:.2f})',
                        'color': 'white',
                        'width': 1 + (strength * 2),
                        'dash': 'dash'
                    })
        
        self.white_liquidity_levels_4h[symbol] = white_levels
    
    def find_strong_support_resistance(self, df, window=20):
        if len(df) < window * 2:
            return [], []
        
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
                print(f"DBSCAN failed: {e}, using simple clustering")
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
    
    def find_strong_support_resistance_15m(self, df, window=15):
        if len(df) < window * 2:
            return [], []
        
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
            except Exception as e:
                print(f"DBSCAN failed: {e}, using simple clustering")
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
    
    def find_strong_support_resistance_5m(self, df, window=10):
        if len(df) < window * 2:
            return [], []
        
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
            except Exception as e:
                print(f"DBSCAN failed: {e}, using simple clustering")
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
    
    def find_strong_support_resistance_1m(self, df, window=7):
        if len(df) < window * 2:
            return [], []
        
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
            except Exception as e:
                print(f"DBSCAN failed: {e}, using simple clustering")
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
    
    def create_main_chart(self, df_1h, symbol):
        if df_1h is None or df_1h.empty:
            return go.Figure()
        
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.6, 0.2, 0.2],
            subplot_titles=("الرسم البياني للسعر - 1 ساعة", "الحجم", "RSI")
        )
        
        fig.add_trace(go.Candlestick(
            x=df_1h['timestamp'],
            open=df_1h['open'],
            high=df_1h['high'],
            low=df_1h['low'],
            close=df_1h['close'],
            name='السعر',
            increasing_line_color='#00ff88',
            decreasing_line_color='#ff0066'
        ), row=1, col=1)
        
        if symbol in self.blue_liquidity_lines:
            for line in self.blue_liquidity_lines[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_1h['timestamp'].iloc[0],
                    x1=df_1h['timestamp'].iloc[-1],
                    y0=line['price'],
                    y1=line['price'],
                    line=dict(
                        color=line['color'],
                        width=line['width'],
                        dash=line['dash']
                    ),
                    name=line['description'],
                    row=1, col=1
                )
                
                fig.add_annotation(
                    x=df_1h['timestamp'].iloc[-1],
                    y=line['price'],
                    text=line['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=40,
                    ay=0,
                    bgcolor='rgba(30, 144, 255, 0.8)',
                    bordercolor='#1E90FF',
                    borderwidth=2,
                    font=dict(color='white', size=10),
                    row=1, col=1
                )
        
        if symbol in self.white_liquidity_levels:
            for level in self.white_liquidity_levels[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_1h['timestamp'].iloc[0],
                    x1=df_1h['timestamp'].iloc[-1],
                    y0=level['price'],
                    y1=level['price'],
                    line=dict(
                        color=level['color'],
                        width=level['width'],
                        dash=level['dash']
                    ),
                    name=level['description'],
                    row=1, col=1
                )
                
                fig.add_annotation(
                    x=df_1h['timestamp'].iloc[-1],
                    y=level['price'],
                    text=level['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=40,
                    ay=0,
                    bgcolor='rgba(255, 255, 255, 0.8)',
                    bordercolor='white',
                    borderwidth=2,
                    font=dict(color='black', size=10),
                    row=1, col=1
                )
        
        if symbol in self.yellow_liquidation_zones:
            for zone in self.yellow_liquidation_zones[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_1h['timestamp'].iloc[0],
                    x1=df_1h['timestamp'].iloc[-1],
                    y0=zone['price'],
                    y1=zone['price'],
                    line=dict(
                        color=zone['color'],
                        width=zone['width'],
                        dash=zone['dash']
                    ),
                    name=zone['description'],
                    row=1, col=1
                )
                
                fig.add_annotation(
                    x=df_1h['timestamp'].iloc[-1],
                    y=zone['price'],
                    text=zone['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=40,
                    ay=0,
                    bgcolor='rgba(255, 255, 0, 0.8)',
                    bordercolor='#FFFF00',
                    borderwidth=2,
                    font=dict(color='black', size=10),
                    row=1, col=1
                )
        
        if symbol in self.orange_magnetic_zones:
            for zone in self.orange_magnetic_zones[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df_1h['timestamp'].iloc[0],
                    x1=df_1h['timestamp'].iloc[-1],
                    y0=zone['price'],
                    y1=zone['price'],
                    line=dict(
                        color=zone['color'],
                        width=zone['width'],
                        dash=zone['dash']
                    ),
                    name=zone['description'],
                    row=1, col=1
                )
                
                fig.add_annotation(
                    x=df_1h['timestamp'].iloc[-1],
                    y=zone['price'],
                    text=zone['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=40,
                    ay=0,
                    bgcolor='rgba(255, 165, 0, 0.8)',
                    bordercolor='#FFA500',
                    borderwidth=2,
                    font=dict(color='white', size=10),
                    row=1, col=1
                )
        
        fig.add_trace(go.Bar(
            x=df_1h['timestamp'],
            y=df_1h['volume'],
            name='الحجم',
            marker_color='#7f8c8d',
            opacity=0.7
        ), row=2, col=1)
        
        if 'RSI' in df_1h.columns:
            fig.add_trace(go.Scatter(
                x=df_1h['timestamp'],
                y=df_1h['RSI'],
                name='RSI',
                line=dict(color='#ff00ff', width=1.5)
            ), row=3, col=1)
            
            fig.add_shape(
                type='rect',
                x0=df_1h['timestamp'].iloc[0],
                x1=df_1h['timestamp'].iloc[-1],
                y0=70,
                y1=100,
                fillcolor='rgba(255, 0, 0, 0.2)',
                line=dict(width=0),
                row=3, col=1
            )
            
            fig.add_shape(
                type='rect',
                x0=df_1h['timestamp'].iloc[0],
                x1=df_1h['timestamp'].iloc[-1],
                y0=0,
                y1=30,
                fillcolor='rgba(0, 255, 0, 0.2)',
                line=dict(width=0),
                row=3, col=1
            )
        
        fig.update_layout(
            title=f"📊 {symbol} - 1 ساعة",
            height=1000,
            showlegend=True,
            hovermode="x unified",
            plot_bgcolor='rgba(10, 10, 30, 0.5)',
            paper_bgcolor='rgba(10, 10, 30, 0.5)',
            margin=dict(l=20, r=20, t=80, b=20),
            font=dict(color='#e0f0ff'),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        
        fig.update_xaxes(rangeslider_visible=False, row=1, col=1)
        
        return fig
    
    def create_15m_chart(self, df_15m, symbol):
        if df_15m is None or df_15m.empty:
            return go.Figure()
        
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.6, 0.2, 0.2],
            subplot_titles=("الرسم البياني للسعر - 15 دقيقة", "الحجم", "RSI")
        )
        
        fig.add_trace(go.Candlestick(
            x=df_15m['timestamp'],
            open=df_15m['open'],
            high=df_15m['high'],
            low=df_15m['low'],
            close=df_15m['close'],
            name='السعر',
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
                    line=dict(
                        color=line['color'],
                        width=line['width'],
                        dash=line['dash']
                    ),
                    name=line['description'],
                    row=1, col=1
                )
                
                fig.add_annotation(
                    x=df_15m['timestamp'].iloc[-1],
                    y=line['price'],
                    text=line['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=40,
                    ay=0,
                    bgcolor='rgba(30, 144, 255, 0.8)',
                    bordercolor='#1E90FF',
                    borderwidth=2,
                    font=dict(color='white', size=10),
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
                    line=dict(
                        color=level['color'],
                        width=level['width'],
                        dash=level['dash']
                    ),
                    name=level['description'],
                    row=1, col=1
                )
                
                fig.add_annotation(
                    x=df_15m['timestamp'].iloc[-1],
                    y=level['price'],
                    text=level['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=40,
                    ay=0,
                    bgcolor='rgba(255, 255, 255, 0.8)',
                    bordercolor='white',
                    borderwidth=2,
                    font=dict(color='black', size=10),
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
                    line=dict(
                        color=zone['color'],
                        width=zone['width'],
                        dash=zone['dash']
                    ),
                    name=zone['description'],
                    row=1, col=1
                )
                
                fig.add_annotation(
                    x=df_15m['timestamp'].iloc[-1],
                    y=zone['price'],
                    text=zone['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=40,
                    ay=0,
                    bgcolor='rgba(255, 255, 0, 0.8)',
                    bordercolor='#FFFF00',
                    borderwidth=2,
                    font=dict(color='black', size=10),
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
                    line=dict(
                        color=zone['color'],
                        width=zone['width'],
                        dash=zone['dash']
                    ),
                    name=zone['description'],
                    row=1, col=1
                )
                
                fig.add_annotation(
                    x=df_15m['timestamp'].iloc[-1],
                    y=zone['price'],
                    text=zone['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=40,
                    ay=0,
                    bgcolor='rgba(255, 165, 0, 0.8)',
                    bordercolor='#FFA500',
                    borderwidth=2,
                    font=dict(color='white', size=10),
                    row=1, col=1
                )
        
        fig.add_trace(go.Bar(
            x=df_15m['timestamp'],
            y=df_15m['volume'],
            name='الحجم',
            marker_color='#7f8c8d',
            opacity=0.7
        ), row=2, col=1)
        
        if 'RSI' in df_15m.columns:
            fig.add_trace(go.Scatter(
                x=df_15m['timestamp'],
                y=df_15m['RSI'],
                name='RSI',
                line=dict(color='#ff00ff', width=1.5)
            ), row=3, col=1)
            
            fig.add_shape(
                type='rect',
                x0=df_15m['timestamp'].iloc[0],
                x1=df_15m['timestamp'].iloc[-1],
                y0=70,
                y1=100,
                fillcolor='rgba(255, 0, 0, 0.2)',
                line=dict(width=0),
                row=3, col=1
            )
            
            fig.add_shape(
                type='rect',
                x0=df_15m['timestamp'].iloc[0],
                x1=df_15m['timestamp'].iloc[-1],
                y0=0,
                y1=30,
                fillcolor='rgba(0, 255, 0, 0.2)',
                line=dict(width=0),
                row=3, col=1
            )
        
        fig.update_layout(
            title=f"📊 {symbol} - 15 دقيقة",
            height=1000,
            showlegend=True,
            hovermode="x unified",
            plot_bgcolor='rgba(10, 10, 30, 0.5)',
            paper_bgcolor='rgba(10, 10, 30, 0.5)',
            margin=dict(l=20, r=20, t=80, b=20),
            font=dict(color='#e0f0ff'),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        
        fig.update_xaxes(rangeslider_visible=False, row=1, col=1)
        
        return fig
    
    def create_5m_chart(self, df_5m, symbol):
        if df_5m is None or df_5m.empty:
            return go.Figure()
        
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.6, 0.2, 0.2],
            subplot_titles=("الرسم البياني للسعر - 5 دقائق", "الحجم", "RSI")
        )
        
        fig.add_trace(go.Candlestick(
            x=df_5m['timestamp'],
            open=df_5m['open'],
            high=df_5m['high'],
            low=df_5m['low'],
            close=df_5m['close'],
            name='السعر',
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
                    line=dict(
                        color=line['color'],
                        width=line['width'],
                        dash=line['dash']
                    ),
                    name=line['description'],
                    row=1, col=1
                )
                
                fig.add_annotation(
                    x=df_5m['timestamp'].iloc[-1],
                    y=line['price'],
                    text=line['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=40,
                    ay=0,
                    bgcolor='rgba(30, 144, 255, 0.8)',
                    bordercolor='#1E90FF',
                    borderwidth=2,
                    font=dict(color='white', size=10),
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
                    line=dict(
                        color=level['color'],
                        width=level['width'],
                        dash=level['dash']
                    ),
                    name=level['description'],
                    row=1, col=1
                )
                
                fig.add_annotation(
                    x=df_5m['timestamp'].iloc[-1],
                    y=level['price'],
                    text=level['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=40,
                    ay=0,
                    bgcolor='rgba(255, 255, 255, 0.8)',
                    bordercolor='white',
                    borderwidth=2,
                    font=dict(color='black', size=10),
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
                    line=dict(
                        color=zone['color'],
                        width=zone['width'],
                        dash=zone['dash']
                    ),
                    name=zone['description'],
                    row=1, col=1
                )
                
                fig.add_annotation(
                    x=df_5m['timestamp'].iloc[-1],
                    y=zone['price'],
                    text=zone['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=40,
                    ay=0,
                    bgcolor='rgba(255, 255, 0, 0.8)',
                    bordercolor='#FFFF00',
                    borderwidth=2,
                    font=dict(color='black', size=10),
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
                    line=dict(
                        color=zone['color'],
                        width=zone['width'],
                        dash=zone['dash']
                    ),
                    name=zone['description'],
                    row=1, col=1
                )
                
                fig.add_annotation(
                    x=df_5m['timestamp'].iloc[-1],
                    y=zone['price'],
                    text=zone['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=40,
                    ay=0,
                    bgcolor='rgba(255, 165, 0, 0.8)',
                    bordercolor='#FFA500',
                    borderwidth=2,
                    font=dict(color='white', size=10),
                    row=1, col=1
                )
        
        fig.add_trace(go.Bar(
            x=df_5m['timestamp'],
            y=df_5m['volume'],
            name='الحجم',
            marker_color='#7f8c8d',
            opacity=0.7
        ), row=2, col=1)
        
        if 'RSI' in df_5m.columns:
            fig.add_trace(go.Scatter(
                x=df_5m['timestamp'],
                y=df_5m['RSI'],
                name='RSI',
                line=dict(color='#ff00ff', width=1.5)
            ), row=3, col=1)
            
            fig.add_shape(
                type='rect',
                x0=df_5m['timestamp'].iloc[0],
                x1=df_5m['timestamp'].iloc[-1],
                y0=70,
                y1=100,
                fillcolor='rgba(255, 0, 0, 0.2)',
                line=dict(width=0),
                row=3, col=1
            )
            
            fig.add_shape(
                type='rect',
                x0=df_5m['timestamp'].iloc[0],
                x1=df_5m['timestamp'].iloc[-1],
                y0=0,
                y1=30,
                fillcolor='rgba(0, 255, 0, 0.2)',
                line=dict(width=0),
                row=3, col=1
            )
        
        fig.update_layout(
            title=f"📊 {symbol} - 5 دقائق",
            height=1000,
            showlegend=True,
            hovermode="x unified",
            plot_bgcolor='rgba(10, 10, 30, 0.5)',
            paper_bgcolor='rgba(10, 10, 30, 0.5)',
            margin=dict(l=20, r=20, t=80, b=20),
            font=dict(color='#e0f0ff'),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        
        fig.update_xaxes(rangeslider_visible=False, row=1, col=1)
        
        return fig
    
    def create_1m_chart(self, df_1m, symbol):
        if df_1m is None or df_1m.empty:
            return go.Figure()
        
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.6, 0.2, 0.2],
            subplot_titles=("الرسم البياني للسعر - 1 دقيقة", "الحجم", "RSI")
        )
        
        fig.add_trace(go.Candlestick(
            x=df_1m['timestamp'],
            open=df_1m['open'],
            high=df_1m['high'],
            low=df_1m['low'],
            close=df_1m['close'],
            name='السعر',
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
                    line=dict(
                        color=line['color'],
                        width=line['width'],
                        dash=line['dash']
                    ),
                    name=line['description'],
                    row=1, col=1
                )
                
                fig.add_annotation(
                    x=df_1m['timestamp'].iloc[-1],
                    y=line['price'],
                    text=line['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=40,
                    ay=0,
                    bgcolor='rgba(30, 144, 255, 0.8)',
                    bordercolor='#1E90FF',
                    borderwidth=2,
                    font=dict(color='white', size=8),
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
                    line=dict(
                        color=level['color'],
                        width=level['width'],
                        dash=level['dash']
                    ),
                    name=level['description'],
                    row=1, col=1
                )
                
                fig.add_annotation(
                    x=df_1m['timestamp'].iloc[-1],
                    y=level['price'],
                    text=level['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=40,
                    ay=0,
                    bgcolor='rgba(255, 255, 255, 0.8)',
                    bordercolor='white',
                    borderwidth=2,
                    font=dict(color='black', size=8),
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
                    line=dict(
                        color=zone['color'],
                        width=zone['width'],
                        dash=zone['dash']
                    ),
                    name=zone['description'],
                    row=1, col=1
                )
                
                fig.add_annotation(
                    x=df_1m['timestamp'].iloc[-1],
                    y=zone['price'],
                    text=zone['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=40,
                    ay=0,
                    bgcolor='rgba(255, 255, 0, 0.8)',
                    bordercolor='#FFFF00',
                    borderwidth=2,
                    font=dict(color='black', size=8),
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
                    line=dict(
                        color=zone['color'],
                        width=zone['width'],
                        dash=zone['dash']
                    ),
                    name=zone['description'],
                    row=1, col=1
                )
                
                fig.add_annotation(
                    x=df_1m['timestamp'].iloc[-1],
                    y=zone['price'],
                    text=zone['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=40,
                    ay=0,
                    bgcolor='rgba(255, 165, 0, 0.8)',
                    bordercolor='#FFA500',
                    borderwidth=2,
                    font=dict(color='white', size=8),
                    row=1, col=1
                )
        
        fig.add_trace(go.Bar(
            x=df_1m['timestamp'],
            y=df_1m['volume'],
            name='الحجم',
            marker_color='#7f8c8d',
            opacity=0.7
        ), row=2, col=1)
        
        if 'RSI' in df_1m.columns:
            fig.add_trace(go.Scatter(
                x=df_1m['timestamp'],
                y=df_1m['RSI'],
                name='RSI',
                line=dict(color='#ff00ff', width=1.2)
            ), row=3, col=1)
            
            fig.add_shape(
                type='rect',
                x0=df_1m['timestamp'].iloc[0],
                x1=df_1m['timestamp'].iloc[-1],
                y0=70,
                y1=100,
                fillcolor='rgba(255, 0, 0, 0.2)',
                line=dict(width=0),
                row=3, col=1
            )
            
            fig.add_shape(
                type='rect',
                x0=df_1m['timestamp'].iloc[0],
                x1=df_1m['timestamp'].iloc[-1],
                y0=0,
                y1=30,
                fillcolor='rgba(0, 255, 0, 0.2)',
                line=dict(width=0),
                row=3, col=1
            )
        
        fig.update_layout(
            title=f"📊 {symbol} - 1 دقيقة",
            height=1000,
            showlegend=True,
            hovermode="x unified",
            plot_bgcolor='rgba(10, 10, 30, 0.5)',
            paper_bgcolor='rgba(10, 10, 30, 0.5)',
            margin=dict(l=20, r=20, t=80, b=20),
            font=dict(color='#e0f0ff', size=10),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        
        fig.update_xaxes(rangeslider_visible=False, row=1, col=1)
        
        return fig
    
    def create_4h_chart(self, df_4h, symbol):
        if df_4h is None or df_4h.empty:
            return go.Figure()
        
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.6, 0.2, 0.2],
            subplot_titles=("الرسم البياني للسعر - 4 ساعات", "الحجم", "RSI")
        )
        
        fig.add_trace(go.Candlestick(
            x=df_4h['timestamp'],
            open=df_4h['open'],
            high=df_4h['high'],
            low=df_4h['low'],
            close=df_4h['close'],
            name='السعر',
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
                    line=dict(
                        color=line['color'],
                        width=line['width'],
                        dash=line['dash']
                    ),
                    name=line['description'],
                    row=1, col=1
                )
                
                fig.add_annotation(
                    x=df_4h['timestamp'].iloc[-1],
                    y=line['price'],
                    text=line['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=40,
                    ay=0,
                    bgcolor='rgba(30, 144, 255, 0.8)',
                    bordercolor='#1E90FF',
                    borderwidth=2,
                    font=dict(color='white', size=10),
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
                    line=dict(
                        color=level['color'],
                        width=level['width'],
                        dash=level['dash']
                    ),
                    name=level['description'],
                    row=1, col=1
                )
                
                fig.add_annotation(
                    x=df_4h['timestamp'].iloc[-1],
                    y=level['price'],
                    text=level['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=40,
                    ay=0,
                    bgcolor='rgba(255, 255, 255, 0.8)',
                    bordercolor='white',
                    borderwidth=2,
                    font=dict(color='black', size=10),
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
                    line=dict(
                        color=zone['color'],
                        width=zone['width'],
                        dash=zone['dash']
                    ),
                    name=zone['description'],
                    row=1, col=1
                )
                
                fig.add_annotation(
                    x=df_4h['timestamp'].iloc[-1],
                    y=zone['price'],
                    text=zone['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=40,
                    ay=0,
                    bgcolor='rgba(255, 255, 0, 0.8)',
                    bordercolor='#FFFF00',
                    borderwidth=2,
                    font=dict(color='black', size=10),
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
                    line=dict(
                        color=zone['color'],
                        width=zone['width'],
                        dash=zone['dash']
                    ),
                    name=zone['description'],
                    row=1, col=1
                )
                
                fig.add_annotation(
                    x=df_4h['timestamp'].iloc[-1],
                    y=zone['price'],
                    text=zone['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=40,
                    ay=0,
                    bgcolor='rgba(255, 165, 0, 0.8)',
                    bordercolor='#FFA500',
                    borderwidth=2,
                    font=dict(color='white', size=10),
                    row=1, col=1
                )
        
        fig.add_trace(go.Bar(
            x=df_4h['timestamp'],
            y=df_4h['volume'],
            name='الحجم',
            marker_color='#7f8c8d',
            opacity=0.7
        ), row=2, col=1)
        
        if 'RSI' in df_4h.columns:
            fig.add_trace(go.Scatter(
                x=df_4h['timestamp'],
                y=df_4h['RSI'],
                name='RSI',
                line=dict(color='#ff00ff', width=1.5)
            ), row=3, col=1)
            
            fig.add_shape(
                type='rect',
                x0=df_4h['timestamp'].iloc[0],
                x1=df_4h['timestamp'].iloc[-1],
                y0=70,
                y1=100,
                fillcolor='rgba(255, 0, 0, 0.2)',
                line=dict(width=0),
                row=3, col=1
            )
            
            fig.add_shape(
                type='rect',
                x0=df_4h['timestamp'].iloc[0],
                x1=df_4h['timestamp'].iloc[-1],
                y0=0,
                y1=30,
                fillcolor='rgba(0, 255, 0, 0.2)',
                line=dict(width=0),
                row=3, col=1
            )
        
        fig.update_layout(
            title=f"📊 {symbol} - 4 ساعات",
            height=1000,
            showlegend=True,
            hovermode="x unified",
            plot_bgcolor='rgba(10, 10, 30, 0.5)',
            paper_bgcolor='rgba(10, 10, 30, 0.5)',
            margin=dict(l=20, r=20, t=80, b=20),
            font=dict(color='#e0f0ff'),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
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
        with st.container():
            st.markdown("""
            <div style="background: rgba(30, 60, 114, 0.3); padding: 30px; border-radius: 15px; 
                        border: 1px solid rgba(255,255,255,0.1);">
            """, unsafe_allow_html=True)
            
            tab1, tab2 = st.tabs(["🔑 تسجيل الدخول", "📝 إنشاء حساب جديد"])
            
            with tab1:
                with st.form("login_form"):
                    username = st.text_input("👤 اسم المستخدم", placeholder="أدخل اسم المستخدم")
                    password = st.text_input("🔒 كلمة المرور", type="password", placeholder="أدخل كلمة المرور")
                    
                    submit_login = st.form_submit_button("🚀 تسجيل الدخول", use_container_width=True)
                    
                    if submit_login:
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
                            st.warning("⚠️ الرجاء إدخال اسم المستخدم وكلمة المرور")
            
            with tab2:
                with st.form("register_form"):
                    new_username = st.text_input("👤 اسم المستخدم", placeholder="اختر اسم مستخدم (3 أحرف على الأقل)")
                    new_password = st.text_input("🔒 كلمة المرور", type="password", placeholder="اختر كلمة مرور (4 أحرف على الأقل)")
                    new_email = st.text_input("📧 البريد الإلكتروني (اختياري)", placeholder="example@email.com")
                    
                    submit_register = st.form_submit_button("📝 إنشاء حساب", use_container_width=True)
                    
                    if submit_register:
                        if new_username and new_password:
                            success, message = user_manager.register_user(new_username, new_password, new_email)
                            if success:
                                st.success(message)
                                st.info("📝 سيتم تفعيل حسابك بعد الدفع عبر تلغرام")
                            else:
                                st.error(message)
                        else:
                            st.warning("⚠️ الرجاء إدخال اسم المستخدم وكلمة المرور")
            
            st.markdown("</div>", unsafe_allow_html=True)
    
    with st.expander("ℹ️ معلومات الدفع"):
        st.info("""
        **💰 طريقة الاشتراك:**
        1. أنشئ حساباً على المنصة
        2. تواصل معي على تلغرام: [@SOFIAN232](https://t.me/SOFIAN232)
        3. أرسل مبلغ 99$ (شهرياً)
        4. أرسل اسم المستخدم الخاص بك
        5. سيتم تفعيل حسابك خلال 24 ساعة
        
        **💎 مميزات الاشتراك:**
        - شموع 5 أطر زمنية
        - خطوط سيولة زرقاء
        - مستويات قوية بيضاء
        - مناطق تصفية صفراء
        - مناطق جذب برتقالية
        """)


def admin_panel(user_manager):
    st.markdown("""
    <div style="background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
                padding: 20px; border-radius: 10px; margin-bottom: 20px;">
        <h2 style="color: white; text-align: center;">🛡️ لوحة تحكم المسؤول</h2>
        <p style="color: #e0f0ff; text-align: center;">إدارة المستخدمين والتفعيل</p>
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
    
    # 📋 المستخدمين المنتظرين
    st.markdown("### 🟡 المستخدمين المنتظرين للتفعيل")
    
    pending_users = user_manager.get_pending_users()
    
    if pending_users:
        for username, data in pending_users.items():
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                st.write(f"**👤 {username}**")
                st.caption(f"📧 {data.get('email', 'لا يوجد')}")
                st.caption(f"📅 سجل: {data.get('created_at', '')[:16] if data.get('created_at') else ''}")
            with col2:
                st.write("💰 **في انتظار الدفع**")
                st.caption("⏳ ينتظر التفعيل")
            with col3:
                if st.button(f"✅ تفعيل {username}", key=f"activate_{username}"):
                    success, message = user_manager.activate_user(username)
                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
    else:
        st.info("✅ لا يوجد مستخدمين في انتظار التفعيل")
    
    # 📋 المستخدمين النشطين
    st.markdown("### 🟢 المستخدمين النشطين")
    
    active_users = user_manager.get_active_users()
    
    if active_users:
        for username, data in active_users.items():
            col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
            with col1:
                st.write(f"**👤 {username}**")
                st.caption(f"📧 {data.get('email', 'لا يوجد')}")
            with col2:
                st.write("✅ **مفعل**")
                if data.get('expiry_date'):
                    st.caption(f"📅 ينتهي: {data['expiry_date'][:10]}")
            with col3:
                if st.button(f"🔴 تعطيل {username}", key=f"deactivate_{username}"):
                    success, message = user_manager.deactivate_user(username)
                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
            with col4:
                if st.button(f"📅 تمديد {username}", key=f"extend_{username}"):
                    success, message = user_manager.extend_subscription(username, 30)
                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
    
    # 📋 جميع المستخدمين
    with st.expander("📋 عرض جميع المستخدمين"):
        all_users = user_manager.get_all_users()
        users_data = []
        for username, data in all_users.items():
            status = "🟢 نشط" if data.get('active', False) else "🟡 في انتظار التفعيل"
            if data.get('is_admin', False):
                status = "👑 مسؤول"
            
            users_data.append({
                "اسم المستخدم": username,
                "الحالة": status,
                "البريد": data.get('email', '-'),
                "تاريخ التسجيل": data.get('created_at', '-')[:16] if data.get('created_at') else '-',
                "تاريخ الدفع": data.get('payment_date', '-')[:16] if data.get('payment_date') else '-'
            })
        
        if users_data:
            df_users = pd.DataFrame(users_data)
            st.dataframe(df_users, use_container_width=True)


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
        <div style="background: rgba(30, 60, 114, 0.3); padding: 20px; border-radius: 10px;
                    border: 2px solid #00ff88;">
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


def analysis_interface():
    st.markdown("""
    <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); 
                border-radius: 15px; margin-bottom: 30px;">
        <h1 style="color: white;">🧠 محلل السيولة المتقدم</h1>
        <p style="color: #e0f0ff;">شموع + خطوط سيولة + مناطق تصفية + جذب مغناطيسي</p>
    </div>
    """, unsafe_allow_html=True)
    
    analyzer = CryptoAnalyzer()
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        symbol = st.text_input("💰 أدخل زوج العملات:", "BTC/USDT").upper()
    
    with col2:
        st.write("")
        if st.button("🚀 تحليل", type="primary", use_container_width=True):
            if check_rate_limit():
                st.session_state['run_analysis'] = True
    
    if st.session_state.get('run_analysis', False):
        st.session_state['run_analysis'] = False
        
        with st.spinner(f"🔄 جاري تحليل {symbol}..."):
            # جلب جميع الأطر الزمنية
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
            
            # إنشاء التبويبات
            tabs = st.tabs(["⏰ 4 ساعات", "📈 1 ساعة", "⏱️ 15 دقيقة", "⏱️ 5 دقائق", "⏱️ 1 دقيقة"])
            
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
                        st.error(f"❌ لا توجد بيانات لـ {tf}")


# ============================================
# 🚀 الدالة الرئيسية
# ============================================

def main():
    # تهيئة session state
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
    if 'username' not in st.session_state:
        st.session_state['username'] = None
    if 'is_admin' not in st.session_state:
        st.session_state['is_admin'] = False
    if 'run_analysis' not in st.session_state:
        st.session_state['run_analysis'] = False
    
    # إنشاء مدير المستخدمين
    user_manager = UserManager()
    
    # إذا لم يكن مسجل الدخول
    if not st.session_state['logged_in']:
        login_page(user_manager)
        return
    
    username = st.session_state['username']
    is_admin = st.session_state['is_admin']
    
    # التحقق من صلاحية المستخدم
    if not is_admin:
        user_data = user_manager.get_user_data(username)
        if not user_data or not user_data.get('active', False):
            payment_page(user_manager)
            return
    
    # الشريط الجانبي
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
    
    # عرض المحتوى
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