import disnake
import datetime

from core.config import EMBED_COLORS, GIFS, MESSAGES


def create_embed(title: str, description: str, color_key: str = 'info', gif_key: str = None) -> disnake.Embed:
    embed = disnake.Embed(
        title=title,
        description=description,
        color=EMBED_COLORS[color_key],
        timestamp=datetime.datetime.now()
    )
    if gif_key and gif_key in GIFS:
        embed.set_image(url=GIFS[gif_key])
    embed.set_footer(text="Mute Quota Bot")
    return embed


def format_time(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}:{m:02d}:{s:02d}"
