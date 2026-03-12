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

# --- 3. LOGIN ---
if 'is_logged_in' not in st.session_state: st.session_state.is_logged_in = False

if not st.session_state.is_logged_in:
    st.title("🛡️ Repair Management System 2026")
    app_mode = st.selectbox("เลือกประเภทงาน (เฉพาะ User)", ["PCBA", "Machine"], index=0)
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

# --- 4. PRE-LOAD DROPDOWNS ---
df_actions = get_clean_df("action_dropdowns")
action_list = df_actions['category'].tolist() if not df_actions.empty else ["Repair", "Replace"]

df_class = get_clean_df("classification_dropdowns")
class_list = df_class['category'].tolist() if not df_class.empty else ["Process", "Material"]

# --- 5. INTERFACE ---
role = st.session_state.role
mode = st.session_state.app_mode

st.sidebar.info(f"👤 {st.session_state.user} | Role: {role.upper()}")
if st.sidebar.button("Logout"):
    st.session_state.is_logged_in = False
    st.rerun()

# --- [SECTION: USER] ---
if role == "user":
    # (ส่วนของ User เหมือนเดิมตาม Code ก่อนหน้า)
    st.header(f"📋 New Request ({mode})")
    # ... [โค้ดส่วน User] ...

# --- [SECTION: TECH] ---
elif role == "tech":
    st.header("🔧 Technician Action Center (Universal Scan)")
    search_sn = st.text_input("🔍 Scan Serial Number (SN) เพื่อซ่อม").strip().upper()
    
    if search_sn:
        df = get_clean_df("sheet1")
        
        # กรองข้อมูล: หา SN ล่าสุดที่ยังไม่ Completed (ไม่เช็ค Category เพื่อให้ Tech เห็นทุกอย่าง)
        job_search = df[(df['serial_number'].astype(str) == search_sn) & (df['status'] != "Completed")]
        
        if not job_search.empty:
            # เลือกรายการล่าสุดเสมอ (Latest Entry)
            job = job_search.tail(1)
            row_data = job.iloc[0]
            
            # --- SIDE-BY-SIDE LAYOUT ---
            col_info, col_form = st.columns([1, 2])
            
            with col_info:
                st.markdown("### 📋 ข้อมูลรายการ")
                st.success(f"**SN:** {row_data['serial_number']}")
                st.info(f"**Work Order:** {row_data['work_order']}")
                st.warning(f"**Category:** {row_data['category']}")
                st.write(f"**Model:** {row_data['model']}")
                st.write(f"**Product:** {row_data['product_name']}")
                st.error(f"**อาการเสีย:** {row_data['failure']}")
                
                # แสดงรูปจาก User (ถ้ามี)
                if row_data.get('user_image'):
                    st.write("🖼️ รูปจาก User:")
                    for img_url in str(row_data['user_image']).split(','):
                        if img_url: st.image(img_url, use_container_width=True)

            with col_form:
                st.markdown("### 🛠️ บันทึกการซ่อม")
                with st.form("tech_action_form"):
                    real_case = st.text_input("สาเหตุ (Real Case)")
                    act_choice = st.selectbox("Action", action_list)
                    class_choice = st.selectbox("Classification", class_list)
                    remark = st.text_area("หมายเหตุ")
                    tech_files = st.file_uploader("📸 รูปหลังซ่อม", accept_multiple_files=True)
                    
                    if st.form_submit_button("💾 บันทึกปิดงาน"):
                        with st.spinner("กำลังอัปเดตข้อมูล..."):
                            # หา Index จริงจากต้นฉบับ (ป้องกันการเลื่อนบรรทัด)
                            idx = job.index[-1] + 2
                            ws = ss.worksheet("sheet1")
                            t_links = upload_multiple_images(tech_files, "TECH", search_sn)
                            t_now = datetime.now().strftime("%Y-%m-%d %H:%M")
                            
                            # อัปเดตสถานะและข้อมูลซ่อม
                            ws.update(f'B{idx}', [['Completed']])
                            ws.update(f'J{idx}:O{idx}', [[real_case, act_choice, class_choice, remark, st.session_state.user, t_now]])
                            ws.update(f'Q{idx}', [[t_links]])
                            
                            st.success(f"ปิดงาน WO: {row_data['work_order']} เรียบร้อย!")
                            st.balloons()
                            # ไม่ต้อง rerun ทันทีเพื่อให้ช่างดูผลลัพธ์แวบหนึ่ง หรือจะใส่ st.rerun() ก็ได้
        else:
            st.error(f"❌ ไม่พบ SN: {search_sn} ที่ค้างซ่อมในระบบ")

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
