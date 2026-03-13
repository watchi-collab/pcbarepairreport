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
import pytz 
from datetime import datetime
from PIL import Image
import plotly.express as px

# --- 1. SETTINGS & CONNECTIONS ---
st.set_page_config(page_title="Repair Management System PRO", layout="wide")
SHEET_ID = "1KtW9m3hFq2sBUeRkNATvD4nRKu_cDCoZENXk7WgOafc"

def get_now():
    tz = pytz.timezone('Asia/Bangkok')
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M")

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
            img.thumbnail((800, 800))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            buf.seek(0)
            res = cloudinary.uploader.upload(buf, folder="repair_system",
                public_id=f"{prefix}_{sn}_{int(time.time())}_{i+1}", format="jpg")
            urls.append(res.get("secure_url"))
        except: continue
    return ",".join(urls)

# --- 3. LOGIN & SESSION ---
if 'is_logged_in' not in st.session_state: st.session_state.is_logged_in = False

if not st.session_state.is_logged_in:
    st.title("🛡️ Repair System Login")
    with st.form("login_form"):
        u = st.text_input("Username").strip()
        p = st.text_input("Password", type="password").strip()
        mode = st.selectbox("โหมดการทำงาน", ["PCBA", "Machine"])
        if st.form_submit_button("เข้าสู่ระบบ", use_container_width=True):
            df_u = get_df("users")
            match = df_u[(df_u['username'].astype(str)==u) & (df_u['password'].astype(str)==p)]
            if not match.empty:
                st.session_state.update({"is_logged_in": True, "user": u, "role": str(match.iloc[0]['role']).lower(), "app_mode": mode})
                st.rerun()
            else: st.error("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    st.stop()

ws_main = ss.worksheet("sheet1")
role = st.session_state.role
current_user = st.session_state.user
app_mode = st.session_state.app_mode

with st.sidebar:
    st.title(f"👤 {current_user}")
    st.info(f"Role: {role.upper()}")
    st.divider()
    if st.button("ออกจากระบบ", use_container_width=True):
        st.session_state.is_logged_in = False; st.rerun()

# --- 4. USER INTERFACE ---
if role == "user":
    st.header(f"🚀 Repair Portal ({app_mode})")
    t1, t2 = st.tabs(["➕ แจ้งซ่อมใหม่", "🔍 ติดตามสถานะ"])

    with t1:
        with st.expander("➕ เพิ่ม Model ใหม่ (หากไม่มีในรายการ)"):
            nm, np = st.text_input("ชื่อ Model"), st.text_input("ชื่อ Product")
            if st.button("บันทึก Model"):
                target = "model_machine" if app_mode == "Machine" else "model_mat"
                ss.worksheet(target).append_row([nm.upper(), np])
                st.success("เพิ่มข้อมูลสำเร็จ!"); time.sleep(1); st.rerun()

        df_m = get_df("model_machine" if app_mode == "Machine" else "model_mat")
        df_st = get_df("station_dropdowns")
        with st.form("request_form"):
            c1, c2 = st.columns(2)
            sel_m = c1.selectbox("Model", [""] + df_m['model'].tolist())
            p_val = df_m[df_m['model']==sel_m]['product_name'].values[0] if sel_m else ""
            c1.text_input("Product", value=p_val, disabled=True)
            sn = c1.text_input("Serial Number").strip().upper()
            wo = c2.text_input("Work Order").strip().upper()
            stat = c2.selectbox("Station", [""] + df_st['station'].tolist())
            fail = c2.text_area("อาการเสีย")
            imgs = st.file_uploader("แนบรูปภาพ", accept_multiple_files=True)
            if st.form_submit_button("ส่งข้อมูลแจ้งซ่อม"):
                if sel_m and sn and wo:
                    urls = upload_images(imgs, "REQ", sn)
                    ws_main.append_row([app_mode, "Pending", wo, sel_m, p_val, sn, stat, fail, get_now(), "", "", "", "", "", "", urls])
                    send_line(f"🚨 แจ้งซ่อมใหม่: {sn} ({sel_m}) โดย {current_user}")
                    st.success("ส่งข้อมูลสำเร็จ!"); time.sleep(1); st.rerun()

    with t2:
        search = st.text_input("🔍 ค้นหา SN/Model").strip().upper()
        df_all = get_df("sheet1")
        if not df_all.empty:
            my_jobs = df_all[df_all['category'] == app_mode]
            if search: my_jobs = my_jobs[my_jobs['serial_number'].astype(str).str.contains(search)]
            for i, r in my_jobs.tail(10).iloc[::-1].iterrows():
                with st.expander(f"[{r['status']}] {r['serial_number']} - {r['user_time']}"):
                    st.write(f"**อาการ:** {r['failure']}")
                    if r['status'] == "Pending" and st.button("🔔 ตามงาน", key=f"urge_{i}"):
                        send_line(f"⚠️ ตามงานด่วน: {r['serial_number']}!"); st.success("ส่งแจ้งเตือนแล้ว")

# --- 5. TECHNICIAN INTERFACE ---
elif role == "tech":
    st.header("🔧 แผงควบคุมงานซ่อม (Technician)")
    sn_scan = st.text_input("🔍 สแกน Serial Number เพื่อทำงาน").strip().upper()
    if sn_scan:
        df_all = get_df("sheet1")
        job = df_all[(df_all['serial_number']==sn_scan) & (df_all['status']=="Pending")]
        if not job.empty:
            j = job.iloc[-1]; ridx = job.index[-1] + 2
            st.info(f"📍 {j['category']} | Model: {j['model']} | อาการ: {j['failure']}")
            
            # Feature: Bridge Machine to PCBA
            if j['category'] == "Machine":
                with st.expander("🔁 ส่งซ่อมบอร์ดต่อ (Bridge to PCBA)"):
                    pcba_sn = st.text_input("ระบุ SN บอร์ด").strip().upper()
                    if st.button("🚀 ยืนยันส่งซ่อมบอร์ด"):
                        ws_main.append_row(["PCBA", "Pending", j['work_order'], j['model'], j['product_name'], pcba_sn, "Machine Bridge", f"จากเครื่อง: {sn_scan}", get_now(), "", "", "", "", "", "", ""])
                        st.success(f"สร้างรายการซ่อมบอร์ด {pcba_sn} แล้ว")

            with st.form("close_job"):
                res = st.radio("ผลการซ่อม", ["Complate", "Scrap"], horizontal=True)
                cls = st.selectbox("Classification", [""] + get_df("class_dropdowns")['classification'].tolist())
                case = st.text_input("สาเหตุที่พบ")
                act = st.text_area("การแก้ไข")
                if st.form_submit_button("บันทึกปิดงาน"):
                    ws_main.update(f'B{ridx}', [[res]])
                    ws_main.update(f'J{ridx}:L{ridx}', [[case, act, cls]])
                    ws_main.update(f'N{ridx}:O{ridx}', [[current_user, get_now()]])
                    send_line(f"✅ ปิดงาน: {sn_scan} ({res}) โดย {current_user}")
                    st.success("บันทึกสำเร็จ!"); time.sleep(1); st.rerun()
        else: st.warning("ไม่พบรายการที่ค้างซ่อม")

# --- 6. ADMIN & SUPER ADMIN ---
elif role in ["admin", "super admin"]:
    st.header("📊 Dashboard & Management")
    df = get_df("sheet1")
    if not df.empty:
        # Analytics
        st.subheader("🛠️ สถิติแยกตามประเภทสาเหตุ (Classification)")
        df_cls = df[df['classification'] != ""]
        if not df_cls.empty:
            fig = px.bar(df_cls, x='classification', color='status', barmode='group')
            st.plotly_chart(fig, use_container_width=True)

        # Export
        towrite = io.BytesIO()
        df.to_excel(towrite, index=False, engine='openpyxl')
        st.download_button("📥 Export to Excel", data=towrite.getvalue(), file_name=f"RepairReport_{get_now()}.xlsx")
        st.dataframe(df)

    if role == "super admin":
        st.divider()
        st.header("👮 Super Admin: จัดการผู้ใช้งาน")
        df_u = get_df("users")
        st.table(df_u[['username', 'role']])
        with st.form("add_u"):
            nu, np, nr = st.text_input("Username"), st.text_input("Password"), st.selectbox("Role", ["user", "tech", "admin", "super admin"])
            if st.form_submit_button("เพิ่มพนักงาน"):
                ss.worksheet("users").append_row([nu, np, nr]); st.success("เพิ่มสำเร็จ!"); st.rerun()
