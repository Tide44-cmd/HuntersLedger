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

## Seasonal server icons

The `/servericon` command group changes the **server icon** using UK time
(`Europe/London`, including BST). It checks once per minute and catches up after
bot downtime. Only Tide44 (`420996360699904000`) or members with **Administrator** permission
can use the icon commands. Manage Server alone does not grant access.
The bot itself needs **Manage Server**. Access is checked when each command
runs; command visibility alone does not grant permission.
Restart the updated bot to register these commands.

### First-time setup (repository files)

Add individual icon files to `resources/server_icons/` in this repository:

| Filename | Theme |
| --- | --- |
| `default.png` | Normal server icon |
| `halloween.png` | Halloween |
| `bonfire.png` | Bonfire/fireworks |
| `christmas.png` | Christmas |
| `easter.png` | Easter |

Names can be any lowercase theme of 1-40 letters, numbers, underscores or
hyphens, starting with a letter. PNG, JPG, JPEG and WebP files are supported.
The filename without the extension is the theme name. If duplicate formats
exist for a theme, preference is PNG, JPG, JPEG, then WebP.

Deploy/pull these files alongside the updated bot, then run
`/servericon set theme:auto`. No Discord image upload is needed. Files are
resolved relative to the bot source, regardless of its working directory.
Adding a file makes it available as an override; use `/servericon schedule`
to give additional themes dates. Only Halloween and bonfire dates are preset.

The bot discovers file changes on its next check, and caches resized images
until their file timestamp or size changes. Files in GitHub must be deployed
to the running bot before it can see them. Repository icons are shared across
servers using this bot; schedules and overrides remain per server.

Alternatively, `/servericon upload theme:default image:<normal server icon>`
(and similarly for other themes) stores a per-server image in SQLite.
Repository files take precedence over Discord uploads with the same name;
remove the repository file to use the uploaded version again. Status labels
which icons come from files and which come from uploads.

Use a separate image for each icon, rather than a sheet of several designs.
Static images up to 8 MiB are centre-cropped and resized to 512 x 512 PNG.
Schedules, overrides and optional uploaded images are stored in SQLite;
keep the database on persistent storage when deploying.

New servers start paused, so installing this update alone changes no icons.
The starter annual schedule is:

| From (UK midnight) | Until (excluded) | Icon |
| --- | --- | --- |
| 14 October | 1 November | `halloween` |
| 1 November | 6 November | `bonfire` |
| Outside these windows | | `default` |

### Overrides and status

- `/servericon set theme:halloween` immediately pins Halloween (or any available theme).
- `/servericon set theme:default` immediately pins the normal icon.
- `/servericon set theme:auto` clears the override and immediately applies today's schedule.
- `/servericon status` shows mode, dates, uploaded/missing images and the last background error.

Manual overrides last until changed, including across restarts. While a mode is
active the bot maintains that icon; make manual changes through these commands.
A failed Discord update leaves the previous mode in place. Background failures
are logged and retried on the next check. If an automatic holiday is missing its
image, the bot uses the default and reports the missing image in status.
The default image must be available as a file or upload before activating any mode.

### Add or change dates

`/servericon schedule theme:christmas start:12-01 end:12-29`

Dates in `MM-DD` repeat every year. The start is inclusive and the end is the
first day the icon is no longer used. Windows can cross New Year, for example
`start:12-31 end:01-03`. Outside holiday windows the default icon returns.

For dates that change each year or one-off occasions, use full dates:

`/servericon schedule theme:easter start:2027-03-26 end:2027-03-30`

Names are flexible: `valentines`, `st_patricks`, `summer`, `autumn`, `half_term`,
`new_year`, `wedding`, or any other theme. Add matching image files or upload them separately.
One window is stored per theme; scheduling that theme again replaces its dates.
Use distinct names if you need several windows for the same design.

If windows overlap, one-off windows take precedence over annual ones, then the
higher `priority` wins (0-100); ties use theme-name alphabetical order. For
example, Halloween can use priority 10 to take precedence over an autumn theme.
Adding dates does not clear a manual override.

`/servericon unschedule theme:christmas` removes that window but keeps the image.
Icon files, uploaded images and windows can be prepared before enabling automatic mode.

The extension uses the existing `discord.py` and Pillow dependencies. On Windows
or minimal containers, install `tzdata` if IANA time zones are unavailable:
`python -m pip install tzdata`.

Run the isolated feature tests without a bot token or a live Discord connection:
`python -m unittest discover -s tests -v`.
