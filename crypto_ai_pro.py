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
# 🌐 بروكسيات مجانية مدمجة
# ============================================

FREE_PROXIES = [
    'http://103.152.112.120:80',
    'http://45.8.112.67:8080',
    'http://45.86.221.146:8080',
    'http://188.166.128.254:80',
    'http://20.115.126.236:80',
    'http://5.182.104.174:80',
    'http://5.182.104.178:80',
    'http://5.182.104.180:80',
    'http://5.182.104.182:80',
    'http://5.182.104.184:80',
    'http://45.8.112.67:8080',
    'http://45.86.221.146:8080',
    'http://103.152.112.120:80',
    'http://103.152.112.120:8080',
    'http://45.8.112.67:80',
]

class SmartExchange:
    """اتصال ذكي مع بروكسيات متعددة"""
    
    def __init__(self):
        self.exchange = None
        self.current_proxy = None
    
    def get_exchange(self):
        """الحصول على اتصال شغال"""
        
        # إذا كان الاتصال موجود وشغال، استخدمه
        if self.exchange:
            try:
                self.exchange.ping()
                return self.exchange
            except:
                pass
        
        # جرب بدون بروكسي أولاً
        try:
            exchange = ccxt.binance({
                'rateLimit': 3000,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'spot',
                    'adjustForTimeDifference': True,
                },
                'headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            })
            exchange.ping()
            self.exchange = exchange
            self.current_proxy = "بدون بروكسي"
            return exchange
        except:
            pass
        
        # جرب مع بروكسيات مجانية
        for proxy in FREE_PROXIES:
            try:
                exchange = ccxt.binance({
                    'rateLimit': 3000,
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'spot',
                        'adjustForTimeDifference': True,
                    },
                    'proxies': {
                        'http': proxy,
                        'https': proxy
                    },
                    'headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                })
                exchange.ping()
                self.exchange = exchange
                self.current_proxy = proxy
                return exchange
            except:
                continue
        
        # جرب KuCoin كبديل أخير
        try:
            exchange = ccxt.kucoin({
                'rateLimit': 3000,
                'enableRateLimit': True,
            })
            exchange.ping()
            self.exchange = exchange
            self.current_proxy = "KuCoin (بديل)"
            return exchange
        except:
            pass
        
        return None

# ============================================
# 🔧 إعدادات التخزين المؤقت
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
# 📊 جلب البيانات مع إعادة المحاولة التلقائية
# ============================================

@st.cache_data(ttl=CACHE_DURATION_DATA)
def fetch_candles_cached(symbol, timeframe='1h', limit=500):
    """جلب البيانات مع إعادة محاولة تلقائية"""
    
    smart = SmartExchange()
    exchange = smart.get_exchange()
    
    if not exchange:
        st.error("❌ لا يمكن الاتصال بأي منصة! جرب VPN أو اتصل بي للمساعدة")
        return None
    
    # عرض البروكسي المستخدم
    if smart.current_proxy:
        st.sidebar.info(f"🌐 يستخدم: {smart.current_proxy}")
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1, 2, 4, 8 ثواني
                time.sleep(wait_time)
                # جرب بروكسي جديد
                smart.exchange = None
                exchange = smart.get_exchange()
                if not exchange:
                    break
            else:
                st.error(f"❌ فشل الجلب بعد {max_retries} محاولات: {str(e)}")
                return None
    
    return None

# ============================================
# 📈 المؤشرات الفنية
# ============================================

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

# ============================================
# 🗄️ نظام المستخدمين
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
            return False, f"❌ خطأ: {str(e)}"
    
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
            return False, f"❌ خطأ: {str(e)}"
    
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

# ============================================
# 🎯 التحليل المتقدم
# ============================================

class CryptoAnalyzer:
    def __init__(self):
        self.smart = SmartExchange()
        self.blue_liquidity_lines = {}
        self.white_liquidity_levels = {}
        self.yellow_liquidation_zones = {}
    
    def fetch_data(self, symbol):
        try:
            df = fetch_candles_cached(symbol, '1h', MAX_CANDLES)
            if df is not None:
                df = calculate_indicators_cached(df)
            return df
        except Exception as e:
            st.error(f"خطأ: {str(e)}")
            return None
    
    def calculate_blue_liquidity_lines(self, df, current_price, symbol):
        blue_lines = []
        
        if df is None or len(df) < 50:
            self.blue_liquidity_lines[symbol] = blue_lines
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
            
            if (lower_wick > body_size * 2 and 
                upper_wick < body_size * 0.5 and
                next_candle['close'] > candle['close']):
                
                blue_lines.append({
                    'price': candle['low'],
                    'type': 'buy_liquidity',
                    'strength': min(0.8 + (lower_wick/total_range), 0.95),
                    'description': '🔵 رفض شرائي قوي',
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
                    'description': '🔵 رفض بيعي قوي',
                    'color': '#1E90FF',
                    'width': 2 + (upper_wick/total_range * 3),
                    'dash': 'solid'
                })
        
        self.blue_liquidity_lines[symbol] = blue_lines[:8]
    
    def calculate_white_liquidity_levels(self, df, current_price, symbol):
        white_levels = []
        
        if df is None or len(df) < 50:
            self.white_liquidity_levels[symbol] = white_levels
            return
        
        if len(df) >= 100:
            high_idx = argrelextrema(df['high'].values, np.greater, order=20)[0]
            low_idx = argrelextrema(df['low'].values, np.less, order=20)[0]
            
            for idx in low_idx[-5:]:
                price = df['low'].iloc[idx]
                distance = abs(price - current_price) / current_price * 100
                if distance <= 5:
                    white_levels.append({
                        'price': price,
                        'type': 'support',
                        'strength': 0.8,
                        'description': '⚪ دعم قوي',
                        'color': 'white',
                        'width': 2,
                        'dash': 'dash'
                    })
            
            for idx in high_idx[-5:]:
                price = df['high'].iloc[idx]
                distance = abs(price - current_price) / current_price * 100
                if distance <= 5:
                    white_levels.append({
                        'price': price,
                        'type': 'resistance',
                        'strength': 0.8,
                        'description': '⚪ مقاومة قوي',
                        'color': 'white',
                        'width': 2,
                        'dash': 'dash'
                    })
        
        self.white_liquidity_levels[symbol] = white_levels[:5]
    
    def calculate_yellow_liquidation_zones(self, df, current_price, symbol):
        yellow_zones = []
        
        if df is None or len(df) < 50:
            self.yellow_liquidation_zones[symbol] = yellow_zones
            return
        
        for i in range(2, len(df)-2):
            current = df.iloc[i]
            prev = df.iloc[i-1]
            next_candle = df.iloc[i+1]
            
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
                
                zone = {
                    'price': current['low'],
                    'type': 'bullish',
                    'strength': volume_ratio,
                    'description': '🟢 منطقة تصفية صاعدة',
                    'color': '#FFFF00',
                    'width': 2,
                    'dash': 'dash'
                }
                yellow_zones.append(zone)
            
            elif (current['volume'] > avg_volume * 2 and
                  upper_wick > candle_range * 0.4 and
                  current['close'] < current['open'] and
                  current['high'] > prev['high'] and
                  next_candle['close'] < current['low']):
                
                zone = {
                    'price': current['high'],
                    'type': 'bearish',
                    'strength': volume_ratio,
                    'description': '🔴 منطقة تصفية هابطة',
                    'color': '#FFFF00',
                    'width': 2,
                    'dash': 'dash'
                }
                yellow_zones.append(zone)
        
        self.yellow_liquidation_zones[symbol] = yellow_zones[:5]
    
    def create_chart(self, df, symbol):
        if df is None or df.empty:
            return go.Figure()
        
        current_price = df['close'].iloc[-1]
        
        self.calculate_blue_liquidity_lines(df, current_price, symbol)
        self.calculate_white_liquidity_levels(df, current_price, symbol)
        self.calculate_yellow_liquidation_zones(df, current_price, symbol)
        
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.6, 0.2, 0.2],
            subplot_titles=("الرسم البياني للسعر", "الحجم", "RSI")
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
        
        # الخطوط الزرقاء
        if symbol in self.blue_liquidity_lines:
            for line in self.blue_liquidity_lines[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df['timestamp'].iloc[0],
                    x1=df['timestamp'].iloc[-1],
                    y0=line['price'],
                    y1=line['price'],
                    line=dict(
                        color=line['color'],
                        width=line['width'],
                        dash=line['dash']
                    ),
                    row=1, col=1
                )
                fig.add_annotation(
                    x=df['timestamp'].iloc[-1],
                    y=line['price'],
                    text=line['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=40,
                    ay=0,
                    bgcolor='rgba(30, 144, 255, 0.8)',
                    font=dict(color='white', size=10),
                    row=1, col=1
                )
        
        # الخطوط البيضاء
        if symbol in self.white_liquidity_levels:
            for level in self.white_liquidity_levels[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df['timestamp'].iloc[0],
                    x1=df['timestamp'].iloc[-1],
                    y0=level['price'],
                    y1=level['price'],
                    line=dict(
                        color=level['color'],
                        width=level['width'],
                        dash=level['dash']
                    ),
                    row=1, col=1
                )
                fig.add_annotation(
                    x=df['timestamp'].iloc[-1],
                    y=level['price'],
                    text=level['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=40,
                    ay=0,
                    bgcolor='rgba(255, 255, 255, 0.8)',
                    font=dict(color='black', size=10),
                    row=1, col=1
                )
        
        # الخطوط الصفراء
        if symbol in self.yellow_liquidation_zones:
            for zone in self.yellow_liquidation_zones[symbol]:
                fig.add_shape(
                    type='line',
                    x0=df['timestamp'].iloc[0],
                    x1=df['timestamp'].iloc[-1],
                    y0=zone['price'],
                    y1=zone['price'],
                    line=dict(
                        color=zone['color'],
                        width=zone['width'],
                        dash=zone['dash']
                    ),
                    row=1, col=1
                )
                fig.add_annotation(
                    x=df['timestamp'].iloc[-1],
                    y=zone['price'],
                    text=zone['description'],
                    showarrow=True,
                    arrowhead=1,
                    ax=40,
                    ay=0,
                    bgcolor='rgba(255, 255, 0, 0.8)',
                    font=dict(color='black', size=10),
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
            title=f"📊 {symbol}",
            height=900,
            showlegend=True,
            hovermode="x unified",
            plot_bgcolor='rgba(10, 10, 30, 0.5)',
            paper_bgcolor='rgba(10, 10, 30, 0.5)',
            font=dict(color='#e0f0ff')
        )
        
        return fig

# ============================================
# 🔐 صفحات المستخدم
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
        """)

def admin_panel(user_manager):
    st.markdown("""
    <div style="background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
                padding: 20px; border-radius: 10px; margin-bottom: 20px;">
        <h2 style="color: white; text-align: center;">🛡️ لوحة تحكم المسؤول</h2>
        <p style="color: #e0f0ff; text-align: center;">إدارة المستخدمين والتفعيل</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### 🟡 المستخدمين المنتظرين للتفعيل")
    
    pending_users = user_manager.get_pending_users()
    
    if pending_users:
        for username, data in pending_users.items():
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                st.write(f"**👤 {username}**")
                st.caption(f"📧 {data.get('email', 'لا يوجد')}")
            with col2:
                st.write("💰 **في انتظار الدفع**")
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
                "تاريخ التسجيل": data.get('created_at', '-')[:16] if data.get('created_at') else '-'
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
        </p>
        <p style="color: #e0f0ff;">
            3️⃣ أرسل لي اسم المستخدم الخاص بك:<br>
            <span style="color: #00ff88;">📝 username: {your_username}</span>
        </p>
    </div>
    """, unsafe_allow_html=True)

def analysis_interface():
    st.markdown("""
    <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); 
                border-radius: 15px; margin-bottom: 30px;">
        <h1 style="color: white;">🧠 محلل السيولة المتقدم</h1>
        <p style="color: #e0f0ff;">شموع + خطوط سيولة + مناطق تصفية</p>
    </div>
    """, unsafe_allow_html=True)
    
    analyzer = CryptoAnalyzer()
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        symbol = st.text_input("💰 أدخل زوج العملات:", "BTC/USDT").upper()
    
    with col2:
        st.write("")
        if st.button("🚀 تحليل", type="primary", use_container_width=True):
            st.session_state['run_analysis'] = True
    
    if st.session_state.get('run_analysis', False):
        st.session_state['run_analysis'] = False
        
        with st.spinner(f"🔄 جاري تحليل {symbol}..."):
            df = analyzer.fetch_data(symbol)
            
            if df is not None and not df.empty:
                fig = analyzer.create_chart(df, symbol)
                st.plotly_chart(fig, use_container_width=True)
                
                # عرض معلومات إضافية
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("السعر الحالي", f"${df['close'].iloc[-1]:.2f}")
                with col2:
                    st.metric("التغيير 24h", f"{((df['close'].iloc[-1] - df['close'].iloc[-20]) / df['close'].iloc[-20] * 100):.2f}%")
                with col3:
                    st.metric("الحجم", f"{df['volume'].iloc[-1]:.0f}")
            else:
                st.error("❌ لا توجد بيانات! جرب VPN أو استخدم بروكسي آخر")

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