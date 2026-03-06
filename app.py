# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
from datetime import datetime
from PIL import Image
import requests
import json

# --- CONFIGURATION ---
DRIVE_FOLDER_ID = "1XRG-tnve3utZCkyfPEzwNQFYnHat9QIE"
SHEET_ID = "1KtW9m3hFq2sBUeRkNATvD4nRKu_cDCoZENXk7WgOafc"

# --- 1. CONNECTION SETUP ---
@st.cache_resource
def init_connections():
    try:
        creds_dict = st.secrets["gcp_service_account"]
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SHEET_ID)
        drive_service = build('drive', 'v3', credentials=creds)
        return spreadsheet, drive_service, True
    except: return None, None, False

ss, drive_service, conn_status = init_connections()

# --- 2. CORE HELPERS ---
def upload_to_drive(file, file_name):
    if not file: return ""
    try:
        img = Image.open(file).convert('RGB')
        img.thumbnail((1200, 1200))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        buf.seek(0)
        file_metadata = {'name': file_name, 'parents': [DRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(buf, mimetype='image/jpeg', resumable=True)
        return drive_service.files().create(body=file_metadata, media_body=media, fields='webViewLink').execute().get('webViewLink')
    except: return ""

def get_clean_df(sheet_name):
    try:
        ws = ss.worksheet(sheet_name)
        df = pd.DataFrame(ws.get_all_records())
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        return df.fillna("")
    except: return pd.DataFrame()

# --- 3. LOGIN INTERFACE ---
if 'login' not in st.session_state: st.session_state.login = False

if not st.session_state.login:
    st.title("🔐 Repair System Login")
    with st.form("login_form"):
        u = st.text_input("Username").strip()
        p = st.text_input("Password", type="password").strip()
        if st.form_submit_button("Login"):
            df_u = get_clean_df("users")
            match = df_u[(df_u['username'].astype(str) == u) & (df_u['password'].astype(str) == p)]
            if not match.empty:
                st.session_state.update({"login": True, "user": u, "role": match.iloc[0]['role']})
                st.rerun()
            else: st.error("Invalid credentials")
    st.stop()

# --- 4. DASHBOARD LOGIC BY ROLE ---
role = st.session_state.role.lower()
st.sidebar.markdown(f"### 👤 {st.session_state.user}\n**Role:** {role.upper()}")
if st.sidebar.button("Log out"):
    st.session_state.login = False
    st.rerun()

# --- SECTION: USER (PCBA & MACHINE) ---
if role == "user":
    st.header("📋 New Repair Request")
    type_choice = st.radio("Select Type", ["PCBA", "Machine"], horizontal=True)
    
    with st.form("user_request", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            wo = st.text_input("Work Order (WO)")
            model = st.text_input("Model")
            sn = st.text_input("Serial Number (SN)")
        with c2:
            station = st.selectbox("Station", ["SMT", "DIP", "FCT", "Packing", "Machine Area"])
            defect = st.text_area("Defect Detail")
            img = st.file_uploader("Upload Defect Image", type=['jpg','png','jpeg'])
            
        if st.form_submit_button("Submit Request"):
            if wo and sn and defect:
                with st.spinner("Uploading..."):
                    img_url = upload_to_drive(img, f"REQ_{sn}.jpg")
                    ws = ss.worksheet("sheet1")
                    # Append: type, time, wo, model, sn, station, defect, img, status
                    ws.append_row([type_choice, datetime.now().strftime("%Y-%m-%d %H:%M"), wo, model, sn, station, defect, img_url, "Pending"])
                    st.success(f"{type_choice} Request Sent!")
            else: st.error("Please fill all required fields.")

# --- SECTION: TECH (STRINGING USER DATA) ---
elif role == "tech":
    st.header("🔧 Technician Action Center")
    type_filter = st.radio("View Tasks For", ["PCBA", "Machine"], horizontal=True)
    
    search_sn = st.text_input("🔍 Search Serial Number (SN)").strip()
    if search_sn:
        df = get_clean_df("sheet1")
        # Filter for active jobs of specific type
        job = df[(df['serial_number'].astype(str) == search_sn) & (df['category'].astype(str) == type_filter) & (df['status'] != "Completed")].tail(1)
        
        if not job.empty:
            st.success(f"Task Found for {type_filter}")
            st.info(f"**User Data:** WO: {job.iloc[0]['work_order']} | Model: {job.iloc[0]['model']} | Defect: {job.iloc[0]['failure']}")
            if job.iloc[0].get('image'): st.image(job.iloc[0]['image'], width=300)
            
            with st.form("tech_action"):
                st.subheader("🛠️ Record Action")
                real_case = st.text_input("Real Case")
                remark = st.text_area("Remark")
                action_img = st.file_uploader("Upload Action Image", type=['jpg','png','jpeg'])
                
                # Logic for Forwarding PCBA
                fwd_loop = False
                if type_filter == "PCBA":
                    fwd_loop = st.checkbox("Forward to Tech PCBA (Re-Repair Loop)")

                if st.form_submit_button("Save & Close Task"):
                    idx = df[df['serial_number'].astype(str) == search_sn].index[-1] + 2
                    ws = ss.worksheet("sheet1")
                    img_link = upload_to_drive(action_img, f"TECH_{search_sn}.jpg")
                    
                    status = "Pending (Fwd)" if fwd_loop else "Completed"
                    # Update columns: Status(I), RealCase(K), Remark(P), Image(S), Time(Q) - Adjust mapping to your sheet
                    ws.update(f'I{idx}', [[status]])
                    ws.update(f'K{idx}', [[real_case]])
                    ws.update(f'P{idx}', [[remark]])
                    ws.update(f'Q{idx}', [[datetime.now().strftime("%Y-%m-%d %H:%M")]])
                    st.success("Action Recorded!")
        else: st.error("No active task found for this SN.")

# --- SECTION: ADMIN & SUPER ADMIN ---
elif role in ["admin", "super admin"]:
    st.header("🏛️ Management Dashboard")
    df_all = get_clean_df("sheet1")
    st.dataframe(df_all, use_container_width=True)
    
    if role == "super admin":
        st.subheader("🔑 System Configuration (Super Admin Only)")
        st.write("Full control over Users and Master Data tables.")
