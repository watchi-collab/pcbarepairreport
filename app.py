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

def send_line(msg, image_url=None, to_summary=False):
    # ดึงค่าจาก st.secrets
    token = st.secrets.get("line_channel_access_token") 
    
    # กำหนด Group ID ตามเงื่อนไข
    GROUP_ID_REPAIR = "C54883d9bd6b1293ff2bad0ba497a80d7"  # กลุ่มแจ้งซ่อมเดิม
    GROUP_ID_SUMMARY = "Ce5d4d803cd538c97b007d75cb406306c" # กลุ่มส่งรายงานใหม่
    
    # เลือกกลุ่มเป้าหมาย
    target_id = GROUP_ID_SUMMARY if to_summary else GROUP_ID_REPAIR
    
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
    
    # ถ้ามีรูปภาพแนบมา
    if image_url:
        first_img = image_url.split(',')[0].strip()
        if first_img.startswith("http"):
            messages.append({
                "type": "image",
                "originalContentUrl": first_img,
                "previewImageUrl": first_img
            })
        
    payload = {
        "to": target_id,
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
    import pytz
    from datetime import datetime
    import pandas as pd
    
    # 1. ตั้งค่าเวลา
    tz = pytz.timezone('Asia/Bangkok')
    now = datetime.now(tz)
    today_str = now.strftime("%Y-%m-%d")
    today_display = now.strftime("%d/%m/%Y")
    nick = st.session_state.get('nickname', 'Unknown')

    # 2. แก้ปัญหา KeyError: ใช้คอลัมน์ 'user_time' ตามรูปภาพในชีท
    # ตรวจสอบว่ามีคอลัมน์ user_time หรือไม่
    target_date_col = 'user_time'
    if target_date_col not in df.columns:
        st.error(f"❌ ไม่พบคอลัมน์ '{target_date_col}' ในไฟล์ (กรุณาตรวจสอบชื่อหัวคอลัมน์)")
        return

    # สร้างคอลัมน์ date_only สำหรับกรองข้อมูลวันที่
    df['date_only'] = pd.to_datetime(df[target_date_col]).dt.strftime('%Y-%m-%d')
    
    # 3. LOGIC การกรองข้อมูล: งานวันนี้ทั้งหมด + งานค้างสะสม (Pending/Wait Part)
    # ใช้คอลัมน์ 'status' ตามรูปภาพ (คอลัมน์ B)
    condition = (df['date_only'] == today_str) | (df['status'].isin(['Pending', 'Wait Part']))
    df_report = df[condition].copy()

    if df_report.empty:
        st.warning(f"📅 ไม่มีรายการงานของวันที่ {today_display} และไม่มีงานค้างสะสม")
        return

    # ฟังก์ชันช่วยสร้างข้อความ (ใช้ 'work_order' คอลัมน์ C)
    def build_report_format(df_sec, section_name, unit_text):
        if df_sec.empty: return None
        
        msg = f"รายงานผลการ \"Repair\" ประจำวันที่ {today_display}\n"
        msg += f"ส่วนงาน: {section_name}\n"
        msg += "--------------------------------\n"
        
        # วนลูปตาม work_order (คอลัมน์ C)
        wo_list = df_sec['work_order'].unique()
        for wo in wo_list:
            if not wo: continue
            wo_data = df_sec[df_sec['work_order'] == wo]
            
            total_wo = len(wo_data)
            p_pending = len(wo_data[wo_data['status'] == 'Pending'])
            p_wait = len(wo_data[wo_data['status'] == 'Wait Part'])
            p_done = len(wo_data[wo_data['status'].isin(['Complete', 'Scrap'])])
            
            msg += f"WO. {wo}\n"
            msg += f"จำนวน{unit_text}ที่เสียทั้งหมด {total_wo} {unit_text}\n"
            if p_pending > 0: msg += f"  - อยู่ระหว่างวิเคราะห์ {p_pending} {unit_text}\n"
            if p_wait > 0: msg += f"  - รอพาร์ท {p_wait} {unit_text}\n"
            if p_done > 0: msg += f"  - ซ่อมเสร็จ {p_done} {unit_text}\n"
            msg += "\n"

        # สรุปภาพรวมท้ายข้อความ
        all_total = len(df_sec)
        all_pending = len(df_sec[df_sec['status'] == 'Pending'])
        all_wait = len(df_sec[df_sec['status'] == 'Wait Part'])
        all_done = len(df_sec[df_sec['status'].isin(['Complete', 'Scrap'])])
        
        msg += "--------------------------------\n"
        msg += f"สรุปภาพรวม {section_name}\n"
        msg += f"จำนวน{unit_text}ที่เสียทั้งหมด {all_total} {unit_text}\n"
        if all_pending > 0: msg += f"  - อยู่ระหว่างวิเคราะห์ {all_pending} {unit_text}\n"
        if all_wait > 0: msg += f"  - รอพาร์ท {all_wait} {unit_text}\n"
        msg += f"  - ซ่อมเสร็จ Ok {all_done} {unit_text}\n"
        msg += "--------------------------------\n"
        msg += f"รายงานโดย: {nick}"
        return msg

    # --- 4. แยกส่งตามหมวดหมู่ ---
    
    # 4.1 ส่ง PCBA (หมวดหมู่ตามคอลัมน์ A)
    df_pcba = df_report[df_report['Category'] == "PCBA"]
    pcba_msg = build_report_format(df_pcba, "PCBA", "บอร์ด")
    if pcba_msg:
        send_line(pcba_msg, to_summary=True)

    # 4.2 ส่ง Machine แยกตามราย Station (คอลัมน์ G)
    df_mac = df_report[df_report['Category'] == "Machine"]
    stations = df_mac['station'].unique()
    for stn in stations:
        if not stn: continue
        stn_data = df_mac[df_mac['station'] == stn]
        stn_msg = build_report_format(stn_data, stn, "เครื่อง")
        if stn_msg:
            send_line(stn_msg, to_summary=True)

    st.success(f"📢 ส่งรายงาน {today_display} เรียบร้อยแล้ว!")

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
    # ปุ่มเดิมของคุณ
    if st.button("🚪 ออกจากระบบ", use_container_width=True):
        st.session_state.is_logged_in = False
        st.rerun()

# --- 6. INTERFACES BY ROLE (USER PORTAL) ---
if role == "user":
    st.header(f"🚀 Repair Portal ({app_mode})")
    
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0

    t1, t2 = st.tabs(["➕ แจ้งซ่อมใหม่", "🔍 ค้นหาและติดตาม"])
    
    with t1:
        df_m = get_df("model_machine" if app_mode == "Machine" else "model_mat")
        df_st = get_df("station_dropdowns")
        
        with st.form("req_form", clear_on_submit=False):
            c1, c2 = st.columns(2)
            
            sel_m = c1.selectbox("Model", [""] + df_m['model'].tolist())
            p_val = df_m[df_m['model']==sel_m]['product_name'].values[0] if sel_m else ""
            c1.text_input("Product", value=p_val, disabled=True)
            
            sn_input = c1.text_input("Serial Number", key="sn_field").strip()
            
            wo = c2.text_input("Work Order").strip().upper()
            stat = c2.selectbox("Station", [""] + df_st['station'].tolist())
            fail_th = c2.text_area("อาการเสีย (Problem Description)")
            
            u_imgs = st.file_uploader("📸 แนบรูปภาพ (จะส่งเข้า LINE)", 
                                     accept_multiple_files=True, 
                                     key=f"user_upload_{st.session_state.uploader_key}")
            
            if st.form_submit_button("ยืนยันแจ้งซ่อมและส่งข้อมูลเข้า LINE", use_container_width=True):
                if not re.match(r'^[a-zA-Z0-9]+$', sn_input):
                    st.error(f"❌ รูปแบบ SN ไม่ถูกต้อง: '{sn_input}'")
                    st.warning("กรุณาเปลี่ยนภาษาคีย์บอร์ดแล้วแสกนใหม่อีกครั้ง")
                
                elif sel_m and sn_input and wo and stat:
                    with st.spinner("กำลังบันทึกข้อมูล..."):
                        sn = validate_sn(sn_input)
                        fail_en = translate_to_en(fail_th)
                        urls = upload_images(u_imgs, "REQ", sn)
                        
                        # 1. บันทึกข้อมูลลง Google Sheets
                        new_row = [app_mode, "Pending", wo, sel_m, p_val, sn, stat, fail_en, get_now(), "", "", "", "", "", "", urls]
                        ws_main.append_row(new_row)
                        
                        # 2. สร้างข้อความแจ้งเตือน LINE (เพิ่ม Station และ Emoji เพื่อความชัดเจน)
                        line_msg = (
                            f"🚨 *New Repair Job!* ({app_mode})\n"
                            f"━━━━━━━━━━━━━━━\n"
                            f"📍 **Station:** {stat}\n"
                            f"🆔 **SN:** {sn}\n"
                            f"📦 **Model:** {sel_m}\n"
                            f"📝 **Problem:** {fail_en}\n"
                            f"👤 **By:** {nick}"
                        )
                        
                        # 3. ส่ง LINE แจ้งเตือน (Default ส่งกลุ่มแจ้งซ่อมเดิม)
                        send_line(line_msg, image_url=urls)
                        
                        # 4. เคลียร์สถานะ
                        st.session_state.uploader_key += 1 
                        st.success("✅ บันทึกและแจ้งเตือนกลุ่ม LINE เรียบร้อย!")
                        time.sleep(1.5)
                        st.rerun()
                else:
                    st.warning("⚠️ กรุณากรอกข้อมูลให้ครบถ้วน (Model, SN, WO, Station)")
                    
# --- ROLE: TECH (Hybrid & Cross-Repair Support) ---
elif role == "tech":
    with st.sidebar:
        st.markdown("---")
        st.subheader("📊 Reporting System")
        report_type = st.selectbox("เลือกส่วนงานที่ต้องการรายงาน:", ["PCBA", "Machine"], index=0 if app_mode == "PCBA" else 1)
        if st.button(f"📢 ส่งรายงาน {report_type}", use_container_width=True):
            send_daily_summary(df_all, report_type)

    st.header("🔧 Technician Workspace (Hybrid Mode)")
    
    t_search, t_new_pcba = st.tabs(["🔍 วิเคราะห์/แก้ไขงานซ่อม", "📦 ส่งซ่อม PCBA (จากหน้างาน Machine)"])

    with t_search:
        sn_scan = st.text_input("🔍 Scan SN (ได้ทั้ง PCBA & Machine)", key="tech_sn_input").strip()
        if sn_scan:
            sn_clean = validate_sn(sn_scan)
            # ค้นหาข้อมูลจากทุก Category เพื่อให้ Tech จัดการได้หมด
            job = df_all[df_all['serial_number'] == sn_clean]
            
            if not job.empty:
                j = job.iloc[-1]
                ridx = job.index[-1] + 2 
                st.info(f"📁 Category: {j['category']} | 📍 Station: {j.get('station')} | ⚠️ Problem: {j.get('failure')}")
                
                # เก็บรูปภาพเดิมไว้เผื่อส่งต่อให้ Job PCBA
                existing_user_img = j.get('user_image', '')
                
                with st.expander("🖼️ ดูรูปภาพจาก User"):
                    display_images_with_link(existing_user_img, "รูปภาพอาการเสีย")

                with st.form("tech_update"):
                    current_wait_part = str(j.get('wait_part_name', "")).strip()
                    p_name_input = st.text_input("Waiting Part Name", value=current_wait_part)
                    
                    stat_list = ["Complete", "Scrap", "Wait Part"]
                    default_status = "Wait Part" if p_name_input else (j.get('status') if j.get('status') in stat_list else "Complete")
                    res = st.radio("Status:", stat_list, index=stat_list.index(default_status), horizontal=True)
                    
                    cls_list = [""] + get_df("class_dropdowns")['classification'].tolist()
                    cls = st.selectbox("Classification", cls_list)
                    case_th = st.text_input("Root Cause")
                    existing_action = str(j.get('action', "")).strip()
                    act_th = st.text_area("Action Taken", value=existing_action)
                    tech_imgs = st.file_uploader("📸 แนบรูปภาพปิดงาน", accept_multiple_files=True)
                    
                    if st.form_submit_button("บันทึกข้อมูล"):
                        can_save = (res == "Wait Part" and p_name_input) or (res in ["Complete", "Scrap"] and case_th and act_th)
                        if can_save:
                            with st.spinner("กำลังบันทึก..."):
                                case_en = translate_to_en(case_th)
                                act_en = translate_to_en(act_th)
                                if res == "Wait Part" and p_name_input and (p_name_input not in act_en):
                                    act_en = f"[Waiting Part: {p_name_input}] " + act_en
                                t_urls = upload_images(tech_imgs, "FIX", sn_clean)
                                
                                ws_main.update_acell(f'B{ridx}', res)
                                ws_main.update(f'J{ridx}:M{ridx}', [[case_en, act_en, cls, ""]])
                                ws_main.update(f'N{ridx}:O{ridx}', [[nick, get_now()]])
                                if t_urls: ws_main.update_acell(f'Q{ridx}', t_urls)
                                
                                if res in ["Complete", "Scrap"]: 
                                    send_line(f"✅ Job Closed! ({j['category']})\nSN: {sn_clean}\nStatus: {res}\nBy: {nick}")
                                
                                st.success("บันทึกสำเร็จ!"); time.sleep(1); st.rerun()
            else: st.warning("ไม่พบข้อมูล SN นี้ในระบบ")

    with t_new_pcba:
        st.subheader("📝 ออกใบแจ้งซ่อม PCBA (เชื่อมโยงจาก Machine Repair)")
        df_pcba_m = get_df("model_mat")
        
        # ค้นหา Job Machine ล่าสุดเพื่อดึงข้อมูลมา Link กันอัตโนมัติ
        ref_sn = st.text_input("แสกน SN เครื่องจักรที่พบปัญหาบอร์ด (เพื่อดึงรูป/Station)").strip().upper()
        ref_data = df_all[df_all['serial_number'] == ref_sn].iloc[-1] if ref_sn in df_all['serial_number'].values else None

        with st.form("tech_new_pcba_form"):
            col1, col2 = st.columns(2)
            pcba_model = col1.selectbox("เลือก Model PCBA (จาก Model Mat)", [""] + df_pcba_m['model'].tolist())
            pcba_sn = col1.text_input("แสกน SN ของบอร์ด PCBA").strip()
            
            # ถ้ามีข้อมูลอ้างอิงจากเครื่องจักร ให้ดึง Station มาใส่ให้เลย
            default_st = ref_data['station'] if ref_data is not None else ""
            pcba_station = col2.text_input("Station/Machine Name", value=default_st)
            pcba_fail = col2.text_area("ระบุอาการเสียของบอร์ด")
            
            # ตัวเลือกดึงรูปภาพเดิม
            use_old_img = st.checkbox("🔗 ดึงรูปภาพจาก Job เครื่องจักรเดิมแนบไปด้วย", value=True) if ref_data is not None and ref_data.get('user_image') else False

            if st.form_submit_button("🚀 ส่งซ่อม PCBA และแจ้งกลุ่ม LINE"):
                if pcba_model and pcba_sn:
                    with st.spinner("กำลังเชื่อมโยงข้อมูลและเปิด Job..."):
                        p_sn = validate_sn(pcba_sn)
                        p_fail_en = translate_to_en(pcba_fail)
                        p_name = df_pcba_m[df_pcba_m['model']==pcba_model]['product_name'].values[0] if pcba_model else ""
                        
                        # จัดการเรื่องรูปภาพ (ใช้รูปเดิมหรือเว้นว่าง)
                        final_urls = ref_data.get('user_image', '') if use_old_img else ""
                        
                        # บันทึกเข้าคิวซ่อมบอร์ด (Category = PCBA)
                        new_pcba_row = ["PCBA", "Pending", f"LINKED:{ref_sn}", pcba_model, p_name, p_sn, pcba_station, p_fail_en, get_now(), "", "", "", "", "", "", final_urls]
                        ws_main.append_row(new_pcba_row)
                        
                        # แจ้งเตือน LINE (กลุ่มแจ้งซ่อม)
                        line_msg = (
                            f"📦 *Tech Request: PCBA Repair*\n"
                            f"━━━━━━━━━━━━━━━\n"
                            f"🆔 **PCBA SN:** {p_sn}\n"
                            f"📦 **Model:** {pcba_model}\n"
                            f"📍 **From:** {pcba_station} (SN: {ref_sn})\n"
                            f"📝 **Prob:** {p_fail_en}\n"
                            f"👤 **Requester:** {nick}"
                        )
                        send_line(line_msg, image_url=final_urls)
                        
                        st.success(f"เปิด Job ซ่อมบอร์ด {p_sn} เรียบร้อย!")
                        time.sleep(1.5); st.rerun()
                else:
                    st.error("กรุณากรอก Model และ SN ของบอร์ดที่ต้องการส่งซ่อม")
                
# --- ROLE: ADMIN / SUPER ADMIN ---
elif role in ["admin", "super admin"]:
    st.header(f"🏛️ Executive Dashboard: {app_mode}")

    df_report = df_all[df_all['category'] == app_mode].copy()
    df_report['tech_datetime'] = pd.to_datetime(df_report['tech_time'], errors='coerce')

    # Metrics Overview
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
        else: 
            st.info("ไม่มีข้อมูลสัปดาห์นี้")

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
        # --- ส่วนที่ 1: แก้ไขข้อมูลงานซ่อม ---
        st.subheader("📝 Edit Raw Data (Repair Logs)")
        st.info("คุณสามารถแก้ไขข้อมูลในตารางนี้ได้โดยตรง (แสดง 50 รายการล่าสุด)")
        edited_df = st.data_editor(df_report.tail(50), use_container_width=True, key="raw_editor")
        
        # --- ส่วนที่ 2: การจัดการผู้ใช้ (เฉพาะ Super Admin) ---
        if role == "super admin":
            st.divider()
            st.subheader("🔑 Super Admin: User Management")
            
            # ดึงข้อมูลจาก Sheet 'users'
            df_u = get_df("users")
            
            u_col1, u_col2 = st.columns([1.5, 1])
            
            with u_col1:
                st.write("👥 **รายชื่อผู้ใช้ปัจจุบัน**")
                # ตกแต่งหัวข้อตารางให้ดูง่าย
                st.dataframe(
                    df_u[['username', 'role', 'nickname', 'line_user_id']], 
                    hide_index=True, 
                    use_container_width=True
                )
            
            with u_col2:
                st.write("➕ **เพิ่มบัญชีผู้ใช้ใหม่**")
                with st.form("add_user_form", clear_on_submit=True):
                    new_u = st.text_input("Username").strip()
                    new_p = st.text_input("Password", type="password").strip()
                    new_n = st.text_input("Nickname").strip()
                    new_lid = st.text_input("Line User ID").strip()
                    new_r = st.selectbox("Role", ["user", "tech", "admin", "super admin"])
                    
                    if st.form_submit_button("บันทึกข้อมูล", use_container_width=True):
                        if new_u and new_p and new_n:
                            # ตรวจสอบชื่อซ้ำ
                            if new_u in df_u['username'].astype(str).values:
                                st.error(f"Username '{new_u}' มีในระบบแล้ว")
                            else:
                                try:
                                    ss.worksheet("users").append_row([new_u, new_p, new_r, new_n, new_lid])
                                    st.success(f"เพิ่ม {new_n} เรียบร้อย!")
                                    time.sleep(1.5)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error: {e}")
                        else:
                            st.warning("กรุณากรอก Username, Password และ Nickname")

            # --- ส่วนที่ 3: ระบบควบคุมส่วนกลาง ---
            st.divider()
            st.write("🚨 **Danger Zone**")
            c_danger1, c_danger2 = st.columns(2)
            
            with c_danger1:
                if st.button("♻️ Clear System Cache", use_container_width=True):
                    st.cache_data.clear()
                    st.cache_resource.clear()
                    st.success("ล้างหน่วยความจำชั่วคราวแล้ว!")
                    time.sleep(1)
                    st.rerun()
            
            with c_danger2:
                del_sn = st.text_input("ระบุ SN ที่จะลบถาวร").strip().upper()
                if st.button("🗑️ ยืนยันการลบ Record", type="secondary", use_container_width=True):
                    if del_sn:
                        try:
                            cell = ws_main.find(del_sn)
                            ws_main.delete_rows(cell.row)
                            st.error(f"ลบ SN {del_sn} ออกจากฐานข้อมูลแล้ว")
                            time.sleep(1.5)
                            st.rerun()
                        except:
                            st.warning("ไม่พบหมายเลข SN นี้")
