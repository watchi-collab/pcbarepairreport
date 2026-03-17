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
import re
from datetime import datetime, timedelta
from PIL import Image
from deep_translator import GoogleTranslator

# --- 1. SETTINGS & CONNECTIONS ---
st.set_page_config(page_title="Repair Management System PRO", layout="wide", page_icon="🛡️")
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

# --- 2. HELPERS ---
def validate_sn(text):
    if not text: return ""
    return re.sub(r'[^a-zA-Z0-9]', '', text).upper()

def get_report_periods():
    tz = pytz.timezone('Asia/Bangkok')
    now = datetime.now(tz).replace(tzinfo=None) 
    start_of_week = now - timedelta(days=now.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start_of_week, start_of_month

start_wk, start_mo = get_report_periods()

def get_df(name):
    try:
        ws = ss.worksheet(name)
        data = ws.get_all_records()
        if not data: return pd.DataFrame()
        df = pd.DataFrame(data)
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        return df.fillna("")
    except: return pd.DataFrame()

def translate_to_en(text):
    if not text: return ""
    try:
        if any("\u0E00" <= char <= "\u0E7F" for char in text):
            return GoogleTranslator(source='th', target='en').translate(text)
        return text
    except: return text

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
                                            public_id=f"{prefix}_{sn}_{int(time.time())}_{i+1}", 
                                            format="jpg")
            urls.append(res.get("secure_url"))
        except: continue
    return ",".join(urls)

