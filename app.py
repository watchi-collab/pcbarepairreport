# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import cloudinary
import cloudinary.uploader
import requests
import time
import io
import plotly.express as px
from datetime import datetime
from PIL import Image

# --- 1. SETTINGS & CONNECTIONS ---
st.set_page_config(page_title="Repair Management System", layout="wide")
SHEET_ID = "1KtW9m3hFq2sBUeRkNATvD4nRKu_cDCoZENXk7WgOafc"

@st.cache_resource
def init_all():
    try:
        creds_dict = st.secrets["gcp_service_account"]
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        ss = client.open_by_key(SHEET_ID)
        cloudinary.config(
            cloud_name = "dn8n04koh", api_key = "352259521151764",
            api_secret = "R9S6W2_-CGIP4d-_uKA-nKW1gOg", secure = True
        )
        return ss, True
    except Exception as e: return e, False

ss, success = init_all()
if not success:
    st.error(f"❌ Connection Error: {ss}"); st.stop()

# --- 2. HELPERS ---
def get_df(name):
    try:
        ws = ss.worksheet(name)
        data = ws.get_all_records()
        if not data: return pd.DataFrame()
        df = pd.DataFrame(data)
        # ปรับหัวคอลัมน์ให้เป็นตัวเล็กและไม่มีช่องว่าง เพื่อให้เรียกใช้ง่าย
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        return df.fillna("")
    except: return pd.DataFrame()

def upload_images(files, prefix, sn):
    urls = []
    if not files: return ""
    for i, file in enumerate(files):
        try:
            img = Image.open(file)
            img.thumbnail((1000, 1000))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            buf.seek(0)
            res = cloudinary.uploader.upload(buf, folder="repair_system",
                public_id=f"{prefix}_{sn}_{int(time.time())}_{i+1}", format="jpg")
            urls.append(res.get("secure_url"))
        except: continue
    return ",".join(urls)

# --- 3. AUTH & SESSION ---
if 'is_logged_in' not in st.session_state: st.session_state.is_logged_in = False

if not st.session_state.is_logged_in:
    st.title("⚙️ Repair System Login")
    with st.form("login"):
        u = st.text_input("Username").strip()
        p = st.text_input("Password", type="password").strip()
        mode = st.selectbox("โหมดการทำงาน (Category)", ["PCBA", "Machine"])
        if st.form_submit_button("Login", use_container_width=True):
            df_u = get_df("users")
            if not df_u.empty:
                match = df_u[(df_u['username'].astype(str)==u) & (df_u['password'].astype(str)==p)]
                if not match.empty:
                    st.session_state.update({"is_logged_in": True, "user": u, "role": str(match.iloc[0]['role']).lower(), "app_mode": mode})
                    st.rerun()
                else: st.error("ข้อมูลไม่ถูกต้อง")
    st.stop()

ws_main = ss.worksheet("sheet1")
role = st.session_state.role
current_user = st.session_state.user
app_mode = st.session_state.app_mode # คือ PCBA หรือ Machine

with st.sidebar:
    st.title(f"👤 {current_user}")
    st.info(f"Mode: {app_mode}")
    if st.button("Log out"):
        st.session_state.is_logged_in = False; st.rerun()

