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
        # Clean column names to lowercase and replace spaces with underscores
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
            f_drive = drive_service.files().create(body=f_meta, media_body=media, fields='webViewLink').execute()
            if f_drive: urls.append(f_drive.get('webViewLink'))
        except: continue
    return ",".join(urls)

# --- 3. LOGIN ---
if 'is_logged_in' not in st.session_state: st.session_state.is_logged_in = False
if not st.session_state.is_logged_in:
    st.title("🛠️ Repair Multi-System 2026")
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
    st.header("📋 แจ้งซ่อมใหม่ (User Reporting)")
    category = st.radio("ประเภทงาน", ["PCBA", "Machine"], horizontal=True)

    df_master = get_clean_df("model_mat")
    model_list = df_master['model'].tolist() if not df_master.empty else []

    with st.form("user_entry_form"):
        c1, c2 = st.columns(2)
        with c1:
            input_model = st.selectbox("Model Name", [""] + model_list)
            auto_prod = ""
            if input_model and not df_master.empty:
                match = df_master[df_master['model'] == input_model]
                if not match.empty: auto_prod = match.iloc[0]['product_name']
            
            product_name = st.text_input("Product Name (Auto)", value=auto_prod, disabled=True)
            wo = st.text_input("Work Order (WO)")
            
        with c2:
            sn = st.text_input("Serial Number (SN)").upper()
            st_list = ["SMT", "DIP", "FCT", "Packing"] if category == "PCBA" else ["Production Line", "Utility"]
            station = st.selectbox("Station", st_list)
            defect = st.text_area("อาการเสีย (Defect)")
        
        user_files = st.file_uploader("📸 แนบรูปภาพประกอบ", accept_multiple_files=True)
        
        if st.form_submit_button("🚀 ส่งข้อมูลแจ้งซ่อม"):
            if input_model and sn and defect:
                with st.spinner("Recording..."):
                    img_links = upload_multiple_images(user_files, f"REQ_{category}", sn)
                    ws = ss.worksheet("sheet1")
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    # Match headers in image_3c8322.png
                    row = [category, "Pending", wo, input_model, auto_prod, sn, station, defect, now]
                    ws.append_row(row + ([""] * 6) + [img_links])
                    st.success("แจ้งซ่อมสำเร็จ!")
            else: st.warning("กรุณากรอกข้อมูลให้ครบถ้วน")

# --- [SECTION: TECH] ---
elif role == "tech":
    st.header("🔧 Technician Action Center")
    view_mode = st.radio("ดูคิวงานประเภท:", ["PCBA", "Machine"], horizontal=True)
    
    # Dropdown data from action_dropdowns sheet
    df_actions = get_clean_df("action_dropdowns")
    action_list = df_actions['category'].tolist() if not df_actions.empty else ["Rework", "Replace", "Cleaned"]

    search_sn = st.text_input(f"🔍 Scan SN ({view_mode}) เพื่อซ่อม").strip().upper()
    if search_sn:
        df = get_clean_df("sheet1")
        # Filter matching SN, Category, and Status
        job = df[(df['serial_number'].astype(str) == search_sn) & 
                 (df['category'].astype(str) == view_mode) & 
                 (df['status'] != "Completed")].tail(1)
        
        if not job.empty:
            st.success(f"พบรายการ: {job.iloc[0]['product_name']} (Model: {job.iloc[0]['model']})")
            
            with st.form("tech_action_form"):
                real_case = st.text_input("สาเหตุ (Real Case)")
                # Use dropdown from Sheet action_dropdowns
                action_choice = st.selectbox("วิธีแก้ไข (Action)", action_list)
                remark = st.text_area("หมายเหตุ")
                tech_files = st.file_uploader("📸 รูปหลังซ่อม", accept_multiple_files=True)
                
                if st.form_submit_button("💾 ปิดงานซ่อม"):
                    idx = df[df['serial_number'].astype(str) == search_sn].index[-1] + 2
                    ws = ss.worksheet("sheet1")
                    t_links = upload_multiple_images(tech_files, "TECH", search_sn)
                    t_now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    
                    # Update Columns B(Status), J-O(Details), Q(Image) based on image_3c8322.png
                    ws.update(f'B{idx}', [['Completed']])
                    ws.update(f'J{idx}:O{idx}', [[real_case, action_choice, view_mode, remark, st.session_state.user, t_now]])
                    ws.update(f'Q{idx}', [[t_links]])
                    st.success("บันทึกปิดงานเรียบร้อย!")
        else:
            st.error(f"ไม่พบ SN นี้ในหมวด {view_mode} ที่ค้างอยู่")
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
