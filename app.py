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
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return None, None, False

ss, drive_service, conn_status = init_all()

# --- 2. HELPERS ---
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
            img.thumbnail((1000, 1000))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            buf.seek(0)
            f_name = f"{prefix}_{sn}_{datetime.now().strftime('%H%M%S')}_{i+1}.jpg"
            f_meta = {'name': f_name, 'parents': [DRIVE_FOLDER_ID]}
            media = MediaIoBaseUpload(buf, mimetype='image/jpeg', resumable=True)
            file_drive = drive_service.files().create(body=f_meta, media_body=media, fields='webViewLink').execute()
            if file_drive:
                urls.append(file_drive.get('webViewLink'))
        except: continue
    return ",".join(urls)

# --- 3. LOGIN ---
if 'is_logged_in' not in st.session_state: st.session_state.is_logged_in = False
if not st.session_state.is_logged_in:
    st.title("🛠️ Repair System 2026")
    with st.form("auth_form"):
        u = st.text_input("Username").strip()
        p = st.text_input("Password", type="password").strip()
        if st.form_submit_button("Sign In"):
            df_u = get_clean_df("users")
            match = df_u[(df_u['username'].astype(str) == u) & (df_u['password'].astype(str) == p)]
            if not match.empty:
                st.session_state.update({"is_logged_in": True, "user": u, "role": match.iloc[0]['role'].lower()})
                st.rerun()
            else: st.error("Login Failed")
    st.stop()

# --- 4. INTERFACE ---
role = st.session_state.role
st.sidebar.info(f"👤 {st.session_state.user} | Role: {role.upper()}")
if st.sidebar.button("Logout"):
    st.session_state.is_logged_in = False
    st.rerun()

# --- [SECTION: USER] ---
if role == "user":
    st.header("📋 New Repair Ticket")
    category = st.radio("Category", ["PCBA", "Machine"], horizontal=True)

    # Smart Mapping Logic
    df_master = get_clean_df("model_mat")
    model_list = df_master['model'].tolist() if not df_master.empty else []

    with st.form("user_entry_form"):
        c1, c2 = st.columns(2)
        with c1:
            input_model = st.selectbox("Select Model", [""] + model_list)
            # ดึงค่า Product Name มาแสดง
            auto_prod = ""
            if input_model and not df_master.empty:
                match = df_master[df_master['model'] == input_model]
                if not match.empty:
                    auto_prod = match.iloc[0]['product_name']
            
            product_name = st.text_input("Product Name (Auto)", value=auto_prod, disabled=True)
            wo = st.text_input("Work Order (WO)")
            
        with c2:
            sn = st.text_input("Serial Number (SN)").upper()
            # ปรับ Station ตามหมวดหมู่
            st_list = ["SMT", "DIP", "FCT"] if category == "PCBA" else ["Line 1", "Line 2", "Utility"]
            station = st.selectbox("Station", st_list)
            defect = st.text_area("Defect Detail")
        
        user_files = st.file_uploader("📸 Upload Photos (Multiple)", accept_multiple_files=True)
        
        if st.form_submit_button("🚀 Submit Request"):
            if input_model and sn and defect:
                with st.spinner("Recording data and images..."):
                    img_links = upload_multiple_images(user_files, f"REQ_{category}", sn)
                    ws = ss.worksheet("sheet1")
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    # คอลัมน์ A-I
                    row = [category, "Pending", wo, input_model, auto_prod, sn, station, defect, now]
                    # เพิ่มช่องว่างสำหรับ J-O แล้วใส่รูปที่ P
                    ws.append_row(row + ([""] * 6) + [img_links])
                    st.success("แจ้งซ่อมสำเร็จ!")
            else: st.warning("Please fill Model, SN, and Defect")

# --- [SECTION: TECH] ---
elif role == "tech":
    st.header("🔧 Technician Action Center")
    view_mode = st.radio("ประเภทงาน:", ["PCBA", "Machine"], horizontal=True)
    search_sn = st.text_input(f"🔍 Scan SN ({view_mode})").strip().upper()
    
    if search_sn:
        df = get_clean_df("sheet1")
        # กรองงาน (ใช้ชื่อคอลัมน์ที่ถูก clean แล้ว)
        job = df[(df['serial_number'].astype(str) == search_sn) & 
                 (df['category'].astype(str) == view_mode) & 
                 (df['status'] != "Completed")].tail(1)
        
        if not job.empty:
            st.success(f"พบรายการ: {job.iloc[0]['product_name']} (Model: {job.iloc[0]['model']})")
            
            # Gallery Preview
            if job.iloc[0].get('user_image'):
                links = str(job.iloc[0]['user_image']).split(",")
                st.write("🖼️ ภาพจาก User:")
                cols = st.columns(min(len(links), 4))
                for idx, lnk in enumerate(links):
                    if lnk: cols[idx % 4].image(lnk, use_container_width=True)

            with st.form("tech_form"):
                real_case = st.text_input("Real Case")
                action = st.text_input("Action")
                remark = st.text_area("Remark")
                tech_files = st.file_uploader("📸 รูปหลังซ่อม", accept_multiple_files=True)
                
                if st.form_submit_button("💾 บันทึกปิดงาน"):
                    with st.spinner("Updating..."):
                        # หาเลขแถว (+2 เพราะ index เริ่ม 0 และ Sheet มี Header)
                        idx = df[df['serial_number'].astype(str) == search_sn].index[-1] + 2
                        ws = ss.worksheet("sheet1")
                        t_links = upload_multiple_images(tech_files, "TECH", search_sn)
                        t_now = datetime.now().strftime("%Y-%m-%d %H:%M")
                        
                        ws.update(f'B{idx}', [['Completed']])
                        ws.update(f'J{idx}:O{idx}', [[real_case, action, view_mode, remark, st.session_state.user, t_now]])
                        ws.update(f'Q{idx}', [[t_links]])
                        st.success("ปิดงานซ่อมเรียบร้อย!")
        else:
            st.error(f"ไม่พบ SN: {search_sn} ในหมวด {view_mode} ที่ยังไม่ซ่อม")

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
