import discord
from discord.ext import commands
from discord import Interaction
from discord import ButtonStyle
from discord.ui import Button, View
from discord import app_commands
import sqlite3
import os
import time
from datetime import timedelta
from datetime import datetime
from dotenv import load_dotenv
import random
from PIL import Image, ImageDraw, ImageFont
import requests


# Load environment variables
load_dotenv()
# Track the bot's start time
start_time = time.time()

TOKEN = os.getenv('DISCORD_TOKEN')
STEAMGRIDDB_API_KEY = os.getenv('STEAMGRIDDB_API_KEY')

# Database setup
conn = sqlite3.connect('hunters_ledger.db')
c = conn.cursor()

# Database schema
c.execute('''CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_name TEXT UNIQUE,
                platform TEXT
            )''')

c.execute('''CREATE TABLE IF NOT EXISTS user_games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                user_name TEXT,
                game_id INTEGER,
                platform TEXT,
                FOREIGN KEY (game_id) REFERENCES games(id)
            )''')
c.execute('''CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT NOT NULL,
                command TEXT NOT NULL,
                game_name TEXT
            )''')
c.execute('''CREATE TABLE IF NOT EXISTS solo_backlogs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                user_name TEXT NOT NULL,
                game_name TEXT NOT NULL,
                status TEXT CHECK(status IN ('not started', 'in progress', 'completed')) DEFAULT 'not started',
                completion_date DATE,
                rating INTEGER CHECK(rating BETWEEN 1 AND 5),
                comments TEXT
            )''')
conn.commit()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

# Sync slash commands with Discord
@bot.event
async def on_ready():
    # Register the bot's slash commands globally (across all servers) or for specific guilds
    await bot.tree.sync()  # Global sync
    print(f"Logged in as {bot.user}!")

# Command: Track a game with platform in the game title
@bot.tree.command(name="trackhunt", description="Add a game to the list")
async def track_hunt(interaction: discord.Interaction, game_name: str):
    # Case-insensitive existence check to prevent A/a duplicates
    c.execute("SELECT id, game_name FROM games WHERE LOWER(game_name) = LOWER(?)", (game_name,))
    row = c.fetchone()

    if row:
        await interaction.response.send_message(f"The game '{row[1]}' is already being tracked.")
        return

    # Insert the game using the user's original casing
    c.execute("INSERT INTO games (game_name) VALUES (?)", (game_name,))
    conn.commit()

    # Auto-join the creator to save an extra command
    user_id = str(interaction.user.id)
    user_name = str(interaction.user)
    c.execute("SELECT id FROM games WHERE LOWER(game_name) = LOWER(?)", (game_name,))
    game_id = c.fetchone()[0]
    c.execute("INSERT INTO user_games (user_id, user_name, game_id) VALUES (?, ?, ?)", (user_id, user_name, game_id))
    conn.commit()

    await interaction.response.send_message(
        f"Game '{game_name}' has been added and you've been added to its hunters."
    )


## Command: Track a game with platform buttons
#@bot.tree.command(name="trackhunt", description="Add a game to the list")
#async def track_hunt(interaction: discord.Interaction, game_name: str):
#    # Check if the game is already in the database
#    c.execute("SELECT * FROM games WHERE game_name = ?", (game_name,))
#    if c.fetchone():
#        await interaction.response.send_message(f"The game '{game_name}' is already being tracked.")
#    else:
#        await interaction.response.send_message(
#            f"Select a platform for '{game_name}':",
#            view=PlatformView(game_name),
#            ephemeral=True
#        )

# View with buttons for platform selection
class PlatformView(discord.ui.View):  # Replace ui.View with discord.ui.View
    def __init__(self, game_name):
        super().__init__()
        self.game_name = game_name

    @discord.ui.button(label="Xbone", style=ButtonStyle.primary, custom_id="platform_Xbone")  # Replace ui.button
    async def xbox_button(self, interaction: discord.Interaction, button: discord.ui.Button):  # Replace ui.Button
        await process_platform(interaction, self.game_name, "Xbone")

    @discord.ui.button(label="360", style=ButtonStyle.primary, custom_id="platform_360")
    async def pc_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await process_platform(interaction, self.game_name, "360")

    @discord.ui.button(label="Windows", style=ButtonStyle.primary, custom_id="platform_windows")
    async def ps_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await process_platform(interaction, self.game_name, "Windows")

# Process platform selection
async def process_platform(interaction: discord.Interaction, game_name: str, platform: str):
    c.execute("INSERT INTO games (game_name, platform) VALUES (?, ?)", (game_name, platform))
    conn.commit()
    await interaction.response.send_message(
        f"Game '{game_name}' has been added to the list under '{platform}'.",
        ephemeral=True
    )


