import io
import os
import discord
from discord import app_commands
from discord.ui import View, Button
from dotenv import load_dotenv
import httpx


from llava import run_llava
from record import *
from models import *
from database import *

load_dotenv() # .env 파일의 환경변수 가져오기


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
    2: "어떤 조치가 필요할지 조언이 필요해요",
    3: "모든 손상 기록을 조회할게요",
    4: "캘린더에 보수 공사 일정을 추가할게요"
}

# 버튼 UI 정의
class QuestionView(View):
    def __init__(self, image_url: str, defect_id: str):
        super().__init__(timeout=None)
        self.image_url = image_url
        self.defect_id = defect_id
        # (참고) self.defect_id를 사용해 LLaVA 분석 결과를 DB에 PATCH할 수 있음


    @discord.ui.button(label=questions[1], style=discord.ButtonStyle.primary) # 첫번째 질문 버튼
    async def q1(self, interaction: discord.Interaction, button: Button):
        await interaction.channel.send( # 어떤 버튼 눌렀는지 알림
        f"{interaction.user.mention}님이 **[{button.label}]** 버튼을 눌렀습니다.\n")

        await interaction.response.defer(thinking=True, ephemeral=True) # 3초가 지나도 상호작용하게끔 thinking=True
        print(f"img url: {self.image_url}")
        result = run_llava(self.image_url, questions[1])
        # result = await asyncio.to_thread(
        #     run_llava, self.image_url, questions[1]
        # )
        
        await interaction.followup.send(result)


    @discord.ui.button(label=questions[2], style=discord.ButtonStyle.primary) # 세번째 질문 버튼
    async def q3(self, interaction: discord.Interaction, button: Button):
        await interaction.channel.send(
        f"{interaction.user.mention}님이 **[{button.label}]** 버튼을 눌렀습니다.\n")

        await interaction.response.defer(thinking=True, ephemeral=True)
        result = await asyncio.to_thread(
            run_llava, self.image_url, questions[2]
        )
        
        await interaction.followup.send(result)

    @discord.ui.button(label=questions[3], style=discord.ButtonStyle.secondary)
    async def q4(self, interaction: discord.Interaction, button: Button):
        await interaction.channel.send(f"{interaction.user.mention}님이 **[{button.label}]** 버튼을 눌렀습니다.\n")
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            await get_records(interaction.channel)
        except Exception as e:
            await interaction.followup.send(f"❌ 서버 연결 오류: {e}")

    @discord.ui.button(label=questions[4], style=discord.ButtonStyle.secondary)
    async def q5(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(DateInputModal())


# ----- FastAPI가 호출할 알림 함수 -----
async def send_defect_alert(defect: DefectOut, llava_summary: str):
    """
    FastAPI 서버가 LLaVA 분석 후 호출하는 함수
    """
    try:
        channel = client.get_channel(CHANNEL_ID)
        if not channel:
            print(f"❌ 알림 실패: 채널(ID: {CHANNEL_ID})을 찾을 수 없음")
            return

        image_path = "." + defect.image
        discord_file = discord.File(image_path, filename=os.path.basename(image_path))

        # 2. ⭐️ [수정] 동적 View 생성
        view = QuestionView(image_url=image_path, defect_id=defect.id)
        

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
