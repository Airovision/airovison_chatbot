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

from database import get_all_defects_from_db, get_defect_by_id, update_repair_status
from models import DefectOut
from typing import List


# ----- DB 연동 손상 기록 조회 -----
def build_defect_detail_embed(record: DefectOut) -> discord.Embed:
    """
    DefectOut 객체를 기반으로 Embed 형태의 상세 정보를 생성합니다.
    """

    risk = record.urgency or "분석 중"
    repair = record.repair_status or "미처리"

    color = discord.Color.red() if risk == "높음" \
            else discord.Color.yellow() if risk == "보통" \
            else discord.Color.green() if risk == "낮음" \
            else discord.Color.greyple()

    location = record.address or f"좌표: {record.latitude}, {record.longitude}"

    embed = discord.Embed(
        title=f"🔍 손상 상세 보기",
        description=(
            f"📍 **위치 :** {location}\n"
            f"🕒 **감지 시각 :** {record.detect_time}\n"
            f"🏷️ **손상 유형 :** {record.defect_type or '분석 중'}\n"
            f"⚠️ **위험도 :** {risk}\n"
            f"🔧 **보수 상태 :** {repair}\n"
        ),
        color=color
    )

    image_url = record.image
    if image_url and image_url.startswith("/data"):
        image_url = f"http://34.218.88.107:8000{image_url}"
    if image_url and (image_url.startswith("http://") or image_url.startswith("https://")):
        embed.set_image(url=image_url)

    return embed


class DefectSelect(discord.ui.Select):
    """
    전체 손상 기록 중 상세 정보를 확인할 손상 기록을 선택합니다.  
    """

    def __init__(self, records: List[DefectOut]):
        options = []
        for r in records:
            short_loc = (r.address or f"{r.latitude:.4f}, {r.longitude:.4f}")[:45]
            label = f"{short_loc}"
            repair = r.repair_status or "미처리"
            desc = f"{r.detect_time} | {r.defect_type or '분석 중'} | {r.urgency or '분석 중'} | {repair}"
            options.append(SelectOption(label=label, description=desc[:100], value=r.id))

        super().__init__(
            placeholder="상세 정보를 확인하고 싶거나 보수 공사를 완료한 손상을 선택하세요",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        defect_id = self.values[0]
        record = await get_defect_by_id(defect_id)
        if not record:
            await interaction.response.send_message("❌ 선택한 손상 기록을 찾을 수 없습니다.", ephemeral=True)
            return

        detail_embed = build_defect_detail_embed(record)
        view = DefectDetailView(record)

        await interaction.response.send_message(
            embed=detail_embed,
            view=view
        )

class DefectSelectView(View):
    def __init__(self, records: List[DefectOut]):
        super().__init__(timeout=600)
        self.add_item(DefectSelect(records))


async def get_records(channel: discord.TextChannel):
    """
    탐지 시각으로부터 30일이 지나지 않은 모든 손상 기록을 Embed 형태로 조회합니다.
    보수 공사가 긴급한 순으로 정렬하며, 상세 정보를 확인할 수 있는 Select 리스트도 함께 전송합니다.
    """

    try:
        records: List[DefectOut] = await get_all_defects_from_db(sort_by_urgency=True)
    except Exception as e:
        await channel.send(f"❌ DB 조회 실패: {e}")
        return
        
    if not records:
        await channel.send("ℹ️ DB에 저장된 손상 기록이 없습니다.")
        return

    await channel.send("📈 **보수 공사가 시급한 순으로 모든 손상 기록을 조회했어요**")

    for record in records:
        risk = record.urgency or "분석 중"
        color = discord.Color.red() if risk == "높음" \
                else discord.Color.yellow() if risk == "보통" \
                else discord.Color.green() if risk == "낮음" \
                else discord.Color.greyple()

        location = record.address or f"좌표: {record.latitude}, {record.longitude}"
        
        image_url = record.image
        if image_url and image_url.startswith("/data"):
            image_url = f"http://34.218.88.107:8000{image_url}"

        repair = record.repair_status or "미처리"

        embed = discord.Embed(
            title=f"📍 {location}",
            description=(
                f"🕒 **감지 시각 :** {record.detect_time}\n"
                f"🏷️ **손상 유형 :** {record.defect_type or '분석 중'}\n" 
                f"⚠️ **위험도 :** {risk}\n"
                f"🔧 **보수 상태 :** {repair}\n"
            ),
            color=color
        )
        if image_url and (image_url.startswith("http://") or image_url.startswith("https://")):
            embed.set_image(url=image_url)
            
        await channel.send(embed=embed)

    select_view = DefectSelectView(records)
    
    await channel.send(
        "🔧 특정 손상의 **상세 정보 확인/보수 상태 변경**을 원하시면 아래에서 선택하세요.",
        view=select_view
    )


async def edit_embed_repair_status(message: discord.Message, new_status: str):
    """
    주어진 메시지의 Embed에서 보수 상태를 '완료'로 변경합니다.
    """
    if not message.embeds:
        return

    embed = message.embeds[0]
    new_embed = embed.copy()

    desc = new_embed.description or ""
    lines = desc.splitlines()
    for i, line in enumerate(lines):
        if "보수 상태" in line:
            lines[i] = f"🔧 **보수 상태 :** {new_status}"
            break
    else:
        lines.append(f"🔧 **보수 상태 :** {new_status}")

    new_embed.description = "\n".join(lines)

    await message.edit(embed=new_embed)


class DefectDetailView(View):
    """
    상세 조회 화면에서 보수 상태에 따라 버튼을 활성화하고,
    버튼 클릭 시 보수 상태를 '완료'로 변경합니다. 
    """
    
    def __init__(self, record: DefectOut):
        super().__init__(timeout=600)
        self.record = record
        self.defect_id = record.id
        self._setup_buttons()

    def _setup_buttons(self):
        status = self.record.repair_status or "미처리"

        if status in ["미처리", "진행중"]:
            self.add_item(self.MakeDoneButton())

    class MakeDoneButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label="보수 공사를 완료했어요", style=discord.ButtonStyle.success)

        async def callback(self, interaction: discord.Interaction):
            view: DefectDetailView = self.view
            await view._change_status(interaction, "완료")

    async def _change_status(self, interaction: discord.Interaction, new_status: str):
        updated = await update_repair_status(self.defect_id, new_status)
        if not updated:
            await interaction.response.send_message("❌ 상태 업데이트 실패", ephemeral=True)
            return

        await edit_embed_repair_status(interaction.message, new_status)

        new_record = await get_defect_by_id(self.defect_id)
        new_view = DefectDetailView(new_record)

        await interaction.response.edit_message(view=new_view)

        await interaction.followup.send(
            f"✅ 선택한 손상의 보수 공사를 **{new_status}** 상태로 변경했습니다!"
        )


