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
        df = pd.DataFrame(data)
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        return df.fillna("")
    except:
        return pd.DataFrame()

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
    token = st.secrets.get("line_channel_access_token") 
    GROUP_ID_REPAIR = "C54883d9bd6b1293ff2bad0ba497a80d7" 
    GROUP_ID_SUMMARY = "Ce5d4d803cd538c97b007d75cb406306c"
    target_id = GROUP_ID_SUMMARY if to_summary else GROUP_ID_REPAIR
    
    if not token: 
        st.error("❌ ไม่พบ Line Channel Access Token ใน Secrets")
        return None
    
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json", 
        "Authorization": f"Bearer {token}"
    }
    
    messages = [{"type": "text", "text": msg}]
    
    if image_url:
        # ดึง URL รูปแรก และตรวจสอบว่าเป็น https หรือไม่ (Line บังคับ https)
        first_img = image_url.split(',')[0].strip()
        if first_img.startswith("https"):
            messages.append({
                "type": "image", 
                "originalContentUrl": first_img, 
                "previewImageUrl": first_img
            })
        
    payload = {"to": target_id, "messages": messages}
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            # แสดง Error บนหน้าจอเพื่อการ Debug
            st.warning(f"⚠️ LINE API Error {response.status_code}: {response.text}")
        return response.status_code
    except Exception as e:
        st.error(f"❌ Connection Error: {e}")
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
    today_str = now.strftime("%Y-%m-%d")
    today_display = now.strftime("%d/%m/%Y")
    nick = st.session_state.get('nick', 'Unknown')

    cat_col = 'category' if 'category' in df.columns else ('Category' if 'Category' in df.columns else '')
    if not cat_col: return
        
    time_col = 'user_time' if 'user_time' in df.columns else ('timestamp' if 'timestamp' in df.columns else 'Timestamp')
    df['date_only'] = pd.to_datetime(df[time_col]).dt.strftime('%Y-%m-%d')
    
    condition = (df['date_only'] == today_str) | (df['status'].isin(['Pending', 'Wait Part']))
    df_report = df[condition].copy()

    if df_report.empty:
        st.warning(f"📅 ไม่มีรายการงาน")
        return

    def build_report_format(df_sec, section_name, unit_text):
        if df_sec.empty: return None
        msg = f"รายงานผลการ \"Repair\" ประจำวันที่ {today_display}\nส่วนงาน: {section_name}\n"
        msg += "--------------------------------\n"
        wo_col = 'work_order'
        wo_list = df_sec[wo_col].unique()
        for wo in wo_list:
            if not wo: continue
            wo_data = df_sec[df_sec[wo_col] == wo]
            total_wo = len(wo_data)
            p_pending = len(wo_data[wo_data['status'] == 'Pending'])
            p_wait = len(wo_data[wo_data['status'] == 'Wait Part'])
            p_done = len(wo_data[wo_data['status'].isin(['Complete', 'Scrap'])])
            msg += f"WO. {wo}\nจำนวน{unit_text}เสีย {total_wo}\n"
            if p_pending > 0: msg += f" - วิเคราะห์ {p_pending}\n"
            if p_wait > 0: msg += f" - รอพาร์ท {p_wait}\n"
            if p_done > 0: msg += f" - เสร็จ {p_done}\n"
            msg += "\n"
        msg += "--------------------------------\nรายงานโดย: " + nick
        return msg

    df_pcba_data = df_report[df_report[cat_col].str.upper() == "PCBA"]
    pcba_msg = build_report_format(df_pcba_data, "PCBA", "บอร์ด")
    if pcba_msg: send_line(pcba_msg, to_summary=True)

    df_mac_data = df_report[df_report[cat_col].str.upper() == "MACHINE"]
    if not df_mac_data.empty:
        stations = df_mac_data['station'].unique()
        for stn in stations:
            stn_data = df_mac_data[df_mac_data['station'] == stn]
            stn_msg = build_report_format(stn_data, stn, "เครื่อง")
            if stn_msg: send_line(stn_msg, to_summary=True)
    st.success("📢 รายงานถูกส่งเรียบร้อยแล้ว!")

# --- 3. SESSION STATE ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.nick = None
    st.session_state.app_mode = None

