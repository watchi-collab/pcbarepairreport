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
from deep_translator import GoogleTranslator

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
def translate_to_en(text):
    if not text: return ""
    try:
        if any("\u0E00" <= char <= "\u0E7F" for char in text):
            return GoogleTranslator(source='th', target='en').translate(text)
        return text
    except: return text

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

# --- 3. LOGIN ---
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
                st.session_state.update({"is_logged_in":True, "user":u, "role":str(match.iloc[0]['role']).lower(), "nickname":match.iloc[0].get('nickname', u), "app_mode":mode})
                st.rerun()
            else: st.error("ข้อมูลไม่ถูกต้อง")
    st.stop()

# --- 4. MAIN LAYOUT & SIDEBAR (EDIT DATA) ---
ws_main = ss.worksheet("sheet1")
df_all = get_df("sheet1")
role, app_mode = st.session_state.role, st.session_state.app_mode

with st.sidebar:
    st.title(f"👤 {st.session_state.nickname}")
    st.write(f"Mode: {app_mode} | Role: {role.upper()}")
    
    # ส่วนแก้ไขข้อมูลด่วนใน Sidebar
    st.divider()
    st.subheader("📝 Quick Edit Status")
    sn_edit = st.text_input("Scan SN to Edit").strip().upper()
    if sn_edit:
        edit_row = df_all[df_all['serial_number'] == sn_edit]
        if not edit_row.empty:
            with st.expander("Edit Details", expanded=True):
                new_stat = st.selectbox("Update Status", ["Pending", "Wait Part", "Complate", "Scrap"], index=["Pending", "Wait Part", "Complate", "Scrap"].index(edit_row.iloc[-1]['status']) if edit_row.iloc[-1]['status'] in ["Pending", "Wait Part", "Complate", "Scrap"] else 0)
                if st.button("Save Changes"):
                    r_idx = edit_row.index[-1] + 2
                    ws_main.update(f'B{r_idx}', [[new_stat]])
                    st.success("Updated!"); time.sleep(1); st.rerun()
        else: st.warning("SN Not Found")
    
    if st.button("🚪 Logout"):
        st.session_state.is_logged_in = False; st.rerun()
        
# --- 4. USER INTERFACE (With Translation) ---
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
            stat = c2.selectbox("Station", [""] + df_st['station'].tolist())
            fail_th = c2.text_area("อาการเสีย (Problem) - พิมพ์ไทยได้")
            u_imgs = st.file_uploader("แนบรูปภาพ", accept_multiple_files=True)
            
            if st.form_submit_button("ยืนยันแจ้งซ่อม"):
                if sel_m and sn and wo and stat:
                    with st.spinner("กำลังแปลภาษาและอัปโหลดรูปภาพ..."):
                        # --- แปลภาษา ---
                        fail_en = translate_to_en(fail_th)
                        urls = upload_images(u_imgs, "REQ", sn)
                    
                    ws_main.append_row([app_mode, "Pending", wo, sel_m, p_val, sn, stat, fail_en, get_now(), "", "", "", "", "", nick, urls])
                    
                    line_msg = (
                        f"🚨 แจ้งซ่อมใหม่!\n"
                        f"Process : {app_mode}\n"
                        f"Station : {stat}\n"
                        f"Model : {sel_m}\n"
                        f"Wo : {wo}\n"
                        f"SN : {sn}\n"
                        f"Problem : {fail_en}\n"
                        f"Nickname : {nick}"
                    )
                    send_line(line_msg)
                    st.success(f"แจ้งซ่อมสำเร็จ! (ระบบแปลเป็น: {fail_en})")
                    time.sleep(1); st.rerun()
                else:
                    st.warning("กรุณากรอกข้อมูลให้ครบถ้วน")

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

