# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import time
import requests
from datetime import datetime
from PIL import Image
import plotly.express as px

# --- CONFIGURATION ---
DRIVE_FOLDER_ID = "1XRG-tnve3utZCkyfPEzwNQFYnHat9QIE"
SHEET_ID = "1KtW9m3hFq2sBUeRkNATvD4nRKu_cDCoZENXk7WgOafc"
LINE_TOKEN = "8R7OZwOHqJNKHy2UZ+cblruG6eemV1ZT3SPxII91m3QVSX6AwTlfd4xhf9vke1q+IwsKf+WjhMs3TcRrBkGIERTaXSa28MceeBFm5lugLDuMUyWWRyvDMUDVRk8ZFAryZf48/nfT0CqsorHhUohIKwdB04t89/1O/w1cDnyilFU="
LINE_GROUP_ID = "U08c0192a3a6d0150daf2f430f1d3f81b"

# --- 1. CONNECTION ---
@st.cache_resource
def init_all():
    try:
        # ใช้ข้อมูลจากที่คุณให้มาโดยตรง
        creds_dict = st.secrets["gcp_service_account"]
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SHEET_ID)
        drive_service = build('drive', 'v3', credentials=creds)
        return spreadsheet, drive_service, True
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return None, None, False

ss, drive_service, conn_status = init_all()

# --- 2. NOTIFICATION & HELPERS ---
def send_line_msg(message):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
    payload = {"to": LINE_GROUP_ID, "messages": [{"type": "text", "text": message}]}
    try: requests.post(url, headers=headers, json=payload)
    except: pass

def get_clean_df(sheet_name):
    try:
        ws = ss.worksheet(sheet_name)
        df = pd.DataFrame(ws.get_all_records())
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        return df.fillna("")
    except: return pd.DataFrame()

def upload_multiple_images(files, prefix, sn):
    urls = []
    if not files: return ""
    for i, file in enumerate(files):
        try:
            img = Image.open(file).convert('RGB')
            img.thumbnail((800, 800))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=75)
            buf.seek(0)
            
            f_name = f"{prefix}_{sn}_{datetime.now().strftime('%H%M%S')}_{i+1}.jpg"
            f_meta = {
                'name': f_name, 
                'parents': [DRIVE_FOLDER_ID]
            }
            media = MediaIoBaseUpload(buf, mimetype='image/jpeg', resumable=True)
            
            # --- แก้ไขจุดนี้: เพิ่ม supportsAllDrives=True ---
            f_drive = drive_service.files().create(
                body=f_meta, 
                media_body=media, 
                fields='id, webViewLink',
                supportsAllDrives=True  # บังคับใช้โควตาเจ้าของโฟลเดอร์
            ).execute()
            
            # เปิด Permission ให้ดูรูปได้
            drive_service.permissions().create(
                fileId=f_drive.get('id'), 
                body={'type': 'anyone', 'role': 'viewer'},
                supportsAllDrives=True
            ).execute()
            
            urls.append(f_drive.get('webViewLink'))
        except Exception as e:
            st.error(f"❌ อัปโหลดล้มเหลว: {e}") # จะช่วยโชว์ Error ถ้ายังติดเรื่องอื่น
            continue
    return ",".join(urls)
# --- 3. LOGIN ---
if 'is_logged_in' not in st.session_state: st.session_state.is_logged_in = False

if not st.session_state.is_logged_in:
    st.title("⚙️ PCBA/Machine Repair System")
    mode_init = st.selectbox("โหมดการทำงาน", ["PCBA", "Machine"])
    with st.form("login_form"):
        u = st.text_input("Username").strip()
        p = st.text_input("Password", type="password").strip()
        if st.form_submit_button("Login"):
            df_u = get_clean_df("users")
            match = df_u[(df_u['username'].astype(str) == u) & (df_u['password'].astype(str) == p)]
            if not match.empty:
                st.session_state.update({"is_logged_in": True, "user": u, "role": match.iloc[0]['role'].lower(), "app_mode": mode_init})
                st.rerun()
            else: st.error("Login Failed")
    st.stop()

