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
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {line_token}"
        }

        header_text = "📢 แจ้งซ่อมใหม่" if status_type == "New Request" else "✅ ซ่อมเสร็จสิ้น"

        message_text = (
            f"{header_text}\n"
            f"---------------------------\n"
            f"🔢 WO: {wo}\n"  # เพิ่มบรรทัดนี้
            f"🆔 SN: {sn}\n"
            f"📦 Model: {model}\n"
            f"⚠️ อาการ: {failure}\n"
            f"👤 ผู้แจ้ง: {operator}\n"
            f"---------------------------\n"
            f"⏰ เวลา: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

        payload = {
            "to": line_to,
            "messages": [{"type": "text", "text": message_text}]
        }

        response = requests.post(url, headers=headers, data=json.dumps(payload))
        return response.status_code == 200
    except Exception as e:
        print(f"LINE Error: {e}")
        return False


# --- 3. SIDEBAR & LOGOUT ---
with st.sidebar:
    if st.session_state.logged_in:
        st.markdown(f"""<div class="user-profile"><h3>👤 {st.session_state.user}</h3><p>{st.session_state.role.upper()}</p></div>""", unsafe_allow_html=True)
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()
    st.divider()
    st.caption("🟢 System Online" if status_conn else "🔴 System Offline")

# --- 4. LOGIN SYSTEM ---
if not st.session_state.logged_in:
    st.title("🔐 PCBA LOGIN")
    with st.form("login"):
        u = st.text_input("Username").strip()
        p = st.text_input("Password", type="password").strip()
        if st.form_submit_button("Login"):
            df_u = get_df("users")
            match = df_u[(df_u['username'].astype(str) == u) & (df_u['password'].astype(str) == p)]
            if not match.empty:
                st.session_state.update({"logged_in": True, "user": u, "role": match.iloc[0]['role']})
                st.rerun()
            else: st.error("Invalid credentials")
    st.stop()


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
    query_params = st.query_params
    default_index = 1 if query_params.get("page") == "track" else 0

    menu = st.sidebar.radio(
        "📍 เมนูการใช้งาน",
        ["🚀 แจ้งซ่อมใหม่", "🔍 ติดตามสถานะงาน"],
        index=default_index
    )

    # --- ฟีเจอร์ที่ 1: แจ้งซ่อมใหม่ (User) ---
    if menu == "🚀 แจ้งซ่อมใหม่":
        st.title("📱 PCBA Repair Request")
        
        with st.form("request_form"):
            wo = st.text_input("Work Order (WO)", placeholder="ระบุเลข WO...").strip().upper()
            sn = st.text_input("Serial Number (SN)", placeholder="พิมพ์หรือสแกน SN ที่นี่...").upper()
            model = st.selectbox("Model", get_dropdown_options("model_mat"))
            station = st.selectbox("Station", get_dropdown_options("station_dropdowns"))
            failure = st.text_area("Symptom / Failure Description")
            u_file = st.file_uploader("Attach Photo (รูปอาการเสีย)")

            if st.form_submit_button("🚀 Submit Request"):
                if model == "--กรุณาเลือก--" or not sn or not wo:
                    st.error("❌ กรุณาระบุ WO, SN และ Model")
                else:
                    with st.spinner("กำลังบันทึกข้อมูล..."):
                        # ดึง Product Name จาก model_mat
                        df_models = get_df("model_mat")
                        match = df_models[df_models['model'].astype(str) == str(model)]
                        p_name = match.iloc[0]['product_name'] if not match.empty else "-"

                        img_b64 = save_image_b64(u_file)

                        # บันทึกข้อมูลตามลำดับคอลัมน์ A-R
                        new_data = [
                            st.session_state.user,  # A: user_id
                            wo,                     # B: wo
                            sn,                     # C: sn
                            model,                  # D: model
                            p_name,                 # E: product
                            station,                # F: station
                            failure,                # G: failure
                            "Pending",              # H: status
                            datetime.now().strftime("%Y-%m-%d %H:%M"), # I: user_time
                            "", "", "", "", "",     # J-N: repair info
                            "",                     # O: tech_id
                            "",                     # P: tech_time
                            img_b64,                # Q: img_user
                            ""                      # R: img_tech
                        ]
                        
                        ss.worksheet("sheet1").append_row(new_data)
                        
                        # แจ้งเตือน LINE (ส่ง WO เข้าไปด้วย)
                        send_line_message(wo, sn, model, failure, status_type="New Request", operator=st.session_state.user)
                        
                        st.success(f"✅ แจ้งซ่อม WO: {wo} สำเร็จ! (Product: {p_name})")
                        st.balloons()

    # --- ฟีเจอร์ที่ 2: ติดตามสถานะ (ย่อหน้าให้ตรงกับ if menu ด้านบน) ---
    elif menu == "🔍 ติดตามสถานะงาน":
        st.title("🔎 Follow Up Status")

        search_input = st.text_input("🔍 ค้นหาด้วย SN หรือชื่อ Model",
                                     placeholder="พิมพ์หรือสแกนที่นี่...").strip().upper()

        if search_input:
            with st.spinner("กำลังค้นหาข้อมูล..."):
                df_main = get_df("sheet1")
                if not df_main.empty:
                    # แก้ไขชื่อคอลัมน์ 'id' เป็น 'user_id' ให้ตรงกับตอนบันทึก
                    filtered_df = df_main[
                        df_main['sn'].astype(str).str.contains(search_input) |
                        df_main['model'].astype(str).str.contains(search_input)
                    ].sort_values(by='user_time', ascending=False)

                    if not filtered_df.empty:
                        st.success(f"🔎 พบรายการที่เกี่ยวข้อง {len(filtered_df)} รายการ")
                        for _, r in filtered_df.iterrows():
                            status = r['status']
                            status_color = "#FFA500" if status == "Pending" else "#28A745" if status == "Completed" else "#DC3545"

                            with st.container(border=True):
                                c1, c2 = st.columns([3, 1])
                                with c1:
                                    st.subheader(f"🔢 SN: {r['sn']}")
                                    st.write(f"📦 **Model:** {r['model']} | **WO:** {r.get('wo', '-')}")
                                    st.caption(f"📅 วันที่แจ้ง: {r['user_time']}")
                                with c2:
                                    st.markdown(f"""
                                        <div style='background-color:{status_color}; padding:10px; border-radius:10px; text-align:center;'>
                                            <span style='color:white; font-weight:bold;'>{status}</span>
                                        </div>
                                    """, unsafe_allow_html=True)

                                if status != "Pending":
                                    with st.expander("📝 รายละเอียดการวิเคราะห์และแก้ไข"):
                                        st.markdown(f"**🔍 สาเหตุที่พบ:** {r.get('real_case', '-')}")
                                        st.markdown(f"**🛠 วิธีการแก้ไข:** {r.get('action_taken', '-')}")
                                        st.caption(f"✅ ดำเนินการโดย: {r.get('tech_id', '-')} เมื่อ {r.get('tech_time', '-')}")
                    else:
                        st.warning(f"⚠️ ไม่พบข้อมูลสำหรับ: '{search_input}'")

        # ประวัติ 5 รายการล่าสุด (ย่อหน้าให้ตรงกับ if search_input)
        st.divider()
        st.subheader("🕒 ประวัติของคุณ (5 รายการล่าสุด)")
        df_all = get_df("sheet1")
        if not df_all.empty:
            # เปลี่ยน 'id' เป็น 'user_id' ให้ตรงกับหัวตาราง
            user_jobs = df_all[df_all['user_id'].astype(str) == st.session_state.user].tail(5).iloc[::-1]
            for _, r in user_jobs.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([2, 2, 1])
                    c1.write(f"**SN:** {r['sn']}\n\n**WO:** {r.get('wo', '-')}")
                    c2.write(f"**วันที่:** {r['user_time']}\n\n**Model:** {r['model']}")
                    stt = r['status']
                    color = "#FFD700" if stt == "Pending" else "#28A745" if stt == "Completed" else "#DC3545"
                    c3.markdown(f"<div style='background:{color};color:white;padding:10px;border-radius:8px;text-align:center;'>{stt}</div>", unsafe_allow_html=True)
