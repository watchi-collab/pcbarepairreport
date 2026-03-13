# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import cloudinary
import cloudinary.uploader
import requests
import time
import io
from datetime import datetime
from PIL import Image

# --- 1. SETTINGS ---
st.set_page_config(page_title="Repair Management System", layout="wide")
SHEET_ID = "1KtW9m3hFq2sBUeRkNATvD4nRKu_cDCoZENXk7WgOafc"

# --- 2. CONNECTIONS ---
@st.cache_resource
def init_all():
    try:
        # Google Sheets
        creds_dict = st.secrets["gcp_service_account"]
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        ss = client.open_by_key(SHEET_ID)
        
        # Cloudinary (Using dn8n04koh)
        cloudinary.config(
            cloud_name = "dn8n04koh",
            api_key = "352259521151764",
            api_secret = "R9S6W2_-CGIP4d-_uKA-nKW1gOg",
            secure = True
        )
        return ss, True
    except Exception as e:
        return e, False

ss, success = init_all()
if not success:
    st.error(f"❌ Connection Error: {ss}")
    st.stop()

# --- 3. HELPERS ---
def send_line(msg):
    token = st.secrets["line_channel_access_token"]
    group_id = st.secrets["line_group_id"]
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    payload = {"to": group_id, "messages": [{"type": "text", "text": msg}]}
    try: requests.post(url, headers=headers, json=payload)
    except: pass

def upload_images(files, prefix, sn):
    urls = []
    if not files: return ""
    for i, file in enumerate(files):
        try:
            img = Image.open(file)
            img.thumbnail((1000, 1000))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            buf.seek(0)
            res = cloudinary.uploader.upload(
                buf, folder="repair_system",
                public_id=f"{prefix}_{sn}_{int(time.time())}_{i+1}",
                format="jpg"
            )
            urls.append(res.get("secure_url"))
        except: continue
    return ",".join(urls)

def get_df(name):
    try:
        ws = ss.worksheet(name)
        df = pd.DataFrame(ws.get_all_records())
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        return df.fillna("")
    except: return pd.DataFrame()

# --- 4. AUTHENTICATION ---
if 'is_logged_in' not in st.session_state:
    st.session_state.is_logged_in = False

if not st.session_state.is_logged_in:
    st.title("⚙️ Repair System Login")
    with st.form("login"):
        u = st.text_input("Username").strip()
        p = st.text_input("Password", type="password").strip()
        mode = st.selectbox("โหมดการทำงาน", ["PCBA", "Machine"])
        if st.form_submit_button("Login"):
            df_u = get_df("users")
            match = df_u[(df_u['username'].astype(str)==u) & (df_u['password'].astype(str)==p)]
            if not match.empty:
                st.session_state.update({"is_logged_in": True, "user": u, "role": match.iloc[0]['role'].lower(), "app_mode": mode})
                st.rerun()
    st.stop()

# --- 5. MAIN LOGIC ---
ws_main = ss.worksheet("sheet1")
role = st.session_state.role
current_user = st.session_state.user
app_mode = st.session_state.app_mode

# Sidebar
with st.sidebar:
    st.title(f"👤 {current_user}")
    st.info(f"Mode: {app_mode}")
    if st.button("Log out"):
        st.session_state.is_logged_in = False
        st.rerun()

