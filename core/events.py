import disnake
import asyncio
import datetime
from disnake.ext import tasks

from core.config import TARGET_CHANNEL_ID, KICK_CHANNEL_ID, MONTHLY_QUOTA_SECONDS, MESSAGES
from core.utils import create_embed, format_time
from core.db import get_user_quota, set_user_quota, log_mute_event, init_database
from core.state import mute_timers, notified_quota_exceeded, status_lines, mute_watchers


def setup(bot: disnake.ext.commands.Bot):
    @bot.event
    async def on_ready():
        print(f'Bot {bot.user} is ready!')
        init_database()
        check_mutes.start()

    @bot.event
    async def on_voice_state_update(member, before, after):
        key = (member.guild.id, member.id)
        if after.channel is None:
            if key in mute_timers:
                start_time = mute_timers.pop(key, None)
                if start_time is not None:
                    elapsed_secs = int((datetime.datetime.now() - start_time).total_seconds())
                    current_quota = get_user_quota(member.id, member.guild.id)
                    new_quota = current_quota + elapsed_secs
                    set_user_quota(member.id, member.guild.id, new_quota)
                    log_mute_event(member.id, member.guild.id, 'unmute', new_quota)
                    print(f"[VOICE EXIT] {member.name} вышел из войса | Сидел: {format_time(elapsed_secs)} | Всего квоты: {format_time(new_quota)} / {format_time(MONTHLY_QUOTA_SECONDS)}")
                notified_quota_exceeded.discard(key)
            else:
                print(f"[VOICE EXIT] {member.name} вышел из войса")
            status_lines.pop(key, None)
            return

        if before.channel is None:
            print(f"[VOICE JOIN] {member.name} присоединился к войсу")

        is_self_muted = (
            after.self_mute and
            not after.mute
        )

        if is_self_muted:
            current_quota = get_user_quota(member.id, member.guild.id)
            if current_quota > MONTHLY_QUOTA_SECONDS:
                if key in notified_quota_exceeded:
                    return
                kick_channel = bot.get_channel(KICK_CHANNEL_ID)
                if member.guild.owner_id == member.id:
                    if key not in notified_quota_exceeded:
                        embed = create_embed(MESSAGES['quota_exceeded_owner_title'], MESSAGES['quota_exceeded_owner_desc'].format(quota=format_time(current_quota), total=format_time(MONTHLY_QUOTA_SECONDS)), 'warning', 'error')
                        await member.send(embed=embed)
                        log_mute_event(member.id, member.guild.id, 'quota_exceeded_owner', current_quota)
                        notified_quota_exceeded.add(key)
                        print(f"[WARN] попытка кикнуть владельца {member.name}")
                    return
                try:
                    if kick_channel and isinstance(kick_channel, disnake.VoiceChannel):
                        await member.move_to(kick_channel)
                        await asyncio.sleep(1)
                        if key not in notified_quota_exceeded:
                            embed = create_embed(MESSAGES['quota_exceeded_title'], MESSAGES['quota_exceeded_desc'].format(quota=format_time(current_quota), total=format_time(MONTHLY_QUOTA_SECONDS)), 'error', 'quota_exceeded')
                            await member.send(embed=embed)
                            log_mute_event(member.id, member.guild.id, 'quota_exceeded', current_quota)
                            notified_quota_exceeded.add(key)
                            print(f"[KICK] {member.name} кикнут по квоте при попытке mutе!")
                except disnake.Forbidden:
                    print(f"[ERROR] Нет прав для перемещения {member.name}")
                except Exception as e:
                    print(f"[ERROR] Ошибка: {e}")
                return

            if member.id not in mute_timers:
                mute_timers[key] = datetime.datetime.now()
                log_mute_event(member.id, member.guild.id, 'mute', current_quota)
                print(f"[MUTE START] {member.name} замьютился | Уже использовано: {format_time(current_quota)} / {format_time(MONTHLY_QUOTA_SECONDS)}")

                async def watcher(uid, guild, guild_id):
                    remaining = MONTHLY_QUOTA_SECONDS - get_user_quota(uid, guild_id)
                    if remaining > 0:
                        await asyncio.sleep(remaining)
                    muted_key = (guild_id, uid)
                    if muted_key in mute_timers:
                        mem = guild.get_member(uid)
                        if mem and mem.voice and mem.voice.channel:
                            try:
                                await mem.move_to(bot.get_channel(KICK_CHANNEL_ID))
                                await asyncio.sleep(1)
                                if muted_key not in notified_quota_exceeded:
                                    embed = create_embed(MESSAGES['quota_exceeded_title'], MESSAGES['quota_exceeded_desc'].format(quota=format_time(MONTHLY_QUOTA_SECONDS), total=format_time(MONTHLY_QUOTA_SECONDS)), 'error', 'quota_exceeded')
                                    await mem.send(embed=embed)
                                    set_user_quota(uid, guild_id, MONTHLY_QUOTA_SECONDS)
                                    log_mute_event(uid, guild_id, 'quota_exceeded', MONTHLY_QUOTA_SECONDS)
                                    notified_quota_exceeded.add(muted_key)
                                    print(f"[KICK] {mem.name} кикнут по квоте (watcher)!")
                                mute_timers.pop(muted_key, None)
                            except Exception as e:
                                print(f"[WATCHER ERROR] {e}")
                mute_watchers[key] = asyncio.create_task(watcher(member.id, member.guild, member.guild.id))
        else:
            if key in mute_timers:
                start_time = mute_timers[key]
                elapsed_secs = int((datetime.datetime.now() - start_time).total_seconds())
                current_quota = get_user_quota(member.id, member.guild.id)
                new_quota = current_quota + elapsed_secs
                set_user_quota(member.id, member.guild.id, new_quota)
                log_mute_event(member.id, member.guild.id, 'unmute', new_quota)
                print(f"[MUTE END] {member.name} анмьютился | Сидел: {format_time(elapsed_secs)} | Всего квоты: {format_time(new_quota)} / {format_time(MONTHLY_QUOTA_SECONDS)}")
                if new_quota >= MONTHLY_QUOTA_SECONDS and member.voice and member.voice.channel:
                    try:
                        kick_channel = bot.get_channel(KICK_CHANNEL_ID)
                        if kick_channel and isinstance(kick_channel, disnake.VoiceChannel):
                            await member.move_to(kick_channel)
                            if key not in notified_quota_exceeded:
                                await member.send(f'Ваша квота для mute закончилась на этот месяц.\nКвота: {format_time(new_quota)}/{format_time(MONTHLY_QUOTA_SECONDS)}')
                                log_mute_event(member.id, member.guild.id, 'quota_exceeded', new_quota)
                                notified_quota_exceeded.add(key)
                                print(f"[KICK] {member.name} кикнут после анмута по квоте!")
                    except Exception as e:
                        print(f"[ERROR] не удалось кикнуть {member.name} после анмута: {e}")
                mute_timers.pop(key, None)
                if key in mute_watchers:
                    mute_watchers[key].cancel()
                    mute_watchers.pop(key, None)

    @tasks.loop(seconds=10)
    async def check_mutes():
        now = datetime.datetime.now()
        to_remove = []
        target_channel = bot.get_channel(TARGET_CHANNEL_ID)
        kick_channel = bot.get_channel(KICK_CHANNEL_ID)
        
        if not target_channel or not isinstance(target_channel, disnake.VoiceChannel):
            return
        if not kick_channel or not isinstance(kick_channel, disnake.VoiceChannel):
            return

        for key, start_time in list(mute_timers.items()):
            guild_id, user_id = key
            if guild_id != target_channel.guild.id:
                continue
            elapsed_total = (now - start_time).total_seconds()
            elapsed_seconds = int(elapsed_total)
            current_quota = get_user_quota(user_id, guild_id)
            total_used = current_quota + elapsed_seconds
            
            member = target_channel.guild.get_member(user_id)
            username = member.name if member else f"User {user_id}"
            
            print(f"[MUTE] {username}: {format_time(elapsed_seconds)} / {format_time(MONTHLY_QUOTA_SECONDS)} | Квота: {format_time(total_used)} / {format_time(MONTHLY_QUOTA_SECONDS)}")
            
            if total_used >= MONTHLY_QUOTA_SECONDS:
                if key in notified_quota_exceeded:
                    to_remove.append(key)
                elif member and member.voice and member.voice.channel:
                    if member.guild.owner_id == user_id:
                        print(f"[WARN] Нельзя переместить владельца сервера ({username}); квота всё равно считается")
                        if key not in notified_quota_exceeded:
                            embed = create_embed(MESSAGES['quota_exceeded_owner_title'], MESSAGES['quota_exceeded_owner_desc'].format(quota=format_time(MONTHLY_QUOTA_SECONDS), total=format_time(MONTHLY_QUOTA_SECONDS)), 'warning', 'error')
                            await member.send(embed=embed)
                            set_user_quota(user_id, guild_id, MONTHLY_QUOTA_SECONDS)
                            log_mute_event(user_id, guild_id, 'quota_exceeded_owner', MONTHLY_QUOTA_SECONDS)
                            notified_quota_exceeded.add(key)
                    else:
                        try:
                            await member.move_to(kick_channel)
                            await asyncio.sleep(1)
                            if key not in notified_quota_exceeded:
                                embed = create_embed(MESSAGES['quota_exceeded_title'], MESSAGES['quota_exceeded_desc'].format(quota=format_time(MONTHLY_QUOTA_SECONDS), total=format_time(MONTHLY_QUOTA_SECONDS)), 'error', 'quota_exceeded')
                                await member.send(embed=embed)
                                set_user_quota(user_id, guild_id, MONTHLY_QUOTA_SECONDS)
                                log_mute_event(user_id, guild_id, 'quota_exceeded', MONTHLY_QUOTA_SECONDS)
                                notified_quota_exceeded.add(key)
                                print(f"[KICK] {username} кикнут по квоте!")
                            to_remove.append(key)
                        except disnake.Forbidden:
                            print(f"[ERROR] Нет прав для перемещения {username}")
                            to_remove.append(key)
                        except disnake.HTTPException as e:
                            if hasattr(e, 'status') and e.status == 429:
                                print(f"[RATE] rate-limited при перемещении {username}: {e}; попробую позже")
                            else:
                                print(f"[ERROR] HTTP ошибка при перемещении {username}: {e}")
                                to_remove.append(key)
                        except Exception as e:
                            print(f"[ERROR] Ошибка при перемещении {username}: {e}")
                            to_remove.append(key)

        for key in to_remove:
            if key in mute_timers:
                mute_timers.pop(key, None)
                if key in mute_watchers:
                    mute_watchers[key].cancel()
                    mute_watchers.pop(key, None)
