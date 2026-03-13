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

# --- 1. SETTINGS & PAGE CONFIG ---
st.set_page_config(page_title="PCBA Repair System", layout="wide", initial_sidebar_state="expanded")

# ID ของ Google Sheet
SHEET_ID = "1KtW9m3hFq2sBUeRkNATvD4nRKu_cDCoZENXk7WgOafc"

# --- 2. INITIALIZE CONNECTIONS ---
@st.cache_resource
def init_all():
    try:
        # Google Sheets Setup
        creds_dict = st.secrets["gcp_service_account"]
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        ss = client.open_by_key(SHEET_ID)
        
        # Cloudinary Setup (ใช้ค่าล่าสุดของคุณ)
        cloudinary.config(
            cloud_name = "dn8n04koh",
            api_key = "352259521151764",
            api_secret = "R9S6W2_-CGIP4d-_uKA-nKW1gOg",
            secure = True
        )
        return ss, True
    except Exception as e:
        return e, False

ss, success = init_all()

if not success:
    st.error(f"❌ Connection Error: {ss}")
    st.stop()

# --- 3. HELPER FUNCTIONS ---
def send_line(msg):
    token = st.secrets["line_channel_access_token"]
    group_id = st.secrets["line_group_id"]
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    payload = {"to": group_id, "messages": [{"type": "text", "text": msg}]}
    try: requests.post(url, headers=headers, json=payload)
    except: pass

def upload_to_cloudinary(files, prefix, sn):
    urls = []
    if not files: return ""
    for i, file in enumerate(files):
        try:
            # ย่อขนาดรูปภาพก่อนส่งเพื่อประหยัด bandwidth
            img = Image.open(file)
            img.thumbnail((1000, 1000))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            buf.seek(0)

            res = cloudinary.uploader.upload(
                buf,
                folder = "repair_system",
                public_id = f"{prefix}_{sn}_{int(time.time())}_{i+1}",
                format = "jpg"
            )
            urls.append(res.get("secure_url"))
        except: continue
    return ",".join(urls)

def get_df(name):
    try:
        ws = ss.worksheet(name)
        df = pd.DataFrame(ws.get_all_records())
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        return df.fillna("")
    except: return pd.DataFrame()

# --- 4. LOGIN SYSTEM ---
if 'is_logged_in' not in st.session_state:
    st.session_state.is_logged_in = False

if not st.session_state.is_logged_in:
    st.title("⚙️ PCBA/Machine Repair System")
    with st.container():
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            with st.form("login_form"):
                st.subheader("🔑 กรุณาเข้าสู่ระบบ")
                u = st.text_input("Username").strip()
                p = st.text_input("Password", type="password").strip()
                m = st.selectbox("โหมดการทำงาน", ["PCBA", "Machine"])
                if st.form_submit_button("เข้าสู่ระบบ", use_container_width=True):
                    df_u = get_df("users")
                    match = df_u[(df_u['username'].astype(str)==u) & (df_u['password'].astype(str)==p)]
                    if not match.empty:
                        st.session_state.update({
                            "is_logged_in": True, 
                            "user": u, 
                            "role": match.iloc[0]['role'].lower(), 
                            "app_mode": m
                        })
                        st.rerun()
                    else: st.error("❌ Username หรือ Password ไม่ถูกต้อง")
    st.stop()

# --- 5. APP INTERFACE ---
ws_main = ss.worksheet("sheet1")
role = st.session_state.role
user_now = st.session_state.user
mode_now = st.session_state.app_mode

# Sidebar จัดการโปรไฟล์
with st.sidebar:
    st.title(f"👤 {user_now}")
    st.write(f"**ตำแหน่ง:** {role.upper()}")
    st.write(f"**โหมด:** {mode_now}")
    st.divider()
    if st.button("Log out", use_container_width=True):
        st.session_state.is_logged_in = False
        st.rerun()

