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

# --- 1. SETTINGS & CONNECTIONS ---
st.set_page_config(page_title="Repair Management System PRO", layout="wide")
SHEET_ID = "1KtW9m3hFq2sBUeRkNATvD4nRKu_cDCoZENXk7WgOafc"

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
            img.thumbnail((800, 800))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            buf.seek(0)
            res = cloudinary.uploader.upload(buf, folder="repair_system",
                public_id=f"{prefix}_{sn}_{int(time.time())}_{i+1}", format="jpg")
            urls.append(res.get("secure_url"))
        except: continue
    return ",".join(urls)

# --- 3. LOGIN & SESSION ---
if 'is_logged_in' not in st.session_state: st.session_state.is_logged_in = False

if not st.session_state.is_logged_in:
    st.title("🛡️ Repair System Login")
    with st.form("login_form"):
        u = st.text_input("Username").strip()
        p = st.text_input("Password", type="password").strip()
        mode = st.selectbox("โหมดการทำงาน", ["PCBA", "Machine"])
        if st.form_submit_button("เข้าสู่ระบบ", use_container_width=True):
            df_u = get_df("users")
            match = df_u[(df_u['username'].astype(str)==u) & (df_u['password'].astype(str)==p)]
            if not match.empty:
                nick = match.iloc[0].get('nickname', u)
                st.session_state.update({
                    "is_logged_in": True, 
                    "user": u, 
                    "nickname": nick,
                    "role": str(match.iloc[0]['role']).lower(), 
                    "app_mode": mode
                })
                st.rerun()
            else: st.error("ข้อมูลไม่ถูกต้อง")
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.title(f"👤 คุณ {st.session_state.nickname}")
    st.write(f"**Role:** {st.session_state.role.upper()}")
    if st.button("🚪 Logout"):
        st.session_state.is_logged_in = False
        st.rerun()

ws_main = ss.worksheet("sheet1")
role, nick, app_mode = st.session_state.role, st.session_state.nickname, st.session_state.app_mode

# --- 4. USER INTERFACE ---
if role == "user":
    st.header(f"🚀 Repair Portal ({app_mode})")
    t1, t2 = st.tabs(["➕ แจ้งซ่อมใหม่", "🔍 ค้นหาและติดตาม"])

    with t1:
        df_m = get_df("model_machine" if app_mode == "Machine" else "model_mat")
        df_st = get_df("station_dropdowns")
        with st.form("req_form"):
            c1, c2 = st.columns(2)
            sel_m = c1.selectbox("Model", [""] + df_m['model'].tolist())
            p_val = df_m[df_m['model']==sel_m]['product_name'].values[0] if sel_m else ""
            c1.text_input("Product", value=p_val, disabled=True)
            sn = c1.text_input("Serial Number").strip().upper()
            wo = c2.text_input("Work Order").strip().upper()
            # เพิ่ม Station เข้าหน้าแจ้งซ่อม
            stat = c2.selectbox("Station", [""] + df_st['station'].tolist())
            fail = c2.text_area("อาการเสีย (Problem)")
            u_imgs = st.file_uploader("แนบรูปภาพ", accept_multiple_files=True)
            
            if st.form_submit_button("ยืนยันแจ้งซ่อม"):
                if sel_m and sn and wo and stat:
                    with st.spinner("Uploading Images..."):
                        urls = upload_images(u_imgs, "REQ", sn)
                    
                    # บันทึกลง Sheets
                    ws_main.append_row([app_mode, "Pending", wo, sel_m, p_val, sn, stat, fail, get_now(), "", "", "", "", "", nick, urls])
                    
                    # --- แก้ไขรูปแบบ LINE เพิ่ม Station ---
                    line_msg = (
                        f"🚨 แจ้งซ่อมใหม่!\n"
                        f"Process : {app_mode}\n"
                        f"Station : {stat}\n"
                        f"Model : {sel_m}\n"
                        f"Wo : {wo}\n"
                        f"SN : {sn}\n"
                        f"Problem : {fail}\n"
                        f"Nickname : {nick}"
                    )
                    send_line(line_msg)
                    st.success("ส่งข้อมูลและแจ้งเตือน LINE เรียบร้อย!"); time.sleep(1); st.rerun()
                else:
                    st.warning("กรุณากรอกข้อมูลให้ครบถ้วน รวมถึงเลือก Station")

    with t2:
        search_q = st.text_input("🔍 ค้นหา SN หรือ Model").strip().upper()
        df_s = get_df("sheet1")
        if not df_s.empty:
            my_jobs = df_s[df_s['category'] == app_mode]
            if search_q:
                my_jobs = my_jobs[(my_jobs['serial_number'].astype(str).str.contains(search_q)) | (my_jobs['model'].astype(str).str.contains(search_q))]
            
            for idx, row in my_jobs.tail(10).iloc[::-1].iterrows():
                with st.expander(f"📌 {row['status']} | {row['serial_number']} ({row['model']})"):
                    st.write(f"**Station:** {row['station']}")
                    st.write(f"**Problem:** {row['failure']}")
                    if st.button("🔔 ตามงานด่วน", key=f"alert_{idx}"):
                        msg = f"⚠️ ตามงานด่วน!\nSN: {row['serial_number']}\nStation: {row['station']}\nผู้ตาม: {nick}"
                        send_line(msg); st.success("ส่งแจ้งเตือนแล้ว")

