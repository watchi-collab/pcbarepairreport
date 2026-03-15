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
from datetime import datetime
from PIL import Image
from deep_translator import GoogleTranslator
from datetime import datetime, timedelta


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
def validate_sn(text):
    """กรองเฉพาะภาษาอังกฤษและตัวเลข (A-Z, 0-9) เท่านั้น"""
    if not text: return ""
    return re.sub(r'[^a-zA-Z0-9]', '', text).upper()

def display_user_images(url_string):
    """แสดงรูปภาพอาการเสียในหน้าช่าง"""
    if not url_string:
        st.info("ไม่มีรูปภาพอาการเสียแนบมา")
        return
    urls = str(url_string).split(",")
    cols = st.columns(min(len(urls), 4))
    for idx, url in enumerate(urls):
        with cols[idx % 4]:
            st.image(url, caption=f"อาการเสีย #{idx+1}", use_container_width=True)
            
# --- ฟังก์ชันช่วยคำนวณช่วงเวลา ---
def get_report_periods():
    tz = pytz.timezone('Asia/Bangkok')
    # ดึงเวลาปัจจุบันแบบมี Timezone แล้วถอด Timezone ออก (.replace(tzinfo=None))
    now = datetime.now(tz).replace(tzinfo=None) 
    
    # หาวันจันทร์ของสัปดาห์นี้
    start_of_week = now - timedelta(days=now.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # หาวันแรกของเดือนนี้
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    return start_of_week, start_of_month

# เรียกใช้ในส่วน Admin
start_wk, start_mo = get_report_periods()
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

    # กรองงานค้าง (ทุกวัน) และงานเสร็จ (เฉพาะวันนี้)
    pending_df = df_mode[df_mode['status'] == 'Pending']
    wait_part_df = df_mode[df_mode['status'] == 'Wait Part']
    done_today_df = df_mode[
        (df_mode['status'].isin(['Complate', 'Scrap'])) & 
        (df_mode['tech_time'].astype(str).str.contains(today_date)) # เช็คจาก Column O
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
            d_cnt = len(wo_data[
                (wo_data['status'].isin(['Complate', 'Scrap'])) & 
                (wo_data['tech_time'].astype(str).str.contains(today_date))
            ])
            
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
            s_d = len(stn_data[(stn_data['status'].isin(['Complate', 'Scrap'])) & (stn_data['tech_time'].astype(str).str.contains(today_date))])
            if (s_p + s_w + s_d) > 0:
                msg += f"Station: {stn}\n"
                msg += f"  - อยู่ระหว่างวิเคราะห์ {s_p} {unit} | รอพาร์ท {s_w} {unit} | ซ่อมเสร็จ {s_d} {unit}\n"
    else:
        msg += f"จำนวน{unit}ที่เสียทั้งหมด {len(pending_df) + len(wait_part_df) + len(done_today_df)} {unit}\n"
        msg += f"  - อยู่ระหว่างวิเคราะห์ {len(pending_df)} {unit}\n"
        msg += f"  - รอพาร์ท {len(wait_part_df)} {unit}\n"
        msg += f"  - ซ่อมเสร็จ {len(done_today_df)} {unit}\n"

    msg += "--------------------------------\n"
    msg += f"รายงานโดย: {st.session_state.nickname}"
    send_line(msg)
    st.success("ส่งรายงานเรียบร้อย!")
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
                st.session_state.update({"is_logged_in":True, "user":u, "role":str(match.iloc[0]['role']).lower(), "nickname":match.iloc[0].get('nickname', u), "app_mode":mode})
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
    sn_edit_input = st.text_input("Scan SN to Edit").strip()
    sn_edit = validate_sn(sn_edit_input)
    
    if sn_edit:
        edit_row = df_all[df_all['serial_number'] == sn_edit]
        if not edit_row.empty:
            with st.expander("Edit Status Only", expanded=True):
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
            p_val = df_m[df_m['model']==sel_m]['product_name'].values[0] if sel_m else ""
            c1.text_input("Product", value=p_val, disabled=True)
            
            sn_input = c1.text_input("Serial Number (Eng/Num Only)").strip()
            sn = validate_sn(sn_input)
            if any("\u0E00" <= char <= "\u0E7F" for char in sn_input):
                st.warning("⚠️ ตรวจพบภาษาไทย! ระบบจะกรองให้เหลือเฉพาะ Eng/ตัวเลข")
            
            wo = c2.text_input("Work Order").strip().upper()
            stat = c2.selectbox("Station", [""] + df_st['station'].tolist())
            fail_th = c2.text_area("อาการเสีย (Problem)")
            u_imgs = st.file_uploader("แนบรูปภาพอาการเสีย", accept_multiple_files=True)
            if st.form_submit_button("ยืนยันแจ้งซ่อม"):
                if sel_m and sn and wo and stat:
                    with st.spinner("Processing..."):
                        fail_en = translate_to_en(fail_th)
                        urls = upload_images(u_imgs, "REQ", sn)
                    new_row = [app_mode, "Pending", wo, sel_m, p_val, sn, stat, fail_en, get_now(), "", "", "", "", "", "", urls]
                    ws_main.append_row(new_row)
                    st.success(f"บันทึกสำเร็จ!"); time.sleep(1); st.rerun()
                else: st.warning("กรุณากรอกข้อมูลให้ครบถ้วน")
    with t2:
        search_q = st.text_input("🔍 ค้นหา SN หรือ Model").strip().upper()
        if not df_all.empty:
            my_jobs = df_all[df_all['category'] == app_mode]
            if search_q:
                my_jobs = my_jobs[(my_jobs['serial_number'].astype(str).str.contains(search_q)) | (my_jobs['model'].astype(str).str.contains(search_q))]
            for idx, row in my_jobs.tail(10).iloc[::-1].iterrows():
                with st.expander(f"📌 {row['status']} | {row['serial_number']} ({row['model']})"):
                    st.write(f"**Station:** {row['station']} | **Problem:** {row['failure']}")

# --- 6. TECHNICIAN INTERFACE ---
elif role == "tech":
    col_main, col_side = st.columns([2, 1])
    with col_main:
        st.header("🔧 Technician Workspace")
        sn_scan_input = st.text_input("🔍 Scan SN เพื่อวิเคราะห์/แก้ไข (English Only)").strip()
        sn_scan = validate_sn(sn_scan_input)
        
        if sn_scan:
            job = df_all[(df_all['serial_number']==sn_scan) & (df_all['category']==app_mode) & (df_all['status'].isin(["Pending", "Wait Part", "Complate"]))]
            if not job.empty:
                j = job.iloc[-1]
                ridx = job.index[-1] + 2 
                
                # --- แสดงรูปภาพที่ User ส่งมา (คอลัมน์ P) ---
                with st.expander("📸 ดูรูปภาพอาการเสียจาก User", expanded=True):
                    display_user_images(j.get('user_image', ''))
                
                if j['status'] == "Complate": st.warning("⚠️ งานนี้ซ่อมเสร็จแล้ว คุณสามารถแก้ไขข้อมูลหรือแนบรูปเพิ่มได้")
                st.info(f"📍 Original Problem: {j['failure']}")
                
                with st.form("tech_update"):
                    current_res = j['status'] if j['status'] in ["Complate", "Scrap", "Wait Part"] else "Complate"
                    res = st.radio("Status:", ["Complate", "Scrap", "Wait Part"], index=["Complate", "Scrap", "Wait Part"].index(current_res), horizontal=True)
                    p_name = st.text_input("Waiting Part Name", value=j.get('wait_part_name', ""))
                    cls_list = [""] + get_df("class_dropdowns")['classification'].tolist()
                    current_cls = j.get('classification', "")
                    cls_idx = cls_list.index(current_cls) if current_cls in cls_list else 0
                    cls = st.selectbox("Classification", cls_list, index=cls_idx)
                    case_th = st.text_input("Root Cause", value=j.get('real_case', ""))
                    act_th = st.text_area("Action Taken", value=j.get('action', ""))
                    tech_imgs = st.file_uploader("📸 แนบรูปภาพขณะซ่อม/ปิดงาน (Column Q)", accept_multiple_files=True)
                    
                    if st.form_submit_button("บันทึกข้อมูล"):
                        if case_th and act_th:
                            with st.spinner("Updating..."):
                                case_en = translate_to_en(case_th)
                                act_en = translate_to_en(act_th)
                                t_urls = upload_images(tech_imgs, "FIX", sn_scan)
                                
                                ws_main.update_acell(f'B{ridx}', res)
                                ws_main.update(f'J{ridx}:O{ridx}', [[case_en, act_en, cls, p_name, nick, get_now()]])
                                if t_urls: ws_main.update_acell(f'Q{ridx}', t_urls)
                            st.success("บันทึกสำเร็จ!"); time.sleep(1); st.rerun()
                        else: st.warning("กรุณากรอกข้อมูลให้ครบ")
            else: st.error("ไม่พบข้อมูล SN นี้")

    with col_side:
        st.subheader("📋 Pending Jobs")
        pending_list = df_all[(df_all['category'] == app_mode) & (df_all['status'].isin(["Pending", "Wait Part"]))]
        if not pending_list.empty:
            display_df = pending_list[['serial_number', 'model', 'status']].copy()
            display_df.columns = ['Serial Number', 'Model', 'Status']
            st.dataframe(display_df, height=600, use_container_width=True, hide_index=True)
        else:
            st.write("No pending jobs 🎉")


# --- ส่วน Admin Panel ฉบับจัดเต็ม ---
elif role in ["admin", "super admin"]:
    st.header(f"🏛️ Executive Admin Dashboard: {app_mode}")
    
    # 1. การคำนวณข้อมูลเบื้องต้น
    unit = "บอร์ด" if app_mode == "PCBA" else "เครื่อง"
    df_report = df_all[df_all['category'] == app_mode].copy()
    # แปลง tech_time เป็น DateTime Object (Column O)
   df_report['tech_datetime'] = pd.to_datetime(df_report['tech_time'], errors='coerce').dt.tz_localize(None)

    # 2. Executive Summary Metrics (รวมทุกอย่าง)
    m1, m2, m3, m4 = st.columns(4)
    total_all = len(df_report)
    total_pending = len(df_report[df_report['status'] == 'Pending'])
    total_wait = len(df_report[df_report['status'] == 'Wait Part'])
    total_done = len(df_report[df_report['status'].isin(['Complate', 'Scrap'])])
    
    m1.metric("งานทั้งหมดในระบบ", f"{total_all} {unit}")
    m2.metric("วิเคราะห์อยู่", f"{total_pending} {unit}", delta_color="inverse")
    m3.metric("รออะไหล่", f"{total_wait} {unit}", delta_color="inverse")
    m4.metric("ปิดงานแล้ว", f"{total_done} {unit}")

    st.divider()

    # 3. ส่วนรายงานแยกตาม Tab
    tab_daily, tab_weekly, tab_monthly, tab_manage = st.tabs([
        "📅 รายงานวันนี้", "📊 สรุปรายสัปดาห์ (Mon-Sun)", "🗓️ สรุปรายเดือน", "🛠️ จัดการข้อมูล Raw Data"
    ])

    # --- TAB: รายวัน ---
    with tab_daily:
        st.subheader("📌 Daily Performance")
        if st.button("📢 ส่งรายงานสรุปเข้า LINE Group ทันที", use_container_width=True, type="primary"):
            send_daily_summary(df_all, app_mode)
        
        # แสดงรายการงานที่ทำเสร็จวันนี้
        today_str = datetime.now(pytz.timezone('Asia/Bangkok')).strftime("%Y-%m-%d")
        done_today = df_report[df_report['tech_time'].astype(str).str.contains(today_str)]
        if not done_today.empty:
            st.write("**งานที่ทำความเคลื่อนไหววันนี้:**")
            st.dataframe(done_today[['serial_number', 'model', 'status', 'real_case', 'action']], use_container_width=True)
        else:
            st.info("วันนี้ยังไม่มีการบันทึกงานเสร็จในระบบ")

    # --- TAB: รายสัปดาห์ ---
    with tab_weekly:
        st.subheader(f"📅 Weekly Report: {start_wk.strftime('%d %b')} - { (start_wk + timedelta(days=6)).strftime('%d %b') }")
        
        weekly_df = df_report[df_report['tech_datetime'] >= start_wk]
        
        c1, c2 = st.columns([1, 2])
        with c1:
            w_done = len(weekly_df[weekly_df['status'].isin(['Complate', 'Scrap'])])
            st.metric("Total Completed (This Week)", f"{w_done} {unit}")
            st.write("**สถานะงานค้างปัจจุบัน:**")
            st.write(f"- อยู่ระหว่างวิเคราะห์: {total_pending}")
            st.write(f"- รอพาร์ท: {total_wait}")
            
        with c2:
            # กราฟแท่งแสดงยอดเสร็จรายวัน (Mon-Sun)
            weekly_chart_data = weekly_df[weekly_df['status'].isin(['Complate', 'Scrap'])]
            if not weekly_chart_data.empty:
                daily_counts = weekly_chart_data.groupby(weekly_chart_data['tech_datetime'].dt.day_name()).size()
                days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                daily_counts = daily_counts.reindex(days_order, fill_value=0)
                st.bar_chart(daily_counts)
            else:
                st.write("ยังไม่มีข้อมูลกราฟสำหรับสัปดาห์นี้")

    # --- TAB: รายเดือน ---
    with tab_monthly:
        st.subheader(f"🗓️ Monthly Overview: {start_mo.strftime('%B %Y')}")
        monthly_df = df_report[df_report['tech_datetime'] >= start_mo]
        
        m_col1, m_col2 = st.columns(2)
        with m_col1:
            m_done = len(monthly_df[monthly_df['status'].isin(['Complate', 'Scrap'])])
            st.info(f"ยอดซ่อมเสร็จสะสมเดือนนี้: **{m_done} {unit}**")
            
            # สรุปอาการเสียยอดฮิต
            if 'classification' in monthly_df.columns:
                st.write("**5 อันดับสาเหตุที่พบมากที่สุด:**")
                st.write(monthly_df['classification'].value_counts().head(5))

        with m_col2:
            if not monthly_df.empty:
                st.write("**สัดส่วนสถานะงานเดือนนี้ (Pie Chart)**")
                status_dist = monthly_df['status'].value_counts()
                st.bar_chart(status_dist)

    # --- TAB: จัดการข้อมูล (Raw Data) ---
    with tab_manage:
        st.subheader("🔍 ค้นหาและแก้ไขข้อมูลเชิงลึก")
        search_filter = st.text_input("กรองข้อมูลด้วย SN / WO / Model").upper()
        
        final_df = df_report.copy()
        if search_filter:
            final_df = final_df[
                (final_df['serial_number'].str.contains(search_filter)) | 
                (final_df['work_order'].str.contains(search_filter)) |
                (final_df['model'].str.contains(search_filter))
            ]
            
        # ปุ่ม Download สำหรับไปทำ Excel ต่อ
        csv = final_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 Download Data as CSV (for Excel)",
            data=csv,
            file_name=f'repair_export_{app_mode}_{datetime.now().strftime("%Y%m%d")}.csv',
            mime='text/csv'
        )

        # แก้ไขข้อมูลหน้าตาราง
        edited_df = st.data_editor(final_df, use_container_width=True, num_rows="dynamic", hide_index=True)
        if st.button("💾 บันทึกการแก้ไขข้อมูลทั้งหมด (ระวัง!)"):
            # ส่วนนี้หากต้องการ Implement การ Save กลับทั้งตารางต้องเขียนลูป Update Worksheet
            st.warning("ระบบ Data Editor แนะนำให้ใช้สำหรับการเตรียมข้อมูลเพื่อ Copy/Paste หรือ Export หากต้องการแก้ไขรายตัวแนะนำใช้ Sidebar")
