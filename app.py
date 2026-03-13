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
def send_line(msg):
    token = st.secrets.get("line_channel_access_token")
    group_id = st.secrets.get("line_group_id")
    if not token or not group_id: return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    payload = {"to": group_id, "messages": [{"type": "text", "text": msg}]}
    try: requests.post(url, headers=headers, json=payload)
    except: pass

def get_df(name):
    try:
        ws = ss.worksheet(name)
        data = ws.get_all_records()
        if not data: return pd.DataFrame()
        df = pd.DataFrame(data)
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
        mode = st.selectbox("โหมดการทำงาน", ["PCBA", "Machine"])
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
app_mode = st.session_state.app_mode

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
        repeat = df_all[(df_all['serial_number'].astype(str) == sn_scan) & (df_all['status'] != "Pending")]
        if not repeat.empty:
            st.warning(f"⚠️ ตรวจพบประวัติการซ่อมซ้ำ! ({len(repeat)} ครั้ง)")
            with st.expander("ดูประวัติเก่า"):
                st.table(repeat[['user_time', 'failure', 'real_case', 'action']])

        job_match = df_all[(df_all['serial_number'].astype(str) == sn_scan) & (df_all['status'] == "Pending")]
        if not job_match.empty:
            job = job_match.iloc[-1]; row_idx = job_match.index[-1] + 2
            
            # --- จุดที่แก้ไข: ดึงข้อมูลจาก sheet class_dropdowns ---
            df_class = get_df("class_dropdowns")
            class_list = df_class['classification'].tolist() if not df_class.empty else ["Other"]

            c1, c2 = st.columns(2)
            with c1:
                # --- จุดที่แก้ไข: เพิ่มการแสดง Product Name ---
                st.info(f"📦 **Product:** {job.get('product_name')}")
                st.write(f"**Model:** {job.get('model')} | **อาการ:** {job.get('failure')}")
                
                if job.get('user_image'):
                    for img in str(job['user_image']).split(','):
                        if img.strip(): st.image(img.strip(), use_container_width=True)
            with c2:
                with st.form("tech_close"):
                    res = st.radio("ผลการซ่อม:", ["Complate", "Scrap"], horizontal=True)
                    cls = st.selectbox("Classification", [""] + class_list)
                    case = st.text_input("Real Case")
                    act = st.text_area("Action")
                    imgs = st.file_uploader("รูปหลังซ่อม", accept_multiple_files=True)
                    if st.form_submit_button("บันทึกปิดงาน"):
                        t_urls = upload_images(imgs, "TECH", sn_scan)
                        now = datetime.now().strftime("%Y-%m-%d %H:%M")
                        ws_main.update(f'B{row_idx}', [[res]])
                        ws_main.update(f'J{row_idx}:L{row_idx}', [[case, act, cls]])
                        ws_main.update(f'N{row_idx}:O{row_idx}', [[current_user, now]])
                        ws_main.update(f'Q{row_idx}', [[t_urls]])
                        send_line(f"✅ ซ่อมเสร็จ! {res} | SN: {sn_scan} โดยช่าง: {current_user}")
                        st.success("บันทึกเรียบร้อย!"); time.sleep(1); st.rerun()
        else: st.info("🔍 ไม่พบงานค้างซ่อม")

    st.divider()
    st.subheader("🕒 ประวัติการซ่อมล่าสุด")
    df_h = get_df("sheet1")
    if not df_h.empty and 'category' in df_h.columns:
        recent = df_h[(df_h['status'] != "Pending") & (df_h['category'] == app_mode)].tail(10)
        st.table(recent[['user_time', 'serial_number', 'status', 'real_case']])