elif role == "tech":
    col_main, col_side = st.columns([2, 1])
    
    with col_main:
        st.header("🔧 Technician Workspace")
        sn_scan = st.text_input("🔍 Scan Serial Number for Analysis").strip().upper()
        if sn_scan:
            job = df_all[(df_all['serial_number']==sn_scan) & (df_all['status'].isin(["Pending", "Wait Part"]))]
            if not job.empty:
                j = job.iloc[-1]; ridx = job.index[-1] + 2
                st.info(f"📍 Original Problem: {j['failure']}")
                with st.form("tech_update"):
                    res = st.radio("Next Status:", ["Complate", "Scrap", "Wait Part"], horizontal=True)
                    p_name = st.text_input("Waiting Part Name (if any)")
                    cls = st.selectbox("Classification", [""] + get_df("class_dropdowns")['classification'].tolist())
                    case_th = st.text_input("Root Cause (Thai/En)")
                    act_th = st.text_area("Action Taken (Thai/En)")
                    tech_imgs = st.file_uploader("แนบรูปภาพขณะซ่อม/ปิดงาน", accept_multiple_files=True)
                    
                    if st.form_submit_button("Submit Analysis"):
                        with st.spinner("Translating & Uploading..."):
                            case_en = translate_to_en(case_th)
                            act_en = translate_to_en(act_th)
                            t_urls = upload_images(tech_imgs, "FIX", sn_scan)
                        
                        # อัปเดตข้อมูล (สมมติว่าคอลัมน์ Q คือที่เก็บรูปภาพของ Tech)
                        ws_main.update(f'B{ridx}', [[res]])
                        ws_main.update(f'J{ridx}:M{ridx}', [[case_en, act_en, cls, p_name]])
                        ws_main.update(f'N{ridx}:O{ridx}', [[st.session_state.nickname, get_now()]])
                        # หากต้องการเก็บรูปภาพ Tech ให้เพิ่ม Column ใน Sheet และ update เพิ่มที่นี่
                        st.success("Data Updated!"); time.sleep(1); st.rerun()
    
    with col_side:
        st.subheader("📋 Pending Jobs")
        st.dataframe(df_all[df_all['status'].isin(["Pending", "Wait Part"])][['serial_number', 'model', 'status']], height=400)

elif role in ["admin", "super admin"]:
    st.header(f"👮 Admin Control Panel ({app_mode})")
    
    # ปุ่มส่งรายงานสรุปเข้า LINE
    if st.button("📢 ส่งรายงานสรุปยอดปัจจุบันเข้า LINE Group", use_container_width=True, type="primary"):
        today_str = datetime.now(pytz.timezone('Asia/Bangkok')).strftime("%d/%m/%Y")
        df_m = df_all[df_all['category'] == app_mode]
        msg = f"📊 Manual Summary ({today_str})\nMode: {app_mode}\n"
        msg += "--------------------------------\n"
        for wo in df_m['work_order'].unique():
            wo_df = df_m[df_m['work_order'] == wo]
            p = len(wo_df[wo_df['status'].isin(['Pending', 'Wait Part'])])
            d = len(wo_df[wo_df['status'].isin(['Complate', 'Scrap'])])
            msg += f"WO.{wo}: Total {len(wo_df)} | Pending {p} | Finish {d}\n"
        send_line(msg)
        st.success("Sent to LINE!")

    st.divider()
    # ตารางแบบ Interactive แก้ไขได้เลย (Streamlit Data Editor)
    st.subheader("📊 Full Data Management (Double-click to edit)")
    edited_df = st.data_editor(df_all, num_rows="dynamic", use_container_width=True)
    if st.button("บันทึกการแก้ไขทั้งหมดในตาราง"):
        # โค้ดส่วนนี้จะวนลูปเขียนทับทั้งแผ่น หรือเลือกเฉพาะแถวที่เปลี่ยน (ขั้นสูง)
        st.info("ระบบกำลังพัฒนาการบันทึกแบบ Bulk... แนะนำให้ใช้ Sidebar Quick Edit ก่อนครับ")
