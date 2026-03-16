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
        
        # ปรับให้ใช้จาก secrets เพื่อความปลอดภัย
        cloudinary.config(
            cloud_name = st.secrets["cloudinary"]["cloud_name"], 
            api_key = st.secrets["cloudinary"]["api_key"],
            api_secret = st.secrets["cloudinary"]["api_secret"], 
            secure = True
        )
        return ss, True
    except Exception as e: return e, False

ss, success = init_all()
if not success:
    st.error(f"❌ Connection Error: {ss}"); st.stop()

# --- 2. HELPERS (New Log & Validation Included) ---

def write_log(action, details=""):
    """ บันทึก Log การใช้งานลงใน Worksheet 'logs' """
    try:
        ws_log = ss.worksheet("logs")
        new_row = [
            get_now(), 
            st.session_state.get("user", "System"),
            st.session_state.get("nickname", "Unknown"),
            st.session_state.get("app_mode", "N/A"),
            action, 
            details
        ]
        ws_log.append_row(new_row)
    except: pass # ป้องกันระบบค้างถ้าเขียน Log ไม่สำเร็จ

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

def send_line(msg):
    token = st.secrets.get("line_channel_access_token")
    group_id = st.secrets.get("line_group_id")
    if not token or not group_id: return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    payload = {"to": group_id, "messages": [{"type": "text", "text": msg}]}
    try: requests.post(url, headers=headers, json=payload)
    except: pass

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
    
    if app_mode == "Machine":
        for stn in sorted(df_mode['station'].unique()):
            stn_data = df_mode[df_mode['station'] == stn]
            s_p = len(stn_data[stn_data['status'] == 'Pending'])
            s_w = len(stn_data[stn_data['status'] == 'Wait Part'])
            s_d = len(stn_data[(stn_data['status'].isin(['Complete', 'Scrap'])) & (stn_data['tech_time'].astype(str).str.contains(today_date))])
            if (s_p + s_w + s_d) > 0:
                msg += f"Station: {stn}\n"
                msg += f"  - อยู่ระหว่างวิเคราะห์ {s_p} {unit} | รอพาร์ท {s_w} {unit} | ซ่อมเสร็จ {s_d} {unit}\n"
    else:
        msg += f"รวม {app_mode}: วิเคราะห์ {len(pending_df)} | รอพาร์ท {len(wait_part_df)} | เสร็จ {len(done_today_df)} {unit}\n"

    msg += "--------------------------------\n"
    msg += f"รายงานโดย: {st.session_state.nickname}"
    send_line(msg)
    write_log("SEND_DAILY_REPORT", f"Mode: {app_mode}")
    st.success("ส่งรายงานเรียบร้อย!")

def display_images_with_link(url_string, caption_prefix="รูปภาพ"):
    if not url_string:
        st.info(f"ไม่มี{caption_prefix}")
        return
    urls = [u.strip() for u in str(url_string).split(",") if u.strip()]
    for idx, url in enumerate(urls):
        st.image(url, caption=f"{caption_prefix} #{idx+1}", use_container_width=True)
        st.code(url)

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
                write_log("LOGIN", f"Logged in to {mode}")
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
                    write_log("QUICK_EDIT_STATUS", f"SN: {sn_edit} -> {new_stat}")
                    st.success("Updated!"); time.sleep(1); st.rerun()
        else: st.warning("ไม่พบ SN")
    
    st.divider()
    if st.button("🚪 ออกจากระบบ", use_container_width=True):
        write_log("LOGOUT")
        st.session_state.is_logged_in = False; st.rerun()

# --- 6. INTERFACES BY ROLE ---

# --- ROLE: USER ---
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
            sn_input = c1.text_input("Serial Number").strip()
            sn = validate_sn(sn_input)
            wo = c2.text_input("Work Order").strip().upper()
            stat = c2.selectbox("Station", [""] + df_st['station'].tolist())
            fail_th = c2.text_area("อาการเสีย (Problem)")
            u_imgs = st.file_uploader("แนบรูปภาพอาการเสีย", accept_multiple_files=True)
            
            if st.form_submit_button("ยืนยันแจ้งซ่อม", use_container_width=True):
                if sel_m and sn and wo and stat:
                    with st.spinner("กำลังส่งข้อมูล..."):
                        fail_en = translate_to_en(fail_th)
                        urls = upload_images(u_imgs, "REQ", sn)
                        new_row = [app_mode, "Pending", wo, sel_m, p_val, sn, stat, fail_en, get_now(), "", "", "", "", "", "", urls]
                        ws_main.append_row(new_row)
                        send_line(f"🚨 แจ้งซ่อมใหม่!\nMode: {app_mode}\nSN: {sn}\nModel: {sel_m}\nProblem: {fail_en}\nBy: {nick}")
                        st.success(f"บันทึกสำเร็จ!"); time.sleep(1); st.rerun()
                else: st.warning("กรุณากรอกข้อมูลให้ครบถ้วน")
    
    with t2:
        search_q = st.text_input("🔍 ค้นหา SN หรือ Model (10 รายการล่าสุด)").strip().upper()
        my_jobs = df_all[df_all['category'] == app_mode]
        if search_q:
            my_jobs = my_jobs[(my_jobs['serial_number'].str.contains(search_q)) | (my_jobs['model'].str.contains(search_q))]
        for idx, row in my_jobs.tail(10).iloc[::-1].iterrows():
            with st.expander(f"📌 {row['status']} | {row['serial_number']} ({row['model']})"):
                st.write(f"**Station:** {row['station']} | **Problem:** {row['failure']}")

