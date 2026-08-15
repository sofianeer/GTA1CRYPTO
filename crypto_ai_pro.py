import streamlit as st
import pandas as pd
import numpy as np
import ccxt
import talib
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import LSTM, Dense, Dropout
from sklearn.preprocessing import MinMaxScaler
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import os
import joblib
import hashlib
from scipy.signal import argrelextrema
from scipy.stats import linregress
from sklearn.cluster import DBSCAN
import matplotlib.colors as mcolors
import time
import random
import textwrap
from PIL import Image
import base64

# إعدادات التطبيق
st.set_page_config(
    page_title="CryptoAI Pro+ 2100",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# إنشاء المجلدات إذا لم تكن موجودة
os.makedirs("models", exist_ok=True)
os.makedirs("data", exist_ok=True)

# تصميم فضائي متطور من عام 2100 مع تحسينات للوضوح
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;700&family=Roboto:wght@300;400;500&display=swap');

:root {
    --primary: #00f0ff;
    --secondary: #0080ff;
    --accent: #ff00f0;
    --dark: #0a0a1a;
    --darker: #050510;
    --light: #ffffff;  /* تغيير إلى أبيض نقي لتحسين الوضوح */
    --text: #e0e0e0;  /* لون النص الأساسي */
    --neon-glow: 0 0 10px rgba(0, 240, 255, 0.7), 0 0 20px rgba(0, 240, 255, 0.5);
    --neon-pink-glow: 0 0 10px rgba(255, 0, 240, 0.7), 0 0 20px rgba(255, 0, 240, 0.5);
    --space-gradient: linear-gradient(135deg, #000428 0%, #004e92 100%);
    --galaxy-bg: url('https://images.unsplash.com/photo-1534796636912-3b95b3ab5986?ixlib=rb-1.2.1&auto=format&fit=crop&w=1350&q=80');
}

body {
    background: var(--space-gradient);
    color: var(--text);
    font-family: 'Roboto', sans-serif;
    line-height: 1.6;
}

h1, h2, h3, h4, h5, h6 {
    font-family: 'Orbitron', sans-serif;
    color: var(--primary);
    text-shadow: var(--neon-glow);
    margin-bottom: 0.5em;
}

.stApp {
    background: var(--space-gradient);
}

/* الشريط الجانبي */
[data-testid="stSidebar"] {
    background: rgba(5, 5, 16, 0.95) !important;
    border-right: 1px solid rgba(0, 240, 255, 0.3);
    box-shadow: var(--neon-glow);
}

/* بطاقات التحليل */
.card {
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 20px;
    background: rgba(10, 10, 30, 0.8);
    border: 1px solid rgba(0, 240, 255, 0.3);
    box-shadow: var(--neon-glow);
    transition: all 0.3s ease;
    backdrop-filter: blur(5px);
    position: relative;
    overflow: hidden;
    color: var(--text);
}

.card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: radial-gradient(circle at 20% 30%, rgba(0, 240, 255, 0.1) 0%, transparent 70%);
    z-index: -1;
}

.card:hover {
    transform: translateY(-5px);
    box-shadow: 0 0 15px rgba(0, 240, 255, 0.8), 0 0 25px rgba(0, 240, 255, 0.4);
}

/* إشارات التداول */
.signal-buy {
    border-left: 4px solid #00ff88;
    background: linear-gradient(90deg, rgba(0, 255, 136, 0.1) 0%, rgba(10, 10, 30, 0) 100%);
    box-shadow: 0 0 10px rgba(0, 255, 136, 0.3);
}

.signal-sell {
    border-left: 4px solid #ff0066;
    background: linear-gradient(90deg, rgba(255, 0, 102, 0.1) 0%, rgba(10, 10, 30, 0) 100%);
    box-shadow: 0 0 10px rgba(255, 0, 102, 0.3);
}

/* مستويات الدعم والمقاومة */
.support-level {
    background: linear-gradient(90deg, rgba(0, 255, 136, 0.1) 0%, rgba(10, 10, 30, 0) 100%);
    border-left: 4px solid #00ff88;
}

.resistance-level {
    background: linear-gradient(90deg, rgba(255, 0, 102, 0.1) 0%, rgba(10, 10, 30, 0) 100%);
    border-left: 4px solid #ff0066;
}

.liquidity-zone {
    background: linear-gradient(90deg, rgba(0, 144, 255, 0.1) 0%, rgba(10, 10, 30, 0) 100%);
    border-left: 4px solid #0090ff;
}

/* تغيرات الأسعار */
.price-change-positive {
    color: #00ff88;
    font-weight: bold;
    text-shadow: 0 0 5px rgba(0, 255, 136, 0.5);
}

.price-change-negative {
    color: #ff0066;
    font-weight: bold;
    text-shadow: 0 0 5px rgba(255, 0, 102, 0.5);
}

/* قوة المستويات */
.level-strength {
    display: inline-block;
    padding: 3px 8px;
    border-radius: 12px;
    font-size: 0.8em;
    font-weight: bold;
    margin-top: 5px;
}

.high-strength {
    background-color: #00ff88;
    color: #050510;
    box-shadow: 0 0 8px rgba(0, 255, 136, 0.5);
}

.medium-strength {
    background-color: #ffaa00;
    color: #050510;
    box-shadow: 0 0 8px rgba(255, 170, 0, 0.5);
}

.low-strength {
    background-color: #ff0066;
    color: #050510;
    box-shadow: 0 0 8px rgba(255, 0, 102, 0.5);
}

/* ثقة الإشارة */
.signal-confidence {
    font-size: 2.5em;
    font-weight: bold;
    text-align: center;
    margin: 15px 0;
    text-shadow: var(--neon-glow);
}

.signal-confidence.high {
    color: #00ff88;
}

.signal-confidence.medium {
    color: #ffaa00;
}

.signal-confidence.low {
    color: #ff0066;
}

/* مربع الإشارة */
.signal-box {
    border-radius: 12px;
    padding: 25px;
    margin: 15px 0;
    text-align: center;
    font-weight: bold;
    font-size: 1.2em;
    backdrop-filter: blur(5px);
    position: relative;
    overflow: hidden;
    color: var(--light);
}

.signal-box::before {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: linear-gradient(
        to bottom right,
        rgba(0, 240, 255, 0) 0%,
        rgba(0, 240, 255, 0) 30%,
        rgba(0, 240, 255, 0.1) 45%,
        rgba(0, 240, 255, 0) 60%,
        rgba(0, 240, 255, 0) 100%
    );
    transform: rotate(30deg);
    animation: holographic-effect 6s linear infinite;
}

.signal-box.buy {
    background: rgba(0, 255, 136, 0.2);
    border: 1px solid #00ff88;
    color: #00ff88;
    box-shadow: 0 0 15px rgba(0, 255, 136, 0.5);
}

.signal-box.sell {
    background: rgba(255, 0, 102, 0.2);
    border: 1px solid #ff0066;
    color: #ff0066;
    box-shadow: 0 0 15px rgba(255, 0, 102, 0.5);
}

/* مستويات المخاطرة */
.risk-level {
    padding: 10px 15px;
    border-radius: 20px;
    font-weight: bold;
    display: inline-block;
    margin: 5px 0;
    backdrop-filter: blur(5px);
    color: white;
}

.risk-high {
    background-color: #ff0066;
    box-shadow: 0 0 10px rgba(255, 0, 102, 0.5);
}

.risk-medium {
    background-color: #ffaa00;
    box-shadow: 0 0 10px rgba(255, 170, 0, 0.5);
}

.risk-low {
    background-color: #00ff88;
    box-shadow: 0 0 10px rgba(0, 255, 136, 0.5);
}

/* لوحة التحليل */
.analysis-box {
    border-left: 4px solid var(--primary);
    padding: 20px;
    margin: 20px 0;
    background: rgba(0, 240, 255, 0.08);
    border-radius: 0 12px 12px 0;
    backdrop-filter: blur(5px);
    color: var(--text);
}

.advice-box {
    border-left: 4px solid #00ff88;
    padding: 20px;
    margin: 20px 0;
    background: rgba(0, 255, 136, 0.08);
    border-radius: 0 12px 12px 0;
    backdrop-filter: blur(5px);
    color: var(--text);
}

.warning-box {
    border-left: 4px solid #ffaa00;
    padding: 20px;
    margin: 20px 0;
    background: rgba(255, 170, 0, 0.08);
    border-radius: 0 12px 12px 0;
    backdrop-filter: blur(5px);
    color: var(--text);
}

/* الروبوت في الشريط الجانبي */
.sidebar-robot {
    width: 150px;
    height: 150px;
    margin: 0 auto 20px;
    display: block;
    animation: float 3s ease-in-out infinite;
    filter: drop-shadow(0 0 15px rgba(0, 240, 255, 0.7));
}

.sidebar-robot-container {
    text-align: center;
    padding: 20px 0;
    border-bottom: 1px solid rgba(0, 240, 255, 0.3);
    margin-bottom: 20px;
    position: relative;
}

.status-pulse {
    width: 12px;
    height: 12px;
    background-color: #00ff88;
    border-radius: 50%;
    display: inline-block;
    margin-right: 8px;
    animation: pulse 1.5s infinite;
}

.sidebar-notes {
    background: rgba(10, 20, 40, 0.7);
    border-radius: 12px;
    padding: 15px;
    margin-bottom: 15px;
    border: 1px solid rgba(0, 240, 255, 0.3);
    box-shadow: 0 0 15px rgba(0, 240, 255, 0.3);
    color: var(--text);
}

.sidebar-note {
    font-size: 0.95em;
    margin-bottom: 12px;
    padding-bottom: 12px;
    border-bottom: 1px dashed rgba(0, 240, 255, 0.3);
    line-height: 1.5;
}

.sidebar-note:last-child {
    border-bottom: none;
}

.ai-chip {
    display: inline-block;
    padding: 5px 12px;
    background: rgba(0, 240, 255, 0.15);
    border-radius: 20px;
    font-size: 0.8em;
    margin: 0 5px;
    border: 1px solid rgba(0, 240, 255, 0.3);
}

/* الرسوم المتحركة */
@keyframes float {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-10px); }
}

