import os
import discord
import requests
import asyncio
from discord import app_commands, SelectOption, Embed
from discord.ui import View, Button, Select
import datetime

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

from database import get_all_defects_from_db 
from models import DefectOut
from typing import List


# ----- DB 연동 손상 기록 조회 -----
async def get_records(channel: discord.TextChannel):
    try:
        records: List[DefectOut] = await get_all_defects_from_db(sort_by_urgency=True)
    except Exception as e:
        await channel.send(f"❌ DB 조회 중 오류가 발생했습니다: {e}")
        return
        
    if not records:
        await channel.send("ℹ️ DB에 저장된 손상 기록이 없습니다.")
        return

    await channel.send("📈 **보수 공사가 시급한 순으로 모든 손상 기록을 조회했어요\n**")

    for record in records:        
        risk = record.urgency or "분석 중"
        
        color = discord.Color.red() if risk == "높음" \
                else discord.Color.yellow() if risk == "보통" \
                else discord.Color.green() if risk == "낮음" \
                else discord.Color.greyple() # 분석 중일 때

        location = record.address or f"좌표: {record.latitude}, {record.longitude}"
        
        image_url = record.image
        print(f"image url = {image_url}")
        if image_url and image_url.startswith("/data"):
            image_url = f"http://34.218.88.107:8000{image_url}"

        embed = discord.Embed(
            title=f"📍 {location}",
            description=(                
                f"🕒 **감지 시각 :** {record.detect_time}\n"
                f"🏷️ **손상 유형 :** {record.defect_type or '분석 중'}\n" 
                f"⚠️ **위험도 :** {risk}\n"
            ),
            color=color
        )
        
        print(f"after image url : {image_url}")
        if image_url and (image_url.startswith("http://") or image_url.startswith("https://")):
            embed.set_image(url=image_url)
            
        await channel.send(embed=embed)


# ----- Google Calendar API 설정 -----
SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_calendar_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('calendar', 'v3', credentials=creds)

def add_to_calendar(date: str, summary: str, description: str):
    service = get_calendar_service()
    event = {
        'summary': summary,
        'description': description,
        'start': {'date': date, 'timeZone': 'Asia/Seoul'},
        'end': {'date': date, 'timeZone': 'Asia/Seoul'}
    }
    created_event = service.events().insert(calendarId='primary', body=event).execute()
    return created_event.get('htmlLink')


# ----- 보수 공사 일정 추가 기능 -----
class DateInputModal(discord.ui.Modal, title="보수 공사 일정 입력"):
    date = discord.ui.TextInput(
        label="날짜 (YYYY-MM-DD)",
        placeholder="예: 2025-12-15",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            selected_date = datetime.datetime.strptime(self.date.value, "%Y-%m-%d").date()
            event_link = add_to_calendar(selected_date.isoformat(), "건물 외벽 보수 공사", f"{interaction.user.display_name}님 요청")
            await interaction.response.send_message(
                f"✅ **보수 공사 일정 확정**\n\n"
                f"{interaction.user.mention}님이 요청하신 보수 공사 일정이 **{selected_date}**에 추가되었습니다.\n"
                f"📅 캘린더에서 보기({event_link})",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ 잘못된 날짜 형식입니다. ({e})", ephemeral=True)