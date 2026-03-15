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
def send_line(msg):
    token = st.secrets.get("line_channel_access_token")
    group_id = st.secrets.get("line_group_id")
    if not token or not group_id: return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    payload = {"to": group_id, "messages": [{"type": "text", "text": msg}]}
    try: requests.post(url, headers=headers, json=payload)
    except: pass

# เพิ่มฟังก์ชันสรุปรายงานตามที่คุณต้องการ
def send_daily_summary(df, app_mode):
    today_str = datetime.now(pytz.timezone('Asia/Bangkok')).strftime("%d/%m/%Y")
    df_mode = df[df['category'] == app_mode]
    
    msg = f"📊 รายงาน Repair ประจำวันที่ {today_str}\nส่วนงาน: {app_mode}\n"
    msg += "--------------------------------\n"
    
    for wo in df_mode['work_order'].unique():
        if not wo: continue
        wo_df = df_mode[df_mode['work_order'] == wo]
        pending = len(wo_df[wo_df['status'].isin(['Pending', 'Wait Part'])])
        done = len(wo_df[wo_df['status'].isin(['Complate', 'Scrap'])])
        msg += f"WO.{wo}: ทั้งหมด {len(wo_df)} | ค้าง {pending} | เสร็จ {done}\n"
    
    msg += "--------------------------------\n📍 สรุปภาพรวม\n"
    if app_mode == "Machine":
        for stn in df_mode['station'].unique():
            if not stn: continue
            s_df = df_mode[df_mode['station'] == stn]
            msg += f"ST.{stn}: ทั้งหมด {len(s_df)} (ค้าง {len(s_df[s_df['status'].isin(['Pending', 'Wait Part'])])})\n"
    else:
        msg += f"ยอดรวม {len(df_mode)} บอร์ด"
    
    send_line(msg)
    st.success("ส่งสรุปรายงานเข้า LINE เรียบร้อยแล้ว")

def translate_to_en(text):
    if not text: return ""
    try:
        if any("\u0E00" <= char <= "\u0E7F" for char in text):
            return GoogleTranslator(source='th', target='en').translate(text)
        return text
    except: return text

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
                st.session_state.update({
                    "is_logged_in":True, 
                    "user":u, 
                    "role":str(match.iloc[0]['role']).lower(), 
                    "nickname":match.iloc[0].get('nickname', u), 
                    "app_mode":mode
                })
                st.rerun()
            else: st.error("ข้อมูลไม่ถูกต้อง")
    st.stop()

# --- 4. MAIN DATA ---
ws_main = ss.worksheet("sheet1")
df_all = get_df("sheet1")
role, app_mode = st.session_state.role, st.session_state.app_mode
nick = st.session_state.nickname

with st.sidebar:
    st.title(f"👤 {nick}")
    st.write(f"Mode: {app_mode} | Role: {role.upper()}")
    st.divider()
    st.subheader("📝 Quick Edit Status")
    sn_edit = st.text_input("Scan SN to Edit").strip().upper()
    if sn_edit:
        edit_row = df_all[df_all['serial_number'] == sn_edit]
        if not edit_row.empty:
            with st.expander("Edit Details", expanded=True):
                current_stat = edit_row.iloc[-1]['status']
                stat_options = ["Pending", "Wait Part", "Complate", "Scrap"]
                idx_stat = stat_options.index(current_stat) if current_stat in stat_options else 0
                new_stat = st.selectbox("Update Status", stat_options, index=idx_stat)
                if st.button("Save Changes"):
                    r_idx = edit_row.index[-1] + 2
                    ws_main.update_acell(f'B{r_idx}', new_stat)
                    st.success("Updated!"); time.sleep(1); st.rerun()
        else: st.warning("SN Not Found")
    
    if st.button("🚪 Logout"):
        st.session_state.is_logged_in = False; st.rerun()
        
