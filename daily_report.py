# daily_report.py
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

# ตั้งค่า Google Sheet
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
# ดึงค่า JSON จาก Environment Variable (ที่จะตั้งใน GitHub)
creds_dict = json.loads(os.environ["GCP_SERVICE_ACCOUNT"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
ss = client.open_by_key("1KtW9m3hFq2sBUeRkNATvD4nRKu_cDCoZENXk7WgOafc")
df = pd.DataFrame(ss.worksheet("sheet1").get_all_records())
df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

# สรุปรายงานสำหรับทั้ง PCBA และ Machine
tz = pytz.timezone('Asia/Bangkok')
today_str = datetime.now(tz).strftime("%d/%m/%Y")

for mode in ["PCBA", "Machine"]:
    df_mode = df[df['category'] == mode]
    if df_mode.empty: continue
    
    msg = f"📊 รายงาน Repair อัตโนมัติ ({today_str})\nส่วนงาน: {mode}\n"
    msg += "--------------------------------\n"
    
    # ราย WO
    for wo in df_mode['work_order'].unique():
        wo_df = df_mode[df_mode['work_order'] == wo]
        pending = len(wo_df[wo_df['status'].isin(['Pending', 'Wait Part'])])
        complete = len(wo_df[wo_df['status'].isin(['Complate', 'Scrap'])])
        msg += f"WO.{wo}: รวม {len(wo_df)} | วิเคราะห์ {pending} | เสร็จ {complete}\n"
    
    msg += "--------------------------------\n📍 สรุปภาพรวม\n"
    if mode == "Machine":
        for stn in df_mode['station'].unique():
            st_df = df_mode[df_mode['station'] == stn]
            msg += f"ST.{stn}: ทั้งหมด {len(st_df)} (วิเคราะห์ {len(st_df[st_df['status'].isin(['Pending', 'Wait Part'])])})\n"
    else:
        msg += f"ยอดรวม {len(df_mode)} บอร์ด"
    
    send_line(msg, os.environ["LINE_TOKEN"], os.environ["LINE_GROUP_ID"])
