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

# ---------------- [SECTION: PROFESSIONAL ADMIN COMMAND CENTER] ----------------
elif role == "admin":
    st.title("🏛️ Admin Executive Command Center")
    
    # ดึงข้อมูลจาก Google Sheets (Sheet หลักที่มี 20 คอลัมน์)
    df_all = get_df("sheet1")
    
    # จัดลำดับ Tabs ใหม่: Analytics -> Repair View (Tab 2) -> Master Data -> Dropdown Settings
    tabs = st.tabs(["📈 Analytics & Export", "🔍 Repair View", "👥 Master Data", "🔻 Dropdown Settings"])

    # --- Tab 1: Analytics & Export (วิเคราะห์ภาพรวม) ---
    with tabs[0]:
        if not df_all.empty:
            t1, t2, t3 = st.columns(3)
            t1.metric("งานทั้งหมด", len(df_all))
            t2.metric("กำลังซ่อม", len(df_all[df_all['status'] == "Pending"]))
            t3.metric("ซ่อมเสร็จแล้ว", len(df_all[df_all['status'] == "Completed"]))
            
            st.divider()
            st.subheader("📂 ออกรายงาน Excel")
            # ตัดคอลัมน์รูปภาพออกเพื่อให้ไฟล์ Excel ไม่หนักเกินไป
            df_report = df_all.drop(columns=['img_user', 'img_tech'], errors='ignore')
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_report.to_excel(writer, index=False, sheet_name='Repair_Report')
            
            st.download_button("📥 Download Full Report", data=buffer.getvalue(), 
                               file_name=f"Repair_Report_{datetime.now().date()}.xlsx", type="primary")

    # --- Tab 2: Repair View (🔍 ติดตามสถานะงานแบบละเอียด) ---
    with tabs[1]:
        st.subheader("🔍 ตรวจสอบและติดตามรายละเอียดงานซ่อม")
        q_sn = st.text_input("ค้นหาด้วย WO หรือ SN", key="admin_search").strip().upper()
        
        df_view = df_all.copy()
        if q_sn:
            df_view = df_view[df_view['sn'].astype(str).str.contains(q_sn) | 
                             df_view['wo'].astype(str).str.contains(q_sn)]

        if not df_view.empty:
            for _, row in df_view.iloc[::-1].iterrows():
                # แสดงผลแบบ Expander เพื่อความสะอาดตาและเป็นมืออาชีพ
                status_color = "🟢" if row['status'] == "Completed" else "🟡"
                with st.expander(f"{status_color} SN: {row['sn']} | WO: {row['wo']} | สถานะ: {row['status']}"):
                    col_text, col_img1, col_img2 = st.columns([2, 1, 1])
                    
                    with col_text:
                        st.markdown(f"### 📋 ข้อมูลการแจ้งซ่อม")
                        # แสดงข้อมูลตามที่คุณต้องการครบทุกช่อง
                        st.write(f"**🔢 Work Order (WO):** {row['wo']}")
                        st.write(f"**🔢 Serial Number (SN):** {row['sn']}")
                        st.write(f"**📟 Model:** {row['model']}")
                        st.write(f"**📦 Product Name:** {row.get('product', '-')}")
                        st.write(f"**📍 Station ที่แจ้ง:** {row['station']}")
                        st.write(f"**📅 วันที่แจ้งซ่อม:** {row['user_time']}")
                        st.markdown(f"**⚠️ อาการเสีย:** `{row['failure']}`")
                        st.divider()
                        st.markdown(f"**🛠️ ผลการซ่อม:** {row.get('real_case', 'รอดำเนินการ...')}")
                        st.caption(f"ผู้แจ้ง: {row['user_id']} | ช่าง: {row.get('tech_id', '-')}")

                    with col_img1:
                        st.caption("📷 รูปอาการเสีย (User)")
                        if row.get('img_user'):
                            st.image(f"data:image/jpeg;base64,{row['img_user']}", use_container_width=True)
                        else:
                            st.info("ไม่มีรูปภาพ")

                    with col_img2:
                        st.caption("📷 รูปขณะซ่อม (Tech)")
                        if row.get('img_tech'):
                            # รองรับหลายรูปที่คั่นด้วย |
                            for img in str(row['img_tech']).split('|'):
                                if img: st.image(f"data:image/jpeg;base64,{img}", use_container_width=True)
        else:
            st.warning("ไม่พบข้อมูลงานซ่อมในระบบ")

    # --- Tab 3: Master Data (👥 จัดการ User และ Model) ---
    with tabs[2]:
        st.subheader("👥 จัดการข้อมูล Master")
        m_sub = st.selectbox("เลือกฐานข้อมูล", ["users", "model_mat"], key="m_data_sel")
        df_master = get_df(m_sub)
        
        if not df_master.empty:
            # ล้างแถวที่เป็น None/Empty อัตโนมัติ (แก้ปัญหา image_e6f4b5.png)
            df_master = df_master.dropna(how='all')
            
            edited = st.data_editor(df_master, num_rows="dynamic", use_container_width=True, key=f"edit_{m_sub}")
            
            if st.button(f"💾 บันทึกการแก้ไข {m_sub}", type="primary"):
                # กรองข้อมูลก่อน Save
                clean_df = edited.dropna(how='all').fillna("").astype(str)
                ws = ss.worksheet(m_sub)
                ws.clear()
                ws.update([clean_df.columns.values.tolist()] + clean_df.values.tolist())
                st.success("อัปเดตฐานข้อมูลสำเร็จ!")
                st.rerun()

    with tabs[3]:  # Repair View
    st.subheader("🔍 Advanced Repair Explorer")
    
    # ช่องค้นหาอัจฉริยะ (ค้นหาได้ทั้ง SN, WO, Model)
    search_query = st.text_input("🔍 ค้นหา (ใส่ SN, WO หรือ Model)").strip().upper()
    
    df_view = df_all.copy()
    if search_query:
        # กรองข้อมูลโดยใช้เงื่อนไข OR (ถ้าเจอคำค้นหาในคอลัมน์ใดคอลัมน์หนึ่งให้แสดงผล)
        df_view = df_view[
            (df_view['sn'].astype(str).str.contains(search_query)) | 
            (df_view['wo'].astype(str).str.contains(search_query)) | 
            (df_view['model'].astype(str).str.contains(search_query))
        ]

    # แสดงผลรายการที่กรองแล้ว
    st.write(f"พบข้อมูลทั้งหมด `{len(df_view)}` รายการ")
    for _, row in df_view.iloc[::-1].head(20).iterrows():
        with st.expander(f"📌 SN: {row['sn']} | WO: {row['wo']} | Model: {row['model']}"):
            # ... (ใส่โค้ดแสดงรายละเอียดและรูปภาพเดิมของคุณ) ...
                
