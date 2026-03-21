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

    # --- จุดแก้ไขที่ 1: ตรวจสอบคอลัมน์ Category (เคสเซนสิทิฟ) ---
    cat_col = 'Category' if 'Category' in df.columns else 'category'
    if cat_col not in df.columns:
        st.error(f"❌ ไม่พบคอลัมน์ Category (คอลัมน์ที่มี: {', '.join(df.columns)})")
        return
        
    # --- จุดแก้ไขที่ 2: ตรวจสอบคอลัมน์ user_time ---
    time_col = 'user_time' if 'user_time' in df.columns else ('Timestamp' if 'Timestamp' in df.columns else 'timestamp')
    df['date_only'] = pd.to_datetime(df[time_col]).dt.strftime('%Y-%m-%d')
    
    # 2. กรองข้อมูล: งานวันนี้ + งานค้างสะสม
    condition = (df['date_only'] == today_str) | (df['status'].isin(['Pending', 'Wait Part']))
    df_report = df[condition].copy()

    if df_report.empty:
        st.warning(f"📅 ไม่มีรายการงานของวันนี้และไม่มีงานค้างสะสม")
        return

    # ฟังก์ชันสร้างข้อความ (ใช้ชื่อคอลัมน์ที่ยืดหยุ่น)
    def build_report_format(df_sec, section_name, unit_text):
        if df_sec.empty: return None
        
        msg = f"รายงานผลการ \"Repair\" ประจำวันที่ {today_display}\n"
        msg += f"ส่วนงาน: {section_name}\n"
        msg += "--------------------------------\n"
        
        # ตรวจสอบชื่อคอลัมน์ Work Order
        wo_col = 'work_order' if 'work_order' in df_sec.columns else 'work_order'
        
        wo_list = df_sec[wo_col].unique()
        for wo in wo_list:
            if not wo: continue
            wo_data = df_sec[df_sec[wo_col] == wo]
            
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

        # สรุปภาพรวม
        total_all = len(df_sec)
        total_pending = len(df_sec[df_sec['status'] == 'Pending'])
        total_wait = len(df_sec[df_sec['status'] == 'Wait Part'])
        total_done = len(df_sec[df_sec['status'].isin(['Complete', 'Scrap'])])
        
        msg += "--------------------------------\n"
        msg += f"สรุปภาพรวม {section_name}\n"
        msg += f"จำนวน{unit_text}ที่เสียทั้งหมด {total_all} {unit_text}\n"
        if total_pending > 0: msg += f"  - อยู่ระหว่างวิเคราะห์ {total_pending} {unit_text}\n"
        if total_wait > 0: msg += f"  - รอพาร์ท {total_wait} {unit_text}\n"
        msg += f"  - ซ่อมเสร็จ Ok {total_done} {unit_text}\n"
        msg += "--------------------------------\n"
        msg += f"รายงานโดย: {nick}"
        return msg

    # --- 3. แยกส่งตามส่วนงาน ---
    
    # ส่ง PCBA
    df_pcba_data = df_report[df_report[cat_col] == "PCBA"]
    pcba_msg = build_report_format(df_pcba_data, "PCBA", "บอร์ด")
    if pcba_msg:
        send_line(pcba_msg, to_summary=True)

    # ส่ง Machine แยกตามราย Station
    df_mac_data = df_report[df_report[cat_col] == "Machine"]
    if not df_mac_data.empty:
        stations = df_mac_data['work_name'].unique()
        for stn in stations:
            if not stn: continue
            stn_data = df_mac_data[df_mac_data['work_name'] == stn]
            stn_msg = build_report_format(stn_data, stn, "เครื่อง")
            if stn_msg:
                send_line(stn_msg, to_summary=True)

    st.success("📢 รายงานถูกส่งเรียบร้อยแล้ว!")



