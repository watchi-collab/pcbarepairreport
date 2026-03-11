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

# --- CONFIGURATION ---
DRIVE_FOLDER_ID = "1XRG-tnve3utZCkyfPEzwNQFYnHat9QIE"
SHEET_ID = "1KtW9m3hFq2sBUeRkNATvD4nRKu_cDCoZENXk7WgOafc"

# --- 1. CONNECTION ---
@st.cache_resource
def init_all():
    try:
        creds_dict = st.secrets["gcp_service_account"]
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SHEET_ID)
        drive_service = build('drive', 'v3', credentials=creds)
        return spreadsheet, drive_service, True
    except: return None, None, False

ss, drive_service, conn_status = init_all()

# --- 2. HELPERS ---
def get_clean_df(sheet_name):
    try:
        ws = ss.worksheet(sheet_name)
        df = pd.DataFrame(ws.get_all_records())
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        return df.fillna("")
    except: return pd.DataFrame()

# --- 3. LOGIN WITH MODE SELECTION ---
if 'is_logged_in' not in st.session_state: st.session_state.is_logged_in = False

if not st.session_state.is_logged_in:
    st.title("🛡️ Repair Management System")
    
    # เลือกโหมดก่อน Login
    app_mode = st.selectbox("เลือกประเภทงาน", ["PCBA", "Machine"], index=0)
    
    with st.form("auth_form"):
        u = st.text_input("Username").strip()
        p = st.text_input("Password", type="password").strip()
        if st.form_submit_button("Sign In"):
            df_u = get_clean_df("users")
            match = df_u[(df_u['username'].astype(str) == u) & (df_u['password'].astype(str) == p)]
            if not match.empty:
                st.session_state.update({
                    "is_logged_in": True, 
                    "user": u, 
                    "role": match.iloc[0]['role'].lower(),
                    "app_mode": app_mode
                })
                st.rerun()
            else: st.error("Login Failed")
    st.stop()

# --- 4. INTERFACE ---
role = st.session_state.role
mode = st.session_state.app_mode

st.sidebar.info(f"👤 {st.session_state.user} | Mode: {mode}")
if st.sidebar.button("Logout"):
    st.session_state.is_logged_in = False
    st.rerun()

# --- [SECTION: USER] ---
if role == "user":
    st.header(f"📋 แจ้งซ่อมใหม่ ({mode} Reporting)")
    
    # --- Dynamic Model Loading ---
    # หากเป็น Machine ให้ดึงจาก model_machine หากเป็น PCBA ให้ดึงจาก model_mat
    model_sheet = "model_machine" if mode == "Machine" else "model_mat"
    df_model_source = get_clean_df(model_sheet)
    model_list = df_model_source['model'].tolist() if not df_model_source.empty else []

    # ดึง Station จาก station_dropdowns
    df_stations = get_clean_df("station_dropdowns")
    station_list = df_stations['category'].tolist() if not df_stations.empty else []

    with st.form("user_entry_form"):
        c1, c2 = st.columns(2)
        with c1:
            input_model = st.selectbox("Model Name", [""] + model_list)
            
            # Smart Mapping จากชีตที่เลือก
            auto_prod = ""
            if input_model:
                match = df_model_source[df_model_source['model'] == input_model]
                if not match.empty:
                    auto_prod = match.iloc[0]['product_name']
            
            product_name = st.text_input("Product Name (Auto)", value=auto_prod, disabled=True)
            wo = st.text_input("Work Order (WO)")
            
        with c2:
            sn = st.text_input("Serial Number (SN)").upper()
            station = st.selectbox("Station", station_list)
            defect = st.text_area("อาการเสีย (Defect)")
        
        if st.form_submit_button("🚀 ส่งข้อมูลแจ้งซ่อม"):
            if input_model and sn and defect:
                with st.spinner("Recording..."):
                    ws = ss.worksheet("sheet1")
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    # บันทึกข้อมูลลง Sheet1 ตามลำดับหัวคอลัมน์
                    # Category, Status, WO, Model, Product Name, SN, Station, Failure, User Time
                    row = [mode, "Pending", wo, input_model, auto_prod, sn, station, defect, now]
                    ws.append_row(row)
                    st.success(f"บันทึกข้อมูลหมวด {mode} เรียบร้อย!")
            else:
                st.warning("กรุณากรอกข้อมูลให้ครบถ้วน")

# --- [SECTION: TECH] ---
elif role == "tech":
    st.header(f"🔧 Technician Action ({mode})")
    # ดึง Action และ Classification จากชีตที่กำหนด
    df_actions = get_clean_df("action_dropdowns")
    df_class = get_clean_df("classification_dropdowns")
    
    search_sn = st.text_input(f"🔍 Scan SN ({mode})").strip().upper()
    
    if search_sn:
        df = get_clean_df("sheet1")
        # กรองเฉพาะโหมดที่เลือกมาตอน Login
        job = df[(df['serial_number'].astype(str) == search_sn) & 
                 (df['category'].astype(str) == mode) & 
                 (df['status'] != "Completed")].tail(1)
        
        if not job.empty:
            st.success(f"พบรายการ: {job.iloc[0]['product_name']}")
            with st.form("tech_form"):
                real_case = st.text_input("Real Case")
                act_choice = st.selectbox("Action", action_list) # จาก action_dropdowns
                class_choice = st.selectbox("Classification", class_list) # จาก classification_dropdowns
                remark = st.text_area("Remark")
                files = st.file_uploader("📸 รูปหลังซ่อม", accept_multiple_files=True)
                
                if st.form_submit_button("💾 บันทึกปิดงาน"):
                    idx = df[df['serial_number'].astype(str) == search_sn].index[-1] + 2
                    ws = ss.worksheet("sheet1")
                    t_links = upload_multiple_images(files, "TECH", search_sn)
                    t_now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    
                    # อัปเดตคอลัมน์ B, J-O และ Q
                    ws.update(f'B{idx}', [['Completed']])
                    ws.update(f'J{idx}:O{idx}', [[real_case, act_choice, class_choice, remark, st.session_state.user, t_now]])
                    ws.update(f'Q{idx}', [[t_links]])
                    st.success("บันทึกสำเร็จ!")
                    
# --- [SECTION: ADMIN] ---
elif role in ["admin", "super admin"]:
    st.header("📊 Admin Dashboard")
    df = get_clean_df("sheet1")
    if not df.empty:
        st.dataframe(df, use_container_width=True)
        # สรุปงานแยกตาม Category
        st.subheader("สถานะแยกตามประเภท")
        summary = df.groupby(['category', 'status']).size().unstack().fillna(0)
        st.bar_chart(summary)
