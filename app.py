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
from datetime import datetime
from PIL import Image

# --- 1. SETTINGS & CONNECTIONS ---
st.set_page_config(page_title="Repair Management System", layout="wide")
SHEET_ID = "1KtW9m3hFq2sBUeRkNATvD4nRKu_cDCoZENXk7WgOafc"

@st.cache_resource
def init_all():
    try:
        creds_dict = st.secrets["gcp_service_account"]
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        ss = client.open_by_key(SHEET_ID)
        cloudinary.config(
            cloud_name = "dn8n04koh", api_key = "352259521151764",
            api_secret = "R9S6W2_-CGIP4d-_uKA-nKW1gOg", secure = True
        )
        return ss, True
    except Exception as e: return e, False

ss, success = init_all()
if not success:
    st.error(f"❌ Connection Error: {ss}"); st.stop()

# --- 2. HELPERS ---
def send_line(msg):
    token = st.secrets.get("line_channel_access_token")
    group_id = st.secrets.get("line_group_id")
    if not token or not group_id: return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    payload = {"to": group_id, "messages": [{"type": "text", "text": msg}]}
    try: requests.post(url, headers=headers, json=payload)
    except: pass

def get_df(name):
    try:
        ws = ss.worksheet(name)
        data = ws.get_all_records()
        if not data: return pd.DataFrame()
        df = pd.DataFrame(data)
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        return df.fillna("")
    except: return pd.DataFrame()

def upload_images(files, prefix, sn):
    urls = []
    if not files: return ""
    for i, file in enumerate(files):
        try:
            img = Image.open(file)
            img.thumbnail((1000, 1000))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            buf.seek(0)
            res = cloudinary.uploader.upload(buf, folder="repair_system",
                public_id=f"{prefix}_{sn}_{int(time.time())}_{i+1}", format="jpg")
            urls.append(res.get("secure_url"))
        except: continue
    return ",".join(urls)

# --- 3. AUTH & SESSION ---
if 'is_logged_in' not in st.session_state: st.session_state.is_logged_in = False

if not st.session_state.is_logged_in:
    st.title("⚙️ Repair System Login")
    with st.form("login"):
        u = st.text_input("Username").strip()
        p = st.text_input("Password", type="password").strip()
        mode = st.selectbox("โหมดการทำงาน", ["PCBA", "Machine"])
        if st.form_submit_button("Login", use_container_width=True):
            df_u = get_df("users")
            if not df_u.empty:
                match = df_u[(df_u['username'].astype(str)==u) & (df_u['password'].astype(str)==p)]
                if not match.empty:
                    st.session_state.update({"is_logged_in": True, "user": u, "role": str(match.iloc[0]['role']).lower(), "app_mode": mode})
                    st.rerun()
                else: st.error("ข้อมูลไม่ถูกต้อง")
    st.stop()

ws_main = ss.worksheet("sheet1")
role = st.session_state.role
current_user = st.session_state.user
app_mode = st.session_state.app_mode

with st.sidebar:
    st.title(f"👤 {current_user}")
    st.info(f"Mode: {app_mode}")
    if st.button("Log out"):
        st.session_state.is_logged_in = False; st.rerun()