# --- 4. [TECH PAGE] ---
if role == "tech":
    st.header("🔧 แผงควบคุมช่าง (Technician)")
    sn_scan = st.text_input("🔍 สแกน Serial Number", placeholder="Scan Barcode...").strip().upper()
    
    if sn_scan:
        df_all = get_df("sheet1")
        
        # 🚩 ตรวจสอบการซ่อมซ้ำ (ใช้คอลัมน์ category ให้ตรงกับชีท)
        repeat_history = df_all[(df_all['serial_number'].astype(str) == sn_scan) & (df_all['status'] != "Pending")]
        if not repeat_history.empty:
            st.warning(f"⚠️ **แจ้งเตือน: ตรวจพบประวัติการซ่อมซ้ำ!** เคสนี้เคยซ่อมไปแล้ว {len(repeat_history)} ครั้ง")
            with st.expander("คลิกเพื่อดูประวัติการซ่อมเก่าของ SN นี้"):
                st.table(repeat_history[['user_time', 'failure', 'real_case', 'action', 'tech_id']])

        # ค้นหางานค้างซ่อม
        job_match = df_all[(df_all['serial_number'].astype(str) == sn_scan) & (df_all['status'] == "Pending")]
        if not job_match.empty:
            job = job_match.iloc[-1]; row_idx = job_match.index[-1] + 2
            
            # ดึง Dropdown
            df_class = get_df("classification_dropdowns")
            class_list = df_class['classification'].tolist() if not df_class.empty else ["Other"]

            c1, c2 = st.columns(2)
            with c1:
                st.subheader("📋 ข้อมูลใบแจ้งซ่อม")
                st.info(f"**Model:** {job.get('model')} | **Product:** {job.get('product_name')}\n\n**อาการ:** {job.get('failure')}")
                if job.get('user_image'):
                    for img in str(job['user_image']).split(','):
                        if img.strip(): st.image(img.strip(), use_container_width=True)

            with c2:
                st.subheader("🛠️ บันทึกการซ่อม")
                with st.form("tech_action"):
                    res_status = st.radio("ผลการซ่อม:", ["Complate", "Scrap"], horizontal=True)
                    class_sel = st.selectbox("Classification", [""] + class_list)
                    real_case = st.text_input("Real Case (สาเหตุจริง)")
                    action_detail = st.text_area("Action (วิธีแก้ไข)")
                    t_files = st.file_uploader("📸 แนบรูปหลังซ่อม", accept_multiple_files=True)
                    if st.form_submit_button("💾 บันทึกปิดงาน"):
                        t_urls = upload_images(t_files, "TECH", sn_scan)
                        now_time = datetime.now().strftime("%Y-%m-%d %H:%M")
                        # อัปเดตข้อมูลตามโครงสร้างชีทของคุณ (Column B, J, K, L, N, O, Q)
                        ws_main.update(f'B{row_idx}', [[res_status]])
                        ws_main.update(f'J{row_idx}:L{row_idx}', [[real_case, action_detail, class_sel]])
                        ws_main.update(f'N{row_idx}:O{row_idx}', [[current_user, now_time]])
                        ws_main.update(f'Q{row_idx}', [[t_urls]])
                        st.success("บันทึกข้อมูลเรียบร้อย!"); time.sleep(1); st.rerun()
        else: st.info("🔍 ไม่พบงานค้างซ่อม (Pending) สำหรับ SN นี้")

    # 🕒 แสดงประวัติงาน 10 รายการล่าสุด
    st.divider()
    st.subheader("🕒 ประวัติการซ่อมล่าสุด (10 รายการ)")
    df_history = get_df("sheet1")
    if not df_history.empty and 'category' in df_history.columns:
        recent = df_history[(df_history['status'] != "Pending") & (df_history['category'] == app_mode)].tail(10)
        if not recent.empty:
            st.table(recent[['user_time', 'serial_number', 'model', 'status', 'real_case', 'tech_id']])

