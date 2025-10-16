import os
import discord
from discord.ui import View, Button
from dotenv import load_dotenv
from llava import run_llava, load_llava_model

load_dotenv()

discord_key = os.getenv("DISCORD")

intents = discord.Intents.all()
client = discord.Client(intents=intents)

CHANNEL_ID = 1427293434796048506
IMAGE_PATH = "images/sample.jpg"
ALTER_TEXT = "🚨 건물에 균열이 의심됩니다 🚨\n 이미지를 보고 아래 질문 중 하나를 선택하세요 👇"


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

        # # 버튼 1: 예
        # self.add_item(Button(label=questions[1], style=discord.ButtonStyle.primary, custom_id="kind"))
        # # 버튼 2: 아니오
        # self.add_item(Button(label=questions[2], style=discord.ButtonStyle.primary, custom_id="measure"))
        # # 버튼 3: 더 설명해줘
        # self.add_item(Button(label=questions[3], style=discord.ButtonStyle.primary, custom_id="number"))

    @discord.ui.button(label=questions[1], style=discord.ButtonStyle.primary)
    async def q1(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        result = run_llava(IMAGE_PATH, questions[1])
        await interaction.followup.send(result)

    @discord.ui.button(label=questions[2], style=discord.ButtonStyle.primary)
    async def q2(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        result = run_llava(IMAGE_PATH, questions[2])
        await interaction.followup.send(result)
    @discord.ui.button(label=questions[3], style=discord.ButtonStyle.primary)
    async def q3(self, interaction: discord.Interaction, button: Button):
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

    load_llava_model()
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

client.run(discord_key)