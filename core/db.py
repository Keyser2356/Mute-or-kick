import sqlite3
import datetime

from core.config import MONTHLY_QUOTA_SECONDS


def init_database():
    conn = sqlite3.connect('mute_quota.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_quota (
            guild_id INTEGER,
            user_id INTEGER,
            month_year TEXT,
            mute_seconds_used INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id, month_year)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mute_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
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


def get_user_quota(user_id, guild_id):
    conn = sqlite3.connect('mute_quota.db')
    cursor = conn.cursor()
    month_year = get_current_month_year()
    cursor.execute('SELECT mute_seconds_used FROM user_quota WHERE user_id = ? AND guild_id = ? AND month_year = ?',
                   (user_id, guild_id, month_year))
    result = cursor.fetchone()
    conn.close()
    if not result:
        return 0
    seconds = result[0]
    # in case the value is stored as minutes in older versions
    if seconds and seconds < MONTHLY_QUOTA_SECONDS // 60:
        seconds = seconds * 60
    return seconds


def set_user_quota(user_id, guild_id, mute_seconds):
    conn = sqlite3.connect('mute_quota.db')
    cursor = conn.cursor()
    month_year = get_current_month_year()
    cursor.execute('SELECT * FROM user_quota WHERE user_id = ? AND guild_id = ? AND month_year = ?',
                   (user_id, guild_id, month_year))
    if cursor.fetchone():
        cursor.execute('UPDATE user_quota SET mute_seconds_used = ? WHERE user_id = ? AND guild_id = ? AND month_year = ?',
                       (mute_seconds, user_id, guild_id, month_year))
    else:
        cursor.execute('INSERT INTO user_quota (guild_id, user_id, month_year, mute_seconds_used) VALUES (?, ?, ?, ?)',
                       (guild_id, user_id, month_year, mute_seconds))
    conn.commit()
    conn.close()


def log_mute_event(user_id, guild_id, event_type, mute_minutes_used):
    conn = sqlite3.connect('mute_quota.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO mute_events (guild_id, user_id, event_type, mute_minutes_used) VALUES (?, ?, ?, ?)',
                   (guild_id, user_id, event_type, mute_minutes_used))
    conn.commit()
    conn.close()
