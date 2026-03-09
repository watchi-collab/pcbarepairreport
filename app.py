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

# --- 2. MULTI-IMAGE HELPER ---
def upload_multiple_images(files, prefix, sn):
    """อัปโหลดหลายรูปและคืนค่าเป็น String ของ URL คั่นด้วยคอมมา"""
    urls = []
    if not files: return ""
    
    for i, file in enumerate(files):
        try:
            img = Image.open(file).convert('RGB')
            img.thumbnail((1200, 1200))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80) # ลดคุณภาพเล็กน้อยเพื่อความเร็ว
            buf.seek(0)
            
            file_name = f"{prefix}_{sn}_{datetime.now().strftime('%H%M%S')}_{i+1}.jpg"
            file_metadata = {'name': file_name, 'parents': [DRIVE_FOLDER_ID]}
            media = MediaIoBaseUpload(buf, mimetype='image/jpeg', resumable=True)
            file_drive = drive_service.files().create(body=file_metadata, media_body=media, fields='webViewLink').execute()
            urls.append(file_drive.get('webViewLink'))
        except: continue
    
    return ",".join(urls) # รวมทุก Link เข้าด้วยกัน

def get_clean_df(sheet_name):
    try:
        ws = ss.worksheet(sheet_name)
        df = pd.DataFrame(ws.get_all_records())
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        return df.fillna("")
    except: return pd.DataFrame()

# --- 3. LOGIN ---
if 'login' not in st.session_state: st.session_state.login = False
if not st.session_state.login:
    st.title("📸 Repair System (Multi-Image Support)")
    with st.form("login"):
        u = st.text_input("User")
        p = st.text_input("Pass", type="password")
        if st.form_submit_button("Login"):
            df_u = get_clean_df("users")
            match = df_u[(df_u['username'].astype(str) == u) & (df_u['password'].astype(str) == p)]
            if not match.empty:
                st.session_state.update({"login": True, "user": u, "role": match.iloc[0]['role'].lower()})
                st.rerun()
    st.stop()

# --- 4. INTERFACE ---
role = st.session_state.role
st.sidebar.info(f"User: {st.session_state.user} | Role: {role.upper()}")
if st.sidebar.button("Logout"):
    st.session_state.login = False
    st.rerun()

# --- [USER SECTION] ---
if role == "user":
    st.header("📋 แจ้งซ่อมพร้อมแนบรูป (สูงสุด 5 รูป)")
    
    with st.form("user_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            wo = st.text_input("Work Order")
            model = st.text_input("Model")
            prod = st.text_input("Product Name")
        with c2:
            sn = st.text_input("Serial Number")
            station = st.selectbox("Station", ["SMT", "DIP", "FCT"])
            defect = st.text_area("Defect Detail")
        
        # แนบได้หลายรูป
        user_files = st.file_uploader("📸 เลือกรูปภาพอาการเสีย (แนบได้หลายรูป)", type=['jpg','jpeg','png'], accept_multiple_files=True)
        
        if st.form_submit_button("🚀 ส่งข้อมูล"):
            if wo and sn and defect:
                with st.spinner("กำลังอัปโหลดรูปภาพทั้งหมด..."):
                    all_urls = upload_multiple_images(user_files, "USER", sn)
                    ws = ss.worksheet("sheet1")
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    # คอลัมน์ A-I + P(user_image)
                    row = [st.session_state.user, "Pending", wo, model, prod, sn, station, defect, now]
                    ws.append_row(row + ([""] * 6) + [all_urls])
                    st.success(f"บันทึกข้อมูลและอัปโหลด {len(user_files)} รูปเรียบร้อย!")

# --- [TECH SECTION] ---
elif role == "tech":
    st.header("🔧 บันทึกการซ่อม")
    search_sn = st.text_input("🔍 Scan SN").strip().upper()
    
    if search_sn:
        df = get_clean_df("sheet1")
        job = df[(df['serial_number'].astype(str) == search_sn) & (df['status'] != "Completed")].tail(1)
        
        if not job.empty:
            # แสดงรูปทั้งหมดจาก User
            if job.iloc[0].get('user_image'):
                st.write("**รูปภาพจาก User:**")
                img_list = job.iloc[0]['user_image'].split(",")
                cols = st.columns(len(img_list))
                for i, url in enumerate(img_list):
                    cols[i].image(url, use_container_width=True)
            
            with st.form("tech_form"):
                real_case = st.text_input("Real Case")
                action = st.text_input("Action")
                remark = st.text_area("Remark")
                tech_files = st.file_uploader("📸 รูปหลังการซ่อม (แนบได้หลายรูป)", type=['jpg','jpeg','png'], accept_multiple_files=True)
                
                if st.form_submit_button("💾 ปิดงาน"):
                    idx = df[df['serial_number'].astype(str) == search_sn].index[-1] + 2
                    ws = ss.worksheet("sheet1")
                    tech_urls = upload_multiple_images(tech_files, "TECH", search_sn)
                    now_tech = datetime.now().strftime("%Y-%m-%d %H:%M")
                    
                    ws.update(f'B{idx}', [['Completed']])
                    ws.update(f'J{idx}:O{idx}', [[real_case, action, "Repair", remark, st.session_state.user, now_tech]])
                    ws.update(f'Q{idx}', [[tech_urls]])
                    st.success("บันทึกสำเร็จ!")

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
