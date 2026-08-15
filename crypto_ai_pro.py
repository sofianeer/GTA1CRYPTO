import streamlit as st
import pandas as pd
import numpy as np
import ccxt
import talib
from scipy.signal import argrelextrema
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
import hashlib
import sqlite3
import warnings
warnings.filterwarnings('ignore')

# ============================================
# 📦 تثبيت المكتبات المطلوبة
# ============================================
# pip install streamlit pandas numpy ccxt TA-Lib scipy plotly sqlite3 MetaTrader5

# ============================================
# 🔧 إعدادات عامة
# ============================================

CACHE_DURATION = 300
MAX_CANDLES = 500
ADMIN_USERNAME = "adminSO"
ADMIN_PASSWORD = "admin25SO"

# ============================================
# 💰 منصة KuCoin (للعملات الرقمية)
# ============================================

@st.cache_resource
def get_kucoin_exchange():
    """الاتصال بـ KuCoin - يعمل في جميع الدول"""
    try:
        exchange = ccxt.kucoin({
            'rateLimit': 3000,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
                'adjustForTimeDifference': True,
            }
        })
        # اختبار الاتصال
        exchange.fetch_ohlcv('BTC/USDT', '1h', limit=1)
        return exchange
    except Exception as e:
        st.error(f"❌ فشل الاتصال بـ KuCoin: {str(e)}")
        return None

# ============================================
# 📊 منصة MetaTrader 5 (للفوركس والذهب)
# ============================================

try:
    import MetaTrader5 as mt5
except ImportError:
    st.warning("⚠️ MetaTrader5 غير مثبت. قم بتثبيته: pip install MetaTrader5")
    mt5 = None

class MT5Manager:
    """إدارة الاتصال بـ MetaTrader 5"""
    
    def __init__(self):
        self.connected = False
        self.symbols = {
            'XAUUSD': 'XAUUSD',
            'XAU/USD': 'XAUUSD',
            'GOLD': 'XAUUSD',
            'EURUSD': 'EURUSD',
            'EUR/USD': 'EURUSD',
            'GBPUSD': 'GBPUSD',
            'GBP/USD': 'GBPUSD',
            'USDJPY': 'USDJPY',
            'USD/JPY': 'USDJPY',
            'AUDUSD': 'AUDUSD',
            'AUD/USD': 'AUDUSD',
            'USDCAD': 'USDCAD',
            'USD/CAD': 'USDCAD',
            'NZDUSD': 'NZDUSD',
            'NZD/USD': 'NZDUSD',
        }
    
    def connect(self):
        """الاتصال بـ MT5"""
        if mt5 is None:
            return False
        
        if not self.connected:
            try:
                # تهيئة MT5
                if not mt5.initialize():
                    st.error("❌ فشل تهيئة MT5")
                    return False
                
                self.connected = True
                st.success("✅ تم الاتصال بـ MetaTrader 5")
                return True
            except Exception as e:
                st.error(f"❌ خطأ في MT5: {str(e)}")
                return False
        
        return True
    
    def disconnect(self):
        """قطع الاتصال بـ MT5"""
        if self.connected and mt5:
            mt5.shutdown()
            self.connected = False
    
    def fetch_data(self, symbol, timeframe='1h', limit=500):
        """جلب بيانات الفوركس والذهب من MT5"""
        
        if not self.connect():
            return None
        
        # تحويل الرمز
        symbol_mt5 = self.symbols.get(symbol, symbol)
        
        # تحويل الإطار الزمني
        timeframe_map = {
            '1m': mt5.TIMEFRAME_M1,
            '5m': mt5.TIMEFRAME_M5,
            '15m': mt5.TIMEFRAME_M15,
            '30m': mt5.TIMEFRAME_M30,
            '1h': mt5.TIMEFRAME_H1,
            '4h': mt5.TIMEFRAME_H4,
            '1d': mt5.TIMEFRAME_D1,
            '1w': mt5.TIMEFRAME_W1,
            '1M': mt5.TIMEFRAME_MN1,
        }
        tf = timeframe_map.get(timeframe, mt5.TIMEFRAME_H1)
        
        try:
            # جلب البيانات
            rates = mt5.copy_rates_from_pos(symbol_mt5, tf, 0, limit)
            
            if rates is None or len(rates) == 0:
                st.error(f"❌ لا توجد بيانات لـ {symbol_mt5}")
                return None
            
            # تحويل إلى DataFrame
            df = pd.DataFrame(rates)
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
            
            return df[['timestamp', 'open', 'high', 'low', 'close']]
            
        except Exception as e:
            st.error(f"❌ خطأ في جلب بيانات {symbol_mt5}: {str(e)}")
            return None
    
    def get_current_price(self, symbol):
        """الحصول على السعر الحالي"""
        
        if not self.connect():
            return None
        
        symbol_mt5 = self.symbols.get(symbol, symbol)
        
        try:
            tick = mt5.symbol_info_tick(symbol_mt5)
            if tick:
                return {
                    'bid': tick.bid,
                    'ask': tick.ask,
                    'last': tick.last if hasattr(tick, 'last') else (tick.bid + tick.ask) / 2
                }
            return None
        except:
            return None

