import streamlit as st
import json
import time
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import paho.mqtt.client as mqtt
from datetime import datetime
import queue 
import uuid 
import math # Untuk hitung total halaman

# =========================
# KONFIGURASI
# =========================
BROKER = "broker.hivemq.com"
PORT = 1883
TOPIC = "project/tralalilo_trolia/sensor"

DEFAULT_LAT = -6.2374
DEFAULT_LON = 106.9930

# =========================
# SETUP HALAMAN
# =========================
st.set_page_config(
    page_title="AirQuality Guard IoT",
    page_icon="🍃",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
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

# =========================
# SHARED QUEUE (JEMBATAN DATA)
# =========================
@st.cache_resource
def get_data_queue():
    return queue.Queue()

data_queue = get_data_queue()

# =========================
# SESSION STATE INIT
# =========================
if "latest_data" not in st.session_state:
    st.session_state.latest_data = {}
if "data_history" not in st.session_state:
    st.session_state.data_history = []

# --- STATE UNTUK PEREKAMAN ---
if "recording" not in st.session_state:
    st.session_state.recording = False
if "recording_buffer" not in st.session_state:
    st.session_state.recording_buffer = []
if "session_id" not in st.session_state:
    st.session_state.session_id = None

# --- STATE UNTUK PAGINATION TABEL ---
if "table_page" not in st.session_state:
    st.session_state.table_page = 0

# =========================
# MQTT LOGIC (BACKGROUND)
# =========================
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("✅ Connected to MQTT")
        client.subscribe(TOPIC)

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        payload['timestamp'] = datetime.now()
        data_queue.put(payload)
    except Exception as e:
        print("Payload error:", e)

@st.cache_resource
def start_mqtt_service():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(BROKER, PORT, 60)
        client.loop_start()
        print("🚀 MQTT Thread Started")
    except Exception as e:
        print(f"Connection Failed: {e}")
    return client

start_mqtt_service()

# =========================
# MAIN THREAD: PROCESS DATA
# =========================
while not data_queue.empty():
    new_data = data_queue.get()
    st.session_state.latest_data = new_data
    
    # 1. Update History untuk Grafik Live
    if not st.session_state.data_history or st.session_state.data_history[-1].get('timestamp') != new_data['timestamp']:
        st.session_state.data_history.append(new_data)
        if len(st.session_state.data_history) > 100:
            st.session_state.data_history.pop(0)
    
    # 2. Logika Perekaman (Recording)
    if st.session_state.recording:
        record_entry = new_data.copy()
        record_entry['session_id'] = st.session_state.session_id
        # Format timestamp agar rapi di tabel
        record_entry['timestamp'] = record_entry['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
        st.session_state.recording_buffer.append(record_entry)

# =========================
# UI LOGIC
# =========================
data = st.session_state.latest_data

def get_gauge_color(score_percent):
    if score_percent >= 80: return "green"
    elif score_percent >= 50: return "orange"
    else: return "red"

def get_status_color(label):
    if label == "BAIK": return "green"
    if label == "SEDANG": return "blue"
    if label == "TIDAK SEHAT": return "#FFCC00"
    if label == "SANGAT TIDAK SEHAT": return "orange"
    return "red"

# --- SIDEBAR ---
with st.sidebar:
    st.title("🎛️ Admin Panel")
    st.success("🟢 MQTT Service Running")
    st.markdown("---")
    
    node = st.selectbox("Pilih Perangkat:", ["Node 1 - Terminal Bekasi", "Node 2 - Offline"])
    
    st.markdown("### ⏺️ Perekaman Data")
    
    # Tombol Start
    if st.button("▶️ Mulai Rekam", type="primary", disabled=st.session_state.recording):
        st.session_state.recording = True
        st.session_state.session_id = str(uuid.uuid4())[:8]
        st.session_state.recording_buffer = [] # Reset buffer saat mulai baru
        st.session_state.table_page = 0 # Reset halaman tabel
        st.rerun()
        
    # Tombol Stop
    if st.button("⏹ Hentikan Rekam", disabled=not st.session_state.recording):
        st.session_state.recording = False
        st.rerun()
    
    if st.session_state.recording:
        st.info(f"Merekam... Data: {len(st.session_state.recording_buffer)} baris")
        
    # Tombol Download
    if st.session_state.recording_buffer:
        df_rec = pd.DataFrame(st.session_state.recording_buffer)
        csv = df_rec.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"data_rekaman_{st.session_state.session_id}.csv",
            mime="text/csv"
        )

    st.markdown("---")
    if st.button("🗑️ Hapus Grafik Live"):
        st.session_state.data_history = []
        st.rerun()

# --- HEADER ---
if not data:
    st.info("📡 Menunggu data MQTT... (Pastikan alat menyala)")
    time.sleep(2)
    st.rerun()

ai_label = data.get("ai_label", "MENUNGGU")
ai_score = float(data.get("ai_score", 0))

st.title("🌫️ AirQuality Guard Dashboard")
st.markdown(f"**Lokasi:** {node} | **Update:** {data.get('timestamp').strftime('%H:%M:%S')}")

if ai_label in ["SANGAT TIDAK SEHAT", "BERBAHAYA"]:
    st.error(f"🚨 PERINGATAN: Kualitas Udara {ai_label}!")
elif ai_label == "TIDAK SEHAT":
    st.warning(f"⚠️ PERINGATAN: Kualitas Udara {ai_label}.")
else:
    st.success(f"✅ Status Udara: {ai_label}")

# --- ROW 1: PETA & GAUGE ---
col_map, col_gauge = st.columns([2, 1])

with col_map:
    st.subheader("📍 Lokasi Real-time")
    map_data = pd.DataFrame({
        'lat': [DEFAULT_LAT],
        'lon': [DEFAULT_LON],
        'status': [ai_label],
        'size': [20]
    })
    color_map = {"BAIK": "green", "SEDANG": "blue", "TIDAK SEHAT": "orange", "BERBAHAYA": "red"}
    
    fig_map = px.scatter_mapbox(
        map_data, lat="lat", lon="lon", color="status", size="size",
        color_discrete_map=color_map, zoom=14, height=300
    )
    fig_map.update_layout(mapbox_style="open-street-map", margin={"r":0,"t":0,"l":0,"b":0})
    st.plotly_chart(fig_map, use_container_width=True)

with col_gauge:
    st.subheader("📊 AI Confidence")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = ai_score * 100,
        title = {'text': f"{ai_label}"},
        gauge = {
            'axis': {'range': [0, 100]},
            'bar': {'color': get_gauge_color(ai_score * 100)},
            'steps': [{'range': [0, 100], 'color': "#f0f2f6"}],
            'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': 70}
        }
    ))
    fig_gauge.update_layout(height=300, margin=dict(l=20, r=20, t=50, b=20))
    st.plotly_chart(fig_gauge, use_container_width=True)