# --- [หน้าสำหรับช่าง] ---
if role == "tech":
    st.header("🔧 แผงควบคุมช่าง (Technician)")
    sn_scan = st.text_input("🔍 สแกน Serial Number", placeholder="Scan Barcode...").strip().upper()
    
    if sn_scan:
        df_all = get_df("sheet1")
        job_match = df_all[(df_all['serial_number'].astype(str) == sn_scan) & (df_all['status'] == "Pending")]
        
        if not job_match.empty:
            job = job_match.iloc[-1]
            row_idx = job_match.index[-1] + 2
            
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("ข้อมูลการแจ้งซ่อม")
                st.info(f"**Model:** {job['model']} \n\n **WO:** {job['work_order']} \n\n **อาการเสีย:** {job['failure']}")
                if job.get('user_image'):
                    for img in str(job['user_image']).split(','):
                        if img: st.image(img.strip(), use_container_width=True)

            with c2:
                st.subheader("บันทึกการซ่อม")
                with st.form("tech_action"):
                    res_status = st.radio("สถานะ:", ["Complate", "Scrap"], horizontal=True)
                    action_detail = st.text_input("Action")
                    t_files = st.file_uploader("แนบรูปหลังซ่อม", accept_multiple_files=True)
                    if st.form_submit_button("บันทึกปิดงาน"):
                        t_urls = upload_images(t_files, "TECH", sn_scan)
                        now_time = datetime.now().strftime("%Y-%m-%d %H:%M")
                        ws_main.update(f'B{row_idx}', [[res_status]])
                        ws_main.update(f'K{row_idx}:O{row_idx}', [[action_detail, "", "", current_user, now_time]])
                        ws_main.update(f'Q{row_idx}', [[t_urls]])
                        send_line(f"✅ {res_status}!\nSN: {sn_scan}\nโดย: {current_user}")
                        st.success("บันทึกเรียบร้อย!"); st.rerun()
        else:
            st.warning("⚠️ ไม่พบงานค้างซ่อมสำหรับ SN นี้")

# --- [หน้าสำหรับ USER] ---
elif role == "user":
    st.header(f"🚀 ใบแจ้งซ่อมใหม่ ({app_mode})")
    
    # ดึงข้อมูลจาก Dropdown Sheets (อ้างอิงจากรูปที่คุณส่งมา)
    df_models = get_df("model_machine" if app_mode == "Machine" else "model_mat")
    df_stations = get_df("station_dropdowns")
    
    with st.form("user_request"):
        col1, col2 = st.columns(2)
        with col1:
            sel_model = st.selectbox("เลือก Model", [""] + df_models['model'].tolist())
            sn_in = st.text_input("Serial Number").strip().upper()
        with col2:
            wo_in = st.text_input("Work Order (WO)").strip().upper()
            # Dropdown Station ดึงจาก Sheet "station_dropdowns"
            station_in = st.selectbox("Station / กระบวนการ", [""] + df_stations['station'].tolist())
        
        u_files = st.file_uploader("📸 แนบรูปถ่ายอาการเสีย", accept_multiple_files=True)
        fail_in = st.text_area("รายละเอียดอาการเสีย")
        
        if st.form_submit_button("ส่งใบแจ้งซ่อม", use_container_width=True):
            if sel_model and sn_in and wo_in:
                with st.spinner("กำลังส่งข้อมูล..."):
                    u_urls = upload_images(u_files, "REQ", sn_in)
                    p_name = df_models[df_models['model']==sel_model].iloc[0]['product_name']
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                    
                    # บันทึกข้อมูลเรียงตาม Column A-Q
                    row = [app_mode, "Pending", wo_in, sel_model, p_name, sn_in, station_in, fail_in, now_str, "", "", "", "", "", ""]
                    ws_main.append_row(row + [u_urls])
                    
                    send_line(f"🚨 แจ้งซ่อมใหม่!\nSN: {sn_in}\nWO: {wo_in}\nStation: {station_in}")
                    st.success("ส่งข้อมูลสำเร็จ!"); st.rerun()
            else:
                st.warning("กรุณากรอก Model, SN และ WO ให้ครบถ้วน")
elif role in ["admin", "super admin"]:
    st.header("📊 Dashboard")
    df = get_clean_df("sheet1")
    if not df.empty:
        st.plotly_chart(px.pie(df, names='status', color='status', color_discrete_map={'Pending':'orange','Complate':'green','Scrap':'red'}))
        st.dataframe(df)
