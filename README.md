# A Hunters Ledger
A Hunters Ledger is a Discord bot designed to help achievement hunters and co-op gamers organize their hunts efficiently. Whether you're tracking down elusive achievements, coordinating multiplayer sessions, or managing a growing list of games, A Hunters Ledger provides all the tools you need to build and manage your gaming adventures.

## Key Features:

- **Game Management:** Easily track, rename, and remove games from your managed list.
- **Hunter Coordination:** Users can sign up for games they are actively hunting and collaborate with others.
- **Insights and Leaderboards:** View the most popular games being hunted or identify games that need more attention.
- **Call to Action:** Ping all players hunting a specific game to gather your party quickly.
- **Bot Health and Transparency:** Check the bot's operational status and track its activities.

---

## Example Use Case:
**Game Name:** Halo: The Master Chief Collection  
**Hunters Signed Up:** Tide44, GamerX, PlayerOne  
**Call to Action:** `/callhunters "Halo: MCC"` will tag all signed-up players instantly.

Whether you're chasing 100% completion or just coordinating sessions with friends, A Hunters Ledger makes achievement hunting collaborative and organized.

---

## 📜 Commands Overview

### 🎮 Game Management
- /trackhunt `"game name"` — Add a game to the managed list.
- /changehunt `"old name"` `"new name"` — Rename a game in the database.
- /forgethunt `"game name"` — Remove a game from the list *(Admin only)*.

### 🧑‍🤝‍🧑 Hunter Management
- /joinhunt `"game name"` — Add yourself to a game's hunter list.
- /leavehunt `"game name"` — Remove yourself from a game's hunter list.
- /showmyhunts — Show all games you’re currently signed up for.
- /showhunter `@user` — View games another user is hunting.

### 🔍 Insights & Discovery
- /mosthunted — Show the top 5 most popular games.
- /nothunted — Show games with no users signed up.
- `showhunts — Display all tracked games.

### 📢 Collaboration & Callouts
- /callhunters `"game name"` — Tag all users hunting a specific game.
- /remindhunters `[message]` — Ping all hunters with a reminder.

### 🎯 Solo Hunt Management
- /newhunt `"game name"` — Add a game to your solo backlog.
- /mysolohunts — View your solo backlog (not started / in progress).
- /starthunt `"game name"` — Mark a solo game as in progress.
- /finishhunt `"game name"` — Mark a solo game as completed.
- /myfinishedhunts `[Month] [Year]` — View completed solo games.
- /givemeahunt — Randomly pick a new solo hunt from your backlog.
- /ratehunt `"game name" rating [comments]` — Rate and review a finished game.
- /huntfeedback `"game name"` — View feedback from others.
- /generatecard `"game name"` — Generate a completion banner for a finished game.

### 🤖 Bot Information
- /botversion — Display bot version and credits.
- /help — Show a full list of available commands.
- /healthcheck — Check database connection, uptime, and registered commands.

---

## How to Set Up and Run
To set up A Hunters Ledger in your Discord server:
1. Ensure you have the necessary permissions to add a bot.
2. Invite the bot to your server.
3. Use `/help` to view all commands and get started.

For source code and detailed instructions, visit the [GitHub Repository](https://github.com/Tide44-cmd/CabinSquadBot).

---

## Example Session:
**Track a Game:**  
`/trackhunt "Gears of War 4"`  
**Join the Hunt:**  
`/joinhunt "Gears of War 4"`  
**Call the Hunters:**  
`/callhunters "Gears of War 4"`  

A Hunters Ledger ensures no one hunts alone!

---

## Transparency and Logs
All bot activity, including game tracking, user signups, and administrative actions, is logged for accountability.

---

## About
**A Hunters Ledger** v2.0  
**Created by:** Tide44  
For achievement hunters, by achievement hunters.