def send_line(msg, image_url=None):
    # ดึงค่าจาก st.secrets (อย่าลืมไปตั้งค่าใน Streamlit Cloud)
    token = st.secrets.get("line_channel_access_token") 
    # ใช้ Group ID ที่คุณระบุมา
    group_id = "C54883d9bd6b1293ff2bad0ba497a80d7" 
    
    if not token: 
        st.error("❌ ไม่พบ Line Channel Access Token ใน Secrets")
        return
    
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json", 
        "Authorization": f"Bearer {token}"
    }
    
    # เตรียมข้อความหลัก
    messages = [{"type": "text", "text": msg}]
    
    # ถ้ามีรูปภาพแนบมา (รองรับการส่งรูปภาพ 1 รูปตามข้อกำหนดของ LINE API ต่อ 1 Bubble)
    if image_url:
        first_img = image_url.split(',')[0].strip()
        if first_img.startswith("http"):
            messages.append({
                "type": "image",
                "originalContentUrl": first_img,
                "previewImageUrl": first_img
            })
        
    payload = {
        "to": group_id,
        "messages": messages
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            print(f"LINE Error: {response.text}")
        return response.status_code
    except Exception as e:
        print(f"Connection Error: {e}")
        return None
def display_images_with_link(url_string, caption_prefix="รูปภาพ"):
    if not url_string:
        st.info(f"ไม่มี{caption_prefix}")
        return
    urls = [u.strip() for u in str(url_string).split(",") if u.strip()]
    for idx, url in enumerate(urls):
        st.image(url, caption=f"{caption_prefix} #{idx+1}", use_container_width=True)
        st.code(url)

def send_daily_summary(df, app_mode):
    tz = pytz.timezone('Asia/Bangkok')
    now = datetime.now(tz)
    today_date = now.strftime("%Y-%m-%d") 
    today_display = now.strftime("%d/%m/%Y")
    
    df_mode = df[df['category'] == app_mode].copy()
    if df_mode.empty:
        st.warning("ไม่มีข้อมูลสำหรับรายงาน")
        return

    unit = "บอร์ด" if app_mode == "PCBA" else "เครื่อง"
    msg = f"รายงานผลการ \"Repair\" ประจำวันที่ {today_display}\n"
    msg += f"ส่วนงาน: {app_mode}\n"
    msg += "--------------------------------\n"

    # 1. เตรียมข้อมูลพื้นฐาน
    pending_df = df_mode[df_mode['status'] == 'Pending']
    wait_part_df = df_mode[df_mode['status'] == 'Wait Part']
    done_today_df = df_mode[
        (df_mode['status'].isin(['Complete', 'Scrap'])) & 
        (df_mode['tech_time'].astype(str).str.contains(today_date))
    ]
    
    # 2. รายงานแยกตาม Work Order
    wo_list = pd.concat([pending_df, wait_part_df, done_today_df])['work_order'].unique()

    if len(wo_list) == 0:
        msg += f"ไม่มีงานค้างและไม่มีงานเสร็จในวันนี้ 🎉\n"
    else:
        for wo in sorted(wo_list):
            if not wo: continue
            wo_data = df_mode[df_mode['work_order'] == wo]
            
            p_cnt = len(wo_data[wo_data['status'] == 'Pending'])
            w_cnt = len(wo_data[wo_data['status'] == 'Wait Part'])
            d_cnt = len(wo_data[(wo_data['status'].isin(['Complete', 'Scrap'])) & 
                               (wo_data['tech_time'].astype(str).str.contains(today_date))])
            
            total_active = p_cnt + w_cnt + d_cnt
            if total_active > 0:
                msg += f"WO. {wo}\n"
                msg += f"จำนวน{unit}ที่เสียทั้งหมด {total_active} {unit}\n"
                if p_cnt > 0:
                    msg += f"  - อยู่ระหว่างวิเคราะห์ {p_cnt} {unit}\n"
                if w_cnt > 0:
                    msg += f"  - รอพาร์ท {w_cnt} {unit}\n"
                if d_cnt > 0:
                    msg += f"  - ซ่อมเสร็จ {d_cnt} {unit}\n"
                msg += "\n"

    # 3. สรุปภาพรวมท้ายรายงาน
    msg += "--------------------------------\n"
    msg += f"สรุปภาพรวม {app_mode}\n"
    
    if app_mode == "Machine":
        for stn in sorted(df_mode['station'].unique()):
            stn_data = df_mode[df_mode['station'] == stn]
            s_p = len(stn_data[stn_data['status'] == 'Pending'])
            s_w = len(stn_data[stn_data['status'] == 'Wait Part'])
            s_d = len(stn_data[(stn_data['status'].isin(['Complete', 'Scrap'])) & 
                              (stn_data['tech_time'].astype(str).str.contains(today_date))])
            
            if (s_p + s_w + s_d) > 0:
                msg += f"Station: {stn}\n"
                parts = []
                if s_p > 0: parts.append(f"วิเคราะห์ {s_p} {unit}")
                if s_w > 0: parts.append(f"รอพาร์ท {s_w} {unit}")
                if s_d > 0: parts.append(f"ซ่อมเสร็จ {s_d} {unit}")
                msg += f"  - " + " | ".join(parts) + "\n"
    else:
        total_all = len(pending_df) + len(wait_part_df) + len(done_today_df)
        msg += f"จำนวน{unit}ที่เสียทั้งหมด {total_all} {unit}\n"
        if len(pending_df) > 0:
            msg += f"  - อยู่ระหว่างวิเคราะห์ {len(pending_df)} {unit}\n"
        if len(wait_part_df) > 0:
            msg += f"  - รอพาร์ท {len(wait_part_df)} {unit}\n"
        if len(done_today_df) > 0:
            msg += f"  - ซ่อมเสร็จ {len(done_today_df)} {unit}\n"

    msg += "--------------------------------\n"
    msg += f"รายงานโดย: {st.session_state.nickname}"
    
    # 4. ส่งข้อมูล
    send_line(msg)
    st.success("ส่งรายงานเข้ากลุ่มเรียบร้อยแล้ว!")
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
                    "is_logged_in": True, "user": u, 
                    "role": str(match.iloc[0]['role']).lower(), 
                    "nickname": match.iloc[0].get('nickname', u), 
                    "app_mode": mode
                })
                st.rerun()
            else: st.error("ข้อมูลไม่ถูกต้อง")
    st.stop()

