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
import warnings
warnings.filterwarnings('ignore')

# ============================================
# 🔧 Supabase Configuration
# ============================================

SUPABASE_URL = "https://drrpyazuzirqkvdveznn.supabase.co"
SUPABASE_KEY = "sb_publishable_x4RtFlvwJ_RAj3Evyy4KOA_mi-YOtBX"

# ============================================
# 🔧 Settings
# ============================================

st.set_page_config(
    page_title="GTA1CRYPTO - Advanced Analyzer",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="auto"
)

MAX_CANDLES = 500
ADMIN_USERNAME = "adminSO"
ADMIN_PASSWORD = "admin25SO"

# ============================================
# 🗄️ User Management with Supabase
# ============================================

try:
    from supabase import create_client, Client
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"❌ Failed to connect to Supabase: {str(e)}")
    st.info("📝 Please install supabase: pip install supabase")
    st.stop()

class UserManager:
    def __init__(self):
        self.supabase = supabase
        self._ensure_admin()
    
    def _hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()
    
    def _ensure_admin(self):
        try:
            result = self.supabase.table("users").select("*").eq("username", ADMIN_USERNAME).execute()
            if not result.data:
                data = {
                    "username": ADMIN_USERNAME,
                    "password": self._hash_password(ADMIN_PASSWORD),
                    "email": "admin@example.com",
                    "active": 1,
                    "created_at": datetime.now().isoformat(),
                    "is_admin": 1,
                    "payment_status": "paid",
                    "payment_date": datetime.now().isoformat(),
                    "expiry_date": (datetime.now() + timedelta(days=365)).isoformat()
                }
                self.supabase.table("users").insert(data).execute()
        except Exception as e:
            print(f"❌ Admin creation error: {e}")
    
    def register_user(self, username, password, email=""):
        if len(username) < 3:
            return False, "❌ Username must be at least 3 characters!"
        if len(password) < 4:
            return False, "❌ Password must be at least 4 characters!"
        
        try:
            result = self.supabase.table("users").select("*").eq("username", username).execute()
            if result.data:
                return False, "❌ Username already exists!"
            
            data = {
                "username": username,
                "password": self._hash_password(password),
                "email": email,
                "active": 0,
                "created_at": datetime.now().isoformat(),
                "is_admin": 0,
                "payment_status": "pending"
            }
            
            self.supabase.table("users").insert(data).execute()
            return True, "✅ Registration successful! Wait for admin activation."
        except Exception as e:
            return False, f"❌ Error: {str(e)}"
    
    def login_user(self, username, password):
        try:
            result = self.supabase.table("users").select("*").eq("username", username).execute()
            
            if not result.data:
                return False, "❌ Username not found!"
            
            user = result.data[0]
            
            if user['active'] == 0:
                return False, "⛔ Account not activated! Contact admin."
            
            if user['password'] != self._hash_password(password):
                return False, "❌ Incorrect password!"
            
            self.supabase.table("users").update({"last_login": datetime.now().isoformat()}).eq("username", username).execute()
            
            return True, "✅ Login successful!"
        except Exception as e:
            return False, f"❌ Error: {str(e)}"
    
    def activate_user(self, username):
        if username == ADMIN_USERNAME:
            return False, "❌ Admin is already activated!"
        
        try:
            result = self.supabase.table("users").select("*").eq("username", username).execute()
            if not result.data:
                return False, "❌ User not found!"
            
            user = result.data[0]
            
            if user['active'] == 1:
                return False, f"✅ {username} is already active!"
            
            expiry = datetime.now() + timedelta(days=30)
            data = {
                "active": 1,
                "payment_status": "paid",
                "payment_date": datetime.now().isoformat(),
                "expiry_date": expiry.isoformat()
            }
            
            self.supabase.table("users").update(data).eq("username", username).execute()
            return True, f"✅ Account {username} activated! (Expires: {expiry.strftime('%Y-%m-%d')})"
        except Exception as e:
            return False, f"❌ Error: {str(e)}"
    
    def deactivate_user(self, username):
        if username == ADMIN_USERNAME:
            return False, "❌ Cannot deactivate admin!"
        
        try:
            result = self.supabase.table("users").select("*").eq("username", username).execute()
            if not result.data:
                return False, "❌ User not found!"
            
            if result.data[0]['active'] == 0:
                return False, f"⚠️ {username} is already deactivated!"
            
            self.supabase.table("users").update({"active": 0, "payment_status": "expired"}).eq("username", username).execute()
            return True, f"✅ Account {username} deactivated!"
        except Exception as e:
            return False, f"❌ Error: {str(e)}"
    
    def delete_user(self, username):
        if username == ADMIN_USERNAME:
            return False, "❌ Cannot delete admin!"
        
        try:
            result = self.supabase.table("users").select("*").eq("username", username).execute()
            if not result.data:
                return False, "❌ User not found!"
            
            self.supabase.table("users").delete().eq("username", username).execute()
            return True, f"✅ User {username} deleted permanently!"
        except Exception as e:
            return False, f"❌ Error: {str(e)}"
    
    def extend_subscription(self, username, days=30):
        try:
            result = self.supabase.table("users").select("expiry_date, active").eq("username", username).execute()
            if not result.data:
                return False, "❌ User not found!"
            
            user = result.data[0]
            
            if user['active'] == 0:
                self.supabase.table("users").update({"active": 1, "payment_status": "paid"}).eq("username", username).execute()
            
            if user.get('expiry_date'):
                current_expiry = datetime.fromisoformat(user['expiry_date'])
                if current_expiry < datetime.now():
                    new_expiry = datetime.now() + timedelta(days=days)
                else:
                    new_expiry = current_expiry + timedelta(days=days)
            else:
                new_expiry = datetime.now() + timedelta(days=days)
            
            self.supabase.table("users").update({
                "expiry_date": new_expiry.isoformat(),
                "payment_status": "paid",
                "active": 1
            }).eq("username", username).execute()
            
            return True, f"✅ Subscription extended for {username} (+{days} days)"
        except Exception as e:
            return False, f"❌ Error: {str(e)}"
    
    def get_pending_users(self):
        try:
            result = self.supabase.table("users").select("*").eq("active", 0).eq("is_admin", 0).execute()
            users = {}
            for user in result.data:
                users[user['username']] = {"email": user.get('email', ''), "created_at": user.get('created_at', '')}
            return users
        except:
            return {}
    
    def get_all_users(self):
        try:
            result = self.supabase.table("users").select("*").execute()
            users = {}
            for user in result.data:
                users[user['username']] = user
            return users
        except:
            return {}
    
    def get_users_count(self):
        try:
            total = len(self.supabase.table("users").select("*").execute().data)
            active = len(self.supabase.table("users").select("*").eq("active", 1).execute().data)
            pending = len(self.supabase.table("users").select("*").eq("active", 0).eq("is_admin", 0).execute().data)
            admin = len(self.supabase.table("users").select("*").eq("is_admin", 1).execute().data)
            return total, active, pending, admin
        except:
            return 0, 0, 0, 0
    
    def is_admin(self, username):
        try:
            result = self.supabase.table("users").select("is_admin").eq("username", username).execute()
            return result.data and result.data[0]['is_admin'] == 1
        except:
            return False
    
    def get_user_data(self, username):
        try:
            result = self.supabase.table("users").select("*").eq("username", username).execute()
            if result.data:
                return result.data[0]
            return None
        except:
            return None

# ============================================
# 🏦 Bitget Exchange
# ============================================

@st.cache_resource
def get_exchange_spot():
    try:
        exchange = ccxt.bitget({
            'rateLimit': 3000,
            'enableRateLimit': True,
            'options': {'defaultType': 'spot', 'adjustForTimeDifference': True}
        })
        exchange.fetch_ohlcv('BTC/USDT', '1h', limit=1)
        return exchange
    except:
        return None

@st.cache_resource
def get_exchange_future():
    try:
        exchange = ccxt.bitget({
            'rateLimit': 3000,
            'enableRateLimit': True,
            'options': {'defaultType': 'swap', 'adjustForTimeDifference': True}
        })
        exchange.fetch_ohlcv('BTC/USDT:USDT', '1h', limit=1)
        return exchange
    except:
        return None

# ============================================
# 📊 Data Fetcher - بدون كاش
# ============================================

