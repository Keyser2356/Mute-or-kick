import discord
import asyncio
import json
import sqlite3
import datetime
from discord.ext import tasks, commands

with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

TOKEN = config['token']
TARGET_CHANNEL_ID = config['target_channel_id']
KICK_CHANNEL_ID = config['kick_channel_id']
MONTHLY_QUOTA_SECONDS = config['monthly_quota_minutes'] * 60
ADMIN_USER_IDS = config['admin_user_ids']

intents = discord.Intents.default()
intents.voice_states = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

mute_timers = {}
notified_quota_exceeded = set()
status_lines = {}
mute_watchers = {}


def format_time(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}:{m:02d}:{s:02d}"

def init_database():
    conn = sqlite3.connect('mute_quota.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_quota (
            user_id INTEGER PRIMARY KEY,
            month_year TEXT,
            mute_seconds_used INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mute_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            event_type TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            mute_minutes_used INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def get_current_month_year():
    now = datetime.datetime.now()
    return f"{now.year}-{now.month:02d}"

def get_user_quota(user_id):
    conn = sqlite3.connect('mute_quota.db')
    cursor = conn.cursor()
    month_year = get_current_month_year()
    cursor.execute('SELECT mute_seconds_used FROM user_quota WHERE user_id = ? AND month_year = ?', 
                   (user_id, month_year))
    result = cursor.fetchone()
    conn.close()
    if not result:
        return 0
    seconds = result[0]
    if seconds and seconds < MONTHLY_QUOTA_SECONDS // 60:
        seconds = seconds * 60
    return seconds

def set_user_quota(user_id, mute_seconds):
    conn = sqlite3.connect('mute_quota.db')
    cursor = conn.cursor()
    month_year = get_current_month_year()
    cursor.execute('SELECT * FROM user_quota WHERE user_id = ? AND month_year = ?', 
                   (user_id, month_year))
    if cursor.fetchone():
        cursor.execute('UPDATE user_quota SET mute_seconds_used = ? WHERE user_id = ? AND month_year = ?',
                       (mute_seconds, user_id, month_year))
    else:
        cursor.execute('INSERT INTO user_quota (user_id, month_year, mute_seconds_used) VALUES (?, ?, ?)',
                       (user_id, month_year, mute_seconds))
    conn.commit()
    conn.close()

def log_mute_event(user_id, event_type, mute_minutes_used):
    conn = sqlite3.connect('mute_quota.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO mute_events (user_id, event_type, mute_minutes_used) VALUES (?, ?, ?)',
                   (user_id, event_type, mute_minutes_used))
    conn.commit()
    conn.close()

@bot.event
async def on_ready():
    print(f'Bot {bot.user} is ready!')
    init_database()
    check_mutes.start()

@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel is None:
        if member.id in mute_timers:
            start_time = mute_timers.pop(member.id, None)
            if start_time is not None:
                elapsed_secs = int((datetime.datetime.now() - start_time).total_seconds())
                current_quota = get_user_quota(member.id)
                new_quota = current_quota + elapsed_secs
                set_user_quota(member.id, new_quota)
                log_mute_event(member.id, 'unmute', new_quota)
                print(f"[VOICE EXIT] {member.name} вышел из войса | Сидел: {format_time(elapsed_secs)} | Всего квоты: {format_time(new_quota)} / {format_time(MONTHLY_QUOTA_SECONDS)}")
            notified_quota_exceeded.discard(member.id)
        else:
            print(f"[VOICE EXIT] {member.name} вышел из войса")
        status_lines.pop(member.id, None)
        return
    
    if before.channel is None:
        print(f"[VOICE JOIN] {member.name} присоединился к войсу")

    is_self_muted = (
        after.self_mute and
        not after.mute
    )

    if is_self_muted:
        current_quota = get_user_quota(member.id)
        if current_quota > MONTHLY_QUOTA_SECONDS:
            if member.id in notified_quota_exceeded:
                return
            kick_channel = bot.get_channel(KICK_CHANNEL_ID)
            if member.guild.owner_id == member.id:
                if member.id not in notified_quota_exceeded:
                    await member.send(f'Ваша квота для mute закончилась на этот месяц, но я не могу вас переместить, потому что вы владелец сервера.\nКвота: {format_time(current_quota)}/{format_time(MONTHLY_QUOTA_SECONDS)}')
                    log_mute_event(member.id, 'quota_exceeded_owner', current_quota)
                    notified_quota_exceeded.add(member.id)
                    print(f"[WARN] попытка кикнуть владельца {member.name}")
                return
            try:
                if kick_channel and isinstance(kick_channel, discord.VoiceChannel):
                    await member.move_to(kick_channel)
                    await asyncio.sleep(1)
                    if member.id not in notified_quota_exceeded:
                        await member.send(f'Ваша квота для mute закончилась на этот месяц.\nКвота: {format_time(current_quota)}/{format_time(MONTHLY_QUOTA_SECONDS)}')
                        log_mute_event(member.id, 'quota_exceeded', current_quota)
                        notified_quota_exceeded.add(member.id)
                        print(f"[KICK] {member.name} кикнут по квоте при попытке mutе!")
            except discord.Forbidden:
                print(f"[ERROR] Нет прав для перемещения {member.name}")
            except Exception as e:
                print(f"[ERROR] Ошибка: {e}")
            return

        if member.id not in mute_timers:
            mute_timers[member.id] = datetime.datetime.now()
            log_mute_event(member.id, 'mute', current_quota)
            print(f"[MUTE START] {member.name} замьютился | Уже использовано: {format_time(current_quota)} / {format_time(MONTHLY_QUOTA_SECONDS)}")
            async def watcher(uid, guild):
                remaining = MONTHLY_QUOTA_SECONDS - get_user_quota(uid)
                if remaining > 0:
                    await asyncio.sleep(remaining)
                if uid in mute_timers:
                    mem = guild.get_member(uid)
                    if mem and mem.voice and mem.voice.channel:
                        try:
                            await mem.move_to(bot.get_channel(KICK_CHANNEL_ID))
                            await asyncio.sleep(1)
                            if uid not in notified_quota_exceeded:
                                await mem.send(f'Ваша квота для mute закончилась на этот месяц.\nКвота: {format_time(MONTHLY_QUOTA_SECONDS)}/{format_time(MONTHLY_QUOTA_SECONDS)}')
                                set_user_quota(uid, MONTHLY_QUOTA_SECONDS)
                                log_mute_event(uid, 'quota_exceeded', MONTHLY_QUOTA_SECONDS)
                                notified_quota_exceeded.add(uid)
                                print(f"[KICK] {mem.name} кикнут по квоте (watcher)!")
                            mute_timers.pop(uid, None)
                        except Exception as e:
                            print(f"[WATCHER ERROR] {e}")
            mute_watchers[member.id] = asyncio.create_task(watcher(member.id, member.guild))
    else:
        if member.id in mute_timers:
            start_time = mute_timers[member.id]
            elapsed_secs = int((datetime.datetime.now() - start_time).total_seconds())
            current_quota = get_user_quota(member.id)
            new_quota = current_quota + elapsed_secs
            set_user_quota(member.id, new_quota)
            log_mute_event(member.id, 'unmute', new_quota)
            print(f"[MUTE END] {member.name} анмьютился | Сидел: {format_time(elapsed_secs)} | Всего квоты: {format_time(new_quota)} / {format_time(MONTHLY_QUOTA_SECONDS)}")
            if new_quota >= MONTHLY_QUOTA_SECONDS and member.voice and member.voice.channel:
                try:
                    kick_channel = bot.get_channel(KICK_CHANNEL_ID)
                    if kick_channel and isinstance(kick_channel, discord.VoiceChannel):
                        await member.move_to(kick_channel)
                        if member.id not in notified_quota_exceeded:
                            await member.send(f'Ваша квота для mute закончилась на этот месяц.\nКвота: {format_time(new_quota)}/{format_time(MONTHLY_QUOTA_SECONDS)}')
                            log_mute_event(member.id, 'quota_exceeded', new_quota)
                            notified_quota_exceeded.add(member.id)
                            print(f"[KICK] {member.name} кикнут после анмута по квоте!")
                except Exception as e:
                    print(f"[ERROR] не удалось кикнуть {member.name} после анмута: {e}")
            mute_timers.pop(member.id, None)
            if member.id in mute_watchers:
                mute_watchers[member.id].cancel()
                mute_watchers.pop(member.id, None)

@tasks.loop(seconds=10)
async def check_mutes():
    now = datetime.datetime.now()
    to_remove = []
    target_channel = bot.get_channel(TARGET_CHANNEL_ID)
    kick_channel = bot.get_channel(KICK_CHANNEL_ID)
    
    if not target_channel or not isinstance(target_channel, discord.VoiceChannel):
        return
    if not kick_channel or not isinstance(kick_channel, discord.VoiceChannel):
        return

    for user_id, start_time in list(mute_timers.items()):
        elapsed_total = (now - start_time).total_seconds()
        elapsed_seconds = int(elapsed_total)
        current_quota = get_user_quota(user_id)
        total_used = current_quota + elapsed_seconds
        
        member = target_channel.guild.get_member(user_id)
        username = member.name if member else f"User {user_id}"
        
        print(f"[MUTE] {username}: {format_time(elapsed_seconds)} / {format_time(MONTHLY_QUOTA_SECONDS)} | Квота: {format_time(total_used)} / {format_time(MONTHLY_QUOTA_SECONDS)}")
        
        if total_used >= MONTHLY_QUOTA_SECONDS:
            if user_id in notified_quota_exceeded:
                to_remove.append(user_id)
            elif member and member.voice and member.voice.channel:
                if member.guild.owner_id == user_id:
                    print(f"[WARN] Нельзя переместить владельца сервера ({username}); квота всё равно считается")
                    if user_id not in notified_quota_exceeded:
                        await member.send(f'Ваша квота для mute закончилась на этот месяц, но я не могу вас переместить, потому что вы владелец сервера.\nКвота: {format_time(MONTHLY_QUOTA_SECONDS)}/{format_time(MONTHLY_QUOTA_SECONDS)}')
                        set_user_quota(user_id, MONTHLY_QUOTA_SECONDS)
                        log_mute_event(user_id, 'quota_exceeded_owner', MONTHLY_QUOTA_SECONDS)
                        notified_quota_exceeded.add(user_id)
                else:
                    try:
                        await member.move_to(kick_channel)
                        await asyncio.sleep(1)
                        if user_id not in notified_quota_exceeded:
                            await member.send(f'Ваша квота для mute закончилась на этот месяц.\nКвота: {format_time(MONTHLY_QUOTA_SECONDS)}/{format_time(MONTHLY_QUOTA_SECONDS)}')
                            set_user_quota(user_id, MONTHLY_QUOTA_SECONDS)
                            log_mute_event(user_id, 'quota_exceeded', MONTHLY_QUOTA_SECONDS)
                            notified_quota_exceeded.add(user_id)
                            print(f"[KICK] {username} кикнут по квоте!")
                        to_remove.append(user_id)
                    except discord.Forbidden:
                        print(f"[ERROR] Нет прав для перемещения {username}")
                        to_remove.append(user_id)
                    except discord.HTTPException as e:
                        if hasattr(e, 'status') and e.status == 429:
                            print(f"[RATE] rate-limited при перемещении {username}: {e}; попробую позже")
                        else:
                            print(f"[ERROR] HTTP ошибка при перемещении {username}: {e}")
                            to_remove.append(user_id)
                    except Exception as e:
                        print(f"[ERROR] Ошибка при перемещении {username}: {e}")
                        to_remove.append(user_id)

    for user_id in to_remove:
        if user_id in mute_timers:
            mute_timers.pop(user_id, None)
            if user_id in mute_watchers:
                mute_watchers[user_id].cancel()
                mute_watchers.pop(user_id, None)

@bot.command(name='resetquota')
async def reset_quota(ctx, user: discord.User):
    if ctx.author.id not in ADMIN_USER_IDS:
        await ctx.send('❌ У вас нет прав для использования этой команды')
        return
    
    set_user_quota(user.id, 0)
    notified_quota_exceeded.discard(user.id)
    await ctx.send(f'✅ Квота пользователя {user.mention} сброшена на 0:00:00')

@bot.command(name='addquota')
async def add_quota(ctx, user: discord.User, minutes: int):
    if ctx.author.id not in ADMIN_USER_IDS:
        await ctx.send('❌ У вас нет прав для использования этой команды')
        return
    
    add_seconds = minutes * 60
    current_quota = get_user_quota(user.id)
    new_quota = current_quota + add_seconds
    set_user_quota(user.id, new_quota)
    log_mute_event(user.id, 'admin_add', new_quota)
    await ctx.send(f'<a:check_yes:1092334850410807326> Добавлено {minutes} минут пользователю {user.mention}\nТекущая квота: {format_time(new_quota)}/{format_time(MONTHLY_QUOTA_SECONDS)}')

@bot.command(name='checkquota')
async def check_quota(ctx, user: discord.User = None):
    target_user = user if user else ctx.author
    used = get_user_quota(target_user.id)
    if target_user.id in mute_timers:
        elapsed = int((datetime.datetime.now() - mute_timers[target_user.id]).total_seconds())
        used += elapsed
    total = MONTHLY_QUOTA_SECONDS
    await ctx.send(f'Квота {target_user.mention}: {format_time(used)}/{format_time(total)}')

bot.run(TOKEN)