@keyframes holographic-effect {
    0% { transform: translateY(-100%) rotate(30deg); }
    100% { transform: translateY(100%) rotate(30deg); }
}

@keyframes neon-flicker {
    0%, 19.999%, 22%, 62.999%, 64%, 64.999%, 70%, 100% {
        opacity: 1;
    }
    20%, 21.999%, 63%, 63.999%, 65%, 69.999% {
        opacity: 0.5;
    }
}

@keyframes pulse {
    0% { transform: scale(0.95); opacity: 0.7; }
    50% { transform: scale(1.1); opacity: 1; }
    100% { transform: scale(0.95); opacity: 0.7; }
}

.neon-flicker {
    animation: neon-flicker 3s infinite alternate;
}

/* الأزرار الفضائية */
.futuristic-button {
    background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
    color: var(--dark);
    border: none;
    border-radius: 25px;
    padding: 12px 30px;
    font-family: 'Orbitron', sans-serif;
    font-weight: bold;
    cursor: pointer;
    transition: all 0.3s ease;
    box-shadow: 0 0 15px rgba(0, 240, 255, 0.5);
    text-transform: uppercase;
    letter-spacing: 1px;
    font-size: 1em;
}

.futuristic-button:hover {
    transform: translateY(-3px);
    box-shadow: 0 0 25px rgba(0, 240, 255, 0.8);
    background: linear-gradient(135deg, var(--accent) 0%, var(--primary) 100%);
    color: white;
}

/* شريط التبويب */
.stTabs [role="tablist"] {
    background: rgba(10, 20, 40, 0.6);
    border-radius: 12px;
    padding: 5px;
    margin-bottom: 20px;
    backdrop-filter: blur(5px);
}

.stTabs [role="tab"] {
    color: var(--text);
    font-weight: bold;
    padding: 10px 20px;
    border-radius: 8px;
    transition: all 0.3s ease;
}

.stTabs [role="tab"][aria-selected="true"] {
    background: rgba(0, 240, 255, 0.2);
    color: var(--primary);
    box-shadow: 0 0 10px rgba(0, 240, 255, 0.3);
}

/* الرأس الرئيسي */
.ai-header {
    background: linear-gradient(135deg, rgba(0, 240, 255, 0.1) 0%, rgba(0, 144, 255, 0.1) 100%);
    border-radius: 15px;
    padding: 30px;
    margin-bottom: 30px;
    text-align: center;
    border: 1px solid rgba(0, 240, 255, 0.3);
    box-shadow: var(--neon-glow);
    backdrop-filter: blur(5px);
    position: relative;
    overflow: hidden;
}

.ai-header::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: url('https://images.unsplash.com/photo-1506318137071-a8e063b4bec0?ixlib=rb-1.2.1&auto=format&fit=crop&w=1350&q=80');
    background-size: cover;
    opacity: 0.1;
    z-index: -1;
}

.ai-header h1 {
    font-size: 2.5em;
    margin-bottom: 10px;
    letter-spacing: 2px;
}

.ai-header p {
    font-size: 1.2em;
    margin-bottom: 20px;
}

/* الرسوم البيانية */
.js-plotly-plot .plotly, .js-plotly-plot .plotly div {
    background: transparent !important;
}

/* شريط التمرير */
::-webkit-scrollbar {
    width: 8px;
}

::-webkit-scrollbar-track {
    background: rgba(10, 10, 30, 0.5);
}

::-webkit-scrollbar-thumb {
    background: var(--primary);
    border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
    background: var(--accent);
}

/* تأثيرات النجوم */
.stars {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    z-index: -1;
    overflow: hidden;
}

.star {
    position: absolute;
    background: white;
    border-radius: 50%;
    animation: twinkle var(--duration) infinite ease-in-out;
}

@keyframes twinkle {
    0%, 100% { opacity: 0.2; }
    50% { opacity: 1; }
}

/* تأثيرات الجسيمات */
.particles {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    z-index: -1;
    overflow: hidden;
}

.particle {
    position: absolute;
    background: rgba(0, 240, 255, 0.5);
    border-radius: 50%;
    animation: float-particle var(--duration) infinite ease-in-out;
}

@keyframes float-particle {
    0% { transform: translate(0, 0); opacity: 0; }
    10% { opacity: 1; }
    90% { opacity: 1; }
    100% { transform: translate(var(--tx), var(--ty)); opacity: 0; }
}

/* تأثيرات الشاشة الفضائية */
.screen-effect {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    z-index: -1;
    background: 
        radial-gradient(circle at 20% 30%, rgba(0, 240, 255, 0.05) 0%, transparent 70%),
        radial-gradient(circle at 80% 70%, rgba(255, 0, 240, 0.05) 0%, transparent 70%);
    pointer-events: none;
}

/* تأثيرات الشبكة */
.grid-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    z-index: -1;
    background-image: 
        linear-gradient(rgba(0, 240, 255, 0.1) 1px, transparent 1px),
        linear-gradient(90deg, rgba(0, 240, 255, 0.1) 1px, transparent 1px);
    background-size: 50px 50px;
    opacity: 0.3;
    pointer-events: none;
}

/* تأثيرات النبض */
.pulse-effect {
    position: absolute;
    width: 100%;
    height: 100%;
    top: 0;
    left: 0;
    background: radial-gradient(circle, rgba(0, 240, 255, 0.1) 0%, transparent 70%);
    animation: pulse 4s infinite ease-in-out;
    z-index: -1;
}

/* تأثيرات الخطوط المتقاطعة */
.scanlines {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    z-index: -1;
    background: linear-gradient(
        to bottom,
        transparent 0%,
        rgba(0, 240, 255, 0.05) 50%,
        transparent 100%
    );
    background-size: 100% 4px;
    pointer-events: none;
    animation: scanline 8s linear infinite;
}

@keyframes scanline {
    0% { background-position: 0 0; }
    100% { background-position: 0 100%; }
}

/* تأثيرات البيانات */
.data-stream {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    z-index: -1;
    background: 
        linear-gradient(0deg, transparent 0%, rgba(0, 240, 255, 0.02) 1%, transparent 100%);
    background-size: 100% 8px;
    pointer-events: none;
    animation: datastream 20s linear infinite;
}

/* تحسينات للوضوح */
.stMarkdown, .stText, .stMetricLabel, .stMetricValue {
    color: var(--text) !important;
}

.stTextInput>div>div>input, .stSelectbox>div>div>select {
    color: var(--light) !important;
    background-color: rgba(10, 20, 40, 0.7) !important;
    border: 1px solid rgba(0, 240, 255, 0.3) !important;
}

.stSelectbox>div>div>select {
    padding: 10px !important;
}

.stButton>button {
    width: 100%;
}

/* بطاقة المساعد الذكي */
.assistant-card {
    background: rgba(10, 20, 40, 0.8);
    border-radius: 15px;
    padding: 20px;
    margin-bottom: 20px;
    border: 1px solid rgba(0, 240, 255, 0.3);
    box-shadow: 0 0 20px rgba(0, 240, 255, 0.2);
    position: relative;
    overflow: hidden;
}

.assistant-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: radial-gradient(circle at 70% 20%, rgba(0, 240, 255, 0.1) 0%, transparent 70%);
    z-index: -1;
}

.assistant-header {
    display: flex;
    align-items: center;
    margin-bottom: 15px;
    padding-bottom: 15px;
    border-bottom: 1px solid rgba(0, 240, 255, 0.2);
}

.assistant-avatar {
    width: 50px;
    height: 50px;
    border-radius: 50%;
    margin-right: 15px;
    background: rgba(0, 240, 255, 0.2);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
}

.assistant-message {
    padding: 15px;
    background: rgba(0, 240, 255, 0.1);
    border-radius: 10px;
    margin-bottom: 10px;
    border-left: 3px solid var(--primary);
}

.assistant-tip {
    padding: 12px;
    background: rgba(255, 170, 0, 0.1);
    border-radius: 10px;
    margin-bottom: 10px;
    border-left: 3px solid #ffaa00;
}

.assistant-warning {
    padding: 12px;
    background: rgba(255, 0, 102, 0.1);
    border-radius: 10px;
    margin-bottom: 10px;
    border-left: 3px solid #ff0066;
}

/* تحسينات للجداول */
.stDataFrame {
    background: rgba(10, 20, 40, 0.7) !important;
    border-radius: 10px !important;
    border: 1px solid rgba(0, 240, 255, 0.3) !important;
}

/* تأثيرات خاصة */
.holographic {
    position: relative;
    overflow: hidden;
}

.holographic::after {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: linear-gradient(
        to bottom right,
        rgba(0, 240, 255, 0) 0%,
        rgba(0, 240, 255, 0) 30%,
        rgba(0, 240, 255, 0.1) 45%,
        rgba(0, 240, 255, 0) 60%,
        rgba(0, 240, 255, 0) 100%
    );
    transform: rotate(30deg);
    animation: holographic-effect 6s linear infinite;
    pointer-events: none;
}

/* تأثيرات النص */
.text-gradient {
    background: linear-gradient(90deg, var(--primary), var(--accent));
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
}

/* تحسينات للتفاعل */
.tooltip {
    position: relative;
    display: inline-block;
}

.tooltip .tooltiptext {
    visibility: hidden;
    width: 200px;
    background-color: rgba(10, 20, 40, 0.9);
    color: var(--text);
    text-align: center;
    border-radius: 6px;
    padding: 10px;
    position: absolute;
    z-index: 1;
    bottom: 125%;
    left: 50%;
    margin-left: -100px;
    opacity: 0;
    transition: opacity 0.3s;
    border: 1px solid rgba(0, 240, 255, 0.3);
    box-shadow: 0 0 15px rgba(0, 240, 255, 0.3);
}

