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

        # --- ส่วนที่ปรับปรุง: เลือกหัวข้อตาม Status Type ---
        if status_type == "New Request":
            header_text = "📢 แจ้งซ่อมใหม่"
        elif status_type == "Completed":
            header_text = "✅ ซ่อมเสร็จสิ้น"
        elif status_type == "Re-notify":
            header_text = "🔔 ติดตามงาน (Urgent!)" # เปลี่ยนหัวข้อสำหรับปุ่มตามงาน
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
    except Exception as e:
        return False


# --- 3. SIDEBAR & LOGOUT (ปรับปรุงใหม่) ---
with st.sidebar:
    # เพิ่ม CSS เฉพาะใน Sidebar เพื่อให้ข้อความและปุ่มดูชัดเจนขึ้น
    st.markdown("""
        <style>
        [data-testid="stSidebar"] {
            background-color: #1a1c23;
            color: white;
        }
        .user-info {
            padding: 15px;
            background: linear-gradient(135deg, #004a99 0%, #002d5f 100%);
            border-radius: 10px;
            margin-bottom: 20px;
            border: 1px solid #34495e;
        }
        </style>
    """, unsafe_allow_html=True)

    if st.session_state.logged_in:
        # แสดงข้อมูลผู้ใช้ในรูปแบบการ์ดที่สวยงาม
        st.markdown(f"""
            <div class="user-info">
                <small style="color: #bdc3c7;">Logged in as:</small>
                <h3 style="margin:0; color: white;">👤 {st.session_state.user}</h3>
                <span style="background: #f39c12; color: black; padding: 2px 8px; border-radius: 5px; font-size: 0.8rem; font-weight: bold;">
                    {st.session_state.role.upper()}
                </span>
            </div>
        """, unsafe_allow_html=True)
        
        # ปุ่ม Logout แบบเด่นชัด
        if st.button("🚪 Sign Out / ออกจากระบบ", use_container_width=True, type="secondary"):
            st.session_state.logged_in = False
            st.session_state.user = ""
            st.session_state.role = ""
            st.rerun()
            
    st.divider()
    
    # สถานะระบบ (วางไว้ส่วนบนเพื่อให้เห็นชัดว่า Online หรือไม่)
    if status_conn:
        st.success("● System Online")
    else:
        st.error("● System Offline")
    
    st.divider()