# --- ROW 2: PARAMETER ---
st.subheader("📈 Parameter Udara")
tab_lokal, tab_api = st.tabs(["🏠 Sensor Lokal", "☁️ Data API"])

with tab_lokal:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("CO", f"{data.get('co')} mg/m³")
    c2.metric("PM 2.5", f"{data.get('pm25')} µg/m³")
    c3.metric("Suhu", f"{data.get('suhu')} °C")
    c4.metric("Kelembapan", f"{data.get('kelembaban')} %")

with tab_api:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("NO₂", f"{data.get('no2')} µg/m³")
    c2.metric("PM 10", f"{data.get('pm10')} µg/m³")
    c3.metric("SO₂", f"{data.get('so2')} µg/m³")
    c4.metric("Ozon", f"{data.get('o3')} µg/m³")

# --- ROW 3: GRAFIK ---
st.subheader("📉 Tren Real-time")
if len(st.session_state.data_history) > 1:
    df_hist = pd.DataFrame(st.session_state.data_history)
    fig_hist = px.line(df_hist, x='timestamp', y=['co', 'pm25', 'no2'], title="Tren Polutan")
    st.plotly_chart(fig_hist, use_container_width=True)
else:
    st.info("Menunggu data untuk grafik...")

# --- ROW 4: TABEL DATA REKAMAN (NEW FEATURE) ---
st.markdown("---")
st.subheader("📋 Log Data Rekaman")

if st.session_state.recording_buffer:
    df_table = pd.DataFrame(st.session_state.recording_buffer)
    
    # Konfigurasi Pagination
    ITEMS_PER_PAGE = 10
    total_items = len(df_table)
    total_pages = math.ceil(total_items / ITEMS_PER_PAGE)
    
    # Tombol Navigasi
    col_prev, col_page, col_next = st.columns([1, 2, 1])
    
    with col_prev:
        if st.button("⬅️ Sebelumnya"):
            if st.session_state.table_page > 0:
                st.session_state.table_page -= 1
                st.rerun()
                
    with col_next:
        if st.button("Selanjutnya ➡️"):
            if st.session_state.table_page < total_pages - 1:
                st.session_state.table_page += 1
                st.rerun()
                
    with col_page:
        st.write(f"Halaman **{st.session_state.table_page + 1}** dari **{total_pages}** (Total: {total_items} data)")

    # Slicing Data (Urutan Terbaru di Atas)
    df_table = df_table.sort_index(ascending=False).reset_index(drop=True)
    start_idx = st.session_state.table_page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    
    # Tampilkan Tabel
    st.dataframe(
        df_table.iloc[start_idx:end_idx], 
        use_container_width=True,
        column_config={
            "timestamp": "Waktu",
            "session_id": "ID Sesi"
        }
    )
else:
    st.info("Belum ada data yang direkam. Klik 'Mulai Rekam' di sidebar untuk mengumpulkan data.")

# Auto Refresh
time.sleep(2)
st.rerun()
