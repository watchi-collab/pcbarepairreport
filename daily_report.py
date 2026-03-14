import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import pytz
from datetime import datetime
import os
import json

def send_line(msg, token, group_id):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    payload = {"to": group_id, "messages": [{"type": "text", "text": msg}]}
    requests.post(url, headers=headers, json=payload)

try:
    # ดึงค่าจาก ENV ที่ตั้งไว้ใน Workflow
    gcp_json = os.environ.get("GCP_JSON_DATA")
    line_token = os.environ.get("LINE_TOKEN")
    line_group = os.environ.get("LINE_GROUP_ID")

    if not gcp_json:
        raise ValueError("GCP_JSON_DATA is empty or not found in Secrets")

    # เชื่อมต่อ Google Sheets
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_info = json.loads(gcp_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
    client = gspread.authorize(creds)
    
    SHEET_ID = "1KtW9m3hFq2sBUeRkNATvD4nRKu_cDCoZENXk7WgOafc"
    ss = client.open_by_key(SHEET_ID)
    df = pd.DataFrame(ss.worksheet("sheet1").get_all_records())
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

    # สรุปรายงาน
    tz = pytz.timezone('Asia/Bangkok')
    today_str = datetime.now(tz).strftime("%d/%m/%Y")

    for mode in ["PCBA", "Machine"]:
        df_mode = df[df['category'] == mode]
        if df_mode.empty: continue
        
        msg = f"📊 รายงาน Repair อัตโนมัติ ({today_str})\nส่วนงาน: {mode}\n"
        msg += "--------------------------------\n"
        
        for wo in df_mode['work_order'].unique():
            wo_df = df_mode[df_mode['work_order'] == wo]
            pending = len(wo_df[wo_df['status'].isin(['Pending', 'Wait Part'])])
            done = len(wo_df[wo_df['status'].isin(['Complate', 'Scrap'])])
            msg += f"WO.{wo}: ทั้งหมด {len(wo_df)} | วิเคราะห์ {pending} | เสร็จ {done}\n"
        
        msg += "--------------------------------\n📍 สรุปภาพรวม\n"
        if mode == "Machine":
            for stn in df_mode['station'].unique():
                st_df = df_mode[df_mode['station'] == stn]
                msg += f"ST.{stn}: ทั้งหมด {len(st_df)} (วิเคราะห์ {len(st_df[st_df['status'].isin(['Pending', 'Wait Part'])])})\n"
        else:
            msg += f"ยอดรวม {len(df_mode)} บอร์ด"
        
        send_line(msg, line_token, line_group)
        print(f"Report for {mode} sent successfully.")

except Exception as e:
    print(f"❌ Error: {str(e)}")
    exit(1)