if not st.session_state.logged_in:
    tab1, tab2 = st.tabs(["🔍 ติดตามสถานะงาน (Public)", "🔐 เข้าสู่ระบบ (Staff Only)"])

    with tab1:
        st.title("🔎 PCBA Repair Tracking")
        st.subheader("เช็คสถานะงานซ่อมของคุณ")
        
        c_search1, c_search2 = st.columns(2)
        with c_search1:
            pub_search = st.text_input("🔢 ระบุเลข SN หรือ WO", key="pub_search").strip().upper()
        with c_search2:
            model_search = st.text_input("📦 ระบุ Model", key="model_search").strip().upper()
        
        if pub_search or model_search:
            with st.spinner("กำลังค้นหาข้อมูล..."):
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
                        st.markdown(f"<p style='color:black;'>🔍 พบข้อมูลทั้งหมด {len(result)} รายการ</p>", unsafe_allow_html=True)
                        for _, r in result.iterrows():
                            status = r.get('status', 'Pending')
                            card_bg = "#FFF9F0" if status == "Pending" else "#F0FFF4"
                            border_c = "#FFA500" if status == "Pending" else "#28A745"
                            
                            with st.container(border=True):
                                # บังคับตัวหนังสือสีดำในส่วน Card Header
                                st.markdown(f"""
                                    <div style="background-color:{card_bg}; border-left: 5px solid {border_c}; padding: 12px; border-radius: 5px;">
                                        <h4 style="margin:0; color: #000000;">🔢 SN: <b>{r['sn']}</b></h4>
                                        <p style="margin:5px 0; color: #000000; font-size: 0.9rem;">📦 <b>Model:</b> {r['model']} | 🔢 <b>WO:</b> {r.get('wo','-')}</p>
                                    </div>
                                """, unsafe_allow_html=True)
                                
                                c1, c2 = st.columns([3, 1])
                                with c1:
                                    st.markdown(f"<p style='color: #000000; margin: 5px 0;'>📅 วันที่แจ้ง: {r['user_time']}</p>", unsafe_allow_html=True)
                                    st.markdown(f"<p style='color: #000000; margin: 0;'>📍 สถานี: {r.get('station','-')}</p>", unsafe_allow_html=True)
                                with c2:
                                    # แถบสถานะแบบสีตัวหนังสือดำ
                                    st.markdown(f"<div style='background: {card_bg}; border: 1px solid {border_c}; color: black; padding: 5px; border-radius: 5px; text-align: center; font-weight: bold;'>{status}</div>", unsafe_allow_html=True)
                                
                                if status != "Pending":
                                    with st.expander("📝 ดูรายละเอียดการซ่อม"):
                                        st.markdown(f"<p style='color:black;'>🛠 <b>วิธีแก้ไข:</b> {r.get('action', '-')}</p>", unsafe_allow_html=True)
                                        st.markdown(f"<p style='color:black;'>🕒 <b>เสร็จเมื่อ:</b> {r.get('tech_time', '-')}</p>", unsafe_allow_html=True)
                    else:
                        st.warning("❌ ไม่พบข้อมูลที่ตรงกับเงื่อนไขที่ระบุ")
                else:
                    st.error("ไม่สามารถเชื่อมต่อฐานข้อมูลได้")
    with tab2:
        # แก้ไขโครงสร้าง Form ตรงนี้ให้ถูกต้อง
        with st.container(border=True):
                    # ปรับแต่งสี Card และตัวหนังสือให้ดำชัดเจน
                    st.markdown(f"""
                        <div style="background-color:{card_color}; border-left: 5px solid {border_color}; padding: 12px; border-radius: 5px;">
                            <h4 style="margin:0; color: #000000;">🔢 SN: <b>{r['sn']}</b></h4>
                            <p style="margin:5px 0; color: #000000;">📦 <b>Model:</b> {r['model']} | <b>WO:</b> {r.get('wo','-')}</p>
                        </div>
                    """, unsafe_allow_html=True)

                    c1, c2 = st.columns([2, 1])
                    with c1:
                        st.markdown(f"<p style='color: #000000; margin: 5px 0;'>📅 {r['user_time']}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p style='color: #000000; margin: 0;'>🚩 สถานะ: <b>{status}</b></p>", unsafe_allow_html=True)
        st.subheader("พนักงาน/ช่างซ่อม เข้าสู่ระบบ")
        
        with st.form("login_form"):
            u = st.text_input("Username").strip()
            p = st.text_input("Password", type="password").strip()
            submit = st.form_submit_button("Login")
            
            if submit:
                df_u = get_df("users")
                if not df_u.empty:
                    match = df_u[(df_u['username'].astype(str) == u) & (df_u['password'].astype(str) == p)]
                    if not match.empty:
                        st.session_state.update({
                            "logged_in": True, 
                            "user": u, 
                            "role": match.iloc[0]['role'],
                            "station": match.iloc[0].get('station', 'General')
                        })
                        st.success("✅ Login สำเร็จ!")
                        st.rerun()
                    else:
                        st.error("❌ Username หรือ Password ไม่ถูกต้อง")
                else:
                    st.error("❌ ไม่สามารถดึงข้อมูลพนักงานได้")
    st.stop() # หยุดการทำงานเพื่อให้แสดงแค่ 2 Tab นี้ก่อน Login


# --- 4. MAIN LOGIC ---
role = st.session_state.role.lower()