# --- 4. MAIN DATA LOAD ---
ws_main = ss.worksheet("sheet1")
df_all = get_df("sheet1")
role, app_mode = st.session_state.role, st.session_state.app_mode
nick = st.session_state.nickname
unit = "บอร์ด" if app_mode == "PCBA" else "เครื่อง"

# --- 5. SIDEBAR ---
with st.sidebar:
    st.title(f"👤 {nick}")
    st.write(f"**Mode:** {app_mode} | **Role:** {role.upper()}")
    st.divider()
    
    st.subheader("📝 Quick Edit Status")
    sn_edit_input = st.text_input("Scan SN to Edit").strip()
    sn_edit = validate_sn(sn_edit_input)
    if sn_edit:
        edit_row = df_all[df_all['serial_number'] == sn_edit]
        if not edit_row.empty:
            with st.expander("Update Status", expanded=True):
                current_stat = edit_row.iloc[-1]['status']
                stat_options = ["Pending", "Wait Part", "Complete", "Scrap"]
                idx_stat = stat_options.index(current_stat) if current_stat in stat_options else 0
                new_stat = st.selectbox("Status", stat_options, index=idx_stat)
                if st.button("บันทึกการเปลี่ยนสถานะ"):
                    r_idx = edit_row.index[-1] + 2
                    ws_main.update_acell(f'B{r_idx}', new_stat)
                    st.success("Updated!"); time.sleep(1); st.rerun()
        else: st.warning("ไม่พบ SN")
    
    # --- เพิ่มส่วนนี้: ปุ่มเช็ค ID (วางไว้ก่อนปุ่มออกจากระบบ) ---
    st.divider()
    if st.button("🔍 เช็ค Line ID ของฉัน", use_container_width=True):
        my_id = st.session_state.get("my_line_id", "")
        if my_id and my_id.startswith("U"):
            st.success("พบ Line ID ในระบบแล้ว")
            st.code(my_id)
            st.info("รายงานสรุปจะถูกส่งไปที่แชทส่วนตัวของ ID นี้")
        else:
            st.error("ยังไม่มี ID ในระบบ (หรือ ID ไม่ถูกต้อง)")
            st.warning("โปรดแจ้ง Admin ให้แก้ไขช่อง line_user_id ใน Sheet 'users'")
            st.write("ID ปัจจุบันของคุณคือ:", f"`{my_id}`")
    
    st.divider()
    # ปุ่มเดิมของคุณ
    if st.button("🚪 ออกจากระบบ", use_container_width=True):
        st.session_state.is_logged_in = False
        st.rerun()

