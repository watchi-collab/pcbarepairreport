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
    
    df_all = get_df("sheet1")
    # ปรับลำดับ: Analytics -> Repair View -> Master Data -> Dropdowns
    tabs = st.tabs(["📈 Analytics & Export", "🔍 Repair View", "👥 Master Data", "🔻 Dropdown Settings"])

    # --- Tab 1: Analytics & Export ---
    with tabs[0]:
        if not df_all.empty:
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

            col_chart1, col_chart2 = st.columns(2)
            with col_chart1:
                st.write("📊 **Jobs by Category**")
                st.bar_chart(df_all['category'].value_counts())
            with col_chart2:
                st.write("📈 **Daily Repair Trend**")
                df_all['date'] = pd.to_datetime(df_all['user_time']).dt.date
                st.line_chart(df_all.groupby('date').size())

            st.divider()
            st.subheader("📂 Export Professional Report")
            # (ส่วน Export Excel คงเดิมตามโค้ดก่อนหน้า)
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_clean = df_all.drop(columns=['img_user', 'img_tech'], errors='ignore')
                df_clean.to_excel(writer, index=False, sheet_name='Details')
            
            st.download_button(label="📥 Download Full Report (Excel)", data=buffer.getvalue(), 
                               file_name=f"Full_Report_{datetime.now().date()}.xlsx", type="primary", use_container_width=True)

    # --- Tab 2: Repair View (ย้ายมาอยู่นี่แล้ว 🔍) ---
    with tabs[1]:
        st.subheader("🔍 Repair Explorer (Detailed View)")
        search_sn = st.text_input("🔍 ค้นหาด้วย Serial Number (SN)", key="view_search").strip().upper()
        
        df_view = df_all.copy()
        if search_sn:
            df_view = df_view[df_view['sn'].astype(str).str.contains(search_sn)]

        if not df_view.empty:
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
        else:
            st.info("ไม่พบข้อมูลงานซ่อม")

    # --- Tab 3: Master Data ---
    with tabs[2]:
        st.subheader("👥 User & Model Management")
        sub_master = st.selectbox("เลือกตารางที่ต้องการจัดการ", ["users", "model_mat"], key="master_tab_sel")
        df_edit = get_df(sub_master)
        
        if not df_edit.empty:
            df_edit = df_edit.dropna(how='all')
            edited = st.data_editor(df_edit, num_rows="dynamic", use_container_width=True, key=f"editor_{sub_master}")
            
            if st.button(f"💾 Save {sub_master} Changes", type="primary", use_container_width=True):
                ws = ss.worksheet(sub_master)
                ws.clear()
                clean_save = edited.dropna(how='all').fillna("").astype(str)
                ws.update([clean_save.columns.values.tolist()] + clean_save.values.tolist())
                st.success("บันทึกข้อมูลเรียบร้อย!")
                st.rerun()

    # --- Tab 4: Dropdown Settings ---
    with tabs[3]:
        st.subheader("🔻 Manage Dropdown Options")
        dd_sheet = st.selectbox("หัวข้อที่แก้ไข", ["defect_dropdowns", "action_dropdowns", "classification_dropdowns"])
        df_dd = get_df(dd_sheet)
        if not df_dd.empty:
            edited_dd = st.data_editor(df_dd, num_rows="dynamic", use_container_width=True)
            if st.button(f"💾 Update {dd_sheet}", use_container_width=True):
                ws_dd = ss.worksheet(dd_sheet)
                ws_dd.clear()
                ws_dd.update([edited_dd.columns.values.tolist()] + edited_dd.fillna("").astype(str).values.tolist())
                st.success("อัปเดตสำเร็จ")

# ---------------- [SECTION: TECHNICIAN] ----------------
elif role == "technician":
    # ... (โค้ด technician ต่อจากนี้) ...
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

# ---------------- [USER SECTION] ----------------
elif role == "user":
    menu = st.sidebar.radio("📍 เมนู", ["🚀 แจ้งซ่อมใหม่", "🔍 ติดตามสถานะงาน"])
    u_station = st.session_state.get('station', 'General')

    if menu == "🚀 แจ้งซ่อมใหม่":
        st.title("📱 Repair Request Form")
        with st.form("request_form", clear_on_submit=True):
            cat = st.radio("ประเภท", ["PCBA", "Machine"], horizontal=True)
            c1, c2 = st.columns(2)
            wo = c1.text_input("WO / Asset").strip().upper()
            sn = c2.text_input("SN").strip().upper()
            model = st.selectbox("Model", get_dropdown_options("model_mat")) if cat == "PCBA" else st.text_input("Machine Model")
            failure = st.text_area("อาการเสีย")
            u_file = st.file_uploader("แนบรูป", type=['jpg','png','jpeg'])
            
            if st.form_submit_button("🚀 ส่งข้อมูล"):
                if not sn or not wo: st.error("กรุณากรอกข้อมูลให้ครบ")
                else:
                    img_b64 = save_image_b64(u_file)
                    new_row = [st.session_state.user, cat, wo, sn, model, "-", u_station, failure, "Pending", 
                               datetime.now().strftime("%Y-%m-%d %H:%M"), "", "", "", "", "", "", "", img_b64, "", ""]
                    ss.worksheet("sheet1").append_row(new_row)
                    send_line_message(wo, sn, model, failure, "New Request", st.session_state.user)
                    st.success("ส่งข้อมูลสำเร็จ!"); st.balloons()

    elif menu == "🔍 ติดตามสถานะงาน":
        st.title("🔎 Follow Up")
        df_m = get_df("sheet1")
        if not df_m.empty:
            my_jobs = df_m[df_m['user_id'].astype(str) == str(st.session_state.user)].tail(10)
            for idx, r in my_jobs.iloc[::-1].iterrows():
                with st.container(border=True):
                    st.write(f"**SN: {r['sn']}** | Status: `{r['status']}`")
                    if r['status'] in ["Pending", "Wait Part"]:
                        if st.button("🔔 ตามงาน", key=f"notify_{idx}"):
                            send_line_message(r['wo'], r['sn'], r['model'], "❗ ตามงานด่วน", "Re-notify", st.session_state.user)
                            st.toast("ส่งแจ้งเตือนแล้ว")
