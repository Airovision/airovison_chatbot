import os
import discord
from dotenv import load_dotenv

load_dotenv()

discord_key = os.getenv("DISCORD")

intents = discord.Intents.all()
client = discord.Client(intents=intents)

@client.event
async def on_message(message):
    if message.content == "핑":
        await message.channel.send("퐁")

client.run(discord_key)