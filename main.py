import os
import discord
from dotenv import load_dotenv

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