# --- [TECHNICIAN PAGE] ---
if role == "tech":
    st.header("🔧 แผงควบคุมช่าง (Technician Action)")
    sn_scan = st.text_input("🔍 สแกน Serial Number เพื่อปิดงาน", placeholder="วางเคอร์เซอร์ที่นี่แล้วสแกน...").strip().upper()
    
    if sn_scan:
        df_all = get_df("sheet1")
        # กรองหางานที่ยัง Pending และตรงกับ SN
        active_jobs = df_all[(df_all['serial_number'].astype(str) == sn_scan) & (df_all['status'] == "Pending")]
        
        if not active_jobs.empty:
            job = active_jobs.iloc[-1]
            idx = active_jobs.index[-1] + 2 # แถวใน Google Sheet
            
            st.divider()
            c1, c2 = st.columns([1, 1])
            with c1:
                st.subheader("📋 รายละเอียดปัญหา")
                st.info(f"**Model:** {job['model']}\n\n**Product:** {job['product_name']}\n\n**อาการเสีย:** {job['failure']}")
                # โชว์รูปจาก Cloudinary (รูปที่ User อัปโหลดมา)
                if job.get('user_image'):
                    urls = str(job['user_image']).split(',')
                    for u in urls:
                        if u: st.image(u.strip(), caption="รูปประกอบจากจุดที่เสีย", use_container_width=True)
            
            with c2:
                st.subheader("🛠️ บันทึกการแก้ไข")
                with st.form("tech_repair"):
                    final_stat = st.radio("สรุปสถานะ:", ["Complate", "Scrap"], horizontal=True)
                    action_txt = st.text_area("วิธีการแก้ไข / Action")
                    remark_txt = st.text_input("หมายเหตุ (ถ้ามี)")
                    t_files = st.file_uploader("📸 ถ่ายรูปยืนยันหลังซ่อม", accept_multiple_files=True)
                    
                    if st.form_submit_button("✅ บันทึกและแจ้งเตือน LINE"):
                        with st.spinner("กำลังอัปโหลดและบันทึกข้อมูล..."):
                            t_urls = upload_to_cloudinary(t_files, "TECH", sn_scan)
                            time_now = datetime.now().strftime("%Y-%m-%d %H:%M")
                            
                            # อัปเดต Google Sheets: B(Status), K(Action), M(Remark), N(TechID), O(Time), Q(Image)
                            ws_main.update(f'B{idx}', [[final_stat]])
                            ws_main.update(f'K{idx}:O{idx}', [[action_txt, "", remark_txt, user_now, time_now]])
                            ws_main.update(f'Q{idx}', [[t_urls]])
                            
                            send_line(f"✅ งาน {final_stat}!\nSN: {sn_scan}\nโดยช่าง: {user_now}\nAction: {action_txt}")
                            st.success("บันทึกข้อมูลสำเร็จ!"); time.sleep(1.5); st.rerun()
        else:
            st.warning("⚠️ ไม่พบรายการที่ค้างซ่อมสำหรับ Serial Number นี้")

# --- [USER PAGE] ---
elif role == "user":
    st.header(f"🚀 แบบฟอร์มแจ้งซ่อม ({mode_now})")
    # เลือกดึงข้อมูล Model ตามโหมดที่เลือกตอน Login
    sheet_model = "model_machine" if mode_now == "Machine" else "model_mat"
    df_m = get_df(sheet_model)
    
    with st.container():
        with st.form("user_request_form"):
            col_a, col_b = st.columns(2)
            with col_a:
                sel_model = st.selectbox("เลือก Model", [""] + df_m['model'].tolist())
                sn_in = st.text_input("Serial Number / Work Order").strip().upper()
            with col_b:
                station = st.text_input("Station / กระบวนการ")
                u_files = st.file_uploader("📸 แนบรูปถ่ายจุดที่เสีย", accept_multiple_files=True)
            
            fail_desc = st.text_area("รายละเอียดอาการเสีย")
            
            if st.form_submit_button("📤 ส่งข้อมูลแจ้งซ่อม"):
                if sel_model and sn_in and fail_desc:
                    with st.spinner("กำลังส่งข้อมูลแจ้งซ่อม..."):
                        u_urls = upload_to_cloudinary(u_files, "REQ", sn_in)
                        p_name = df_m[df_m['model']==sel_model].iloc[0]['product_name']
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                        
                        # แถวข้อมูล: A(Type), B(Status), C(WO), D(Model), E(Prod), F(SN), G(ST), H(Fail), I(Time)... P(URL)
                        row_data = [mode_now, "Pending", "", sel_model, p_name, sn_in, station, fail_desc, now_str, "", "", "", "", "", ""]
                        ws_main.append_row(row_data + [u_urls])
                        
                        send_line(f"🚨 แจ้งซ่อมใหม่ ({mode_now})\nSN: {sn_in}\nModel: {sel_model}\nอาการ: {fail_desc}")
                        st.success("ส่งข้อมูลสำเร็จ! ระบบกำลังแจ้งเตือนช่าง..."); time.sleep(1.5); st.rerun()
                else:
                    st.warning("❗ กรุณากรอกข้อมูล Model, SN และอาการเสียให้ครบถ้วน")

# --- [ADMIN SECTION] ---
elif role in ["admin", "super admin"]:
    st.header("📊 Dashboard")
    df = get_clean_df("sheet1")
    if not df.empty:
        st.plotly_chart(px.pie(df, names='status', color='status', color_discrete_map={'Pending':'orange','Complate':'green','Scrap':'red'}))
        st.dataframe(df)