.tooltip:hover .tooltiptext {
    visibility: visible;
    opacity: 1;
}

/* أرقام الصفقات باللون الأبيض */
.trade-numbers {
    color: white !important;
    font-weight: bold;
}

/* التعديلات المطلوبة لجعل النصوص والأرقام باللون الأبيض */
.stMetricLabel, .stMetricValue, .stMetricDelta {
    color: white !important;
}

.stMetricLabel {
    font-size: 1.1em !important;
    font-weight: bold !important;
}

.stMetricValue {
    font-size: 1.4em !important;
    font-weight: bold !important;
}

.stMetricDelta {
    font-size: 1em !important;
}
</style>

<!-- تأثيرات الخلفية الفضائية -->
<div class="stars" id="stars"></div>
<div class="particles" id="particles"></div>
<div class="screen-effect"></div>
<div class="grid-overlay"></div>
<div class="scanlines"></div>
<div class="data-stream"></div>
<div class="pulse-effect"></div>

<script>
// إنشاء النجوم
const starsContainer = document.getElementById('stars');
for (let i = 0; i < 200; i++) {
    const star = document.createElement('div');
    star.className = 'star';
    star.style.width = `${Math.random() * 3}px`;
    star.style.height = star.style.width;
    star.style.left = `${Math.random() * 100}%`;
    star.style.top = `${Math.random() * 100}%`;
    star.style.setProperty('--duration', `${5 + Math.random() * 10}s`);
    starsContainer.appendChild(star);
}

