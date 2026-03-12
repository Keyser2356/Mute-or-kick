<p align="center">
  <h1 align="center">Mute Limiter</h1>
  <p align="center">
    <b>"Your AFK time is a privilege, not a right."</b><br>
    A bot that tracks monthly mute quotas and revokes the ability to sit with a muted mic once the limit is exceeded.
  </p>

  <p align="center">
    <a href="https://docs.betterdiscord.app/plugins/"><img src="https://img.shields.io/badge/BetterDiscord-Compatible-7289da?style=for-the-badge&logo=discord&logoColor=white" alt="Better Discord - dev.guide"></a>
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54" alt="Python"></a>
    <a href="https://github.com/Keyser2356/Mute-or-kick/stargazers"><img src="https://img.shields.io/github/stars/Keyser2356/Mute-or-kick?style=for-the-badge&color=yellow" alt="Stars"></a>
  </p>
</p>

---

### ✨ What does this bot do?

When a member exceeds their **monthly mute quota** (configured by server admins), the bot:

1. **Identifies** the violator.
2. **Move** the offender to the AFK channel automatically.
3. **Sends** a notification to the user.
4. **Prevents** them from joining voice channels while muted.

---

### 📋 Features

- **Customizable Monthly Quota:** Set the limit (default: 60 minutes).
- **Sarcastic Notifications:** Beautifully crafted embed messages with GIFs and a touch of salt.
- **Detailed Logging:** Keep track of every enforcement action.
- **Admin Commands:** View stats, manual reset, and real-time quota adjustments.

---

### 🚀 Quick Start

```bash
git clone https://github.com/Keyser2356/Mute-or-kick.git
cd Mute-or-kick
pip install discord.py
python bot.py
