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
    token = st.secrets.get("line_channel_access_token")
    group_id = st.secrets.get("line_group_id")
    if not token or not group_id: return
    
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    
    messages = [{"type": "text", "text": msg}]
    if image_url:
        first_img = image_url.split(',')[0]
        messages.append({
            "type": "image",
            "originalContentUrl": first_img,
            "previewImageUrl": first_img
        })
        
    payload = {"to": group_id, "messages": messages}
    requests.post(url, headers=headers, json=payload)

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

    pending_df = df_mode[df_mode['status'] == 'Pending']
    wait_part_df = df_mode[df_mode['status'] == 'Wait Part']
    done_today_df = df_mode[
        (df_mode['status'].isin(['Complete', 'Scrap'])) & 
        (df_mode['tech_time'].astype(str).str.contains(today_date))
    ]
    
    wo_list = pd.concat([pending_df, wait_part_df, done_today_df])['work_order'].unique()

    if len(wo_list) == 0:
        msg += f"ไม่มีงานค้างและไม่มีงานเสร็จในวันนี้ 🎉\n"
    else:
        for wo in sorted(wo_list):
            if not wo: continue
            wo_data = df_mode[df_mode['work_order'] == wo]
            p_cnt = len(wo_data[wo_data['status'] == 'Pending'])
            w_cnt = len(wo_data[wo_data['status'] == 'Wait Part'])
            d_cnt = len(wo_data[(wo_data['status'].isin(['Complete', 'Scrap'])) & (wo_data['tech_time'].astype(str).str.contains(today_date))])
            
            if (p_cnt + w_cnt + d_cnt) > 0:
                msg += f"WO. {wo}\n"
                msg += f"จำนวน{unit}ที่เสียทั้งหมด {p_cnt + w_cnt + d_cnt} {unit}\n"
                msg += f"  - อยู่ระหว่างวิเคราะห์ {p_cnt} {unit}\n"
                msg += f"  - รอพาร์ท {w_cnt} {unit}\n"
                msg += f"  - ซ่อมเสร็จ {d_cnt} {unit}\n"

    msg += "--------------------------------\n"
    msg += f"สรุปภาพรวม {app_mode}\n"
    msg += f"รายงานโดย: {st.session_state.nickname}"
    send_line(msg)
    st.success("ส่งรายงานเรียบร้อย!")

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
    
    st.divider()
    if st.button("🚪 ออกจากระบบ", use_container_width=True):
        st.session_state.is_logged_in = False; st.rerun()

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
# --- ROLE: TECH (ปรับปรุงระบบอัตโนมัติ) ---
# --- ROLE: TECH (ปรับปรุงให้บันทึก Wait Part ได้) ---
elif role == "tech":
    st.header("🔧 Technician Workspace")
    sn_scan = st.text_input("🔍 Scan SN เพื่อวิเคราะห์/แก้ไข", key="tech_sn_input").strip()
    
    if sn_scan:
        if not re.match(r'^[a-zA-Z0-9]+$', sn_scan):
            st.error("❌ รูปแบบ SN ไม่ถูกต้อง (ต้องเป็นภาษาอังกฤษและตัวเลขเท่านั้น)")
        else:
            job = df_all[(df_all['serial_number']==sn_scan) & (df_all['category']==app_mode)]
            if not job.empty:
                j = job.iloc[-1]
                ridx = job.index[-1] + 2 
                
                with st.expander("📝 รายละเอียดอาการเสียจาก User", expanded=True):
                    c1, c2 = st.columns(2)
                    c1.write(f"**Model:** {j.get('model')}")
                    c1.write(f"**Station:** {j.get('station')}")
                    c2.write(f"**Time:** {j.get('user_time')}")
                    c2.write(f"**Problem:** {j.get('failure')}")
                    display_images_with_link(j.get('user_image', ''), "รูปภาพจาก User")

                with st.form("tech_update"):
                    p_name_input = st.text_input("Waiting Part Name", value=j.get('wait_part_name', ""))
                    
                    # ระบบเลือก Status อัตโนมัติถ้ามีการกรอกชื่อพาร์ท
                    default_status = "Wait Part" if p_name_input else (j.get('status') if j.get('status') in ["Complete", "Scrap", "Wait Part"] else "Complete")
                    
                    # ค้นหา Index ของสถานะปัจจุบัน
                    stat_list = ["Complete", "Scrap", "Wait Part"]
                    try:
                        curr_idx = stat_list.index(default_status)
                    except:
                        curr_idx = 0

                    res = st.radio("Status:", stat_list, index=curr_idx, horizontal=True)
                    
                    cls_list = [""] + get_df("class_dropdowns")['classification'].tolist()
                    cls = st.selectbox("Classification", cls_list)
                    case_th = st.text_input("Root Cause (ใส่เมื่อซ่อมเสร็จ)")
                    act_th = st.text_area("Action Taken (ใส่รายละเอียดการซ่อม)")
                    tech_imgs = st.file_uploader("📸 แนบรูปภาพปิดงาน", accept_multiple_files=True)
                    
                    if st.form_submit_button("บันทึกข้อมูล"):
                        # --- การตรวจสอบเงื่อนไขการบันทึก ---
                        # 1. ถ้าเลือก Wait Part: อนุญาตให้บันทึกได้ทันที (เพื่อจองพาร์ทไว้ในระบบ)
                        # 2. ถ้าเลือก Complete/Scrap: ต้องกรอก Root Cause และ Action Taken ให้ครบ
                        can_save = False
                        if res == "Wait Part" and p_name_input:
                            can_save = True
                        elif res in ["Complete", "Scrap"] and case_th and act_th:
                            can_save = True
                        
                        if can_save:
                            with st.spinner("กำลังบันทึกข้อมูล..."):
                                case_en = translate_to_en(case_th)
                                act_en = translate_to_en(act_th)
                                
                                # รวมข้อมูลพาร์ทเข้ากับ Action Taken เฉพาะตอนที่บันทึก
                                final_action = act_en
                                if p_name_input:
                                    # หากเป็น Wait Part ให้ระบุไว้ชัดเจนใน Action
                                    part_info = f" [Waiting Part: {p_name_input}]"
                                    if part_info not in final_action:
                                        final_action += part_info
                                
                                t_urls = upload_images(tech_imgs, "FIX", sn_scan)
                                
                                # บันทึกและล้างชื่อพาร์ทใน Column M (ย้ายไปอยู่ใน Action แทน)
                                ws_main.update_acell(f'B{ridx}', res)
                                ws_main.update(f'J{ridx}:O{ridx}', [[case_en, final_action, cls, "", nick, get_now()]])
                                
                                if t_urls: 
                                    ws_main.update_acell(f'Q{ridx}', t_urls)
                                
                                # แจ้งเตือน LINE
                                icon = "⚠️" if res == "Wait Part" else "✅"
                                line_msg = f"{icon} Update: {res}\nSN: {sn_scan}\nPart: {p_name_input if p_name_input else 'N/A'}\nAction: {final_action}\nTech: {nick}"
                                send_line(line_msg, image_url=t_urls if t_urls else j.get('user_image', ''))
                                
                                st.success("บันทึกสถานะเรียบร้อย!")
                                time.sleep(1)
                                st.rerun()
                        else:
                            if res == "Wait Part" and not p_name_input:
                                st.error("กรุณาระบุชื่อพาร์ทที่ต้องรอ (Waiting Part Name)")
                            else:
                                st.error("กรุณากรอก Root Cause และ Action Taken ให้ครบถ้วนเพื่อปิดงาน")
            else:
                st.warning(f"ไม่พบข้อมูล SN: {sn_scan}")