class JoinHuntView(discord.ui.View):
    def __init__(self, game_id: int, game_name: str):
        super().__init__(timeout=60)
        self.game_id = game_id
        self.game_name = game_name

    @discord.ui.button(label="Join this hunt", style=ButtonStyle.success)
    async def join_this_hunt(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        user_name = str(interaction.user)

        c.execute("SELECT 1 FROM user_games WHERE user_id = ? AND game_id = ?", (user_id, self.game_id))
        if c.fetchone():
            await interaction.response.send_message(
                f"{interaction.user.mention}, you're already hunting '{self.game_name}'.",
                ephemeral=True
            )
            return

        c.execute(
            "INSERT INTO user_games (user_id, user_name, game_id) VALUES (?, ?, ?)",
            (user_id, user_name, self.game_id)
        )
        conn.commit()
        await interaction.response.send_message(
            f"{interaction.user.mention} joined the hunt for '{self.game_name}'.",
            ephemeral=True
        )

async def send_safely(
    interaction: discord.Interaction,
    content: str,
    *,
    ephemeral: bool = False,
    view: discord.ui.View | None = None
):
    # Use followup if we've already acknowledged (or deferred) the interaction
    if interaction.response.is_done():
        if view is None:
            await interaction.followup.send(content, ephemeral=ephemeral)
        else:
            await interaction.followup.send(content, ephemeral=ephemeral, view=view)
    else:
        if view is None:
            await interaction.response.send_message(content, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(content, ephemeral=ephemeral, view=view)


  
# ---- Mass add modal for solo backlog ----
class MassHuntsModal(discord.ui.Modal, title="Add Multiple Solo Hunts"):
    not_started = discord.ui.TextInput(
        label='Not started',
        style=discord.TextStyle.paragraph,
        required=False,
        placeholder='E.g. Hollow Knight, Ori and the Blind Forest'
    )
    in_progress = discord.ui.TextInput(
        label='In progress',
        style=discord.TextStyle.paragraph,
        required=False,
        placeholder='E.g. Elden Ring, Hades'
    )

    def __init__(self, user_id: int, user_name: str):
        super().__init__()
        self._user_id = user_id
        self._user_name = user_name

    async def on_submit(self, interaction: discord.Interaction):
        def parse_list(raw: str) -> list[str]:
            if not raw:
                return []
            # Split on commas, strip whitespace, drop empties
            return [g.strip() for g in raw.split(",") if g.strip()]

        def norm(s: str) -> str:
            # Normalize for case/spacing comparisons
            return " ".join(s.split()).lower()

        ns_raw = parse_list(str(self.not_started.value))
        ip_raw = parse_list(str(self.in_progress.value))

        # Deduplicate within each list while keeping last-typed casing
        ns_map = {norm(g): g for g in ns_raw}
        ip_map = {norm(g): g for g in ip_raw}

        # Conflict resolution: if a game is in both lists, "In progress" wins
        for key in set(ns_map.keys()) & set(ip_map.keys()):
            ns_map.pop(key, None)

        added_ns, added_ip = [], []
        moved_to_ns, moved_to_ip = [], []
        unchanged = []

        def upsert(game_display: str, target_status: str, added_list: list[str], moved_list: list[str]):
            # Does this title already exist for the user?
            c.execute(
                'SELECT game_name, status FROM solo_backlogs WHERE user_id = ? AND LOWER(game_name) = LOWER(?)',
                (self._user_id, game_display)
            )
            row = c.fetchone()

            if not row:
                # Insert new (use the casing the user typed)
                c.execute(
                    'INSERT INTO solo_backlogs (user_id, user_name, game_name, status) VALUES (?, ?, ?, ?)',
                    (self._user_id, self._user_name, game_display, target_status)
                )
                added_list.append(game_display)
                return

            existing_name, existing_status = row
            if existing_status != target_status:
                # Move status (keep existing casing; don't overwrite user's canonical title)
                c.execute(
                    'UPDATE solo_backlogs SET status = ?, user_name = ? WHERE user_id = ? AND LOWER(game_name) = LOWER(?)',
                    (target_status, self._user_name, self._user_id, game_display)
                )
                moved_list.append(existing_name)
            else:
                unchanged.append(existing_name)

        # Apply Not started first, then In progress (IP wins in conflicts handled above)
        for g in ns_map.values():
            upsert(g, "not started", added_ns, moved_to_ns)
        for g in ip_map.values():
            upsert(g, "in progress", added_ip, moved_to_ip)

        conn.commit()

        # Build a tidy summary
        segments = []
        if added_ip:
            segments.append("**In Progress – added:** " + ", ".join(added_ip))
        if moved_to_ip:
            segments.append("**Moved to In Progress:** " + ", ".join(moved_to_ip))
        if added_ns:
            segments.append("**Not Started – added:** " + ", ".join(added_ns))
        if moved_to_ns:
            segments.append("**Moved to Not Started:** " + ", ".join(moved_to_ns))

        if not segments:
            await interaction.response.send_message(
                "Nothing to change. (Everything you entered is already in that status.)",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Updated your solo backlog:\n" + "\n".join(segments),
            ephemeral=True
        )


  
# Command: Show all tracked hunts
@bot.tree.command(name="showhunts", description="Show all games currently being managed")
async def show_hunts(interaction: discord.Interaction):
    c.execute("SELECT game_name FROM games ORDER BY game_name ASC")
    games = c.fetchall()
    if games:
        game_list = "\n".join([game[0] for game in games])
        await interaction.response.send_message(f"**Tracked Hunts:**\n{game_list}")
    else:
        await interaction.response.send_message("No games are currently being tracked.")

## Command: Show all tracked hunts
#@bot.tree.command(name="showhunts", description="Show all games currently being managed")
#async def show_hunts(interaction: discord.Interaction):
#    c.execute("SELECT game_name, platform FROM games ORDER BY game_name ASC")
#    games = c.fetchall()
#    if games:
#        game_list = "\n".join([f"{game[0]} ({game[1]})" for game in games])
#        await interaction.response.send_message(f"**Tracked Hunts:**\n{game_list}")
#    else:
#        await interaction.response.send_message("No games are currently being tracked.")

# Command: Show who is hunting a specific game
@bot.tree.command(name="whohunts", description="Show who is playing a specific game with a user count")
@app_commands.describe(game_name="Start typing to search...")
async def who_hunts(interaction: discord.Interaction, game_name: str):
    c.execute("SELECT id, game_name FROM games WHERE LOWER(game_name) = LOWER(?)", (game_name,))
    game = c.fetchone()
    if not game:
        await interaction.response.send_message(f"Game '{game_name}' not found.", ephemeral=True)
        return

    game_id, canonical_name = game
    c.execute("SELECT user_name FROM user_games WHERE game_id = ?", (game_id,))
    users = [u[0] for u in c.fetchall()]

    user_list = "\n".join(users) if users else "_No hunters yet_"
    view = JoinHuntView(game_id, canonical_name)

    await interaction.response.send_message(
        f"**Players for '{canonical_name}' ({len(users)} hunters):**\n{user_list}",
        view=view
    )

@who_hunts.autocomplete('game_name')
async def who_hunts_autocomplete(interaction: discord.Interaction, current: str):
    like = f"%{current}%"
    c.execute(
        "SELECT game_name FROM games WHERE game_name LIKE ? COLLATE NOCASE ORDER BY game_name ASC LIMIT 25",
        (like,)
    )
    return [app_commands.Choice(name=row[0], value=row[0]) for row in c.fetchall()]


# Command: Join a hunt
@bot.tree.command(name="joinhunt", description="Add yourself to a game's player list")
@app_commands.describe(game_name="Start typing to search...")
async def join_hunt(interaction: discord.Interaction, game_name: str):
    user_id = str(interaction.user.id)
    user_name = str(interaction.user)

    # Case-insensitive lookup
    c.execute("SELECT id, game_name FROM games WHERE LOWER(game_name) = LOWER(?)", (game_name,))
    game = c.fetchone()
    if not game:
        await interaction.response.send_message(f"Game '{game_name}' not found.", ephemeral=True)
        return

    game_id, canonical_name = game
    c.execute(
        "SELECT 1 FROM user_games WHERE user_id = ? AND game_id = ?",
        (user_id, game_id)
    )
    if c.fetchone():
        await interaction.response.send_message(
            f"{interaction.user.mention}, you're already hunting '{canonical_name}'.",
            ephemeral=True
        )
        return

    c.execute(
        "INSERT INTO user_games (user_id, user_name, game_id) VALUES (?, ?, ?)",
        (user_id, user_name, game_id)
    )
    conn.commit()
    await interaction.response.send_message(
        f"{interaction.user.mention}, you've joined the hunt for '{canonical_name}'."
    )

# ---- Autocomplete for joinhunt ----
@join_hunt.autocomplete('game_name')
async def join_hunt_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[app_commands.Choice[str]]:
    # Fetch up to 25 matching games (Discord limit) - case-insensitive
    like = f"%{current}%"
    c.execute("SELECT game_name FROM games WHERE game_name LIKE ? COLLATE NOCASE ORDER BY game_name ASC LIMIT 25", (like,))
    rows = c.fetchall()
    return [app_commands.Choice(name=r[0], value=r[0]) for r in rows]

# Command: Leave a hunt
@bot.tree.command(name="leavehunt", description="Remove yourself from a game's player list")
@app_commands.describe(game_name="Start typing to search...")
async def leave_hunt(interaction: discord.Interaction, game_name: str):
    user_id = str(interaction.user.id)

    c.execute("SELECT id, game_name FROM games WHERE LOWER(game_name) = LOWER(?)", (game_name,))
    game = c.fetchone()
    if not game:
        await interaction.response.send_message(f"Game '{game_name}' not found.", ephemeral=True)
        return

    game_id, canonical_name = game
    c.execute("DELETE FROM user_games WHERE user_id = ? AND game_id = ?", (user_id, game_id))
    conn.commit()

    if c.rowcount:
        await interaction.response.send_message(
            f"{interaction.user.mention}, you've left the hunt for '{canonical_name}'."
        )
    else:
        await interaction.response.send_message(
            f"{interaction.user.mention}, you weren't signed up for '{canonical_name}'.",
            ephemeral=True
        )

@leave_hunt.autocomplete('game_name')
async def leave_hunt_autocomplete(interaction: discord.Interaction, current: str):
    like = f"%{current}%"
    c.execute(
        "SELECT game_name FROM games WHERE game_name LIKE ? COLLATE NOCASE ORDER BY game_name ASC LIMIT 25",
        (like,)
    )
    return [app_commands.Choice(name=row[0], value=row[0]) for row in c.fetchall()]


# Command: Show games the user is hunting
@bot.tree.command(name="showmyhunts", description="Show all games you are added to")
async def show_my_hunts(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    c.execute('''SELECT g.game_name 
                 FROM games g 
                 JOIN user_games ug ON g.id = ug.game_id 
                 WHERE ug.user_id = ? 
                 ORDER BY g.game_name ASC''', (user_id,))
    games = c.fetchall()
    if games:
        game_list = "\n".join([game[0] for game in games])
        await interaction.response.send_message(f"**Your Hunts:**\n{game_list}")
    else:
        await interaction.response.send_message("You are not signed up for any games.")

# Command: Show all games a user is added to
@bot.tree.command(name="showhunter", description="Show all games a user is added to")
async def show_hunter(interaction: Interaction, user: discord.User):
    user_id = str(user.id)
    c.execute('''SELECT g.game_name 
                 FROM games g 
                 JOIN user_games ug ON g.id = ug.game_id 
                 WHERE ug.user_id = ? 
                 ORDER BY g.game_name ASC''', (user_id,))
    games = c.fetchall()
    if games:
        game_list = "\n".join([game[0] for game in games])
        await interaction.response.send_message(f"**Games {user.mention} is hunting:**\n{game_list}")
    else:
        await interaction.response.send_message(f"{user.mention} is not signed up for any games.")

# Command: Show the top 5 most popular games
@bot.tree.command(name="mosthunted", description="Show the top 5 most popular games")
async def most_hunted(interaction: Interaction):
    c.execute('''SELECT g.game_name, COUNT(ug.user_id) as player_count 
                 FROM games g 
                 JOIN user_games ug ON g.id = ug.game_id 
                 GROUP BY g.game_name 
                 ORDER BY player_count DESC 
                 LIMIT 5''')
    games = c.fetchall()
    if games:
        game_list = "\n".join([f"{game[0]} - {game[1]} hunters" for game in games])
        await interaction.response.send_message(f"**Top 5 Most Hunted Games:**\n{game_list}")
    else:
        await interaction.response.send_message("No games have hunters yet.")

# Command: Show games with no hunters
@bot.tree.command(name="nothunted", description="Show a list of games with no users signed up")
async def not_hunted(interaction: Interaction):
    c.execute('''SELECT g.game_name 
                 FROM games g 
                 LEFT JOIN user_games ug ON g.id = ug.game_id 
                 WHERE ug.game_id IS NULL''')
    games = c.fetchall()
    if games:
        game_list = "\n".join([game[0] for game in games])
        await interaction.response.send_message(f"**Games with No Hunters:**\n{game_list}")
    else:
        await interaction.response.send_message("All games currently have hunters.")

# Command: Rename a game in the database
@bot.tree.command(name="changehunt", description="Rename a game in the database")
@commands.has_permissions(administrator=True)
async def change_hunt(interaction: Interaction, old_name: str, new_name: str):
    c.execute("UPDATE games SET game_name = ? WHERE game_name = ?", (new_name, old_name))
    if conn.total_changes > 0:
        conn.commit()
        await interaction.response.send_message(f"Game '{old_name}' has been renamed to '{new_name}'.")
    else:
        await interaction.response.send_message(f"Game '{old_name}' not found.")

# Command: Remove a game from the list (Admin Only)
class ConfirmForgetView(discord.ui.View):
    def __init__(self, invoker_id: int, game_id: int, canonical_name: str):
        super().__init__(timeout=60)
        self.invoker_id = invoker_id
        self.game_id = game_id
        self.canonical_name = canonical_name

    async def _not_invoker(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message("Only the requester can confirm this action.", ephemeral=True)
            return True
        return False

    @discord.ui.button(label="Yes, remove this game", style=ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._not_invoker(interaction):
            return
        # Remove all signups, then the game
        c.execute("DELETE FROM user_games WHERE game_id = ?", (self.game_id,))
        c.execute("DELETE FROM games WHERE id = ?", (self.game_id,))
        conn.commit()
        await interaction.response.edit_message(
            content=f"Removed '{self.canonical_name}' from the tracked hunts.", view=None
        )

    @discord.ui.button(label="Cancel", style=ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._not_invoker(interaction):
            return
        await interaction.response.edit_message(content="Cancelled. No changes made.", view=None)


@bot.tree.command(name="forgethunt", description="Remove a game from the tracked list (deletes the game for everyone(Admin Only)).")
@app_commands.describe(game_name="Start typing to search...")
async def forget_hunt(interaction: discord.Interaction, game_name: str):
    # Find the game (case-insensitive)
    c.execute("SELECT id, game_name FROM games WHERE LOWER(game_name) = LOWER(?)", (game_name,))
    game = c.fetchone()
    if not game:
        await interaction.response.send_message(f"Game '{game_name}' not found.", ephemeral=True)
        return

    game_id, canonical_name = game

    # Who's hunting?
    c.execute("SELECT user_id FROM user_games WHERE game_id = ?", (game_id,))
    hunters = [u[0] for u in c.fetchall()]
    others_count = len([u for u in hunters if u != str(interaction.user.id)])

    # If the requester is the only hunter, remove immediately
    if others_count == 0:
        c.execute("DELETE FROM user_games WHERE game_id = ?", (game_id,))
        c.execute("DELETE FROM games WHERE id = ?", (game_id,))
        conn.commit()
        await interaction.response.send_message(
            f"Removed '{canonical_name}'. (You were the only hunter.)"
        )
        return

    # Otherwise, ask for confirmation
    await interaction.response.send_message(
        f"Are you sure you want to remove '{canonical_name}'? "
        f"**{others_count}** other user(s) are still hunting this game.",
        view=ConfirmForgetView(interaction.user.id, game_id, canonical_name),
        ephemeral=True
    )

@forget_hunt.autocomplete('game_name')
async def forget_hunt_autocomplete(interaction: discord.Interaction, current: str):
    like = f"%{current}%"
    c.execute(
        "SELECT game_name FROM games WHERE game_name LIKE ? COLLATE NOCASE ORDER BY game_name ASC LIMIT 25",
        (like,)
    )
    return [app_commands.Choice(name=row[0], value=row[0]) for row in c.fetchall()]


# Command: Remove a user from all games (Admin Only)
@bot.tree.command(name="forgethunter", description="Remove a user from all games (Admin only)")
@commands.has_permissions(administrator=True)
async def forget_hunter(interaction: Interaction, user: discord.User):
    user_id = str(user.id)
    c.execute("DELETE FROM user_games WHERE user_id = ?", (user_id,))
    conn.commit()
    await interaction.response.send_message(f"{user.mention} has been removed from all games.")



# Solo Backlog Management Commands

# Command: /newhunt
@bot.tree.command(name="newhunt", description="Add a game to your solo backlog with the status 'not started.'")
async def new_hunt(interaction: discord.Interaction, game_name: str):
    # Check if the game already exists for the user
    c.execute('SELECT COUNT(*) FROM solo_backlogs WHERE user_id = ? AND game_name = ?', (interaction.user.id, game_name))
    if c.fetchone()[0] > 0:
        await interaction.response.send_message(f"Game '{game_name}' is already in your solo backlog.")
        return

    # Add the game if it doesn't exist
    c.execute('INSERT INTO solo_backlogs (user_id, user_name, game_name) VALUES (?, ?, ?)',
              (interaction.user.id, interaction.user.name, game_name))
    conn.commit()
    await interaction.response.send_message(f"Game '{game_name}' added to your solo backlog with status 'not started'.")


# Command: /mysolohunts - Display your solo backlog with statuses ('not started' or 'in progress')
@bot.tree.command(name="mysolohunts", description="Display your solo backlog with statuses ('not started' or 'in progress').")
async def my_solo_hunts(interaction: discord.Interaction):
    c.execute('SELECT game_name, status FROM solo_backlogs WHERE user_id = ? ORDER BY status DESC, game_name ASC', (interaction.user.id,))
    games = c.fetchall()
    
    if games:
        # Separate games by status
        in_progress = [game[0] for game in games if game[1] == "in progress"]
        not_started = [game[0] for game in games if game[1] == "not started"]
        
        # Build response
        response = ""
        if in_progress:
            response += "**In Progress:**\n" + "\n".join(in_progress) + "\n\n"
        if not_started:
            response += "**Not Started:**\n" + "\n".join(not_started)
        
        await interaction.response.send_message(f"Your solo hunts:\n{response}")
    else:
        await interaction.response.send_message("Your solo backlog is empty.")


# Command: /starthunt
@bot.tree.command(name="starthunt", description="Set a game's status to 'in progress.'")
async def start_hunt(interaction: discord.Interaction, game_name: str):
    c.execute('UPDATE solo_backlogs SET status = "in progress" WHERE user_id = ? AND game_name = ? AND status = "not started"',
              (interaction.user.id, game_name))
    conn.commit()
    if c.rowcount:
        await interaction.response.send_message(f"Game '{game_name}' is now 'in progress'.")
    else:
        await interaction.response.send_message(f"Cannot start '{game_name}': either it doesn't exist or it's already started.")

# Command: /giveup - Remove a game from your solo backlog.
@bot.tree.command(name="giveup", description="Remove a game from your solo backlog.")
async def give_up(interaction: discord.Interaction, game_name: str):
    c.execute('DELETE FROM solo_backlogs WHERE user_id = ? AND game_name = ?', (interaction.user.id, game_name))
    conn.commit()
    if c.rowcount:
        await interaction.response.send_message(f"Game '{game_name}' has been removed from your solo backlog.")
    else:
        await interaction.response.send_message(f"Cannot find the game '{game_name}' in your solo backlog.")


# Command: /finishhunt
@bot.tree.command(name="finishhunt", description="Set a game's status to 'completed.'")
async def finish_hunt(interaction: discord.Interaction, game_name: str):
    # Update the game's status to 'completed' with the current date
    c.execute('UPDATE solo_backlogs SET status = "completed", completion_date = DATE("now") WHERE user_id = ? AND game_name = ? AND status = "in progress"',
              (interaction.user.id, game_name))
    conn.commit()
    if c.rowcount:
        await interaction.response.send_message(f"Game '{game_name}' is now 'completed'.")
    else:
        await interaction.response.send_message(f"Cannot finish '{game_name}': either it doesn't exist or it's not in progress.")


# Command: /newmasshunts
@bot.tree.command(name="newmasshunts", description="Add multiple games to your solo backlog via a modal.")
async def new_mass_hunts(interaction: discord.Interaction):
    await interaction.response.send_modal(MassHuntsModal(interaction.user.id, interaction.user.name))


# Command: /myfinishedhunts
@bot.tree.command(name="myfinishedhunts", description="Show completed games, either all-time or for a specific month and year.")
async def my_finished_hunts(interaction: discord.Interaction, month: int = None, year: int = None):
    query = 'SELECT game_name, completion_date FROM solo_backlogs WHERE user_id = ? AND status = "completed"'
    params = [interaction.user.id]
    if month and year:
        query += ' AND strftime("%m", completion_date) = ? AND strftime("%Y", completion_date) = ?'
        params.extend([f"{int(month):02}", str(year)])
    query += ' ORDER BY game_name ASC'
    c.execute(query, tuple(params))
    games = c.fetchall()
    if games:
        response = "\n".join([f"{game[0]} - Completed on {game[1]}" for game in games])
        await interaction.response.send_message(f"Your completed games:\n{response}")
    else:
        await interaction.response.send_message("No completed games found for the specified period.")

# Command: /givemeahunt
@bot.tree.command(name="givemeahunt", description="Randomly select a hunt from your backlog and set it to 'in progress.'")
async def give_me_a_hunt(interaction: discord.Interaction):
    c.execute('SELECT game_name FROM solo_backlogs WHERE user_id = ? AND status = "not started"', (interaction.user.id,))
    games = [game[0] for game in c.fetchall()]
    if games:
        selected_game = random.choice(games)
        c.execute('UPDATE solo_backlogs SET status = "in progress" WHERE user_id = ? AND game_name = ?',
                  (interaction.user.id, selected_game))
        conn.commit()
        await interaction.response.send_message(f"Your next hunt: '{selected_game}' is now 'in progress'.")
    else:
        await interaction.response.send_message("No games available in your backlog to hunt.")

# Command: /ratehunt
@bot.tree.command(name="ratehunt", description="Rate a completed game and leave optional comments.")
async def rate_hunt(interaction: discord.Interaction, game_name: str, rating: int, comments: str = None):
    c.execute('UPDATE solo_backlogs SET rating = ?, comments = ? WHERE user_id = ? AND game_name = ? AND status = "completed"',
              (rating, comments, interaction.user.id, game_name))
    conn.commit()
    if c.rowcount:
        await interaction.response.send_message(f"Rating added for '{game_name}': {rating}/5. {comments if comments else ''}")
    else:
        await interaction.response.send_message(f"Cannot rate '{game_name}': either it doesn't exist or it hasn't been completed.")

# Command: /huntfeedback
@bot.tree.command(name="huntfeedback", description="View feedback and ratings left by others for a specific game.")
async def hunt_feedback(interaction: discord.Interaction, game_name: str):
    c.execute('SELECT user_name, rating, comments FROM solo_backlogs WHERE game_name = ? AND rating IS NOT NULL', (game_name,))
    feedback = c.fetchall()
    if feedback:
        response = "\n".join([f"{fb[0]}: {fb[1]}/5 - {fb[2]}" for fb in feedback])
        await interaction.response.send_message(f"Feedback for '{game_name}':\n{response}")
    else:
        await interaction.response.send_message(f"No feedback found for '{game_name}'.")

# Command: Displays a list of all available commands
@bot.tree.command(name="help", description="Displays a list of all available commands.")
async def help_command(interaction: discord.Interaction):
    help_text = """
**Haven's Ledger Commands:**

- **Co-op and Multiplayer Backlog Management:**
  - `/trackhunt "game name"` - Add a game to the co-op backlog.
  - `/showhunts` - Show all games currently being managed.
  - `/whohunts "game name"` - Show who is playing a specific game.
  - `/joinhunt "game name"` - Add yourself to a game's player list.
  - `/leavehunt "game name"` - Remove yourself from a game's player list.
  - `/showmyhunts` - Show all games you are added to.
  - `/showhunter @user` - Show all games a user is added to.
  - `/mosthunted` - Show the top 5 most popular games.
  - `/nothunted` - Show a list of games with no users signed up.
  - `/changehunt "old name" "new name"` - Rename a game in the database.
  - `/callhunters "game name"` - Tag all users signed up to a specific game.

- **Solo Backlog Management:**
  - `/newhunt "game name"` - Add a game to your solo backlog with the status "not started."
  - `/mysolohunts` - Display your solo backlog with statuses ("not started" or "in progress").
  - `/starthunt "game name"` - Set a game's status to "in progress."
  - `/finishhunt "game name"` - Set a game's status to "completed."
  - `/myfinishedhunts [Month] [Year]` - Show completed games, either all-time or for a specific month and year.
  - `/givemeahunt` - Randomly select a hunt from your backlog and set it to "in progress."
  - `/ratehunt "game name" "rating out of 5" [comments]` - Rate a completed game and leave optional comments.
  - `/huntfeedback "game name"` - View feedback and ratings left by others for a specific game.
  - `/generatecard "game name"` - Generate a completion card for a finished solo game.

- **Bot Information:**
  - `/botversion` - Displays the bot's version and additional information.
  - `/healthcheck` - Check the bot's status and health.

Need further assistance? Feel free to ask!
"""
    await interaction.response.send_message(help_text)
  
# Command: Check who added a specific game (Admin only).
@bot.tree.command(name="whoadded", description="Check who added a specific game (Admin only).")
@commands.has_permissions(administrator=True)
async def who_added(interaction: discord.Interaction, game_name: str):
    c.execute("SELECT user FROM logs WHERE command = 'trackhunt' AND game_name = ?", (game_name,))
    users = c.fetchall()
    if users:
        user_list = "\n".join([user[0] for user in users])
        await interaction.response.send_message(f"Users who added '{game_name}':\n{user_list}")
    else:
        await interaction.response.send_message(f"No records found for the game '{game_name}'.")

# Command: Call all hunters for a specific game
@bot.tree.command(name="callhunters", description="Tag all users signed up to a specific game, with an optional message")
@app_commands.describe(
    game_name="Start typing to search…",
    message="Optional message to include"
)
async def call_hunters(
    interaction: discord.Interaction,
    game_name: str,
    message: str | None = None
):
    # Case-insensitive game lookup
    c.execute('SELECT id, game_name FROM games WHERE LOWER(game_name) = LOWER(?)', (game_name,))
    game = c.fetchone()
    if not game:
        await send_safely(interaction, f"Game '{game_name}' not found.", ephemeral=True)
        return

    game_id, canonical_name = game

    # Fetch hunters
    c.execute('SELECT user_id FROM user_games WHERE game_id = ?', (game_id,))
    rows = c.fetchall()
    if not rows:
        await send_safely(interaction, f"No hunters are signed up for '{canonical_name}'.", ephemeral=True)
        return

    user_ids = [str(r[0]) for r in rows]

    # Build message parts
    note = (message or "").strip()
    extra = f"\n\n{interaction.user.mention} says\n> {note}" if note else ""
    header = f"Calling all hunters for '{canonical_name}':"

    # Send in safe chunks (Discord limits; keep it conservative)
    def chunks(seq, n):
        for i in range(0, len(seq), n):
            yield seq[i:i + n]

    first = True
    for group in chunks(user_ids, 40):  # 40 mentions per message is a safe cap
        mentions = " ".join(f"<@{uid}>" for uid in group)
        content = f"{header}\n{mentions}{extra}" if first else mentions
        await send_safely(interaction, content)
        first = False

# ---- Autocomplete for game_name ----
@call_hunters.autocomplete('game_name')
async def call_hunters_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[app_commands.Choice[str]]:
    like = f"%{current}%"
    c.execute(
        "SELECT game_name FROM games WHERE game_name LIKE ? COLLATE NOCASE ORDER BY game_name ASC LIMIT 25",
        (like,)
    )
    return [app_commands.Choice(name=row[0], value=row[0]) for row in c.fetchall()]
async def call_hunters(interaction: Interaction, game_name: str, message: str | None = None):
    # Case-insensitive game lookup
    c.execute('SELECT id, game_name FROM games WHERE LOWER(game_name) = LOWER(?)', (game_name,))
    game = c.fetchone()
    if not game:
        await interaction.response.send_message(f"Game '{game_name}' not found.", ephemeral=True)
        return

    game_id, canonical_name = game
    c.execute('SELECT ug.user_id FROM user_games ug WHERE ug.game_id = ?', (game_id,))
    users = c.fetchall()

    if not users:
        await interaction.response.send_message(f"No hunters are signed up for '{canonical_name}'.", ephemeral=True)
        return

    mentions = " ".join([f"<@{user[0]}>" for user in users])
    extra = ""
    if message and message.strip():
        extra = f"\n\n{interaction.user.mention} says\n> {message.strip()}"

    await interaction.response.send_message(
        f"Calling all hunters for '{canonical_name}':\n{mentions}{extra}"
    )


    if users:
        mentions = " ".join([f"<@{user[0]}>" for user in users])
        await interaction.response.send_message(f"{message}\n\n{mentions}")
    else:
        await interaction.response.send_message("No users are currently signed up for any games.")

# Command: Show bot version and information
@bot.tree.command(name="botversion", description="Show bot version and additional information")
async def bot_version(interaction: Interaction):
    version_info = "**A Hunters Ledger v2.0**\nCreated by Tide44\nGitHub: [A Hunters Ledger](https://github.com/Tide44-cmd/HuntersLedger)"
    await interaction.response.send_message(version_info)

# Command: Healthcheck
@bot.tree.command(name="healthcheck", description="Checks the bot's status and health")
async def healthcheck(interaction: Interaction):
    try:
        # Check database connection
        c.execute("SELECT 1")
        db_status = "✅ A Hunters Ledger is running smoothly!"
    except Exception as e:
        db_status = f"❌ Error: {str(e)}"
    
    # Calculate uptime
    uptime_seconds = int(time.time() - start_time)
    uptime = str(timedelta(seconds=uptime_seconds))

    # Get registered commands
    command_count = len(bot.tree.get_commands())

    # Construct the health report
    health_report = (
        "**A Hunters Ledger Health Check:**\n"
        f"- **Uptime:** {uptime}\n"
        f"- **Database:** {db_status}\n"
        f"- **Registered Commands:** {command_count}\n"
    )
    
    await interaction.response.send_message(health_report)
  
# Command: Progress Graph
@bot.tree.command(name="myprogressgraph", description="Visualize your solo backlog status in a graph (mobile friendly PNG).")
async def my_progress_graph(interaction: discord.Interaction):
    import pygal
    import io
    import cairosvg

    user_id = str(interaction.user.id)
    c.execute('SELECT status, COUNT(*) FROM solo_backlogs WHERE user_id = ? GROUP BY status', (user_id,))
    data = c.fetchall()

    if not data:
        await interaction.response.send_message("Your solo backlog is empty. Add games to see progress graphs.")
        return

    # Defer the interaction (prevent Discord from timing out)
    await interaction.response.defer()

    # Generate SVG using Pygal
    pie_chart = pygal.Pie()
    pie_chart.title = f"{interaction.user.name}'s Solo Backlog Progress"
    for status, count in data:
        pie_chart.add(status.capitalize(), count)

    # Render SVG to bytes (in memory)
    svg_data = pie_chart.render()

    # Convert SVG to PNG using CairoSVG
    png_buffer = io.BytesIO()
    cairosvg.svg2png(bytestring=svg_data, write_to=png_buffer)
    png_buffer.seek(0)  # Reset buffer before sending

    # Send PNG file as a follow-up (since interaction is deferred)
    await interaction.followup.send(
        content=f"{interaction.user.mention}, here is your backlog progress graph:",
        file=discord.File(png_buffer, filename="progress.png")
    )

# Test Image generate here
# ==== Imports ====


# ==== Resource Paths ====
RESOURCE_PATH = "resources/"
DEFAULT_BACKGROUND = "background.jpg"
FONT_PATH = os.path.join(RESOURCE_PATH, "MedievalSharp.ttf")

# ==== Font Sizes ====
GAME_NAME_FONT_SIZE = 72
TEXT_FONT_SIZE = 48
FOOTER_FONT_SIZE = 30

# ==== Avatar Settings ====
AVATAR_SIZE = (100, 100)
AVATAR_POSITION = (100, 150)

# ==== Game Cover Settings ====
COVER_SIZE = (345, 518)
COVER_POSITION = (850, 110)

# ==== Utilities ====
def get_scaled_font(text, base_size, max_width, font_path, draw_context):
    """Returns a font that fits within max_width and the final font size."""
    font_size = base_size
    font = ImageFont.truetype(font_path, font_size)
    while font_size > 40:
        bbox = draw_context.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        if text_width <= max_width:
            break
        font_size -= 2
        font = ImageFont.truetype(font_path, font_size)
    return font, font_size


def draw_text_with_outline(draw, position, text, font, fill="white", outline="black", outline_thickness=3):
    """Draw text with an outline for visibility."""
    x, y = position
    for dx in range(-outline_thickness, outline_thickness + 1):
        for dy in range(-outline_thickness, outline_thickness + 1):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
    draw.text(position, text, font=font, fill=fill)

def fetch_steamgriddb_cover(game_name):
    """Fetch a 600x900 game cover from SteamGridDB."""
    headers = {"Authorization": f"Bearer {STEAMGRIDDB_API_KEY}"}
    search_url = f"https://www.steamgriddb.com/api/v2/search/autocomplete/{game_name}"
    response = requests.get(search_url, headers=headers)

    if response.status_code != 200 or not response.json().get("data"):
        print(f"Game '{game_name}' not found on SteamGridDB.")
        return None

    game_id = response.json()["data"][0]["id"]
    image_url = f"https://www.steamgriddb.com/api/v2/grids/game/{game_id}?dimensions=600x900"
    response = requests.get(image_url, headers=headers)

    if response.status_code != 200 or not response.json().get("data"):
        print(f"No 600x900 images found for '{game_name}'.")
        return None

    return response.json()["data"][0]["url"]

def download_image(url, save_path):
    """Download an image from a URL to a local file."""
    if url:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            with open(save_path, "wb") as file:
                for chunk in response.iter_content(1024):
                    file.write(chunk)
            return save_path
    return None

# ==== Banner Generation ====
async def generate_completion_banner(game_name, user_name, completion_date, avatar_url, genre=None):
    try:
        # Background image
        background_file = f"background_{genre.lower()}.jpg" if genre else DEFAULT_BACKGROUND
        background_path = os.path.join(RESOURCE_PATH, background_file)
        if not os.path.exists(background_path):
            background_path = os.path.join(RESOURCE_PATH, DEFAULT_BACKGROUND)

        background = Image.open(background_path).convert('RGBA')

        # Icons
        xbox_logo = Image.open(os.path.join(RESOURCE_PATH, "xbox_logo.png")).convert('RGBA')
        calendar_icon = Image.open(os.path.join(RESOURCE_PATH, "calendar_icon.png")).convert('RGBA')
        for icon in [xbox_logo, calendar_icon]:
            icon.thumbnail((50, 50))

        # Avatar processing
        response = requests.get(avatar_url, stream=True)
        avatar = Image.open(response.raw).convert("RGBA").resize(AVATAR_SIZE, Image.LANCZOS)
        mask = Image.new("L", AVATAR_SIZE, 0)
        ImageDraw.Draw(mask).ellipse((0, 0, *AVATAR_SIZE), fill=255)

        # Game cover
        game_cover = None
        cover_url = fetch_steamgriddb_cover(game_name)
        if cover_url:
            cover_path = download_image(cover_url, os.path.join(RESOURCE_PATH, f"{game_name}_cover.jpg"))
            if cover_path:
                game_cover = Image.open(cover_path).convert("RGBA").resize(COVER_SIZE, Image.LANCZOS)

        # Load and resize comp_banner image
        comp_banner = Image.open(os.path.join(RESOURCE_PATH, "completion_banner.png")).convert("RGBA")
        comp_banner = comp_banner.resize((400, 70), Image.LANCZOS)

        # Create drawing context
        draw = ImageDraw.Draw(background)
        text_font = ImageFont.truetype(FONT_PATH, TEXT_FONT_SIZE)
        footer_font = ImageFont.truetype(FONT_PATH, FOOTER_FONT_SIZE)

        # Get scaled game name font and its actual size
        game_font, actual_font_size = get_scaled_font(game_name, GAME_NAME_FONT_SIZE, 550, FONT_PATH, draw)

        # Define element positions
        positions = {
            "game_name": (215, 150 + actual_font_size // 2),  # Vertical adjustment for centering
            "xbox_logo": (125, 280),
            "user_name": (185, 275),
            "calendar_icon": (125, 360),
            "completion_date": (185, 355),
            "comp_banner": (125, 425),
        }

        # Draw elements
        draw_text_with_outline(draw, positions["game_name"], game_name, game_font)
        background.paste(xbox_logo, positions["xbox_logo"], xbox_logo)
        draw_text_with_outline(draw, positions["user_name"], user_name, text_font)
        background.paste(calendar_icon, positions["calendar_icon"], calendar_icon)
        draw_text_with_outline(draw, positions["completion_date"], completion_date, text_font)
        background.paste(comp_banner, positions["comp_banner"], comp_banner)
        background.paste(avatar, AVATAR_POSITION, mask)

        # Paste game cover if available
        if game_cover:
            background.paste(game_cover, COVER_POSITION, game_cover)

        output_path = os.path.join(RESOURCE_PATH, f'completion_{user_name}.png')
        background.save(output_path)
        return output_path

    except Exception as e:
        print(f"Error generating banner: {e}")
        return None

# ==== Discord Slash Command ====
@bot.tree.command(name="generatecard", description="Generate a completion card for a finished game.")
async def generate_card(interaction: discord.Interaction, game_name: str, genre: str = None):
    user_id = str(interaction.user.id)
    user_name = interaction.user.display_name
    avatar_url = interaction.user.display_avatar.url

    await interaction.response.defer()

    c.execute("""
        SELECT completion_date 
        FROM solo_backlogs 
        WHERE user_id = ? AND game_name = ? AND status = 'completed'
    """, (user_id, game_name))
    
    result = c.fetchone()
    if not result:
        await interaction.followup.send(f"You have not completed '{game_name}', so a card cannot be generated.")
        return

    completion_date = datetime.strptime(result[0], "%Y-%m-%d").strftime("%-d %b %Y")
    banner_path = await generate_completion_banner(game_name, user_name, completion_date, avatar_url, genre)

    if banner_path:
        await interaction.followup.send(
            f"Here is your completion card, {interaction.user.mention}! 🎉",
            file=discord.File(banner_path)
        )
        os.remove(banner_path)
    else:
        await interaction.followup.send("Error generating the completion card. Please try again later.")


# Test image generate End


# Run the bot
bot.run(TOKEN)