# --- 6. INTERFACES BY ROLE (USER PORTAL - WITH SN VALIDATION) ---
if role == "user":
    st.header(f"🚀 Repair Portal ({app_mode})")
    
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0

    t1, t2 = st.tabs(["➕ แจ้งซ่อมใหม่", "🔍 ค้นหาและติดตาม"])
    
    with t1:
        df_m = get_df("model_machine" if app_mode == "Machine" else "model_mat")
        df_st = get_df("station_dropdowns")
        
        with st.form("req_form", clear_on_submit=False): # เปลี่ยนเป็น False เพื่อควบคุมการเคลียร์เอง
            c1, c2 = st.columns(2)
            
            sel_m = c1.selectbox("Model", [""] + df_m['model'].tolist())
            p_val = df_m[df_m['model']==sel_m]['product_name'].values[0] if sel_m else ""
            c1.text_input("Product", value=p_val, disabled=True)
            
            # รับค่า SN
            sn_input = c1.text_input("Serial Number", key="sn_field").strip()
            
            wo = c2.text_input("Work Order").strip().upper()
            stat = c2.selectbox("Station", [""] + df_st['station'].tolist())
            fail_th = c2.text_area("อาการเสีย (Problem Description)")
            
            u_imgs = st.file_uploader("📸 แนบรูปภาพ (จะส่งเข้า LINE)", 
                                     accept_multiple_files=True, 
                                     key=f"user_upload_{st.session_state.uploader_key}")
            
            if st.form_submit_button("ยืนยันแจ้งซ่อมและส่งข้อมูลเข้า LINE", use_container_width=True):
                # --- ตรวจสอบ SN ว่าเป็นภาษาอังกฤษ/ตัวเลข เท่านั้นหรือไม่ ---
                # หากมีภาษาไทย หรืออักขระพิเศษ ระบบจะเด้ง Error และไม่เคลียร์ค่า
                if not re.match(r'^[a-zA-Z0-9]+$', sn_input):
                    st.error(f"❌ รูปแบบ SN ไม่ถูกต้อง: '{sn_input}' (ต้องเป็นภาษาอังกฤษและตัวเลขเท่านั้น)")
                    st.warning("กรุณาเปลี่ยนภาษาคีย์บอร์ดแล้วแสกนใหม่อีกครั้ง")
                
                elif sel_m and sn_input and wo and stat:
                    with st.spinner("กำลังบันทึกข้อมูล..."):
                        # ทำความสะอาด SN อีกรอบ
                        sn = validate_sn(sn_input)
                        
                        # 1. แปลภาษา
                        fail_en = translate_to_en(fail_th)
                        
                        # 2. อัปโหลดรูป
                        urls = upload_images(u_imgs, "REQ", sn)
                        
                        # 3. บันทึก Sheets
                        new_row = [app_mode, "Pending", wo, sel_m, p_val, sn, stat, fail_en, get_now(), "", "", "", "", "", "", urls]
                        ws_main.append_row(new_row)
                        
                        # 4. ส่ง LINE
                        line_msg = f"🚨 New Job! ({app_mode})\nSN: {sn}\nModel: {sel_m}\nProblem: {fail_en}\nBy: {nick}"
                        send_line(line_msg, image_url=urls)
                        
                        # --- 5. บันทึกเสร็จสิ้น ค่อยทำการเคลียร์ค่าทั้งหมด ---
                        st.session_state.uploader_key += 1 
                        st.success("บันทึกสำเร็จ!")
                        time.sleep(1)
                        st.rerun() # เคลียร์หน้าจอทั้งหมดและ Focus กลับไปที่ SN
                else:
                    st.warning("กรุณากรอกข้อมูลให้ครบถ้วน")
    with t2:
        search_q = st.text_input("🔍 ค้นหา SN หรือ Model (10 รายการล่าสุด)").strip().upper()
        my_jobs = df_all[df_all['category'] == app_mode]
        
        if search_q:
            my_jobs = my_jobs[(my_jobs['serial_number'].str.contains(search_q)) | (my_jobs['model'].str.contains(search_q))]
        
        # แสดงรายการล่าสุดขึ้นก่อน (Reverse Order)
        for idx, row in my_jobs.tail(10).iloc[::-1].iterrows():
            with st.expander(f"📌 {row['status']} | {row['serial_number']} ({row['model']})"):
                st.write(f"**Station:** {row['station']}")
                st.write(f"**Problem (EN):** {row['failure']}")
                st.write(f"**Time:** {row['user_time']}")
                
                # แสดงรูปภาพที่เคยส่งไว้ (ถ้ามี)
                if row.get('user_image'):
                    display_images_with_link(row['user_image'], "รูปภาพที่แจ้งซ่อม")
