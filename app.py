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
    if not text: return ""
    return re.sub(r'[^a-zA-Z0-9]', '', text).upper()

def display_user_images(url_string):
    if not url_string:
        st.info("ไม่มีรูปภาพอาการเสียแนบมา")
        return
    urls = str(url_string).split(",")
    cols = st.columns(min(len(urls), 4))
    for idx, url in enumerate(urls):
        with cols[idx % 4]:
            st.image(url, caption=f"อาการเสีย #{idx+1}", use_container_width=True)

def get_report_periods():
    tz = pytz.timezone('Asia/Bangkok')
    now = datetime.now(tz).replace(tzinfo=None) 
    start_of_week = now - timedelta(days=now.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start_of_week, start_of_month

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
    
    # กรองข้อมูลตาม PCBA หรือ Machine
    df_mode = df[df['category'] == app_mode].copy()
    
    if df_mode.empty:
        st.warning("ไม่มีข้อมูลสำหรับรายงาน")
        return

    unit = "บอร์ด" if app_mode == "PCBA" else "เครื่อง"
    msg = f"รายงานผลการ \"Repair\" ประจำวันที่ {today_display}\n"
    msg += f"ส่วนงาน: {app_mode}\n"
    msg += "--------------------------------\n"

    # กรองงานค้าง (ย้อนหลังทั้งหมด) และงานที่เสร็จ (เฉพาะวันนี้)
    pending_df = df_mode[df_mode['status'] == 'Pending']
    wait_part_df = df_mode[df_mode['status'] == 'Wait Part']
    done_today_df = df_mode[
        (df_mode['status'].isin(['Complate', 'Scrap'])) & 
        (df_mode['tech_time'].astype(str).str.contains(today_date))
    ]
    
    # รวมรายชื่อ WO ที่ต้องรายงาน (มีงานค้าง หรือ เสร็จวันนี้)
    wo_list = pd.concat([pending_df, wait_part_df, done_today_df])['work_order'].unique()

    if len(wo_list) == 0:
        msg += f"ไม่มีงานค้างและไม่มีงานเสร็จในวันนี้ 🎉\n"
    else:
        for wo in sorted(wo_list):
            if not wo: continue
            wo_data = df_mode[df_mode['work_order'] == wo]
            
            # คำนวณยอดเฉพาะใน WO นั้นๆ
            cnt_pending = len(wo_data[wo_data['status'] == 'Pending'])
            cnt_wait = len(wo_data[wo_data['status'] == 'Wait Part'])
            cnt_done_today = len(wo_data[
                (wo_data['status'].isin(['Complate', 'Scrap'])) & 
                (wo_data['tech_time'].astype(str).str.contains(today_date))
            ])
            
            total_wo = cnt_pending + cnt_wait + cnt_done_today
            
            # รายงานเฉพาะ WO ที่มียอดรวมมากกว่า 0 (มีงานค้างหรือเสร็จวันนี้)
            if total_wo > 0:
                msg += f"WO. {wo}\n"
                msg += f"จำนวน{unit}ที่เสียทั้งหมด {total_wo} {unit}\n"
                msg += f"  - อยู่ระหว่างวิเคราะห์ {cnt_pending} {unit}\n"
                msg += f"  - รอพาร์ท {cnt_wait} {unit}\n"
                msg += f"  - ซ่อมเสร็จ {cnt_done_today} {unit}\n"

    # --- ส่วนสรุปภาพรวม ---
    msg += "--------------------------------\n"
    msg += f"สรุปภาพรวม {app_mode}\n"
    
    if app_mode == "Machine":
        # แยกตาม Station สำหรับ Machine
        for stn in sorted(df_mode['station'].unique()):
            if not stn: continue
            stn_data = df_mode[df_mode['station'] == stn]
            
            s_pending = len(stn_data[stn_data['status'] == 'Pending'])
            s_wait = len(stn_data[stn_data['status'] == 'Wait Part'])
            s_done = len(stn_data[
                (stn_data['status'].isin(['Complate', 'Scrap'])) & 
                (stn_data['tech_time'].astype(str).str.contains(today_date))
            ])
            
            total_stn = s_pending + s_wait + s_done
            if total_stn > 0:
                msg += f"Station: {stn}\n"
                msg += f"  จำนวน{unit}ที่เสียทั้งหมด {total_stn} {unit}\n"
                msg += f"    - อยู่ระหว่างวิเคราะห์ {s_pending} {unit}\n"
                msg += f"    - รอพาร์ท {s_wait} {unit}\n"
                msg += f"    - ซ่อมเสร็จ {s_done} {unit}\n"
    else:
        # สรุปยอดรวม PCBA
        total_p = len(pending_df)
        total_w = len(wait_part_df)
        total_d = len(done_today_df)
        msg += f"จำนวน{unit}ที่เสียทั้งหมด {total_p + total_w + total_d} {unit}\n"
        msg += f"  - อยู่ระหว่างวิเคราะห์ {total_p} {unit}\n"
        msg += f"  - รอพาร์ท {total_w} {unit}\n"
        msg += f"  - ซ่อมเสร็จ {total_d} {unit}\n"

    msg += "--------------------------------\n"
    msg += f"รายงานโดย: {st.session_state.nickname}"
    
    send_line(msg)
    st.success("ส่งรายงานแยกสถานะเรียบร้อยแล้ว")

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
            res = cloudinary.uploader.upload(buf, folder="repair_system", public_id=f"{prefix}_{sn}_{int(time.time())}_{i+1}", format="jpg")
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
unit = "บอร์ด" if app_mode == "PCBA" else "เครื่อง"

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

# --- 5. INTERFACES ---
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
            wo = c2.text_input("Work Order").strip().upper()
            stat = c2.selectbox("Station", [""] + df_st['station'].tolist())
            fail_th = c2.text_area("อาการเสีย (Problem)")
            u_imgs = st.file_uploader("แนบรูปภาพอาการเสีย", accept_multiple_files=True)
            if st.form_submit_button("ยืนยันแจ้งซ่อม"):
                if sel_m and sn and wo and stat:
                    fail_en = translate_to_en(fail_th)
                    urls = upload_images(u_imgs, "REQ", sn)
                    new_row = [app_mode, "Pending", wo, sel_m, p_val, sn, stat, fail_en, get_now(), "", "", "", "", "", "", urls]
                    ws_main.append_row(new_row)
                    st.success("บันทึกสำเร็จ!"); time.sleep(1); st.rerun()
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
                display_user_images(j.get('user_image', ''))
                
                with st.form("tech_update"):
                    res = st.radio("Status:", ["Complate", "Scrap", "Wait Part"], horizontal=True)
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
                            
                            # 1. บันทึกข้อมูลลง Google Sheets
                            ws_main.update_acell(f'B{ridx}', res)
                            ws_main.update(f'J{ridx}:O{ridx}', [[case_en, act_en, cls, p_name, nick, get_now()]])
                            if t_urls: 
                                ws_main.update_acell(f'Q{ridx}', t_urls)
                            
                            # 2. ส่งแจ้งเตือน LINE เฉพาะเมื่อสถานะเป็น Complate หรือ Scrap
                            if res in ["Complate", "Scrap"]:
                                try:
                                    tech_msg = f"✅ งานซ่อมเสร็จสิ้น! ({app_mode})\n"
                                    tech_msg += f"SN: {sn_scan}\n"
                                    tech_msg += f"สถานะ: {res}\n"
                            
                                   
                                    tech_msg += f"การแก้ไข: {act_th}\n"
                                    tech_msg += f"ช่างผู้ดูแล: {nick}"
                                    

                            st.success("บันทึกสำเร็จ!")
                            time.sleep(1.5)
                            st.rerun()
                        else:
                            st.error("กรุณากรอก Root Cause และ Action Taken ก่อนบันทึก")
            else:
                st.error("ไม่พบข้อมูล Serial Number นี้ในระบบ")
    with col_side:
        st.subheader("📋 Pending Jobs")
        pending_list = df_all[(df_all['category'] == app_mode) & (df_all['status'].isin(["Pending", "Wait Part"]))]
        st.dataframe(pending_list[['serial_number', 'model', 'status']], use_container_width=True, hide_index=True)

elif role in ["admin", "super admin"]:
    st.header(f"🏛️ Executive Admin Dashboard: {app_mode}")
    df_report = df_all[df_all['category'] == app_mode].copy()
    df_report['tech_datetime'] = pd.to_datetime(df_report['tech_time'], errors='coerce').dt.tz_localize(None)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("งานทั้งหมด", f"{len(df_report)} {unit}")
    m2.metric("วิเคราะห์อยู่", f"{len(df_report[df_report['status']=='Pending'])} {unit}")
    m3.metric("รออะไหล่", f"{len(df_report[df_report['status']=='Wait Part'])} {unit}")
    m4.metric("ปิดงานแล้ว", f"{len(df_report[df_report['status'].isin(['Complate', 'Scrap'])])} {unit}")

    tab_daily, tab_weekly, tab_monthly, tab_manage = st.tabs(["📅 รายงานวันนี้", "📊 รายสัปดาห์", "🗓️ รายเดือน", "🛠️ Raw Data"])
    
    with tab_daily:
        if st.button("📢 ส่งรายงาน LINE", use_container_width=True):
            send_daily_summary(df_all, app_mode)
        st.dataframe(df_report.tail(10), use_container_width=True)

 # --- TAB: รายสัปดาห์ (เจาะลึก Classification & Station) ---
    with tab_weekly:
        st.subheader(f"📊 Weekly Analytics: {start_wk.strftime('%d %b')} - Present")
        
        # กรองข้อมูลเฉพาะสัปดาห์นี้
        weekly_df = df_report[df_report['tech_datetime'] >= start_wk].copy()
        
        if not weekly_df.empty:
            # 1. สรุปภาพรวมด้วย Metrics
            c1, c2, c3 = st.columns(3)
            w_done = len(weekly_df[weekly_df['status'].isin(['Complate', 'Scrap'])])
            w_wait = len(weekly_df[weekly_df['status'] == 'Wait Part'])
            c1.metric("ซ่อมเสร็จสัปดาห์นี้", f"{w_done} {unit}")
            c2.metric("รอพาร์ทใหม่", f"{w_wait} {unit}")
            c3.metric("งานใหม่สัปดาห์นี้", f"{len(weekly_df)} {unit}")

            st.divider()

            # 2. วิเคราะห์ตาม Classification และ Station
            col_left, col_right = st.columns(2)

            with col_left:
                st.write("🔍 **สาเหตุงานเสีย (Classification)**")
                if 'classification' in weekly_df.columns and not weekly_df['classification'].isnull().all():
                    class_counts = weekly_df['classification'].value_counts().reset_index()
                    class_counts.columns = ['สาเหตุ', 'จำนวน']
                    st.bar_chart(class_counts.set_index('สาเหตุ'))
                else:
                    st.info("ยังไม่มีข้อมูล Classification")

            with col_right:
                st.write("📍 **สถานีที่เกิดปัญหา (Station)**")
                if 'station' in weekly_df.columns:
                    station_counts = weekly_df['station'].value_counts().reset_index()
                    station_counts.columns = ['Station', 'จำนวน']
                    st.dataframe(station_counts, use_container_width=True, hide_index=True)
                else:
                    st.info("ไม่มีข้อมูล Station")

            # 3. ตารางแจกแจงละเอียด (Heatmap-like Table)
            st.write("📋 **ตารางสรุปสาเหตุแยกตาม Station**")
            pivot_df = weekly_df.pivot_table(
                index='station', 
                columns='classification', 
                aggfunc='size', 
                fill_value=0
            )
            st.dataframe(pivot_df, use_container_width=True)

            # 4. ส่วน Export Excel (ย้ายมาไว้ด้านล่างเพื่อให้ดูเป็นขั้นตอนสุดท้าย)
            st.divider()
            st.subheader("📥 Download Weekly Analysis")
            
            output = io.BytesIO()
            try:
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    # Sheet 1: ข้อมูลดิบ
                    weekly_df.to_excel(writer, sheet_name='Weekly_Raw_Data', index=False)
                    # Sheet 2: สรุป Pivot
                    pivot_df.to_excel(writer, sheet_name='Station_Class_Summary')
                    
                    # ปรับความกว้างคอลัมน์
                    workbook = writer.book
                    for worksheet in writer.sheets.values():
                        worksheet.set_column('A:Z', 18)

                processed_data = output.getvalue()
                st.download_button(
                    label="🟢 Download Weekly Report (Excel)",
                    data=processed_data,
                    file_name=f'Weekly_Repair_Report_{start_wk.strftime("%Y%m%d")}.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"ไม่สามารถสร้างไฟล์ Excel ได้: {e}")

        else:
            st.warning("⚠️ ยังไม่มีข้อมูลการซ่อมในสัปดาห์นี้")
    with tab_monthly:
        st.subheader(f"Monthly: {start_mo.strftime('%B %Y')}")
        monthly_df = df_report[df_report['tech_datetime'] >= start_mo]
        if not monthly_df.empty:
            st.write(f"ปิดงานสะสม: {len(monthly_df[monthly_df['status'].isin(['Complate', 'Scrap'])])}")
            if 'classification' in monthly_df.columns:
                st.bar_chart(monthly_df['classification'].value_counts().head(5))
                # --- เพิ่มแท็บ "ค้นหารูปภาพ (Image Gallery)" ---
    with tab_manage: # หรือจะสร้าง tab_gallery = st.tabs([...]) เพิ่มก็ได้ครับ
        st.subheader("🖼️ ค้นหาและดึงรูปภาพเพื่อทำ Report")
        
        col_search1, col_search2 = st.columns([2, 1])
        with col_search1:
            target_sn = st.text_input("🔍 ระบุ Serial Number เพื่อดูรูปภาพ").strip().upper()
        
        if target_sn:
            # ค้นหาข้อมูลจาก SN ที่ระบุ
            img_job = df_report[df_report['serial_number'] == target_sn]
            
            if not img_job.empty:
                row = img_job.iloc[-1]
                
                c_img1, c_img2 = st.columns(2)
                
                with c_img1:
                    st.write("📸 **รูปจากผู้แจ้งซ่อม (User)**")
                    user_imgs = str(row.get('user_image', '')).split(',')
                    if user_imgs[0]:
                        for u_url in user_imgs:
                            st.image(u_url, use_container_width=True)
                            st.code(u_url) # แสดง Link ให้ก๊อปปี้ไปใส่ใน PP ได้เลย
                    else:
                        st.info("ไม่มีรูปจากผู้แจ้ง")

                with c_img2:
                    st.write("🔧 **รูปจากช่างซ่อม (Technician)**")
                    tech_imgs = str(row.get('tech_image', '')).split(',') # ตรวจสอบคอลัมน์ Q
                    if tech_imgs[0]:
                        for t_url in tech_imgs:
                            st.image(t_url, use_container_width=True)
                            st.code(t_url) # แสดง Link สำหรับทำ Report
                    else:
                        st.info("ไม่มีรูปจากช่าง")
            else:
                st.warning("ไม่พบข้อมูล Serial Number นี้ในระบบ")

    with tab_manage:
        search_f = st.text_input("Filter Raw Data").upper()
        final_df = df_report[df_report['serial_number'].str.contains(search_f)] if search_f else df_report
        st.download_button("📥 Download CSV", final_df.to_csv(index=False).encode('utf-8-sig'), "report.csv", "text/csv")
        st.data_editor(final_df, use_container_width=True)

# --- เพิ่มแท็บ System Health Check ---
    with tab_manage: # หรือเปลี่ยนเป็น tab_health ถ้าคุณสร้างเพิ่ม
        st.divider()
        st.subheader("🛠️ System Health Check")
        
        c1, c2, c3 = st.columns(3)
        
        # 1. ตรวจสอบการเชื่อมต่อ Google Sheets
        with c1:
            try:
                if df_all is not None:
                    st.success("✅ Google Sheets")
                    st.caption(f"Connected: {len(df_all)} records")
                else:
                    st.error("❌ Google Sheets")
            except:
                st.error("❌ Google Sheets Connection Lost")

        # 2. ตรวจสอบ Cloudinary (ระบบรูปภาพ)
        with c2:
            try:
                import cloudinary
                # ลองดึง config ออกมาเช็ค
                if cloudinary.config().cloud_name:
                    st.success("✅ Cloudinary API")
                    st.caption("Image Server: Online")
                else:
                    st.warning("⚠️ Cloudinary Config Missing")
            except:
                st.error("❌ Cloudinary Module Error")

    

        # เพิ่มปุ่มสำหรับ Clear Cache กรณีข้อมูลไม่อัปเดต
        st.write("---")
        if st.button("♻️ Refresh System Cache", use_container_width=True):
            st.cache_data.clear()
            st.cache_resource.clear()
            st.success("ล้างแคชเรียบร้อยแล้ว! ข้อมูลจะถูกดึงใหม่ทั้งหมด")
            st.rerun()