# ============================================
# 🎯 محلل الأسواق المتعدد
# ============================================

class MultiMarketAnalyzer:
    """محلل متعدد الأسواق - عملات رقمية + فوركس + ذهب"""
    
    def __init__(self):
        self.kucoin = None
        self.mt5 = MT5Manager()
        self.blue_liquidity_lines = {}
        self.white_liquidity_levels = {}
        self.yellow_liquidation_zones = {}
    
    def get_exchange(self):
        """الحصول على اتصال KuCoin"""
        if not self.kucoin:
            self.kucoin = get_kucoin_exchange()
        return self.kucoin
    
    def fetch_data(self, symbol, timeframe='1h', limit=500):
        """جلب البيانات حسب نوع الرمز"""
        
        # قائمة رموز الفوركس والذهب
        forex_symbols = ['XAUUSD', 'XAU/USD', 'GOLD', 'GC=F', 
                        'EURUSD', 'EUR/USD', 'GBPUSD', 'GBP/USD',
                        'USDJPY', 'USD/JPY', 'AUDUSD', 'AUD/USD',
                        'USDCAD', 'USD/CAD', 'NZDUSD', 'NZD/USD']
        
        if symbol in forex_symbols:
            return self.fetch_forex_data(symbol, timeframe, limit)
        else:
            return self.fetch_crypto_data(symbol, timeframe, limit)
    
    def fetch_crypto_data(self, symbol, timeframe='1h', limit=500):
        """جلب بيانات العملات الرقمية من KuCoin"""
        
        exchange = self.get_exchange()
        if not exchange:
            return None
        
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            st.error(f"❌ خطأ في جلب {symbol} من KuCoin: {str(e)}")
            return None
    
    def fetch_forex_data(self, symbol, timeframe='1h', limit=500):
        """جلب بيانات الفوركس والذهب من MT5"""
        
        # محاولة MT5 أولاً
        df = self.mt5.fetch_data(symbol, timeframe, limit)
        
        if df is not None:
            return df
        
        # إذا فشل MT5، جرب yfinance
        try:
            import yfinance as yf
            ticker_map = {
                'XAUUSD': 'XAUUSD=X',
                'XAU/USD': 'XAUUSD=X',
                'GOLD': 'GC=F',
                'EURUSD': 'EURUSD=X',
                'EUR/USD': 'EURUSD=X',
                'GBPUSD': 'GBPUSD=X',
                'USDJPY': 'USDJPY=X',
            }
            ticker = ticker_map.get(symbol, symbol)
            
            interval_map = {
                '1m': '1m', '5m': '5m', '15m': '15m', '30m': '30m',
                '1h': '60m', '4h': '1h', '1d': '1d'
            }
            interval = interval_map.get(timeframe, '60m')
            
            data = yf.download(ticker, period='1mo', interval=interval, progress=False)
            
            if not data.empty:
                df = data.reset_index()
                df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
                return df
            
        except:
            pass
        
        st.error(f"❌ لا يمكن جلب بيانات {symbol}")
        return None
    
    def calculate_indicators(self, df):
        """حساب المؤشرات الفنية"""
        
        if df is None or df.empty:
            return df
        
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        
        # RSI
        df['RSI'] = talib.RSI(close, timeperiod=14)
        
        # MACD
        df['MACD'], df['MACD_signal'], df['MACD_hist'] = talib.MACD(close)
        
        # المتوسطات
        df['SMA_20'] = talib.SMA(close, timeperiod=20)
        df['SMA_50'] = talib.SMA(close, timeperiod=50)
        df['EMA_100'] = talib.EMA(close, timeperiod=100)
        
        # Bollinger Bands
        df['BB_upper'], df['BB_middle'], df['BB_lower'] = talib.BBANDS(
            close, timeperiod=20, nbdevup=2, nbdevdn=2
        )
        
        # ATR
        df['ATR'] = talib.ATR(high, low, close, timeperiod=14)
        
        # ADX
        df['ADX'] = talib.ADX(high, low, close, timeperiod=14)
        
        return df.dropna()
    
    def calculate_blue_liquidity(self, df, symbol):
        """حساب خطوط السيولة الزرقاء"""
        
        blue_lines = []
        
        if df is None or len(df) < 50:
            self.blue_liquidity_lines[symbol] = blue_lines
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
            
            if (lower_wick > body_size * 2 and 
                upper_wick < body_size * 0.5 and
                next_candle['close'] > candle['close']):
                
                blue_lines.append({
                    'price': candle['low'],
                    'type': 'buy_liquidity',
                    'strength': min(0.8 + (lower_wick/total_range), 0.95),
                    'description': '🔵 رفض شرائي',
                    'color': '#1E90FF',
                    'width': 2,
                    'dash': 'solid'
                })
            
            if (upper_wick > body_size * 2 and 
                lower_wick < body_size * 0.5 and
                next_candle['close'] < candle['close']):
                
                blue_lines.append({
                    'price': candle['high'],
                    'type': 'sell_liquidity',
                    'strength': min(0.8 + (upper_wick/total_range), 0.95),
                    'description': '🔵 رفض بيعي',
                    'color': '#1E90FF',
                    'width': 2,
                    'dash': 'solid'
                })
        
        self.blue_liquidity_lines[symbol] = blue_lines[:10]
    
    def calculate_white_levels(self, df, symbol):
        """حساب المستويات البيضاء"""
        
        white_levels = []
        
        if df is None or len(df) < 50:
            self.white_liquidity_levels[symbol] = white_levels
            return
        
        if len(df) >= 100:
            high_idx = argrelextrema(df['high'].values, np.greater, order=15)[0]
            low_idx = argrelextrema(df['low'].values, np.less, order=15)[0]
            
            current_price = df['close'].iloc[-1]
            
            for idx in low_idx[-10:]:
                price = df['low'].iloc[idx]
                distance = abs(price - current_price) / current_price * 100
                if distance <= 10:
                    white_levels.append({
                        'price': price,
                        'type': 'support',
                        'strength': 0.8,
                        'description': '⚪ دعم',
                        'color': 'white',
                        'width': 2,
                        'dash': 'dash'
                    })
            
            for idx in high_idx[-10:]:
                price = df['high'].iloc[idx]
                distance = abs(price - current_price) / current_price * 100
                if distance <= 10:
                    white_levels.append({
                        'price': price,
                        'type': 'resistance',
                        'strength': 0.8,
                        'description': '⚪ مقاومة',
                        'color': 'white',
                        'width': 2,
                        'dash': 'dash'
                    })
        
        self.white_liquidity_levels[symbol] = white_levels[:8]
    
    def calculate_yellow_zones(self, df, symbol):
        """حساب مناطق التصفية الصفراء"""
        
        yellow_zones = []
        
        if df is None or len(df) < 50:
            self.yellow_liquidation_zones[symbol] = yellow_zones
            return
        
        for i in range(5, len(df)-5):
            current = df.iloc[i]
            prev = df.iloc[i-1]
            next_candle = df.iloc[i+1]
            
            upper_wick = current['high'] - max(current['open'], current['close'])
            lower_wick = min(current['open'], current['close']) - current['low']
            candle_range = current['high'] - current['low']
            
            avg_volume = df['volume'].iloc[max(0, i-20):i].mean() if 'volume' in df else 1
            volume_ratio = current['volume'] / avg_volume if avg_volume > 0 else 1
            
            if candle_range > 0:
                if (volume_ratio > 1.5 and
                    lower_wick > candle_range * 0.4 and
                    current['close'] > current['open'] and
                    current['low'] < prev['low'] and
                    next_candle['close'] > current['high']):
                    
                    yellow_zones.append({
                        'price': current['low'],
                        'type': 'bullish',
                        'strength': volume_ratio,
                        'description': '🟢 تصفية صاعدة',
                        'color': '#FFFF00',
                        'width': 2,
                        'dash': 'dash'
                    })
                
                if (volume_ratio > 1.5 and
                    upper_wick > candle_range * 0.4 and
                    current['close'] < current['open'] and
                    current['high'] > prev['high'] and
                    next_candle['close'] < current['low']):
                    
                    yellow_zones.append({
                        'price': current['high'],
                        'type': 'bearish',
                        'strength': volume_ratio,
                        'description': '🔴 تصفية هابطة',
                        'color': '#FFFF00',
                        'width': 2,
                        'dash': 'dash'
                    })
        
        self.yellow_liquidation_zones[symbol] = yellow_zones[:8]
    
    def create_chart(self, df, symbol):
        """إنشاء الرسم البياني"""
        
        if df is None or df.empty:
            return go.Figure()
        
        current_price = df['close'].iloc[-1]
        
        self.calculate_blue_liquidity(df, symbol)
        self.calculate_white_levels(df, symbol)
        self.calculate_yellow_zones(df, symbol)
        
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.6, 0.2, 0.2],
            subplot_titles=("الرسم البياني", "الحجم", "RSI")
        )
        
        # شموع
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
                    line=dict(color=line['color'], width=line['width'], dash=line['dash']),
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
                    line=dict(color=level['color'], width=level['width'], dash=level['dash']),
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
                    line=dict(color=zone['color'], width=zone['width'], dash=zone['dash']),
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
        
        # المتوسطات
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
        
        # الحجم
        if 'volume' in df.columns:
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
                    (username, password, email, active, created_at, is_admin, payment_status, expiry_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    ADMIN_USERNAME,
                    self._hash_password(ADMIN_PASSWORD),
                    "admin@example.com",
                    1,
                    datetime.now().isoformat(),
                    1,
                    "paid",
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
            return False, "❌ اسم المستخدم يجب أن يكون 3 أحرف"
        if len(password) < 4:
            return False, "❌ كلمة المرور يجب أن تكون 4 أحرف"
        
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
            return True, "✅ تم التسجيل بنجاح! انتظر التفعيل"
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
                return False, "⛔ حسابك غير مفعل!"
            
            if user[1] != self._hash_password(password):
                conn.close()
                return False, "❌ كلمة مرور خاطئة"
            
            cursor.execute("UPDATE users SET last_login=? WHERE username=?", 
                         (datetime.now().isoformat(), username))
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
                UPDATE users 
                SET active=1, payment_status='paid', expiry_date=?
                WHERE username=?
            ''', (expiry.isoformat(), username))
            conn.commit()
            conn.close()
            return True, f"✅ تم تفعيل {username}"
        except Exception as e:
            return False, f"❌ خطأ: {str(e)}"
    
    def get_pending_users(self):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT username, email, created_at FROM users WHERE active=0 AND is_admin=0")
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
            cursor.execute("SELECT username, email, active, created_at, is_admin, payment_status, expiry_date FROM users")
            users = cursor.fetchall()
            conn.close()
            result = {}
            for user in users:
                result[user[0]] = {
                    "email": user[1],
                    "active": bool(user[2]),
                    "created_at": user[3],
                    "is_admin": bool(user[4]),
                    "payment_status": user[5],
                    "expiry_date": user[6]
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
            cursor.execute("SELECT username, email, active, created_at, is_admin, payment_status, expiry_date FROM users WHERE username=?", (username,))
            user = cursor.fetchone()
            conn.close()
            if user:
                return {
                    "username": user[0],
                    "email": user[1],
                    "active": bool(user[2]),
                    "created_at": user[3],
                    "is_admin": bool(user[4]),
                    "payment_status": user[5],
                    "expiry_date": user[6]
                }
            return None
        except:
            return None

# ============================================
# 🔐 واجهات المستخدم
# ============================================

def login_page(user_manager):
    st.markdown("""
    <div style="text-align: center; padding: 30px;">
        <h1 style="font-size: 3em;">🔐 منصة التحليل المتقدم</h1>
        <p style="font-size: 1.2em; color: #888;">العملات الرقمية + الفوركس + الذهب</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        tab1, tab2 = st.tabs(["🔑 تسجيل الدخول", "📝 إنشاء حساب"])
        
        with tab1:
            with st.form("login_form"):
                username = st.text_input("👤 اسم المستخدم")
                password = st.text_input("🔒 كلمة المرور", type="password")
                
                if st.form_submit_button("🚀 تسجيل الدخول", use_container_width=True):
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
                new_username = st.text_input("👤 اسم المستخدم")
                new_password = st.text_input("🔒 كلمة المرور", type="password")
                new_email = st.text_input("📧 البريد الإلكتروني (اختياري)")
                
                if st.form_submit_button("📝 إنشاء حساب", use_container_width=True):
                    success, message = user_manager.register_user(new_username, new_password, new_email)
                    if success:
                        st.success(message)
                        st.info("📝 سيتم تفعيل حسابك بعد الدفع")
                    else:
                        st.error(message)

def admin_panel(user_manager):
    st.markdown("### 🛡️ لوحة تحكم المسؤول")
    
    pending = user_manager.get_pending_users()
    
    if pending:
        for username, data in pending.items():
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                st.write(f"**👤 {username}**")
                st.caption(f"📧 {data.get('email', 'لا يوجد')}")
            with col2:
                st.write("💰 في انتظار الدفع")
            with col3:
                if st.button(f"✅ تفعيل {username}", key=f"activate_{username}"):
                    success, message = user_manager.activate_user(username)
                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
    else:
        st.success("✅ لا يوجد مستخدمين في انتظار التفعيل")
    
    with st.expander("📋 جميع المستخدمين"):
        all_users = user_manager.get_all_users()
        users_data = []
        for username, data in all_users.items():
            status = "🟢 نشط" if data.get('active', False) else "🟡 غير مفعل"
            if data.get('is_admin', False):
                status = "👑 مسؤول"
            
            users_data.append({
                "المستخدم": username,
                "الحالة": status,
                "البريد": data.get('email', '-'),
                "تاريخ التسجيل": data.get('created_at', '-')[:10] if data.get('created_at') else '-'
            })
        
        if users_data:
            st.dataframe(pd.DataFrame(users_data), use_container_width=True)

def payment_page():
    st.markdown("""
    <div style="text-align: center; padding: 30px;">
        <h2>💎 تفعيل الحساب</h2>
        <p>للوصول إلى جميع الميزات، يرجى تفعيل حسابك</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.info("""
    **💰 طريقة الاشتراك:**
    1. تواصل معي على تلغرام: [@SOFIAN232](https://t.me/SOFIAN232)
    2. أرسل مبلغ 99$ (شهرياً)
    3. أرسل اسم المستخدم الخاص بك
    4. سيتم تفعيل حسابك خلال 24 ساعة
    """)

def analysis_interface():
    st.markdown("""
    <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); 
                border-radius: 15px; margin-bottom: 30px;">
        <h1 style="color: white;">🧠 محلل الأسواق المتقدم</h1>
        <p style="color: #e0f0ff;">العملات الرقمية | الفوركس | الذهب</p>
    </div>
    """, unsafe_allow_html=True)
    
    analyzer = MultiMarketAnalyzer()
    
    # أمثلة للرموز
    st.markdown("""
    **📌 أمثلة للرموز:**
    - **عملات رقمية:** BTC/USDT, ETH/USDT, SOL/USDT
    - **الذهب:** XAUUSD, XAU/USD, GOLD
    - **الفوركس:** EURUSD, GBPUSD, USDJPY, AUDUSD
    """)
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        symbol = st.text_input("💰 أدخل الرمز:", "BTC/USDT").upper()
    
    with col2:
        timeframe = st.selectbox("⏰ الإطار الزمني", 
                                 ['1m', '5m', '15m', '30m', '1h', '4h', '1d'])
    
    if st.button("🚀 تحليل", type="primary", use_container_width=True):
        with st.spinner(f"🔄 جاري تحليل {symbol}..."):
            df = analyzer.fetch_data(symbol, timeframe)
            
            if df is not None and not df.empty:
                df = analyzer.calculate_indicators(df)
                
                # عرض معلومات السعر
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("السعر الحالي", f"${df['close'].iloc[-1]:.2f}")
                with col2:
                    change = ((df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2]) * 100
                    st.metric("التغيير", f"{change:.2f}%", 
                             delta=f"{change:.2f}%")
                with col3:
                    if 'RSI' in df.columns:
                        st.metric("RSI", f"{df['RSI'].iloc[-1]:.2f}")
                with col4:
                    if 'ATR' in df.columns:
                        st.metric("ATR", f"{df['ATR'].iloc[-1]:.2f}")
                
                # الرسم البياني
                fig = analyzer.create_chart(df, symbol)
                st.plotly_chart(fig, use_container_width=True)
                
                # عرض البيانات
                with st.expander("📋 عرض البيانات"):
                    st.dataframe(df.tail(20))
            else:
                st.error(f"❌ لا توجد بيانات لـ {symbol}")

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
    
    user_manager = UserManager()
    
    if not st.session_state['logged_in']:
        login_page(user_manager)
        return
    
    username = st.session_state['username']
    is_admin = st.session_state['is_admin']
    
    # التحقق من صلاحية المستخدم
    if not is_admin:
        user_data = user_manager.get_user_data(username)
        if not user_data or not user_data.get('active', False):
            payment_page()
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
            <p>👤 {username}</p>
            <p>🔑 {"👑 مسؤول" if is_admin else "👤 مستخدم"}</p>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("🚪 تسجيل الخروج", use_container_width=True):
            st.session_state['logged_in'] = False
            st.session_state['username'] = None
            st.session_state['is_admin'] = False
            st.rerun()
    
    if is_admin:
        tab_admin, tab_analysis = st.tabs(["🛡️ لوحة التحكم", "📊 التحليل"])
        with tab_admin:
            admin_panel(user_manager)
        with tab_analysis:
            analysis_interface()
    else:
        analysis_interface()

if __name__ == "__main__":
    main()