# ----- Google Calendar API 설정 -----
SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_calendar_service():
    if not os.path.exists("token.json"):
        raise RuntimeError("❌ token.json 파일이 없습니다.")
    
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    elif not creds or not creds.valid:
        raise RuntimeError("❌ token.json이 유효하지 않습니다.")

    return build('calendar', 'v3', credentials=creds)


# ----- 보수 공사 일정 추가 기능 -----
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

class DateInputModal(discord.ui.Modal, title="보수 공사 일정 입력"):
    def __init__(self, defect_id: str, image_url: str, defect_type: str, urgency: str, address: str):
        super().__init__(timeout=None)
        self.defect_id = defect_id
        self.image_url = image_url
        self.defect_type = defect_type
        self.urgency = urgency
        self.address = address

    date = discord.ui.TextInput(
        label="날짜 (YYYY-MM-DD)",
        placeholder="예: 2025-12-15",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            selected_date = datetime.datetime.strptime(self.date.value, "%Y-%m-%d").date()
        except ValueError as e:
            await interaction.response.send_message(
                f"❌ 잘못된 날짜 형식입니다. YYYY-MM-DD 형식으로 입력해주세요.",
                ephemeral=True
            )
                
        try:
            description = (
                f"🆔 {self.defect_id}\n"
                f"📍 {self.address}\n"
                f"🏷️ {self.defect_type}\n"
                f"⚠️ 위험도 {self.urgency}\n"
                f"🖼️ {self.image_url}\n\n"
                f"👤 {interaction.user.display_name}\n"
            )
            event_link = add_to_calendar(
                selected_date.isoformat(),
                f"건물 외벽 보수 공사",
                description
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ 캘린더 등록 실패: {e}", ephemeral=True)
            return

        updated = await update_repair_status(self.defect_id, "진행중")
        if not updated:
            await interaction.response.send_message(
                "⚠️ 일정은 등록됐지만 보수 상태 업데이트는 실패했습니다.",
                ephemeral=True
            )
            return
        
        await interaction.response.send_message(
            f"✅ **보수 공사 일정 확정**\n\n"
            f"{interaction.user.mention}님이 요청하신 보수 공사 일정을 **{selected_date}**에 추가했습니다.\n"
            f"해당 손상의 보수 상태가 **진행중**으로 변경되었습니다.\n\n"
            f"📅 캘린더에서 보기({event_link})\n\n"            
        )