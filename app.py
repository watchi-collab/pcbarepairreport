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
            img.thumbnail((800, 800))
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

# --- 3. LOGIN & DROPDOWNS ---
if 'is_logged_in' not in st.session_state: st.session_state.is_logged_in = False
if not st.session_state.is_logged_in:
    st.title("🛡️ Repair Management System")
    app_mode = st.selectbox("โหมดเริ่มต้น (สำหรับ User)", ["PCBA", "Machine"])
    with st.form("login_form"):
        u = st.text_input("Username").strip()
        p = st.text_input("Password", type="password").strip()
        if st.form_submit_button("Login"):
            df_u = get_clean_df("users")
            match = df_u[(df_u['username'].astype(str) == u) & (df_u['password'].astype(str) == p)]
            if not match.empty:
                st.session_state.update({"is_logged_in": True, "user": u, "role": match.iloc[0]['role'].lower(), "app_mode": app_mode})
                st.rerun()
            else: st.error("Login Failed")
    st.stop()

# โหลดข้อมูลตัวเลือก
df_actions = get_clean_df("action_dropdowns")
action_list = df_actions['category'].tolist() if not df_actions.empty else ["N/A"]
df_class = get_clean_df("classification_dropdowns")
class_list = df_class['category'].tolist() if not df_class.empty else ["N/A"]

# --- 4. INTERFACE ---
role = st.session_state.role
st.sidebar.info(f"👤 {st.session_state.user} | Role: {role.upper()}")
if st.sidebar.button("Logout"):
    st.session_state.is_logged_in = False
    st.rerun()

# --- [SECTION: TECH] ---
if role == "tech":
    st.header("🔧 Technician Action Center (Universal Scan)")
    search_sn = st.text_input("🔍 Scan Serial Number (SN) เพื่อซ่อม").strip().upper()
    
    if search_sn:
        df_all = get_clean_df("sheet1")
        
        # กรองงานปัจจุบันที่ค้างซ่อม (Pending)
        active_jobs = df_all[(df_all['serial_number'].astype(str) == search_sn) & (df_all['status'] != "Completed")]
        
        # ประวัติการซ่อมเก่า (History)
        history_df = df_all[(df_all['serial_number'].astype(str) == search_sn) & (df_all['status'] == "Completed")]

        if not active_jobs.empty:
            job = active_jobs.tail(1) # เลือกรายการล่าสุด
            row_data = job.iloc[0]
            
            col_info, col_form = st.columns([1, 1.2])
            
            with col_info:
                st.subheader("📋 ข้อมูลงานปัจจุบัน")
                st.success(f"**SN:** {row_data['serial_number']}")
                st.info(f"**Work Order:** {row_data['work_order']}")
                st.warning(f"**หมวดหมู่:** {row_data['category']}")
                st.write(f"**อาการเสีย:** {row_data['failure']}")
                
                if row_data.get('user_image'):
                    st.write("🖼️ รูปจาก User:")
                    for img in str(row_data['user_image']).split(','):
                        if img: st.image(img, use_container_width=True)

            with col_form:
                st.subheader("🛠️ บันทึกการแก้ไข")
                with st.form("tech_repair_form"):
                    real_case = st.text_input("Real Case (สาเหตุ)")
                    act_choice = st.selectbox("Action (วิธีแก้)", action_list)
                    class_choice = st.selectbox("Classification", class_list)
                    remark = st.text_area("Remark")
                    tech_files = st.file_uploader("📸 รูปหลังซ่อม", accept_multiple_files=True)
                    
                    if st.form_submit_button("💾 บันทึกและปิดงาน"):
                        idx = job.index[-1] + 2
                        ws = ss.worksheet("sheet1")
                        t_links = upload_multiple_images(tech_files, "TECH", search_sn)
                        t_now = datetime.now().strftime("%Y-%m-%d %H:%M")
                        
                        ws.update(f'B{idx}', [['Completed']])
                        ws.update(f'J{idx}:O{idx}', [[real_case, act_choice, class_choice, remark, st.session_state.user, t_now]])
                        ws.update(f'Q{idx}', [[t_links]])
                        st.success(f"ปิดงานสำเร็จ!")
                        st.rerun()
            
            # --- SHOW HISTORY BELOW FORM ---
            st.divider()
            st.subheader("🕒 ประวัติการซ่อมเก่า (Repair History)")
            if not history_df.empty:
                # เลือกเฉพาะคอลัมน์ที่สำคัญมาโชว์
                display_cols = ['user_time', 'failure', 'real_case', 'action', 'tech_id', 'tech_time']
                st.table(history_df[display_cols].sort_values(by='tech_time', ascending=False))
            else:
                st.info("เครื่องนี้ยังไม่เคยมีประวัติการซ่อมในระบบ")
        else:
            st.error(f"❌ ไม่พบ SN: {search_sn} ที่ค้างซ่อม")
            # ถ้าไม่เจองานค้างซ่อม แต่อยากดูประวัติเก่า ก็โชว์ให้ดูได้
            if not history_df.empty:
                st.subheader("🕒 ประวัติการซ่อมเก่า (ค้นพบเฉพาะรายการที่ปิดงานแล้ว)")
                st.table(history_df[['user_time', 'failure', 'action', 'tech_id']].sort_values(by='user_time', ascending=False))

# --- [SECTION: USER] ---
elif role == "user":
    st.header(f"📋 แจ้งซ่อมใหม่ ({st.session_state.app_mode})")
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
