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
from models import DefectOut # List[DefectOut] 타입 힌트용
from typing import List      # List 타입 힌트용


# ------------------ 손상 기록 조회 기능 ------------------
# async def get_records(channel: discord.TextChannel):
#     # [가상 DB 데이터 - 실제는 AWS RDS에서 조회]
#     records = [
#         {"id": 1, "type": "콘크리트 균열", "location": "하이테크 센터 3층", "time": "2025-10-13 10:24", "risk": "높음", "image_url": "https://www.sciencetimes.co.kr/jnrepo/uploads//2018/02/n-ethicsalarms.jpg"},
#         {"id": 2, "type": "콘크리트 박리", "location": "본관 1층 모서리", "time": "2025-10-10 14:00", "risk": "낮음", "image_url": "https://samhwa.com/app/uploads/2022/11/defect_view_12_01.jpg"},
#         {"id": 3, "type": "누수 흔적", "location": "학생회관 2층", "time": "2025-10-05 09:30", "risk": "중간", "image_url": "https://octapi.lxzin.com/imageBlockProp/image/202506/18/720/0/a1f71cde-4048-4dbd-a5f6-9bfb63ef7f7b.png"},
#         {"id": 4, "type": "철근 노출", "location": "본관 2층 복도", "time": "2025-10-12 11:15", "risk": "중간", "image_url": "https://image.chosun.com/sitedata/image/202307/07/2023070701225_0.jpg"},
#         {"id": 5, "type": "강재 손상", "location": "학생회관 1층 외벽", "time": "2025-10-08 09:45", "risk": "높음", "image_url": "https://www.shutterstock.com/image-photo/rusty-weathered-concrete-wall-peeling-260nw-2646950607.jpg"},
#         {"id": 6, "type": "도장 손상", "location": "2호관 북쪽 외벽", "time": "2025-10-11 14:30", "risk": "높음", "image_url": "https://www.phiko.kr/data/file/z4_03/3743920070_k4YofaRs_d4637ad3df60465f3605cdf201cff7e62a5ebba6.jpeg"}
#     ]

#     risk_order = {"높음": 3, "중간": 2, "낮음": 1}
#     records.sort(key=lambda r: (-risk_order.get(r["risk"], 0), r["time"]))
    
#     await channel.send("📈 **보수 공사가 시급한 순으로 모든 손상 기록을 조회했어요\n**")

#     for record in records:
#         color = discord.Color.red() if record["risk"] == "높음" \
#                 else discord.Color.yellow() if record["risk"] == "중간" \
#                 else discord.Color.green()

#         embed = discord.Embed(
#             title=f"📍 {record['location']}",
#             description=(                
#                 f"🕒 **감지 시각 :** {record['time']}\n"
#                 f"🏷️ **손상 유형 :** {record['type']}\n"
#                 f"⚠️ **위험도 :** {record['risk']}\n"
#             ),
#             color=color
#         )

#         embed.set_image(url=record["image_url"])
#         await channel.send(embed=embed)


# ------------------ 손상 기록 조회 기능 (DB 연동) ------------------
async def get_records(channel: discord.TextChannel):
    
    # DB에서 데이터 조회 (sort는 DB가 담당)
    try:
        records: List[DefectOut] = await get_all_defects_from_db(sort_by_urgency=True)
    except Exception as e:
        await channel.send(f"❌ DB 조회 중 오류가 발생했습니다: {e}")
        return
        
    if not records:
        await channel.send("ℹ️ DB에 저장된 손상 기록이 없습니다.")
        return

    await channel.send("📈 **보수 공사가 시급한 순으로 모든 손상 기록을 조회했어요\n**")

    # Pydantic 모델 리스트(records)를 순회
    for record in records:
        
        # Pydantic 모델 속성(attribute) 사용
        
        # 위험도(Urgency)가 아직 분석 안됐으면(None) "분석 중"으로 표시
        risk = record.urgency or "분석 중" # None이 없게끔 처리
        
        # 위험도(Urgency)에 따른 색상 설정
        color = discord.Color.red() if risk == "높음" \
                else discord.Color.yellow() if risk == "보통" \
                else discord.Color.green() if risk == "낮음" \
                else discord.Color.greyple() # (분석 중일 때)

        # 위치 정보: 주소가 있으면 주소, 없으면 좌표
        location = record.address or f"좌표: {record.latitude}, {record.longitude}"
        
        # 이미지 URL: 로컬 경로(/data/..)인 경우 전체 URL로 변환
        image_url = record.image
        print(f"image url = {image_url}")
        if image_url and image_url.startswith("/data"):
            # (주의) 127.0.0.1:8000은 config.py에서 관리하는 것이 좋습니다.
            image_url = f"http://127.0.0.1:8000{image_url}" 

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


# ------------------ Google Calendar API 설정 ------------------
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


# ------------------ 보수 공사 일정 추가 기능 ------------------
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

# 드롭다운 형식(최대 +25일)
# class ScheduleSelect(Select):
#     def __init__(self):
#         today = datetime.date.today()
#         options = []

#         # 오늘부터 25일까지 날짜 옵션 생성
#         for i in range(1, 26):
#             date = today + datetime.timedelta(days=i)
#             formatted_date = date.strftime("%Y년 %m월 %d일")
#             options.append(SelectOption(label=formatted_date, value=date.isoformat()))

#         super().__init__(
#             placeholder="보수 공사를 희망하는 날짜를 선택하세요",
#             options=options
#         )

#     async def callback(self, interaction: discord.Interaction):
#         selected_date = self.values[0]
#         summary = "건물 외벽 보수 공사"
#         description = f"{interaction.user.display_name}님 요청 보수 공사 일정"

#         try:
#             event_link = add_to_calendar(selected_date, summary, description)
#             await interaction.response.edit_message(
#                 content=f"✅ **보수 공사 일정 확정**\n\n"
#                         f"{interaction.user.mention}님이 요청하신 보수 공사 일정이 **{selected_date}**에 추가되었습니다.\n"
#                         f"📅 캘린더에서 보기({event_link})",
#                 view=None
#             )
#         except Exception as e:
#             await interaction.response.edit_message(
#                 content=f"❌ 일정 추가 실패: {e}",
#                 view=None
#             )

# class ScheduleView(View):
#     def __init__(self):
#         super().__init__(timeout=120)
#         self.add_item(ScheduleSelect())