# --- 4. [TECH PAGE] ---
if role == "tech":
    st.header("🔧 แผงควบคุมช่าง (Technician)")
    sn_scan = st.text_input("🔍 สแกน Serial Number", placeholder="Scan Barcode...").strip().upper()
    
    if sn_scan:
        df_all = get_df("sheet1")
        repeat = df_all[(df_all['serial_number'].astype(str) == sn_scan) & (df_all['status'] != "Pending")]
        if not repeat.empty:
            st.warning(f"⚠️ ตรวจพบประวัติการซ่อมซ้ำ! ({len(repeat)} ครั้ง)")
            with st.expander("ดูประวัติเก่า"):
                st.table(repeat[['user_time', 'failure', 'real_case', 'action']])

        job_match = df_all[(df_all['serial_number'].astype(str) == sn_scan) & (df_all['status'] == "Pending")]
        if not job_match.empty:
            job = job_match.iloc[-1]; row_idx = job_match.index[-1] + 2
            df_class = get_df("classification_dropdowns")
            class_list = df_class['classification'].tolist() if not df_class.empty else ["Other"]

            c1, c2 = st.columns(2)
            with c1:
                st.info(f"**Model:** {job.get('model')} | **อาการ:** {job.get('failure')}")
                if job.get('user_image'):
                    for img in str(job['user_image']).split(','):
                        if img.strip(): st.image(img.strip(), use_container_width=True)
            with c2:
                with st.form("tech_close"):
                    res = st.radio("ผลการซ่อม:", ["Complate", "Scrap"], horizontal=True)
                    cls = st.selectbox("Classification", [""] + class_list)
                    case = st.text_input("Real Case")
                    act = st.text_area("Action")
                    imgs = st.file_uploader("รูปหลังซ่อม", accept_multiple_files=True)
                    if st.form_submit_button("บันทึกปิดงาน"):
                        t_urls = upload_images(imgs, "TECH", sn_scan)
                        now = datetime.now().strftime("%Y-%m-%d %H:%M")
                        ws_main.update(f'B{row_idx}', [[res]])
                        ws_main.update(f'J{row_idx}:L{row_idx}', [[case, act, cls]])
                        ws_main.update(f'N{row_idx}:O{row_idx}', [[current_user, now]])
                        ws_main.update(f'Q{row_idx}', [[t_urls]])
                        send_line(f"✅ ซ่อมเสร็จ! {res} | SN: {sn_scan} โดยช่าง: {current_user}")
                        st.success("บันทึกเรียบร้อย!"); time.sleep(1); st.rerun()
        else: st.info("🔍 ไม่พบงานค้างซ่อมสำหรับ SN นี้")

    st.divider()
    st.subheader("🕒 ประวัติการซ่อมล่าสุด")
    df_h = get_df("sheet1")
    if not df_h.empty and 'category' in df_h.columns:
        recent = df_h[(df_h['status'] != "Pending") & (df_h['category'] == app_mode)].tail(10)
        st.table(recent[['user_time', 'serial_number', 'status', 'real_case']])

