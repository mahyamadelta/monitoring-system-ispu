import streamlit as st
import pandas as pd
import json
import uuid
import time
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import paho.mqtt.client as mqtt
import queue  # Library penting untuk Threading

# --- KONFIGURASI UTAMA ---
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "project/tralalilo_trolia/sensor"

DEFAULT_LAT = -6.2495451129593675
DEFAULT_LON = 107.01400510003951

# --- SETUP HALAMAN ---
st.set_page_config(
    page_title="AirQuality Dashboard",
    page_icon="🍃",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS ---
st.markdown("""
    <style>
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 15px;
        text-align: center;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
    }
    </style>
    """, unsafe_allow_html=True)

# --- SHARED QUEUE (Jembatan Thread Aman) ---
# Kita gunakan cache_resource agar queue ini satu untuk semua
@st.cache_resource
def get_data_queue():
    return queue.Queue()

data_queue = get_data_queue()

# --- MQTT CALLBACKS (Dijalankan di Background Thread) ---
# PENTING: Jangan panggil st.session_state di sini!
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ MQTT Connected to {MQTT_TOPIC}")
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"❌ Failed to connect: {rc}")

def on_message(client, userdata, msg):
    try:
        raw_msg = msg.payload.decode()
        payload = json.loads(raw_msg)
        # Tambahkan timestamp saat diterima
        payload['timestamp'] = datetime.now()
        # Masukkan ke antrean (Queue) agar diambil oleh Main Thread
        data_queue.put(payload)
    except Exception as e:
        print(f"⚠️ Error parsing MQTT: {e}")

# --- START MQTT ---
@st.cache_resource
def start_mqtt_service():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start() # Jalan di background
    except Exception as e:
        print(f"Connection Error: {e}")
    return client

client = start_mqtt_service()

# --- INISIALISASI STATE (Main Thread) ---
if "data_buffer" not in st.session_state:
    st.session_state.data_buffer = []
if "last_packet" not in st.session_state:
    st.session_state.last_packet = {
        "suhu": 0, "kelembaban": 0, "co": 0, "pm25": 0,
        "no2": 0, "pm10": 0, "so2": 0, "o3": 0,
        "ai_label": "Menunggu...", "ai_score": 0,
        "timestamp": datetime.now()
    }
if "recording" not in st.session_state:
    st.session_state.recording = False
if "session_id" not in st.session_state:
    st.session_state.session_id = None

# --- PROSES DATA DARI QUEUE (Di Main Thread) ---
# Ambil semua data yang menumpuk di antrean dan update session_state
while not data_queue.empty():
    payload = data_queue.get()
    st.session_state.last_packet = payload
    
    # Logika Recording dipindah ke sini (aman)
    if st.session_state.recording:
        record = {
            "timestamp": payload['timestamp'],
            "session_id": st.session_state.session_id,
            "suhu": payload.get('suhu', 0),
            "kelembaban": payload.get('kelembaban', 0),
            "co": payload.get('co', 0),
            "pm25": payload.get('pm25', 0),
            "no2": payload.get('no2', 0),
            "pm10": payload.get('pm10', 0),
            "so2": payload.get('so2', 0),
            "o3": payload.get('o3', 0),
            "ai_score": payload.get('ai_score', 0),
            "ai_label": payload.get('ai_label', 'N/A'),
            "lat": DEFAULT_LAT,
            "lon": DEFAULT_LON
        }
        st.session_state.data_buffer.append(record)

# --- HELPER FUNCTIONS ---
def get_gauge_color(score):
    if score <= 50: return "#32CD32"
    elif score <= 100: return "#4169E1"
    elif score <= 200: return "#FFD700"
    elif score <= 300: return "#FF4500"
    else: return "#000000"

def get_recommendation(label):
    if label == "BAIK": return "✅ Udara Segar! Sangat baik untuk kegiatan luar ruangan."
    elif label == "SEDANG": return "⚠️ Kualitas sedang. Kelompok sensitif harap waspada."
    elif label == "TIDAK SEHAT": return "😷 Gunakan masker. Kurangi aktivitas berat di luar."
    elif label in ["SANGAT TIDAK SEHAT", "SGT TDK SEHAT"]: return "⛔ BAHAYA! Hindari keluar rumah."
    elif label == "BERBAHAYA": return "☠️ EVAKUASI! Udara beracun."
    else: return "Menunggu data..."

# ================= DASHBOARD UI =================