# Load Data
df_stations = get_clean_df("station_dropdowns")
station_list = df_stations['category'].tolist() if not df_stations.empty else ["General"]
df_actions = get_clean_df("action_dropdowns")
action_list = df_actions['category'].tolist() if not df_actions.empty else ["Repair", "Replace"]

# --- 4. INTERFACE ---
role = st.session_state.role
current_mode = st.session_state.app_mode

# --- [TECH SECTION] ---
if role == "tech":
    st.header("🔧 Technician Action Center")
    search_sn = st.text_input("🔍 Scan Serial Number (SN)").strip().upper()
    if search_sn:
        df_all = get_clean_df("sheet1")
        active = df_all[(df_all['serial_number'].astype(str) == search_sn) & (df_all['status'] == "Pending")]
        if not active.empty:
            job = active.tail(1).iloc[0]
            idx = active.tail(1).index[0] + 2
            
            col1, col2 = st.columns([1, 1.2])
            with col1:
                st.subheader("📋 Job Detail")
                st.info(f"**Model:** {job['model']}\n\n**Failure:** {job['failure']}")
                if job.get('user_image'):
                    for img in str(job['user_image']).split(','):
                        if img: st.image(img.strip(), use_container_width=True)
            
            with col2:
                with st.form("repair_form"):
                    res_status = st.radio("Status", ["Complate", "Scrap"], horizontal=True)
                    r_case = st.text_input("Real Case")
                    act = st.selectbox("Action", action_list)
                    rem = st.text_area("Remark")
                    files = st.file_uploader("📸 Tech Photo", accept_multiple_files=True)
                    if st.form_submit_button("💾 Save & Close"):
                        t_links = upload_multiple_images(files, "TECH", search_sn)
                        t_now = datetime.now().strftime("%Y-%m-%d %H:%M")
                        ws = ss.worksheet("sheet1")
                        ws.update(f'B{idx}', [[res_status]])
                        ws.update(f'J{idx}:O{idx}', [[r_case, act, "", rem, st.session_state.user, t_now]])
                        ws.update(f'Q{idx}', [[t_links]])
                        send_line_msg(f"✅ Job Closed!\nSN: {search_sn}\nStatus: {res_status}\nBy: {st.session_state.user}")
                        st.success("บันทึกสำเร็จ!"); time.sleep(2); st.rerun()

# --- [USER SECTION] ---
elif role == "user":
    st.header(f"🚀 New Repair Request ({current_mode})")
    df_models = get_clean_df("model_machine" if current_mode == "Machine" else "model_mat")
    with st.form("user_form"):
        model = st.selectbox("Model", [""] + df_models['model'].tolist())
        sn = st.text_input("Serial Number").upper()
        stn = st.selectbox("Station", station_list)
        defect = st.text_area("Defect Detail")
        u_files = st.file_uploader("📸 Defect Photo", accept_multiple_files=True)
        if st.form_submit_button("Submit Request"):
            if model and sn:
                links = upload_multiple_images(u_files, "REQ", sn)
                ws = ss.worksheet("sheet1")
                p_name = df_models[df_models['model']==model].iloc[0]['product_name']
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                # บันทึกถึงคอลัมน์ P (16)
                row_base = [current_mode, "Pending", "", model, p_name, sn, stn, defect, now, "", "", "", "", "", ""]
                ws.append_row(row_base + [links])
                send_line_msg(f"🚨 New Repair Request!\nMode: {current_mode}\nSN: {sn}\nStation: {stn}\nDefect: {defect}")
                st.success("ส่งแจ้งซ่อมสำเร็จ!"); st.rerun()

# --- [ADMIN SECTION] ---
elif role in ["admin", "super admin"]:
    st.header("📊 Dashboard")
    df = get_clean_df("sheet1")
    if not df.empty:
        st.plotly_chart(px.pie(df, names='status', color='status', color_discrete_map={'Pending':'orange','Complate':'green','Scrap':'red'}))
        st.dataframe(df)