elif role in ["admin", "super admin"]:
    st.header(f"🏛️ Executive Dashboard: {app_mode}")
    df_report = df_all[df_all['category'] == app_mode].copy()
    df_report['tech_datetime'] = pd.to_datetime(df_report['tech_time'], errors='coerce')
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("งานทั้งหมด", f"{len(df_report)} {unit}")
    m2.metric("Pending", f"{len(df_report[df_report['status']=='Pending'])} {unit}")
    m3.metric("Wait Part", f"{len(df_report[df_report['status']=='Wait Part'])} {unit}")
    m4.metric("Complete/Scrap", f"{len(df_report[df_report['status'].isin(['Complete', 'Scrap'])])} {unit}")
    tabs = st.tabs(["📅 รายงานวันนี้", "📊 รายสัปดาห์", "🖼️ Gallery", "🛠️ Management"])
    with tabs[0]:
        if st.button("📢 ส่งรายงานสรุปประจำวันเข้า LINE", use_container_width=True):
            send_daily_summary(df_all, app_mode)
        st.dataframe(df_report.tail(20), use_container_width=True)
    with tabs[1]:
        weekly_df = df_report[df_report['tech_datetime'].dt.tz_localize(None) >= start_wk] if not df_report.empty else pd.DataFrame()
        if not weekly_df.empty:
            st.bar_chart(weekly_df['classification'].value_counts())
        else: st.info("ไม่มีข้อมูลสัปดาห์นี้")
    with tabs[2]:
        target_sn = st.text_input("🔍 ระบุ SN ดูรูปภาพ").strip().upper()
        if target_sn:
            img_job = df_report[df_report['serial_number'] == target_sn]
            if not img_job.empty:
                row = img_job.iloc[-1]
                c1, c2 = st.columns(2)
                with c1: display_images_with_link(row.get('user_image', ''), "รูปจาก User")
                with c2: display_images_with_link(row.get('tech_image', ''), "รูปจาก Tech")
    with tabs[3]:
        st.data_editor(df_report.tail(50), use_container_width=True)
        if role == "super admin":
            if st.button("♻️ Clear Cache"):
                st.cache_data.clear(); st.cache_resource.clear(); st.rerun()
