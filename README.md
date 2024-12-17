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

## Commands Overview:

### Game Management:
- /trackhunt `"game name"` - Adds a game to the managed list.
- /changehunt `"old name"` `"new name"` - Renames a game in the database.
- ?forgethunt `"game name"` - Removes a game from the list (Admin only).

### Hunter Management:
- /joinhunt `"game name"` - Add yourself to a game's hunter list.
- /leavehunt `"game name"` - Remove yourself from a game's hunter list.
- /showmyhunts - Displays all games you're signed up for.
- /showhunter `@user` - Displays all games a specific user is hunting.
- ?forgethunter `@user` - Remove a user from all games (Admin only).

### Insights and Discovery:
- /mosthunted - Displays the top 5 most popular games by player count.
- /nothunted - Shows a list of games with no users signed up.
- /showhunts - Displays all currently tracked games.

### Collaboration and Call to Action:
- /callhunters `"game name"` - Tags all users signed up for a specific game.

### Bot Information and Health:
- /botversion - Displays the bot's version and additional information.
- /help - Provides a list of all available commands.
- /healthcheck - Checks the bot's status, including database connection and uptime.

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
