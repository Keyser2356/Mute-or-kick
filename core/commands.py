import disnake
from disnake.ext import commands
import datetime

from core.config import ADMIN_USER_IDS, MESSAGES, MONTHLY_QUOTA_SECONDS
from core.db import get_user_quota, set_user_quota, log_mute_event
from core.utils import create_embed, format_time
from core.state import mute_timers, notified_quota_exceeded


def setup(bot: commands.Bot):
    @bot.slash_command(name='resetquota', description='Сбросить квоту мута пользователю (только для админов)')
    async def reset_quota(inter: disnake.ApplicationCommandInteraction, user: disnake.User):
        if inter.author.id not in ADMIN_USER_IDS:
            embed = create_embed(MESSAGES['no_permission_title'], MESSAGES['no_permission_desc'], 'error')
            await inter.response.send_message(embed=embed, ephemeral=True)
            return
        
        set_user_quota(user.id, inter.guild_id, 0)
        notified_quota_exceeded.discard((inter.guild_id, user.id))
        embed = create_embed(MESSAGES['reset_success_title'], MESSAGES['reset_success_desc'].format(user=user.mention), 'success')
        await inter.response.send_message(embed=embed, ephemeral=True)

    @bot.slash_command(name='addquota', description='Добавить минуты к квоте мута (только для админов)')
    async def add_quota(inter: disnake.ApplicationCommandInteraction, user: disnake.User, minutes: int):
        if inter.author.id not in ADMIN_USER_IDS:
            embed = create_embed(MESSAGES['no_permission_title'], MESSAGES['no_permission_desc'], 'error')
            await inter.response.send_message(embed=embed, ephemeral=True)
            return
        
        add_seconds = minutes * 60
        current_quota = get_user_quota(user.id, inter.guild_id)
        new_quota = current_quota + add_seconds
        set_user_quota(user.id, inter.guild_id, new_quota)
        log_mute_event(user.id, inter.guild_id, 'admin_add', new_quota)
        embed = create_embed(MESSAGES['add_success_title'], MESSAGES['add_success_desc'].format(user=user.mention, minutes=minutes, quota=format_time(new_quota), total=format_time(MONTHLY_QUOTA_SECONDS)), 'success')
        await inter.response.send_message(embed=embed, ephemeral=True)

    @bot.slash_command(name='checkquota', description='Проверить вашу квоту мута')
    async def check_quota(inter: disnake.ApplicationCommandInteraction, user: disnake.User = None):
        target_user = user if user else inter.author
        used = get_user_quota(target_user.id, inter.guild_id)
        key = (inter.guild_id, target_user.id)
        if key in mute_timers:
            elapsed = int((datetime.datetime.now() - mute_timers[key]).total_seconds())
            used += elapsed
        total = MONTHLY_QUOTA_SECONDS
        embed = create_embed(MESSAGES['check_quota_title'], MESSAGES['check_quota_desc'].format(user=target_user.mention, quota=format_time(used), total=format_time(total)), 'info')
        await inter.response.send_message(embed=embed, ephemeral=True)