// إنشاء الجسيمات
const particlesContainer = document.getElementById('particles');
for (let i = 0; i < 50; i++) {
    const particle = document.createElement('div');
    particle.className = 'particle';
    particle.style.width = `${2 + Math.random() * 5}px`;
    particle.style.height = particle.style.width;
    particle.style.left = `${Math.random() * 100}%`;
    particle.style.top = `${Math.random() * 100}%`;
    particle.style.setProperty('--duration', `${10 + Math.random() * 20}s`);
    particle.style.setProperty('--tx', `${-50 + Math.random() * 100}px`);
    particle.style.setProperty('--ty', `${-50 + Math.random() * 100}px`);
    particlesContainer.appendChild(particle);
}
</script>
""", unsafe_allow_html=True)

class MarketSimulator:
    def __init__(self, spread=0.001, commission=0.0005):
        self.spread = spread
        self.commission = commission
        self.balance = 10000  # الرصيد الافتراضي
        self.initial_balance = 10000
        self.positions = []
        
    def execute_order(self, price, action, quantity=None, risk_per_trade=0.02, stop_loss_distance=None):
        # حساب السعر بعد السبريد
        executed_price = price * (1 + self.spread) if action == "BUY" else price * (1 - self.spread)
        
        # حساب حجم المركز بناءً على إدارة المخاطر
        if quantity is None and stop_loss_distance is not None:
            risk_amount = self.balance * risk_per_trade
            quantity = risk_amount / stop_loss_distance
        
        # تطبيق العمولة
        executed_price = executed_price * (1 - self.commission)
        
        return executed_price, quantity
    
    def update_balance(self, profit):
        self.balance += profit
        return self.balance

class CryptoPredictor2100:
    def __init__(self):
        self.exchange = ccxt.binance({
            'rateLimit': 3000,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot'
            }
        })
        self.scalers = {}
        self.models = {}
        self.market_simulator = MarketSimulator()
        self.last_api_call = 0
        self.current_signal = None
        self.first_visit = True
        self.analysis_complete = False

    def get_symbol_hash(self, symbol):
        return hashlib.md5(symbol.encode()).hexdigest()

    def fetch_data(self, symbol, days=30, timeframe='1h'):
        # تحديد معدل الاستعلام للواجهة البرمجية
        current_time = time.time()
        if current_time - self.last_api_call < 60:  # 60 ثانية بين الطلبات
            time.sleep(60 - (current_time - self.last_api_call))
        
        try:
            since = self.exchange.parse8601((datetime.now() - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ'))
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            self.last_api_call = time.time()
            return df
        except Exception as e:
            st.error(f"خطأ في جلب البيانات لـ {symbol}: {str(e)}")
            self.last_api_call = time.time()
            return None

    def calculate_indicators(self, df):
        if df.empty:
            return df
            
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        volume = df['volume'].values
        
        # المؤشرات الفنية
        df['RSI'] = talib.RSI(close, timeperiod=14)
        df['MACD'], df['MACD_signal'], df['MACD_hist'] = talib.MACD(close)
        df['BB_upper'], df['BB_middle'], df['BB_lower'] = talib.BBANDS(close)
        df['ATR'] = talib.ATR(high, low, close, timeperiod=14)
        df['SMA_20'] = talib.SMA(close, timeperiod=20)
        df['SMA_50'] = talib.SMA(close, timeperiod=50)
        df['EMA_100'] = talib.EMA(close, timeperiod=100)
        
        # متوسط السعر المرجح بحجم التداول
        df['VWAP'] = (df['volume'] * (df['high'] + df['low'] + df['close']) / 3).cumsum() / df['volume'].cumsum()
        
        # مؤشر RSI للحجم
        df['VRSI'] = talib.RSI(df['volume'], timeperiod=14)
        
        # مناطق الحجم الكبير
        df['volume_ma'] = talib.SMA(volume, timeperiod=20)
        df['high_volume'] = df['volume'] > df['volume_ma'] * 1.5
        
        # مؤشر RSI المرجح
        df['WRSI'] = talib.RSI(df['close'] * df['volume'], timeperiod=14)
        
        # مؤشر ADX
        df['ADX'] = talib.ADX(high, low, close, timeperiod=14)
        
        # المؤشر العشوائي
        df['slowk'], df['slowd'] = talib.STOCH(high, low, close)
        
        return df.dropna()

    def assess_volatility(self, df):
        """تقييم مستوى التقلب في السوق"""
        volatility = {
            'level': 'low',
            'score': 0,
            'indicators': {}
        }
        
        if df.empty:
            return volatility
            
        # 1. تقييم ATR
        atr = df['ATR'].iloc[-1]
        atr_avg = df['ATR'].mean()
        atr_ratio = atr / atr_avg
        volatility['indicators']['ATR'] = {
            'value': atr,
            'ratio': atr_ratio,
            'assessment': 'high' if atr_ratio > 1.5 else 'medium' if atr_ratio > 1.2 else 'low'
        }
        
        # 2. عرض باند بولينجر
        bb_width = (df['BB_upper'].iloc[-1] - df['BB_lower'].iloc[-1]) / df['BB_middle'].iloc[-1]
        bb_width_avg = ((df['BB_upper'] - df['BB_lower']) / df['BB_middle']).mean()
        bb_width_ratio = bb_width / bb_width_avg
        volatility['indicators']['BB_Width'] = {
            'value': bb_width,
            'ratio': bb_width_ratio,
            'assessment': 'high' if bb_width_ratio > 1.5 else 'medium' if bb_width_ratio > 1.2 else 'low'
        }
        
        # 3. تغير السعر في آخر 4 ساعات
        price_change = abs(df['close'].iloc[-1] - df['close'].iloc[-4]) / df['close'].iloc[-4] * 100
        volatility['indicators']['Price_Change_4h'] = {
            'value': price_change,
            'assessment': 'high' if price_change > 3 else 'medium' if price_change > 1.5 else 'low'
        }
        
        # 4. حجم تداول غير طبيعي
        volume_ratio = df['volume'].iloc[-1] / df['volume_ma'].iloc[-1]
        volatility['indicators']['Volume_Spike'] = {
            'value': volume_ratio,
            'assessment': 'high' if volume_ratio > 2 else 'medium' if volume_ratio > 1.5 else 'low'
        }
        
        # حساب النتيجة الكلية
        high_count = sum(1 for ind in volatility['indicators'].values() if ind['assessment'] == 'high')
        med_count = sum(1 for ind in volatility['indicators'].values() if ind['assessment'] == 'medium')
        
        volatility_score = high_count * 2 + med_count * 1
        volatility['score'] = volatility_score
        
        if volatility_score >= 4:
            volatility['level'] = 'extreme'
        elif volatility_score >= 3:
            volatility['level'] = 'high'
        elif volatility_score >= 2:
            volatility['level'] = 'medium'
        else:
            volatility['level'] = 'low'
        
        return volatility

    def find_support_resistance(self, df, window=24):
        if len(df) < window * 2:
            return [], []
            
        # إيجاد القمم والقيعان المحلية
        high_idx = argrelextrema(df['high'].values, np.greater, order=window)[0]
        low_idx = argrelextrema(df['low'].values, np.less, order=window)[0]
        
        # تجميع المستويات القريبة باستخدام DBSCAN
        def cluster_levels(levels, threshold=0.005):
            if len(levels) == 0:
                return []
            
            levels_2d = np.array(levels).reshape(-1, 1)
            eps = np.mean(levels) * threshold
            db = DBSCAN(eps=eps, min_samples=2).fit(levels_2d)
            labels = db.labels_
            
            clusters = {}
            for i, level in enumerate(levels):
                label = labels[i]
                if label not in clusters:
                    clusters[label] = []
                clusters[label].append(level)
            
            clustered_levels = []
            for label, group in clusters.items():
                if label != -1:
                    clustered_levels.append(np.mean(group))
            
            return clustered_levels
        
        support_levels = df.iloc[low_idx]['low'].values
        resistance_levels = df.iloc[high_idx]['high'].values
        
        support_clusters = cluster_levels(support_levels)
        resistance_clusters = cluster_levels(resistance_levels)
        
        # تقييم قوة المستويات
        def score_levels(levels, df, is_support=True):
            scored = []
            for level in levels:
                if is_support:
                    touches = len(df[(df['low'] <= level * 1.005) & (df['low'] >= level * 0.995)])
                    volume_at_level = df[(df['low'] <= level * 1.005) & (df['low'] >= level * 0.995)]['volume'].mean()
                else:
                    touches = len(df[(df['high'] >= level * 0.995) & (df['high'] <= level * 1.005)])
                    volume_at_level = df[(df['high'] >= level * 0.995) & (df['high'] <= level * 1.005)]['volume'].mean()
                
                score = touches * 0.6 + (volume_at_level / df['volume'].mean()) * 0.4
                scored.append((level, score, touches))
            
            scored.sort(key=lambda x: x[1], reverse=True)
            return [x[:2] for x in scored[:3]]  # level, strength
        
        support = score_levels(support_clusters, df, is_support=True)
        resistance = score_levels(resistance_clusters, df, is_support=False)
        
        return support, resistance

    def find_liquidity_zones(self, df):
        if df.empty or len(df[df['high_volume']]) < 10:
            return []
            
        high_volume_df = df[df['high_volume']]
        liquidity_zones = []
        
        from sklearn.cluster import KMeans
        X = high_volume_df[['close', 'volume']].values
        kmeans = KMeans(n_clusters=3, random_state=42).fit(X)
        high_volume_df['cluster'] = kmeans.labels_
        
        for cluster in range(3):
            cluster_data = high_volume_df[high_volume_df['cluster'] == cluster]
            if len(cluster_data) > 0:
                min_price = cluster_data['close'].min()
                max_price = cluster_data['close'].max()
                total_volume = cluster_data['volume'].sum()
                liquidity_zones.append({
                    'range': (min_price, max_price),
                    'volume': total_volume,
                    'volume_pct': total_volume / high_volume_df['volume'].sum() * 100
                })
        
        liquidity_zones.sort(key=lambda x: x['volume'], reverse=True)
        zones = [x['range'] for x in liquidity_zones[:3]]
        
        return zones

    def prepare_data(self, df):
        if df.empty or len(df) < 24:
            return np.array([]), np.array([]), None
            
        scaler = MinMaxScaler()
        scaled_data = scaler.fit_transform(df[['close']])
        
        X, y = [], []
        look_back = 24
        
        for i in range(look_back, len(scaled_data)):
            X.append(scaled_data[i-look_back:i, 0])
            y.append(scaled_data[i, 0])
            
        return np.array(X), np.array(y), scaler

    def train_model(self, symbol, df):
        try:
            X, y, scaler = self.prepare_data(df)
            
            if len(X) == 0 or len(y) == 0:
                st.warning("لا توجد بيانات كافية لتدريب النموذج")
                return None, None
                
            X = X.reshape(X.shape[0], X.shape[1], 1)
            
            model = Sequential([
                LSTM(128, return_sequences=True, input_shape=(X.shape[1], 1)),
                Dropout(0.3),
                LSTM(64, return_sequences=True),
                Dropout(0.2),
                LSTM(32),
                Dropout(0.1),
                Dense(1)
            ])
            
            model.compile(optimizer='adam', loss='mse')
            model.fit(X, y, epochs=50, batch_size=32, verbose=0)
            
            symbol_hash = self.get_symbol_hash(symbol)
            model.save(f'models/{symbol_hash}_model.h5')
            joblib.dump(scaler, f'models/{symbol_hash}_scaler.pkl')
            
            return model, scaler
        except Exception as e:
            st.error(f"خطأ في تدريب النموذج: {str(e)}")
            return None, None

    def load_model(self, symbol):
        symbol_hash = self.get_symbol_hash(symbol)
        model_path = f'models/{symbol_hash}_model.h5'
        scaler_path = f'models/{symbol_hash}_scaler.pkl'
        
        if os.path.exists(model_path) and os.path.exists(scaler_path):
            try:
                model = load_model(model_path)
                scaler = joblib.load(scaler_path)
                return model, scaler
            except:
                return None, None
        return None, None

    def predict(self, symbol, df):
        model, scaler = self.load_model(symbol)
        
        if model is None or scaler is None:
            model, scaler = self.train_model(symbol, df)
            if model is None:
                return None
                
        X, _, _ = self.prepare_data(df)
        if len(X) == 0:
            return None
            
        X = X[-1].reshape(1, X.shape[1], 1)
        prediction = model.predict(X, verbose=0)[0][0]
        return scaler.inverse_transform([[prediction]])[0][0]

    def calculate_trade_accuracy(self, df, current_price, predicted_price, support, resistance):
        accuracy = 50  # الأساس 50%
        
        if df.empty:
            return accuracy
            
        # عوامل الدقة
        rsi = df['RSI'].iloc[-1]
        macd_hist = df['MACD_hist'].iloc[-1]
        price_position = (current_price - df['BB_lower'].iloc[-1]) / (df['BB_upper'].iloc[-1] - df['BB_lower'].iloc[-1])
        adx = df['ADX'].iloc[-1]
        w_rsi = df['WRSI'].iloc[-1]
        vwap_position = (current_price - df['VWAP'].iloc[-1]) / df['VWAP'].iloc[-1] * 100
        
        if predicted_price > current_price:  # إشارة شراء
            if rsi < 60:
                accuracy += 8 * (1 - rsi/60)
            if macd_hist > 0:
                accuracy += 5 * (macd_hist / df['close'].iloc[-1] * 100)
            if price_position < 0.5:
                accuracy += 5 * (1 - price_position)
            if adx > 25:
                accuracy += 5 * (adx / 50)
            if w_rsi < 60:
                accuracy += 5 * (1 - w_rsi/60)
            if vwap_position > -1:
                accuracy += 5
                
            if support:
                for s, strength in support:
                    distance_pct = abs(current_price - s) / current_price * 100
                    if distance_pct < 1:
                        accuracy += 10 * strength * (1 - distance_pct/1)
                        break
        else:  # إشارة بيع
            if rsi > 40:
                accuracy += 8 * (rsi/70)
            if macd_hist < 0:
                accuracy += 5 * abs(macd_hist / df['close'].iloc[-1] * 100)
            if price_position > 0.5:
                accuracy += 5 * price_position
            if adx > 25:
                accuracy += 5 * (adx / 50)
            if w_rsi > 40:
                accuracy += 5 * (w_rsi/70)
            if vwap_position < 1:
                accuracy += 5
                
            if resistance:
                for r, strength in resistance:
                    distance_pct = abs(current_price - r) / current_price * 100
                    if distance_pct < 1:
                        accuracy += 10 * strength * (1 - distance_pct/1)
                        break
        
        if df['high_volume'].iloc[-1]:
            accuracy += 5 * (df['volume'].iloc[-1] / df['volume_ma'].iloc[-1])
            
        trend_strength = 0
        if len(df) > 50:
            slope, _, _, _, _ = linregress(range(50), df['close'].iloc[-50:])
            if (slope > 0 and predicted_price > current_price) or (slope < 0 and predicted_price < current_price):
                trend_strength = min(abs(slope / df['close'].iloc[-1] * 1000), 10)
                accuracy += trend_strength
            
        return min(95, max(55, accuracy))

    def generate_trade_signal(self, df, predicted_price, support, resistance, liquidity_zones):
        if predicted_price is None or df.empty:
            return None
            
        current_price = df['close'].iloc[-1]
        atr = df['ATR'].iloc[-1]
        rsi = df['RSI'].iloc[-1]
        vwap = df['VWAP'].iloc[-1]
        adx = df['ADX'].iloc[-1]
        
        # تقييم التقلب
        volatility = self.assess_volatility(df)
        
        accuracy = self.calculate_trade_accuracy(df, current_price, predicted_price, support, resistance)
        
        # تقليل الدقة إذا كان التقلب عاليًا
        if volatility['level'] in ['high', 'extreme']:
            accuracy = max(55, accuracy * 0.7)  # تقليل الدقة بنسبة 30%
        
        # تعريف المتغيرات مسبقًا لتجنب الأخطاء
        closest_support = None
        closest_resistance = None
        
        # تحسين نقاط الدخول والخروج
        if predicted_price > current_price * 1.015 and rsi < 65:
            # تحسين إشارة الشراء
            entry = current_price * 1.005  # نقطة الدخول الأساسية
            
            # ضبط الدخول بناءً على أقرب دعم
            if support:
                support_below = [s for s, _ in support if s < current_price]
                if support_below:
                    closest_support = max(support_below)
                    entry = max(entry, closest_support * 1.005)  # الدخول أعلى بقليل من الدعم
            
            # حساب وقف الخسارة الآمن بنسبة 3-4% حسب التقلبات
            max_loss_pct = 3.0 + (1.0 if volatility['level'] in ['high', 'extreme'] else 0)  # 3% للأسواق العادية، 4% للأسواق المتقلبة
            
            # حساب وقف الخسارة الأساسي
            stop_loss = current_price * (1 - max_loss_pct/100)
            
            # ضبط وقف الخسارة بناءً على الدعم والمتوسط المتحرك
            if support:
                support_below = [s for s, _ in support if s < current_price]
                if support_below:
                    stop_loss = max(max(support_below) * 0.99, stop_loss)  # زيادة هامش الأمان إلى 1% تحت الدعم
            
            # استخدام ATR لوقف الخسارة إذا كان أفضل
            atr_stop = current_price - (atr * 2.5)  # زيادة مضاعف ATR إلى 2.5
            stop_loss = max(stop_loss, atr_stop)
            
            # حساب جني الأرباح بنسبة 5-6% حسب التقلبات
            min_take_profit = entry * (1 + (5.0 + (1.0 if volatility['level'] in ['high', 'extreme'] else 0))/100)  # 5% للأسواق العادية، 6% للأسواق المتقلبة
            
            # ضبط جني الأرباح بناءً على المقاومة
            take_profit = min_take_profit
            if resistance:
                resistance_above = [r for r, _ in resistance if r > current_price]
                if resistance_above:
                    closest_resistance = min(resistance_above)
                    take_profit = min(closest_resistance * 0.99, take_profit)  # زيادة هامش الأمان إلى 1% تحت المقاومة
            
            # الضبط بناءً على مناطق السيولة
            if liquidity_zones:
                for zone in liquidity_zones:
                    if zone[0] < take_profit < zone[1]:
                        take_profit = zone[0] * 0.99  # زيادة هامش الأمان
            
            # التأكد من أن جني الأرباح أعلى من نقطة الدخول
            if take_profit <= entry:
                take_profit = entry * 1.06  # زيادة بنسبة 6% كحد أدنى
            
            # حساب نسبة المخاطرة/العائد
            risk_reward = round((take_profit - entry) / (entry - stop_loss), 2)
            
            # حساب ثقة الصفقة
            confidence = accuracy
            if closest_support:
                distance_pct = abs(current_price - closest_support) / current_price * 100
                confidence = min(95, confidence + 10 * (1 - distance_pct/2))
            if current_price > vwap:
                confidence = min(95, confidence + 5)
            if adx > 25:
                confidence = min(95, confidence + 5 * (adx / 50))
            
            signal = {
                'action': 'BUY',
                'entry': round(entry, 4),
                'stop_loss': round(stop_loss, 4),
                'take_profit': round(take_profit, 4),
                'confidence': round(confidence, 1),
                'risk_reward': risk_reward,
                'accuracy': round(accuracy, 1),
                'trend_strength': round(adx, 1),
                'strategy': 'اختراق مع دعم' if closest_support and abs(current_price - closest_support) < current_price * 0.01 else 'متابعة الاتجاه',
                'current_price': round(current_price, 4),
                'predicted_price': round(predicted_price, 4),
                'volatility': volatility,
                'timestamp': df['timestamp'].iloc[-1]
            }
            
            if volatility['level'] == 'extreme':
                signal['risk_note'] = "تحذير شديد: السوق شديد التقلب - تجنب المراكز الكبيرة"
            elif volatility['level'] == 'high':
                signal['risk_note'] = "تحذير: السوق متقلب - قلل من حجم المركز"
            else:
                signal['risk_note'] = "التقلب ضمن النطاق الطبيعي"
            
            return signal
            
        elif predicted_price < current_price * 0.985 and rsi > 35:
            # تحسين إشارة البيع
            entry = current_price * 0.995  # نقطة الدخول الأساسية
            
            # ضبط الدخول بناءً على أقرب مقاومة
            if resistance:
                resistance_above = [r for r, _ in resistance if r > current_price]
                if resistance_above:
                    closest_resistance = min(resistance_above)
                    entry = min(entry, closest_resistance * 0.995)  # الدخول أقل بقليل من المقاومة
            
            # حساب وقف الخسارة الآمن بنسبة 3-4% حسب التقلبات
            max_loss_pct = 3.0 + (1.0 if volatility['level'] in ['high', 'extreme'] else 0)  # 3% للأسواق العادية، 4% للأسواق المتقلبة
            
            # حساب وقف الخسارة الأساسي
            stop_loss = current_price * (1 + max_loss_pct/100)
            
            # ضبط وقف الخسارة بناءً على المقاومة والمتوسط المتحرك
            if resistance:
                resistance_above = [r for r, _ in resistance if r > current_price]
                if resistance_above:
                    stop_loss = min(min(resistance_above) * 1.01, stop_loss)  # زيادة هامش الأمان إلى 1% فوق المقاومة
            
            # استخدام ATR لوقف الخسارة إذا كان أفضل
            atr_stop = current_price + (atr * 2.5)  # زيادة مضاعف ATR إلى 2.5
            stop_loss = min(stop_loss, atr_stop)
            
            # حساب جني الأرباح بنسبة 5-6% حسب التقلبات
            min_take_profit = entry * (1 - (5.0 + (1.0 if volatility['level'] in ['high', 'extreme'] else 0))/100)  # 5% للأسواق العادية، 6% للأسواق المتقلبة
            
            # ضبط جني الأرباح بناءً على الدعم
            take_profit = min_take_profit
            if support:
                support_below = [s for s, _ in support if s < current_price]
                if support_below:
                    closest_support = max(support_below)
                    take_profit = max(closest_support * 1.01, take_profit)  # زيادة هامش الأمان إلى 1% فوق الدعم
            
            # الضبط بناءً على مناطق السيولة
            if liquidity_zones:
                for zone in liquidity_zones:
                    if zone[0] < take_profit < zone[1]:
                        take_profit = zone[1] * 1.01  # زيادة هامش الأمان
            
            # التأكد من أن جني الأرباح أقل من نقطة الدخول
            if take_profit >= entry:
                take_profit = entry * 0.94  # انخفاض بنسبة 6% كحد أدنى
            
            # حساب نسبة المخاطرة/العائد
            risk_reward = round((entry - take_profit) / (stop_loss - entry), 2)
            
            # حساب ثقة الصفقة
            confidence = accuracy
            if closest_resistance:
                distance_pct = abs(current_price - closest_resistance) / current_price * 100
                confidence = min(95, confidence + 10 * (1 - distance_pct/2))
            if current_price < vwap:
                confidence = min(95, confidence + 5)
            if adx > 25:
                confidence = min(95, confidence + 5 * (adx / 50))
            
            signal = {
                'action': 'SELL',
                'entry': round(entry, 4),
                'stop_loss': round(stop_loss, 4),
                'take_profit': round(take_profit, 4),
                'confidence': round(confidence, 1),
                'risk_reward': risk_reward,
                'accuracy': round(accuracy, 1),
                'trend_strength': round(adx, 1),
                'strategy': 'اختراق مع مقاومة' if closest_resistance and abs(current_price - closest_resistance) < current_price * 0.01 else 'متابعة الاتجاه',
                'current_price': round(current_price, 4),
                'predicted_price': round(predicted_price, 4),
                'volatility': volatility,
                'timestamp': df['timestamp'].iloc[-1]
            }
            
            if volatility['level'] == 'extreme':
                signal['risk_note'] = "تحذير شديد: السوق شديد التقلب - تجنب المراكز الكبيرة"
            elif volatility['level'] == 'high':
                signal['risk_note'] = "تحذير: السوق متقلب - قلل من حجم المركز"
            else:
                signal['risk_note'] = "التقلب ضمن النطاق الطبيعي"
            
            return signal
        
        return None

    def create_main_chart(self, df, support, resistance, liquidity_zones, predicted_price, symbol):
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                          vertical_spacing=0.05, 
                          row_heights=[0.7, 0.3])
        
        # الشموع اليابانية
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
        
        # المتوسطات المتحركة
        fig.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['SMA_20'],
            name='SMA 20',
            line=dict(color='#ffaa00', width=1.5)
        ), row=1, col=1)
        
        fig.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['SMA_50'],
            name='SMA 50',
            line=dict(color='#0090ff', width=1.5)
        ), row=1, col=1)
        
        fig.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['EMA_100'],
            name='EMA 100',
            line=dict(color='#aa00ff', width=1.5)
        ), row=1, col=1)
        
        # VWAP
        fig.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['VWAP'],
            name='VWAP',
            line=dict(color='#00f0ff', width=1.5, dash='dot')
        ), row=1, col=1)
        
        # الدعم والمقاومة
        for level, strength in support:
            fig.add_shape(type='line',
                        x0=df['timestamp'].iloc[0], y0=level,
                        x1=df['timestamp'].iloc[-1], y1=level,
                        line=dict(color='#00ff88', width=2, dash='dash'),
                        name=f'دعم {level:.2f}',
                        row=1, col=1)
        
        for level, strength in resistance:
            fig.add_shape(type='line',
                        x0=df['timestamp'].iloc[0], y0=level,
                        x1=df['timestamp'].iloc[-1], y1=level,
                        line=dict(color='#ff0066', width=2, dash='dash'),
                        name=f'مقاومة {level:.2f}',
                        row=1, col=1)
        
        # مناطق السيولة
        for zone in liquidity_zones:
            fig.add_shape(type='rect',
                        x0=df['timestamp'].iloc[0], y0=zone[0],
                        x1=df['timestamp'].iloc[-1], y1=zone[1],
                        fillcolor='#0090ff', opacity=0.15, line_width=0,
                        name=f'منطقة سيولة {zone[0]:.2f}-{zone[1]:.2f}',
                        row=1, col=1)
        
        # التنبؤ
        if predicted_price:
            fig.add_trace(go.Scatter(
                x=[df['timestamp'].iloc[-1], df['timestamp'].iloc[-1] + timedelta(hours=4)],
                y=[df['close'].iloc[-1], predicted_price],
                name='التنبؤ',
                line=dict(color='#00f0ff', width=3, dash='dot'),
                marker=dict(size=12, color='#00f0ff')
            ), row=1, col=1)
        
        # الحجم
        fig.add_trace(go.Bar(
            x=df['timestamp'],
            y=df['volume'],
            name='الحجم',
            marker_color='#7f8c8d',
            opacity=0.7
        ), row=2, col=1)
        
        # المتوسط المتحرك للحجم
        fig.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['volume_ma'],
            name='متوسط الحجم',
            line=dict(color='#ff0066', width=1.5)
        ), row=2, col=1)
        
        # التنسيق
        fig.update_layout(
            title=f"تحليل متقدم لـ {symbol}",
            height=800,
            showlegend=True,
            hovermode="x unified",
            plot_bgcolor='rgba(10, 10, 30, 0.5)',
            paper_bgcolor='rgba(10, 10, 30, 0.5)',
            margin=dict(l=20, r=20, t=60, b=20),
            font=dict(color='#e0f0ff'),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                font=dict(color='#e0f0ff')
            )
        )
        
        fig.update_xaxes(
            rangeslider_visible=False,
            row=1, col=1,
            gridcolor='rgba(0, 240, 255, 0.1)',
            zerolinecolor='rgba(0, 240, 255, 0.1)'
        )
        
        fig.update_yaxes(
            title_text="السعر (USDT)", 
            row=1, 
            col=1,
            gridcolor='rgba(0, 240, 255, 0.1)',
            zerolinecolor='rgba(0, 240, 255, 0.1)'
        )
        
        fig.update_yaxes(
            title_text="الحجم", 
            row=2, 
            col=1,
            gridcolor='rgba(0, 240, 255, 0.1)',
            zerolinecolor='rgba(0, 240, 255, 0.1)'
        )
        
        return fig

    def generate_auto_analysis(self, symbol, df, signal, support, resistance, liquidity_zones):
        """إنشاء تحليل تلقائي مفصل للعملة المشفرة"""
        if df.empty:
            return "لا توجد بيانات كافية لإنشاء تحليل مفصل"
            
        current_price = df['close'].iloc[-1]
        rsi = df['RSI'].iloc[-1]
        macd_hist = df['MACD_hist'].iloc[-1]
        adx = df['ADX'].iloc[-1]
        vwap = df['VWAP'].iloc[-1]
        volatility = self.assess_volatility(df)
        
        analysis = []
        advice = []
        warnings = []
        
        # التحليل العام
        analysis.append(f"### 📊 تحليل متقدم لـ {symbol}")
        analysis.append(f"**السعر الحالي:** {current_price:.4f} USDT")
        
        if signal:
            action = "شراء" if signal['action'] == 'BUY' else "بيع"
            analysis.append(f"**الإشارة الحالية:** {action} بثقة {signal['confidence']:.0f}%")
        else:
            analysis.append("**الإشارة الحالية:** لا توجد إشارة تداول قوية في هذا الوقت")
        
        analysis.append(f"**مؤشر RSI:** {rsi:.2f} - {'مشترى زائد' if rsi < 30 else 'منطقة شراء' if rsi < 50 else 'محايد' if rsi < 70 else 'منطقة بيع'}")
        analysis.append(f"**ADX (قوة الاتجاه):** {adx:.2f} - {'ضعيف' if adx < 25 else 'متوسط' if adx < 50 else 'قوي'}")
        analysis.append(f"**الموقع بالنسبة لـ VWAP:** {'أعلى' if current_price > vwap else 'أقل'} من متوسط السعر المرجح بالحجم")
        
        # تحليل التقلب
        volatility_text = {
            'extreme': 'شديد',
            'high': 'عالي',
            'medium': 'متوسط',
            'low': 'منخفض'
        }.get(volatility['level'], 'منخفض')
        
        analysis.append(f"**مستوى التقلب:** {volatility_text}")
        
        # تحليل الدعم والمقاومة
        if support:
            closest_support = min([(abs(current_price - s[0]), s[0], s[1]) for s in support], key=lambda x: x[0])
            analysis.append(f"**أقرب دعم:** {closest_support[1]:.4f} (القوة: {'قوي' if closest_support[2] > 0.7 else 'متوسط' if closest_support[2] > 0.4 else 'ضعيف'})")
        else:
            analysis.append("**الدعم:** لا توجد مستويات دعم واضحة")
            
        if resistance:
            closest_resistance = min([(abs(current_price - r[0]), r[0], r[1]) for r in resistance], key=lambda x: x[0])
            analysis.append(f"**أقرب مقاومة:** {closest_resistance[1]:.4f} (القوة: {'قوي' if closest_resistance[2] > 0.7 else 'متوسط' if closest_resistance[2] > 0.4 else 'ضعيف'})")
        else:
            analysis.append("**المقاومة:** لا توجد مستويات مقاومة واضحة")
        
        # تحليل مناطق السيولة
        if liquidity_zones:
            analysis.append("**مناطق السيولة:**")
            for zone in liquidity_zones:
                analysis.append(f"- {zone[0]:.4f} إلى {zone[1]:.4f}")
        else:
            analysis.append("**مناطق السيولة:** لا توجد مناطق سيولة واضحة")
        
        # نصائح التداول بناءً على التحليل
        if signal:
            advice.append("### 💡 توصيات التداول")
            
            if signal['action'] == 'BUY':
                advice.append(f"- **نقطة الدخول المثالية:** حوالي {signal['entry']:.4f}")
                advice.append(f"- **وقف الخسارة الآمن:** ضعه عند {signal['stop_loss']:.4f} (هامش أمان 1% تحت أقرب دعم)")
                advice.append(f"- **جني الأرباح:** الهدف الأول عند {signal['take_profit']:.4f}")
                
                if support:
                    advice.append("- فكر في الدخول التدريجي عند مستويات الدعم إذا كانت متاحة")
                
                if signal['confidence'] > 75:
                    advice.append("- هذه صفقة عالية الثقة، يمكنك تخصيص جزء أكبر من رأس المال")
                elif signal['confidence'] > 60:
                    advice.append("- هذه صفقة متوسطة الثقة، التزم بحجم مركزك المعتاد")
                else:
                    advice.append("- هذه صفقة منخفضة الثقة، استخدم حجم مركز أصغر من المعتاد")
                
                if current_price > vwap:
                    advice.append("- السعر فوق VWAP يدعم فرضية الشراء")
                
                if rsi < 50:
                    advice.append("- مؤشر RSI يشير إلى وجود مجال للحركة الصعودية")
            else:  # إشارة بيع
                advice.append(f"- **نقطة الدخول المثالية:** حوالي {signal['entry']:.4f}")
                advice.append(f"- **وقف الخسارة الآمن:** ضعه عند {signal['stop_loss']:.4f} (هامش أمان 1% فوق أقرب مقاومة)")
                advice.append(f"- **جني الأرباح:** الهدف الأول عند {signal['take_profit']:.4f}")
                
                if resistance:
                    advice.append("- فكر في الدخول التدريجي عند مستويات المقاومة إذا كانت متاحة")
                
                if signal['confidence'] > 75:
                    advice.append("- هذه صفقة عالية الثقة، يمكنك تخصيص جزء أكبر من رأس المال")
                elif signal['confidence'] > 60:
                    advice.append("- هذه صفقة متوسطة الثقة، التزم بحجم مركزك المعتاد")
                else:
                    advice.append("- هذه صفقة منخفضة الثقة، استخدم حجم مركز أصغر من المعتاد")
                
                if current_price < vwap:
                    advice.append("- السعر تحت VWAP يدعم فرضية البيع")
                
                if rsi > 50:
                    advice.append("- مؤشر RSI يشير إلى وجود مجال للحركة الهبوطية")
            
            advice.append(f"- **نسبة العائد/المخاطرة:** 1:{signal['risk_reward']:.2f} (ممتازة إذا كانت أعلى من 1:3)")
        
        # التحذيرات
        if volatility['level'] == 'extreme':
            warnings.append("### ⚠️ تحذيرات هامة")
            warnings.append("- التقلب الشديد في السوق يزيد من المخاطر")
            warnings.append("- تجنب المراكز الكبيرة في هذه الظروف")
            warnings.append("- اضبط أوامر وقف الخسارة بعناية لتجنب التنفيذ غير المرغوب فيه")
        elif volatility['level'] == 'high':
            warnings.append("### ⚠️ تحذيرات هامة")
            warnings.append("- السوق متقلب حاليًا، كن حذرًا في صفقاتك")
            warnings.append("- قلل من حجم مركزك المعتاد بنسبة 30-50%")
        
        if adx < 25 and signal:
            warnings.append("- قوة الاتجاه ضعيفة (ADX < 25)، مما يقلل من موثوقية الإشارة")
        
        if (signal and signal['action'] == 'BUY' and rsi > 60) or (signal and signal['action'] == 'SELL' and rsi < 40):
            warnings.append("- مؤشر RSI في منطقة انعكاس محتملة، كن حذرًا")
        
        # دمج التحليل
        full_analysis = "\n\n".join(analysis)
        if advice:
            full_analysis += "\n\n" + "\n\n".join(advice)
        if warnings:
            full_analysis += "\n\n" + "\n\n".join(warnings)
        
        return full_analysis

    def generate_ai_assistant_advice(self, signal, df):
        """إنشاء نصائح مساعد الذكاء الاصطناعي بناءً على إشارة التداول"""
        if not signal:
            return []
            
        advice = []
        current_price = df['close'].iloc[-1]
        rsi = df['RSI'].iloc[-1]
        adx = df['ADX'].iloc[-1]
        vwap = df['VWAP'].iloc[-1]
        
        if signal['action'] == 'BUY':
            # نصائح الشراء
            advice.append("### 🤖 نصائح مساعد الذكاء الاصطناعي")
            
            if signal['confidence'] > 75:
                advice.append("🟢 **صفقة عالية الثقة**: هذه فرصة تداول ممتازة مع احتمالية نجاح عالية.")
                advice.append("💡 يمكنك تخصيص ما يصل إلى 5% من رأس المال لهذه الصفقة.")
            elif signal['confidence'] > 60:
                advice.append("🟡 **صفقة متوسطة الثقة**: هذه فرصة تداول جيدة ولكنها تحتاج إلى مراقبة دقيقة.")
                advice.append("💡 التزم بحجم مركزك المعتاد (2-3% من رأس المال).")
            else:
                advice.append("🔴 **صفقة منخفضة الثقة**: هذه فرصة تداول محفوفة بالمخاطر وتحتاج إلى حذر شديد.")
                advice.append("💡 استخدم حجم مركز أصغر من المعتاد (1% أو أقل من رأس المال).")
            
            if current_price > vwap:
                advice.append("📈 **السعر فوق VWAP**: هذا يعزز فرضية الشراء حيث أن الزخم صاعد.")
            
            if rsi < 50:
                advice.append("📊 **RSI في منطقة الشراء**: هناك مجال للحركة الصعودية قبل الوصول إلى منطقة التشبع الشرائي.")
            
            if adx > 25:
                advice.append("🚀 **اتجاه قوي**: مؤشر ADX يشير إلى وجود اتجاه قوي مما يعزز موثوقية الإشارة.")
            
            advice.append(f"🎯 **استراتيجية الدخول**: {signal['strategy']}")
            
        else:  # إشارة بيع
            # نصائح البيع
            advice.append("### 🤖 نصائح مساعد الذكاء الاصطناعي")
            
            if signal['confidence'] > 75:
                advice.append("🟢 **صفقة عالية الثقة**: هذه فرصة تداول ممتازة مع احتمالية نجاح عالية.")
                advice.append("💡 يمكنك تخصيص ما يصل إلى 5% من رأس المال لهذه الصفقة.")
            elif signal['confidence'] > 60:
                advice.append("🟡 **صفقة متوسطة الثقة**: هذه فرصة تداول جيدة ولكنها تحتاج إلى مراقبة دقيقة.")
                advice.append("💡 التزم بحجم مركزك المعتاد (2-3% من رأس المال).")
            else:
                advice.append("🔴 **صفقة منخفضة الثقة**: هذه فرصة تداول محفوفة بالمخاطر وتحتاج إلى حذر شديد.")
                advice.append("💡 استخدم حجم مركز أصغر من المعتاد (1% أو أقل من رأس المال).")
            
            if current_price < vwap:
                advice.append("📉 **السعر تحت VWAP**: هذا يعزز فرضية البيع حيث أن الزخم هابط.")
            
            if rsi > 50:
                advice.append("📊 **RSI في منطقة البيع**: هناك مجال للحركة الهبوطية قبل الوصول إلى منطقة التشبع البيعي.")
            
            if adx > 25:
                advice.append("🚀 **اتجاه قوي**: مؤشر ADX يشير إلى وجود اتجاه قوي مما يعزز موثوقية الإشارة.")
            
            advice.append(f"🎯 **استراتيجية الدخول**: {signal['strategy']}")
        
        # إدارة المخاطر
        advice.append("### ⚠️ إدارة المخاطر")
        advice.append(f"🔒 **وقف الخسارة الآمن**: ضعه عند {signal['stop_loss']:.4f} (هامش أمان إضافي بنسبة 1%)")
        advice.append(f"🎯 **جني الأرباح**: الهدف الأول عند {signal['take_profit']:.4f}")
        advice.append(f"📊 **نسبة العائد/المخاطرة**: 1:{signal['risk_reward']:.2f} {'(ممتازة)' if signal['risk_reward'] >= 3 else '(جيدة)' if signal['risk_reward'] >= 2 else '(مقبولة)'}")
        
        # التقلب
        volatility = signal.get('volatility', {}).get('level', 'low')
        if volatility == 'extreme':
            advice.append("🌪️ **تقلب شديد**: قلل من حجم المركز بنسبة 50% على الأقل.")
        elif volatility == 'high':
            advice.append("🌊 **تقلب عالي**: قلل من حجم المركز بنسبة 30%.")
        
        return advice

def load_main_content(analyzer):
    """تحميل محتوى التطبيق الرئيسي"""
    # رأس فضائي متطور
    st.markdown("""
    <div class="ai-header neon-flicker">
        <h1 style="font-size: 3em; margin-bottom: 10px;">CRYPTOAI PRO+ 2100</h1>
        <p style="font-size: 1.2em; margin-bottom: 20px;">منصة تحليل العملات المشفرة بالذكاء الاصطناعي من المستقبل</p>
        <div style="display: flex; justify-content: center; gap: 15px; margin-top: 20px;">
            <span class="ai-chip">شبكات عصبية كمومية</span>
            <span class="ai-chip">تحليلات تنبؤية دقيقة</span>
            <span class="ai-chip">إشارات تداول ذكية</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # إدخال العملة
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        symbol = st.text_input("أدخل زوج العملة المشفرة (مثال BTC/USDT):", "BTC/USDT", key="symbol_input",
                             help="أدخل زوج التداول الذي تريد تحليله").upper()
    with col2:
        days = st.selectbox("الإطار الزمني:", [7, 14, 30, 60], index=2, key="days_select")
    with col3:
        st.write("")
        st.write("")
        analyze_btn = st.button("🚀 تحليل شامل", key="analyze_btn", 
                              help="انقر لبدء التحليل الفني المتقدم",
                              type="primary", use_container_width=True)
    
    if analyze_btn:
        with st.spinner("جاري تحليل العملة وتدريب نموذج الذكاء الاصطناعي..."):
            df = analyzer.fetch_data(symbol, days)
            
            if df is not None and len(df) > 50:
                df = analyzer.calculate_indicators(df)
                support, resistance = analyzer.find_support_resistance(df)
                liquidity_zones = analyzer.find_liquidity_zones(df)
                predicted_price = analyzer.predict(symbol, df)
                signal = analyzer.generate_trade_signal(df, predicted_price, support, resistance, liquidity_zones)
                analyzer.current_signal = signal
                analyzer.analysis_complete = True
                
                st.success("تم التحليل بنجاح!")
                
                tab1, tab2, tab3 = st.tabs([
                    "🚀 إشارة التداول", 
                    "📈 التحليل البياني", 
                    "🏦 المستويات الرئيسية"
                ])
                
                with tab1:
                    if signal:
                        st.subheader("🎯 إشارة تداول من الذكاء الاصطناعي")
                        
                        # عرض الإشارة بوضوح
                        action_text = "شراء" if signal['action'] == 'BUY' else "بيع"
                        action_class = "buy" if signal['action'] == 'BUY' else "sell"
                        
                        st.markdown(f"""
                        <div class="signal-box {action_class}">
                            <h2 style="margin:0;text-transform:uppercase;font-size:1.8em;">إشارة {action_text}</h2>
                            <p style="margin:5px 0;font-size:1.2em;">الأصل: {symbol}</p>
                            <p style="margin:5px 0;font-size:1.1em;">الإستراتيجية: {signal.get('strategy', 'N/A')}</p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # عرض ثقة الإشارة
                        confidence_class = "high" if signal['confidence'] > 75 else "medium" if signal['confidence'] > 60 else "low"
                        st.markdown(f"""
                        <div class="signal-confidence {confidence_class}">
                            {signal['confidence']:.0f}%
                            <div style="font-size:0.5em;margin-top:5px;">ثقة الإشارة</div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # عرض نقاط التداول
                        cols = st.columns(4)
                        cols[0].metric("السعر الحالي", f"{signal['current_price']:.4f}", 
                                     help="السعر الحالي للعملة", 
                                     label_visibility="visible")
                        cols[1].metric("السعر المتوقع", f"{signal['predicted_price']:.4f}", 
                                      f"{((signal['predicted_price'] - signal['current_price'])/signal['current_price']*100):.2f}%",
                                      delta_color="normal",
                                      help="التنبؤ بالسعر بعد 4 ساعات")
                        cols[2].metric("نقطة الدخول", f"{signal['entry']:.4f}", 
                                      help="السعر الموصى به لفتح المركز")
                        cols[3].metric("العائد/المخاطرة", f"1:{signal['risk_reward']:.2f}", 
                                      help="نسبة العائد المتوقع إلى المخاطرة")
                        
                        # تنسيق الأرقام باللون الأبيض
                        st.markdown("""
                        <style>
                            .stMetricLabel, .stMetricValue, .stMetricDelta {
                                color: white !important;
                            }
                            .stMetricLabel {
                                font-size: 1.1em !important;
                                font-weight: bold !important;
                            }
                            .stMetricValue {
                                font-size: 1.4em !important;
                                font-weight: bold !important;
                            }
                            .stMetricDelta {
                                font-size: 1em !important;
                            }
                        </style>
                        """, unsafe_allow_html=True)
                        
                        # عرض وقف الخسارة وجني الأرباح
                        cols = st.columns(2)
                        cols[0].metric("وقف الخسارة الآمن", f"{signal['stop_loss']:.4f}", 
                                      f"-{abs((signal['entry'] - signal['stop_loss'])/signal['entry']*100):.2f}%",
                                      delta_color="inverse",
                                      help="نقطة وقف الخسارة الموصى بها (3-4% حسب التقلبات)")
                        cols[1].metric("جني الأرباح", f"{signal['take_profit']:.4f}", 
                                      f"+{abs((signal['take_profit'] - signal['entry'])/signal['entry']*100):.2f}%",
                                      help="هدف جني الأرباح الموصى به (5-6% حسب التقلبات)")
                        
                        # عرض تحليل التقلب
                        volatility = signal.get('volatility', {})
                        volatility_level = volatility.get('level', 'low')
                        volatility_text = {
                            'extreme': 'شديد',
                            'high': 'عالي',
                            'medium': 'متوسط',
                            'low': 'منخفض'
                        }.get(volatility_level, 'منخفض')
                        
                        volatility_class = {
                            'extreme': 'risk-high',
                            'high': 'risk-medium',
                            'medium': 'risk-medium',
                            'low': 'risk-low'
                        }.get(volatility_level, 'risk-low')
                        
                        st.markdown("### 📊 تقييم تقلب السوق")
                        st.markdown(f"""
                        <div class="{volatility_class} risk-level">
                            {signal.get('risk_note', 'N/A')}
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # عرض مؤشرات التقلب
                        atr = volatility['indicators']['ATR']
                        bb_width = volatility['indicators']['BB_Width']
                        price_change = volatility['indicators']['Price_Change_4h']
                        volume_spike = volatility['indicators']['Volume_Spike']
                        
                        cols = st.columns(4)
                        cols[0].metric("ATR", f"{atr['value']:.4f}", 
                                      f"{'عالي' if atr['assessment'] == 'high' else 'متوسط' if atr['assessment'] == 'medium' else 'منخفض'}",
                                      help="متوسط المدى الحقيقي (مقياس التقلب)")
                        cols[1].metric("عرض بولينجر", f"{bb_width['value']:.4f}", 
                                      f"{'عالي' if bb_width['assessment'] == 'high' else 'متوسط' if bb_width['assessment'] == 'medium' else 'منخفض'}",
                                      help="عرض نطاق بولينجر (مقياس التقلب)")
                        cols[2].metric("تغير 4 ساعات", f"{price_change['value']:.2f}%", 
                                      f"{'عالي' if price_change['assessment'] == 'high' else 'متوسط' if price_change['assessment'] == 'medium' else 'منخفض'}",
                                      help="تغير السعر في آخر 4 ساعات")
                        cols[3].metric("ارتفاع الحجم", f"{volume_spike['value']:.2f}x", 
                                      f"{'عالي' if volume_spike['assessment'] == 'high' else 'متوسط' if volume_spike['assessment'] == 'medium' else 'منخفض'}",
                                      help="حجم التداول مقارنة بالمتوسط")
                        
                        # عرض نصائح مساعد الذكاء الاصطناعي
                        st.markdown("### 🤖 مساعد التداول الذكي")
                        ai_advice = analyzer.generate_ai_assistant_advice(signal, df)
                        
                        for advice in ai_advice:
                            if advice.startswith("###"):
                                st.markdown(advice, unsafe_allow_html=True)
                            else:
                                st.markdown(f"""
                                <div class="assistant-message">
                                    {advice}
                                </div>
                                """, unsafe_allow_html=True)
                        
                    else:
                        st.warning("⚠️ لا توجد إشارة تداول قوية في هذا الوقت")
                        st.info("""
                        <div class="ai-panel">
                            <h4 style="margin-top:0;">أسباب محتملة:</h4>
                            <ul style="margin:0;padding-left:20px;">
                                <li style="margin-bottom:8px;">السوق في نطاق جانبي (تداول في قناة ضيقة)</li>
                                <li style="margin-bottom:8px;">المؤشرات الفنية غير حاسمة</li>
                                <li style="margin-bottom:8px;">لا توجد مستويات دعم/مقاومة واضحة</li>
                                <li style="margin-bottom:8px;">تقلب عالي في السوق</li>
                                <li>ضعف قوة الاتجاه (ADX أقل من 25)</li>
                            </ul>
                        </div>
                        """, unsafe_allow_html=True)
                
                with tab2:
                    st.subheader("📈 التحليل البياني المتقدم")
                    fig = analyzer.create_main_chart(df, support, resistance, liquidity_zones, predicted_price, symbol)
                    st.plotly_chart(fig, use_container_width=True)
                
                with tab3:
                    st.subheader("🏦 مستويات الدعم والمقاومة الرئيسية")
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.markdown("### 🛡️ مستويات الدعم")
                        if support:
                            for level, strength in sorted(support, key=lambda x: x[0], reverse=True):
                                distance_pct = (df['close'].iloc[-1] - level) / level * 100
                                strength_class = "high-strength" if strength > 0.7 else "medium-strength" if strength > 0.4 else "low-strength"
                                strength_text = "قوي" if strength > 0.7 else "متوسط" if strength > 0.4 else "ضعيف"
                                
                                st.markdown(f"""
                                <div class="card support-level">
                                    <h4 style="margin-top:0;">{level:.4f}</h4>
                                    <p>المسافة من السعر الحالي: 
                                        <span class="{'price-change-negative' if distance_pct < 0 else 'price-change-positive'}">
                                            {abs(distance_pct):.2f}%
                                        </span>
                                    </p>
                                    <p>قوة المستوى: 
                                        <span class="level-strength {strength_class}">{strength_text}</span>
                                    </p>
                                </div>
                                """, unsafe_allow_html=True)
                        else:
                            st.warning("لا توجد مستويات دعم واضحة")
                    
                    with col2:
                        st.markdown("### 🚧 مستويات المقاومة")
                        if resistance:
                            for level, strength in sorted(resistance, key=lambda x: x[0]):
                                distance_pct = (level - df['close'].iloc[-1]) / df['close'].iloc[-1] * 100
                                strength_class = "high-strength" if strength > 0.7 else "medium-strength" if strength > 0.4 else "low-strength"
                                strength_text = "قوي" if strength > 0.7 else "متوسط" if strength > 0.4 else "ضعيف"
                                
                                st.markdown(f"""
                                <div class="card resistance-level">
                                    <h4 style="margin-top:0;">{level:.4f}</h4>
                                    <p>المسافة من السعر الحالي: 
                                        <span class="{'price-change-negative' if distance_pct < 0 else 'price-change-positive'}">
                                            {abs(distance_pct):.2f}%
                                        </span>
                                    </p>
                                    <p>قوة المستوى: 
                                        <span class="level-strength {strength_class}">{strength_text}</span>
                                    </p>
                                </div>
                                """, unsafe_allow_html=True)
                        else:
                            st.warning("لا توجد مستويات مقاومة واضحة")
                    
                    with col3:
                        st.markdown("### 💧 مناطق السيولة")
                        if liquidity_zones:
                            for zone in liquidity_zones:
                                price_range_pct = (zone[1] - zone[0]) / zone[0] * 100
                                st.markdown(f"""
                                <div class="card liquidity-zone">
                                    <h4 style="margin-top:0;">{zone[0]:.4f} - {zone[1]:.4f}</h4>
                                    <p>نطاق السعر: {price_range_pct:.2f}%</p>
                                    <p>الحجم: تركيز عالي</p>
                                    <div class="gauge-container">
                                        <div class="gauge">
                                            <div class="gauge-fill" style="width:{min(price_range_pct*3, 100)}%"></div>
                                        </div>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
                        else:
                            st.warning("لا توجد مناطق سيولة واضحة")
                    
                    # تمثيل مرئي للمستويات
                    if support or resistance:
                        st.markdown("---")
                        st.subheader("📊 تمثيل مرئي للمستويات الرئيسية")
                        
                        levels_fig = go.Figure()
                        
                        # السعر
                        levels_fig.add_trace(go.Scatter(
                            x=df['timestamp'],
                            y=df['close'],
                            name='السعر',
                            line=dict(color='#00f0ff', width=2)
                        ))
                        
                        # الدعم
                        for level, strength in support:
                            levels_fig.add_shape(type='line',
                                x0=df['timestamp'].iloc[0], y0=level,
                                x1=df['timestamp'].iloc[-1], y1=level,
                                line=dict(color='#00ff88', width=2, dash='dash'),
                                name=f'دعم {level:.2f}')
                            
                            levels_fig.add_trace(go.Scatter(
                                x=[df['timestamp'].iloc[-1]],
                                y=[level],
                                mode='markers+text',
                                marker=dict(size=12, color='#00ff88'),
                                text=[f' دعم {level:.2f}'],
                                textposition="middle right",
                                showlegend=False
                            ))
                        
                        # المقاومة
                        for level, strength in resistance:
                            levels_fig.add_shape(type='line',
                                x0=df['timestamp'].iloc[0], y0=level,
                                x1=df['timestamp'].iloc[-1], y1=level,
                                line=dict(color='#ff0066', width=2, dash='dash'),
                                name=f'مقاومة {level:.2f}')
                            
                            levels_fig.add_trace(go.Scatter(
                                x=[df['timestamp'].iloc[-1]],
                                y=[level],
                                mode='markers+text',
                                marker=dict(size=12, color='#ff0066'),
                                text=[f' مقاومة {level:.2f}'],
                                textposition="middle right",
                                showlegend=False
                            ))
                        
                        levels_fig.update_layout(
                            title="تصور مستويات الدعم والمقاومة",
                            height=500,
                            showlegend=True,
                            hovermode="x unified",
                            plot_bgcolor='rgba(10, 10, 30, 0.5)',
                            paper_bgcolor='rgba(10, 10, 30, 0.5)',
                            margin=dict(l=20, r=20, t=60, b=20),
                            font=dict(color='#e0f0ff'),
                            legend=dict(
                                orientation="h",
                                yanchor="bottom",
                                y=1.02,
                                xanchor="right",
                                x=1,
                                font=dict(color='#e0f0ff')
                            )
                        )
                        
                        st.plotly_chart(levels_fig, use_container_width=True)
                
                # الشريط الجانبي مع الروبوت والملاحظات
                with st.sidebar:
                    st.markdown("""
                    <div class="sidebar-robot-container">
                        <img src="https://cdn-icons-png.flaticon.com/512/4712/4712035.png" class="sidebar-robot">
                        <h3>مساعد التداول الآلي</h3>
                        <div class="status-pulse"></div>
                        <span>نظام الذكاء الاصطناعي نشط</span>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    st.markdown("### 📝 ملاحظات التحليل")
                    
                    if signal:
                        st.markdown(f"""
                        <div class="sidebar-notes">
                            <div class="sidebar-note">
                                <strong>الإشارة الحالية:</strong> {'شراء' if signal['action'] == 'BUY' else 'بيع'}
                            </div>
                            <div class="sidebar-note">
                                <strong>الثقة:</strong> {signal['confidence']:.0f}%
                            </div>
                            <div class="sidebar-note">
                                <strong>الإستراتيجية:</strong> {signal['strategy']}
                            </div>
                            <div class="sidebar-note">
                                <strong>العائد/المخاطرة:</strong> 1:{signal['risk_reward']:.2f}
                            </div>
                            <div class="sidebar-note">
                                <strong>التقلب:</strong> {'شديد' if signal['volatility']['level'] == 'extreme' else 'عالي' if signal['volatility']['level'] == 'high' else 'متوسط' if signal['volatility']['level'] == 'medium' else 'منخفض'}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # عرض نصائح مساعد الذكاء الاصطناعي في الشريط الجانبي
                        st.markdown("### 💡 نصائح المساعد")
                        ai_advice = analyzer.generate_ai_assistant_advice(signal, df)
                        
                        for advice in ai_advice:
                            if not advice.startswith("###"):
                                st.markdown(f"""
                                <div class="sidebar-notes">
                                    <div class="sidebar-note">• {advice}</div>
                                </div>
                                """, unsafe_allow_html=True)
            else:
                st.error("فشل في جلب بيانات كافية للعملة المشفرة المحددة")

def main():
    analyzer = CryptoPredictor2100()
    load_main_content(analyzer)

if __name__ == "__main__":
    main()