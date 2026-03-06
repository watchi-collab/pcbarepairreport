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
    if not file: return ""
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
        df = pd.DataFrame(ws.get_all_records())
        # ปรับชื่อคอลัมน์ให้ไม่มีช่องว่างเพื่อลด Error
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        return df.fillna("")
    except: return pd.DataFrame()

# --- 3. LOGIN SYSTEM ---
if 'login' not in st.session_state: st.session_state.login = False

if not st.session_state.login:
    st.title("🔐 Repair System Login 2026")
    with st.form("login_form"):
        user = st.text_input("Username").strip()
        pwd = st.text_input("Password", type="password").strip()
        if st.form_submit_button("Login"):
            df_u = get_data("users")
            if not df_u.empty:
                match = df_u[(df_u['username'].astype(str) == user) & (df_u['password'].astype(str) == pwd)]
                if not match.empty:
                    st.session_state.update({"login": True, "user": user, "role": match.iloc[0]['role'].lower()})
                    st.rerun()
                else: st.error("ข้อมูลไม่ถูกต้อง")
    st.stop()

# --- 4. MAIN INTERFACE ---
role = st.session_state.role
st.sidebar.info(f"👤 {st.session_state.user} | Role: {role.upper()}")
if st.sidebar.button("Log out"):
    st.session_state.login = False
    st.rerun()

# --- [SECTION: USER] ---
if role == "user":
    st.header("📋 แจ้งซ่อมใหม่ (User Reporting)")
    repair_type = st.radio("ประเภทงาน", ["PCBA", "Machine"], horizontal=True)
    
    with st.form("user_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            wo = st.text_input("Work Order (WO)").upper()
            model = st.text_input("Model Name").upper()
            prod_name = st.text_input("Product Name")
        with c2:
            sn = st.text_input("Serial Number (SN)").upper()
            station = st.selectbox("Station", ["SMT", "DIP", "FCT", "Packing", "Machine Area"])
            defect = st.text_area("อาการเสีย (Defect)")
            
        if st.form_submit_button("🚀 ส่งข้อมูลแจ้งซ่อม"):
            if all([wo, sn, defect]):
                with st.spinner("กำลังบันทึกข้อมูล..."):
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    # A:user_id, B:status, C:wo, D:model, E:prod, F:sn, G:station, H:failure, I:user_time
                    row = [st.session_state.user, "Pending", wo, model, prod_name, sn, station, defect, now]
                    ss.worksheet("sheet1").append_row(row)
                    st.success("บันทึกข้อมูลแจ้งซ่อมสำเร็จ!")
            else: st.warning("กรุณากรอกข้อมูลให้ครบถ้วน")

# --- [SECTION: TECH] ---
elif role == "tech":
    st.header("🔧 บันทึกการซ่อม (Technician Action)")
    target_sn = st.text_input("🔍 Scan Serial Number เพื่อดำเนินการ").strip().upper()
    
    if target_sn:
        df = get_data("sheet1")
        # ค้นหางานล่าสุดที่ยังซ่อมไม่เสร็จของ SN นี้
        job = df[(df['serial_number'].astype(str) == target_sn) & (df['status'] != "Completed")].tail(1)
        
        if not job.empty:
            st.success(f"พบข้อมูลงานเสีย: {job.iloc[0]['work_order']}")
            st.info(f"**Model:** {job.iloc[0]['model']} | **อาการ:** {job.iloc[0]['failure']}")
            
            with st.form("tech_form"):
                st.subheader("🛠️ Tech Action Detail")
                real_case = st.text_input("Real Case (สาเหตุ)")
                action = st.text_input("Action Taken (การแก้ไข)")
                classif = st.selectbox("Classification", ["Solder Bridge", "Missing Part", "Wrong Part", "Damage", "Machine Error"])
                remark = st.text_area("Remark (หมายเหตุ)")
                
                if st.form_submit_button("💾 บันทึกและปิดงาน"):
                    with st.spinner("กำลังอัปเดต..."):
                        # หาตำแหน่งแถวใน Sheets
                        idx = df[df['serial_number'].astype(str) == target_sn].index[-1] + 2
                        ws = ss.worksheet("sheet1")
                        now_tech = datetime.now().strftime("%Y-%m-%d %H:%M")
                        
                        # อัปเดตสถานะที่คอลัมน์ B
                        ws.update(f'B{idx}', [['Completed']])
                        # อัปเดตข้อมูลซ่อม J:real_case, K:action, L:class, M:remark, N:tech_id, O:tech_time
                        tech_row = [[real_case, action, classif, remark, st.session_state.user, now_tech]]
                        ws.update(f'J{idx}:O{idx}', tech_row)
                        
                        st.success("บันทึกผลการซ่อมเรียบร้อย!")
        else: st.error("ไม่พบข้อมูล SN นี้ที่ค้างซ่อม")

# --- [SECTION: ADMIN] ---
elif role in ["admin", "super admin"]:
    st.header("📊 Admin Dashboard & Control")
    df = get_data("sheet1")
    
    st.subheader("รายการซ่อมทั้งหมด (Column A-O)")
    st.dataframe(df, use_container_width=True)
    
    if not df.empty:
        c1, c2 = st.columns(2)
        with c1:
            st.write("**สถานะงานรวม**")
            st.bar_chart(df['status'].value_counts())
        with c2:
            # ปุ่ม Export
            csv = df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 Download Report (CSV)", data=csv, file_name="repair_report.csv", mime='text/csv')
