# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import io
import base64
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from PIL import Image
import requests
import json

# --- 1. SETTINGS & STYLE ---
st.set_page_config(page_title="PCBA System 2026 PRO", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { 
        background-color: #ffffff; 
        padding: 20px; 
        border-radius: 12px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        border: 1px solid #eee;
    }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #ffffff;
        border-radius: 8px 8px 0px 0px;
        padding: 10px 20px;
        border: 1px solid #eee;
    }
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
        return pd.DataFrame(data) if data else pd.DataFrame()
    except:
        return pd.DataFrame()


# ฟังก์ชันจัดการตัวเลือก Dropdown (ต้องมีเพื่อให้ User/Tech ทำงานได้)
def get_dropdown_options(sheet_name):
    df = get_df(sheet_name)
    options = ["--กรุณาเลือก--"]
    if not df.empty:
        options.extend(df.iloc[:, 0].astype(str).tolist())
    return options


def save_image_b64(file):
    if not file: return ""
    img = Image.open(file)
    img.thumbnail((450, 450))
    buf = io.BytesIO()
    img.convert('RGB').save(buf, format="JPEG", quality=60)
    return base64.b64encode(buf.getvalue()).decode()


def calculate_tat(row):
    try:
        if row['user_time'] and row['tech_time']:
            fmt = "%Y-%m-%d %H:%M"
            start = datetime.strptime(str(row['user_time']), fmt)
            end = datetime.strptime(str(row['tech_time']), fmt)
            diff = end - start
            return round(diff.total_seconds() / 3600, 2)
    except:
        pass
    return None


# --- 3. SIDEBAR & LOGIN ---
with st.sidebar:
    if status_conn:
        st.success("● System Online")
    else:
        st.error("○ System Offline")

    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if st.session_state.logged_in:
        st.info(f"User: {st.session_state.user}\nRole: {st.session_state.role}")
        if st.button("🚪 Logout"):
            st.session_state.logged_in = False
            st.rerun()

if not st.session_state.logged_in:
    st.title("🔐 Login PCBA PRO")
    with st.form("login"):
        u = st.text_input("Username").strip()
        p = st.text_input("Password", type="password").strip()
        if st.form_submit_button("เข้าสู่ระบบ"):
            df_u = get_df("users")
            match = df_u[(df_u['username'] == u) & (df_u['password'].astype(str) == p)]
            if not match.empty:
                st.session_state.update({"logged_in": True, "user": u, "role": match.iloc[0]['role']})
                st.rerun()
            else:
                st.error("ข้อมูลไม่ถูกต้อง")
    st.stop()

role = st.session_state.role.lower()

# ---------------- [SECTION: ADMIN] ----------------
if role == "admin":
    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["📊 Dashboard", "👥 Master Data", "🔻 Dropdowns", "🔍 Repair View", "📸 QA Gallery"])
    df_main = get_df("sheet1")

    with tab1:
        if not df_main.empty:
            df_main['dt'] = pd.to_datetime(df_main['user_time'])
            df_main['date_only'] = df_main['dt'].dt.date
            col_d1, col_d2 = st.columns([2, 1])
            with col_d1:
                dr = st.date_input("Filter Range", [df_main['date_only'].min(), df_main['date_only'].max()])
            with col_d2:
                if st.button("🔄 Refresh Data"):
                    st.cache_resource.clear();
                    st.rerun()

            df_f = df_main[
                (df_main['date_only'] >= dr[0]) & (df_main['date_only'] <= (dr[1] if len(dr) > 1 else dr[0]))].copy()
            df_f['tat'] = df_f.apply(calculate_tat, axis=1)

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Jobs", len(df_f))
            m2.metric("Pending", len(df_f[df_f['status'] == 'Pending']))
            m3.metric("Avg TAT", f"{df_f['tat'].mean():.1f} Hr" if not df_f['tat'].empty else "N/A")
            m4.metric("Scrap Rate",
                      f"{(len(df_f[df_f['status'] == 'Scrapped']) / len(df_f) * 100):.1f}%" if len(df_f) > 0 else "0%")

            st.subheader("🔥 Repair Load Heatmap")
            df_f['hour'] = df_f['dt'].dt.hour
            df_f['day'] = df_f['dt'].dt.day_name()
            heatmap_data = df_f.groupby(['day', 'hour']).size().unstack(fill_value=0)
            st.plotly_chart(px.imshow(heatmap_data, color_continuous_scale='Blues'), use_container_width=True)
    # --- TAB 2: MASTER DATA (User & Model) ---
    with tab2:
        st.subheader("👥 การจัดการข้อมูลผู้ใช้งานและโมเดลสินค้า")
        target_sheet = st.selectbox("เลือกข้อมูลที่ต้องการจัดการ", ["users", "model_mat"])

        df_edit = get_df(target_sheet)
        if not df_edit.empty:
            # ใช้ st.data_editor เพื่อให้ Admin สามารถแก้ไขข้อมูลบนหน้าเว็บได้ทันที
            edited_df = st.data_editor(df_edit, num_rows="dynamic", use_container_width=True,
                                       key=f"edit_{target_sheet}")

            if st.button(f"💾 บันทึกการเปลี่ยนแปลงใน {target_sheet}"):
                try:
                    ws_target = ss.worksheet(target_sheet)
                    ws_target.clear()  # ล้างข้อมูลเก่า
                    # บันทึกข้อมูลใหม่รวมถึง Header
                    ws_target.update([edited_df.columns.values.tolist()] + edited_df.values.tolist())
                    st.success("บันทึกข้อมูลเรียบร้อยแล้ว!")
                    st.cache_resource.clear()  # ล้าง Cache เพื่อให้ดึงข้อมูลใหม่มาใช้ทันที
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาด: {e}")

    # --- TAB 3: DROPDOWNS ---
    with tab3:
        st.subheader("🔻 ตั้งค่ารายการตัวเลือก (Dropdown Lists)")
        # ดึงชื่อแผ่นงานที่เกี่ยวข้องกับ Dropdown ทั้งหมด
        drop_sheets = ["station_dropdowns", "defect_dropdowns", "action_dropdowns", "classification_dropdowns"]
        selected_drop = st.selectbox("เลือกรายการที่ต้องการแก้ไข", drop_sheets)

        df_drop = get_df(selected_drop)
        if not df_drop.empty:
            # ตารางสำหรับแก้ไขตัวเลือก
            edited_drop = st.data_editor(df_drop, num_rows="dynamic", use_container_width=True,
                                         key=f"edit_{selected_drop}")

            if st.button(f"💾 อัปเดตรายการ {selected_drop}"):
                try:
                    ws_drop = ss.worksheet(selected_drop)
                    ws_drop.clear()
                    ws_drop.update([edited_drop.columns.values.tolist()] + edited_drop.values.tolist())
                    st.success("อัปเดตรายการสำเร็จ!")
                    st.cache_resource.clear()
                except Exception as e:
                    st.error(f"ไม่สามารถบันทึกได้: {e}")
    with tab4:
        st.subheader("🔍 Repair View")
        df_m = get_df("model_mat")
        if not df_main.empty:
            df_v = df_main.merge(df_m[['model', 'product_name']], on='model', how='left')
            st.dataframe(df_v, use_container_width=True, hide_index=True)
            st.download_button("📥 Download CSV", df_v.to_csv(index=False).encode('utf-8-sig'), "report.csv", "text/csv")

    with tab5:
        st.subheader("📸 QA Gallery")
        search_sn = st.text_input("Enter SN to Compare").upper()
        gal = df_main[df_main['sn'] == search_sn] if search_sn else df_main.tail(6)
        for _, r in gal.iterrows():
            with st.expander(f"📦 SN: {r['sn']} | {r['status']}"):
                c1, c2 = st.columns(2)
                if r['img_user']: c1.image(f"data:image/jpeg;base64,{r['img_user']}", caption="Before")
                if r['img_tech']: c2.image(f"data:image/jpeg;base64,{r['img_tech']}", caption="After")

