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

# --- 3. LOGIN & GLOBAL DATA ---
if 'is_logged_in' not in st.session_state: st.session_state.is_logged_in = False

if not st.session_state.is_logged_in:
    st.title("🛡️ Repair & Scrap Management System")
    app_mode_init = st.selectbox("เลือกโหมดการทำงาน (สำหรับ User)", ["PCBA", "Machine"])
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

# Load Dropdowns
df_actions = get_clean_df("action_dropdowns")
action_list = df_actions['category'].tolist() if not df_actions.empty else ["Repair", "Replace", "N/A"]
df_class = get_clean_df("classification_dropdowns")
class_list = df_class['category'].tolist() if not df_class.empty else ["Material", "Process", "N/A"]
df_stations = get_clean_df("station_dropdowns")
station_list = df_stations['category'].tolist() if not df_stations.empty else ["General"]

# --- 4. INTERFACE ---
role = st.session_state.role
current_mode = st.session_state.app_mode
st.sidebar.info(f"👤 {st.session_state.user} | Role: {role.upper()}")
if st.sidebar.button("Logout"):
    st.session_state.is_logged_in = False
    st.rerun()

# --- [SECTION: TECH] ---
if role == "tech":
    st.header("🔧 Technician Action Center")
    search_sn = st.text_input("🔍 Scan Serial Number (SN)").strip().upper()
    
    if search_sn:
        df_all = get_clean_df("sheet1")
        active_jobs = df_all[(df_all['serial_number'].astype(str) == search_sn) & (df_all['status'] == "Pending")]
        history_df = df_all[(df_all['serial_number'].astype(str) == search_sn) & (df_all['status'] != "Pending")]

        if not active_jobs.empty:
            job = active_jobs.tail(1)
            row_data = job.iloc[0]
            
            col_info, col_form = st.columns([1, 1.2])
            with col_info:
                st.subheader("📋 รายละเอียดงาน")
                st.info(f"**SN:** {row_data['serial_number']} | **Product:** {row_data['product_name']}")
                st.warning(f"**Model:** {row_data['model']} | **WO:** {row_data['work_order']}")
                st.error(f"**อาการเสีย:** {row_data['failure']}")
                if row_data.get('user_image'):
                    for img in str(row_data['user_image']).split(','):
                        if img: st.image(img, use_container_width=True)

            with col_form:
                st.subheader("🛠️ บันทึกผลการดำเนินงาน")
                with st.form("tech_repair_form"):
                    # เพิ่มตัวเลือกสถานะ Complate หรือ Scrap
                    new_status = st.radio("เลือกสถานะการปิดงาน:", ["Complate", "Scrap"], horizontal=True)
                    real_case = st.text_input("Real Case (สาเหตุที่พบ)")
                    act_choice = st.selectbox("Action (การแก้ไข)", action_list)
                    class_choice = st.selectbox("Classification", class_list)
                    remark = st.text_area("Remark")
                    tech_files = st.file_uploader("📸 รูปประกอบ", accept_multiple_files=True)
                    
                    if st.form_submit_button("💾 บันทึกข้อมูล"):
                        idx = job.index[-1] + 2
                        ws = ss.worksheet("sheet1")
                        t_links = upload_multiple_images(tech_files, "TECH", search_sn)
                        t_now = datetime.now().strftime("%Y-%m-%d %H:%M")
                        
                        # อัปเดตสถานะตามที่เลือก (Complate หรือ Scrap)
                        ws.update(f'B{idx}', [[new_status]])
                        ws.update(f'J{idx}:O{idx}', [[real_case, act_choice, class_choice, remark, st.session_state.user, t_now]])
                        ws.update(f'Q{idx}', [[t_links]])
                        
                        if new_status == "Complate": st.balloons()
                        else: st.snow()
                        
                        st.success(f"บันทึกเป็นสถานะ {new_status} เรียบร้อย!")
                        time.sleep(2); st.rerun()

            # --- Machine Link Logic ---
            if row_data['category'] == "Machine":
                with st.expander("🔗 แจ้งซ่อม PCBA ภายในเครื่องนี้"):
                    df_pcba_m = get_clean_df("model_mat")
                    with st.form("link_form"):
                        n_sn = st.text_input("PCBA SN").upper()
                        n_mod = st.selectbox("PCBA Model", [""] + df_pcba_m['model'].tolist())
                        if st.form_submit_button("🚀 ส่งซ่อม"):
                            p_name = df_pcba_m[df_pcba_m['model']==n_mod].iloc[0]['product_name']
                            ws = ss.worksheet("sheet1")
                            ws.append_row(["PCBA", "Pending", row_data['work_order'], n_mod, p_name, n_sn, row_data['station'], f"[Linked: {search_sn}]", datetime.now().strftime("%Y-%m-%d %H:%M")]+([""]*6))
                            st.success("ผูกข้อมูลสำเร็จ!")

        else:
            st.error("ไม่พบงานรอดำเนินการ (Pending)")
        
        if not history_df.empty:
            st.divider()
            st.subheader("🕒 ประวัติการซ่อม/จำหน่าย (History)")
            st.dataframe(history_df[['user_time', 'status', 'failure', 'action', 'tech_id']], use_container_width=True)