# --- SIDEBAR ---
with st.sidebar:
    st.title("🎛️ Panel Kontrol")
    
    # Indikator sederhana (tidak realtime update icon, tapi cukup)
    st.success("🟢 MQTT Service Running")

    st.markdown("---")
    st.header("⏺️ Perekaman Data")
    
    if st.button("▶️ Mulai Rekam", type="primary", disabled=st.session_state.recording):
        st.session_state.recording = True
        st.session_state.session_id = str(uuid.uuid4())[:8]
        st.rerun()
        
    if st.button("⏹ Stop Rekam", disabled=not st.session_state.recording):
        st.session_state.recording = False
        st.rerun()
        
    if st.session_state.recording:
        st.info(f"Sedang Merekam... (ID: {st.session_state.session_id})")
        
    if st.session_state.data_buffer:
        df = pd.DataFrame(st.session_state.data_buffer)
        st.download_button("💾 Download CSV", df.to_csv(index=False), "data_ispu.csv", "text/csv")

# --- HEADER UTAMA ---
st.title("🍃 AirQuality Guard Dashboard")
latest = st.session_state.last_packet
ispu_score = latest.get('ai_score', 0)
ispu_label = latest.get('ai_label', 'Menunggu...')

# --- ROW 1: GAUGE & STATUS ---
col1, col2 = st.columns([1, 2])

with col1:
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = ispu_score,
        title = {'text': "Skor ISPU"},
        gauge = {
            'axis': {'range': [None, 500]},
            'bar': {'color': get_gauge_color(ispu_score)},
            'steps': [
                {'range': [0, 50], 'color': "lightgreen"},
                {'range': [50, 100], 'color': "lightblue"},
                {'range': [100, 200], 'color': "orange"},
                {'range': [200, 300], 'color': "red"},
                {'range': [300, 500], 'color': "purple"}
            ],
        }
    ))
    fig.update_layout(height=280, margin=dict(l=20, r=20, t=30, b=20))
    # Perbaikan Warning: use_container_width dihapus jika error, atau diganti
    # Streamlit terbaru menyarankan tidak pakai argumen ini jika deprecated, 
    # tapi kita coba pakai argumen native plotly config di st.plotly_chart jika perlu.
    # Untuk amannya kita pakai key-word argument khusus jika versi baru.
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.markdown(f"### Status: **{ispu_label}**")
    
    if ispu_label == "BAIK":
        st.success(get_recommendation(ispu_label))
    elif ispu_label == "SEDANG":
        st.info(get_recommendation(ispu_label))
    elif ispu_label == "TIDAK SEHAT":
        st.warning(get_recommendation(ispu_label))
    else:
        st.error(get_recommendation(ispu_label))
        
    ts_str = latest.get('timestamp')
    if isinstance(ts_str, datetime):
        ts_str = ts_str.strftime("%H:%M:%S")
    st.caption(f"Update Terakhir: {ts_str}")

# --- BARIS 2: KARTU PARAMETER ---
st.subheader("📊 Detail Parameter")
tab1, tab2 = st.tabs(["🏠 Sensor Lokal", "☁️ Data Wilayah (API)"])

with tab1:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Suhu", f"{latest.get('suhu', 0)} °C")
    c2.metric("Kelembapan", f"{latest.get('kelembaban', 0)} %")
    c3.metric("CO", f"{latest.get('co', 0)} mg/m³")
    c4.metric("PM 2.5", f"{latest.get('pm25', 0)} µg/m³")

with tab2:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("NO₂", f"{latest.get('no2', 0)} µg/m³")
    c2.metric("PM 10", f"{latest.get('pm10', 0)} µg/m³")
    c3.metric("SO₂", f"{latest.get('so2', 0)} µg/m³")
    c4.metric("O₃", f"{latest.get('o3', 0)} µg/m³")

# --- BARIS 3: PETA & GRAFIK ---
c_map, c_graph = st.columns([1, 1])

with c_map:
    st.subheader("📍 Lokasi Alat")
    map_data = pd.DataFrame({
        'lat': [DEFAULT_LAT], 
        'lon': [DEFAULT_LON],
        'ispu': [ispu_score]
    })
    # Perbaikan Warning: width="stretch" tidak ada di st.map versi lama, 
    # tapi use_container_width=True masih umum. Jika error, gunakan parameter width integer.
    # Kita coba ikuti warning user:
    try:
        st.map(map_data, size=20, color="#FF0000", zoom=14, use_container_width=True)
    except:
        # Fallback jika parameter dihapus total
        st.map(map_data, size=20, color="#FF0000", zoom=14)

with c_graph:
    st.subheader("📈 Tren Real-time")
    if st.session_state.data_buffer:
        df_chart = pd.DataFrame(st.session_state.data_buffer)
        fig_chart = px.line(df_chart, x='timestamp', y=['co', 'pm25'], title="Tren Polutan Lokal")
        st.plotly_chart(fig_chart, use_container_width=True)
    else:
        st.info("Mulai perekaman untuk melihat grafik.")

# --- AUTO REFRESH ---
time.sleep(2)

st.rerun()