# --- 5. [USER PAGE] ---
elif role == "user":
    st.header(f"🚀 ระบบแจ้งซ่อม ({app_mode})")
    
    # --- ส่วนติดตามสถานะงานพร้อมปุ่มแจ้งเตือนช่าง ---
    st.subheader("📊 ติดตามสถานะงานและแจ้งเตือน")
    
    col_s1, col_s2 = st.columns([3, 1])
    with col_s1:
        search_query = st.text_input("🔍 ค้นหา SN หรือ Model เพื่อติดตามงาน", placeholder="พิมพ์เพื่อค้นหา...").strip().upper()
    with col_s2:
        st.write(" ")
        if st.button("🔄 Refresh Status", use_container_width=True): st.rerun()
    
    df_s = get_df("sheet1")
    if not df_s.empty and 'category' in df_s.columns:
        my_jobs = df_s[df_s['category'] == app_mode]
        if search_query:
            my_jobs = my_jobs[(my_jobs['serial_number'].astype(str).str.contains(search_query)) | 
                             (my_jobs['model'].astype(str).str.contains(search_query))]
        else:
            my_jobs = my_jobs.tail(5)

        if not my_jobs.empty:
            my_jobs = my_jobs.iloc[::-1] # ล่าสุดขึ้นก่อน
            for _, row in my_jobs.iterrows():
                # สร้างการแสดงผลแต่ละรายการพร้อมปุ่มแจ้งเตือน
                with st.expander(f"📌 SN: {row['serial_number']} | Status: {row['status']} | Time: {row['user_time']}"):
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        st.write(f"**Model:** {row['model']} | **WO:** {row['work_order']}")
                        st.write(f"**อาการเสีย:** {row['failure']}")
                        if row['status'] != "Pending":
                            st.write(f"✅ **วิธีแก้:** {row['action']}")
                    with c2:
                        # ปุ่มแจ้งเตือนช่าง (เฉพาะงานที่ยังไม่เสร็จ)
                        if row['status'] == "Pending":
                            if st.button(f"🔔 ตามงานช่าง SN: {row['serial_number'][-4:]}", key=f"btn_{row['serial_number']}"):
                                send_line(f"⚠️ [ติดตามงานด่วน!]\nSN: {row['serial_number']}\nสถานะ: {row['status']}\nแจ้งโดย: {current_user}\nรบกวนช่างตรวจสอบด้วยครับ")
                                st.success("ส่งการแจ้งเตือนเข้า LINE แล้ว!")
                        else:
                            st.success("งานนี้ซ่อมเสร็จแล้ว")

    st.divider()
    # --- ฟอร์มแจ้งซ่อมใหม่ ---
    st.subheader("📝 สร้างใบแจ้งซ่อมใหม่")
    df_m = get_df("model_machine" if app_mode == "Machine" else "model_mat")
    df_st = get_df("station_dropdowns")

    with st.form("user_req"):
        col1, col2 = st.columns(2)
        with col1:
            sel_m = st.selectbox("เลือก Model", [""] + (df_m['model'].tolist() if not df_m.empty else []))
            p_name = df_m[df_m['model'] == sel_m]['product_name'].values[0] if sel_m and not df_m.empty else ""
            st.text_input("Product Name", value=p_name, disabled=True)
            sn = st.text_input("Serial Number").strip().upper()
        with col2:
            wo = st.text_input("Work Order").strip().upper()
            stat = st.selectbox("Station", [""] + (df_st['station'].tolist() if not df_st.empty else []))
            fail = st.text_area("รายละเอียดอาการเสีย")
        
        up_imgs = st.file_uploader("📸 แนบรูปภาพ", accept_multiple_files=True)
        if st.form_submit_button("📤 ส่งใบแจ้งซ่อม", use_container_width=True):
            if sel_m and sn and wo:
                u_urls = upload_images(up_imgs, "REQ", sn)
                now_s = datetime.now().strftime("%Y-%m-%d %H:%M")
                row_data = [app_mode, "Pending", wo, sel_m, p_name, sn, stat, fail, now_s, "", "", "", "", "", ""]
                ws_main.append_row(row_data + [u_urls])
                send_line(f"🚨 แจ้งซ่อมใหม่!\nSN: {sn}\nModel: {sel_m}\nโดย: {current_user}")
                st.success("ส่งเรียบร้อย!"); time.sleep(1); st.rerun()

# --- [หน้าสำหรับ ADMIN / SUPER ADMIN] ---
elif role in ["admin", "super admin"]:
    st.header("📊 Dashboard ระบบแจ้งซ่อม")
    df = get_clean_df("sheet1")
    
    if not df.empty:
        # ส่วนแสดง Metrics สรุปผล
        c1, c2, c3 = st.columns(3)
        c1.metric("งานค้าง (Pending)", len(df[df['status'] == "Pending"]))
        c2.metric("ซ่อมเสร็จ (Complate)", len(df[df['status'] == "Complate"]))
        c3.metric("Scrap", len(df[df['status'] == "Scrap"]))
        
        st.divider()
        
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            st.subheader("สัดส่วนสถานะงาน")
            fig = px.pie(df, names='status', color='status', 
                         color_discrete_map={'Pending':'orange','Complate':'green','Scrap':'red'})
            st.plotly_chart(fig, use_container_width=True)
            
        with col_chart2:
            st.subheader("งานแยกตาม Model")
            fig2 = px.bar(df, x='model', color='status', barmode='group')
            st.plotly_chart(fig2, use_container_width=True)

        st.subheader("📋 ตารางข้อมูลทั้งหมด")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("ยังไม่มีข้อมูลในระบบ")
