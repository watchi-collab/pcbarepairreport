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
    .stMetric { 
        background-color: #ffffff; padding: 20px; border-radius: 12px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #eee;
    }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
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
        if not df.empty:
            df.columns = df.columns.str.strip()
        return df
    except:
        return pd.DataFrame()


def get_dropdown_options(sheet_name):
    df = get_df(sheet_name)
    options = ["--กรุณาเลือก--"]
    if not df.empty:
        options.extend(df.iloc[:, 0].astype(str).tolist())
    return options


def save_image_b64(file, size=(400, 400), quality=40):
    if not file: return ""
    img = Image.open(file)
    img.thumbnail(size)
    buf = io.BytesIO()
    img.convert('RGB').save(buf, format="JPEG", quality=quality, optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


def save_multiple_images_b64(files):
    if not files: return ""
    b64_list = []
    current_length = 0
    for file in files:
        b64_str = save_image_b64(file, size=(350, 350), quality=35)
        if current_length + len(b64_str) < 48000:  # Google Sheets Cell Limit Guard
            b64_list.append(b64_str)
            current_length += len(b64_str) + 1
        else:
            st.warning("⚠️ บางรูปถูกข้ามเนื่องจากขนาดข้อมูลใกล้เต็มขีดจำกัด")
            break
    return ",".join(b64_list)


def calculate_tat(row):
    try:
        fmt = "%Y-%m-%d %H:%M"
        start = datetime.strptime(str(row['user_time']), fmt)
        end = datetime.strptime(str(row['tech_time']), fmt)
        return round((end - start).total_seconds() / 3600, 2)
    except:
        return None


def send_line_message(sn, model, failure):
    """ฟังก์ชันส่งข้อความแจ้งเตือนผ่าน LINE Messaging API"""
    try:
        # ดึงค่าจาก Secrets
        line_token = st.secrets["line_channel_access_token"]
        line_to = st.secrets["line_group_id"]

        url = "https://api.line.me/v2/bot/message/push"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {line_token}"
        }

        # จัดรูปแบบข้อความ
        message_text = (
            f"📢 **แจ้งซ่อมใหม่ (New Request)**\n"
            f"---------------------------\n"
            f"🔢 SN: {sn}\n"
            f"📦 Model: {model}\n"
            f"⚠️ อาการเสีย: {failure}\n"
            f"---------------------------\n"
            f"⏰ เวลา: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

        payload = {
            "to": line_to,
            "messages": [
                {
                    "type": "text",
                    "text": message_text
                }
            ]
        }

        response = requests.post(url, headers=headers, data=json.dumps(payload))
        return response.status_code == 200
    except Exception as e:
        st.error(f"⚠️ ไม่สามารถส่งแจ้งเตือน LINE ได้: {e}")
        return False


# --- 3. SIDEBAR ---
with st.sidebar:
    if status_conn:
        st.success("● System Online")
    else:
        st.error("○ System Offline")

    if st.session_state.get('logged_in'):
        st.info(f"👤 **User:** {st.session_state.user}\n🔐 **Role:** {st.session_state.role}")
        if st.button("🚪 Logout"):
            st.session_state.logged_in = False
            st.rerun()

# --- 4. LOGIN ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if not st.session_state.logged_in:
    st.title("🔐 Login PCBA PRO 2026")
    with st.form("login_form"):
        u = st.text_input("Username").strip()
        p = st.text_input("Password", type="password").strip()
        if st.form_submit_button("เข้าสู่ระบบ"):
            df_u = get_df("users")
            match = df_u[(df_u['username'] == u) & (df_u['password'].astype(str) == p)]
            if not match.empty:
                st.session_state.update({"logged_in": True, "user": u, "role": match.iloc[0]['role']})
                st.rerun()
            else:
                st.error("Username หรือ Password ไม่ถูกต้อง")
    st.stop()

role = st.session_state.role.lower()

# ---------------- [SECTION: ADMIN] ----------------
if role == "admin":
    tabs = st.tabs(["📊 Dashboard", "👥 Master Data", "🔻 Dropdowns", "🔍 Repair View", "📸 QA Gallery"])
    df_main = get_df("sheet1")
    df_m = get_df("model_mat")

    with tabs[0]:  # Dashboard

            st.subheader("📊 Repair Insight Dashboard")

            if not df_main.empty:
                # กรองเฉพาะรายการที่ซ่อมเสร็จแล้วเพื่อนำมาวิเคราะห์
                df_comp = df_main[df_main['status'].isin(['Completed', 'Scrapped'])].copy()

                # --- ส่วนที่ 1: การแสดง Metrics หลัก ---
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Total Requests", len(df_main))
                m2.metric("Pending Work", len(df_main[df_main['status'] == 'Pending']))
                m3.metric("Completed", len(df_main[df_main['status'] == 'Completed']))
                # คำนวณ % การซ่อมสำเร็จ
                success_rate = (len(df_main[df_main['status'] == 'Completed']) / len(df_main) * 100) if len(
                    df_main) > 0 else 0
                m4.metric("Success Rate", f"{success_rate:.1f}%")

                st.divider()

                # --- ส่วนที่ 2: กราฟ Classification และ Remark ---
                col_left, col_right = st.columns(2)

                with col_left:
                    st.markdown("##### 📌 สัดส่วนการจำแนกปัญหา (Classification)")
                    if not df_comp.empty and 'classification' in df_comp.columns:
                        # สร้างกราฟวงกลมแสดงสัดส่วน Classification
                        fig_class = px.pie(
                            df_comp,
                            names='classification',
                            hole=0.4,
                            color_discrete_sequence=px.colors.qualitative.Safe
                        )
                        fig_class.update_layout(height=400, margin=dict(t=0, b=0, l=0, r=0))
                        st.plotly_chart(fig_class, use_container_width=True)
                    else:
                        st.info("💡 รอข้อมูลการซ่อมเพื่อแสดงกราฟ Classification")

                with col_right:
                    st.markdown("##### 📝 สรุปบันทึกเพิ่มเติม (Top Remarks)")
                    if not df_comp.empty and 'remark' in df_comp.columns:
                        # นับจำนวน Remark ที่เกิดขึ้นบ่อย
                        # กรองค่าว่างออกก่อนนับ
                        df_remark = df_comp[df_comp['remark'].str.strip() != ""]
                        remark_counts = df_remark['remark'].value_counts().reset_index().head(10)
                        remark_counts.columns = ['Remark', 'Count']

                        # สร้างกราฟแท่งแนวนอน
                        fig_remark = px.bar(
                            remark_counts,
                            y='Remark',
                            x='Count',
                            orientation='h',
                            color='Count',
                            color_continuous_scale='Viridis'
                        )
                        fig_remark.update_layout(height=400, margin=dict(t=0, b=0, l=0, r=0))
                        st.plotly_chart(fig_remark, use_container_width=True)
                    else:
                        st.info("💡 รอข้อมูลการซ่อมเพื่อแสดงกราฟ Remark")

                st.divider()

                # --- ส่วนที่ 3: สรุปตาม Defect Type ---
                st.markdown("##### 🔍 ประเภท Defect ที่พบบ่อย (Defect Type Summary)")
                if not df_comp.empty:
                    defect_data = df_comp['defect_type'].value_counts().reset_index()
                    defect_data.columns = ['Defect Type', 'Total']
                    fig_defect = px.bar(defect_data, x='Defect Type', y='Total', color='Defect Type')
                    st.plotly_chart(fig_defect, use_container_width=True)

            else:
                st.warning("⚠️ ไม่พบข้อมูลในระบบ")

    with tabs[1]:  # Master Data
        sub_target = st.selectbox("จัดการข้อมูล", ["users", "model_mat"])
        df_edit = get_df(sub_target)
        edited = st.data_editor(df_edit, num_rows="dynamic", use_container_width=True)
        if st.button(f"💾 Save {sub_target}"):
            ws = ss.worksheet(sub_target)
            ws.clear()
            ws.update([edited.columns.values.tolist()] + edited.values.tolist())
            st.success("บันทึกสำเร็จ!")

    with tabs[2]:  # Dropdowns
        drop_sheet = st.selectbox("เลือกรายการ Dropdown", ["station_dropdowns", "defect_dropdowns", "action_dropdowns",
                                                           "classification_dropdowns"])
        df_drop = get_df(drop_sheet)
        edited_drop = st.data_editor(df_drop, num_rows="dynamic", use_container_width=True)
        if st.button(f"💾 Update {drop_sheet}"):
            ws = ss.worksheet(drop_sheet)
            ws.clear()
            ws.update([edited_drop.columns.values.tolist()] + edited_drop.values.tolist())
            st.success("อัปเดตเรียบร้อย!")

    with tabs[3]:  # Repair View
        if not df_main.empty:
            df_v = df_main.merge(df_m[['model', 'product_name']], on='model', how='left')
            st.dataframe(df_v, use_container_width=True, hide_index=True)

    with tabs[4]:  # QA Gallery
            st.subheader("📸 QA Gallery & Inspection")
            search_sn = st.text_input("🔍 Search SN to Inspect", placeholder="พิมพ์ SN ที่ต้องการตรวจสอบ...").upper()

            # กรองข้อมูลตาม SN หรือแสดง 10 รายการล่าสุด
            gal = df_main[df_main['sn'] == search_sn] if search_sn else df_main.tail(10)

            if gal.empty:
                st.warning("ไม่พบข้อมูลที่ค้นหา")
            else:
                for _, r in gal.iterrows():
                    # แสดงหัวข้อด้วย SN และสถานะ
                    status_color = "🟢" if r['status'] == "Completed" else "🔴" if r['status'] == "Scrapped" else "🟡"
                    with st.expander(f"📦 SN: {r['sn']} | Status: {status_color} {r['status']}"):

                        # --- ส่วนที่ 1: รายละเอียดงานเสีย (Symptom Details) ---
                        st.markdown("#### 📝 รายละเอียดงานเสีย")
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            st.write(f"**Model:** {r.get('model', 'N/A')}")
                            st.write(f"**Station:** {r.get('station', 'N/A')}")
                        with c2:
                            st.write(f"**Reported Time:** {r.get('user_time', 'N/A')}")
                            st.write(f"**Repair Time:** {r.get('tech_time', 'N/A')}")
                        with c3:
                            st.info(f"**Symptom:** {r.get('failure', 'N/A')}")

                        st.divider()

                        st.markdown("#### 🔧 บันทึกการแก้ไขโดย Technician")

                        # เพิ่ม CSS เพื่อบังคับให้ตัวเลขและข้อความใน Metric เป็นสีดำ (หรือสีที่คุณต้องการ)
                        st.markdown("""
                                <style>
                                [data-testid="stMetricValue"] {
                                    color: #000000 !important;
                                }
                                [data-testid="stMetricLabel"] {
                                    color: #333333 !important;
                                }
                                </style>
                                """, unsafe_allow_html=True)

                        ca, cb, cc = st.columns(3)
                        # แสดงข้อมูลการซ่อมที่บันทึกไว้ใน Sheet
                        ca.metric("Real Case", r.get('real_case', '-'))
                        cb.metric("Defect Type", r.get('defect_type', '-'))
                        cc.metric("Action", r.get('action', '-'))

                        if r.get('remark'):
                            st.warning(f"**Remark:** {r['remark']}")

                        st.divider()

                        # --- ส่วนที่ 3: รูปภาพหลักฐาน (Evidence) ---
                        st.markdown("#### 🖼 Evidence Photos")
                        col_u, col_t = st.columns(2)

                        with col_u:
                            st.write("📸 **User (Before)**")
                            if r.get('img_user'):
                                st.image(f"data:image/jpeg;base64,{r['img_user']}", use_container_width=True)
                            else:
                                st.caption("ไม่มีรูปภาพจาก User")

                        with col_t:
                            st.write("🛠 **Technician (After)**")
                            if r.get('img_tech'):
                                # แยกรูปภาพกรณีมีหลายรูป (Comma Separated Base64)
                                tech_imgs = str(r['img_tech']).split(",")
                                for b64_img in tech_imgs:
                                    if b64_img:
                                        st.image(f"data:image/jpeg;base64,{b64_img}", use_container_width=True)
                            else:
                                st.caption("ไม่มีรูปภาพการซ่อม")

# ---------------- [SECTION: TECHNICIAN - MULTI-JOB SUPPORT] ----------------
elif role == "technician":
    st.title("🔧 Technician Repair Record")
    target_sn = st.text_input("🔍 Scan Serial Number (SN)").upper()

    if target_sn:
        df_main = get_df("sheet1")
        # 1. ค้นหาทุกรายการที่มี SN ตรงกัน
        all_jobs = df_main[df_main['sn'] == target_sn].copy()

        if not all_jobs.empty:
            st.subheader(f"📋 รายการทั้งหมดสำหรับ SN: {target_sn}")

            # 2. เตรียมรายการตัวเลือกพร้อมแยกสถานะด้วยสี
            options = []
            for i, r in all_jobs.iterrows():
                # กำหนด Icon ตามสถานะ
                status_icon = "🔴 Pending" if r['status'] == "Pending" else "🟢 Completed"
                # สร้าง Label ที่ระบุ Model และ Station เพื่อการเลือกที่ถูกต้อง
                label = f"แถว {i + 2} | {status_icon} | Model: {r['model']} | Station: {r['station']} | Symptom: {r['failure']}"
                options.append((i + 2, label))

                # 3. ให้ช่างเลือกรายการที่ต้องการดำเนินการ
            selected_item = st.radio(
                "กรุณาเลือกรายการที่ต้องการดำเนินการ:",
                options,
                format_func=lambda x: x[1]
            )

            # ดึงข้อมูลแถวที่เลือกมาใช้งาน
            selected_row = selected_item[0]
            job = all_jobs.loc[selected_row - 2]

            st.divider()
            st.success(f"🛠 กำลังจัดการข้อมูลใน **แถวที่ {selected_row}**")

            # แสดงภาพประกอบจาก User (ถ้ามี)
            if job.get('img_user'):
                st.image(f"data:image/jpeg;base64,{job['img_user']}", width=350, caption="อาการเสียที่แจ้งโดย User")

            # 4. ฟอร์มสำหรับบันทึกผลการซ่อม
            with st.form("repair_result"):
                c1, c2 = st.columns(2)
                with c1:
                    real_case = st.text_input("Real Case / Root Cause", value=job.get('real_case', ''))
                    defect = st.selectbox("Defect Type", get_dropdown_options("defect_dropdowns"))
                with c2:
                    action = st.selectbox("Action Taken", get_dropdown_options("action_dropdowns"))
                    classify = st.selectbox("Classification", get_dropdown_options("classification_dropdowns"))

                remark = st.text_area("Remark / Rework Note", value=job.get('remark', ''))

                # กำหนดค่าเริ่มต้นของสถานะตามข้อมูลเดิม
                res_options = ["Completed", "Scrapped"]
                res_idx = 0 if job.get('status') == "Completed" else 1 if job.get('status') == "Scrapped" else 0
                status = st.radio("Result", res_options, index=res_idx, horizontal=True)

                t_files = st.file_uploader("Upload Repair Photo", type=['jpg', 'png'], accept_multiple_files=True)

                if st.form_submit_button("💾 Save & Update Job"):
                    if "--กรุณาเลือก--" in [defect, action, classify]:
                        st.error("❌ กรุณาเลือกข้อมูล Dropdown ให้ครบถ้วน")
                    else:
                        with st.spinner("กำลังอัปเดตข้อมูลลง Google Sheet..."):
                            # บีบอัดภาพเพื่อป้องกันปัญหาข้อมูลเกิน 50k ตัวอักษร
                            img_tech_combined = save_multiple_images_b64(t_files)

                            ws = ss.worksheet("sheet1")

                            # อัปเดตเฉพาะแถวที่เลือก (Selected Row)
                            ws.update(range_name=f'G{selected_row}', values=[[status]])
                            ws.update(range_name=f'I{selected_row}:M{selected_row}',
                                      values=[[real_case, defect, action, classify, remark]])
                            ws.update(range_name=f'N{selected_row}',
                                      values=[[datetime.now().strftime("%Y-%m-%d %H:%M")]])

                            # บันทึกรูปภาพในคอลัมน์ P
                            if img_tech_combined:
                                ws.update(range_name=f'P{selected_row}', values=[[img_tech_combined]])

                            st.success(f"✅ บันทึกข้อมูลสำเร็จ! แถวที่ {selected_row} ได้รับการอัปเดต")
                            st.balloons()
                            st.rerun()
        else:
            st.warning(f"❌ ไม่พบประวัติการแจ้งซ่อมสำหรับ SN: {target_sn}")

# ---------------- [SECTION: USER] ----------------
# ---------------- [SECTION: USER - WITH SCANNER SUPPORT] ----------------
elif role == "user":
    query_params = st.query_params
    default_index = 1 if query_params.get("page") == "track" else 0

    menu = st.sidebar.radio(
        "📍 เมนูการใช้งาน",
        ["🚀 แจ้งซ่อมใหม่", "🔍 ติดตามสถานะงาน"],
        index=default_index
    )

    # --- ฟีเจอร์ที่ 1: แจ้งซ่อมใหม่ ---
    if menu == "🚀 แจ้งซ่อมใหม่":
        st.title("📱 PCBA Repair Request")

        # เพิ่มปุ่มสแกนผ่านกล้อง (ใช้สำหรับถ่ายรูป Barcode เพื่ออ่านค่า)
        with st.expander("📷 เปิดกล้องสแกน SN (แทนการพิมพ์)"):
            scan_file = st.camera_input("สแกน Barcode/QR Code บนบอร์ด")
            if scan_file:
                st.info("💡 ระบบกำลังประมวลผลรูปภาพ (ในอนาคตเชื่อมต่อ AI OCR ได้)")

        with st.form("request_form"):
            sn = st.text_input("Serial Number (SN)", placeholder="พิมพ์หรือสแกน SN ที่นี่...").upper()
            model = st.selectbox("Model", get_dropdown_options("model_mat"))
            station = st.selectbox("Station", get_dropdown_options("station_dropdowns"))
            failure = st.text_area("Symptom / Failure Description")
            u_file = st.file_uploader("Attach Photo (รูปอาการเสีย)")

            if st.form_submit_button("🚀 Submit Request"):
                if model == "--กรุณาเลือก--" or not sn:
                    st.error("❌ กรุณาระบุ SN และ Model")
                else:
                    with st.spinner("กำลังบันทึกข้อมูล..."):
                        img_b64 = save_image_b64(u_file)
                        ss.worksheet("sheet1").append_row(
                            ["", sn, model, "", station, failure, "Pending",
                             datetime.now().strftime("%Y-%m-%d %H:%M"),
                             "", "", "", "", "", "", img_b64, ""]
                        )
                        send_line_message(sn, model, failure)
                        st.success("✅ แจ้งซ่อมสำเร็จ!")
                        st.balloons()

    # --- ฟีเจอร์ที่ 2: ติดตามสถานะ (รองรับสแกน SN) ---
    elif menu == "🔍 ติดตามสถานะงาน":
        st.title("🔎 Follow Up Status")

        # เพิ่มช่องทางสแกน SN เพื่อค้นหาทันที
        with st.expander("📷 สแกน SN เพื่อค้นหา"):
            cam_scan = st.camera_input("ถ่ายรูป SN เพื่อค้นหา")

        search_input = st.text_input("🔍 ค้นหาด้วย SN หรือชื่อ Model",
                                     placeholder="พิมพ์หรือสแกนที่นี่...").strip().upper()

        if search_input:
            with st.spinner("กำลังค้นหาข้อมูล..."):
                df_main = get_df("sheet1")
                if not df_main.empty:
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
                                    st.write(f"📦 **Model:** {r['model']}")
                                    st.caption(f"📅 วันที่แจ้ง: {r['user_time']}")
                                with c2:
                                    st.markdown(f"""
                                        <div style='background-color:{status_color}; padding:10px; border-radius:10px; text-align:center;'>
                                            <span style='color:white; font-weight:bold;'>{status}</span>
                                        </div>
                                    """, unsafe_allow_html=True)

                                # แสดงข้อมูลการซ่อมเพิ่มเติมเมื่อมีการบันทึกผลแล้ว
                                if status != "Pending":
                                    # เปลี่ยนหัวข้อให้สื่อถึงการวิเคราะห์และแก้ไขตาม real_case
                                    with st.expander("📝 รายละเอียดการวิเคราะห์และแก้ไข"):
                                        # อ้างอิงจากคอลัมน์ real_case เป็นหลักตามความต้องการ
                                        st.markdown(f"**🔍 สาเหตุที่พบ (Real Case):** {r.get('real_case', '-')}")
                                        st.markdown(f"**🛠 วิธีการแก้ไข:** {r.get('action', '-')}")

                                        # แสดงหมายเหตุเพิ่มเติม (ถ้ามี)
                                        if r.get('remark'):
                                            st.info(f"💡 **หมายเหตุ:** {r['remark']}")

                                        # แสดงวันเวลาที่ทำรายการสำเร็จ
                                        st.caption(f"✅ ดำเนินการเสร็จสิ้นเมื่อ: {r.get('tech_time', '-')}")
                    else:
                        st.warning(f"⚠️ ไม่พบข้อมูลสำหรับ: '{search_input}'")
