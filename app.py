# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import cloudinary
import cloudinary.uploader
import io
import time
import requests
from datetime import datetime
from PIL import Image

# --- 1. SETTING & CONFIGURATION ---
st.set_page_config(page_title="Repair System", layout="wide")

SHEET_ID = "1KtW9m3hFq2sBUeRkNATvD4nRKu_cDCoZENXk7WgOafc"

# --- 2. INITIALIZE CONNECTIONS ---
@st.cache_resource
def init_all():
    try:
        # Google Sheets
        creds_dict = st.secrets["gcp_service_account"]
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        ss = client.open_by_key(SHEET_ID)
        
        # Cloudinary (khongkoo account)
        cloudinary.config(
            cloud_name = st.secrets["cloudinary"]["cloud_name"],
            api_key = st.secrets["cloudinary"]["api_key"],
            api_secret = st.secrets["cloudinary"]["api_secret"],
            secure = True
        )
        return ss, True
    except Exception as e:
        return e, False

ss, status = init_all()
if not status:
    st.error(f"การเชื่อมต่อล้มเหลว: {ss}")
    st.stop()

# --- 3. HELPER FUNCTIONS ---
def send_line(msg):
    url = "https://api.line.me/v2/bot/message/push"
    token = st.secrets["line_channel_access_token"]
    group_id = st.secrets["line_group_id"]
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    payload = {"to": group_id, "messages": [{"type": "text", "text": msg}]}
    try: requests.post(url, headers=headers, json=payload)
    except: pass

def upload_to_cloudinary(files, prefix, sn):
    urls = []
    if not files: return ""
    for i, file in enumerate(files):
        try:
            res = cloudinary.uploader.upload(
                file,
                folder = "repair_system",
                public_id = f"{prefix}_{sn}_{int(time.time())}_{i+1}",
                transformation = [{"width": 800, "crop": "limit"}] # บีบอัดรูป
            )
            urls.append(res.get("secure_url"))
        except: continue
    return ",".join(urls)

def get_df(sheet_name):
    try:
        ws = ss.worksheet(sheet_name)
        df = pd.DataFrame(ws.get_all_records())
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        return df.fillna("")
    except: return pd.DataFrame()

# --- 4. AUTHENTICATION ---
if 'is_logged_in' not in st.session_state:
    st.session_state.is_logged_in = False

if not st.session_state.is_logged_in:
    st.title("🛡️ PCBA/Machine Repair System")
    with st.form("login"):
        u = st.text_input("Username").strip()
        p = st.text_input("Password", type="password").strip()
        mode = st.selectbox("Mode", ["PCBA", "Machine"])
        if st.form_submit_button("เข้าสู่ระบบ"):
            df_u = get_df("users")
            match = df_u[(df_u['username'].astype(str)==u) & (df_u['password'].astype(str)==p)]
            if not match.empty:
                st.session_state.update({"is_logged_in": True, "user": u, "role": match.iloc[0]['role'].lower(), "app_mode": mode})
                st.rerun()
            else: st.error("Username หรือ Password ไม่ถูกต้อง")
    st.stop()

# --- 5. MAIN INTERFACE ---
ws = ss.worksheet("sheet1")
role = st.session_state.role
user_name = st.session_state.user
app_mode = st.session_state.app_mode

st.sidebar.title(f"👤 {user_name}")
st.sidebar.info(f"Role: {role.upper()}\nMode: {app_mode}")
if st.sidebar.button("Log out"):
    st.session_state.is_logged_in = False
    st.rerun()