elif role == "tech":
    col_main, col_side = st.columns([2, 1])
    with col_main:
        st.header("🔧 Technician Workspace")
        sn_scan = validate_sn(st.text_input("🔍 Scan SN เพื่อวิเคราะห์/แก้ไข").strip())
        if sn_scan:
            job = df_all[(df_all['serial_number']==sn_scan) & (df_all['category']==app_mode)]
            if not job.empty:
                j = job.iloc[-1]
                ridx = job.index[-1] + 2
                display_images_with_link(j.get('user_image', ''), "รูปอาการเสียจาก User")
                
                with st.form("tech_update"):
                    res = st.radio("Status:", ["Complete", "Scrap", "Wait Part"], horizontal=True)
                    p_name = st.text_input("Waiting Part Name", value=j.get('wait_part_name', ""))
                    cls_list = [""] + get_df("class_dropdowns")['classification'].tolist()
                    cls = st.selectbox("Classification", cls_list)
                    case_th = st.text_input("Root Cause")
                    act_th = st.text_area("Action Taken")
                    tech_imgs = st.file_uploader("📸 แนบรูปภาพปิดงาน", accept_multiple_files=True)
                    
                    if st.form_submit_button("บันทึกข้อมูล"):
                        if case_th and act_th:
                            case_en = translate_to_en(case_th)
                            act_en = translate_to_en(act_th)
                            t_urls = upload_images(tech_imgs, "FIX", sn_scan)
                            
                            ws_main.update_acell(f'B{ridx}', res)
                            ws_main.update(f'J{ridx}:O{ridx}', [[case_en, act_en, cls, p_name, nick, get_now()]])
                            if t_urls: ws_main.update_acell(f'Q{ridx}', t_urls)
                            
                            write_log("TECH_UPDATE", f"SN: {sn_scan}, Status: {res}")

                            if res in ["Complete", "Scrap"]:
                                try:
                                    tech_msg = f"✅ งานซ่อมเสร็จสิ้น! ({app_mode})\nSN: {sn_scan}\nสถานะ: {res}\nช่าง: {nick}"
                                    send_line(tech_msg)
                                except: pass
                            
                            st.success("บันทึกสำเร็จ!"); time.sleep(1.5); st.rerun()
                        else: st.error("กรุณากรอก Root Cause และ Action Taken ก่อนบันทึก")
            else: st.error("ไม่พบข้อมูล Serial Number นี้ในระบบ")
    
    with col_side:
        st.subheader("📋 งานค้าง (Pending)")
        pending_list = df_all[(df_all['category'] == app_mode) & (df_all['status'].isin(["Pending", "Wait Part"]))]
        st.dataframe(pending_list[['serial_number', 'model', 'status']], use_container_width=True, hide_index=True)

elif role in ["admin", "super admin"]:
    st.header(f"🏛️ Executive Dashboard: {app_mode}")
    df_report = df_all[df_all['category'] == app_mode].copy()
    df_report['tech_datetime'] = pd.to_datetime(df_report['tech_time'], errors='coerce').dt.tz_localize(None)

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
        weekly_df = df_report[df_report['tech_datetime'] >= start_wk].copy()
        if not weekly_df.empty:
            c1, c2 = st.columns(2)
            with c1:
                st.write("**Classification Breakdown**")
                st.bar_chart(weekly_df['classification'].value_counts())
            with c2:
                st.write("**Station Breakdown**")
                st.dataframe(weekly_df['station'].value_counts(), use_container_width=True)
        else: st.info("ไม่มีข้อมูลสัปดาห์นี้")

    with tabs[2]:
        target_sn = st.text_input("🔍 ระบุ SN เพื่อดูรูปภาพประกอบ Report").strip().upper()
        if target_sn:
            img_job = df_report[df_report['serial_number'] == target_sn]
            if not img_job.empty:
                row = img_job.iloc[-1]
                c_img1, c_img2 = st.columns(2)
                with c_img1: display_images_with_link(row.get('user_image', ''), "รูปจาก User")
                with c_img2: display_images_with_link(row.get('tech_image', ''), "รูปจาก Tech")
            else: st.warning("ไม่พบ SN")

    with tabs[3]:
        st.subheader("📝 Edit Raw Data")
        edited_df = st.data_editor(df_report.tail(50), use_container_width=True)
        
        if role == "super admin":
            st.divider()
            st.subheader("🔑 Super Admin Panel")
            s_col1, s_col2 = st.columns(2)
            with s_col1:
                st.write("👥 **User Management**")
                df_u = get_df("users")
                st.dataframe(df_u, hide_index=True)
                with st.expander("Add New User"):
                    nu = st.text_input("Username")
                    np = st.text_input("Password", type="password")
                    nn = st.text_input("Nickname")
                    nr = st.selectbox("Role", ["user", "tech", "admin", "super admin"])
                    if st.button("Save User"):
                        ss.worksheet("users").append_row([nu, np, nr, nn])
                        write_log("ADD_USER", f"Added user: {nu}")
                        st.success("User added!"); st.rerun()
            with s_col2:
                st.write("🚨 **Danger Zone**")
                if st.button("♻️ Clear System Cache"):
                    st.cache_data.clear(); st.cache_resource.clear(); st.rerun()
                del_sn = st.text_input("ระบุ SN ที่จะลบถาวร")
                if st.button("🗑️ Delete Record", type="secondary"):
                    try:
                        cell = ws_main.find(del_sn)
                        ws_main.delete_rows(cell.row)
                        write_log("DELETE_RECORD", f"Deleted SN: {del_sn}")
                        st.error(f"Deleted SN {del_sn}"); time.sleep(1); st.rerun()
                    except: st.warning("SN not found")