# ---------------- [SECTION: ADMIN] ----------------
if role == "admin":
    tabs = st.tabs(["📊 Dashboard", "👥 Master Data", "🔻 Dropdowns", "🔍 Repair View", "📸 QA Gallery"])
    df_main = get_df("sheet1")

    with tabs[0]:  # DASHBOARD
        st.subheader("📊 PCBA Performance Analysis")
        if not df_main.empty:
            df_main['user_time'] = pd.to_datetime(df_main['user_time'], errors='coerce')
            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 2, 1])
                start_d = c1.date_input("วันที่เริ่มต้น", datetime.now().replace(day=1))
                end_d = c2.date_input("วันที่สิ้นสุด", datetime.now())
                mask = (df_main['user_time'].dt.date >= start_d) & (df_main['user_time'].dt.date <= end_d)
                df_filtered = df_main.loc[mask]

                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    df_filtered.to_excel(writer, index=False, sheet_name='Report')
                c3.write("");
                c3.download_button("📥 Export Excel", buffer.getvalue(), f"Report_{start_d}.xlsx")

            m1, m2, m3 = st.columns(3)
            m1.metric("Total Jobs", len(df_filtered))
            m2.metric("Completed", len(df_filtered[df_filtered['status'] == 'Completed']))
            m3.metric("Pending", len(df_filtered[df_filtered['status'] == 'Pending']))

            st.divider()
            col_chart1, col_chart2 = st.columns(2)
            with col_chart1:
                st.markdown("#### 🍕 Classification Summary")
                df_cl = df_filtered[df_filtered['classification'] != ""]
                if not df_cl.empty: st.plotly_chart(px.pie(df_cl, names='classification', hole=0.4),
                                                    use_container_width=True)
            with col_chart2:
                st.markdown("#### 📈 Top Defect Types")
                df_dt = df_filtered[df_filtered['defect_type'] != ""]
                if not df_dt.empty:
                    top_df = df_dt['defect_type'].value_counts().reset_index()
                    st.plotly_chart(px.bar(top_df, x='count', y='defect_type', orientation='h', color='count'),
                                    use_container_width=True)

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

    # --- ฟีเจอร์ที่ 2: หน้าติดตามสถานะและตามงาน (/?page=track) ---
    elif menu == "🔍 ติดตามสถานะงาน":
        st.title("🔎 Follow Up Status")
        search_input = st.text_input("🔍 ค้นหาด่วน (SN/WO)", placeholder="พิมพ์เลขที่ต้องการค้นหา...").strip().upper()

        df_main = get_df("sheet1")
        if not df_main.empty:
            # กรองข้อมูล
            if search_input:
                filtered_df = df_main[df_main['sn'].astype(str).str.contains(search_input) | 
                                    df_main['wo'].astype(str).str.contains(search_input)]
            else:
                # แสดงรายการของตัวเอง 10 รายการล่าสุด
                filtered_df = df_main[df_main['user_id'].astype(str) == str(st.session_state.user)].tail(10)

            for idx, r in filtered_df.iloc[::-1].iterrows():
                status = r.get('status', 'Pending')
                row_index = idx + 2
                
                # แยกสีตามสถานะให้ชัดเจน
                card_color = "#FFF9F0" if status == "Pending" else "#F0FFF4"
                border_color = "#FFA500" if status == "Pending" else "#28A745"

                with st.container(border=True):
                    # ส่วนหัว Card
                    st.markdown(f"""
                        <div style="background-color:{card_color}; border-left: 5px solid {border_color}; padding: 10px; border-radius: 5px;">
                            <h4 style="margin:0;">🔢 SN: {r['sn']}</h4>
                            <small>📦 Model: {r['model']} | WO: {r.get('wo','-')}</small>
                        </div>
                    """, unsafe_allow_html=True)

                    c1, c2 = st.columns([2, 1])
                    with c1:
                        st.write(f"📅 {r['user_time']}")
                        st.write(f"🚩 สถานะ: **{status}**")
                    
                    with c2:
                        if status == "Pending":
                            # ระบบ Cooldown ป้องกันการกดย้ำเกินไป
                            now = datetime.now()
                            last_notify_str = str(r.get('last_notify', ''))
                            can_notify = True
                            if last_notify_str and last_notify_str not in ["", "None", "nan"]:
                                try:
                                    last_notify_dt = datetime.strptime(last_notify_str, "%Y-%m-%d %H:%M")
                                    if (now - last_notify_dt).total_seconds() < 600: # 10 นาที
                                        can_notify = False
                                except: pass

                            if can_notify:
                                if st.button("🔔 ตามงาน", key=f"btn_{idx}", type="primary", use_container_width=True):
                                    # ส่ง LINE หัวข้อ "ตามงาน"
                                    success = send_line_message(
                                        r.get('wo','-'), r['sn'], r['model'], 
                                        "❗ รบกวนตรวจสอบ งานยังไม่ได้รับการแก้ไข", 
                                        status_type="Re-notify", 
                                        operator=st.session_state.user
                                    )
                                    if success:
                                        ss.worksheet("sheet1").update_cell(row_index, 19, now.strftime("%Y-%m-%d %H:%M"))
                                        st.toast("ส่งแจ้งเตือนติดตามงานแล้ว!", icon="🔔")
                                        st.rerun()
                            else:
                                st.button("⏳ รอสักครู่", key=f"wait_{idx}", disabled=True, use_container_width=True)

                    if status != "Pending":
                        with st.expander("📝 รายละเอียดการซ่อม"):
                            st.write(f"🛠 **ผลการซ่อม:** {r.get('action', '-')}")
                            st.write(f"🔍 **สาเหตุ:** {r.get('real_case', '-')}")