def fetch_candles(symbol, timeframe='1h', limit=500):
    clean_symbol = symbol.upper().strip()
    is_future = ':' in clean_symbol or clean_symbol.endswith('-PERP') or clean_symbol.endswith('-SWAP') or clean_symbol.startswith('XAU') or clean_symbol.startswith('XAG')
    
    if is_future:
        exchange = get_exchange_future()
        if '/' in clean_symbol and ':' not in clean_symbol:
            clean_symbol = clean_symbol.replace('/', '/') + ':USDT'
    else:
        exchange = get_exchange_spot()
    
    if not exchange:
        return None
    
    try:
        ohlcv = exchange.fetch_ohlcv(clean_symbol, timeframe, limit=min(limit, 1000))
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except:
        return None

def calculate_indicators(df):
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
        df['BB_upper'], df['BB_middle'], df['BB_lower'] = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2)
        df['volume_ma'] = talib.SMA(df['volume'], timeperiod=20)
        df['OBV'] = talib.OBV(df['close'], df['volume'])
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        df['VWAP'] = (df['volume'] * typical_price).cumsum() / df['volume'].cumsum()
        
        return df.dropna()
    except:
        return df

# ============================================
# 📊 Main Analyzer
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
        
    def fetch_data(self, symbol):
        try:
            df_1h = fetch_candles(symbol, '1h', MAX_CANDLES)
            df_4h = fetch_candles(symbol, '4h', MAX_CANDLES // 2)
            
            if df_1h is not None:
                df_1h = calculate_indicators(df_1h)
            if df_4h is not None:
                df_4h = calculate_indicators(df_4h)
            
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
            
            return df_1h, df_4h
        except:
            return None, None
    
    def fetch_data_15m(self, symbol):
        try:
            df_15m = fetch_candles(symbol, '15m', MAX_CANDLES)
            if df_15m is not None:
                df_15m = calculate_indicators(df_15m)
                current_price = df_15m['close'].iloc[-1]
                self.calculate_blue_liquidity_lines_15m(df_15m, current_price, symbol)
                self.calculate_white_liquidity_levels_15m(df_15m, current_price, symbol)
                self.calculate_yellow_liquidation_zones_15m(df_15m, symbol)
                self.calculate_orange_magnetic_zones_15m(df_15m, current_price, symbol)
            return df_15m
        except:
            return None
    
    def fetch_data_5m(self, symbol):
        try:
            df_5m = fetch_candles(symbol, '5m', MAX_CANDLES)
            if df_5m is not None:
                df_5m = calculate_indicators(df_5m)
                current_price = df_5m['close'].iloc[-1]
                self.calculate_blue_liquidity_lines_5m(df_5m, current_price, symbol)
                self.calculate_white_liquidity_levels_5m(df_5m, current_price, symbol)
                self.calculate_yellow_liquidation_zones_5m(df_5m, symbol)
                self.calculate_orange_magnetic_zones_5m(df_5m, current_price, symbol)
            return df_5m
        except:
            return None
    
    def fetch_data_1m(self, symbol):
        try:
            df_1m = fetch_candles(symbol, '1m', MAX_CANDLES)
            if df_1m is not None:
                df_1m = calculate_indicators(df_1m)
                current_price = df_1m['close'].iloc[-1]
                self.calculate_blue_liquidity_lines_1m(df_1m, current_price, symbol)
                self.calculate_white_liquidity_levels_1m(df_1m, current_price, symbol)
                self.calculate_yellow_liquidation_zones_1m(df_1m, symbol)
                self.calculate_orange_magnetic_zones_1m(df_1m, current_price, symbol)
            return df_1m
        except:
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
    
    def calculate_orange_magnetic_zones(self, df, current_price, symbol):
        orange_zones = []
        if df is None or len(df) < 100:
            self.orange_magnetic_zones[symbol] = orange_zones
            return
        try:
            returns = np.diff(df['close'].values) / df['close'].values[:-1]
            price_velocity = np.mean(np.abs(returns[-20:])) * 100 if len(returns) >= 20 else 1
            turning_points = []
            for i in range(2, len(df)-2):
                if (df['high'].iloc[i] > df['high'].iloc[i-1] and df['high'].iloc[i] > df['high'].iloc[i+1] and df['close'].iloc[i] > df['open'].iloc[i]):
                    turning_points.append(df['high'].iloc[i])
                if (df['low'].iloc[i] < df['low'].iloc[i-1] and df['low'].iloc[i] < df['low'].iloc[i+1] and df['close'].iloc[i] < df['open'].iloc[i]):
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
                    for cluster_id in np.unique(clusters):
                        cluster_points = turning_points[clusters == cluster_id]
                        if len(cluster_points) >= 2:
                            center_price = np.mean(cluster_points)
                            points_density = len(cluster_points) / (np.std(cluster_points) + 1)
                            distance_pct = abs(center_price - current_price) / current_price * 100
                            strength = min(points_density / 10, 1.0) * (1 - distance_pct / 10)
                            attraction = "↑" if center_price > current_price else "↓"
                            if distance_pct < price_velocity * 2:
                                orange_zones.append({
                                    'price': float(center_price), 'type': 'magnetic_zone',
                                    'strength': float(strength), 'distance_pct': distance_pct,
                                    'points_count': len(cluster_points), 'attraction_direction': attraction,
                                    'description': f'🧲 {attraction}', 'color': 'rgba(255, 165, 0, 0.5)',
                                    'width': 2 + strength * 2, 'dash': 'dot' if strength < 0.5 else 'solid'
                                })
        except:
            pass
        orange_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.orange_magnetic_zones[symbol] = orange_zones[:5]
    
    def calculate_orange_magnetic_zones_15m(self, df, current_price, symbol):
        orange_zones = []
        if df is None or len(df) < 100:
            self.orange_magnetic_zones_15m[symbol] = orange_zones
            return
        try:
            returns = np.diff(df['close'].values) / df['close'].values[:-1]
            price_velocity = np.mean(np.abs(returns[-30:])) * 100 if len(returns) >= 30 else 1
            turning_points = []
            for i in range(2, len(df)-2):
                if (df['high'].iloc[i] > df['high'].iloc[i-1] and df['high'].iloc[i] > df['high'].iloc[i+1] and df['close'].iloc[i] > df['open'].iloc[i]):
                    turning_points.append(df['high'].iloc[i])
                if (df['low'].iloc[i] < df['low'].iloc[i-1] and df['low'].iloc[i] < df['low'].iloc[i+1] and df['close'].iloc[i] < df['open'].iloc[i]):
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
                    for cluster_id in np.unique(clusters):
                        cluster_points = turning_points[clusters == cluster_id]
                        if len(cluster_points) >= 2:
                            center_price = np.mean(cluster_points)
                            points_density = len(cluster_points) / (np.std(cluster_points) + 1)
                            distance_pct = abs(center_price - current_price) / current_price * 100
                            strength = min(points_density / 10, 1.0) * (1 - distance_pct / 8)
                            attraction = "↑" if center_price > current_price else "↓"
                            if distance_pct < price_velocity * 2:
                                orange_zones.append({
                                    'price': float(center_price), 'type': 'magnetic_zone_15m',
                                    'strength': float(strength), 'distance_pct': distance_pct,
                                    'points_count': len(cluster_points), 'attraction_direction': attraction,
                                    'description': f'🧲{attraction}', 'color': 'rgba(255, 165, 0, 0.5)',
                                    'width': 2 + strength * 2, 'dash': 'dot' if strength < 0.5 else 'solid'
                                })
        except:
            pass
        orange_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.orange_magnetic_zones_15m[symbol] = orange_zones[:5]
    
    def calculate_orange_magnetic_zones_5m(self, df, current_price, symbol):
        orange_zones = []
        if df is None or len(df) < 80:
            self.orange_magnetic_zones_5m[symbol] = orange_zones
            return
        try:
            returns = np.diff(df['close'].values) / df['close'].values[:-1]
            price_velocity = np.mean(np.abs(returns[-40:])) * 100 if len(returns) >= 40 else 1
            turning_points = []
            for i in range(2, len(df)-2):
                if (df['high'].iloc[i] > df['high'].iloc[i-1] and df['high'].iloc[i] > df['high'].iloc[i+1] and df['close'].iloc[i] > df['open'].iloc[i]):
                    turning_points.append(df['high'].iloc[i])
                if (df['low'].iloc[i] < df['low'].iloc[i-1] and df['low'].iloc[i] < df['low'].iloc[i+1] and df['close'].iloc[i] < df['open'].iloc[i]):
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
                    for cluster_id in np.unique(clusters):
                        cluster_points = turning_points[clusters == cluster_id]
                        if len(cluster_points) >= 2:
                            center_price = np.mean(cluster_points)
                            points_density = len(cluster_points) / (np.std(cluster_points) + 1)
                            distance_pct = abs(center_price - current_price) / current_price * 100
                            strength = min(points_density / 10, 1.0) * (1 - distance_pct / 5)
                            attraction = "↑" if center_price > current_price else "↓"
                            if distance_pct < price_velocity * 2:
                                orange_zones.append({
                                    'price': float(center_price), 'type': 'magnetic_zone_5m',
                                    'strength': float(strength), 'distance_pct': distance_pct,
                                    'points_count': len(cluster_points), 'attraction_direction': attraction,
                                    'description': f'🧲{attraction}', 'color': 'rgba(255, 165, 0, 0.5)',
                                    'width': 2 + strength * 2, 'dash': 'dot' if strength < 0.5 else 'solid'
                                })
        except:
            pass
        orange_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.orange_magnetic_zones_5m[symbol] = orange_zones[:6]
    
    def calculate_orange_magnetic_zones_1m(self, df, current_price, symbol):
        orange_zones = []
        if df is None or len(df) < 60:
            self.orange_magnetic_zones_1m[symbol] = orange_zones
            return
        try:
            returns = np.diff(df['close'].values) / df['close'].values[:-1]
            price_velocity = np.mean(np.abs(returns[-50:])) * 100 if len(returns) >= 50 else 1
            turning_points = []
            for i in range(2, len(df)-2):
                if (df['high'].iloc[i] > df['high'].iloc[i-1] and df['high'].iloc[i] > df['high'].iloc[i+1] and df['close'].iloc[i] > df['open'].iloc[i]):
                    turning_points.append(df['high'].iloc[i])
                if (df['low'].iloc[i] < df['low'].iloc[i-1] and df['low'].iloc[i] < df['low'].iloc[i+1] and df['close'].iloc[i] < df['open'].iloc[i]):
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
                    for cluster_id in np.unique(clusters):
                        cluster_points = turning_points[clusters == cluster_id]
                        if len(cluster_points) >= 2:
                            center_price = np.mean(cluster_points)
                            points_density = len(cluster_points) / (np.std(cluster_points) + 1)
                            distance_pct = abs(center_price - current_price) / current_price * 100
                            strength = min(points_density / 10, 1.0) * (1 - distance_pct / 3)
                            attraction = "↑" if center_price > current_price else "↓"
                            if distance_pct < price_velocity * 1.5:
                                orange_zones.append({
                                    'price': float(center_price), 'type': 'magnetic_zone_1m',
                                    'strength': float(strength), 'distance_pct': distance_pct,
                                    'points_count': len(cluster_points), 'attraction_direction': attraction,
                                    'description': f'🧲{attraction}', 'color': 'rgba(255, 165, 0, 0.5)',
                                    'width': 1.5 + strength * 2, 'dash': 'dot' if strength < 0.5 else 'solid'
                                })
        except:
            pass
        orange_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.orange_magnetic_zones_1m[symbol] = orange_zones[:7]
    
    def calculate_orange_magnetic_zones_4h(self, df, current_price, symbol):
        orange_zones = []
        if df is None or len(df) < 50:
            self.orange_magnetic_zones_4h[symbol] = orange_zones
            return
        try:
            returns = np.diff(df['close'].values) / df['close'].values[:-1]
            price_velocity = np.mean(np.abs(returns[-15:])) * 100 if len(returns) >= 15 else 1
            turning_points = []
            for i in range(2, len(df)-2):
                if (df['high'].iloc[i] > df['high'].iloc[i-1] and df['high'].iloc[i] > df['high'].iloc[i+1] and df['close'].iloc[i] > df['open'].iloc[i]):
                    turning_points.append(df['high'].iloc[i])
                if (df['low'].iloc[i] < df['low'].iloc[i-1] and df['low'].iloc[i] < df['low'].iloc[i+1] and df['close'].iloc[i] < df['open'].iloc[i]):
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
                    for cluster_id in np.unique(clusters):
                        cluster_points = turning_points[clusters == cluster_id]
                        if len(cluster_points) >= 2:
                            center_price = np.mean(cluster_points)
                            points_density = len(cluster_points) / (np.std(cluster_points) + 1)
                            distance_pct = abs(center_price - current_price) / current_price * 100
                            strength = min(points_density / 10, 1.0) * (1 - distance_pct / 15)
                            attraction = "↑" if center_price > current_price else "↓"
                            if distance_pct < price_velocity * 2:
                                orange_zones.append({
                                    'price': float(center_price), 'type': 'magnetic_zone_4h',
                                    'strength': float(strength), 'distance_pct': distance_pct,
                                    'points_count': len(cluster_points), 'attraction_direction': attraction,
                                    'description': f'🧲{attraction}', 'color': 'rgba(255, 165, 0, 0.5)',
                                    'width': 2 + strength * 2, 'dash': 'dot' if strength < 0.5 else 'solid'
                                })
        except:
            pass
        orange_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.orange_magnetic_zones_4h[symbol] = orange_zones[:4]
    
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
                    if abs(price - current_price) / current_price * 100 <= 5:
                        touches = sum(1 for i in range(max(0, idx-5), min(len(df), idx+5)) if abs(df['low'].iloc[i] - price) <= price * 0.005)
                        support_levels.append((price, min(touches / 5, 1.0)))
                resistance_levels = []
                for idx in high_idx[-10:]:
                    price = df['high'].iloc[idx]
                    if abs(price - current_price) / current_price * 100 <= 5:
                        touches = sum(1 for i in range(max(0, idx-5), min(len(df), idx+5)) if abs(df['high'].iloc[i] - price) <= price * 0.005)
                        resistance_levels.append((price, min(touches / 5, 1.0)))
                for price, strength in support_levels[:3]:
                    yellow_zones.append({'price': price, 'type': 'support_zone', 'strength': strength, 'description': f'🟡 S ({strength:.2f})', 'color': '#FFFF00', 'width': 1 + (strength * 2), 'dash': 'dash'})
                for price, strength in resistance_levels[:3]:
                    yellow_zones.append({'price': price, 'type': 'resistance_zone', 'strength': strength, 'description': f'🟡 R ({strength:.2f})', 'color': '#FFFF00', 'width': 1 + (strength * 2), 'dash': 'dash'})
        except:
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
                    if abs(price - current_price) / current_price * 100 <= 3:
                        touches = sum(1 for i in range(max(0, idx-3), min(len(df), idx+3)) if abs(df['low'].iloc[i] - price) <= price * 0.003)
                        support_levels.append((price, min(touches / 3, 1.0)))
                resistance_levels = []
                for idx in high_idx[-15:]:
                    price = df['high'].iloc[idx]
                    if abs(price - current_price) / current_price * 100 <= 3:
                        touches = sum(1 for i in range(max(0, idx-3), min(len(df), idx+3)) if abs(df['high'].iloc[i] - price) <= price * 0.003)
                        resistance_levels.append((price, min(touches / 3, 1.0)))
                for price, strength in support_levels[:4]:
                    yellow_zones.append({'price': price, 'type': 'support_zone_15m', 'strength': strength, 'description': f'🟡 S15 ({strength:.2f})', 'color': '#FFFF00', 'width': 1 + (strength * 2), 'dash': 'dash'})
                for price, strength in resistance_levels[:4]:
                    yellow_zones.append({'price': price, 'type': 'resistance_zone_15m', 'strength': strength, 'description': f'🟡 R15 ({strength:.2f})', 'color': '#FFFF00', 'width': 1 + (strength * 2), 'dash': 'dash'})
        except:
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
                    if abs(price - current_price) / current_price * 100 <= 2:
                        touches = sum(1 for i in range(max(0, idx-2), min(len(df), idx+2)) if abs(df['low'].iloc[i] - price) <= price * 0.002)
                        support_levels.append((price, min(touches / 2, 1.0)))
                resistance_levels = []
                for idx in high_idx[-20:]:
                    price = df['high'].iloc[idx]
                    if abs(price - current_price) / current_price * 100 <= 2:
                        touches = sum(1 for i in range(max(0, idx-2), min(len(df), idx+2)) if abs(df['high'].iloc[i] - price) <= price * 0.002)
                        resistance_levels.append((price, min(touches / 2, 1.0)))
                for price, strength in support_levels[:5]:
                    yellow_zones.append({'price': price, 'type': 'support_zone_5m', 'strength': strength, 'description': f'🟡 S5 ({strength:.2f})', 'color': '#FFFF00', 'width': 1 + (strength * 2), 'dash': 'dash'})
                for price, strength in resistance_levels[:5]:
                    yellow_zones.append({'price': price, 'type': 'resistance_zone_5m', 'strength': strength, 'description': f'🟡 R5 ({strength:.2f})', 'color': '#FFFF00', 'width': 1 + (strength * 2), 'dash': 'dash'})
        except:
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
                    if abs(price - current_price) / current_price * 100 <= 1.5:
                        touches = sum(1 for i in range(max(0, idx-1), min(len(df), idx+2)) if abs(df['low'].iloc[i] - price) <= price * 0.0015)
                        support_levels.append((price, min(touches / 2, 1.0)))
                resistance_levels = []
                for idx in high_idx[-25:]:
                    price = df['high'].iloc[idx]
                    if abs(price - current_price) / current_price * 100 <= 1.5:
                        touches = sum(1 for i in range(max(0, idx-1), min(len(df), idx+2)) if abs(df['high'].iloc[i] - price) <= price * 0.0015)
                        resistance_levels.append((price, min(touches / 2, 1.0)))
                for price, strength in support_levels[:6]:
                    yellow_zones.append({'price': price, 'type': 'support_zone_1m', 'strength': strength, 'description': f'🟡 S1 ({strength:.2f})', 'color': '#FFFF00', 'width': 1 + (strength * 1.5), 'dash': 'dash'})
                for price, strength in resistance_levels[:6]:
                    yellow_zones.append({'price': price, 'type': 'resistance_zone_1m', 'strength': strength, 'description': f'🟡 R1 ({strength:.2f})', 'color': '#FFFF00', 'width': 1 + (strength * 1.5), 'dash': 'dash'})
        except:
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
                    if abs(price - current_price) / current_price * 100 <= 8:
                        touches = sum(1 for i in range(max(0, idx-3), min(len(df), idx+3)) if abs(df['low'].iloc[i] - price) <= price * 0.008)
                        support_levels.append((price, min(touches / 3, 1.0)))
                resistance_levels = []
                for idx in high_idx[-8:]:
                    price = df['high'].iloc[idx]
                    if abs(price - current_price) / current_price * 100 <= 8:
                        touches = sum(1 for i in range(max(0, idx-3), min(len(df), idx+3)) if abs(df['high'].iloc[i] - price) <= price * 0.008)
                        resistance_levels.append((price, min(touches / 3, 1.0)))
                for price, strength in support_levels[:3]:
                    yellow_zones.append({'price': price, 'type': 'support_zone_4h', 'strength': strength, 'description': f'🟡 S4h ({strength:.2f})', 'color': '#FFFF00', 'width': 1 + (strength * 2), 'dash': 'dash'})
                for price, strength in resistance_levels[:3]:
                    yellow_zones.append({'price': price, 'type': 'resistance_zone_4h', 'strength': strength, 'description': f'🟡 R4h ({strength:.2f})', 'color': '#FFFF00', 'width': 1 + (strength * 2), 'dash': 'dash'})
        except:
            pass
        yellow_zones.sort(key=lambda x: x['strength'], reverse=True)
        self.yellow_liquidation_zones_4h[symbol] = yellow_zones[:5]
    
    def calculate_blue_liquidity_lines(self, df_1h, current_price, symbol):
        blue_lines = []
        if df_1h is None or len(df_1h) < 50:
            self.blue_liquidity_lines[symbol] = blue_lines
            return
        try:
            for i in range(max(0, len(df_1h)-20), len(df_1h)-1):
                candle = df_1h.iloc[i]; next_candle = df_1h.iloc[i+1]
                upper_wick = candle['high'] - max(candle['open'], candle['close'])
                lower_wick = min(candle['open'], candle['close']) - candle['low']
                body_size = abs(candle['close'] - candle['open'])
                total_range = candle['high'] - candle['low']
                if total_range == 0: continue
                if lower_wick > body_size * 2 and upper_wick < body_size * 0.5 and next_candle['close'] > candle['close']:
                    blue_lines.append({'price': candle['low'], 'type': 'buy_liquidity', 'strength': min(0.8 + (lower_wick/total_range), 0.95), 'timeframe': 'immediate', 'description': '🔵 B', 'color': '#1E90FF', 'width': 2 + (lower_wick/total_range * 3), 'dash': 'solid'})
                if upper_wick > body_size * 2 and lower_wick < body_size * 0.5 and next_candle['close'] < candle['close']:
                    blue_lines.append({'price': candle['high'], 'type': 'sell_liquidity', 'strength': min(0.8 + (upper_wick/total_range), 0.95), 'timeframe': 'immediate', 'description': '🔵 S', 'color': '#1E90FF', 'width': 2 + (upper_wick/total_range * 3), 'dash': 'solid'})
            lookback = min(50, len(df_1h))
            price_tolerance = current_price * 0.02
            local_highs = [df_1h['high'].iloc[i] for i in range(1, lookback-1) if df_1h['high'].iloc[i] > df_1h['high'].iloc[i-1] and df_1h['high'].iloc[i] > df_1h['high'].iloc[i+1]]
            local_lows = [df_1h['low'].iloc[i] for i in range(1, lookback-1) if df_1h['low'].iloc[i] < df_1h['low'].iloc[i-1] and df_1h['low'].iloc[i] < df_1h['low'].iloc[i+1]]
            for price in local_highs[:5]:
                if abs(price - current_price) <= price_tolerance:
                    blue_lines.append({'price': price, 'type': 'sell_liquidity', 'strength': 0.7, 'timeframe': 'near', 'description': '🔵 R', 'color': '#00BFFF', 'width': 2, 'dash': 'dash'})
            for price in local_lows[:5]:
                if abs(price - current_price) <= price_tolerance:
                    blue_lines.append({'price': price, 'type': 'buy_liquidity', 'strength': 0.7, 'timeframe': 'near', 'description': '🔵 S', 'color': '#00BFFF', 'width': 2, 'dash': 'dash'})
        except:
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
                candle = df_15m.iloc[i]; next_candle = df_15m.iloc[i+1]
                upper_wick = candle['high'] - max(candle['open'], candle['close'])
                lower_wick = min(candle['open'], candle['close']) - candle['low']
                body_size = abs(candle['close'] - candle['open'])
                total_range = candle['high'] - candle['low']
                if total_range == 0: continue
                if lower_wick > body_size * 2 and upper_wick < body_size * 0.3 and next_candle['close'] > candle['close']:
                    blue_lines.append({'price': candle['low'], 'type': 'buy_liquidity_15m', 'strength': min(0.8 + (lower_wick/total_range), 0.95), 'timeframe': 'immediate_15m', 'description': '🔵 B15', 'color': '#1E90FF', 'width': 2 + (lower_wick/total_range * 3), 'dash': 'solid'})
                if upper_wick > body_size * 2 and lower_wick < body_size * 0.3 and next_candle['close'] < candle['close']:
                    blue_lines.append({'price': candle['high'], 'type': 'sell_liquidity_15m', 'strength': min(0.8 + (upper_wick/total_range), 0.95), 'timeframe': 'immediate_15m', 'description': '🔵 S15', 'color': '#1E90FF', 'width': 2 + (upper_wick/total_range * 3), 'dash': 'solid'})
            lookback = min(80, len(df_15m))
            price_tolerance = current_price * 0.01
            local_highs = [df_15m['high'].iloc[i] for i in range(1, lookback-1) if df_15m['high'].iloc[i] > df_15m['high'].iloc[i-1] and df_15m['high'].iloc[i] > df_15m['high'].iloc[i+1]]
            local_lows = [df_15m['low'].iloc[i] for i in range(1, lookback-1) if df_15m['low'].iloc[i] < df_15m['low'].iloc[i-1] and df_15m['low'].iloc[i] < df_15m['low'].iloc[i+1]]
            for price in local_highs[:8]:
                if abs(price - current_price) <= price_tolerance:
                    blue_lines.append({'price': price, 'type': 'sell_liquidity_15m', 'strength': 0.7, 'timeframe': 'near_15m', 'description': '🔵 R15', 'color': '#00BFFF', 'width': 2, 'dash': 'dash'})
            for price in local_lows[:8]:
                if abs(price - current_price) <= price_tolerance:
                    blue_lines.append({'price': price, 'type': 'buy_liquidity_15m', 'strength': 0.7, 'timeframe': 'near_15m', 'description': '🔵 S15', 'color': '#00BFFF', 'width': 2, 'dash': 'dash'})
        except:
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
                candle = df_5m.iloc[i]; next_candle = df_5m.iloc[i+1]
                upper_wick = candle['high'] - max(candle['open'], candle['close'])
                lower_wick = min(candle['open'], candle['close']) - candle['low']
                body_size = abs(candle['close'] - candle['open'])
                total_range = candle['high'] - candle['low']
                if total_range == 0: continue
                if lower_wick > body_size * 1.8 and upper_wick < body_size * 0.4 and next_candle['close'] > candle['close']:
                    blue_lines.append({'price': candle['low'], 'type': 'buy_liquidity_5m', 'strength': min(0.8 + (lower_wick/total_range), 0.95), 'timeframe': 'immediate_5m', 'description': '🔵 B5', 'color': '#1E90FF', 'width': 2 + (lower_wick/total_range * 3), 'dash': 'solid'})
                if upper_wick > body_size * 1.8 and lower_wick < body_size * 0.4 and next_candle['close'] < candle['close']:
                    blue_lines.append({'price': candle['high'], 'type': 'sell_liquidity_5m', 'strength': min(0.8 + (upper_wick/total_range), 0.95), 'timeframe': 'immediate_5m', 'description': '🔵 S5', 'color': '#1E90FF', 'width': 2 + (upper_wick/total_range * 3), 'dash': 'solid'})
            lookback = min(100, len(df_5m))
            price_tolerance = current_price * 0.005
            local_highs = [df_5m['high'].iloc[i] for i in range(2, lookback-2) if df_5m['high'].iloc[i] > df_5m['high'].iloc[i-1] and df_5m['high'].iloc[i] > df_5m['high'].iloc[i-2] and df_5m['high'].iloc[i] > df_5m['high'].iloc[i+1] and df_5m['high'].iloc[i] > df_5m['high'].iloc[i+2]]
            local_lows = [df_5m['low'].iloc[i] for i in range(2, lookback-2) if df_5m['low'].iloc[i] < df_5m['low'].iloc[i-1] and df_5m['low'].iloc[i] < df_5m['low'].iloc[i-2] and df_5m['low'].iloc[i] < df_5m['low'].iloc[i+1] and df_5m['low'].iloc[i] < df_5m['low'].iloc[i+2]]
            for price in local_highs[:10]:
                if abs(price - current_price) <= price_tolerance:
                    blue_lines.append({'price': price, 'type': 'sell_liquidity_5m', 'strength': 0.7, 'timeframe': 'near_5m', 'description': '🔵 R5', 'color': '#00BFFF', 'width': 2, 'dash': 'dash'})
            for price in local_lows[:10]:
                if abs(price - current_price) <= price_tolerance:
                    blue_lines.append({'price': price, 'type': 'buy_liquidity_5m', 'strength': 0.7, 'timeframe': 'near_5m', 'description': '🔵 S5', 'color': '#00BFFF', 'width': 2, 'dash': 'dash'})
        except:
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
                candle = df_1m.iloc[i]; next_candle = df_1m.iloc[i+1]
                upper_wick = candle['high'] - max(candle['open'], candle['close'])
                lower_wick = min(candle['open'], candle['close']) - candle['low']
                body_size = abs(candle['close'] - candle['open'])
                total_range = candle['high'] - candle['low']
                if total_range == 0: continue
                if lower_wick > body_size * 1.5 and upper_wick < body_size * 0.5 and next_candle['close'] > candle['close']:
                    blue_lines.append({'price': candle['low'], 'type': 'buy_liquidity_1m', 'strength': min(0.7 + (lower_wick/total_range), 0.9), 'timeframe': 'immediate_1m', 'description': '🔵 B1', 'color': '#1E90FF', 'width': 1.5 + (lower_wick/total_range * 2), 'dash': 'solid'})
                if upper_wick > body_size * 1.5 and lower_wick < body_size * 0.5 and next_candle['close'] < candle['close']:
                    blue_lines.append({'price': candle['high'], 'type': 'sell_liquidity_1m', 'strength': min(0.7 + (upper_wick/total_range), 0.9), 'timeframe': 'immediate_1m', 'description': '🔵 S1', 'color': '#1E90FF', 'width': 1.5 + (upper_wick/total_range * 2), 'dash': 'solid'})
            lookback = min(120, len(df_1m))
            price_tolerance = current_price * 0.0025
            local_highs = [df_1m['high'].iloc[i] for i in range(2, lookback-2) if df_1m['high'].iloc[i] > df_1m['high'].iloc[i-1] and df_1m['high'].iloc[i] > df_1m['high'].iloc[i+1]]
            local_lows = [df_1m['low'].iloc[i] for i in range(2, lookback-2) if df_1m['low'].iloc[i] < df_1m['low'].iloc[i-1] and df_1m['low'].iloc[i] < df_1m['low'].iloc[i+1]]
            for price in local_highs[:12]:
                if abs(price - current_price) <= price_tolerance:
                    blue_lines.append({'price': price, 'type': 'sell_liquidity_1m', 'strength': 0.65, 'timeframe': 'near_1m', 'description': '🔵 R1', 'color': '#00BFFF', 'width': 1.8, 'dash': 'dash'})
            for price in local_lows[:12]:
                if abs(price - current_price) <= price_tolerance:
                    blue_lines.append({'price': price, 'type': 'buy_liquidity_1m', 'strength': 0.65, 'timeframe': 'near_1m', 'description': '🔵 S1', 'color': '#00BFFF', 'width': 1.8, 'dash': 'dash'})
        except:
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
                candle = df_4h.iloc[i]; next_candle = df_4h.iloc[i+1]
                upper_wick = candle['high'] - max(candle['open'], candle['close'])
                lower_wick = min(candle['open'], candle['close']) - candle['low']
                body_size = abs(candle['close'] - candle['open'])
                total_range = candle['high'] - candle['low']
                if total_range == 0: continue
                if lower_wick > body_size * 2 and upper_wick < body_size * 0.5 and next_candle['close'] > candle['close']:
                    blue_lines.append({'price': candle['low'], 'type': 'buy_liquidity_4h', 'strength': min(0.8 + (lower_wick/total_range), 0.95), 'timeframe': 'immediate_4h', 'description': '🔵 B4h', 'color': '#1E90FF', 'width': 2 + (lower_wick/total_range * 3), 'dash': 'solid'})
                if upper_wick > body_size * 2 and lower_wick < body_size * 0.5 and next_candle['close'] < candle['close']:
                    blue_lines.append({'price': candle['high'], 'type': 'sell_liquidity_4h', 'strength': min(0.8 + (upper_wick/total_range), 0.95), 'timeframe': 'immediate_4h', 'description': '🔵 S4h', 'color': '#1E90FF', 'width': 2 + (upper_wick/total_range * 3), 'dash': 'solid'})
            lookback = min(30, len(df_4h))
            price_tolerance = current_price * 0.03
            local_highs = [df_4h['high'].iloc[i] for i in range(1, lookback-1) if df_4h['high'].iloc[i] > df_4h['high'].iloc[i-1] and df_4h['high'].iloc[i] > df_4h['high'].iloc[i+1]]
            local_lows = [df_4h['low'].iloc[i] for i in range(1, lookback-1) if df_4h['low'].iloc[i] < df_4h['low'].iloc[i-1] and df_4h['low'].iloc[i] < df_4h['low'].iloc[i+1]]
            for price in local_highs[:5]:
                if abs(price - current_price) <= price_tolerance:
                    blue_lines.append({'price': price, 'type': 'sell_liquidity_4h', 'strength': 0.7, 'timeframe': 'near_4h', 'description': '🔵 R4h', 'color': '#00BFFF', 'width': 2, 'dash': 'dash'})
            for price in local_lows[:5]:
                if abs(price - current_price) <= price_tolerance:
                    blue_lines.append({'price': price, 'type': 'buy_liquidity_4h', 'strength': 0.7, 'timeframe': 'near_4h', 'description': '🔵 S4h', 'color': '#00BFFF', 'width': 2, 'dash': 'dash'})
        except:
            pass
        unique_lines = []
        seen_prices = set()
        for line in blue_lines:
            if line['price'] not in seen_prices:
                seen_prices.add(line['price'])
                unique_lines.append(line)
        self.blue_liquidity_lines_4h[symbol] = unique_lines
    
    def calculate_white_liquidity_levels(self, df_1h, current_price, symbol):
        white_levels = []
        if df_1h is None:
            self.white_liquidity_levels[symbol] = white_levels
            return
        try:
            support, resistance = self.find_strong_support_resistance(df_1h, window=12)
            for price, strength in support[:3]:
                if strength > 0.7 and abs(price - current_price) / current_price * 100 <= 5:
                    white_levels.append({'price': price, 'type': 'strong_support', 'strength': strength, 'description': f'⚪ S ({strength:.2f})', 'color': 'white', 'width': 1 + (strength * 2), 'dash': 'dash'})
            for price, strength in resistance[:3]:
                if strength > 0.7 and abs(price - current_price) / current_price * 100 <= 5:
                    white_levels.append({'price': price, 'type': 'strong_resistance', 'strength': strength, 'description': f'⚪ R ({strength:.2f})', 'color': 'white', 'width': 1 + (strength * 2), 'dash': 'dash'})
        except:
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
                if strength > 0.6 and abs(price - current_price) / current_price * 100 <= 3:
                    white_levels.append({'price': price, 'type': 'strong_support_15m', 'strength': strength, 'description': f'⚪ S15 ({strength:.2f})', 'color': 'white', 'width': 1 + (strength * 2), 'dash': 'dash'})
            for price, strength in resistance[:4]:
                if strength > 0.6 and abs(price - current_price) / current_price * 100 <= 3:
                    white_levels.append({'price': price, 'type': 'strong_resistance_15m', 'strength': strength, 'description': f'⚪ R15 ({strength:.2f})', 'color': 'white', 'width': 1 + (strength * 2), 'dash': 'dash'})
        except:
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
                if strength > 0.55 and abs(price - current_price) / current_price * 100 <= 2:
                    white_levels.append({'price': price, 'type': 'strong_support_5m', 'strength': strength, 'description': f'⚪ S5 ({strength:.2f})', 'color': 'white', 'width': 1 + (strength * 2), 'dash': 'dash'})
            for price, strength in resistance[:5]:
                if strength > 0.55 and abs(price - current_price) / current_price * 100 <= 2:
                    white_levels.append({'price': price, 'type': 'strong_resistance_5m', 'strength': strength, 'description': f'⚪ R5 ({strength:.2f})', 'color': 'white', 'width': 1 + (strength * 2), 'dash': 'dash'})
        except:
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
                if strength > 0.5 and abs(price - current_price) / current_price * 100 <= 1.5:
                    white_levels.append({'price': price, 'type': 'strong_support_1m', 'strength': strength, 'description': f'⚪ S1 ({strength:.2f})', 'color': 'white', 'width': 1 + (strength * 1.5), 'dash': 'dash'})
            for price, strength in resistance[:6]:
                if strength > 0.5 and abs(price - current_price) / current_price * 100 <= 1.5:
                    white_levels.append({'price': price, 'type': 'strong_resistance_1m', 'strength': strength, 'description': f'⚪ R1 ({strength:.2f})', 'color': 'white', 'width': 1 + (strength * 1.5), 'dash': 'dash'})
        except:
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
                if strength > 0.7 and abs(price - current_price) / current_price * 100 <= 8:
                    white_levels.append({'price': price, 'type': 'strong_support_4h', 'strength': strength, 'description': f'⚪ S4h ({strength:.2f})', 'color': 'white', 'width': 1 + (strength * 2), 'dash': 'dash'})
            for price, strength in resistance[:3]:
                if strength > 0.7 and abs(price - current_price) / current_price * 100 <= 8:
                    white_levels.append({'price': price, 'type': 'strong_resistance_4h', 'strength': strength, 'description': f'⚪ R4h ({strength:.2f})', 'color': 'white', 'width': 1 + (strength * 2), 'dash': 'dash'})
        except:
            pass
        self.white_liquidity_levels_4h[symbol] = white_levels
    
    def find_strong_support_resistance(self, df, window=20):
        if len(df) < window * 2:
            return [], []
        try:
            high_idx = argrelextrema(df['high'].values, np.greater, order=window)[0]
            low_idx = argrelextrema(df['low'].values, np.less, order=window)[0]
            def cluster_and_score(levels, price_data, is_support=True):
                if len(levels) == 0:
                    return []
                eps_value = max(np.std(levels) * 0.5, np.mean(levels) * 0.001)
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
                        touches = len(price_data[(price_data['low' if is_support else 'high'] <= avg_price * 1.005) & (price_data['low' if is_support else 'high'] >= avg_price * 0.995)])
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
        except:
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
                eps_value = max(np.std(levels) * 0.3, np.mean(levels) * 0.001)
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
                        touches = len(price_data[(price_data['low' if is_support else 'high'] <= avg_price * 1.003) & (price_data['low' if is_support else 'high'] >= avg_price * 0.997)])
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
        except:
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
                eps_value = max(np.std(levels) * 0.2, np.mean(levels) * 0.0005)
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
                        touches = len(price_data[(price_data['low' if is_support else 'high'] <= avg_price * 1.002) & (price_data['low' if is_support else 'high'] >= avg_price * 0.998)])
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
        except:
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
                eps_value = max(np.std(levels) * 0.15, np.mean(levels) * 0.0003)
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
                        touches = len(price_data[(price_data['low' if is_support else 'high'] <= avg_price * 1.0015) & (price_data['low' if is_support else 'high'] >= avg_price * 0.9985)])
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
        except:
            return [], []
    
    def create_main_chart(self, df_1h, symbol):
        if df_1h is None or df_1h.empty:
            return go.Figure()
        fig = make_subplots(rows=1, cols=1)
        fig.add_trace(go.Candlestick(x=df_1h['timestamp'], open=df_1h['open'], high=df_1h['high'], low=df_1h['low'], close=df_1h['close'], name='Price', increasing_line_color='#00ff88', decreasing_line_color='#ff0066'), row=1, col=1)
        for line in self.blue_liquidity_lines.get(symbol, []):
            fig.add_shape(type='line', x0=df_1h['timestamp'].iloc[0], x1=df_1h['timestamp'].iloc[-1], y0=line['price'], y1=line['price'], line=dict(color=line['color'], width=line['width'], dash=line['dash']), row=1, col=1)
            fig.add_annotation(x=df_1h['timestamp'].iloc[-1], y=line['price'], text=line['description'], showarrow=True, arrowhead=1, ax=35, ay=0, bgcolor='rgba(30, 144, 255, 0.6)', bordercolor='#1E90FF', borderwidth=1, font=dict(color='white', size=7), row=1, col=1)
        for level in self.white_liquidity_levels.get(symbol, []):
            fig.add_shape(type='line', x0=df_1h['timestamp'].iloc[0], x1=df_1h['timestamp'].iloc[-1], y0=level['price'], y1=level['price'], line=dict(color=level['color'], width=level['width'], dash=level['dash']), row=1, col=1)
            fig.add_annotation(x=df_1h['timestamp'].iloc[-1], y=level['price'], text=level['description'], showarrow=True, arrowhead=1, ax=35, ay=0, bgcolor='rgba(255, 255, 255, 0.6)', bordercolor='white', borderwidth=1, font=dict(color='black', size=7), row=1, col=1)
        for zone in self.yellow_liquidation_zones.get(symbol, []):
            fig.add_shape(type='line', x0=df_1h['timestamp'].iloc[0], x1=df_1h['timestamp'].iloc[-1], y0=zone['price'], y1=zone['price'], line=dict(color=zone['color'], width=zone['width'], dash=zone['dash']), row=1, col=1)
            fig.add_annotation(x=df_1h['timestamp'].iloc[-1], y=zone['price'], text=zone['description'], showarrow=True, arrowhead=1, ax=35, ay=0, bgcolor='rgba(255, 255, 0, 0.6)', bordercolor='#FFFF00', borderwidth=1, font=dict(color='black', size=7), row=1, col=1)
        for zone in self.orange_magnetic_zones.get(symbol, []):
            fig.add_shape(type='line', x0=df_1h['timestamp'].iloc[0], x1=df_1h['timestamp'].iloc[-1], y0=zone['price'], y1=zone['price'], line=dict(color=zone['color'], width=zone['width'], dash=zone['dash']), row=1, col=1)
            fig.add_annotation(x=df_1h['timestamp'].iloc[-1], y=zone['price'], text=zone['description'], showarrow=True, arrowhead=1, ax=35, ay=0, bgcolor='rgba(255, 165, 0, 0.6)', bordercolor='#FFA500', borderwidth=1, font=dict(color='white', size=7), row=1, col=1)
        fig.update_layout(title=f"📊 {symbol} - 1h", height=700, showlegend=False, hovermode="x unified", plot_bgcolor='rgba(10, 10, 30, 0.5)', paper_bgcolor='rgba(10, 10, 30, 0.5)', margin=dict(l=10, r=10, t=40, b=10), font=dict(color='#e0f0ff', size=10))
        fig.update_xaxes(rangeslider_visible=False, row=1, col=1)
        return fig
    
    def create_15m_chart(self, df_15m, symbol):
        if df_15m is None or df_15m.empty:
            return go.Figure()
        fig = make_subplots(rows=1, cols=1)
        fig.add_trace(go.Candlestick(x=df_15m['timestamp'], open=df_15m['open'], high=df_15m['high'], low=df_15m['low'], close=df_15m['close'], name='Price', increasing_line_color='#00ff88', decreasing_line_color='#ff0066'), row=1, col=1)
        for line in self.blue_liquidity_lines_15m.get(symbol, []):
            fig.add_shape(type='line', x0=df_15m['timestamp'].iloc[0], x1=df_15m['timestamp'].iloc[-1], y0=line['price'], y1=line['price'], line=dict(color=line['color'], width=line['width'], dash=line['dash']), row=1, col=1)
            fig.add_annotation(x=df_15m['timestamp'].iloc[-1], y=line['price'], text=line['description'], showarrow=True, arrowhead=1, ax=25, ay=0, bgcolor='rgba(30, 144, 255, 0.5)', bordercolor='#1E90FF', borderwidth=1, font=dict(color='white', size=6), row=1, col=1)
        for level in self.white_liquidity_levels_15m.get(symbol, []):
            fig.add_shape(type='line', x0=df_15m['timestamp'].iloc[0], x1=df_15m['timestamp'].iloc[-1], y0=level['price'], y1=level['price'], line=dict(color=level['color'], width=level['width'], dash=level['dash']), row=1, col=1)
            fig.add_annotation(x=df_15m['timestamp'].iloc[-1], y=level['price'], text=level['description'], showarrow=True, arrowhead=1, ax=25, ay=0, bgcolor='rgba(255, 255, 255, 0.5)', bordercolor='white', borderwidth=1, font=dict(color='black', size=6), row=1, col=1)
        for zone in self.yellow_liquidation_zones_15m.get(symbol, []):
            fig.add_shape(type='line', x0=df_15m['timestamp'].iloc[0], x1=df_15m['timestamp'].iloc[-1], y0=zone['price'], y1=zone['price'], line=dict(color=zone['color'], width=zone['width'], dash=zone['dash']), row=1, col=1)
            fig.add_annotation(x=df_15m['timestamp'].iloc[-1], y=zone['price'], text=zone['description'], showarrow=True, arrowhead=1, ax=25, ay=0, bgcolor='rgba(255, 255, 0, 0.5)', bordercolor='#FFFF00', borderwidth=1, font=dict(color='black', size=6), row=1, col=1)
        for zone in self.orange_magnetic_zones_15m.get(symbol, []):
            fig.add_shape(type='line', x0=df_15m['timestamp'].iloc[0], x1=df_15m['timestamp'].iloc[-1], y0=zone['price'], y1=zone['price'], line=dict(color=zone['color'], width=zone['width'], dash=zone['dash']), row=1, col=1)
            fig.add_annotation(x=df_15m['timestamp'].iloc[-1], y=zone['price'], text=zone['description'], showarrow=True, arrowhead=1, ax=25, ay=0, bgcolor='rgba(255, 165, 0, 0.5)', bordercolor='#FFA500', borderwidth=1, font=dict(color='white', size=6), row=1, col=1)
        fig.update_layout(title=f"📊 {symbol} - 15m", height=700, showlegend=False, hovermode="x unified", plot_bgcolor='rgba(10, 10, 30, 0.5)', paper_bgcolor='rgba(10, 10, 30, 0.5)', margin=dict(l=10, r=10, t=40, b=10), font=dict(color='#e0f0ff', size=10))
        return fig
    
    def create_5m_chart(self, df_5m, symbol):
        if df_5m is None or df_5m.empty:
            return go.Figure()
        fig = make_subplots(rows=1, cols=1)
        fig.add_trace(go.Candlestick(x=df_5m['timestamp'], open=df_5m['open'], high=df_5m['high'], low=df_5m['low'], close=df_5m['close'], name='Price', increasing_line_color='#00ff88', decreasing_line_color='#ff0066'), row=1, col=1)
        for line in self.blue_liquidity_lines_5m.get(symbol, []):
            fig.add_shape(type='line', x0=df_5m['timestamp'].iloc[0], x1=df_5m['timestamp'].iloc[-1], y0=line['price'], y1=line['price'], line=dict(color=line['color'], width=line['width'], dash=line['dash']), row=1, col=1)
            fig.add_annotation(x=df_5m['timestamp'].iloc[-1], y=line['price'], text=line['description'], showarrow=True, arrowhead=1, ax=20, ay=0, bgcolor='rgba(30, 144, 255, 0.5)', bordercolor='#1E90FF', borderwidth=1, font=dict(color='white', size=6), row=1, col=1)
        for level in self.white_liquidity_levels_5m.get(symbol, []):
            fig.add_shape(type='line', x0=df_5m['timestamp'].iloc[0], x1=df_5m['timestamp'].iloc[-1], y0=level['price'], y1=level['price'], line=dict(color=level['color'], width=level['width'], dash=level['dash']), row=1, col=1)
            fig.add_annotation(x=df_5m['timestamp'].iloc[-1], y=level['price'], text=level['description'], showarrow=True, arrowhead=1, ax=20, ay=0, bgcolor='rgba(255, 255, 255, 0.5)', bordercolor='white', borderwidth=1, font=dict(color='black', size=6), row=1, col=1)
        for zone in self.yellow_liquidation_zones_5m.get(symbol, []):
            fig.add_shape(type='line', x0=df_5m['timestamp'].iloc[0], x1=df_5m['timestamp'].iloc[-1], y0=zone['price'], y1=zone['price'], line=dict(color=zone['color'], width=zone['width'], dash=zone['dash']), row=1, col=1)
            fig.add_annotation(x=df_5m['timestamp'].iloc[-1], y=zone['price'], text=zone['description'], showarrow=True, arrowhead=1, ax=20, ay=0, bgcolor='rgba(255, 255, 0, 0.5)', bordercolor='#FFFF00', borderwidth=1, font=dict(color='black', size=6), row=1, col=1)
        for zone in self.orange_magnetic_zones_5m.get(symbol, []):
            fig.add_shape(type='line', x0=df_5m['timestamp'].iloc[0], x1=df_5m['timestamp'].iloc[-1], y0=zone['price'], y1=zone['price'], line=dict(color=zone['color'], width=zone['width'], dash=zone['dash']), row=1, col=1)
            fig.add_annotation(x=df_5m['timestamp'].iloc[-1], y=zone['price'], text=zone['description'], showarrow=True, arrowhead=1, ax=20, ay=0, bgcolor='rgba(255, 165, 0, 0.5)', bordercolor='#FFA500', borderwidth=1, font=dict(color='white', size=6), row=1, col=1)
        fig.update_layout(title=f"📊 {symbol} - 5m", height=700, showlegend=False, hovermode="x unified", plot_bgcolor='rgba(10, 10, 30, 0.5)', paper_bgcolor='rgba(10, 10, 30, 0.5)', margin=dict(l=10, r=10, t=40, b=10), font=dict(color='#e0f0ff', size=10))
        return fig
    
    def create_1m_chart(self, df_1m, symbol):
        if df_1m is None or df_1m.empty:
            return go.Figure()
        fig = make_subplots(rows=1, cols=1)
        fig.add_trace(go.Candlestick(x=df_1m['timestamp'], open=df_1m['open'], high=df_1m['high'], low=df_1m['low'], close=df_1m['close'], name='Price', increasing_line_color='#00ff88', decreasing_line_color='#ff0066'), row=1, col=1)
        for line in self.blue_liquidity_lines_1m.get(symbol, []):
            fig.add_shape(type='line', x0=df_1m['timestamp'].iloc[0], x1=df_1m['timestamp'].iloc[-1], y0=line['price'], y1=line['price'], line=dict(color=line['color'], width=line['width'], dash=line['dash']), row=1, col=1)
            fig.add_annotation(x=df_1m['timestamp'].iloc[-1], y=line['price'], text=line['description'], showarrow=True, arrowhead=1, ax=15, ay=0, bgcolor='rgba(30, 144, 255, 0.5)', bordercolor='#1E90FF', borderwidth=1, font=dict(color='white', size=5), row=1, col=1)
        for level in self.white_liquidity_levels_1m.get(symbol, []):
            fig.add_shape(type='line', x0=df_1m['timestamp'].iloc[0], x1=df_1m['timestamp'].iloc[-1], y0=level['price'], y1=level['price'], line=dict(color=level['color'], width=level['width'], dash=level['dash']), row=1, col=1)
            fig.add_annotation(x=df_1m['timestamp'].iloc[-1], y=level['price'], text=level['description'], showarrow=True, arrowhead=1, ax=15, ay=0, bgcolor='rgba(255, 255, 255, 0.5)', bordercolor='white', borderwidth=1, font=dict(color='black', size=5), row=1, col=1)
        for zone in self.yellow_liquidation_zones_1m.get(symbol, []):
            fig.add_shape(type='line', x0=df_1m['timestamp'].iloc[0], x1=df_1m['timestamp'].iloc[-1], y0=zone['price'], y1=zone['price'], line=dict(color=zone['color'], width=zone['width'], dash=zone['dash']), row=1, col=1)
            fig.add_annotation(x=df_1m['timestamp'].iloc[-1], y=zone['price'], text=zone['description'], showarrow=True, arrowhead=1, ax=15, ay=0, bgcolor='rgba(255, 255, 0, 0.5)', bordercolor='#FFFF00', borderwidth=1, font=dict(color='black', size=5), row=1, col=1)
        for zone in self.orange_magnetic_zones_1m.get(symbol, []):
            fig.add_shape(type='line', x0=df_1m['timestamp'].iloc[0], x1=df_1m['timestamp'].iloc[-1], y0=zone['price'], y1=zone['price'], line=dict(color=zone['color'], width=zone['width'], dash=zone['dash']), row=1, col=1)
            fig.add_annotation(x=df_1m['timestamp'].iloc[-1], y=zone['price'], text=zone['description'], showarrow=True, arrowhead=1, ax=15, ay=0, bgcolor='rgba(255, 165, 0, 0.5)', bordercolor='#FFA500', borderwidth=1, font=dict(color='white', size=5), row=1, col=1)
        fig.update_layout(title=f"📊 {symbol} - 1m", height=700, showlegend=False, hovermode="x unified", plot_bgcolor='rgba(10, 10, 30, 0.5)', paper_bgcolor='rgba(10, 10, 30, 0.5)', margin=dict(l=10, r=10, t=40, b=10), font=dict(color='#e0f0ff', size=8))
        return fig
    
    def create_4h_chart(self, df_4h, symbol):
        if df_4h is None or df_4h.empty:
            return go.Figure()
        fig = make_subplots(rows=1, cols=1)
        fig.add_trace(go.Candlestick(x=df_4h['timestamp'], open=df_4h['open'], high=df_4h['high'], low=df_4h['low'], close=df_4h['close'], name='Price', increasing_line_color='#00ff88', decreasing_line_color='#ff0066'), row=1, col=1)
        for line in self.blue_liquidity_lines_4h.get(symbol, []):
            fig.add_shape(type='line', x0=df_4h['timestamp'].iloc[0], x1=df_4h['timestamp'].iloc[-1], y0=line['price'], y1=line['price'], line=dict(color=line['color'], width=line['width'], dash=line['dash']), row=1, col=1)
            fig.add_annotation(x=df_4h['timestamp'].iloc[-1], y=line['price'], text=line['description'], showarrow=True, arrowhead=1, ax=35, ay=0, bgcolor='rgba(30, 144, 255, 0.6)', bordercolor='#1E90FF', borderwidth=1, font=dict(color='white', size=7), row=1, col=1)
        for level in self.white_liquidity_levels_4h.get(symbol, []):
            fig.add_shape(type='line', x0=df_4h['timestamp'].iloc[0], x1=df_4h['timestamp'].iloc[-1], y0=level['price'], y1=level['price'], line=dict(color=level['color'], width=level['width'], dash=level['dash']), row=1, col=1)
            fig.add_annotation(x=df_4h['timestamp'].iloc[-1], y=level['price'], text=level['description'], showarrow=True, arrowhead=1, ax=35, ay=0, bgcolor='rgba(255, 255, 255, 0.6)', bordercolor='white', borderwidth=1, font=dict(color='black', size=7), row=1, col=1)
        for zone in self.yellow_liquidation_zones_4h.get(symbol, []):
            fig.add_shape(type='line', x0=df_4h['timestamp'].iloc[0], x1=df_4h['timestamp'].iloc[-1], y0=zone['price'], y1=zone['price'], line=dict(color=zone['color'], width=zone['width'], dash=zone['dash']), row=1, col=1)
            fig.add_annotation(x=df_4h['timestamp'].iloc[-1], y=zone['price'], text=zone['description'], showarrow=True, arrowhead=1, ax=35, ay=0, bgcolor='rgba(255, 255, 0, 0.6)', bordercolor='#FFFF00', borderwidth=1, font=dict(color='black', size=7), row=1, col=1)
        for zone in self.orange_magnetic_zones_4h.get(symbol, []):
            fig.add_shape(type='line', x0=df_4h['timestamp'].iloc[0], x1=df_4h['timestamp'].iloc[-1], y0=zone['price'], y1=zone['price'], line=dict(color=zone['color'], width=zone['width'], dash=zone['dash']), row=1, col=1)
            fig.add_annotation(x=df_4h['timestamp'].iloc[-1], y=zone['price'], text=zone['description'], showarrow=True, arrowhead=1, ax=35, ay=0, bgcolor='rgba(255, 165, 0, 0.6)', bordercolor='#FFA500', borderwidth=1, font=dict(color='white', size=7), row=1, col=1)
        fig.update_layout(title=f"📊 {symbol} - 4h", height=700, showlegend=False, hovermode="x unified", plot_bgcolor='rgba(10, 10, 30, 0.5)', paper_bgcolor='rgba(10, 10, 30, 0.5)', margin=dict(l=10, r=10, t=40, b=10), font=dict(color='#e0f0ff', size=10))
        return fig

# ============================================
# 🔐 Login & Admin Pages
# ============================================

def login_page(user_manager):
    st.markdown("""
    <div style="text-align: center; padding: 30px; background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%); border-radius: 15px;">
        <h1 style="color: #00ff88; font-size: 3em; margin-bottom: 5px;">🚀 GTA1CRYPTO</h1>
        <p style="color: #e0f0ff; font-size: 1.2em;">Advanced Liquidity Analysis Platform</p>
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
    <div style="background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
                padding: 20px; border-radius: 10px; margin-bottom: 20px;">
        <h2 style="color: #00ff88; text-align: center;">🛡️ Admin Panel</h2>
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
                            st.write(f"✅ {days_left} days left")
                        else:
                            st.write(f"⚠️ Expired")
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
    <div style="text-align: center; padding: 30px; background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
                border-radius: 15px; margin-bottom: 30px;">
        <h1 style="color: #00ff88;">💎 Activate Account</h1>
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
    <div style="text-align: center; padding: 15px; background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%); 
                border-radius: 15px; margin-bottom: 20px;">
        <h1 style="color: #00ff88; font-size: 2.2em; margin-bottom: 5px;">🚀 GTA1CRYPTO</h1>
        <p style="color: #e0f0ff; font-size: 1em;">Advanced Liquidity & Liquidation Analysis</p>
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
        st.markdown("### 🚀 GTA1CRYPTO")
        st.markdown(f"👤 **User:** {username}")
        st.markdown(f"🔑 **Role:** {'👑 Admin' if is_admin else '👤 User'}")
        
        if not is_admin:
            user_data = user_manager.get_user_data(username)
            if user_data and user_data.get('expiry_date'):
                try:
                    expiry = datetime.fromisoformat(user_data['expiry_date'])
                    days_left = (expiry - datetime.now()).days
                    if days_left > 0:
                        st.markdown(f"📅 **Days Left:** ✅ {days_left} days")
                    else:
                        st.markdown(f"📅 **Days Left:** ⚠️ Expired")
                except:
                    pass
        
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