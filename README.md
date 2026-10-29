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
- /forgethunt `"game name"` — Remove a game from the list *(Owner only)*.

### 🧑‍🤝‍🧑 Hunter Management
- /joinhunt `"game name"` — Add yourself to a game's hunter list.
- /leavehunt `"game name"` — Remove yourself from a game's hunter list.
- /showmyhunts — Show all games you’re currently signed up for.
- /showhunter `@user` — View games another user is hunting.

Owner-only management commands such as `/changehunt`, `/forgethunt`,
`/forgethunter`, `/removehunter`, and `/whoadded` are restricted to Tide44's
Discord user ID (`420996360699904000`).

### 🔍 Insights & Discovery
- /mosthunted — Show the top 5 most popular games.
- /nothunted — Show games with no users signed up.
- /showhunts — Display all tracked games.

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

## Manual server icons

The `/servericon` command group changes the server icon only when an authorized
user explicitly requests a change. There are no schedules, timers, automatic
holiday changes, or background checks. Tide44 (`420996360699904000`) and server
administrators can use these commands; the bot itself needs **Manage Server**.

Add individual PNG, JPG, JPEG, or WebP files to `resources/server_icons/`.
The filename becomes the theme name, such as `default.png`, `halloween.png`, or
`christmas.png`. Names may contain 1-40 lowercase letters, numbers, underscores,
or hyphens and must start with a letter.

Repository files are shared by every server running this bot and take precedence
over uploaded images with the same theme name. Alternatively,
`/servericon upload theme:<name> image:<file>` stores a per-server image in SQLite.
Static images up to 8 MiB are centre-cropped and resized to 512 x 512 PNG.

- `/servericon set theme:default` applies the normal icon.
- `/servericon set theme:halloween` applies a named icon immediately.
- `/servericon upload theme:<name> image:<file>` adds or replaces an uploaded icon.
- `/servericon status` shows the selected icon and all available manual choices.

Installing or restarting the bot does not change the current Discord icon. Any
database left in the former automatic mode is changed to paused on startup and
stays untouched until `/servericon set` is used.

Run the isolated feature tests without a bot token or live Discord connection:
`python -m unittest discover -s tests -v`.
