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
import pytz 
from datetime import datetime
from PIL import Image
import plotly.express as px  # เพิ่มเพื่อแสดงผลกราฟในหน้า Admin

# --- 1. SETTINGS & CONNECTIONS ---
st.set_page_config(page_title="Repair Management System", layout="wide")
SHEET_ID = "1KtW9m3hFq2sBUeRkNATvD4nRKu_cDCoZENXk7WgOafc"

# ฟังก์ชันดึงเวลาปัจจุบันแบบไทย
def get_now():
    tz = pytz.timezone('Asia/Bangkok')
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M")

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
        mode = st.selectbox("โหมดการทำงานเริ่มต้น", ["PCBA", "Machine"])
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
    st.info(f"Role: {role.upper()}")
    if st.button("Log out"):
        st.session_state.is_logged_in = False; st.rerun()

# --- 4. [TECH PAGE] ---
if role == "tech":
    st.header("🔧 Technician Dashboard (Universal)")
    sn_scan = st.text_input("🔍 สแกน Serial Number (Machine/PCBA)", placeholder="Scan...").strip().upper()
    
    if sn_scan:
        df_all = get_df("sheet1")
        job_match = df_all[(df_all['serial_number'].astype(str) == sn_scan) & (df_all['status'] == "Pending")]
        
        if not job_match.empty:
            job = job_match.iloc[-1]
            row_idx = job_match.index[-1] + 2
            job_cat = job.get('category')
            st.info(f"📍 พบงาน: **{job_cat}** | Model: {job.get('model')}")
            
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("📋 Job Info")
                st.write(f"**Product:** {job.get('product_name')}")
                st.write(f"**อาการ:** {job.get('failure')}")
                if job.get('user_image'):
                    for img in str(job['user_image']).split(','):
                        if img.strip(): st.image(img.strip(), use_container_width=True)
                
                if job_cat == "Machine":
                    st.divider()
                    st.subheader("🔁 Link to PCBA Repair")
                    with st.expander("กรอก SN บอร์ดที่ส่งซ่อมต่อ"):
                        pcba_sn = st.text_input("PCBA Board Serial Number").strip().upper()
                        if st.button("🚀 Confirm Bridge to PCBA"):
                            if pcba_sn:
                                now_s = get_now()
                                link_msg = f"Sent from Machine SN: {sn_scan} | Reason: {job.get('failure')}"
                                pcba_row = ["PCBA", "Pending", job.get('work_order'), job.get('model'), job.get('product_name'), pcba_sn, "Bridge from Machine", link_msg, now_s, "", "", "", "", "", "", ""]
                                ws_main.append_row(pcba_row)
                                send_line(f"🛠️ [PCBA Linkage]\nMachine: {sn_scan}\nPCBA SN: {pcba_sn}\nส่งโดย: {current_user}")
                                st.success("สร้างรายการซ่อมบอร์ดเรียบร้อย!")
                            else: st.error("โปรดระบุ SN บอร์ด")

            with c2:
                st.subheader("💾 Close Job")
                df_class = get_df("class_dropdowns")
                class_list = df_class['classification'].tolist() if not df_class.empty else ["Other"]
                
                with st.form("tech_close_final"):
                    res = st.radio("Result:", ["Complate", "Scrap"], horizontal=True)
                    cls = st.selectbox("Classification", [""] + class_list)
                    case = st.text_input("Real Case")
                    act = st.text_area("Action")
                    imgs = st.file_uploader("Upload Repair Image", accept_multiple_files=True)
                    if st.form_submit_button("ยืนยันปิดงาน"):
                        t_urls = upload_images(imgs, "TECH", sn_scan)
                        now_s = get_now()
                        ws_main.update(f'B{row_idx}', [[res]])
                        ws_main.update(f'J{row_idx}:L{row_idx}', [[case, act, cls]])
                        ws_main.update(f'N{row_idx}:O{row_idx}', [[current_user, now_s]])
                        ws_main.update(f'Q{row_idx}', [[t_urls]])
                        send_line(f"✅ [ปิดงานสำเร็จ]\nSN: {sn_scan}\nสถานะ: {res}\nช่าง: {current_user}")
                        st.success("บันทึกสำเร็จ!"); time.sleep(1); st.rerun()
        else: st.warning("🔍 ไม่พบงานค้างซ่อม")

# --- 5. [USER PAGE] ---
elif role == "user":
    st.header(f"🚀 Repair System ({app_mode})")
    tab_req, tab_track = st.tabs(["➕ แจ้งซ่อมใหม่", "🔍 ติดตามงาน"])
    with tab_req:
        df_m = get_df("model_machine" if app_mode == "Machine" else "model_mat")
        df_st = get_df("station_dropdowns")
        with st.form("user_req_new"):
            c1, c2 = st.columns(2)
            with c1:
                sel_m = st.selectbox("Model", [""] + (df_m['model'].tolist() if not df_m.empty else []))
                p_name = df_m[df_m['model'] == sel_m]['product_name'].values[0] if sel_m and not df_m.empty else ""
                st.text_input("Product", value=p_name, disabled=True)
                sn = st.text_input("SN").strip().upper()
            with c2:
                wo = st.text_input("WO").strip().upper()
                stat = st.selectbox("Station", [""] + (df_st['station'].tolist() if not df_st.empty else []))
                fail = st.text_area("Failure Detail")
            u_imgs = st.file_uploader("Upload Image", accept_multiple_files=True)
            if st.form_submit_button("ส่งแจ้งซ่อม"):
                if sel_m and sn and wo:
                    u_urls = upload_images(u_imgs, "REQ", sn)
                    now_s = get_now()
                    ws_main.append_row([app_mode, "Pending", wo, sel_m, p_name, sn, stat, fail, now_s, "", "", "", "", "", "", u_urls])
                    send_line(f"🚨 [แจ้งซ่อมใหม่]\nSN: {sn}\nModel: {sel_m}\nโดย: {current_user}")
                    st.success("ส่งข้อมูลสำเร็จ!"); time.sleep(1); st.rerun()
    with tab_track:
        search_q = st.text_input("🔍 Search SN/Model", key="u_search").strip().upper()
        df_s = get_df("sheet1")
        if not df_s.empty:
            my_jobs = df_s[df_s['category'] == app_mode]
            if search_q:
                my_jobs = my_jobs[(my_jobs['serial_number'].astype(str).str.contains(search_q)) | (my_jobs['model'].astype(str).str.contains(search_q))]
            else: my_jobs = my_jobs.tail(10)
            for idx, row in my_jobs.iloc[::-1].iterrows():
                with st.expander(f"📌 {row['status']} | SN: {row['serial_number']} | {row['user_time']}"):
                    col_i, col_b = st.columns([3, 1])
                    with col_i:
                        st.write(f"**Model:** {row['model']} | **Failure:** {row['failure']}")
                        if row['status'] != "Pending": st.write(f"**Action:** {row['action']}")
                    with col_b:
                        if row['status'] == "Pending":
                            if st.button("🔔 ตามงาน", key=f"f_{idx}"):
                                send_line(f"⚠️ [ตามงานด่วน]\nSN: {row['serial_number']}\nโดย: {current_user}")
                                st.success("ส่งแจ้งเตือนแล้ว")

# --- 6. [ADMIN PAGE] ---
elif role in ["admin", "super admin"]:
    st.header("📊 Dashboard ระบบแจ้งซ่อม")
    df = get_df("sheet1") # แก้ไขจาก get_clean_df เป็น get_df
    
    if not df.empty:
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