# --- 5. [USER PAGE] ---
elif role == "user":
    st.header(f"🚀 ระบบแจ้งซ่อม ({app_mode})")
    
    # --- ส่วนติดตามสถานะงาน ---
    st.subheader("📊 ตรวจสอบสถานะงานของคุณ")
    if st.button("🔄 อัปเดตสถานะล่าสุด (Refresh Status)", use_container_width=True):
        st.cache_resource.clear()
        st.rerun()
    
    df_status = get_df("sheet1")
    if not df_status.empty and 'category' in df_status.columns:
        # กรองงานในโหมดปัจจุบัน
        my_jobs = df_status[df_status['category'] == app_mode].tail(5)
        if not my_jobs.empty:
            def color_status(val):
                color = 'orange' if val == 'Pending' else ('green' if val == 'Complate' else 'red')
                return f'color: {color}; font-weight: bold'
            # แสดงคอลัมน์สำคัญให้ User เห็น
            st.dataframe(my_jobs[['user_time', 'serial_number', 'model', 'status', 'action']].style.applymap(color_status, subset=['status']), use_container_width=True)
        else: st.info("ยังไม่มีข้อมูลการแจ้งซ่อมในระบบ")

    st.divider()
    # --- ฟอร์มแจ้งซ่อมใหม่ ---
    st.subheader("📝 กรอกข้อมูลแจ้งซ่อม")
    df_models = get_df("model_machine" if app_mode == "Machine" else "model_mat")
    df_stations = get_df("station_dropdowns")

    with st.form("user_request"):
        col1, col2 = st.columns(2)
        with col1:
            sel_model = st.selectbox("เลือก Model", [""] + (df_models['model'].tolist() if not df_models.empty else []))
            p_auto = df_models[df_models['model'] == sel_model]['product_name'].values[0] if sel_model and not df_models.empty else ""
            st.text_input("Product Name", value=p_auto, disabled=True)
            sn_in = st.text_input("Serial Number").strip().upper()
        with col2:
            wo_in = st.text_input("Work Order (WO)").strip().upper()
            station_in = st.selectbox("Station", [""] + (df_stations['station'].tolist() if not df_stations.empty else []))
            fail_in = st.text_area("อาการเสีย")
        
        # แนบรูปไว้ด้านล่าง
        u_files = st.file_uploader("📸 แนบรูปภาพอาการเสีย", accept_multiple_files=True)
        
        if st.form_submit_button("📤 ส่งข้อมูลแจ้งซ่อม", use_container_width=True):
            if sel_model and sn_in and wo_in:
                with st.spinner("กำลังอัปโหลดรูปภาพ..."):
                    u_urls = upload_images(u_files, "REQ", sn_in)
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                    # ส่งเข้าชีทเรียงตาม Category, Status, WO, Model, P_Name, SN, Station, Failure, Time...
                    row = [app_mode, "Pending", wo_in, sel_model, p_auto, sn_in, station_in, fail_in, now_str, "", "", "", "", "", ""]
                    ws_main.append_row(row + [u_urls])
                    st.success("ส่งข้อมูลสำเร็จ!"); time.sleep(1); st.rerun()
            else: st.warning("กรุณากรอก Model, SN และ WO ให้ครบถ้วน")

# --- [หน้าสำหรับ ADMIN / SUPER ADMIN] ---
elif role in ["admin", "super admin"]:
    st.header("📊 Dashboard ระบบแจ้งซ่อม")
    df = get_clean_df("sheet1")
    
    if not df.empty:
        # ส่วนแสดง Metrics สรุปผล
        c1, c2, c3 = st.columns(3)
        c1.metric("งานค้าง (Pending)", len(df[df['status'] == "Pending"]))
        c2.metric("ซ่อมเสร็จ (Complate)", len(df[df['status'] == "Complate"]))
        c3.metric("Scrap", len(df[df['status'] == "Scrap"]))
        
        st.divider()
        
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            st.subheader("สัดส่วนสถานะงาน")
            fig = px.pie(df, names='status', color='status', 
                         color_discrete_map={'Pending':'orange','Complate':'green','Scrap':'red'})
            st.plotly_chart(fig, use_container_width=True)
            
        with col_chart2:
            st.subheader("งานแยกตาม Model")
            fig2 = px.bar(df, x='model', color='status', barmode='group')
            st.plotly_chart(fig2, use_container_width=True)

        st.subheader("📋 ตารางข้อมูลทั้งหมด")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("ยังไม่มีข้อมูลในระบบ")