# --- 5. TECH PAGE ---
elif role == "tech":
    st.header("🔧 Technician Workspace")
    sn_scan = st.text_input("🔍 Scan Serial Number").strip().upper()
    if sn_scan:
        df_all = get_df("sheet1")
        job = df_all[(df_all['serial_number']==sn_scan) & (df_all['status'].isin(["Pending", "Wait Part"]))]
        if not job.empty:
            j = job.iloc[-1]; ridx = job.index[-1] + 2
            st.info(f"📍 อาการ: {j['failure']}")
            with st.form("tech_update"):
                res = st.radio("สถานะ:", ["Complate", "Scrap", "Wait Part"], horizontal=True)
                p_name = st.text_input("ชื่อพาร์ทที่รอ (ถ้ามี)")
                cls = st.selectbox("Classification", [""] + get_df("class_dropdowns")['classification'].tolist())
                case = st.text_input("สาเหตุจริง")
                act = st.text_area("วิธีแก้ไข")
                if st.form_submit_button("บันทึกการซ่อม"):
                    ws_main.update(f'B{ridx}', [[res]])
                    ws_main.update(f'J{ridx}:L{ridx}', [[case, act, cls]])
                    ws_main.update(f'M{ridx}', [[p_name]])
                    ws_main.update(f'N{ridx}:O{ridx}', [[nick, get_now()]])
                    
                    # แจ้งเตือนปิดงาน
                    send_line(f"✅ ปิดงานเรียบร้อย!\nSN: {sn_scan}\nStatus: {res}\nช่าง: {nick}")
                    st.success("อัปเดตข้อมูลแล้ว!"); time.sleep(1); st.rerun()

# --- 6. SUPER ADMIN: MANAGE USERS ---
elif role == "super admin":
    st.header("👮 Super Admin Control")
    df_u = get_df("users")
    
    with st.expander("👤 จัดการผู้ใช้งานและชื่อเล่น"):
        # ตรวจสอบว่ามีคอลัมน์ nickname หรือยัง
        display_cols = ['username', 'role']
        if 'nickname' in df_u.columns:
            display_cols.append('nickname')
        st.dataframe(df_u[display_cols], use_container_width=True)
        
        with st.form("add_user"):
            st.subheader("➕ เพิ่มผู้ใช้งาน")
            col1, col2 = st.columns(2)
            u_in = col1.text_input("Username (Emp ID)")
            n_in = col1.text_input("Nickname (ชื่อเล่น)")
            p_in = col2.text_input("Password", type="password")
            r_in = col2.selectbox("Role", ["user", "tech", "admin", "super admin"])
            
            if st.form_submit_button("เพิ่ม User"):
                if u_in and n_in and p_in:
                    # บันทึกลงชีต users (คอลัมน์ 1:User, 2:Pass, 3:Role, 4:Nickname)
                    ss.worksheet("users").append_row([u_in, p_in, r_in, n_in])
                    st.success(f"เพิ่มคุณ {n_in} สำเร็จ!"); time.sleep(1); st.rerun()
                else:
                    st.warning("กรุณากรอกข้อมูลให้ครบ")