f not st.session_state.logged_in:
    with st.columns([1, 2, 1])[1]: 
        st.title("🔐 Login System")
        st.subheader("PCBA & Machine Repair Service")
        
        with st.form("login_form"):
            user_input = st.text_input("👤 Username")
            pass_input = st.text_input("🔑 Password", type="password")
            # ตัด role_input ออกเพื่อให้ระบบจัดการเอง
            mode_input = st.selectbox("⚙️ Mode", ["Machine", "PCBA"])
            
            submit = st.form_submit_button("เข้าสู่ระบบ", use_container_width=True)
            
            if submit:
                df_users = get_df("users")
                df_users['username'] = df_users['username'].astype(str).str.strip()
                
                # ค้นหา User
                user_match = df_users[df_users['username'] == str(user_input).strip()]
                
                if not user_match.empty:
                    row = user_match.iloc[0]
                    found_role = None
                    
                    # ลำดับการตรวจสอบสิทธิ์ (Priority Check)
                    # ระบบจะเช็คว่า Password ที่กรอกมา ตรงกับคอลัมน์ไหนในแถวนั้น
                    role_priority = [
                        ("super admin", "password_super_admin"),
                        ("admin", "password_admin"),
                        ("tech", "password_tech"),
                        ("user", "password_user")
                    ]
                    
                    input_p = str(pass_input).strip()
                    for role_name, col_name in role_priority:
                        db_p = str(row[col_name]).strip()
                        if db_p != "nan" and db_p != "" and db_p == input_p:
                            found_role = role_name
                            break # เจอ Role ที่ตรงกับ Password แล้วให้หยุดเช็ค
                    
                    if found_role:
                        st.session_state.logged_in = True
                        st.session_state.role = found_role
                        st.session_state.app_mode = mode_input
                        st.session_state.nick = row['nickname']
                        
                        st.success(f"ยินดีต้อนรับคุณ {st.session_state.nick} สิทธิ์: {found_role}")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ รหัสผ่านไม่ถูกต้อง หรือคุณไม่มีสิทธิ์เข้าใช้งาน")
                else:
                    st.error("❌ ไม่พบข้อมูลผู้ใช้งาน")