# --- [SECTION: USER] ---
elif role == "user":
    st.header(f"📋 บริการแจ้งซ่อม ({current_mode})")
    t1, t2 = st.tabs(["🚀 แจ้งซ่อมใหม่", "🔍 ติดตามงาน"])
    
    with t1:
        # ... (ส่วนแจ้งซ่อมเดิม โดยบันทึก status เป็น "Pending" เสมอ) ...
        df_models = get_clean_df("model_machine" if current_mode == "Machine" else "model_mat")
        with st.form("user_form"):
            in_model = st.selectbox("Model", [""] + df_models['model'].tolist())
            sn = st.text_input("SN").upper()
            dfct = st.text_area("อาการเสีย")
            if st.form_submit_button("🚀 ส่งแจ้งซ่อม"):
                if in_model and sn:
                    ws = ss.worksheet("sheet1")
                    p_name = df_models[df_models['model']==in_model].iloc[0]['product_name']
                    ws.append_row([current_mode, "Pending", "", in_model, p_name, sn, "", dfct, datetime.now().strftime("%Y-%m-%d %H:%M")]+([""]*7))
                    st.success("ส่งข้อมูลสำเร็จ!"); time.sleep(1); st.rerun()

    with t2:
        query = st.text_input("🔍 ค้นหา SN เพื่อติดตามสถานะ").strip().upper()
        if query:
            df_track = get_clean_df("sheet1")
            res = df_track[df_track['serial_number'].str.contains(query)]
            for _, r in res.sort_values(by='user_time', ascending=False).iterrows():
                # แยกสีตามสถานะใหม่
                st_color = "orange" if r['status'] == "Pending" else ("green" if r['status'] == "Complate" else "red")
                icon = "⏳" if r['status'] == "Pending" else ("✅" if r['status'] == "Complate" else "🗑️")
                with st.expander(f"{icon} SN: {r['serial_number']} | Status: {r['status']}"):
                    st.write(f"สถานะปัจจุบัน: :{st_color}[{r['status']}]")
                    if r['status'] != "Pending":
                        st.write(f"ผลการดำเนินงาน: {r['action']} (โดย {r['tech_id']})")

# --- [SECTION: ADMIN] ---
elif role in ["admin", "super admin"]:
    st.header("📊 Admin Dashboard")
    df = get_clean_df("sheet1")
    if not df.empty:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", len(df))
        c2.metric("Pending", len(df[df['status']=="Pending"]), delta_color="inverse")
        c3.metric("Complate", len(df[df['status']=="Complate"]))
        c4.metric("Scrap", len(df[df['status']=="Scrap"]))
        
        fig = px.pie(df, names='status', title="Overall Status Distribution", 
                     color='status', color_discrete_map={'Pending':'orange', 'Complate':'green', 'Scrap':'red'})
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df, use_container_width=True)
