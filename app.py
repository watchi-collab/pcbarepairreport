# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import time
from datetime import datetime
from PIL import Image
import plotly.express as px

# --- CONFIGURATION (จุดบันทึกรูปภาพตามที่คุณระบุ) ---
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

# --- 3. LOGIN & GLOBAL DATA ---
if 'is_logged_in' not in st.session_state: st.session_state.is_logged_in = False

if not st.session_state.is_logged_in:
    st.title("🛡️ Repair Management System")
    app_mode_init = st.selectbox("โหมดสำหรับ User", ["PCBA", "Machine"])
    with st.form("login_form"):
        u = st.text_input("Username").strip()
        p = st.text_input("Password", type="password").strip()
        if st.form_submit_button("Login"):
            df_u = get_clean_df("users")
            match = df_u[(df_u['username'].astype(str) == u) & (df_u['password'].astype(str) == p)]
            if not match.empty:
                st.session_state.update({"is_logged_in": True, "user": u, "role": match.iloc[0]['role'].lower(), "app_mode": app_mode_init})
                st.rerun()
            else: st.error("Login Failed")
    st.stop()

df_stations = get_clean_df("station_dropdowns")
station_list = df_stations['category'].tolist() if not df_stations.empty else ["General"]
df_actions = get_clean_df("action_dropdowns")
action_list = df_actions['category'].tolist() if not df_actions.empty else ["Repair", "Replace"]

# --- 4. INTERFACE ---
role = st.session_state.role
current_mode = st.session_state.app_mode
st.sidebar.info(f"👤 {st.session_state.user} | Role: {role.upper()}")
if st.sidebar.button("Logout"):
    st.session_state.is_logged_in = False
    st.rerun()

# --- [SECTION: TECH] ---
if role == "tech":
    st.header("🔧 Technician Center")
    search_sn = st.text_input("🔍 สแกน SN เพื่อค้นหางาน").strip().upper()
    
    if search_sn:
        df_all = get_clean_df("sheet1")
        active_jobs = df_all[(df_all['serial_number'].astype(str) == search_sn) & (df_all['status'] == "Pending")]
        history_df = df_all[(df_all['serial_number'].astype(str) == search_sn) & (df_all['status'] != "Pending")]

        if not active_jobs.empty:
            job = active_jobs.tail(1)
            row_data = job.iloc[0]
            
            c1, c2 = st.columns([1, 1.2])
            with c1:
                st.subheader("📋 ข้อมูลงาน")
                st.info(f"**Product:** {row_data['product_name']}\n\n**Model:** {row_data['model']}")
                st.error(f"**อาการเสีย:** {row_data['failure']}")
                
                # แสดงรูปที่ User แนบมา (ถ้ามี)
                if 'user_image' in row_data and row_data['user_image']:
                    st.write("🖼️ **รูปจาก User:**")
                    for img_url in str(row_data['user_image']).split(','):
                        if img_url: st.image(img_url.strip(), use_container_width=True)

            with c2:
                st.subheader("🛠️ บันทึกผล")
                with st.form("tech_form"):
                    new_status = st.radio("สถานะงาน:", ["Complate", "Scrap"], horizontal=True)
                    real_case = st.text_input("Real Case")
                    act_choice = st.selectbox("Action", action_list)
                    remark = st.text_area("Remark")
                    t_files = st.file_uploader("📸 รูปประกอบหลังซ่อม", accept_multiple_files=True)
                    
                    if st.form_submit_button("💾 บันทึกปิดงาน"):
                        with st.spinner("กำลังส่งรูปไปที่ Google Drive..."):
                            idx = job.index[-1] + 2
                            ws = ss.worksheet("sheet1")
                            t_links = upload_multiple_images(t_files, "TECH", search_sn)
                            t_now = datetime.now().strftime("%Y-%m-%d %H:%M")
                            
                            # อัปเดต Column B(2), J-O(10-15), Q(17)
                            ws.update(f'B{idx}', [[new_status]])
                            ws.update(f'J{idx}:O{idx}', [[real_case, act_choice, "", remark, st.session_state.user, t_now]])
                            ws.update(f'Q{idx}', [[t_links]])
                            st.success(f"ปิดงานเป็น {new_status} แล้ว!")
                            time.sleep(2); st.rerun()

            if row_data['category'] == "Machine":
                with st.expander("🔗 แจ้งซ่อม PCBA ภายในเครื่องนี้"):
                    # ฟังก์ชันผูก Machine กับ PCBA ตามที่ออกแบบไว้
                    pass 

        if not history_df.empty:
            st.divider()
            st.subheader("🕒 ประวัติการซ่อมเก่า")
            st.table(history_df[['user_time', 'status', 'action', 'tech_id']])

# --- [SECTION: USER] ---
elif role == "user":
    st.header(f"📋 ระบบแจ้งซ่อม ({current_mode})")
    tab1, tab2 = st.tabs(["🚀 แจ้งซ่อมใหม่", "🔍 ติดตามงาน"])
    
    with tab1:
        df_models = get_clean_df("model_machine" if current_mode == "Machine" else "model_mat")
        with st.form("user_form"):
            in_mod = st.selectbox("Model", [""] + df_models['model'].tolist())
            sn = st.text_input("SN").upper()
            stn = st.selectbox("Station", station_list)
            dfct = st.text_area("อาการเสีย")
            u_files = st.file_uploader("📸 แนบรูปประกอบ", accept_multiple_files=True)
            
            if st.form_submit_button("🚀 ส่งข้อมูล"):
                if in_mod and sn:
                    with st.spinner("อัปโหลดรูปภาพ..."):
                        u_links = upload_multiple_images(u_files, "REQ", sn)
                        ws = ss.worksheet("sheet1")
                        p_name = df_models[df_models['model']==in_mod].iloc[0]['product_name']
                        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M")
                        
                        # สร้าง List 15 คอลัมน์แรก + คอลัมน์ที่ 16 (P) คือ u_links
                        row = [current_mode, "Pending", "", in_mod, p_name, sn, stn, dfct, now_ts, "", "", "", "", "", ""]
                        ws.append_row(row + [u_links])
                        st.success("แจ้งซ่อมสำเร็จ!"); st.rerun()

    with tab2:
        query = st.text_input("🔍 ค้นหา SN หรือ Model เพื่อติดตามสถานะ").strip().upper()
        if query:
            df_track = get_clean_df("sheet1")
            res = df_track[df_track['serial_number'].str.contains(query) | df_track['model'].str.contains(query)]
            for _, r in res.sort_values(by='user_time', ascending=False).iterrows():
                st_color = "orange" if r['status'] == "Pending" else ("green" if r['status'] == "Complate" else "red")
                with st.expander(f"SN: {r['serial_number']} | Status: {r['status']}"):
                    st.write(f"สถานะ: :{st_color}[{r['status']}]")
                    if r.get('user_image'): st.image(str(r['user_image']).split(',')[0], width=200)

# --- [SECTION: ADMIN] ---
elif role in ["admin", "super admin"]:
    st.header("📊 Admin Dashboard")
    df = get_clean_df("sheet1")
    if not df.empty:
        st.plotly_chart(px.pie(df, names='status', color='status', 
                               color_discrete_map={'Pending':'orange', 'Complate':'green', 'Scrap':'red'}))
        st.dataframe(df)