# --- 5. USER INTERFACE ---
if role == "user":
    st.header(f"🚀 Repair Portal ({app_mode})")
    t1, t2 = st.tabs(["➕ แจ้งซ่อมใหม่", "🔍 ค้นหาและติดตาม"])

    with t1:
        df_m = get_df("model_machine" if app_mode == "Machine" else "model_mat")
        df_st = get_df("station_dropdowns")
        with st.form("req_form"):
            c1, c2 = st.columns(2)
            sel_m = c1.selectbox("Model", [""] + df_m['model'].tolist())
            p_val = ""
            if sel_m:
                matched_p = df_m[df_m['model']==sel_m]['product_name'].values
                p_val = matched_p[0] if len(matched_p) > 0 else ""
                
            c1.text_input("Product", value=p_val, disabled=True)
            sn = c1.text_input("Serial Number").strip().upper()
            wo = c2.text_input("Work Order").strip().upper()
            stat = c2.selectbox("Station", [""] + df_st['station'].tolist())
            fail_th = c2.text_area("อาการเสีย (Problem) - พิมพ์ไทยได้")
            u_imgs = st.file_uploader("แนบรูปภาพ", accept_multiple_files=True)
            
            if st.form_submit_button("ยืนยันแจ้งซ่อม"):
                if sel_m and sn and wo and stat:
                    with st.spinner("กำลังแปลภาษาและอัปโหลดรูปภาพ..."):
                        fail_en = translate_to_en(fail_th)
                        urls = upload_images(u_imgs, "REQ", sn)
                    
                    # ลำดับคอลัมน์ A-P (P=user_image)
                    new_row = [app_mode, "Pending", wo, sel_m, p_val, sn, stat, fail_en, get_now(), "", "", "", "", "", "", urls]
                    ws_main.append_row(new_row)
                    
                    line_msg = f"🚨 แจ้งซ่อมใหม่!\nMode: {app_mode}\nStation: {stat}\nModel: {sel_m}\nSN: {sn}\nProblem: {fail_en}\nBy: {nick}"
                    send_line(line_msg)
                    st.success(f"แจ้งซ่อมสำเร็จ!")
                    time.sleep(1); st.rerun()
                else: st.warning("กรุณากรอกข้อมูลให้ครบถ้วน")

    with t2:
        search_q = st.text_input("🔍 ค้นหา SN หรือ Model").strip().upper()
        if not df_all.empty:
            my_jobs = df_all[df_all['category'] == app_mode]
            if search_q:
                my_jobs = my_jobs[(my_jobs['serial_number'].astype(str).str.contains(search_q)) | (my_jobs['model'].astype(str).str.contains(search_q))]
            
            for idx, row in my_jobs.tail(10).iloc[::-1].iterrows():
                with st.expander(f"📌 {row['status']} | {row['serial_number']} ({row['model']})"):
                    st.write(f"**Station:** {row['station']}")
                    st.write(f"**Problem:** {row['failure']}")
                    if st.button("🔔 ตามงานด่วน", key=f"alert_{idx}"):
                        msg = f"⚠️ ตามงานด่วน!\nSN: {row['serial_number']}\nStation: {row['station']}\nผู้ตาม: {nick}"
                        send_line(msg); st.success("ส่งแจ้งเตือนแล้ว")

