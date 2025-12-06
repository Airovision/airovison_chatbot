import io
import os
from urllib.parse import urlparse
import discord
from discord import app_commands
from discord.ui import View, Button
from dotenv import load_dotenv
import httpx

from llava import run_llava
from record import *
from models import *
from database import *
from io import BytesIO


# .env 로드
load_dotenv()


# ----- Discord 설정 -----
discord_key = os.getenv("DISCORD")

intents = discord.Intents.all()
intents.message_content = True
client = discord.Client(intents=intents)

CHANNEL_ID = 1427293434796048506
IMAGE_PATH = "images/sample.jpg"


# ----- 질문 목록 -----
questions = {
    1: "이미지에 나타난 손상에 대해 분석 요약해주세요",
    2: "어떤 조치가 필요할지 조언해주세요",
    3: "모든 손상 기록을 조회할게요",
    4: "캘린더에 보수 공사 일정을 추가할게요"
}

# ----- 버튼 UI 정의 -----
class QuestionView(View):
    def __init__(self, image_url: str, defect_id: str, defect_type: str, urgency: str):
        super().__init__(timeout=None)
        self.image_url = image_url
        self.defect_id = defect_id
        self.defect_type = defect_type
        self.urgency = urgency

    # Q1 버튼 - "이미지에 나타난 손상에 대해 분석 요약해주세요"
    @discord.ui.button(label=questions[1], style=discord.ButtonStyle.primary)
    async def q1(self, interaction: discord.Interaction, button: Button):
        await interaction.channel.send(f"{interaction.user.mention}님이 **[{button.label}]** 버튼을 눌렀습니다.\n")

        await interaction.response.defer(thinking=True)
        print(f"img url: {self.image_url}")
        result = await asyncio.to_thread(
            run_llava, self.image_url, questions[1], self.defect_id, self.defect_type, self.urgency
        )
        
        await interaction.followup.send(result)

    # Q2 버튼 - "어떤 조치가 필요할지 조언해주세요"
    @discord.ui.button(label=questions[2], style=discord.ButtonStyle.primary)
    async def q2(self, interaction: discord.Interaction, button: Button):
        await interaction.channel.send(f"{interaction.user.mention}님이 **[{button.label}]** 버튼을 눌렀습니다.\n")

        await interaction.response.defer(thinking=True)
        result = await asyncio.to_thread(
            run_llava, self.image_url, questions[2], self.defect_id, self.defect_type, self.urgency
        )
        
        await interaction.followup.send(result)

    # Q3 - "모든 손상 기록을 조회할게요"
    @discord.ui.button(label=questions[3], style=discord.ButtonStyle.secondary)
    async def q3(self, interaction: discord.Interaction, button: Button):
        await interaction.channel.send(f"{interaction.user.mention}님이 **[{button.label}]** 버튼을 눌렀습니다.\n")
        
        await interaction.response.defer(thinking=True)
        try:
            await get_records(interaction.channel)
        except Exception as e:
            await interaction.followup.send(f"❌ 서버 연결 오류: {e}")

    # Q4 - "캘린더에 보수 공사 일정을 추가할게요"
    @discord.ui.button(label=questions[4], style=discord.ButtonStyle.secondary)
    async def q4(self, interaction: discord.Interaction, button: Button):
        await interaction.channel.send(f"{interaction.user.mention}님이 **[{button.label}]** 버튼을 눌렀습니다.\n")

        await interaction.response.send_modal(DateInputModal(
            defect_id=self.defect_id,
            image_url=self.image_url,
            defect_type=self.defect_type,
            urgency=self.urgency,
            address = self.address
        ))


# ----- FastAPI가 호출할 알림 함수 -----
async def send_defect_alert(defect: DefectOut, llava_summary: str):
    """
    FastAPI 서버가 LLaVA 분석 후 호출하는 함수입니다.
    """

    try:
        channel = client.get_channel(CHANNEL_ID)
        if not channel:
            print(f"❌ 알림 실패: 채널(ID: {CHANNEL_ID})을 찾을 수 없음")
            return

        image_url = defect.image

        # 1) S3 URL인 경우
        if image_url.startswith("http://") or image_url.startswith("https://"):
            try:
                resp = requests.get(image_url, timeout=10)
                resp.raise_for_status()
            except requests.RequestException as e:
                print(f"❌ S3 이미지 다운로드 실패: {image_url} / {e}")
                return

            buf = BytesIO(resp.content)
            parsed = urlparse(image_url)
            filename = os.path.basename(parsed.path) or f"defect_{defect.id}.jpg"
            discord_file = discord.File(buf, filename=filename)

            view_image_url = image_url

        else:
            # 2) 로컬 경로인 경우
            image_path = "." + image_url
            discord_file = discord.File(image_path, filename=os.path.basename(image_path))
            view_image_url = image_path

        view = QuestionView(image_url=view_image_url, defect_id=defect.id, defect_type=defect.defect_type, urgency=defect.urgency)
        
        await channel.send(content=llava_summary, file=discord_file, view=view)
        print(f"✅ Discord 알림 전송 완료 (ID: {defect.id})")

    except Exception as e:
        print(f"❌ Discord 알림 전송 중 오류: {e}")


# ----- Discord 이벤트 핸들러 -----
@client.event
async def on_ready():
    print("---" * 10)
    print(f"✅ Discord 봇 로그인 완료: {client.user}")

    channel = client.get_channel(CHANNEL_ID)
    if channel:
        print(f"✅ 알림 채널 준비 완료: #{channel.name}")
    else:
        print(f"❌ 채널을 찾을 수 없습니다. CHANNEL_ID를 확인하세요.")
        
    print("---" * 10)