# --- 4. LOGIN UI ---
if not st.session_state.logged_in:
    _, center_col, _ = st.columns([1, 2, 1])
    with center_col:
        st.title("🔐 Login System")
        with st.form("login_form"):
            user_input = st.text_input("👤 Username").strip()
            pass_input = st.text_input("🔑 Password", type="password").strip()
            mode_input = st.selectbox("⚙️ Mode", ["Machine", "PCBA"])
            if st.form_submit_button("เข้าสู่ระบบ", use_container_width=True):
                df_users = get_df("users")
                if not df_users.empty:
                    df_users['username'] = df_users['username'].astype(str).str.strip()
                    user_match = df_users[df_users['username'] == user_input]
                    if not user_match.empty:
                        row = user_match.iloc[0]
                        found_role = None
                        role_priority = [("super admin", "password_super_admin"), ("admin", "password_admin"), ("tech", "password_tech"), ("user", "password_user")]
                        for role_name, col_name in role_priority:
                            db_p = str(row.get(col_name, "")).strip()
                            if db_p and db_p != "nan" and db_p == pass_input:
                                found_role = role_name
                                break
                        if found_role:
                            st.session_state.logged_in = True
                            st.session_state.role = found_role
                            st.session_state.app_mode = mode_input
                            st.session_state.nick = row.get('nickname', user_input)
                            st.success(f"✅ ยินดีต้อนรับคุณ {st.session_state.nick}")
                            time.sleep(1); st.rerun()
                        else: st.error("❌ รหัสผ่านไม่ถูกต้อง")
                    else: st.error("❌ ไม่พบผู้ใช้งาน")