# --- 3. MAIN APP CONTENT (เมื่อ Logged In แล้ว) ---
else: 
    # --- 1. ประกาศตัวแปร ---
    role = st.session_state.role
    app_mode = st.session_state.app_mode
    nick = st.session_state.nick
    unit = "บอร์ด" if app_mode == "PCBA" else "เครื่อง"

    # โหลดข้อมูล
    ws_main = ss.worksheet("sheet1")
    df_all = get_df("sheet1")

    # --- 4. SIDEBAR ---
    with st.sidebar:
        st.title(f"👤 {nick}")
        st.write(f"**Mode:** {app_mode} | **Role:** {role.upper()}")
        st.divider()
        
        st.subheader("📝 Quick Edit Status")
        sn_edit_input = st.text_input("Scan SN to Edit Status", key="sb_sn_edit").strip()
        if sn_edit_input:
            sn_clean_edit = validate_sn(sn_edit_input)
            edit_row = df_all[df_all['serial_number'] == sn_clean_edit]
            
            if not edit_row.empty:
                with st.expander("Update Status", expanded=True):
                    current_stat = edit_row.iloc[-1]['status']
                    stat_options = ["Pending", "Wait Part", "Complete", "Scrap"]
                    idx_stat = stat_options.index(current_stat) if current_stat in stat_options else 0
                    new_stat = st.selectbox("Status", stat_options, index=idx_stat)
                    
                    if st.button("บันทึกการเปลี่ยนสถานะ"):
                        r_idx = edit_row.index[-1] + 2
                        ws_main.update_acell(f'B{r_idx}', new_stat)
                        st.success("อัปเดตสถานะสำเร็จ!"); time.sleep(1); st.rerun()
            else:
                st.warning("ไม่พบ SN นี้ในฐานข้อมูล")
        
        st.divider()
        if st.button("🚪 Log Out", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()

    # --- 5. แท็บการทำงานหลักแยกตาม Role ---
    if role == "user":
        st.header(f"🚀 Repair Portal ({app_mode})")
        
        if "uploader_key" not in st.session_state:
            st.session_state.uploader_key = 0
    
        t1, t2, t3 = st.tabs(["➕ แจ้งซ่อมใหม่", "🔍 ค้นหาและติดตาม", "📋 ลงทะเบียน Model"])
        
        with t1:
            df_m = get_df("model_machine" if app_mode == "Machine" else "model_mat")
            df_st = get_df("station_dropdowns")
            
            with st.form("req_form", clear_on_submit=False):
                c1, c2 = st.columns(2)
                sel_m = c1.selectbox("Model", [""] + df_m['model'].unique().tolist())
                p_val = df_m[df_m['model']==sel_m]['product_name'].values[0] if sel_m else ""
                c1.text_input("Product", value=p_val, disabled=True)
                sn_input = c1.text_input("Serial Number", key="sn_field").strip()
                
                wo = c2.text_input("Work Order").strip().upper()
                stat = c2.selectbox("Station", [""] + df_st['station'].tolist())
                fail_th = c2.text_area("อาการเสีย (Problem Description)")
                
                u_imgs = st.file_uploader("📸 แนบรูปภาพ", accept_multiple_files=True, key=f"user_upload_{st.session_state.uploader_key}")
                
                if st.form_submit_button("ยืนยันแจ้งซ่อม", use_container_width=True):
                    if not re.match(r'^[a-zA-Z0-9]+$', sn_input):
                        st.error(f"❌ รูปแบบ SN ไม่ถูกต้อง")
                    elif sel_m and sn_input and wo and stat:
                        with st.spinner("กำลังบันทึก..."):
                            sn = validate_sn(sn_input)
                            fail_en = translate_to_en(fail_th)
                            urls = upload_images(u_imgs, "REQ", sn)
                            new_row = [app_mode, "Pending", wo, sel_m, p_val, sn, stat, fail_en, get_now(), "", "", "", "", "", "", urls]
                            ws_main.append_row(new_row)
                            send_line(f"🚨 New Job!\nSN: {sn}\nModel: {sel_m}\nBy: {nick}", image_url=urls)
                            st.session_state.uploader_key += 1 
                            st.success("✅ บันทึกสำเร็จ!"); time.sleep(1); st.rerun()
                    else:
                        st.warning("⚠️ กรุณากรอกข้อมูลให้ครบถ้วน")

        with t2:
            st.write("ส่วนการค้นหาและติดตามข้อมูล...")

        with t3:
            st.subheader(f"➕ ลงทะเบียน Model ใหม่ ({app_mode})")
            with st.form("user_add_new_model_form"):
                if app_mode == "PCBA":
                    u_new_m = st.text_input("PCBA Model Name").strip()
                    u_new_p = st.text_input("Product Name").strip()
                    if st.form_submit_button("บันทึกข้อมูล PCBA"):
                        if u_new_m and u_new_p:
                            ss.worksheet("model_mat").append_row([u_new_m, u_new_p])
                            st.success("✅ บันทึกสำเร็จ!"); time.sleep(1); st.rerun()
                else:
                    col_u1, col_u2 = st.columns(2)
                    u_m_model = col_u1.text_input("Model Machine").strip()
                    u_m_product = col_u1.text_input("Product Name").strip()
                    u_m_work = col_u2.text_input("Work Name (String/PCS)").strip()
                    if st.form_submit_button("บันทึกข้อมูล Machine"):
                        if u_m_model and u_m_product and u_m_work:
                            ss.worksheet("model_machine").append_row([u_m_model, u_m_product, u_m_work])
                            st.success("✅ บันทึกสำเร็จ!"); time.sleep(1); st.rerun()

    elif role == "tech":
        with st.sidebar:
            st.markdown("---")
            st.subheader("📊 Reporting System")
            report_type = st.selectbox("เลือกส่วนงาน:", ["PCBA", "Machine"], index=0 if app_mode == "PCBA" else 1)
            if st.button(f"📢 ส่งรายงาน {report_type}", use_container_width=True):
                send_daily_summary(df_all, report_type)
    
        st.header("🔧 Technician Workspace")
        t_search, t_new_pcba, t_add_m = st.tabs(["🔍 วิเคราะห์/แก้ไข", "📦 ส่งซ่อม PCBA", "⚙️ Master Data"])
    
        with t_search:
            sn_scan = st.text_input("🔍 Scan SN", key="tech_sn_input").strip()
            if sn_scan:
                sn_clean = validate_sn(sn_scan)
                job = df_all[df_all['serial_number'] == sn_clean]
                if not job.empty:
                    j = job.iloc[-1]
                    ridx = job.index[-1] + 2 
                    st.info(f"📁 Category: {j['category']} | ⚠️ Problem: {j.get('failure')}")
                    with st.expander("🖼️ ดูรูปภาพจาก User"):
                        display_images_with_link(j.get('user_image', ''), "รูปภาพอาการเสีย")
                    
                    with st.form("tech_update"):
                        p_name_input = st.text_input("Waiting Part Name", value=str(j.get('wait_part_name', "")))
                        stat_list = ["Complete", "Scrap", "Wait Part"]
                        res = st.radio("Status:", stat_list, horizontal=True)
                        cls = st.selectbox("Classification", [""] + get_df("class_dropdowns")['classification'].tolist())
                        case_th = st.text_input("Root Cause")
                        act_th = st.text_area("Action Taken", value=str(j.get('action', "")))
                        tech_imgs = st.file_uploader("📸 รูปปิดงาน", accept_multiple_files=True)
                        
                        if st.form_submit_button("บันทึกข้อมูล"):
                            if (res == "Wait Part" and p_name_input) or (res in ["Complete", "Scrap"] and case_th and act_th):
                                with st.spinner("บันทึก..."):
                                    case_en = translate_to_en(case_th)
                                    act_en = translate_to_en(act_th)
                                    t_urls = upload_images(tech_imgs, "FIX", sn_clean)
                                    ws_main.update_acell(f'B{ridx}', res)
                                    ws_main.update(f'J{ridx}:M{ridx}', [[case_en, act_en, cls, p_name_input]])
                                    ws_main.update(f'N{ridx}:O{ridx}', [[nick, get_now()]])
                                    if t_urls: ws_main.update_acell(f'Q{ridx}', t_urls)
                                    send_line(f"✅ Job Closed!\nSN: {sn_clean}\nBy: {nick}")
                                    st.success("บันทึกสำเร็จ!"); time.sleep(1); st.rerun()
                else: st.warning("ไม่พบข้อมูล")

        with t_new_pcba:
            st.subheader("📝 ออกใบแจ้งซ่อม PCBA")
            sn_machine_ref = st.text_input("สแกน SN เครื่องจักร", key="sn_ref")
            ref_data = {}
            if sn_machine_ref:
                machine_job = df_all[df_all['serial_number'] == validate_sn(sn_machine_ref)]
                if not machine_job.empty:
                    m_last = machine_job.iloc[-1]
                    ref_data = {"work_order": m_last.get('work_order', ''), "station": m_last.get('station', ''), "user_image": m_last.get('user_image', '')}
                    st.success(f"🔗 เชื่อมโยง WO: {ref_data['work_order']}")

            with st.form("new_pcba_from_machine"):
                c1, c2 = st.columns(2)
                df_model_mat = get_df("model_mat")
                selected_pcba_model = c1.selectbox("เลือก Model PCBA", [""] + df_model_mat['model'].dropna().unique().tolist())
                sn_pcba = c1.text_input("สแกน SN บอร์ด").strip()
                stn_name = c2.text_input("Station Name", value=ref_data.get('station', ''))
                pcba_failure = c2.text_area("อาการเสีย")
                
                if st.form_submit_button("🚀 ส่งซ่อม PCBA"):
                    if selected_pcba_model and sn_pcba and pcba_failure:
                        p_name = df_model_mat[df_model_mat['model'] == selected_pcba_model].iloc[0]['product_name']
                        new_pcba_job = ["PCBA", "Pending", ref_data.get('work_order', ''), selected_pcba_model, p_name, sn_pcba, stn_name, pcba_failure, get_now(), "", "", "", "", "", "", ref_data.get('user_image', '')]
                        ws_main.append_row(new_pcba_job)
                        send_line(f"📥 New PCBA Repair!\nSN: {sn_pcba}")
                        st.success("สำเร็จ!"); time.sleep(1); st.rerun()

        with t_add_m:
            st.subheader(f"⚙️ เพิ่ม Master Data ({app_mode})")
            with st.form("tech_add_model_form"):
                t_m = st.text_input("Model Name").strip()
                t_p = st.text_input("Product Name").strip()
                if app_mode == "Machine":
                    t_w = st.text_input("Work Name").strip()
                    if st.form_submit_button("บันทึก Machine"):
                        ss.worksheet("model_machine").append_row([t_m, t_p, t_w]); st.success("OK"); st.rerun()
                else:
                    if st.form_submit_button("บันทึก PCBA"):
                        ss.worksheet("model_mat").append_row([t_m, t_p]); st.success("OK"); st.rerun()

    # --- ROLE: ADMIN / SUPER ADMIN ---
    elif role in ["admin", "super admin"]:
        st.header(f"🏛️ Executive Dashboard: {app_mode}")
        df_report = df_all[df_all['category'] == app_mode].copy()
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("งานทั้งหมด", f"{len(df_report)} {unit}")
        m2.metric("Pending", len(df_report[df_report['status']=='Pending']))
        m3.metric("Wait Part", len(df_report[df_report['status']=='Wait Part']))
        m4.metric("Complete/Scrap", len(df_report[df_report['status'].isin(['Complete', 'Scrap'])]))

        tabs = st.tabs(["📅 รายงานวันนี้", "📊 รายสัปดาห์", "🖼️ Gallery", "🛠️ Management"])
        with tabs[0]:
            if st.button("📢 ส่งรายงานสรุปประจำวันเข้า LINE", use_container_width=True):
                send_daily_summary(df_all, app_mode)
            st.dataframe(df_report.tail(50), use_container_width=True)

        with tabs[3]:
            st.subheader("📝 Edit Raw Data")
            edited_df = st.data_editor(df_report.tail(50), use_container_width=True)
            
            if role == "super admin":
                st.divider()
                st.subheader("🔑 User Management")
                df_u = get_df("users")
                u_col1, u_col2 = st.columns([1.5, 1])
                u_col1.dataframe(df_u[['username', 'role', 'nickname']], hide_index=True)
                with u_col2.form("add_user_form"):
                    nu, np, nn = st.text_input("User"), st.text_input("Pass", type="password"), st.text_input("Nick")
                    nr = st.selectbox("Role", ["user", "tech", "admin", "super admin"])
                    if st.form_submit_button("บันทึก"):
                        ss.worksheet("users").append_row([nu, np, nr, nn, ""]); st.success("เพิ่มแล้ว"); st.rerun()
