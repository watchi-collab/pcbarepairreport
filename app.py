# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import io
import base64
from datetime import datetime
from PIL import Image
import requests
import json

# --- 1. SETTINGS & STYLE ---
st.set_page_config(page_title="PCBA System 2026 PRO", layout="wide")

# --- 2. CONNECTIONS & HELPERS ---
@st.cache_resource
def init_connections():
    try:
        creds_dict = st.secrets["gcp_service_account"]
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        # ใช้ ID จากที่คุณระบุในโค้ด
        spreadsheet = client.open_by_key("1KtW9m3hFq2sBUeRkNATvD4nRKu_cDCoZENXk7WgOafc")
        return spreadsheet, True
    except Exception as e:
        return None, False

ss, status_conn = init_connections()

def get_df(sheet_name):
    try:
        ws = ss.worksheet(sheet_name)
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        if not df.empty: 
            df.columns = df.columns.str.strip()
            # กรองแถวว่างทิ้งทันทีเพื่อป้องกันปัญหา None ในตาราง
            df = df.dropna(how='all')
        return df.fillna("")
    except:
        return pd.DataFrame()

def save_image_b64(file):
    if file is None: return ""
    img = Image.open(file)
    img.thumbnail((400, 400))
    buf = io.BytesIO()
    img.convert('RGB').save(buf, format="JPEG", quality=50)
    return base64.b64encode(buf.getvalue()).decode()

def save_multiple_images_b64(files):
    if not files: return ""
    encoded_images = []
    for file in files:
        try:
            img = Image.open(file)
            img.thumbnail((400, 400))
            buf = io.BytesIO()
            img.convert('RGB').save(buf, format="JPEG", quality=40)
            encoded_images.append(base64.b64encode(buf.getvalue()).decode())
        except: continue
    return "|".join(encoded_images)

def get_dropdown_options(sheet_name):
    df = get_df(sheet_name)
    options = ["--กรุณาเลือก--"]
    if not df.empty: options.extend(df.iloc[:, 0].astype(str).tolist())
    return options

def send_line_message(wo, sn, model, failure, status_type="New Request", operator="Unknown"):
    try:
        line_token = st.secrets["line_channel_access_token"]
        line_to = st.secrets["line_group_id"]
        url = "https://api.line.me/v2/bot/message/push"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {line_token}"}
        msg = f"\n📢 [{status_type}]\n🛠 WO: {wo}\n🆔 SN: {sn}\n📟 Model: {model}\n⚠️ อาการ: {failure}\n👤 โดย: {operator}"
        payload = {"to": line_to, "messages": [{"type": "text", "text": msg}]}
        requests.post(url, headers=headers, data=json.dumps(payload))
        return True
    except: return False

# --- 3. SESSION STATE ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

# --- 4. LOGIN & PUBLIC TRACKING ---
if not st.session_state.logged_in:
    tab1, tab2 = st.tabs(["🔍 ติดตามสถานะงาน (Public)", "🔐 เข้าสู่ระบบ (Staff Only)"])
    
    with tab1:
        st.title("🔎 PCBA Repair Tracking")
        c1, c2 = st.columns(2)
        p_sn = c1.text_input("🔢 SN / WO", key="pub_sn").strip().upper()
        p_mo = c2.text_input("📦 Model", key="pub_mo").strip().upper()
        if p_sn or p_mo:
            df_pub = get_df("sheet1")
            if not df_pub.empty:
                res = df_pub[(df_pub['sn'].astype(str).str.contains(p_sn) | df_pub['wo'].astype(str).str.contains(p_sn)) & 
                             (df_pub['model'].astype(str).str.contains(p_mo))]
                for _, r in res.tail(5).iterrows():
                    st.info(f"SN: {r['sn']} | Status: {r['status']} | Last Update: {r.get('tech_time','-')}")

    with tab2:
        with st.form("login_form"):
            u = st.text_input("Username").strip()
            p = st.text_input("Password", type="password").strip()
            if st.form_submit_button("Login"):
                df_u = get_df("users")
                if not df_u.empty:
                    df_u['username'] = df_u['username'].astype(str).str.strip()
                    df_u['password'] = df_u['password'].astype(str).str.strip()
                    match = df_u[(df_u['username'] == u) & (df_u['password'] == p)]
                    if not match.empty:
                        st.session_state.update({"logged_in": True, "user": u, "role": match.iloc[0]['role'], "station": match.iloc[0].get('station', 'General')})
                        st.rerun()
                    else: st.error("❌ ข้อมูลไม่ถูกต้อง")
    st.stop()

# --- 5. MAIN INTERFACE (BY ROLE) ---
role = st.session_state.role
st.sidebar.markdown(f"### 👤 {st.session_state.user}\n**Role:** {role.upper()}")
if st.sidebar.button("🚪 Sign Out"):
    st.session_state.logged_in = False
    st.rerun()