# ---------------- [TECHNICIAN SECTION] ----------------
elif role == "technician":
    st.title("🔧 Technician Repair Record")
    target_sn = st.text_input("🔍 Scan SN").strip().upper()
    if target_sn:
        df_main = get_df("sheet1")
        jobs = df_main[df_main['sn'].astype(str) == target_sn].copy()
        if not jobs.empty:
            options = [(i, f"Job #{i+1} | {r['status']} ({r['user_time']})") for i, r in jobs.iterrows()]
            sel = st.radio("เลือกรายการ:", options[::-1], format_func=lambda x: x[1])
            job = jobs.loc[sel[0]]
            sel_row = sel[0] + 2

            with st.form("tech_update"):
                stt = st.selectbox("Status", ["Completed", "In Progress", "Wait Part", "Scrap"])
                rc = st.text_input("Root Cause")
                dt = st.selectbox("Defect Type", get_dropdown_options("defect_dropdowns"))
                ac = st.selectbox("Action", get_dropdown_options("action_dropdowns"))
                cl = st.selectbox("Classification", get_dropdown_options("classification_dropdowns"))
                imgs = st.file_uploader("Upload Photos", accept_multiple_files=True)
                
                if st.form_submit_button("💾 Save Update"):
                    ws = ss.worksheet("sheet1")
                    ws.update(f'I{sel_row}', [[stt]])
                    ws.update(f'K{sel_row}:N{sel_row}', [[rc, dt, ac, cl]])
                    ws.update(f'P{sel_row}:Q{sel_row}', [[st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")]])
                    if imgs:
                        ws.update(f'S{sel_row}', [[save_multiple_images_b64(imgs)]])
                    send_line_message(job.get('wo','-'), job['sn'], job['model'], f"Update: {stt}", stt, st.session_state.user)
                    st.success("บันทึกสำเร็จ!"); st.rerun()

# ---------------- [SECTION: USER - REPORT & TRACKING] ----------------
if role == "user":
    st.title("📋 PCBA Repair Reporting")
    
    # แบ่งเป็น 2 Tabs: แจ้งซ่อมใหม่ และ ติดตามสถานะ
    u_tabs = st.tabs(["📝 New Repair Request", "🔍 Track Status"])
    
    # --- Tab 1: แจ้งซ่อมใหม่ (ย่อส่วนฟอร์มให้กระชับ) ---
    with u_tabs[0]:
        with st.form("repair_form", clear_on_submit=True):
            st.subheader("บันทึกข้อมูลการแจ้งซ่อม")
            c1, c2 = st.columns(2)
            with c1:
                wo = st.text_input("Work Order (WO)").strip().upper()
                sn = st.text_input("Serial Number (SN)").strip().upper()
                model = st.selectbox("Model", get_dropdown_options("model_mat")) # ดึงจาก Master Data
            with c2:
                product = st.text_input("Product Name")
                station = st.text_input("Station / Line")
                failure = st.text_area("Symptom / อาการเสีย")
            
            uploaded_file = st.file_uploader("แนบรูปภาพอาการเสีย", type=['jpg', 'jpeg', 'png'])
            
            if st.form_submit_button("🚀 Submit Request", use_container_width=True):
                if wo and sn and failure:
                    # Logic บันทึกข้อมูลลง Google Sheets (A-T)
                    # ... (ส่วนบันทึกข้อมูลเดิมของคุณ) ...
                    st.success("ส่งข้อมูลแจ้งซ่อมเรียบร้อยแล้ว!")
                else:
                    st.error("กรุณากรอกข้อมูล WO, SN และอาการเสียให้ครบถ้วน")

 # --- Tab 2: ติดตามสถานะงาน (เวอร์ชันเพิ่มตัวกรองสถานะด่วน) ---
    with u_tabs[1]:
        st.subheader("🔍 ติดตามสถานะงานซ่อม")
        
        # 1. ปุ่มตัวกรองสถานะด่วน (Quick Filters)
        c_f1, c_f2, c_f3, c_f4 = st.columns(4)
        filter_all = c_f1.button("📑 ทั้งหมด", use_container_width=True)
        filter_pending = c_f2.button("🟡 รอซ่อม", use_container_width=True)
        filter_process = c_f3.button("🔵 กำลังซ่อม", use_container_width=True)
        filter_done = c_f4.button("🟢 เสร็จแล้ว", use_container_width=True)

        # 2. ช่องค้นหาอัจฉริยะ
        search_query = st.text_input("🔍 ค้นหาด้วย SN, WO หรือ Model", key="user_search_query").strip().upper()
        
        df_user = get_df("sheet1")
        if not df_user.empty:
            # เริ่มต้นด้วยงานของตัวเอง
            my_jobs = df_user[df_user['user_id'].astype(str) == str(st.session_state.user)]
            
            # Logic การกรองข้อมูล (Filter Logic)
            if search_query:
                # ถ้ามีการค้นหา ให้ค้นจากฐานข้อมูลทั้งหมด
                my_jobs = df_user[
                    (df_user['sn'].astype(str).str.contains(search_query)) | 
                    (df_user['wo'].astype(str).str.contains(search_query)) | 
                    (df_user['model'].astype(str).str.contains(search_query))
                ]
            
            # กรองตามปุ่มสถานะที่กด (ถ้ามีการกดปุ่ม)
            if filter_pending:
                my_jobs = my_jobs[my_jobs['status'] == "Pending"]
            elif filter_process:
                my_jobs = my_jobs[my_jobs['status'].isin(["In Progress", "Wait Part"])]
            elif filter_done:
                my_jobs = my_jobs[my_jobs['status'] == "Completed"]

            # 3. แสดงผลรายการ
            if not my_jobs.empty:
                st.caption(f"💡 แสดงผลทั้งหมด {len(my_jobs)} รายการ")
                for idx, row in my_jobs.iloc[::-1].iterrows():
                    status = row['status']
                    # กำหนดสีตามสถานะ
                    st_color = "🟢" if status == "Completed" else "🟡" if status == "Pending" else "🔵"
                    
                    with st.container(border=True):
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.markdown(f"### {st_color} Status: {status}")
                            st.markdown(f"""
                            **📄 ข้อมูลรายการ:**
                            * **WO/Asset:** `{row['wo']}` | **SN:** `{row['sn']}`
                            * **Model:** {row['model']} ({row.get('product', '-')})
                            * **แจ้งเมื่อ:** {row['user_time']}
                            """)
                            st.info(f"⚠️ **อาการ:** {row['failure']}")
                            
                            if status == "Completed":
                                st.success(f"🛠️ **ผลซ่อม:** {row.get('real_case', '-')}")
                                st.caption(f"👨‍🔧 ช่าง: {row.get('tech_id','-')} | {row.get('tech_time','-')}")
                        
                        with col2:
                            if row.get('img_user'):
                                st.image(f"data:image/jpeg;base64,{row['img_user']}", use_container_width=True)
                            
                            if status in ["Pending", "Wait Part", "In Progress"]:
                                if st.button(f"🔔 ตามงาน", key=f"ping_btn_{idx}", use_container_width=True):
                                    send_line_message(row['wo'], row['sn'], row['model'], "❗ ตามงานด่วน", "Re-notify", st.session_state.user)
                                    st.toast(f"ส่งแจ้งเตือนตามงาน {row['sn']} แล้ว!")
            else:
                st.warning("🔎 ไม่พบข้อมูลที่ตรงกับเงื่อนไข")