# --- ROLE: TECH (ปรับปรุงการดึงข้อมูลจาก Column Action และล้างค่า Column M) ---
elif role == "tech":
    # --- 1. Sidebar: ระบบส่งรายงานสรุปยอด ---
    with st.sidebar:
        st.markdown("---")
        st.subheader("📊 Reporting System")
        
        # ตัวเลือกประเภทรายงาน (Default ตาม app_mode ปัจจุบัน)
        report_type = st.selectbox(
            "เลือกส่วนงานที่ต้องการรายงาน:",
            ["PCBA", "Machine"],
            index=0 if app_mode == "PCBA" else 1
        )
        
        if st.button(f"📢 ส่งรายงาน {report_type}", use_container_width=True):
            with st.spinner(f"กำลังสรุปข้อมูล {report_type}..."):
                # เรียกฟังก์ชันสรุปยอดที่ซ่อนบรรทัดเลข 0 ไว้แล้ว
                send_daily_summary(df_all, report_type)

    # --- 2. ส่วนแสดงผลหลัก: Technician Workspace ---
    st.header("🔧 Technician Workspace")
    sn_scan = st.text_input("🔍 Scan SN เพื่อวิเคราะห์/แก้ไข", key="tech_sn_input").strip()
    
    if sn_scan:
        if not re.match(r'^[a-zA-Z0-9]+$', sn_scan):
            st.error("❌ รูปแบบ SN ไม่ถูกต้อง (ภาษาอังกฤษและตัวเลขเท่านั้น)")
        else:
            job = df_all[(df_all['serial_number'] == sn_scan) & (df_all['category'] == app_mode)]
            if not job.empty:
                j = job.iloc[-1]
                ridx = job.index[-1] + 2 
                
                # แสดง Info เบื้องต้น
                st.info(f"📍 Station: {j.get('station')} | ⚠️ Problem: {j.get('failure')}")
                
                with st.expander("🖼️ ดูรูปภาพจาก User (คลิกเพื่อเปิดดู)"):
                    display_images_with_link(j.get('user_image', ''), "รูปภาพอาการเสีย")

                with st.form("tech_update"):
                    # ดึงค่า wait_part_name ปัจจุบัน (Column M)
                    current_wait_part = str(j.get('wait_part_name', "")).strip()
                    p_name_input = st.text_input("Waiting Part Name", value=current_wait_part)
                    
                    # ระบบสถานะอัตโนมัติ
                    stat_list = ["Complete", "Scrap", "Wait Part"]
                    default_status = "Wait Part" if p_name_input else (j.get('status') if j.get('status') in stat_list else "Complete")
                    res = st.radio("Status:", stat_list, index=stat_list.index(default_status), horizontal=True)
                    
                    cls_list = [""] + get_df("class_dropdowns")['classification'].tolist()
                    cls = st.selectbox("Classification", cls_list)
                    
                    # --- ย้าย Root Cause มาไว้ก่อนหน้า Action ---
                    case_th = st.text_input("Root Cause")
                    
                    # ดึง Action เดิม (Column K) มาแสดงเพื่อให้พิมพ์รายละเอียดต่อได้
                    existing_action = str(j.get('action', "")).strip()
                    act_th = st.text_area("Action Taken", value=existing_action)
                    
                    tech_imgs = st.file_uploader("📸 แนบรูปภาพปิดงาน", accept_multiple_files=True)
                    
                    if st.form_submit_button("บันทึกข้อมูล"):
                        # เงื่อนไขความครบถ้วนของข้อมูล
                        can_save = (res == "Wait Part" and p_name_input) or (res in ["Complete", "Scrap"] and case_th and act_th)
                        
                        if can_save:
                            with st.spinner("กำลังบันทึกข้อมูล..."):
                                case_en = translate_to_en(case_th)
                                act_en = translate_to_en(act_th)
                                
                                # จัดการข้อความ Waiting Part ใน Action
                                if res == "Wait Part" and p_name_input and (p_name_input not in act_en):
                                    act_en = f"[Waiting Part: {p_name_input}] " + act_en

                                t_urls = upload_images(tech_imgs, "FIX", sn_scan)
                                
                                # --- อัปเดต Google Sheets และล้าง Column M ---
                                ws_main.update_acell(f'B{ridx}', res)
                                ws_main.update(f'J{ridx}:M{ridx}', [[case_en, act_en, cls, ""]]) # ส่ง "" ไปที่ Column M
                                ws_main.update(f'N{ridx}:O{ridx}', [[nick, get_now()]])
                                
                                if t_urls: ws_main.update_acell(f'Q{ridx}', t_urls)
                            if res in ["Complete", "Scrap"]: send_line(f"✅ ซ่อมเสร็จ! ({app_mode})\nSN: {sn_scan}\nStatus: {res}\nBy: {nick}")
                            st.success("บันทึกสำเร็จ!"); time.sleep(1); st.rerun()
            else: st.warning("ไม่พบข้อมูล")
                
