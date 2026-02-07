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

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user' not in st.session_state: st.session_state.user = ""
if 'role' not in st.session_state: st.session_state.role = ""
if 'station' not in st.session_state: st.session_state.station = ""

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
    except:
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

def get_dropdown_options(sheet_name):
    df = get_df(sheet_name)
    options = ["--กรุณาเลือก--"]
    if not df.empty: options.extend(df.iloc[:, 0].astype(str).tolist())
    return options

def save_image_b64(file):
    if not file: return ""
    img = Image.open(file)
    img.thumbnail((400, 400))
    buf = io.BytesIO()
    img.convert('RGB').save(buf, format="JPEG", quality=40)
    return base64.b64encode(buf.getvalue()).decode()

def save_multiple_images_b64(files):
    if not files: return ""
    return ",".join(filter(None, [save_image_b64(f) for f in files]))

def send_line_message(wo, sn, model, failure, status_type="New Request", operator="Unknown"):
    try:
        line_token = st.secrets["line_channel_access_token"]
        line_to = st.secrets["line_group_id"]
        url = "https://api.line.me/v2/bot/message/push"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {line_token}"}

        if status_type == "New Request":
            header_text = "📢 แจ้งซ่อมใหม่"
        elif status_type == "Completed":
            header_text = "✅ ซ่อมเสร็จสิ้น"
        elif status_type == "Re-notify":
            header_text = "🔔 ติดตามงาน (Urgent!)"
        else:
            header_text = f"📦 อัปเดตสถานะ: {status_type}"

        message_text = (
            f"{header_text}\n"
            f"---------------------------\n"
            f"🔢 WO: {wo}\n"
            f"🆔 SN: {sn}\n"
            f"📦 Model: {model}\n"
            f"⚠️ อาการ: {failure}\n"
            f"👤 ผู้แจ้ง: {operator}\n"
            f"---------------------------\n"
            f"⏰ เวลา: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

        payload = {"to": line_to, "messages": [{"type": "text", "text": message_text}]}
        requests.post(url, headers=headers, data=json.dumps(payload))
        return True
    except:
        return False

# --- 3. LOGIN PAGE (BEFORE LOGGED IN) ---
if not st.session_state.logged_in:
    tab1, tab2 = st.tabs(["🔍 ติดตามสถานะงาน (Public)", "🔐 เข้าสู่ระบบ (Staff Only)"])

    # --- หน้าติดตามสถานะงาน (Public) - ปรับปรุงใหม่ ---
    with tab1:
        st.title("🔎 PCBA Repair Tracking")
        c_search1, c_search2 = st.columns(2)
        with c_search1:
            pub_search = st.text_input("🔢 ระบุเลข SN หรือ WO", key="pub_search").strip().upper()
        with c_search2:
            model_search = st.text_input("📦 ระบุ Model", key="model_search").strip().upper()
        
        if pub_search or model_search:
            df_pub = get_df("sheet1")
            if not df_pub.empty:
                query = pd.Series([True] * len(df_pub))
                if pub_search:
                    query &= (df_pub['sn'].astype(str).str.contains(pub_search) | 
                              df_pub['wo'].astype(str).str.contains(pub_search))
                if model_search:
                    query &= (df_pub['model'].astype(str).str.contains(model_search))

                result = df_pub[query].sort_values(by='user_time', ascending=False)
                
                if not result.empty:
                    st.write(f"พบข้อมูลทั้งหมด {len(result)} รายการ")
                    for _, r in result.iterrows():
                        status = r.get('status', 'Pending')
                        
                        # --- กำหนดรายละเอียดสถานะให้ชัดเจน ---
                        if status == "Pending":
                            status_label = "🟠 **รอช่างตรวจสอบ (Pending)**"
                            waiting_info = "⏳ ขั้นตอน: งานรอช่างเข้าคิวตรวจสอบ"
                            card_bg, border_c = "#FFF9F0", "#FFA500"
                        elif status == "Completed":
                            status_label = "✅ **ซ่อมเสร็จสิ้น (Completed)**"
                            waiting_info = "📦 ขั้นตอน: ซ่อมเสร็จแล้ว พร้อมส่งมอบ"
                            card_bg, border_c = "#F0FFF4", "#28A745"
                        else:
                            status_label = f"🔍 **{status}**"
                            waiting_info = ""
                            card_bg, border_c = "#F8F9FA", "#6C757D"

                        with st.container(border=True):
                            # ส่วนการแสดงผลหลัก (Public View)
                            st.markdown(f"""
                                <div style="background-color:{card_bg}; border-left: 5px solid {border_c}; padding: 12px; border-radius: 5px;">
                                    <h4 style="margin:0; color:#1a1a1a;">🔢 SN: {r['sn']}</h4>
                                    <p style="margin:4px 0; font-size:0.9rem; color:#444;">📦 Model: {r['model']} | WO: {r.get('wo','-')}</p>
                                    <div style="font-weight:bold; color:#d35400; font-size:0.85rem;">{waiting_info}</div>
                                </div>
                            """, unsafe_allow_html=True)
                            
                            col_p1, col_p2 = st.columns(2)
                            with col_p1:
                                st.write(f"📍 **สถานะ:** {status_label}")
                                st.write(f"🕒 **เวลาแจ้งซ่อม:** {r['user_time']}")
                            
                            with col_p2:
                                if status == "Completed":
                                    # สำหรับบุคคลทั่วไป แสดงเวลาที่เสร็จเพื่อให้ทราบความคืบหน้า
                                    st.write(f"👷 **ช่างผู้ดูแล:** {r.get('tech_id', '-')}")
                                    st.write(f"🏁 **วันที่ซ่อมเสร็จ:** {r.get('tech_time', '-')}")
                                elif status == "Pending":
                                    st.info("ℹ️ พนักงานผู้แจ้งสามารถกด 'ตามงาน' ได้ในหน้าล็อคอิน")

                            # แสดงรายละเอียดวิธีซ่อมสั้นๆ ให้ทราบ (Public)
                            if status == "Completed":
                                with st.expander("📝 สรุปการแก้ไข"):
                                    st.write(f"**วิธีแก้:** {r.get('action', '-')}")
                else:
                    st.warning("❌ ไม่พบข้อมูล")
    with tab2:
        st.subheader("พนักงาน/ช่างซ่อม เข้าสู่ระบบ")
        with st.form("login_form"):
            u = st.text_input("Username").strip()
            p = st.text_input("Password", type="password").strip()
            if st.form_submit_button("Login"):
                df_u = get_df("users")
                if not df_u.empty:
                    match = df_u[(df_u['username'].astype(str) == u) & (df_u['password'].astype(str) == p)]
                    if not match.empty:
                        st.session_state.update({
                            "logged_in": True, "user": u, 
                            "role": match.iloc[0]['role'],
                            "station": match.iloc[0].get('station', 'General')
                        })
                        st.rerun()
                    else:
                        st.error("❌ ข้อมูลไม่ถูกต้อง")
    st.stop()

# --- 4. SIDEBAR (AFTER LOGGED IN) ---
with st.sidebar:
    st.markdown(f"""
        <div style="padding:15px; background:linear-gradient(135deg, #004a99 0%, #002d5f 100%); border-radius:10px; color:white;">
            <small>User:</small><h3 style="margin:0;">👤 {st.session_state.user}</h3>
            <span style="background:#f39c12; color:black; padding:2px 8px; border-radius:5px; font-size:0.8rem; font-weight:bold;">{st.session_state.role.upper()}</span>
        </div>
    """, unsafe_allow_html=True)
    if st.button("🚪 Sign Out"):
        st.session_state.logged_in = False
        st.rerun()
    st.divider()
    st.write("● System Online" if status_conn else "● Offline")

# --- 4. MAIN LOGIC ---
role = st.session_state.role.lower()



# ---------------- [SECTION: ADMIN] ----------------
if role == "admin":
    tabs = st.tabs(["📊 Dashboard", "👥 Master Data", "🔻 Dropdowns", "🔍 Repair View", "📸 QA Gallery"])
    df_main = get_df("sheet1")

    with tabs[0]:  # 📊 DASHBOARD (UPGRADED 2026)
        st.subheader("📊 PCBA Performance Analysis")
        
        # --- 1. ประกาศค่าเริ่มต้น (ป้องกัน NameError) ---
        avg_lt = 0.0
        df_filtered = pd.DataFrame() # สร้าง DF เปล่าไว้ก่อน
        
        if not df_main.empty:
            # เตรียมข้อมูลเวลา
            df_main['user_time'] = pd.to_datetime(df_main['user_time'], errors='coerce')
            df_main['tech_time'] = pd.to_datetime(df_main['tech_time'], errors='coerce')
            
            # --- 2. ตัวกรองข้อมูล (Filters) ---
            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 2, 1])
                start_d = c1.date_input("📅 วันที่เริ่มต้น", datetime.now().replace(day=1))
                end_d = c2.date_input("📅 วันที่สิ้นสุด", datetime.now())
                
                mask = (df_main['user_time'].dt.date >= start_d) & (df_main['user_time'].dt.date <= end_d)
                df_filtered = df_main.loc[mask].copy()
                
                # ปุ่ม Export Excel
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    df_filtered.to_excel(writer, index=False, sheet_name='Report')
                c3.write("")
                c3.download_button("📥 Export Excel", buffer.getvalue(), f"PCBA_Report_{start_d}.xlsx", use_container_width=True)

            # --- 3. คำนวณ Lead Time เฉพาะงานที่เสร็จ ---
            df_lead = df_filtered[df_filtered['status'] == 'Completed'].copy()
            if not df_lead.empty:
                # คำนวณส่วนต่างเป็นชั่วโมง
                df_lead['duration'] = (df_lead['tech_time'] - df_lead['user_time']).dt.total_seconds() / 3600
                avg_lt = df_lead['duration'].mean()

            # --- 4. บัตรตัวเลขหลัก (KPI Cards) พร้อมปรับสีตัวหนังสือให้ชัด ---
            total = len(df_filtered)
            comp = len(df_lead)
            pend = len(df_filtered[df_filtered['status'] == 'Pending'])
            success_rate = (comp / total * 100) if total > 0 else 0

            # บังคับสีตัวหนังสือด้วย CSS (แก้ปัญหามองไม่เห็นใน Dark/Light mode)
            st.markdown("""
                <style>
                [data-testid="stMetricValue"] { color: #004a99 !important; font-weight: bold; }
                [data-testid="stMetricLabel"] { color: #333333 !important; font-size: 1.1rem; }
                div[data-testid="metric-container"] {
                    background-color: #ffffff; 
                    border: 1px solid #d1d5db;
                    padding: 15px;
                    border-radius: 10px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                }
                </style>
            """, unsafe_allow_html=True)

            k1, k2, k3, k4 = st.columns(4)
            with k1: st.metric("Total Jobs", f"{total} แผง")
            with k2: st.metric("Completed", f"{comp} แผง", delta=f"{success_rate:.1f}% Rate")
            with k3: st.metric("Pending", f"{pend} แผง", delta=f"{pend} งานค้าง", delta_color="inverse")
            with k4: st.metric("Avg. Lead Time", f"{avg_lt:.1f} Hrs")

            st.divider()

            # --- 5. กราฟวิเคราะห์ (Charts) ---
            col_chart1, col_chart2 = st.columns([1, 1])
            
            with col_chart1:
                st.markdown("#### 🍕 Defect Classification")
                df_cl = df_filtered[df_filtered['classification'] != ""]
                if not df_cl.empty:
                    fig_pie = px.pie(df_cl, names='classification', hole=0.5, 
                                   color_discrete_sequence=px.colors.qualitative.Pastel)
                    st.plotly_chart(fig_pie, use_container_width

    with tabs[1]:  # Master Data
        sub = st.selectbox("จัดการข้อมูล", ["users", "model_mat"], key="master_sub")
        df_edit = get_df(sub)

        if not df_edit.empty:
            if sub == "users":
                # ดึงตัวเลือกจาก Sheet station_dropdowns
                st_list = get_dropdown_options("station_dropdowns")
                st_list = [s for s in st_list if s != "--กรุณาเลือก--"]

                # ตรวจสอบว่าค่าที่มีอยู่ใน df_edit มีอันไหนไม่อยู่ใน st_list ไหม (ป้องกัน Error พิมพ์ไม่ได้)
                current_stations = df_edit['station'].unique().tolist()
                combined_options = list(set(st_list + [str(x) for x in current_stations if x and x != "None"]))

                edited = st.data_editor(
                    df_edit,
                    num_rows="dynamic",
                    use_container_width=True,
                    key="editor_users",
                    column_config={
                        "station": st.column_config.SelectboxColumn(
                            "Station",
                            options=combined_options,  # ใช้ตัวเลือกที่รวมค่าเก่าและค่าใหม่เข้าด้วยกัน
                            width="medium"
                        ),
                        "role": st.column_config.SelectboxColumn(
                            "Role",
                            options=["admin", "user", "technician"]
                        )
                    }
                )
            else:
                # สำหรับตารางอื่นๆ ให้พิมพ์ได้อิสระ
                edited = st.data_editor(df_edit, num_rows="dynamic", use_container_width=True, key="editor_other")

            if st.button(f"💾 Save {sub}", key="save_master"):
                ws = ss.worksheet(sub)
                ws.clear()
                # เติมค่าว่างแทนที่ None ก่อนบันทึก
                df_to_save = edited.fillna("")
                ws.update([df_to_save.columns.values.tolist()] + df_to_save.values.tolist())
                st.success("บันทึกข้อมูลเรียบร้อยแล้ว!")
                st.rerun()

    with tabs[2]:  # Dropdowns
        drop = st.selectbox("เลือก Dropdown",
                            ["station_dropdowns", "defect_dropdowns", "action_dropdowns", "classification_dropdowns"])
        df_drop = get_df(drop)
        edited_drop = st.data_editor(df_drop, num_rows="dynamic")
        if st.button(f"💾 Update {drop}"):
            ws = ss.worksheet(drop);
            ws.clear();
            ws.update([edited_drop.columns.values.tolist()] + edited_drop.values.tolist());
            st.success("Updated!")

    with tabs[3]:
        st.dataframe(df_main, use_container_width=True)

    with tabs[4]:  # QA Gallery
        st.subheader("📸 QA Inspection")
        search_sn = st.text_input("🔍 Search SN", key="admin_search").upper()
        gal_data = df_main[df_main['sn'] == search_sn] if search_sn else df_main.tail(10).iloc[::-1]
        for _, r in gal_data.iterrows():
            with st.expander(f"📦 SN: {r['sn']} | Status: {r.get('status', '-')}"):
                c_inf1, c_inf2 = st.columns(2)
                c_inf1.write(f"**Model:** {r['model']} | **Station:** {r['station']}")
                c_inf2.write(f"**Real Case:** {r.get('real_case', '-')}")
                st.divider()
                col_i1, col_i2 = st.columns(2)
                if r.get('img_user'): col_i1.image(f"data:image/jpeg;base64,{r['img_user']}", caption="Before (User)")
                if r.get('img_tech'):
                    t_imgs = str(r['img_tech']).split(",")
                    col_i2.image(f"data:image/jpeg;base64,{t_imgs[0]}", caption="After (Tech)")

# ---------------- [SECTION: TECHNICIAN] ----------------
elif role == "technician":
    st.title("🔧 Technician Repair Record")
    target_sn = st.text_input("🔍 Scan Serial Number (SN)").upper()

    if target_sn:
        df_main = get_df("sheet1")
        if not df_main.empty:
            jobs = df_main[df_main['sn'].astype(str) == target_sn].copy()
            if not jobs.empty:
                options = [(i, f"รายการที่ {i+1} | {r['status']} | {r['model']}") for i, r in jobs.iterrows()]
                sel = st.radio("เลือกรายการที่ต้องการอัปเดต:", options, format_func=lambda x: x[1])
                idx_original, job = sel[0], jobs.loc[sel[0]]
                sel_row = idx_original + 2  # แปลง Index เป็นลำดับแถวใน Google Sheets (Header + 1-based)

                p_name = str(job.get('product', '')).strip()
                if p_name in ["", "-", "None", "nan"]:
                    df_models = get_df("model_mat")
                    match = df_models[df_models['model'].astype(str) == str(job['model'])]
                    p_name = match.iloc[0]['product_name'] if not match.empty else "-"

                with st.container(border=True):
                    c_u1, c_u2 = st.columns([2, 1])
                    with c_u1:
                        st.write(f"**🔢 SN:** {job['sn']} | **📦 Model:** {job['model']} | **🔢 WO:** {job.get('wo', '-')}")
                        st.success(f"**🏷️ Product Name:** {p_name}")
                        st.error(f"⚠️ **Symptom:** {job.get('failure', 'N/A')}")
                    if job.get('img_user'): 
                        c_u2.image(f"data:image/jpeg;base64,{job['img_user']}", caption="Before")

                with st.form("repair_form"):
                    rc = st.text_input("Real Case", value=job.get('real_case', ''))
                    dt = st.selectbox("Defect Type", get_dropdown_options("defect_dropdowns"))
                    ac = st.selectbox("Action Taken", get_dropdown_options("action_dropdowns"))
                    cl = st.selectbox("Classification", get_dropdown_options("classification_dropdowns"))
                    stt = st.radio("Result", ["Completed", "Scrapped"], horizontal=True)
                    imgs = st.file_uploader("Upload Repair Photos", accept_multiple_files=True)

                    if st.form_submit_button("💾 Save Update"):
                        ws = ss.worksheet("sheet1")
                        ws.update(f'E{sel_row}', [[p_name]])
                        ws.update(f'H{sel_row}', [[stt]])
                        ws.update(f'J{sel_row}:N{sel_row}', [[rc, dt, ac, cl, "-"]])
                        ws.update(f'O{sel_row}', [[st.session_state.user]])
                        ws.update(f'P{sel_row}', [[datetime.now().strftime("%Y-%m-%d %H:%M")]])
                        
                        if imgs: 
                            ws.update(f'R{sel_row}', [[save_multiple_images_b64(imgs)]])

                        # --- แก้ไขจุดนี้: ส่งค่า wo เพิ่มเข้าไปเป็นตัวแรก ---
                        send_line_message(
                            job.get('wo', '-'), 
                            job['sn'], 
                            job['model'], 
                            f"ผลการซ่อม: {stt} (สาเหตุ: {rc})", 
                            status_type="Completed", 
                            operator=st.session_state.user
                        )
                        
                        st.success(f"✅ อัปเดตงานซ่อม SN: {job['sn']} เรียบร้อย!")
                        st.rerun()
            else:
                st.warning("ไม่พบข้อมูล SN นี้ในระบบ")


elif role == "user":
    # 1. จัดการ URL Query Parameters เพื่อแยกหน้า
    query_params = st.query_params
    page_now = query_params.get("page", "request")  # ค่าเริ่มต้นคือหน้าแจ้งซ่อม

    # ตั้งค่า Index ของ Radio ตาม URL
    default_index = 0 if page_now == "request" else 1

    menu = st.sidebar.radio(
        "📍 เมนูการใช้งาน",
        ["🚀 แจ้งซ่อมใหม่", "🔍 ติดตามสถานะงาน"],
        index=default_index
    )

    # --- ฟีเจอร์ที่ 1: หน้าแจ้งซ่อมใหม่ (/?page=request) ---
    if menu == "🚀 แจ้งซ่อมใหม่":
        st.title("📱 PCBA Repair Request")
        u_station = st.session_state.get('station', '-')

        with st.form("request_form"):
            col1, col2 = st.columns(2)
            with col1:
                wo = st.text_input("Work Order (WO)", placeholder="เลข WO...").strip().upper()
            with col2:
                sn = st.text_input("Serial Number (SN)", placeholder="สแกน SN...").upper()
            
            model = st.selectbox("Model", get_dropdown_options("model_mat"))
            st.info(f"📍 **แจ้งจากสถานี:** {u_station}")
            
            failure = st.text_area("Symptom / Failure Description (อาการเสีย)")
            u_file = st.file_uploader("Attach Photo (รูปอาการเสีย)")

            if st.form_submit_button("🚀 ส่งข้อมูลแจ้งซ่อม"):
                if model == "--กรุณาเลือก--" or not sn or not wo:
                    st.error("❌ กรุณาระบุ WO, SN และ Model ให้ครบถ้วน")
                else:
                    with st.spinner("กำลังบันทึก..."):
                        df_models = get_df("model_mat")
                        match = df_models[df_models['model'].astype(str) == str(model)]
                        p_name = match.iloc[0]['product_name'] if not match.empty else "-"
                        img_b64 = save_image_b64(u_file)

                        new_data = [
                            st.session_state.user, wo, sn, model, p_name, u_station, failure, 
                            "Pending", datetime.now().strftime("%Y-%m-%d %H:%M"), 
                            "", "", "", "", "", "", "", img_b64, ""
                        ]
                        
                        ss.worksheet("sheet1").append_row(new_data)
                        # ส่ง LINE หัวข้อ "แจ้งซ่อมใหม่"
                        send_line_message(wo, sn, model, failure, status_type="New Request", operator=st.session_state.user)
                        st.success(f"✅ บันทึก WO: {wo} สำเร็จ!")
                        st.balloons()

    # --- ฟีเจอร์ที่ 2: หน้าติดตามสถานะและตามงาน (ปรับปรุงใหม่) ---
    elif menu == "🔍 ติดตามสถานะงาน":
        st.title("🔎 Follow Up Status")
        search_input = st.text_input("🔍 ค้นหาด่วน (SN/WO)", placeholder="พิมพ์เลขที่ต้องการค้นหา...").strip().upper()

        df_main = get_df("sheet1")
        if not df_main.empty:
            if search_input:
                filtered_df = df_main[df_main['sn'].astype(str).str.contains(search_input) | 
                                    df_main['wo'].astype(str).str.contains(search_input)]
            else:
                filtered_df = df_main[df_main['user_id'].astype(str) == str(st.session_state.user)].tail(15)

            for idx, r in filtered_df.iloc[::-1].iterrows():
                status = r.get('status', 'Pending')
                row_index = idx + 2
                
                # --- [เพิ่ม] กำหนดคำอธิบายสถานะให้ชัดเจนว่า "รออะไร" ---
                if status == "Pending":
                    status_desc = "🟠 **รอช่างตรวจสอบ (Pending)**"
                    waiting_for = "⏳ กำลังรอ: ช่างสแกนรับงานเข้าคิวซ่อม"
                    card_color = "#FFF9F0"
                    border_color = "#FFA500"
                elif status == "Completed":
                    status_desc = "✅ **ซ่อมเสร็จสิ้น (Completed)**"
                    waiting_for = "📦 สถานะ: งานพร้อมส่งกลับ/เข้าขั้นตอนถัดไป"
                    card_color = "#F0FFF4"
                    border_color = "#28A745"
                elif status == "Scrapped":
                    status_desc = "❌ **คัดทิ้ง (Scrapped)**"
                    waiting_for = "⚠️ สถานะ: ซ่อมไม่ได้/รอทำเรื่องตัดทิ้ง"
                    card_color = "#FFF5F5"
                    border_color = "#DC3545"
                else:
                    status_desc = f"🔍 **{status}**"
                    waiting_for = ""
                    card_color = "#F8F9FA"
                    border_color = "#6C757D"

                with st.container(border=True):
                    # ส่วนหัว Card
                    st.markdown(f"""
                        <div style="background-color:{card_color}; border-left: 5px solid {border_color}; padding: 12px; border-radius: 5px;">
                            <h4 style="margin:0; color:#1a1a1a;">🔢 SN: {r['sn']}</h4>
                            <p style="margin:4px 0; font-size:0.9rem; color:#444;">📦 Model: {r['model']} | WO: {r.get('wo','-')}</p>
                            <div style="font-weight:bold; color:#d35400; font-size:0.85rem;">{waiting_for}</div>
                        </div>
                    """, unsafe_allow_html=True)

                    c1, c2 = st.columns([2, 1])
                    with c1:
                        st.write(f"📍 **สถานะปัจจุบัน:** {status_desc}")
                        st.write(f"⏱️ **เวลาที่แจ้ง:** {r['user_time']}")
                        
                        # --- [เพิ่ม] แสดงข้อมูลช่างถ้าซ่อมเสร็จแล้ว ---
                        if status != "Pending" and r.get('tech_id'):
                            st.write(f"👷 **ช่างผู้ดูแล:** {r['tech_id']}")
                            st.write(f"🏁 **เสร็จเมื่อ:** {r.get('tech_time', '-')}")
                    
                    with c2:
                        if status == "Pending":
                            # ระบบ Cooldown
                            now = datetime.now()
                            last_notify_str = str(r.get('last_notify', ''))
                            can_notify = True
                            if last_notify_str and last_notify_str not in ["", "None", "nan"]:
                                try:
                                    last_notify_dt = datetime.strptime(last_notify_str, "%Y-%m-%d %H:%M")
                                    if (now - last_notify_dt).total_seconds() < 600:
                                        can_notify = False
                                except: pass

                            if can_notify:
                                if st.button("🔔 ตามงานด่วน", key=f"btn_{idx}", type="primary", use_container_width=True):
                                    success = send_line_message(
                                        r.get('wo','-'), r['sn'], r['model'], 
                                        "❗ รบกวนตรวจสอบ งานยังไม่ได้รับการแก้ไข", 
                                        status_type="Re-notify", 
                                        operator=st.session_state.user
                                    )
                                    if success:
                                        ss.worksheet("sheet1").update_cell(row_index, 19, now.strftime("%Y-%m-%d %H:%M"))
                                        st.toast("ส่งแจ้งเตือนเข้า LINE กลุ่มช่างแล้ว!", icon="🔔")
                                        st.rerun()
                            else:
                                st.button("⏳ เพิ่งตามไป (รอ 10น.)", key=f"wait_{idx}", disabled=True, use_container_width=True)

                    if status != "Pending":
                        with st.expander("📝 ดูสรุปผลการซ่อม"):
                            st.info(f"🛠 **วิธีแก้ไข:** {r.get('action', '-')}")
                            st.warning(f"🔍 **สาเหตุที่พบ:** {r.get('real_case', '-')}")
                            if r.get('img_tech'):
                                st.image(f"data:image/jpeg;base64,{r['img_tech'].split(',')[0]}", caption="รูปหลักฐานจากช่าง", width=300)
