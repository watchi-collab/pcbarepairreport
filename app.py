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
            img.thumbnail((1000, 1000))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            buf.seek(0)
            f_name = f"{prefix}_{sn}_{datetime.now().strftime('%H%M%S')}_{i+1}.jpg"
            f_meta = {'name': f_name, 'parents': [DRIVE_FOLDER_ID]}
            media = MediaIoBaseUpload(buf, mimetype='image/jpeg', resumable=True)
            f_drive = drive_service.files().create(body=f_meta, media_body=media, fields='webViewLink').execute()
            urls.append(file_drive.get('webViewLink'))
        except: continue
    return ",".join(urls)

# --- 3. LOGIN ---
if 'is_logged_in' not in st.session_state: st.session_state.is_logged_in = False
if not st.session_state.is_logged_in:
    st.title("🛠️ Repair System 2026 (Smart Mapping)")
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

    # ดึงข้อมูล Master Model
    df_master = get_clean_df("model_mat")
    model_list = df_master['model'].tolist() if not df_master.empty else []

    with st.form("user_entry_form"):
        c1, c2 = st.columns(2)
        with c1:
            # ใช้ Selectbox หรือ Text input ที่ตรวจสอบ Model
            input_model = st.selectbox("Select Model", [""] + model_list)
            
            # Smart Mapping: ค้นหา Product Name จาก Model ที่เลือก
            auto_prod = ""
            if input_model:
                match_prod = df_master[df_master['model'] == input_model]['product_name']
                if not match_prod.empty:
                    auto_prod = match_prod.iloc[0]
            
            # แสดงค่าที่ผูกกัน (Disabled ให้ User ดูอย่างเดียว หรือ Text Input ปกติ)
            product_name = st.text_input("Product Name (Auto-fill)", value=auto_prod)
            wo = st.text_input("Work Order (WO)")
            
        with c2:
            sn = st.text_input("Serial Number (SN)").upper()
            station = st.selectbox("Station", ["SMT", "DIP", "FCT", "Main Line", "Maintenance"])
            defect = st.text_area("Defect Detail")
        
        user_files = st.file_uploader("📸 Upload Photos", accept_multiple_files=True)
        
        if st.form_submit_button("🚀 Submit Request"):
            if input_model and sn and defect:
                with st.spinner("Saving..."):
                    img_links = upload_multiple_images(user_files, f"REQ_{category}", sn)
                    ws = ss.worksheet("sheet1")
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    # คอลัมน์ A:category, B:status, C:wo, D:model, E:product_name, F:sn, G:station, H:failure, I:time
                    row = [category, "Pending", wo, input_model, product_name, sn, station, defect, now]
                    ws.append_row(row + ([""] * 6) + [img_links])
                    st.success("บันทึกข้อมูลเรียบร้อย!")
            else: st.warning("Please fill required fields (Model, SN, Defect)")

# --- [SECTION: TECH] ---
elif role == "tech":
    st.header("🔧 Technician Action Center")
    # Tech เลือกกรองดูงานตามความถนัด
    view_mode = st.radio("ดูคิวงานประเภท:", ["PCBA", "Machine"], horizontal=True)
    
    search_sn = st.text_input(f"🔍 Scan SN ({view_mode}) เพื่อซ่อม").strip().upper()
    if search_sn:
        df = get_clean_df("sheet1")
        # กรองงานที่ตรงทั้ง SN และ Category และยังไม่เสร็จ
        job = df[(df['serial_number'].astype(str) == search_sn) & 
                 (df['category'].astype(str) == view_mode) & 
                 (df['status'] != "Completed")].tail(1)
        
        if not job.empty:
            st.success(f"พบงาน {view_mode}: {job.iloc[0]['work_order']}")
            if job.iloc[0].get('user_image'):
                st.write("🖼️ รูปจาก User:")
                links = str(job.iloc[0]['user_image']).split(",")
                cols = st.columns(4)
                for idx, lnk in enumerate(links):
                    if lnk: cols[idx % 4].image(lnk, use_container_width=True)

            with st.form("tech_action_form"):
                real_case = st.text_input("สาเหตุ (Real Case)")
                action = st.text_input("วิธีแก้ไข (Action)")
                remark = st.text_area("หมายเหตุ")
                tech_files = st.file_uploader("📸 รูปหลังซ่อม", type=['jpg','png'], accept_multiple_files=True)
                
                if st.form_submit_button("💾 ปิดงานซ่อม"):
                    idx = df[df['serial_number'].astype(str) == search_sn].index[-1] + 2
                    ws = ss.worksheet("sheet1")
                    t_links = upload_multiple_images(tech_files, "TECH", search_sn)
                    t_now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    
                    ws.update(f'B{idx}', [['Completed']])
                    # อัปเดตข้อมูลซ่อม J-O และ Q
                    ws.update(f'J{idx}:O{idx}', [[real_case, action, view_mode, remark, st.session_state.user, t_now]])
                    ws.update(f'Q{idx}', [[t_links]])
                    st.success("บันทึกปิดงานเรียบร้อย!")
        else:
            st.error(f"ไม่พบ SN นี้ในหมวด {view_mode} ที่ค้างอยู่")
# --- [SECTION: ADMIN] ---
elif role in ["admin", "super admin"]:
    st.header("📊 Admin Dashboard")
    df = get_clean_df("sheet1")
    
    if not df.empty:
        # ส่วนแสดงตารางพร้อม Filter
        st.subheader("รายการซ่อมทั้งหมด")
        st.dataframe(df, use_container_width=True)
        
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart({"data": [{"values": df['status'].value_counts(), "labels": df['status'].value_counts().index, "type": "pie"}]}) if 'status' in df else st.write("No status data")
        with c2:
            csv = df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 Download Report (CSV)", data=csv, file_name=f"Report_{datetime.now().strftime('%Y%m%d')}.csv")