# เพิ่มเติมส่วน Super Admin ใน Tab "Management" (tabs[3])

    with tabs[3]:
        # ส่วนที่ 1: แก้ไขข้อมูลดิบ (Raw Data Editor)
        st.subheader("📝 Edit Raw Data (Repair Logs)")
        edited_df = st.data_editor(df_report.tail(50), use_container_width=True, key="raw_editor")
        
        # ส่วนที่ 2: การจัดการผู้ใช้ (User Management) - เฉพาะ Super Admin
        if role == "super admin":
            st.divider()
            st.subheader("🔑 Super Admin: User Management")
            
            # ดึงข้อมูลผู้ใช้ปัจจุบัน
            df_u = get_df("users")
            
            col_u1, col_u2 = st.columns([2, 1])
            
            with col_u1:
                st.write("👥 **รายชื่อผู้ใช้ทั้งหมด**")
                # แสดงตาราง User และสามารถกดลบหรือแก้ไขเบื้องต้นได้
                st.dataframe(df_u, hide_index=True, use_container_width=True)
            
            with col_u2:
                st.write("➕ **เพิ่มผู้ใช้ใหม่**")
                with st.form("add_user_form", clear_on_submit=True):
                    new_u = st.text_input("Username (ภาษาอังกฤษ)").strip()
                    new_p = st.text_input("Password", type="password").strip()
                    new_n = st.text_input("Nickname (ชื่อเล่น)").strip()
                    new_lid = st.text_input("Line User ID (ถ้ามี)").strip()
                    new_r = st.selectbox("Role", ["user", "tech", "admin", "super admin"])
                    
                    if st.form_submit_button("บันทึกผู้ใช้ใหม่", use_container_width=True):
                        if new_u and new_p and new_n:
                            try:
                                # ตรวจสอบ Username ซ้ำ
                                if new_u in df_u['username'].astype(str).values:
                                    st.error("Username นี้มีอยู่ในระบบแล้ว")
                                else:
                                    ss.worksheet("users").append_row([new_u, new_p, new_r, new_n, new_lid])
                                    st.success(f"เพิ่มคุณ {new_n} เรียบร้อย!")
                                    time.sleep(1)
                                    st.rerun()
                            except Exception as e:
                                st.error(f"เกิดข้อผิดพลาด: {e}")
                        else:
                            st.warning("กรุณากรอกข้อมูล Username, Password และ Nickname")

            st.divider()
            st.write("🚨 **ระบบควบคุมส่วนกลาง**")
            c_danger1, c_danger2 = st.columns(2)
            with c_danger1:
                if st.button("♻️ Clear System Cache", use_container_width=True):
                    st.cache_data.clear()
                    st.cache_resource.clear()
                    st.success("Cache Cleared!")
                    st.rerun()
            
            with c_danger2:
                del_sn = st.text_input("ระบุ SN ที่จะลบถาวร (ระวัง!)").strip()
                if st.button("🗑️ Delete Record", type="secondary", use_container_width=True):
                    if del_sn:
                        try:
                            cell = ws_main.find(del_sn)
                            ws_main.delete_rows(cell.row)
                            st.error(f"ลบข้อมูล SN {del_sn} ออกจากระบบแล้ว")
                            time.sleep(1)
                            st.rerun()
                        except:
                            st.warning("ไม่พบ SN นี้ในระบบ")