# ---------------- [SECTION: TECHNICIAN] ----------------
elif role == "technician":
    st.title("🔧 Technician Repair Record")
    target_sn = st.text_input("🔍 Scan Serial Number (SN)").upper()
    if target_sn:
        df_main = get_df("sheet1")
        job = df_main[(df_main['sn'] == target_sn) & (df_main['status'] == 'Pending')].tail(1)
        if not job.empty:
            st.info(f"**Model:** {job.iloc[0]['model']} | **Symptom:** {job.iloc[0]['failure']}")
            with st.form("repair_result"):
                col1, col2 = st.columns(2)
                with col1:
                    real_case = st.text_input("Real Case")
                    defect = st.selectbox("Defect Type", get_dropdown_options("defect_dropdowns"))
                with col2:
                    action = st.selectbox("Action Taken", get_dropdown_options("action_dropdowns"))
                    classify = st.selectbox("Classification", get_dropdown_options("classification_dropdowns"))
                status = st.radio("Repair Result", ["Completed", "Scrapped"], horizontal=True)
                t_file = st.file_uploader("Upload Repair Photo", type=['jpg', 'png'])
                if st.form_submit_button("Save & Close Job"):
                    if "--กรุณาเลือก--" in [defect, action, classify]:
                        st.error("❌ กรุณาเลือกตัวเลือกให้ครบถ้วน")
                    else:
                        img_tech = save_image_b64(t_file)
                        row_idx = ss.worksheet("sheet1").find(target_sn).row
                        ws = ss.worksheet("sheet1")
                        # อัปเดตทีละช่วงเพื่อความแม่นยำ
                        ws.update(range_name=f'G{row_idx}', values=[[status]])
                        ws.update(range_name=f'I{row_idx}:M{row_idx}',
                                  values=[[real_case, defect, action, classify, ""]])
                        ws.update(range_name=f'N{row_idx}', values=[[datetime.now().strftime("%Y-%m-%d %H:%M")]])
                        ws.update(range_name=f'P{row_idx}', values=[[img_tech]])
                        st.success("บันทึกสำเร็จ!");
                        st.rerun()
        else:
            st.warning("ไม่พบงานค้างซ่อม")

# ---------------- [SECTION: USER] ----------------
elif role == "user":
    st.title("📱 PCBA Repair Request")
    with st.form("user_request"):
        u_sn = st.text_input("Serial Number").upper()
        u_mod = st.selectbox("Model", get_dropdown_options("model_mat"))
        u_st = st.selectbox("Station", get_dropdown_options("station_dropdowns"))
        u_fail = st.text_area("Symptom/Failure")
        u_file = st.file_uploader("Take/Upload Photo")
        if st.form_submit_button("Submit Request"):
            if u_mod == "--กรุณาเลือก--" or u_st == "--กรุณาเลือก--" or not u_sn:
                st.error("❌ กรุณากรอกข้อมูลให้ครบ")
            else:
                img_u = save_image_b64(u_file)
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                ss.worksheet("sheet1").append_row(
                    ["", u_sn, u_mod, "", u_st, u_fail, "Pending", now, "", "", "", "", "", "", img_u, ""])
                st.success("ส่งข้อมูลสำเร็จ!");
                st.balloons()
