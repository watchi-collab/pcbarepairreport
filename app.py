# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import cloudinary
import cloudinary.uploader
import requests
import time
from datetime import datetime

# --- CONFIGURATION ---
SHEET_ID = "1KtW9m3hFq2sBUeRkNATvD4nRKu_cDCoZENXk7WgOafc"

# --- 1. INITIALIZE CONNECTIONS ---
@st.cache_resource
def init_all():
    # Google Sheets Connection
    creds_dict = st.secrets["gcp_service_account"]
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    ss = client.open_by_key(SHEET_ID)
    
    # Cloudinary Connection (Using Environment Variable style)
    cloudinary.config(
        cloud_name = "dn8n04koh",
        api_key = "352259521151764",
        api_secret = "R9S6W2_-CGIP4d-_uKA-nKW1gOg",
        secure = True
    )
    return ss

ss = init_all()

# --- 2. HELPER FUNCTIONS ---
def send_line(msg):
    token = st.secrets["line_channel_access_token"]
    group_id = st.secrets["line_group_id"]
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    payload = {"to": group_id, "messages": [{"type": "text", "text": msg}]}
    try: requests.post(url, headers=headers, json=payload)
    except: pass

def upload_images(files, prefix, sn):
    urls = []
    if not files: return ""
    for i, file in enumerate(files):
        try:
            res = cloudinary.uploader.upload(
                file,
                folder = "repair_system",
                public_id = f"{prefix}_{sn}_{int(time.time())}_{i+1}",
                transformation = [{"width": 1000, "crop": "limit"}]
            )
            urls.append(res.get("secure_url"))
        except: continue
    return ",".join(urls)

def get_df(name):
    ws = ss.worksheet(name)
    df = pd.DataFrame(ws.get_all_records())
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df.fillna("")

# --- 3. AUTHENTICATION ---
if 'is_logged_in' not in st.session_state:
    st.session_state.is_logged_in = False

if not st.session_state.is_logged_in:
    st.title("🛠️ PCBA Repair System")
    with st.form("login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            df_u = get_df("users")
            match = df_u[(df_u['username'].astype(str)==u) & (df_u['password'].astype(str)==p)]
            if not match.empty:
                st.session_state.update({"is_logged_in": True, "user": u, "role": match.iloc[0]['role'].lower()})
                st.rerun()
            else: st.error("Login Failed")
    st.stop()

# --- 4. MAIN INTERFACE ---
ws = ss.worksheet("sheet1")
role = st.session_state.role

# --- TECH SECTION ---
if role == "tech":
    st.header(f"🔧 Technician: {st.session_state.user}")
    sn_scan = st.text_input("🔍 Scan Serial Number").strip().upper()
    
    if sn_scan:
        df = get_df("sheet1")
        active = df[(df['serial_number'].astype(str) == sn_scan) & (df['status'] == "Pending")]
        
        if not active.empty:
            job = active.iloc[-1]
            idx = active.index[-1] + 2
            
            col1, col2 = st.columns(2)
            with col1:
                st.info(f"**Model:** {job['model']}\n\n**Defect:** {job['failure']}")
                if job.get('user_image'):
                    st.image(str(job['user_image']).split(',')[0], caption="Image from User", use_container_width=True)
            
            with col2:
                with st.form("finish_job"):
                    stat = st.radio("Result", ["Complate", "Scrap"], horizontal=True)
                    act = st.text_input("Action")
                    t_files = st.file_uploader("Upload Tech Photo", accept_multiple_files=True)
                    if st.form_submit_button("Confirm & Close Job"):
                        t_urls = upload_images(t_files, "TECH", sn_scan)
                        now = datetime.now().strftime("%Y-%m-%d %H:%M")
                        # Update B (Status), K-O (Tech Info), Q (Tech Image)
                        ws.update(f'B{idx}', [[stat]])
                        ws.update(f'K{idx}:O{idx}', [[act, "", "", st.session_state.user, now]])
                        ws.update(f'Q{idx}', [[t_urls]])
                        send_line(f"✅ Job {stat}!\nSN: {sn_scan}\nBy: {st.session_state.user}")
                        st.success("Done!"); time.sleep(1); st.rerun()
        else:
            st.warning("No pending job found for this SN.")

# --- USER SECTION ---
elif role == "user":
    st.header("🚀 New Repair Request")
    df_m = get_df("model_mat")
    with st.form("request_form"):
        model = st.selectbox("Model", [""] + df_m['model'].tolist())
        sn = st.text_input("Serial Number").strip().upper()
        fail = st.text_area("Defect Detail")
        u_files = st.file_uploader("Attach Photo", accept_multiple_files=True)
        if st.form_submit_button("Submit"):
            if model and sn:
                u_urls = upload_images(u_files, "REQ", sn)
                p_name = df_m[df_m['model']==model].iloc[0]['product_name']
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                row = ["PCBA", "Pending", "", model, p_name, sn, "", fail, now, "", "", "", "", "", ""]
                ws.append_row(row + [u_urls])
                send_line(f"🚨 New Repair Request!\nSN: {sn}\nModel: {model}")
                st.success("Submitted!"); time.sleep(1); st.rerun()

# --- [ADMIN SECTION] ---
elif role in ["admin", "super admin"]:
    st.header("📊 Dashboard")
    df = get_clean_df("sheet1")
    if not df.empty:
        st.plotly_chart(px.pie(df, names='status', color='status', color_discrete_map={'Pending':'orange','Complate':'green','Scrap':'red'}))
        st.dataframe(df)
