import json

with open('config.json', 'r', encoding='utf-8') as f:
    _cfg = json.load(f)

TOKEN = _cfg['token']
TARGET_CHANNEL_ID = _cfg['target_channel_id']
KICK_CHANNEL_ID = _cfg['kick_channel_id']
MONTHLY_QUOTA_SECONDS = _cfg['monthly_quota_minutes'] * 60
ADMIN_USER_IDS = _cfg['admin_user_ids']
LANGUAGE = _cfg['language']
EMBED_COLORS = _cfg['embed_colors']
MESSAGES = _cfg['messages'][LANGUAGE]
GIFS = _cfg['gifs']