# --- 5. [USER PAGE] ---
elif role == "user":
    st.header(f"🚀 Repair Management System ({app_mode})")
    tab_request, tab_tracking = st.tabs(["➕ แจ้งซ่อมใหม่", "🔍 ติดตามงาน & ประวัติ"])

    with tab_request:
        st.subheader("📝 กรอกรายละเอียดการแจ้งซ่อม")
        df_m = get_df("model_machine" if app_mode == "Machine" else "model_mat")
        df_st = get_df("station_dropdowns")

        with st.form("user_req_form"):
            col1, col2 = st.columns(2)
            with col1:
                sel_m = st.selectbox("เลือก Model", [""] + (df_m['model'].tolist() if not df_m.empty else []))
                p_name = df_m[df_m['model'] == sel_m]['product_name'].values[0] if sel_m and not df_m.empty else ""
                st.text_input("Product Name", value=p_name, disabled=True)
                sn = st.text_input("Serial Number").strip().upper()
            with col2:
                wo = st.text_input("Work Order (WO)").strip().upper()
                stat = st.selectbox("Station", [""] + (df_st['station'].tolist() if not df_st.empty else []))
                fail = st.text_area("รายละเอียดอาการเสีย")
            up_imgs = st.file_uploader("📸 แนบรูปภาพประกอบ", accept_multiple_files=True)
            if st.form_submit_button("📤 ส่งข้อมูลแจ้งซ่อม", use_container_width=True):
                if sel_m and sn and wo:
                    u_urls = upload_images(up_imgs, "REQ", sn)
                    now_s = datetime.now().strftime("%Y-%m-%d %H:%M")
                    # คอลัมน์ A=Category, B=Status, C=Work_order, D=Model, E=Product_name...
                    row_data = [app_mode, "Pending", wo, sel_m, p_name, sn, stat, fail, now_s, "", "", "", "", "", ""]
                    ws_main.append_row(row_data + [u_urls])
                    send_line(f"🚨 แจ้งซ่อมใหม่!\nSN: {sn}\nโดย: {current_user}")
                    st.success("ส่งแจ้งซ่อมสำเร็จ!"); time.sleep(1); st.rerun()

    with tab_tracking:
        st.subheader("📊 ตรวจสอบสถานะงาน")
        c_search, c_refresh = st.columns([3, 1])
        with c_search:
            search_query = st.text_input("🔍 ค้นหาด้วย SN หรือ Model", key="user_search_input").strip().upper()
        with c_refresh:
            st.write(" ")
            if st.button("🔄 รีเฟรชสถานะ", use_container_width=True): st.rerun()

        df_s = get_df("sheet1")
        if not df_s.empty and 'category' in df_s.columns:
            all_jobs = df_s[df_s['category'] == app_mode]
            if search_query:
                filtered_jobs = all_jobs[(all_jobs['serial_number'].astype(str).str.contains(search_query)) | 
                                         (all_jobs['model'].astype(str).str.contains(search_query))]
            else:
                filtered_jobs = all_jobs.tail(10)

            if not filtered_jobs.empty:
                filtered_jobs = filtered_jobs.iloc[::-1]
                for idx, row in filtered_jobs.iterrows():
                    status_color = "🟠" if row['status'] == "Pending" else ("🟢" if row['status'] == "Complate" else "🔴")
                    with st.expander(f"{status_color} SN: {row['serial_number']} | Status: {row['status']} | {row['user_time']}"):
                        col_info, col_btn = st.columns([3, 1])
                        with col_info:
                            st.write(f"**Model:** {row['model']} | **Product:** {row['product_name']}")
                            st.write(f"**WO:** {row['work_order']} | **อาการ:** {row['failure']}")
                        with col_btn:
                            if row['status'] == "Pending":
                                btn_key = f"btn_fup_{idx}_{row['serial_number']}"
                                if st.button(f"🔔 ตามช่าง", key=btn_key, use_container_width=True):
                                    send_line(f"⚠️ [ตามงานด่วน]\nSN: {row['serial_number']}\nแจ้งโดย: {current_user}")
                                    st.success("ส่งแจ้งเตือนแล้ว!")