# --- TECH PAGE ---
if role == "tech":
    st.header("🔧 สำหรับช่าง (Technician)")
    sn_scan = st.text_input("🔍 สแกน Serial Number เพื่อซ่อม").strip().upper()
    
    if sn_scan:
        df_all = get_df("sheet1")
        active = df_all[(df_all['serial_number'].astype(str) == sn_scan) & (df_all['status'] == "Pending")]
        
        if not active.empty:
            job = active.iloc[-1]
            idx = active.index[-1] + 2 # Google Sheets index starts at 1 + Header
            
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("ข้อมูลการแจ้งซ่อม")
                st.write(f"**Model:** {job['model']}")
                st.write(f"**Product:** {job['product_name']}")
                st.error(f"**อาการเสีย:** {job['failure']}")
                if job.get('user_image'):
                    for img in str(job['user_image']).split(','):
                        if img: st.image(img.strip(), caption="รูปประกอบจาก User", use_container_width=True)

            with col2:
                st.subheader("บันทึกผลการทำงาน")
                with st.form("tech_finish"):
                    new_status = st.radio("สรุปสถานะ:", ["Complate", "Scrap"], horizontal=True)
                    action_text = st.text_input("การแก้ไข (Action)")
                    remark = st.text_area("หมายเหตุเพิ่มเติม")
                    t_files = st.file_uploader("📸 ถ่ายรูปยืนยัน", accept_multiple_files=True)
                    
                    if st.form_submit_button("💾 บันทึกปิดงาน"):
                        with st.spinner("กำลังส่งข้อมูล..."):
                            t_urls = upload_to_cloudinary(t_files, "TECH", sn_scan)
                            now = datetime.now().strftime("%Y-%m-%d %H:%M")
                            # Update Sheets: Status(B), Action(K), Remark(M), TechID(N), TechTime(O), TechImage(Q)
                            ws.update(f'B{idx}', [[new_status]])
                            ws.update(f'K{idx}:O{idx}', [[action_text, "", remark, user_name, now]])
                            ws.update(f'Q{idx}', [[t_urls]])
                            
                            send_line(f"✅ งาน {new_status}!\nSN: {sn_scan}\nAction: {action_text}\nBy: {user_name}")
                            st.success("บันทึกข้อมูลเรียบร้อย!"); time.sleep(1); st.rerun()
        else:
            st.warning("ไม่พบรายการค้างซ่อมสำหรับ SN นี้")

# --- USER PAGE ---
elif role == "user":
    st.header(f"🚀 แจ้งซ่อมใหม่ ({app_mode})")
    sheet_name = "model_machine" if app_mode == "Machine" else "model_mat"
    df_m = get_df(sheet_name)
    
    with st.form("user_request"):
        m_list = [""] + df_m['model'].tolist()
        sel_model = st.selectbox("เลือก Model", m_list)
        sn_input = st.text_input("Serial Number").strip().upper()
        fail_desc = st.text_area("อาการเสียที่พบ")
        u_files = st.file_uploader("📸 แนบรูปภาพประกอบ", accept_multiple_files=True)
        
        if st.form_submit_button("ส่งข้อมูลแจ้งซ่อม"):
            if sel_model and sn_input:
                with st.spinner("กำลังบันทึกข้อมูล..."):
                    u_urls = upload_to_cloudinary(u_files, "REQ", sn_input)
                    prod_name = df_m[df_m['model']==sel_model].iloc[0]['product_name']
                    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M")
                    
                    # Data: A(Type), B(Status), C(WO), D(Model), E(Prod), F(SN), G(ST), H(Fail), I(Time) ... P(U_Img)
                    row = [app_mode, "Pending", "", sel_model, prod_name, sn_input, "", fail_desc, now_ts, "", "", "", "", "", ""]
                    ws.append_row(row + [u_urls])
                    
                    send_line(f"🚨 แจ้งซ่อมใหม่ ({app_mode})\nSN: {sn_input}\nModel: {sel_model}\nอาการ: {fail_desc}")
                    st.success("แจ้งซ่อมสำเร็จ!"); time.sleep(1); st.rerun()
            else:
                st.warning("กรุณากรอกข้อมูล Model และ SN ให้ครบถ้วน")

# --- [ADMIN SECTION] ---
elif role in ["admin", "super admin"]:
    st.header("📊 Dashboard")
    df = get_clean_df("sheet1")
    if not df.empty:
        st.plotly_chart(px.pie(df, names='status', color='status', color_discrete_map={'Pending':'orange','Complate':'green','Scrap':'red'}))
        st.dataframe(df)
