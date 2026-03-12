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

def upload_multiple_images(files, prefix, sn):
    urls = []
    if not files: return ""
    for i, file in enumerate(files):
        try:
            img = Image.open(file).convert('RGB')
            img.thumbnail((800, 800)) # ลดขนาดลงเล็กน้อยเพื่อความเร็ว
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=75)
            buf.seek(0)
            f_name = f"{prefix}_{sn}_{datetime.now().strftime('%H%M%S')}_{i+1}.jpg"
            f_meta = {'name': f_name, 'parents': [DRIVE_FOLDER_ID]}
            media = MediaIoBaseUpload(buf, mimetype='image/jpeg', resumable=True)
            f_drive = drive_service.files().create(body=f_meta, media_body=media, fields='webViewLink').execute()
            urls.append(f_drive.get('webViewLink'))
        except: continue
    return ",".join(urls)

# --- 3. LOGIN WITH MODE SELECTION ---
if 'is_logged_in' not in st.session_state: st.session_state.is_logged_in = False

if not st.session_state.is_logged_in:
    st.title("🛡️ Repair Management System")
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

# --- 4. PRE-LOAD DROPDOWNS (เพื่อป้องกัน NameError ในทุกหน้า) ---
# โหลดข้อมูลสถานี
df_stations = get_clean_df("station_dropdowns")
station_list = df_stations['category'].tolist() if not df_stations.empty else ["N/A"]

# โหลดข้อมูล Action และ Classification
df_actions = get_clean_df("action_dropdowns")
action_list = df_actions['category'].tolist() if not df_actions.empty else ["Repair", "Replace"]

df_class = get_clean_df("classification_dropdowns")
class_list = df_class['category'].tolist() if not df_class.empty else ["Process", "Material"]

# --- 5. INTERFACE ---
role = st.session_state.role
mode = st.session_state.app_mode

st.sidebar.info(f"👤 {st.session_state.user} | Role: {role.upper()} | Mode: {mode}")
if st.sidebar.button("Logout"):
    st.session_state.is_logged_in = False
    st.rerun()

# --- [SECTION: USER] ---
if role == "user":
    st.header(f"📋 แจ้งซ่อมใหม่ ({mode} Reporting)")
    model_sheet = "model_machine" if mode == "Machine" else "model_mat"
    df_model_source = get_clean_df(model_sheet)
    model_options = df_model_source['model'].tolist() if not df_model_source.empty else []

    with st.form("user_entry_form"):
        c1, c2 = st.columns(2)
        with c1:
            input_model = st.selectbox("Model Name", [""] + model_options)
            auto_prod = ""
            if input_model:
                m_match = df_model_source[df_model_source['model'] == input_model]
                if not m_match.empty: auto_prod = m_match.iloc[0]['product_name']
            st.text_input("Product Name (Auto)", value=auto_prod, disabled=True)
            wo = st.text_input("Work Order (WO)")
        with c2:
            sn = st.text_input("Serial Number (SN)").upper()
            station = st.selectbox("Station", station_list)
            defect = st.text_area("อาการเสีย (Defect)")
        
        user_files = st.file_uploader("📸 แนบรูปภาพประกอบ", accept_multiple_files=True)
        
        if st.form_submit_button("🚀 ส่งข้อมูลแจ้งซ่อม"):
            if input_model and sn and defect:
                with st.spinner("Saving..."):
                    img_links = upload_multiple_images(user_files, f"REQ_{mode}", sn)
                    ws = ss.worksheet("sheet1")
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    # A:Category, B:Status, C:WO, D:Model, E:P_Name, F:SN, G:Station, H:Defect, I:Time, P:Image
                    row = [mode, "Pending", wo, input_model, auto_prod, sn, station, defect, now]
                    ws.append_row(row + ([""] * 6) + [img_links])
                    st.success(f"บันทึกข้อมูล {mode} สำเร็จ!")
            else: st.warning("กรุณากรอก Model, SN และอาการเสีย")

# --- [SECTION: TECH] ---
elif role == "tech":
    st.header(f"🔧 Technician Action ({mode})")
    search_sn = st.text_input(f"🔍 Scan SN ของ {mode}").strip().upper()
    
    if search_sn:
        df = get_clean_df("sheet1")
        job = df[(df['serial_number'].astype(str) == search_sn) & 
                 (df['category'].astype(str) == mode) & 
                 (df['status'] != "Completed")].tail(1)
        
        if not job.empty:
            st.success(f"พบรายการ: {job.iloc[0]['product_name']} | อาการ: {job.iloc[0]['failure']}")
            
            with st.form("tech_action_form"):
                real_case = st.text_input("สาเหตุ (Real Case)")
                # ดึง List จากที่เราโหลดเตรียมไว้ในส่วนที่ 4
                act_choice = st.selectbox("Action", action_list)
                class_choice = st.selectbox("Classification", class_list)
                remark = st.text_area("หมายเหตุ")
                tech_files = st.file_uploader("📸 รูปหลังซ่อม", accept_multiple_files=True)
                
                if st.form_submit_button("💾 บันทึกปิดงาน"):
                    with st.spinner("Updating..."):
                        # หาแถวเพื่อ Update (Index + 2)
                        idx = df[df['serial_number'].astype(str) == search_sn].index[-1] + 2
                        ws = ss.worksheet("sheet1")
                        t_links = upload_multiple_images(tech_files, "TECH", search_sn)
                        t_now = datetime.now().strftime("%Y-%m-%d %H:%M")
                        
                        ws.update(f'B{idx}', [['Completed']])
                        # J:RealCase, K:Action, L:Class, M:Remark, N:Tech, O:Time
                        ws.update(f'J{idx}:O{idx}', [[real_case, act_choice, class_choice, remark, st.session_state.user, t_now]])
                        ws.update(f'Q{idx}', [[t_links]])
                        st.success("บันทึกการซ่อมเรียบร้อย!")
                        st.rerun()
        else:
            st.error(f"ไม่พบ SN {search_sn} ที่ค้างซ่อมในระบบ {mode}")

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
