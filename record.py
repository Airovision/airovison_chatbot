import os
import discord
import requests
import asyncio
from discord import app_commands, SelectOption, Embed
from discord.ui import View, Button, Select
import datetime


# AWS API 조회 기능
async def get_records(channel: discord.TextChannel):
    # [가상 DB 데이터 - 실제는 AWS RDS에서 조회]
    records = [
        {"id": 1, "type": "콘크리트 균열", "location": "하이테크 센터 3층", "time": "2025-10-13 10:24", "risk": "높음", "image_url": "https://www.sciencetimes.co.kr/jnrepo/uploads//2018/02/n-ethicsalarms.jpg"},
        {"id": 2, "type": "콘크리트 박리", "location": "본관 1층 모서리", "time": "2025-10-10 14:00", "risk": "낮음", "image_url": "https://samhwa.com/app/uploads/2022/11/defect_view_12_01.jpg"},
        {"id": 3, "type": "누수 흔적", "location": "학생회관 2층", "time": "2025-10-05 09:30", "risk": "중간", "image_url": "https://octapi.lxzin.com/imageBlockProp/image/202506/18/720/0/a1f71cde-4048-4dbd-a5f6-9bfb63ef7f7b.png"},
        {"id": 4, "type": "철근 노출", "location": "본관 2층 복도", "time": "2025-10-12 11:15", "risk": "중간", "image_url": "https://image.chosun.com/sitedata/image/202307/07/2023070701225_0.jpg"},
        {"id": 5, "type": "강재 손상", "location": "학생회관 1층 외벽", "time": "2025-10-08 09:45", "risk": "높음", "image_url": "https://www.shutterstock.com/image-photo/rusty-weathered-concrete-wall-peeling-260nw-2646950607.jpg"},
        {"id": 6, "type": "도장 손상", "location": "2호관 북쪽 외벽", "time": "2025-10-11 14:30", "risk": "높음", "image_url": "https://www.phiko.kr/data/file/z4_03/3743920070_k4YofaRs_d4637ad3df60465f3605cdf201cff7e62a5ebba6.jpeg"}
    ]

    risk_order = {"높음": 3, "중간": 2, "낮음": 1}
    records.sort(key=lambda r: (-risk_order.get(r["risk"], 0), r["time"]))
    
    await channel.send("📈 **보수 공사가 시급한 순으로 모든 손상 기록을 조회했어요\n**")

    for record in records:
        color = discord.Color.red() if record["risk"] == "높음" \
                else discord.Color.yellow() if record["risk"] == "중간" \
                else discord.Color.green()

        embed = discord.Embed(
            title=f"📍 {record['location']}",
            description=(                
                f"🕒 **감지 시각 :** {record['time']}\n"
                f"🏷️ **손상 유형 :** {record['type']}\n"
                f"⚠️ **위험도 :** {record['risk']}\n"
            ),
            color=color
        )

        embed.set_image(url=record["image_url"])
        await channel.send(embed=embed)

# 캘린더 일정 추가
class ScheduleSelect(Select):
    def __init__(self):
        # 오늘 날짜를 기준으로 향후 30일의 옵션을 생성
        today = datetime.date.today()
        options = []

        for i in range(1, 31):
            date = today + datetime.timedelta(days = i)
            formatted_date = date.strftime("%Y년 %m월 %d일")
            options.append(SelectOption(label=f"{formatted_date}", value=date.isoformat()))
        
        super().__init__(placeholder="보수 공사를 희망하는 일자를 선택하세요.", 
                         min_values=1, max_values=1, options=options, custom_id="select_schedule")

    async def callback(self, interaction: discord.Interaction):
        selected_date = self.values[0]

        await interaction.response.edit_message(
            content=f"✅ **[보수 공사 일정 확정]**\n\n"
                    f"{interaction.user.mention}님이 요청하신 일자 **{selected_date}**로 보수 공사 일정이 추가되었습니다.\n"
                    f"상세 보수 내용은 관리자 캘린더를 확인하십시오.",
            view=None
        )

class ScheduleView(View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(ScheduleSelect())