# --- 6. TECHNICIAN INTERFACE (ปรับปรุงให้แก้ไขงานที่เสร็จแล้วได้) ---
elif role == "tech":
    col_main, col_side = st.columns([2, 1])
    
    with col_main:
        st.header("🔧 Technician Workspace")
        sn_scan = st.text_input("🔍 Scan SN สำหรับวิเคราะห์ หรือ แก้ไขงาน (Edit)").strip().upper()
        
        if sn_scan:
            # แก้ไขเงื่อนไข: ให้ค้นหาเจอทั้งงานที่ค้าง (Pending, Wait Part) และงานที่เสร็จแล้ว (Complate)
            job = df_all[(df_all['serial_number']==sn_scan) & 
                         (df_all['category']==app_mode) & 
                         (df_all['status'].isin(["Pending", "Wait Part", "Complate"]))]
            
            if not job.empty:
                j = job.iloc[-1]
                ridx = job.index[-1] + 2 
                
                # แสดงสถานะปัจจุบัน
                if j['status'] == "Complate":
                    st.warning(f"⚠️ งานนี้ซ่อมเสร็จแล้ว คุณกำลังอยู่ในโหมด 'แก้ไขข้อมูล/แนบรูปเพิ่ม'")
                
                st.info(f"📍 Original Problem: {j['failure']}")
                
                with st.form("tech_update"):
                    st.subheader("Update Analysis & Images")
                    
                    # ดึงค่าเดิมมาเป็นค่าเริ่มต้น (Default Value)
                    current_res = j['status'] if j['status'] in ["Complate", "Scrap", "Wait Part"] else "Complate"
                    res = st.radio("Next Status:", ["Complate", "Scrap", "Wait Part"], 
                                   index=["Complate", "Scrap", "Wait Part"].index(current_res),
                                   horizontal=True)
                    
                    p_name = st.text_input("Waiting Part Name", value=j.get('wait_part_name', ""))
                    
                    cls_list = [""] + get_df("class_dropdowns")['classification'].tolist()
                    current_cls = j.get('classification', "")
                    cls_idx = cls_list.index(current_cls) if current_cls in cls_list else 0
                    cls = st.selectbox("Classification", cls_list, index=cls_idx)
                    
                    case_th = st.text_input("Root Cause (ไทย/Eng)", value=j.get('real_case', ""))
                    act_th = st.text_area("Action Taken (ไทย/Eng)", value=j.get('action', ""))
                    
                    st.markdown("---")
                    tech_imgs = st.file_uploader("📸 แนบรูปภาพเพิ่มเติม (จะไปบันทึกที่ Column Q)", accept_multiple_files=True)
                    
                    submit_label = "Update & Save Changes" if j['status'] == "Complate" else "Submit Analysis & Close Job"
                    
                    if st.form_submit_button(submit_label):
                        if case_th and act_th:
                            with st.spinner("กำลังบันทึกข้อมูล..."):
                                case_en = translate_to_en(case_th)
                                act_en = translate_to_en(act_th)
                                t_urls = upload_images(tech_imgs, "FIX", sn_scan)
                                
                                # กรณีแก้ไขงานเดิมและลืมแนบรูป: ถ้าไม่มีรูปใหม่ ให้ใช้ URL เดิมจากช่อง Q (ถ้ามี)
                                # แต่ปกติ update_acell จะเขียนทับ ถ้าต้องการเพิ่มรูปต่อจากเดิมต้องมี Logic เพิ่ม
                                # ในที่นี้จะเขียนทับด้วยรูปใหม่ที่อัปโหลดครับ
                                
                                ws_main.update_acell(f'B{ridx}', res)
                                repair_info = [[case_en, act_en, cls, p_name, nick, get_now()]]
                                ws_main.update(f'J{ridx}:O{ridx}', repair_info)
                                
                                # บันทึกรูปภาพ (เฉพาะถ้ามีการเลือกไฟล์ใหม่)
                                if t_urls:
                                    ws_main.update_acell(f'Q{ridx}', t_urls)
                            
                            st.success("บันทึกการแก้ไขเรียบร้อยแล้ว!")
                            time.sleep(1); st.rerun()
                        else: st.warning("กรุณากรอกสาเหตุและวิธีแก้ไข")
            else:
                st.error("ไม่พบข้อมูล SN นี้ในระบบ")

# --- 7. ADMIN INTERFACE ---
elif role in ["admin", "super admin"]:
    st.header(f"👮 Admin Control Panel ({app_mode})")
    
    # ปุ่มเรียกใช้ฟังก์ชันที่คุณต้องการ
    if st.button("📢 ส่งรายงานสรุปยอดปัจจุบันเข้า LINE Group", use_container_width=True, type="primary"):
        send_daily_summary(df_all, app_mode)

    st.divider()
    st.subheader("📊 Full Data Management")
    st.data_editor(df_all, num_rows="dynamic", use_container_width=True)