# ---------------- [SECTION: ADMIN] ----------------
if role == "admin":
    st.title("🏛️ Admin Executive Command Center")
    df_all = get_df("sheet1")
    
    # จัดลำดับ Tabs: Analytics -> Repair View -> Master Data -> Dropdown
    tabs = st.tabs(["📈 Analytics", "🔍 Repair View", "👥 Master Data", "🔻 Dropdowns"])

    with tabs[0]: # Analytics & Export
        if not df_all.empty:
            t1, t2, t3 = st.columns(3)
            t1.metric("งานทั้งหมด", len(df_all))
            t2.metric("กำลังซ่อม", len(df_all[df_all['status'].isin(["Pending", "In Progress", "Wait Part"])]))
            t3.metric("เสร็จแล้ว", len(df_all[df_all['status'] == "Completed"]))
            
            st.divider()
            df_report = df_all.drop(columns=['img_user', 'img_tech'], errors='ignore')
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_report.to_excel(writer, index=False, sheet_name='Report')
            st.download_button("📥 Download Excel Report", data=buffer.getvalue(), 
                               file_name=f"Repair_{datetime.now().date()}.xlsx", type="primary")

    with tabs[1]: # Repair View (หน้าแสดงรายละเอียดทั้งหมด)
        st.subheader("🔍 ตรวจสอบรายละเอียดงานซ่อม")
        q_search = st.text_input("ค้นหา SN, WO หรือ Model", key="adm_search").strip().upper()
        
        df_view = df_all.copy()
        if q_search:
            df_view = df_view[df_view['sn'].astype(str).str.contains(q_search) | 
                             df_view['wo'].astype(str).str.contains(q_search) |
                             df_view['model'].astype(str).str.contains(q_search)]

        if not df_view.empty:
            for idx, row in df_view.iloc[::-1].iterrows():
                st_color = "🟢" if row['status'] == "Completed" else "🟡"
                with st.expander(f"{st_color} SN: {row['sn']} | WO: {row['wo']} | {row['status']}"):
                    c1, c2, c3 = st.columns([2, 1, 1])
                    with c1:
                        st.markdown(f"""
                        **📋 รายละเอียดงาน:**
                        * **🔢 Work Order:** `{row['wo']}`
                        * **🆔 Serial Number:** `{row['sn']}`
                        * **📟 Model:** {row['model']}
                        * **📦 Product Name:** {row.get('product', '-')}
                        * **📍 Station:** {row['station']}
                        * **📅 วันที่แจ้ง:** {row['user_time']}
                        * **⚠️ อาการเสีย:** `{row['failure']}`
                        ---
                        **🛠️ ผลการซ่อม:** {row.get('real_case', 'กำลังดำเนินการ')}
                        """)
                    with c2:
                        st.caption("📷 รูปแจ้งซ่อม")
                        if row.get('img_user'):
                            st.image(f"data:image/jpeg;base64,{row['img_user']}", use_container_width=True)
                    with c3:
                        st.caption("📷 รูปงานซ่อม")
                        if row.get('img_tech'):
                            for img in str(row['img_tech']).split('|'):
                                if img: st.image(f"data:image/jpeg;base64,{img}", use_container_width=True)

    with tabs[2]: # Master Data
        st.subheader("👥 Manage Master Data")
        m_sub = st.selectbox("เลือกตาราง", ["users", "model_mat"])
        df_m = get_df(m_sub).dropna(how='all')
        edited = st.data_editor(df_m, num_rows="dynamic", use_container_width=True)
        if st.button(f"💾 Save {m_sub}"):
            ws = ss.worksheet(m_sub)
            ws.clear()
            ws.update([edited.columns.values.tolist()] + edited.fillna("").astype(str).values.tolist())
            st.success("บันทึกข้อมูลแล้ว!")

    with tabs[3]: # Dropdowns
        st.subheader("🔻 Dropdown Settings")
        dd_sub = st.selectbox("เลือกตัวเลือก", ["defect_dropdowns", "action_dropdowns", "classification_dropdowns"])
        df_dd = get_df(dd_sub).dropna(how='all')
        edited_dd = st.data_editor(df_dd, num_rows="dynamic", use_container_width=True)
        if st.button(f"💾 Update {dd_sub}"):
            ws_dd = ss.worksheet(dd_sub)
            ws_dd.clear()
            ws_dd.update([edited_dd.columns.values.tolist()] + edited_dd.fillna("").astype(str).values.tolist())
            st.success("อัปเดตตัวเลือกแล้ว!")