# --- 5. [USER PAGE] ---
elif role == "user":
    st.header(f"🚀 Repair Management System ({app_mode})")
    tab_request, tab_tracking = st.tabs(["➕ แจ้งซ่อมใหม่", "🔍 ติดตามงาน & ประวัติ"])

    # --- Tab 1: แจ้งซ่อมใหม่ ---
    with tab_request:
        st.subheader("📝 กรอกรายละเอียดการแจ้งซ่อม")
        df_m = get_df("model_machine" if app_mode == "Machine" else "model_mat")
        df_st = get_df("station_dropdowns")

        with st.form("user_req_form"):
            col1, col2 = st.columns(2)
            with col1:
                sel_m = st.selectbox("เลือก Model", [""] + (df_m['model'].tolist() if not df_m.empty else []))
                p_name = df_m[df_m['model'] == sel_m]['product_name'].values[0] if sel_m and not df_m.empty else ""
                st.text_input("Product Name", value=p_name, disabled=True)
                sn = st.text_input("Serial Number").strip().upper()
            with col2:
                wo = st.text_input("Work Order (WO)").strip().upper()
                stat = st.selectbox("Station", [""] + (df_st['station'].tolist() if not df_st.empty else []))
                fail = st.text_area("รายละเอียดอาการเสีย")
            up_imgs = st.file_uploader("📸 แนบรูปภาพประกอบ", accept_multiple_files=True)
            if st.form_submit_button("📤 ส่งข้อมูลแจ้งซ่อม", use_container_width=True):
                if sel_m and sn and wo:
                    u_urls = upload_images(up_imgs, "REQ", sn)
                    now_s = datetime.now().strftime("%Y-%m-%d %H:%M")
                    row_data = [app_mode, "Pending", wo, sel_m, p_name, sn, stat, fail, now_s, "", "", "", "", "", ""]
                    ws_main.append_row(row_data + [u_urls])
                    send_line(f"🚨 แจ้งซ่อมใหม่!\nSN: {sn}\nโดย: {current_user}")
                    st.success("ส่งแจ้งซ่อมสำเร็จ!"); time.sleep(1); st.rerun()

    # --- Tab 2: ติดตามงาน & ประวัติ ---
    with tab_tracking:
        st.subheader("📊 ตรวจสอบสถานะงาน")
        c_search, c_refresh = st.columns([3, 1])
        with c_search:
            search_query = st.text_input("🔍 ค้นหาด้วย SN หรือ Model", key="user_search_input").strip().upper()
        with c_refresh:
            st.write(" ")
            if st.button("🔄 รีเฟรชสถานะ", use_container_width=True): st.rerun()

        df_s = get_df("sheet1")
        if not df_s.empty and 'category' in df_s.columns:
            all_jobs = df_s[df_s['category'] == app_mode]
            if search_query:
                filtered_jobs = all_jobs[(all_jobs['serial_number'].astype(str).str.contains(search_query)) | 
                                         (all_jobs['model'].astype(str).str.contains(search_query))]
            else:
                filtered_jobs = all_jobs.tail(10)

            if not filtered_jobs.empty:
                # เรียงลำดับให้ล่าสุดอยู่บน
                filtered_jobs = filtered_jobs.iloc[::-1]
                
                # --- จุดที่แก้ไข: ใช้ enumerate เพื่อเอา index มาทำเป็น key ของปุ่ม ---
                for idx, row in filtered_jobs.iterrows():
                    status_color = "🟠" if row['status'] == "Pending" else ("🟢" if row['status'] == "Complate" else "🔴")
                    with st.expander(f"{status_color} SN: {row['serial_number']} | Status: {row['status']} | {row['user_time']}"):
                        col_info, col_btn = st.columns([3, 1])
                        with col_info:
                            st.write(f"**Model:** {row['model']} | **WO:** {row['work_order']}")
                            st.write(f"**อาการ:** {row['failure']}")
                            if row['status'] != "Pending":
                                st.success(f"**Action:** {row['action']}")
                        with col_btn:
                            if row['status'] == "Pending":
                                # สร้าง Key แบบไม่ซ้ำโดยใช้ index ของ DataFrame
                                btn_key = f"btn_fup_{idx}_{row['serial_number']}"
                                if st.button(f"🔔 ตามช่าง", key=btn_key, use_container_width=True):
                                    send_line(f"⚠️ [ตามงานด่วน]\nSN: {row['serial_number']}\nแจ้งโดย: {current_user}")
                                    st.success("ส่งแจ้งเตือนแล้ว!")
            else:
                st.info("ไม่พบข้อมูล")

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
