import disnake
from disnake.ext import commands

from core.config import TOKEN, ADMIN_USER_IDS
from core.events import setup as setup_events
from core.commands import setup as setup_commands

intents = disnake.Intents.default()
intents.voice_states = True
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix='!',
    intents=intents,
    owner_ids=set(ADMIN_USER_IDS)
)

# register event/cmd handlers defined in other modules
setup_events(bot)
setup_commands(bot)

if __name__ == '__main__':
    bot.run(TOKEN)
