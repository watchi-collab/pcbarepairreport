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
            img.thumbnail((1000, 1000))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            buf.seek(0)
            file_name = f"{prefix}_{sn}_{datetime.now().strftime('%H%M%S')}_{i+1}.jpg"
            file_metadata = {'name': file_name, 'parents': [DRIVE_FOLDER_ID]}
            media = MediaIoBaseUpload(buf, mimetype='image/jpeg', resumable=True)
            file_drive = drive_service.files().create(body=file_metadata, media_body=media, fields='webViewLink').execute()
            urls.append(file_drive.get('webViewLink'))
        except: continue
    return ",".join(urls)

def get_clean_df(sheet_name):
    try:
        ws = ss.worksheet(sheet_name)
        df = pd.DataFrame(ws.get_all_records())
        # ทำความสะอาดหัวคอลัมน์ให้เป็นตัวเล็กและไม่มีช่องว่าง
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        return df.fillna("")
    except: return pd.DataFrame()

# --- 3. LOGIN (Fixed Key Conflict) ---
if 'is_logged_in' not in st.session_state: 
    st.session_state.is_logged_in = False

if not st.session_state.is_logged_in:
    st.title("📸 Repair System (Multi-Image)")
    # เปลี่ยนชื่อฟอร์มเพื่อไม่ให้ซ้ำกับ session state key
    with st.form("auth_form"):
        u = st.text_input("Username").strip()
        p = st.text_input("Password", type="password").strip()
        if st.form_submit_button("เข้าสู่ระบบ"):
            df_u = get_clean_df("users")
            if not df_u.empty:
                match = df_u[(df_u['username'].astype(str) == u) & (df_u['password'].astype(str) == p)]
                if not match.empty:
                    st.session_state.update({
                        "is_logged_in": True, 
                        "user": u, 
                        "role": match.iloc[0]['role'].lower()
                    })
                    st.rerun()
                else: st.error("ID หรือ Password ไม่ถูกต้อง")
    st.stop()

# --- 4. INTERFACE ---
role = st.session_state.role
st.sidebar.info(f"👤 {st.session_state.user} | Role: {role.upper()}")
if st.sidebar.button("Log out"):
    st.session_state.is_logged_in = False
    st.rerun()

# --- [SECTION: USER] ---
if role == "user":
    st.header("📋 แจ้งซ่อมพร้อมแนบรูป")
    with st.form("user_entry_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            wo = st.text_input("Work Order")
            model = st.text_input("Model")
            prod = st.text_input("Product Name")
        with c2:
            sn = st.text_input("Serial Number").upper()
            station = st.selectbox("Station", ["SMT", "DIP", "FCT", "Packing"])
            defect = st.text_area("Defect Detail")
        
        user_files = st.file_uploader("📸 แนบรูปภาพ (หลายรูป)", type=['jpg','jpeg','png'], accept_multiple_files=True)
        
        if st.form_submit_button("🚀 ส่งข้อมูลแจ้งซ่อม"):
            if wo and sn and defect:
                with st.spinner("กำลังประมวลผลรูปภาพ..."):
                    img_links = upload_multiple_images(user_files, "USER", sn)
                    ws = ss.worksheet("sheet1")
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    # แถวข้อมูล A-I
                    row = [st.session_state.user, "Pending", wo, model, prod, sn, station, defect, now]
                    # เพิ่มช่องว่างสำหรับ J-O แล้วใส่ Link รูปที่คอลัมน์ P
                    ws.append_row(row + ([""] * 6) + [img_links])
                    st.success(f"บันทึกข้อมูลและอัปโหลด {len(user_files)} รูปเรียบร้อย!")
            else: st.warning("กรุณากรอกข้อมูลให้ครบถ้วน")

# --- [SECTION: TECH] ---
elif role == "tech":
    st.header("🔧 บันทึกการซ่อม (Technician)")
    search_sn = st.text_input("🔍 Scan Serial Number (SN)").strip().upper()
    
    if search_sn:
        df = get_clean_df("sheet1")
        # ค้นหางานล่าสุดที่ยัง Pending ของ SN นี้
        job = df[(df['serial_number'].astype(str) == search_sn) & (df['status'] != "Completed")].tail(1)
        
        if not job.empty:
            st.info(f"Found Job: {job.iloc[0]['work_order']} | Defect: {job.iloc[0]['failure']}")
            
            # แสดงรูปจาก User แบบ Gallery
            if job.iloc[0].get('user_image'):
                links = str(job.iloc[0]['user_image']).split(",")
                st.write("**🖼️ รูปภาพจาก User:**")
                cols = st.columns(4)
                for idx, lnk in enumerate(links):
                    if lnk: cols[idx % 4].image(lnk, use_container_width=True)
            
            with st.form("tech_action_form"):
                c1, c2 = st.columns(2)
                with c1:
                    real_case = st.text_input("Real Case")
                    action = st.text_input("Action")
                with c2:
                    remark = st.text_area("Remark")
                    tech_files = st.file_uploader("📸 รูปหลังซ่อม (หลายรูป)", type=['jpg','png'], accept_multiple_files=True)
                
                if st.form_submit_button("💾 บันทึกและปิดงาน"):
                    with st.spinner("กำลังอัปเดตข้อมูล..."):
                        idx = df[df['serial_number'].astype(str) == search_sn].index[-1] + 2
                        ws = ss.worksheet("sheet1")
                        t_links = upload_multiple_images(tech_files, "TECH", search_sn)
                        t_now = datetime.now().strftime("%Y-%m-%d %H:%M")
                        
                        # อัปเดตสถานะ (B) และข้อมูลซ่อม J-O, Q
                        ws.update(f'B{idx}', [['Completed']])
                        # J:real_case, K:action, L:class, M:remark, N:tech_id, O:tech_time
                        ws.update(f'J{idx}:O{idx}', [[real_case, action, "Fixed", remark, st.session_state.user, t_now]])
                        ws.update(f'Q{idx}', [[t_links]])
                        st.success("บันทึกผลการซ่อมสำเร็จ!")
        else: st.error("ไม่พบข้อมูล SN นี้ที่ค้างซ่อม")

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
