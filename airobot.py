import os
import discord
from discord import app_commands
from discord.ui import View, Button
from dotenv import load_dotenv
from llava import run_llava, load_llava_model

load_dotenv()

discord_key = os.getenv("DISCORD")

intents = discord.Intents.all()
intents.message_content = True
client = discord.Client(intents=intents)

CHANNEL_ID = 1427293434796048506
IMAGE_PATH = "images/sample.jpg"
ALTER_TEXT = "⚠️ 손상 감지 ⚠️\n" \
"새로운 외벽 손상이 탐지되었습니다. 아래의 정보를 확인하세요.\n" \
"📍 위치    : 인천 미추홀구 인하로 100, 인하대학교용현캠퍼스 하이테크센터\n" \
"🕒 감지 시각: 2025-10-13 10:24 AM\n" \
"🏷️ 손상 유형: 콘크리트 균열\n" \
"🧠 분석 요약: 창문 왼편에 균열이 의심됩니다. 또한 페인트 벗겨짐 등 일부 손상도 확인됩니다. "


# 질문 목록 정리
questions = {
    1: "이미지에 나타난 손상의 종류는 무엇인가요?",
    2: "건물의 손상 정도를 측정할 수 있나요?",
    3: "이 손상은 얼마나 위험한가요? (1~10 단계로 평가)"
}

# ✅ 버튼 UI 정의
class QuestionView(View):
    def __init__(self):
        super().__init__(timeout=None)


    @discord.ui.button(label=questions[1], style=discord.ButtonStyle.primary) # 첫번째 질문 버튼
    async def q1(self, interaction: discord.Interaction, button: Button):
        await interaction.channel.send( # 어떤 버튼 눌렀는지 알림
        f"{interaction.user.mention}님이 **[{button.label}]** 버튼을 눌렀습니다.\n")

        await interaction.response.defer(thinking=True, ephemeral=True) # 3초가 지나도 상호작용하게끔 thinkin=True
        result = run_llava(IMAGE_PATH, questions[1]) # 라바에 해당 질문 넣기

        await interaction.followup.send(result)

    @discord.ui.button(label=questions[2], style=discord.ButtonStyle.primary) # 두번째 질문 버튼
    async def q2(self, interaction: discord.Interaction, button: Button):
        await interaction.channel.send(
        f"{interaction.user.mention}님이 **[{button.label}]** 버튼을 눌렀습니다.\n")

        await interaction.response.defer(thinking=True, ephemeral=True)
        result = run_llava(IMAGE_PATH, questions[2])

        await interaction.followup.send(result)

    @discord.ui.button(label=questions[3], style=discord.ButtonStyle.primary) # 세번째 질문 버튼
    async def q3(self, interaction: discord.Interaction, button: Button):
        await interaction.channel.send(
        f"{interaction.user.mention}님이 **[{button.label}]** 버튼을 눌렀습니다.\n")

        await interaction.response.defer(thinking=True, ephemeral=True)
        result = run_llava(IMAGE_PATH, questions[3])

        await interaction.followup.send(result)


@client.event
async def on_ready():
    print(f"✅ 로그인 완료: {client.user}")
    channel = client.get_channel(CHANNEL_ID)

    if channel is None:
        print("❌ 채널을 찾을 수 없습니다. CHANNEL_ID를 확인하세요.")
        return
    

    load_llava_model() # 처음 시작할 때 모델 로드

    # 이미지 파일이 존재하면 전송
    if os.path.exists(IMAGE_PATH):
        view = QuestionView()
        file = discord.File(IMAGE_PATH, filename=os.path.basename(IMAGE_PATH))
        await channel.send(content=f"{ALTER_TEXT}", file=file, view=view)
    else:
        await channel.send(f"**질문:** {ALTER_TEXT}\n(⚠️ 이미지 파일을 찾을 수 없습니다: {IMAGE_PATH})")

client.run(discord_key)


# test code
# @client.event
# async def on_message(message):
#     if message.content == "핑":
#         await message.channel.send("퐁")
