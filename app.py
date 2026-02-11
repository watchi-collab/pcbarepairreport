# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import io
import base64
from datetime import datetime
import plotly.express as px
from PIL import Image
import requests
import json

# --- 1. SETTINGS & STYLE ---
st.set_page_config(page_title="PCBA System 2026 PRO", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #eee; }
    .stTabs [aria-selected="true"] { background-color: #004a99 !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. CONNECTIONS & HELPERS ---
@st.cache_resource
def init_connections():
    try:
        creds_dict = st.secrets["gcp_service_account"]
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
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
        if not df.empty: df.columns = df.columns.str.strip()
        return df.fillna("")
    except:
        return pd.DataFrame()

def get_category_options():
    df = get_df("category_dropdowns")
    return df.iloc[:, 0].astype(str).tolist() if not df.empty else ["PCBA", "Machine"]

def get_dropdown_options(sheet_name):
    df = get_df(sheet_name)
    options = ["--กรุณาเลือก--"]
    if not df.empty: options.extend(df.iloc[:, 0].astype(str).tolist())
    return options

def save_multiple_images_b64(files):
    """ฟังก์ชันสำหรับแปลงไฟล์รูปภาพหลายไฟล์ให้เป็น Base64 String ชุดเดียว"""
    if not files: return ""
    encoded_images = []
    for file in files:
        try:
            img = Image.open(file)
            # ปรับขนาดและลดคุณภาพเพื่อไม่ให้ข้อมูลใน Google Sheets เต็มเร็วเกินไป
            img.thumbnail((400, 400)) 
            buf = io.BytesIO()
            img.convert('RGB').save(buf, format="JPEG", quality=40)
            b64 = base64.b64encode(buf.getvalue()).decode()
            encoded_images.append(b64)
        except Exception as e:
            continue
    # รวมรูปภาพเข้าด้วยกันโดยใช้เครื่องหมาย | คั่น (เพื่อให้ตอนดึงมาโชว์แยกรูปได้)
    return "|".join(encoded_images)

def send_line_message(wo, sn, model, failure, status_type="New Request", operator="Unknown"):
    try:
        line_token = st.secrets["line_channel_access_token"]
        line_to = st.secrets["line_group_id"]
        url = "https://api.line.me/v2/bot/message/push"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {line_token}"}
        
        header_map = {
            "New Request": "📢 แจ้งซ่อมใหม่",
            "Completed": "✅ ซ่อมเสร็จสิ้น",
            "Re-notify": "🔔 ติดตามงาน (Urgent!)"
        }
        header_text = header_map.get(status_type, f"📦 อัปเดตสถานะ: {status_type}")

        message_text = (
            f"{header_text}\n---------------------------\n"
            f"🔢 WO: {wo}\n🆔 SN: {sn}\n📦 Model: {model}\n"
            f"⚠️ อาการ: {failure}\n👤 ผู้แจ้ง: {operator}\n"
            f"---------------------------\n⏰ เวลา: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        payload = {"to": line_to, "messages": [{"type": "text", "text": message_text}]}
        requests.post(url, headers=headers, data=json.dumps(payload))
        return True
    except:
        return False

# --- 3. SESSION STATE ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user' not in st.session_state: st.session_state.user = ""
if 'role' not in st.session_state: st.session_state.role = ""
if 'station' not in st.session_state: st.session_state.station = ""

# --- 4. LOGIN & PUBLIC TRACKING ---
if not st.session_state.logged_in:
    tab1, tab2 = st.tabs(["🔍 ติดตามสถานะงาน (Public)", "🔐 เข้าสู่ระบบ (Staff Only)"])
    
    with tab1:
        st.title("🔎 PCBA Repair Tracking")
        c1, c2 = st.columns(2)
        p_sn = c1.text_input("🔢 SN / WO").strip().upper()
        p_mo = c2.text_input("📦 Model").strip().upper()
        
        if p_sn or p_mo:
            df_pub = get_df("sheet1")
            if not df_pub.empty:
                res = df_pub[
                    (df_pub['sn'].astype(str).str.contains(p_sn) | df_pub['wo'].astype(str).str.contains(p_sn)) &
                    (df_pub['model'].astype(str).str.contains(p_mo))
                ]
                if not res.empty:
                    for _, r in res.iterrows():
                        st.info(f"SN: {r['sn']} | Status: {r['status']} | Last Update: {r.get('tech_time','-')}")
                else: st.warning("ไม่พบข้อมูล")

    with tab2:
        with st.form("login_form"):
            u = st.text_input("Username").strip()
            p = st.text_input("Password", type="password").strip()
            
            if st.form_submit_button("Login"):
                df_u = get_df("users")
                if not df_u.empty:
                    # แปลงข้อมูลใน Google Sheets ให้เป็น String และลบช่องว่างทิ้ง
                    df_u['username'] = df_u['username'].astype(str).str.strip()
                    df_u['password'] = df_u['password'].astype(str).str.strip()
                    
                    # ตรวจสอบคู่ Username & Password
                    match = df_u[(df_u['username'] == u) & (df_u['password'] == p)]
                    
                    if not match.empty:
                        st.session_state.update({
                            "logged_in": True, 
                            "user": u, 
                            "role": match.iloc[0]['role'], 
                            "station": match.iloc[0].get('station', 'General')
                        })
                        st.rerun()
                    else: 
                        st.error("❌ ข้อมูลไม่ถูกต้อง (โปรดเช็ค Username/Password)")

# --- 5. SIDEBAR (AFTER LOGIN) ---
with st.sidebar:
    st.markdown(f"### 👤 {st.session_state.user}\n**Role:** {st.session_state.role.upper()}")
    if st.button("🚪 Sign Out"):
        st.session_state.logged_in = False
        st.rerun()
    st.divider()
    st.write("● System Online" if status_conn else "● Offline")

# --- 6. MAIN CONTENT BY ROLE ---
role = st.session_state.role

# ---------------- [SECTION: PROFESSIONAL ADMIN COMMAND CENTER] ----------------
elif role == "admin":
    st.title("🏛️ Admin Executive Command Center")
    
    # ดึงข้อมูลหลักจาก Google Sheets
    df_all = get_df("sheet1")
    
    # สร้างเมนู Tabs 4 ส่วนหลัก
    tabs = st.tabs(["📈 Analytics & Export", "👥 Master Data", "🔻 Dropdown Settings", "🔍 Repair View"])

    # --- Tab 1: Analytics & Export (ส่วนวิเคราะห์และดึงรายงาน) ---
    with tabs[0]:
        if not df_all.empty:
            # 1.1 Executive Summary Metrics
            total = len(df_all)
            completed = len(df_all[df_all['status'] == "Completed"])
            pending = len(df_all[df_all['status'] == "Pending"])
            success_rate = (completed / total * 100) if total > 0 else 0

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Jobs", total)
            c2.metric("Pending Tasks", pending, delta=f"{pending} jobs", delta_color="inverse")
            c3.metric("Completed", completed)
            c4.metric("Success Rate", f"{success_rate:.1f}%")

            st.divider()

            # 1.2 กราฟวิเคราะห์
            col_chart1, col_chart2 = st.columns(2)
            with col_chart1:
                st.write("📊 **Jobs by Category**")
                st.bar_chart(df_all['category'].value_counts())
            with col_chart2:
                st.write("📈 **Daily Repair Trend**")
                df_all['date'] = pd.to_datetime(df_all['user_time']).dt.date
                st.line_chart(df_all.groupby('date').size())

            st.divider()

            # 1.3 ระบบ Export Excel รายเดือน/รายสัปดาห์ พร้อม Summary Sheet
            st.subheader("📂 Export Professional Report")
            col_ex1, col_ex2 = st.columns(2)
            with col_ex1:
                export_type = st.selectbox("เลือกประเภทรายงาน", ["รายสัปดาห์ (Weekly)", "รายเดือน (Monthly)", "ทั้งหมด (All)"])
            with col_ex2:
                selected_date = st.date_input("เลือกวันที่เริ่มต้นเพื่อกรองข้อมูล", datetime.now().date())

            # Logic การกรองวันที่
            df_all['user_time_dt'] = pd.to_datetime(df_all['user_time'])
            if export_type == "รายสัปดาห์ (Weekly)":
                start_date = pd.to_datetime(selected_date)
                end_date = start_date + pd.Timedelta(days=7)
                df_export = df_all[(df_all['user_time_dt'] >= start_date) & (df_all['user_time_dt'] < end_date)]
            elif export_type == "รายเดือน (Monthly)":
                df_export = df_all[(df_all['user_time_dt'].dt.month == selected_date.month) & (df_all['user_time_dt'].dt.year == selected_date.year)]
            else:
                df_export = df_all

            if not df_export.empty:
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    # Sheet 1: รายละเอียด (ลบรูปออกเพื่อให้ไฟล์เบา)
                    df_clean = df_export.drop(columns=['img_user', 'img_tech', 'user_time_dt', 'date'], errors='ignore')
                    df_clean.to_excel(writer, index=False, sheet_name='Repair_Details')
                    # Sheet 2: Executive Summary
                    summary_status = df_clean['status'].value_counts().reset_index()
                    summary_status.columns = ['Status', 'Count']
                    summary_status.to_excel(writer, index=False, sheet_name='Summary_Report', startrow=1, startcol=1)
                    
                    # ปรับแต่งความสวยงาม
                    workbook = writer.book
                    header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1})
                    ws_sum = writer.sheets['Summary_Report']
                    ws_sum.write('B1', 'Summary by Status', header_fmt)
                    ws_sum.set_column('B:C', 20)

                st.download_button(label="📥 Download Excel Report", data=buffer.getvalue(), 
                                   file_name=f"Repair_Report_{export_type}.xlsx", type="primary", use_container_width=True)

    # --- Tab 2: Master Data (จัดการ Users & Models - พิมพ์ได้ ลบได้) ---
    with tabs[1]:
        st.subheader("👥 User & Model Management")
        sub_master = st.selectbox("เลือกตารางที่ต้องการจัดการ", ["users", "model_mat"], key="master_sel")
        df_edit = get_df(sub_master)
        
        if not df_edit.empty:
            st.info("💡 เคล็ดลับ: พิมพ์ในตารางเพื่อแก้ไข หรือเพิ่มแถวใหม่ที่บรรทัดสุดท้ายได้ทันที")
            edited = st.data_editor(df_edit, num_rows="dynamic", use_container_width=True)
            
            c_save, c_del = st.columns([1, 1])
            if c_save.button(f"💾 Save {sub_master} Changes", type="primary", use_container_width=True):
                ws = ss.worksheet(sub_master)
                ws.clear()
                ws.update([edited.columns.values.tolist()] + edited.fillna("").astype(str).values.tolist())
                st.success("บันทึกข้อมูลเรียบร้อย!")
                st.rerun()
            
            # ฟังก์ชันลบข้อมูลเฉพาะจุด
            with st.expander("❌ ลบข้อมูลผู้ใช้/โมเดล"):
                target_del = st.selectbox(f"เลือก {df_edit.columns[0]} ที่ต้องการลบ", df_edit.iloc[:,0].tolist())
                if st.button("Confirm Delete", type="secondary"):
                    new_df = df_edit[df_edit.iloc[:,0] != target_del]
                    ss.worksheet(sub_master).clear()
                    ss.worksheet(sub_master).update([new_df.columns.values.tolist()] + new_df.values.tolist())
                    st.warning("ลบข้อมูลสำเร็จ")
                    st.rerun()

    # --- Tab 3: Dropdown Settings (ตั้งค่าลิสต์รายการซ่อม) ---
    with tabs[2]:
        st.subheader("🔻 Manage Dropdown Options")
        dd_sheet = st.selectbox("เลือกหัวข้อที่ต้องการแก้ไข", ["defect_dropdowns", "action_dropdowns", "classification_dropdowns"])
        df_dd = get_df(dd_sheet)
        if not df_dd.empty:
            edited_dd = st.data_editor(df_dd, num_rows="dynamic", use_container_width=True)
            if st.button(f"💾 Update {dd_sheet}", use_container_width=True):
                ws_dd = ss.worksheet(dd_sheet)
                ws_dd.clear()
                ws_dd.update([edited_dd.columns.values.tolist()] + edited_dd.fillna("").astype(str).values.tolist())
                st.success("อัปเดตตัวเลือกสำเร็จ")

    # --- Tab 4: Repair View (ส่องรายละเอียดและรูปภาพทั้งหมด) ---
    with tabs[3]:
        st.subheader("🔍 Repair Explorer (Detailed View)")
        search_sn = st.text_input("🔍 ค้นหาด้วย Serial Number (SN)").strip().upper()
        
        df_view = df_all.copy()
        if search_sn:
            df_view = df_view[df_view['sn'].astype(str).str.contains(search_sn)]

        for _, row in df_view.iloc[::-1].iterrows():
            with st.expander(f"📌 SN: {row['sn']} | WO: {row.get('wo','-')} | Status: {row['status']}"):
                col_info, col_img_u, col_img_t = st.columns([2, 1, 1])
                with col_info:
                    st.markdown(f"**Model:** {row['model']} | **Station:** {row['station']}")
                    st.error(f"⚠️ **Symptom:** {row['failure']}")
                    st.success(f"🛠️ **Action:** {row.get('action','-')} | **Cause:** {row.get('real_case','-')}")
                    st.caption(f"Reporter: {row['user_id']} ({row['user_time']})")
                    st.caption(f"Technician: {row.get('tech_id','-')} ({row.get('tech_time','-')})")
                
                with col_img_u:
                    st.write("📷 **User Photo**")
                    if row.get('img_user'):
                        st.image(f"data:image/jpeg;base64,{row['img_user']}", use_container_width=True)
                
                with col_img_t:
                    st.write("📷 **Repair Photos**")
                    if row.get('img_tech'):
                        t_imgs = str(row['img_tech']).split('|')
                        for t_img in t_imgs:
                            if t_img: st.image(f"data:image/jpeg;base64,{t_img}", use_container_width=True)
# ---------------- [SECTION: TECHNICIAN] ----------------
elif role == "technician":
    st.title("🔧 Technician Repair Record")
    target_sn = st.text_input("🔍 Scan Serial Number (SN)").strip().upper()

    if target_sn:
        df_main = get_df("sheet1")
        if not df_main.empty:
            # ค้นหา SN ที่ตรงกัน
            jobs = df_main[df_main['sn'].astype(str) == target_sn].copy()
            
            if not jobs.empty:
                # ตัวเลือกรายการ (เรียงจากใหม่ไปเก่า)
                options = [(i, f"Job #{i+1} | Status: {r['status']} | Model: {r['model']} ({r['user_time']})") for i, r in jobs.iterrows()]
                options.reverse() 
                
                sel = st.radio("เลือกรายการที่ต้องการดำเนินการ:", options, format_func=lambda x: x[1])
                idx_original = sel[0]
                job = jobs.loc[idx_original]
                sel_row = idx_original + 2  # Row ใน Google Sheets

                with st.container(border=True):
                    c_u1, c_u2 = st.columns([2, 1])
                    with c_u1:
                        st.markdown(f"### 🔢 SN: {job['sn']}")
                        st.markdown(f"**📦 Model:** {job['model']} | **🔢 WO:** {job.get('wo', '-')}")
                        st.error(f"⚠️ **Symptom:** {job.get('failure', 'N/A')}")
                    
                    with c_u2:
                        # แสดงรูปจากผู้แจ้ง (คอลัมน์ R)
                        u_img = job.get('img_user', '')
                        if u_img and str(u_img) not in ["", "None", "nan"]:
                            st.image(f"data:image/jpeg;base64,{u_img}", caption="รูปภาพจากผู้แจ้ง", use_container_width=True)
                        else:
                            st.caption("🚫 ไม่มีรูปประกอบจากผู้แจ้ง")

                # --- ฟอร์มบันทึกผลการซ่อม ---
                with st.form("update_form"):
                    st.write("### 📝 บันทึกผลการซ่อม")
                    col_f1, col_f2 = st.columns(2)
                    
                    with col_f1:
                        stt = st.selectbox("Status", ["Completed", "In Progress", "Wait Part", "Scrap"])
                        rc = st.text_input("Real Case / Root Cause", placeholder="ระบุสาเหตุที่พบ")
                        dt = st.selectbox("Defect Type", get_dropdown_options("defect_dropdowns"))
                    
                    with col_f2:
                        ac = st.selectbox("Action", get_dropdown_options("action_dropdowns"))
                        cl = st.selectbox("Classification", get_dropdown_options("classification_dropdowns"))
                        imgs = st.file_uploader("Upload Repair Photo(s)", accept_multiple_files=True)

                    if st.form_submit_button("💾 Save Update"):
                        ws = ss.worksheet("sheet1")
                        
                        # 1. อัปเดตสถานะ (Col I)
                        ws.update(f'I{sel_row}', [[stt]])
                        
                        # 2. อัปเดตรายละเอียด (K: Real Case, L: Defect Type, M: Action, N: Classification)
                        ws.update(f'K{sel_row}:N{sel_row}', [[rc, dt, ac, cl]])
                        
                        # 3. อัปเดตข้อมูลผู้ซ่อม (P: Tech ID, Q: Tech Time)
                        ws.update(f'P{sel_row}:Q{sel_row}', [[st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")]])
                        
                        # 4. จัดการรูปภาพช่าง (ลงที่ Col S ตามโครงสร้างใหม่)
                        if imgs:
                            img_tech_b64 = save_multiple_images_b64(imgs) # ฟังก์ชันรวมรูปเป็น b64
                            ws.update(f'S{sel_row}', [[img_tech_b64]])

                        # 5. แจ้งเตือนผ่าน LINE
                        send_line_message(
                            job.get('wo', '-'), job['sn'], job['model'], 
                            f"ผลซ่อม: {stt} | {rc}", 
                            status_type=stt, 
                            operator=st.session_state.user
                        )
                        
                        st.success(f"✅ บันทึกข้อมูล SN: {job['sn']} เรียบร้อย!")
                        st.balloons()
                        st.rerun()
            else:
                st.warning("❌ ไม่พบข้อมูล SN นี้ในระบบ")
                
# ---------------- [SECTION: USER / OPERATOR] ----------------
elif role == "user":
    menu = st.sidebar.radio("📍 เมนูการใช้งาน", ["🚀 แจ้งซ่อมใหม่", "🔍 ติดตามสถานะงาน"])
    
    # แก้ไข NameError: ดึงค่าสถานะของผู้ใช้งานปัจจุบัน
    u_station = st.session_state.get('station', 'General Station')

    if menu == "🚀 แจ้งซ่อมใหม่":
        st.title("📱 Repair Request Form")
        
        with st.form("request_form", clear_on_submit=True):
            # 1. เลือกประเภทงาน
            repair_category = st.radio("🛠️ เลือกประเภทงานซ่อม", ["PCBA", "Machine"], horizontal=True)
            
            col1, col2 = st.columns(2)
            with col1:
                wo = st.text_input("Work Order / Asset No.", placeholder="เลข WO หรือ Asset...").strip().upper()
            with col2:
                sn = st.text_input("Serial Number (SN)", placeholder="สแกน SN...").strip().upper()
            
            # 2. ปรับเปลี่ยน Model ตามประเภท
            if repair_category == "PCBA":
                model_options = get_dropdown_options("model_mat")
                model = st.selectbox("Model PCBA", model_options)
            else:
                model = st.text_input("Machine Name / Model", placeholder="ระบุชื่อเครื่องจักร/รุ่น")
            
            st.info(f"📍 **แจ้งจากสถานี:** {u_station}")
            
            failure = st.text_area("Symptom / Failure Description (อาการเสีย)")
            u_file = st.file_uploader("Attach Photo (รูปอาการเสีย)", type=['png', 'jpg', 'jpeg'])

            submit_btn = st.form_submit_button("🚀 ส่งข้อมูลแจ้งซ่อม")

            if submit_btn:
                # ตรวจสอบความถูกต้องของข้อมูล
                is_pcba_invalid = (repair_category == "PCBA" and (model == "--กรุณาเลือก--" or not model))
                if not sn or not wo or is_pcba_invalid:
                    st.error("❌ กรุณากรอกข้อมูลสำคัญ (WO, SN, Model) ให้ครบถ้วน")
                else:
                    with st.spinner("กำลังบันทึกข้อมูล..."):
                        # ค้นหา Product Name กรณี PCBA
                        p_name = "-"
                        if repair_category == "PCBA":
                            df_models = get_df("model_mat")
                            if not df_models.empty:
                                match = df_models[df_models['model'].astype(str) == str(model)]
                                p_name = match.iloc[0]['product_name'] if not match.empty else "-"
                        
                        img_b64 = save_image_b64(u_file)

                        # จัดเรียงข้อมูลลง A-T (20 คอลัมน์ ตามโครงสร้างล่าสุดของคุณ)
                        new_row = [
                            st.session_state.user,      # A: user_id
                            repair_category,            # B: category
                            wo,                         # C: wo
                            sn,                         # D: sn
                            model,                      # E: model
                            p_name,                     # F: product
                            u_station,                  # G: station
                            failure,                    # H: failure
                            "Pending",                  # I: status
                            datetime.now().strftime("%Y-%m-%d %H:%M"), # J: user_time
                            "", "", "", "", "",         # K-O: เว้นว่าง (สำหรับช่าง)
                            "",                         # P: tech_id
                            "",                         # Q: tech_time
                            img_b64,                    # R: img_user
                            "",                         # S: img_tech
                            ""                          # T: last_notify (ลำดับที่ 20)
                        ]
                        
                        # บันทึกข้อมูลเพียงครั้งเดียว
                        ss.worksheet("sheet1").append_row(new_row)
                        
                        # ส่งแจ้งเตือนผ่าน LINE
                        send_line_message(
                            wo, sn, f"[{repair_category}] {model}", 
                            failure, 
                            status_type="New Request", 
                            operator=st.session_state.user
                        )
                        
                        st.success(f"✅ บันทึกรายการ {repair_category} สำเร็จ!")
                        st.balloons()
                        # st.rerun() # เปิดใช้งานหากต้องการ Refresh หน้าจอทันที
    # --- ฟีเจอร์ที่ 2: ติดตามสถานะ (เวอร์ชันตัด QA ออก) ---
    elif menu == "🔍 ติดตามสถานะงาน":
        st.title("🔎 Follow Up Status")
        search_input = st.text_input("🔍 ค้นหาด่วน (SN/WO)", placeholder="พิมพ์เลข SN หรือ WO เพื่อค้นหา...").strip().upper()

        df_main = get_df("sheet1")
        if not df_main.empty:
            # 1. การกรองข้อมูล: ถ้ามีการพิมพ์ค้นหาให้หาจากทั้งหมด ถ้าไม่พิมพ์ให้โชว์แค่ของ User คนนั้น 10 รายการล่าสุด
            if search_input:
                filtered_df = df_main[df_main['sn'].astype(str).str.contains(search_input) | 
                                    df_main['wo'].astype(str).str.contains(search_input)]
            else:
                filtered_df = df_main[df_main['user_id'].astype(str) == str(st.session_state.user)].tail(10)

            if filtered_df.empty:
                st.info("💡 ไม่พบรายการแจ้งซ่อมของคุณในขณะนี้")
            else:
                # แสดงรายการจากใหม่ไปเก่า (Reverse)
                for idx, r in filtered_df.iloc[::-1].iterrows():
                    status = r.get('status', 'Pending')
                    row_index = idx + 2
                    
                    # กำหนดสีและคำอธิบายตามสถานะ
                    if status == "Pending":
                        status_desc, waiting_for, color = "🟠 Pending", "⏳ รอช่างรับงาน", "#FFA500"
                    elif status == "Completed":
                        status_desc, waiting_for, color = "✅ Completed", "📦 ซ่อมเสร็จสิ้น", "#28A745"
                    elif status == "In Progress":
                        status_desc, waiting_for, color = "🔵 In Progress", "🛠️ กำลังดำเนินการซ่อม", "#007BFF"
                    else:
                        status_desc, waiting_for, color = f"🔍 {status}", "", "#6C757D"

                    with st.container(border=True):
                        # ส่วนหัว Card แสดงข้อมูลหลัก
                        st.markdown(f"""
                            <div style="border-left: 5px solid {color}; padding-left: 15px; margin-bottom: 10px;">
                                <h4 style="margin:0;">SN: {r['sn']} | {status_desc}</h4>
                                <small style="color: #666;">Model: {r['model']} | WO: {r.get('wo','-')}</small><br>
                                <strong style="color: {color}; font-size: 0.85rem;">{waiting_for}</strong>
                            </div>
                        """, unsafe_allow_html=True)

                        c1, c2 = st.columns([2, 1])
                        with c1:
                            st.write(f"⏱️ **เวลาที่แจ้ง:** {r['user_time']}")
                            if status != "Pending" and r.get('tech_id'):
                                st.write(f"👷 **ช่างผู้ดูแล:** {r['tech_id']}")

                        with c2:
                            # แสดงปุ่ม "ตามงาน" เฉพาะงานที่ยังไม่เสร็จ
                            if status in ["Pending", "Wait Part"]:
                                now = datetime.now()
                                last_notify_str = str(r.get('last_notify', ''))
                                can_notify = True
                                
                                # ตรวจสอบ Cooldown 10 นาที (600 วินาที)
                                if last_notify_str and last_notify_str not in ["", "None", "nan"]:
                                    try:
                                        last_dt = datetime.strptime(last_notify_str, "%Y-%m-%d %H:%M")
                                        if (now - last_dt).total_seconds() < 600:
                                            can_notify = False
                                    except: pass

                                # --- แก้ไขส่วนที่มีปัญหา Syntax Error ---
                                    if can_notify:
                                        if st.button("🔔 ตามงานด่วน", key=f"btn_{idx}", type="primary", use_container_width=True):
                                            # ตรวจสอบการปิดวงเล็บในส่วนนี้
                                            success = send_line_message(
                                                r.get('wo','-'), 
                                                r['sn'], 
                                                r['model'], 
                                                "❗ งานยังไม่ได้รับการแก้ไข รบกวนช่างตรวจสอบครับ/ค่ะ", 
                                                status_type="Re-notify", 
                                                operator=st.session_state.user
                                            ) # <--- ปิดวงเล็บให้ตรงกับบรรทัด success
                                            
                                            if success:
                                                # อัปเดตเวลาแจ้งเตือนล่าสุดลงคอลัมน์ T (ลำดับที่ 20)
                                                ss.worksheet("sheet1").update_cell(row_index, 20, datetime.now().strftime("%Y-%m-%d %H:%M"))
                                                st.toast("✅ ส่งแจ้งเตือนตามงานแล้ว!", icon="🔔")
                                                st.rerun()