# ---------------- [SECTION: TECHNICIAN] ----------------
elif role == "technician":
    st.title("🔧 Technician Repair Record")
    target_sn = st.text_input("🔍 Scan SN สำหรับซ่อม").strip().upper()
    if target_sn:
        df_main = get_df("sheet1")
        jobs = df_main[df_main['sn'].astype(str) == target_sn].copy()
        if not jobs.empty:
            options = [(i, f"Job #{i+1} | {r['status']} ({r['user_time']})") for i, r in jobs.iterrows()]
            sel = st.radio("เลือกรายการที่ต้องการอัปเดต:", options[::-1], format_func=lambda x: x[1])
            sel_row = sel[0] + 2 # บวก 2 สำหรับ Header ใน Google Sheets

            with st.form("tech_update"):
                st.subheader(f"🛠️ Update SN: {target_sn}")
                stt = st.selectbox("สถานะการซ่อม", ["Completed", "In Progress", "Wait Part", "Scrap"])
                rc = st.text_input("สาเหตุ (Root Cause)")
                dt = st.selectbox("Defect Type", get_dropdown_options("defect_dropdowns"))
                ac = st.selectbox("Action Taken", get_dropdown_options("action_dropdowns"))
                cl = st.selectbox("Classification", get_dropdown_options("classification_dropdowns"))
                imgs = st.file_uploader("แนบรูปหลังซ่อม", accept_multiple_files=True)
                
                if st.form_submit_button("💾 Save Update"):
                    ws = ss.worksheet("sheet1")
                    ws.update(f'I{sel_row}', [[stt]])
                    ws.update(f'K{sel_row}:N{sel_row}', [[rc, dt, ac, cl]])
                    ws.update(f'P{sel_row}:Q{sel_row}', [[st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")]])
                    if imgs:
                        ws.update(f'S{sel_row}', [[save_multiple_images_b64(imgs)]])
                    st.success("บันทึกข้อมูลการซ่อมสำเร็จ!"); st.rerun()
        else:
            st.warning("ไม่พบ SN นี้ในรายการแจ้งซ่อม")

# ---------------- [SECTION: USER] ----------------
elif role == "user":
    st.title("📋 PCBA Repair Reporting")
    u_tabs = st.tabs(["📝 New Request", "🔍 My Tracking"])
    
    with u_tabs[0]: # แจ้งซ่อม
        with st.form("repair_form", clear_on_submit=True):
            st.subheader("บันทึกข้อมูลการแจ้งซ่อม")
            c1, c2 = st.columns(2)
            with c1:
                wo = st.text_input("Work Order (WO)").strip().upper()
                sn = st.text_input("Serial Number (SN)").strip().upper()
                model = st.selectbox("Model", get_dropdown_options("model_mat"))
            with c2:
                product = st.text_input("Product Name")
                station = st.text_input("Station / Line")
                failure = st.text_area("Symptom / อาการเสีย")
            uploaded_file = st.file_uploader("แนบรูปภาพอาการเสีย", type=['jpg', 'jpeg', 'png'])
            
            if st.form_submit_button("🚀 Submit Request", use_container_width=True):
                if wo and sn and failure:
                    # ใส่ฟังก์ชัน save_to_sheets เดิมของคุณตรงนี้
                    st.success("ส่งข้อมูลแจ้งซ่อมเรียบร้อยแล้ว!")
                else:
                    st.error("กรุณากรอกข้อมูลให้ครบถ้วน")

    with u_tabs[1]: # ติดตามงาน
        st.subheader("🔍 ติดตามสถานะงานซ่อม")
        q_user = st.text_input("ค้นหา SN/WO ของคุณ", key="u_search").strip().upper()
        df_u = get_df("sheet1")
        if not df_u.empty:
            my_jobs = df_u[df_u['user_id'].astype(str) == str(st.session_state.user)]
            if q_user:
                my_jobs = my_jobs[my_jobs['sn'].astype(str).str.contains(q_user) | 
                                 my_jobs['wo'].astype(str).str.contains(q_user)]
            
            for idx, row in my_jobs.iloc[::-1].iterrows():
                status = row['status']
                st_color = "🟢" if status == "Completed" else "🟡"
                with st.container(border=True):
                    col_t, col_i = st.columns([3, 1])
                    with col_t:
                        st.markdown(f"### {st_color} Status: {status}")
                        st.markdown(f"""
                        * **WO:** `{row['wo']}` | **SN:** `{row['sn']}`
                        * **Model:** {row['model']} | **Product:** {row.get('product', '-')}
                        * **Station:** {row['station']} | **วันที่:** {row['user_time']}
                        """)
                        st.info(f"⚠️ อาการ: {row['failure']}")
                        if status in ["Pending", "In Progress"]:
                            if st.button(f"🔔 ตามงาน SN: {row['sn'][-4:]}", key=f"p_{idx}"):
                                st.toast("แจ้งเตือนช่างแล้ว!")
                    with col_i:
                        if row.get('img_user'):
                            st.image(f"data:image/jpeg;base64,{row['img_user']}", use_container_width=True)
