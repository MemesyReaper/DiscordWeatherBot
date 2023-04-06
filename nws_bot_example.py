import os
import discord
from discord.ext import commands, tasks
import aiohttp
import json
from datetime import datetime, timezone, timedelta
import pytz

# Discord bot token
TOKEN = 'token'

# NWS user creditenals 
NWS_USER_AGENT = ''
NWS_API_EMAIL = ''

# Set up the bot
intents = discord.Intents.default()
intents.typing = False
intents.presences = False
bot = commands.Bot(command_prefix='!', intents=intents)

# Lists (idk/remember what these do, just stops the warning from being posted twice)
active_warnings = {}
posted_warnings = []

# Makes a warning ID to be put in list above
def get_warning_id(properties):
    issued_time = datetime.fromisoformat(properties['sent'])
    county = properties['areaDesc']
    return f'{issued_time.strftime("%Y%m%d%H%M%S")}-{county}'

# Checks if the warning is new
def is_new_warning(warning, posted_warnings):
    properties = warning['properties']
    event = properties['event']
    if event not in ["Tornado Warning"]:
        return False
    issued_time = datetime.fromisoformat(properties['sent'])
    now = datetime.now(timezone.utc)
    warning_age = now - issued_time
    if warning_age > timedelta(minutes=15):
        return False
    warning_id = get_warning_id(properties)
    return warning_id not in posted_warnings

# Fetches warnings from the NWS API
async def fetch_warnings():
    headers = {
        'User-Agent': NWS_USER_AGENT,
        'From': NWS_API_EMAIL,
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get('https://api.weather.gov/alerts/active') as response:
            if response.status == 200:
                return await response.json()

# Checks if the message is longer than 2000 characters
async def send_long_message(channel, message):
    if len(message) > 2000:
        # Split the message into chunks and send each chunk
        chunks = [message[i:i+2000] for i in range(0, len(message), 2000)]
        for chunk in chunks:
            await channel.send(chunk)
    else:
        await channel.send(message)

# Sends both the long message and short message
async def send_warnings():
    global active_warnings, posted_warnings
    channel = discord.utils.get(bot.get_all_channels(), name='nws-alerts')
    if channel:
        warnings = await fetch_warnings()
        if warnings:
            new_warnings = [warning for warning in warnings['features'] if is_new_warning(warning, posted_warnings)]
            if new_warnings:
                for warning in new_warnings:
                    properties = warning['properties']
                    warning_id = get_warning_id(properties)
                    posted_warnings.append(warning_id)
                    expiration_time = datetime.fromisoformat(properties['expires'])
                    active_warnings[warning_id] = expiration_time
                    short_warning = format_short_message(warning)
                    full_warning = f'{properties["event"]}: {properties["headline"]}\n{properties["description"]}\n{properties["instruction"]}'
                    await channel.send(short_warning, tts=True)
                    await send_long_message(channel, full_warning)
                  
            else:
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                print(f'[{now}] No new warnings found')
        else:
            print('Unable to fetch warnings')
        # Remove expired warnings
        now = datetime.now(timezone.utc)
        expired_warnings = [warning_id for warning_id, expiration_time in active_warnings.items() if now > expiration_time]
        for warning_id in expired_warnings:
            active_warnings.pop(warning_id)
            posted_warnings.remove(warning_id)


# Formats the short message
def format_short_message(warning):
    properties = warning['properties']
    event = properties['event']
    if event not in ["Tornado Warning", "Severe Thunderstorm Warning"]:
        return ''
    areas = properties['areaDesc'].split(';')
    area_list = [f'{area.strip()} County' for area in areas]
    county_list = ', '.join(area_list)
    sent_time = datetime.fromisoformat(properties['sent']).astimezone(timezone(timedelta(hours=-4))).strftime('%I:%M %p')
    expires_time = datetime.fromisoformat(properties['expires']).astimezone(timezone(timedelta(hours=-4))).strftime('%I:%M %p')
    return f'@everyone {event} for {county_list} until {expires_time} EDT. Issued at {sent_time} EDT.'

# Checks NWS API for new alerts
@tasks.loop(minutes=1)
async def check_warnings():
    await send_warnings()

# Starts bot
@bot.event
async def on_ready():
    global started_at
    started_at = datetime.now(pytz.utc)
    print(f'{bot.user} has connected to Discord!')
    check_warnings.start()

bot.run(TOKEN)
