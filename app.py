# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
from datetime import datetime
from PIL import Image
import requests
import json

# --- CONFIGURATION ---
DRIVE_FOLDER_ID = "1XRG-tnve3utZCkyfPEzwNQFYnHat9QIE"
SHEET_ID = "1KtW9m3hFq2sBUeRkNATvD4nRKu_cDCoZENXk7WgOafc"

# --- 1. CONNECTION SETUP ---
@st.cache_resource
def init_all_connections():
    try:
        creds_dict = st.secrets["gcp_service_account"]
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SHEET_ID)
        drive_service = build('drive', 'v3', credentials=creds)
        return spreadsheet, drive_service, True
    except Exception as e:
        return None, None, False

ss, drive_service, conn_status = init_all_connections()

# --- 2. CORE FUNCTIONS ---
def upload_to_drive(file, file_name):
    """อัปโหลดรูปภาพต้นฉบับไปที่ Drive (ความชัด 85%)"""
    try:
        img = Image.open(file)
        img.thumbnail((1200, 1200)) 
        buf = io.BytesIO()
        img.convert('RGB').save(buf, format="JPEG", quality=85)
        buf.seek(0)
        file_metadata = {'name': file_name, 'parents': [DRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(buf, mimetype='image/jpeg', resumable=True)
        file_drive = drive_service.files().create(body=file_metadata, media_body=media, fields='webViewLink').execute()
        return file_drive.get('webViewLink')
    except: return ""

def get_data(sheet_name):
    try:
        ws = ss.worksheet(sheet_name)
        return pd.DataFrame(ws.get_all_records()).fillna("")
    except: return pd.DataFrame()

# --- 3. LOGIN SYSTEM ---
if 'login' not in st.session_state: st.session_state.login = False

if not st.session_state.login:
    st.title("🔐 Repair System Login")
    with st.form("login_form"):
        user = st.text_input("Username").strip()
        pwd = st.text_input("Password", type="password").strip()
        if st.form_submit_button("Login"):
            df_u = get_data("users")
            match = df_u[(df_u['username'].astype(str) == user) & (df_u['password'].astype(str) == pwd)]
            if not match.empty:
                st.session_state.update({"login": True, "user": user, "role": match.iloc[0]['role']})
                st.rerun()
            else: st.error("ข้อมูลไม่ถูกต้อง")
    st.stop()

# --- 4. INTERFACE BY ROLE ---
role = st.session_state.role
st.sidebar.info(f"👤 {st.session_state.user} | Role: {role}")
if st.sidebar.button("Log out"):
    st.session_state.login = False
    st.rerun()

# --- [SECTION: USER] ---
if role == "user":
    st.header("📋 แจ้งซ่อมใหม่ (User)")
    repair_type = st.radio("ประเภทงานเสีย", ["PCBA", "Machine"], horizontal=True)
    
    with st.form("user_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            wo = st.text_input("Work Order (WO)")
            model = st.text_input("Model")
            sn = st.text_input("Serial Number (SN)")
        with c2:
            station = st.selectbox("Station", ["SMT", "DIP", "FCT", "Packing", "Machine Area"])
            defect = st.text_area("อาการเสีย (Defect)")
            img_file = st.file_uploader("แนบรูปภาพอาการเสีย", type=['jpg','png','jpeg'])
            
        if st.form_submit_button("🚀 ส่งข้อมูลแจ้งซ่อม"):
            if all([wo, sn, defect]):
                with st.spinner("กำลังบันทึก..."):
                    img_url = upload_to_drive(img_file, f"USER_{sn}.jpg") if img_file else ""
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    # บันทึก: Type, Time, WO, Model, SN, Station, Defect, Image, Status
                    ss.worksheet("sheet1").append_row([repair_type, now, wo, model, sn, station, defect, img_url, "Pending"])
                    st.success("ส่งข้อมูลสำเร็จ!")
            else: st.warning("กรุณากรอกข้อมูลให้ครบ")

# --- [SECTION: TECH] ---
elif role == "tech":
    st.header("🔧 บันทึกการซ่อม (Technician)")
    repair_type = st.radio("เลือกประเภทงานที่ต้องการซ่อม", ["PCBA", "Machine"], horizontal=True)
    
    target_sn = st.text_input("🔍 ค้นหา Serial Number เพื่อดำเนินการ").upper()
    if target_sn:
        df = get_data("sheet1")
        # กรองข้อมูลที่ยังไม่เสร็จและตรงกับ Type
        job = df[(df['sn'].astype(str) == target_sn) & (df['status'] != "Completed")].tail(1)
        
        if not job.empty:
            st.markdown("### 📋 ข้อมูลจาก User")
            st.write(f"**WO:** {job.iloc[0]['wo']} | **Model:** {job.iloc[0]['model']} | **Station:** {job.iloc[0]['station']}")
            st.info(f"**อาการเสีย:** {job.iloc[0]['defect']}")
            if job.iloc[0]['user_image']: st.image(job.iloc[0]['user_image'], caption="รูปจาก User", width=400)
            
            st.divider()
            with st.form("tech_action_form"):
                st.subheader("🛠️ Tech Action")
                real_case = st.text_input("Real Case (สาเหตุที่แท้จริง)")
                remark = st.text_area("Remark (หมายเหตุการซ่อม)")
                tech_img = st.file_uploader("แนบรูปหลังการซ่อม (Tech Image)", type=['jpg','png','jpeg'])
                
                # ฟังก์ชันพิเศษส่งต่อ PCBA
                fwd_pcba = False
                if repair_type == "PCBA":
                    fwd_pcba = st.checkbox("ส่งต่อให้ Tech PCBA (กรณีซ่อมไม่จบ)")

                if st.form_submit_button("💾 บันทึกและปิดงาน"):
                    idx = df[df['sn'].astype(str) == target_sn].index[-1] + 2
                    ws = ss.worksheet("sheet1")
                    img_tech_url = upload_to_drive(tech_img, f"TECH_{target_sn}.jpg") if tech_img else ""
                    
                    # อัปเดตข้อมูล Tech (คอลัมน์ I, J, K, L, M ตามลำดับใน Sheet)
                    now_tech = datetime.now().strftime("%Y-%m-%d %H:%M")
                    status_final = "Completed" if not fwd_pcba else "Pending (Fwd)"
                    
                    ws.update(f'H{idx}:L{idx}', [[status_final, real_case, remark, img_tech_url, now_tech]])
                    st.success("บันทึกผลการซ่อมเรียบร้อย!")
                    if fwd_pcba: st.warning("ส่งต่อข้อมูลไปยังแผนก PCBA เรียบร้อย")
        else: st.error("ไม่พบข้อมูล SN นี้ในระบบที่รอซ่อม")

# --- [SECTION: ADMIN / SUPER ADMIN] ---
elif role in ["admin", "super admin"]:
    st.title(f"🚀 {role.upper()} Management")
    tabs = st.tabs(["📊 Dashboard", "⚙️ Manage Master Data", "👥 User Control"])
    
    with tabs[0]:
        df = get_data("sheet1")
        st.subheader("Repair Data Overview")
        st.dataframe(df, use_container_width=True)
        # ตัวอย่างกราฟ
        if not df.empty:
            st.bar_chart(df['status'].value_counts())

    with tabs[1]:
        st.subheader("Manage Models & Stations")
        # โค้ดสำหรับ Admin แก้ไข Master Data (เช่น model_mat)
        
    if role == "super admin":
        with tabs[2]:
            st.subheader("User Account Management")
            # โค้ดสำหรับ Super Admin จัดการบัญชีผู้ใช้