# --- 5. MAIN CONTENT ---
else: 
    role = st.session_state.role
    app_mode = st.session_state.app_mode
    nick = st.session_state.nick
    
    try:
        ws_main = ss.worksheet("sheet1")
        df_all = get_df("sheet1")
    except Exception as e:
        st.error(f"Error Sheet1: {e}"); st.stop()

    with st.sidebar:
        st.title(f"👤 {nick}")
        st.write(f"**Mode:** {app_mode} | **Role:** {role.upper()}")
        st.divider()
        sn_edit = st.text_input("Scan SN to Edit Status").strip()
        if sn_edit:
            sn_c = validate_sn(sn_edit)
            edit_row = df_all[df_all['serial_number'] == sn_c]
            if not edit_row.empty:
                with st.expander("Update Status", expanded=True):
                    new_st = st.selectbox("Status", ["Pending", "Wait Part", "Complete", "Scrap"])
                    if st.button("บันทึก"):
                        ridx = edit_row.index[-1] + 2
                        ws_main.update_acell(f'B{ridx}', new_st)
                        st.success("OK"); time.sleep(1); st.rerun()
        st.divider()
        if st.button("🚪 Log Out", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()

    # --- Role Based Logic (Correct Indentation) ---
    if role == "user":
        st.header(f"🚀 Repair Portal ({app_mode})")
        if "uploader_key" not in st.session_state: st.session_state.uploader_key = 0
        t1, t2, t3 = st.tabs(["➕ แจ้งซ่อมใหม่", "🔍 ค้นหา", "📋 ลงทะเบียน Model"])
        
        with t1:
            df_m = get_df("model_machine" if app_mode == "Machine" else "model_mat")
            df_st = get_df("station_dropdowns")
            with st.form("req_form"):
                c1, c2 = st.columns(2)
                m_list = [""] + df_m['model'].unique().tolist() if not df_m.empty else [""]
                sel_m = c1.selectbox("Model", m_list)
                p_val = df_m[df_m['model'] == sel_m]['product_name'].values[0] if sel_m and not df_m.empty else ""
                c1.text_input("Product", value=p_val, disabled=True)
                sn_in = c1.text_input("Serial Number").strip()
                wo_in = c2.text_input("Work Order").strip().upper()
                stn_list = [""] + df_st.iloc[:,0].tolist() if not df_st.empty else [""]
                stat_in = c2.selectbox("Station", stn_list)
                fail_in = c2.text_area("อาการเสีย")
                u_imgs = st.file_uploader("📸 รูปภาพ", accept_multiple_files=True, key=f"u_{st.session_state.uploader_key}")
                if st.form_submit_button("ยืนยันแจ้งซ่อม"):
                    if sel_m and sn_in and wo_in:
                        sn = validate_sn(sn_in)
                        urls = upload_images(u_imgs, "REQ", sn) if u_imgs else ""
                        new_row = [app_mode, "Pending", wo_in, sel_m, p_val, sn, stat_in, translate_to_en(fail_in), get_now(), "", "", "", "", "", "", urls]
                        ws_main.append_row(new_row)
                        send_line(f"🚨 New Job: {sn}", image_url=urls)
                        st.session_state.uploader_key += 1
                        st.success("สำเร็จ!"); time.sleep(1); st.rerun()

        with t2:
            s_sn = st.text_input("ค้นหา SN")
            if s_sn: st.dataframe(df_all[df_all['serial_number'] == validate_sn(s_sn)])

        with t3:
            with st.form("add_model_user"):
                m_n = st.text_input("Model Name")
                p_n = st.text_input("Product Name")
                if st.form_submit_button("บันทึก"):
                    target = "model_machine" if app_mode == "Machine" else "model_mat"
                    ss.worksheet(target).append_row([m_n, p_n])
                    st.success("OK"); time.sleep(1); st.rerun()

    elif role == "tech":
        st.header("🔧 Technician Workspace")
        if st.sidebar.button(f"📢 ส่งรายงาน {app_mode}"): send_daily_summary(df_all, app_mode)
        
        t_fix, t_pcba, t_master = st.tabs(["🔍 แก้ไขงาน", "📦 ส่งซ่อม PCBA", "⚙️ Master"])
        with t_fix:
            sn_s = st.text_input("🔍 Scan SN").strip()
            if sn_s:
                sn_c = validate_sn(sn_s)
                job = df_all[df_all['serial_number'] == sn_c]
                if not job.empty:
                    j = job.iloc[-1]; ridx = job.index[-1] + 2
                    display_images_with_link(j.get('user_image', ''))
                    with st.form("tech_update"):
                        p_name = st.text_input("Wait Part Name", value=str(j.get('wait_part_name', "")))
                        res = st.radio("Status:", ["Complete", "Scrap", "Wait Part"], horizontal=True)
                        cls = st.selectbox("Classification", [""] + get_df("class_dropdowns").iloc[:,0].tolist())
                        rc = st.text_input("Root Cause")
                        act = st.text_area("Action", value=str(j.get('action', "")))
                        t_imgs = st.file_uploader("📸 รูปปิดงาน", accept_multiple_files=True)
                        if st.form_submit_button("บันทึก"):
                            t_urls = upload_images(t_imgs, "FIX", sn_c)
                            ws_main.update_acell(f'B{ridx}', res)
                            ws_main.update(f'J{ridx}:M{ridx}', [[translate_to_en(rc), translate_to_en(act), cls, p_name]])
                            ws_main.update(f'N{ridx}:O{ridx}', [[nick, get_now()]])
                            if t_urls: ws_main.update_acell(f'Q{ridx}', t_urls)
                            st.success("บันทึกสำเร็จ!"); time.sleep(1); st.rerun()

        with t_pcba:
            sn_ref = st.text_input("สแกน SN เครื่องจักร (Ref)")
            with st.form("pcba_repair"):
                df_m_mat = get_df("model_mat")
                sel_p = st.selectbox("Model PCBA", [""] + df_m_mat['model'].unique().tolist())
                sn_p = st.text_input("SN บอร์ด")
                if st.form_submit_button("ส่งซ่อม PCBA"):
                    p_n = df_m_mat[df_m_mat['model'] == sel_p].iloc[0]['product_name']
                    ws_main.append_row(["PCBA", "Pending", "", sel_p, p_n, validate_sn(sn_p), "", "", get_now()])
                    st.success("OK"); time.sleep(1); st.rerun()

        with t_master:
            with st.form("master_add"):
                tm, tp = st.text_input("Model"), st.text_input("Product")
                if st.form_submit_button("เพิ่ม"):
                    ss.worksheet("model_machine" if app_mode == "Machine" else "model_mat").append_row([tm, tp])
                    st.success("OK"); st.rerun()

    elif role in ["admin", "super admin"]:
        st.header("🏛️ Executive Dashboard")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("งานรวม", len(df_all))
        m2.metric("⏳ Pending", len(df_all[df_all['status'] == 'Pending']))
        m3.metric("🛠️ Wait Part", len(df_all[df_all['status'] == 'Wait Part']))
        m4.metric("✅ Done", len(df_all[df_all['status'].isin(['Complete', 'Scrap'])]))
        
        adm_t = st.tabs(["💻 PCBA", "🏗️ Machine", "⚙️ Management"])
        with adm_t[0]: 
            st.dataframe(df_all[df_all['category'] == 'PCBA'])
        with adm_t[2]:
            st.subheader("📝 Raw Data Edit")
            st.data_editor(df_all.tail(50))
            if role == "super admin":
                df_u = get_df("users")
                st.dataframe(df_u)
                with st.form("add_u"):
                    nu, np, nn = st.text_input("User"), st.text_input("Pass"), st.text_input("Nick")
                    nr = st.selectbox("Role", ["user", "tech", "admin", "super admin"])
                    if st.form_submit_button("Add User"):
                        new_u = [nu, "", "", "", "", nr, nn]
                        rmap = {"user": 1, "tech": 2, "admin": 3, "super admin": 4}
                        new_u[rmap[nr]] = np
                        ss.worksheet("users").append_row(new_u)
                        st.success("OK"); st.rerun()
