import discord
from discord.ext import commands
from discord import Interaction
from discord import ButtonStyle
from discord.ui import Button, View
from discord import app_commands
from discord import Embed, Color
import sqlite3
import os
import time
from datetime import timedelta
from datetime import datetime
from dotenv import load_dotenv
import random
from PIL import Image, ImageDraw, ImageFont
import requests
import re
import asyncio


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

# --- Challenge tables (Next10 / A-Z Hunts) ---
  
c.execute('''
CREATE TABLE IF NOT EXISTS next10_lists (
    user_id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS next10_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    game_name TEXT NOT NULL,
    completed INTEGER DEFAULT 0,
    completed_at TIMESTAMP,
    UNIQUE(user_id, game_name)
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS az_lists (
    user_id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS az_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    letter TEXT NOT NULL,
    game_name TEXT,                 -- NULL means NA
    completed INTEGER DEFAULT 0,
    completed_at TIMESTAMP,
    UNIQUE(user_id, letter)
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS challenge_stats (
    user_id TEXT PRIMARY KEY,
    next10_completed_count INTEGER DEFAULT 0,
    az_completed_count INTEGER DEFAULT 0
)
''')

# --- Marks of the Hunt ---

c.execute("""
CREATE TABLE IF NOT EXISTS hunting_marks (
    key TEXT PRIMARY KEY,
    slot_index INTEGER NOT NULL,        -- fixed position on board (0..N-1)
    is_hidden INTEGER DEFAULT 0          -- 1 = secret mark not shown in empty slot hints
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS user_hunting_marks (
    user_id TEXT NOT NULL,
    key TEXT NOT NULL,
    unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, key),
    FOREIGN KEY (key) REFERENCES hunting_marks(key)
)
""")
conn.commit()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

# Load extensions on startup
@bot.event # Sync slash commands with Discord
async def on_ready():
  # Register the bot's slash commands globally (across all servers) or for specific guilds
    await bot.load_extension("calendar_invite")  # Name of the Python file (no .py)
    await bot.tree.sync()
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

async def _send_long(interaction: discord.Interaction, header: str, lines: list[str]):
    if not lines:
        await interaction.response.send_message(header)
        return
    message_limit = 1900
    current = header + "\n"
    first = True
    for line in lines:
        if len(current) + len(line) + 1 > message_limit:
            if first:
                await interaction.response.send_message(current.rstrip())
                first = False
            else:
                await interaction.followup.send(current.rstrip())
            current = ""
        current += line + "\n"
    if current:
        if first:
            await interaction.response.send_message(current.rstrip())
        else:
            await interaction.followup.send(current.rstrip())

  
# ---- Mass add modal for solo backlog ----
class MassHuntsModal(discord.ui.Modal, title="Mass add solo hunts"):
   # instructions = discord.ui.TextInput(
   #   label="How to use",
   #   style=discord.TextStyle.short,
   #   default="Add items separated by commas (,).",
   #   required=False,
   #   min_length=len("Add items separated by commas (,)."),
   #   max_length=len("Add items separated by commas (,)."),
   # )
    not_started = discord.ui.TextInput(
        label='Not started',
        style=discord.TextStyle.paragraph,
        required=False,
        placeholder='e.g., Hollow Knight, Ori and the Blind Forest — or one per line'
    )
    in_progress = discord.ui.TextInput(
        label='In progress',
        style=discord.TextStyle.paragraph,
        required=False,
        placeholder='e.g., Elden Ring, Hades — or one per line'
    )

    def __init__(self, user_id: int, user_name: str):
        super().__init__()
        self._user_id = user_id
        self._user_name = user_name

    async def on_submit(self, interaction: discord.Interaction):
        def parse_list(raw: str) -> list[str]:
            if not raw:
                return []
            # Accept commas, semicolons, or new lines
            parts = re.split(r"[,;\n]+", str(raw))
            return [p.strip() for p in parts if p.strip()]

        def norm(s: str) -> str:
            return " ".join(s.split()).lower()

        ns_raw = parse_list(str(self.not_started.value))
        ip_raw = parse_list(str(self.in_progress.value))

        # --- unchanged logic below ---
        ns_map = {norm(g): g for g in ns_raw}
        ip_map = {norm(g): g for g in ip_raw}

        # In progress wins if listed in both
        for key in set(ns_map.keys()) & set(ip_map.keys()):
            ns_map.pop(key, None)

        added_ns, added_ip = [], []
        moved_to_ns, moved_to_ip = [], []
        unchanged = []

        def upsert(game_display: str, target_status: str, added_list: list[str], moved_list: list[str]):
            c.execute(
                'SELECT game_name, status FROM solo_backlogs WHERE user_id = ? AND LOWER(game_name) = LOWER(?)',
                (self._user_id, game_display)
            )
            row = c.fetchone()

            if not row:
                c.execute(
                    'INSERT INTO solo_backlogs (user_id, user_name, game_name, status) VALUES (?, ?, ?, ?)',
                    (self._user_id, self._user_name, game_display, target_status)
                )
                added_list.append(game_display)
                return

            existing_name, existing_status = row
            if existing_status != target_status:
                c.execute(
                    'UPDATE solo_backlogs SET status = ?, user_name = ? WHERE user_id = ? AND LOWER(game_name) = LOWER(?)',
                    (target_status, self._user_name, self._user_id, game_display)
                )
                moved_list.append(existing_name)
            else:
                unchanged.append(existing_name)

        for g in ns_map.values():
            upsert(g, "not started", added_ns, moved_to_ns)
        for g in ip_map.values():
            upsert(g, "in progress", added_ip, moved_to_ip)

        conn.commit()

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

def is_completed_for_user(user_id: str, game_name: str) -> bool:
    c.execute('''
        SELECT 1 FROM solo_backlogs
        WHERE user_id = ? AND LOWER(game_name) = LOWER(?) AND status = "completed"
        LIMIT 1
    ''', (user_id, game_name))
    return c.fetchone() is not None

def strike_if_done(user_id: str, game_name: str) -> str:
    return f"~~{game_name}~~ ✅" if is_completed_for_user(user_id, game_name) else game_name

def ensure_challenge_stats_row(user_id: str):
    c.execute("INSERT OR IGNORE INTO challenge_stats (user_id) VALUES (?)", (user_id,))
    conn.commit()

  
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

    footer_note = (
        "\n\n*If the button timed out, use* `/whohunts` *and search for the game again, "
        "or join directly with* `/joinhunt`."
    )

    await interaction.response.send_message(
        f"**Players for '{canonical_name}' ({len(users)} hunters):**\n{user_list}{footer_note}",
        view=view
    )

# Autocomplete for game names
@who_hunts.autocomplete("game_name")
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


@bot.tree.command(name="mysolohunts", description="Show your active solo hunts (paginated).")
async def my_solo_hunts(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    c.execute("""
        SELECT game_name, status
        FROM solo_backlogs
        WHERE user_id = ?
          AND status IN ("in progress", "not started")
        ORDER BY
            CASE status
                WHEN "in progress" THEN 0
                WHEN "not started" THEN 1
            END,
            game_name COLLATE NOCASE ASC
    """, (user_id,))

    rows = c.fetchall()

    if not rows:
        await interaction.response.send_message(
            "You don't have any active solo hunts right now.",
            ephemeral=True
        )
        return

    lines = []
    for name, status in rows:
        if status == "in progress":
            lines.append(f"▶ **{name}** _(In Progress)_")
        else:
            lines.append(f"• {name} _(Not Started)_")

    pages = chunk_lines(lines)

    title = f"🎯 {interaction.user.display_name}'s Active Solo Hunts"

    view = PagedTextView(
        pages=pages,
        title=title,
        invoker_id=interaction.user.id
    )

    # ❗ NOT ephemeral
    await interaction.response.send_message(
        embed=view.make_embed(),
        view=view
    )



# Command: /starthunt
@bot.tree.command(name="starthunt", description="Set a game's status to 'in progress.'")
@app_commands.describe(game_name="Select a game from your 'not started' solo backlog")
async def start_hunt(interaction: discord.Interaction, game_name: str):
    c.execute('''
        UPDATE solo_backlogs 
        SET status = "in progress" 
        WHERE user_id = ? AND game_name = ? AND status = "not started"
    ''', (interaction.user.id, game_name))
    conn.commit()
    if c.rowcount:
        await interaction.response.send_message(f"Game '{game_name}' is now 'in progress'.")
    else:
        await interaction.response.send_message(f"Cannot start '{game_name}': either it doesn't exist or it's already started.")


@start_hunt.autocomplete('game_name')
async def starthunt_autocomplete(interaction: discord.Interaction, current: str):
    user_id = str(interaction.user.id)
    like = f"%{current}%"
    c.execute(
        '''SELECT game_name FROM solo_backlogs
           WHERE user_id = ? AND status = 'not started' AND game_name LIKE ? COLLATE NOCASE
           ORDER BY game_name ASC LIMIT 25''',
        (user_id, like)
    )
    return [app_commands.Choice(name=row[0], value=row[0]) for row in c.fetchall()]


# Command: /giveup - Remove a game from your solo backlog.
@bot.tree.command(name="giveup", description="Remove a game from your solo backlog.")
async def give_up(interaction: discord.Interaction, game_name: str):
    c.execute('DELETE FROM solo_backlogs WHERE user_id = ? AND game_name = ?', (interaction.user.id, game_name))
    conn.commit()
    if c.rowcount:
      # ✅ Only evaluate after a successful finish
#        evaluate_and_unlock_marks(user_id)
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
      # ✅ Only evaluate after a successful finish
#        evaluate_and_unlock_marks(user_id)
        await interaction.response.send_message(f"Game '{game_name}' is now 'completed'.")
    else:
        await interaction.response.send_message(f"Cannot finish '{game_name}': either it doesn't exist or it's not in progress.")

@finish_hunt.autocomplete('game_name')
async def finishhunt_autocomplete(interaction: discord.Interaction, current: str):
    user_id = str(interaction.user.id)
    like = f"%{current}%"
    c.execute(
        '''SELECT game_name FROM solo_backlogs
           WHERE user_id = ? AND status = 'in progress' AND game_name LIKE ? COLLATE NOCASE
           ORDER BY game_name ASC LIMIT 25''',
        (user_id, like)
    )
    return [app_commands.Choice(name=row[0], value=row[0]) for row in c.fetchall()]



# Command: /newmasshunts
@bot.tree.command(name="newmasshunts", description="Add multiple games to your solo backlog via a modal.")
async def new_mass_hunts(interaction: discord.Interaction):
    await interaction.response.send_modal(MassHuntsModal(interaction.user.id, interaction.user.name))


# Command: /myfinishedhunts
class PagedTextView(discord.ui.View):
    def __init__(self, pages: list[str], title: str, invoker_id: int):
        super().__init__(timeout=300)
        self.pages = pages
        self.title = title
        self.invoker_id = invoker_id
        self.page = 0
        self._update_buttons()

    def _update_buttons(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = False
        self.children[0].disabled = self.page == 0
        self.children[1].disabled = self.page >= (len(self.pages) - 1)

    def make_embed(self) -> discord.Embed:
        e = discord.Embed(title=self.title, description=self.pages[self.page], color=0x2b2d31)
        e.set_footer(text=f"Page {self.page+1}/{len(self.pages)}")
        return e

    async def _gate(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message("Only the person who ran the command can use these buttons.", ephemeral=True)
            return True
        return False

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._gate(interaction):
            return
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._gate(interaction):
            return
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)


def chunk_lines(lines: list[str], max_chars: int = 1500) -> list[str]:
    pages = []
    buf = ""
    for line in lines:
        if len(buf) + len(line) + 1 > max_chars:
            pages.append(buf.rstrip())
            buf = ""
        buf += line + "\n"
    if buf.strip():
        pages.append(buf.rstrip())
    return pages or ["(no entries)"]


@bot.tree.command(name="myfinishedhunts", description="Show your completed solo hunts (optional month/year).")
async def my_finished_hunts(interaction: discord.Interaction, month: int = None, year: int = None):
    user_id = str(interaction.user.id)

    query = '''
        SELECT game_name, completion_date
        FROM solo_backlogs
        WHERE user_id = ? AND status = "completed"
    '''
    params = [user_id]

    if month and year:
        query += ' AND strftime("%m", completion_date) = ? AND strftime("%Y", completion_date) = ?'
        params.extend([f"{int(month):02}", str(year)])

    query += ' ORDER BY completion_date DESC, game_name COLLATE NOCASE ASC'

    c.execute(query, tuple(params))
    rows = c.fetchall()

    if not rows:
        await interaction.response.send_message("No completed games found for that period.", ephemeral=True)
        return

    lines = [f"• **{name}** — {date}" for (name, date) in rows]
    pages = chunk_lines(lines)

    title = "✅ My Finished Hunts"
    if month and year:
        title += f" — {int(month):02}/{year}"

    view = PagedTextView(pages, title, interaction.user.id)
    await interaction.response.send_message(embed=view.make_embed(), view=view, ephemeral=True)

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
class HelpView(discord.ui.View):
    def __init__(self, is_admin: bool):
        super().__init__(timeout=300)
        self.is_admin = is_admin

        self.add_item(self.SectionButton("Quick Start", "quick"))
        self.add_item(self.SectionButton("Co-op Hunts", "coop"))
        self.add_item(self.SectionButton("Solo Hunts", "solo"))

        self.add_item(self.SectionButton("Challenges", "challenges", row=1))
        self.add_item(self.SectionButton("Cards", "cards", row=1))
        self.add_item(self.SectionButton("Info", "info", row=1))
        self.add_item(self.SectionButton("Fun", "fun", row=1))
        if is_admin:
            self.add_item(self.SectionButton("Admin", "admin", row=1))

    class SectionButton(discord.ui.Button):
        def __init__(self, label: str, key: str, row: int = 0):
            super().__init__(label=label, style=discord.ButtonStyle.primary, row=row)
            self.key = key

        async def callback(self, interaction: discord.Interaction):
            embed = build_ledger_help_embed(self.key, is_admin=interaction.user.guild_permissions.administrator)
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=self.view)
            else:
                await interaction.response.edit_message(embed=embed, view=self.view)


def build_ledger_help_embed(section: str, is_admin: bool) -> discord.Embed:
    e = discord.Embed(color=0x2b2d31)
    base_note = "Use the buttons below to switch sections."

    if section == "quick":
        e.title = "A Hunter’s Ledger — Help"
        e.description = (
            "**Quick Start**\n"
            "1) Add solo hunts: `/newhunt` or `/newmasshunts`\n"
            "2) View solo hunts: `/mysolohunts`\n"
            "3) Start a hunt: `/starthunt`\n"
            "4) Finish a hunt: `/finishhunt`\n"
            "5) Want a random pick? `/givemeahunt`\n\n"
            f"{base_note}"
        )
        return e

    if section == "coop":
        e.title = "Co-op / Multiplayer Hunts"
        e.description = (
            "• Track a co-op game: `/trackhunt \"name\"`\n"
            "• Browse all tracked: `/showhunts`\n"
            "• See who’s hunting: `/whohunts \"name\"`\n"
            "• Join/Leave: `/joinhunt \"name\"` / `/leavehunt \"name\"`\n"
            "• Call everyone for a game: `/callhunters \"name\" [message]`\n"
        )
        return e

    if section == "solo":
        e.title = "Solo Hunts"
        e.description = (
            "• Add: `/newhunt \"name\"`\n"
            "• Mass add: `/newmasshunts`\n"
            "• View active: `/mysolohunts`\n"
            "• Start: `/starthunt \"name\"`\n"
            "• Finish: `/finishhunt \"name\"`\n"
            "• Drop: `/giveup \"name\"`\n"
            "• Completed list: `/myfinishedhunts [month] [year]`\n"
            "• Rate a completed hunt: `/ratehunt \"name\" 1-5 [comments]`\n"
        )
        return e

    if section == "challenges":
        e.title = "Challenges"
        e.description = (
            "• Your Next 10 list: `/mynext10`\n"
            "• Reset Next 10: `/resetnext10`\n\n"
            "• Your A–Z list: `/azhunts`\n"
            "• Reset A–Z: `/resetaz`\n\n"
            "_Lists auto-strike completed hunts based on your solo backlog._"
        )
        return e

    if section == "cards":
        e.title = "Completion Cards"
        e.description = (
            "• Generate a completion card:\n"
            "  `/generatecard \"game\" [genre]`\n\n"
            "Genres (current): `fps`, `horror`, `racing`, `rpg`, `strategy`\n"
        )
        return e

    if section == "info":
        e.title = "Bot Info"
        e.description = (
            "• Version: `/botversion`\n"
            "• Health: `/healthcheck`\n"
        )
        return e

    if section == "fun":
        e.title = "Fun"
        e.description = "• Coming soon 😄"
        return e

    if section == "admin" and is_admin:
        e.title = "Admin"
        e.description = (
            "• Rename tracked hunt: `/changehunt \"old\" \"new\"`\n"
            "• Remove tracked hunt: `/forgethunt \"name\"`\n"
            "• Remove hunter from all: `/forgethunter @user`\n"
        )
        return e

    return build_ledger_help_embed("quick", is_admin=is_admin)


@bot.tree.command(name="help", description="Shows help sections with buttons.")
async def help_command(interaction: discord.Interaction):
    is_admin = bool(interaction.guild and interaction.user.guild_permissions.administrator)
    view = HelpView(is_admin=is_admin)
    embed = build_ledger_help_embed("quick", is_admin=is_admin)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

  
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

# Command: Show bot version and information
@bot.tree.command(name="botversion", description="Show bot version and additional information")
async def bot_version(interaction: Interaction):
    version_info = "**A Hunters Ledger v3.0**\nCreated by Tide44\nGitHub: [A Hunters Ledger](https://github.com/Tide44-cmd/HuntersLedger)"
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


ALLOWED_GENRES = {"fps", "horror", "racing", "rpg", "strategy"}

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
@app_commands.describe(
    game_name="Pick a game you've completed (autocomplete)",
    genre="Optional: pick a theme (autocomplete)"
)
async def generate_card(interaction: discord.Interaction, game_name: str, genre: str = None):
    user_id = str(interaction.user.id)
    user_name = interaction.user.display_name
    avatar_url = interaction.user.display_avatar.url

    # Validate/normalise genre
    genre_clean = None
    if genre:
        genre_clean = genre.strip().lower()
        if genre_clean not in ALLOWED_GENRES:
            await interaction.response.send_message(
                "That genre isn't available.\n"
                f"Available genres: {', '.join(sorted(ALLOWED_GENRES))}",
                ephemeral=True
            )
            return

    await interaction.response.defer()

    # Case-insensitive lookup + ensure completed
    c.execute("""
        SELECT completion_date
        FROM solo_backlogs
        WHERE user_id = ?
          AND LOWER(game_name) = LOWER(?)
          AND status = 'completed'
        LIMIT 1
    """, (user_id, game_name))

    row = c.fetchone()
    if not row:
        await interaction.followup.send(
            f"You have not completed '{game_name}', so a card cannot be generated.",
            ephemeral=True
        )
        return

    raw_date = row[0]

    # completion_date can be NULL if older entries existed before you started storing dates
    # If it's NULL, just show "Completed" without a date
    if raw_date:
        try:
            # Stored as YYYY-MM-DD via DATE("now")
            dt = datetime.strptime(raw_date, "%Y-%m-%d")
            # Windows-safe (avoid %-d)
            date_str = dt.strftime("%d %b %Y").lstrip("0")
        except Exception:
            # Fallback: show whatever is stored
            date_str = str(raw_date)
    else:
        date_str = "Completed"

    # IMPORTANT: pass date_str (string), not the datetime object
    banner_path = await generate_completion_banner(
        game_name=game_name,
        user_name=user_name,
        completion_date=date_str,
        avatar_url=avatar_url,
        genre=genre_clean
    )

    if banner_path:
        await interaction.followup.send(
            f"Here is your completion card, {interaction.user.mention}! 🎉",
            file=discord.File(banner_path)
        )
        try:
            os.remove(banner_path)
        except OSError:
            pass
    else:
        await interaction.followup.send(
            "Error generating the completion card. Please try again later.",
            ephemeral=True
        )


# ---- Autocomplete: completed games, most recent first ----
@generate_card.autocomplete("game_name")
async def generatecard_game_autocomplete(interaction: discord.Interaction, current: str):
    user_id = str(interaction.user.id)
    like = f"%{current}%"
    c.execute('''
        SELECT game_name
        FROM solo_backlogs
        WHERE user_id = ?
          AND status = "completed"
          AND game_name LIKE ? COLLATE NOCASE
        ORDER BY completion_date IS NULL, completion_date DESC, game_name COLLATE NOCASE ASC
        LIMIT 25
    ''', (user_id, like))
    return [app_commands.Choice(name=r[0], value=r[0]) for r in c.fetchall()]


# ---- Autocomplete: genre "autoselect" ----
@generate_card.autocomplete("genre")
async def generatecard_genre_autocomplete(interaction: discord.Interaction, current: str):
    cur = (current or "").strip().lower()
    options = sorted(ALLOWED_GENRES)
    filtered = [g for g in options if cur in g]
    return [app_commands.Choice(name=g, value=g) for g in filtered[:25]]

# Test image generate End
@bot.tree.command(name="mynext10", description="Create (if needed) and view your Next 10 hunts challenge list.")
async def my_next10(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    ensure_challenge_stats_row(user_id)

    # Does a list exist?
    c.execute("SELECT 1 FROM next10_lists WHERE user_id = ?", (user_id,))
    has_list = c.fetchone() is not None

    if not has_list:
        # Pull eligible games: not started or in progress
        c.execute('''
            SELECT game_name
            FROM solo_backlogs
            WHERE user_id = ? AND status IN ("not started", "in progress")
        ''', (user_id,))
        pool = [r[0] for r in c.fetchall()]
        if len(pool) < 1:
            await interaction.response.send_message(
                "You don't have any solo hunts in **Not Started** or **In Progress** to build a Next 10 list.",
                ephemeral=True
            )
            return

        random.shuffle(pool)
        picked = pool[:10]

        c.execute("INSERT INTO next10_lists (user_id) VALUES (?)", (user_id,))
        for g in picked:
            c.execute(
                "INSERT OR IGNORE INTO next10_items (user_id, game_name) VALUES (?, ?)",
                (user_id, g)
            )
        conn.commit()

    # Load list
    c.execute('''
        SELECT game_name
        FROM next10_items
        WHERE user_id = ?
        ORDER BY id ASC
    ''', (user_id,))
    items = [r[0] for r in c.fetchall()]

    if not items:
        # Safety: list exists but items missing
        await interaction.response.send_message(
            "Your Next 10 list exists but is empty. Use `/resetnext10` then `/mynext10` to rebuild it.",
            ephemeral=True
        )
        return

    # Build display with strike-through if now completed
    display_lines = [f"{i+1}. {strike_if_done(user_id, name)}" for i, name in enumerate(items)]
    completed_now = sum(1 for name in items if is_completed_for_user(user_id, name))

    # If all complete -> stamp + prompt reset
    if completed_now == len(items):
        c.execute('''
            UPDATE challenge_stats
            SET next10_completed_count = next10_completed_count + 1
            WHERE user_id = ?
        ''', (user_id,))
        conn.commit()

        c.execute("SELECT next10_completed_count FROM challenge_stats WHERE user_id = ?", (user_id,))
        count = c.fetchone()[0]

        msg = (
            f"🏁 **Next 10 complete!**\n"
            f"You've completed your Next10 list **{count}** time(s).\n\n"
            f"Run `/resetnext10` to generate a fresh list."
        )
        await interaction.response.send_message(msg, ephemeral=True)
        return

    header = f"🎯 **{interaction.user.display_name}'s Next 10** — {completed_now}/10 completed"
    await _send_long(interaction, header, display_lines)


@bot.tree.command(name="resetnext10", description="Delete your current Next 10 list so you can generate a new one.")
async def reset_next10(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    c.execute("DELETE FROM next10_items WHERE user_id = ?", (user_id,))
    c.execute("DELETE FROM next10_lists WHERE user_id = ?", (user_id,))
    conn.commit()

    await interaction.response.send_message(
        "✅ Your Next 10 list has been cleared. Run `/mynext10` to generate a new one.",
        ephemeral=True
    )

import string

def normalise_title_for_az(title: str) -> str:
    """
    Normalises a game title for A–Z challenges by removing common
    leading articles like 'The ' and 'A '.
    """
    if not title:
        return title

    t = title.strip()

    for prefix in ("the ", "a "):
        if t.lower().startswith(prefix):
            return t[len(prefix):].lstrip()

    return t


def pick_game_for_letter(user_id: str, letter: str) -> str | None:
    letter = letter.upper()

    # Only eligible games (not started / in progress)
    c.execute('''
        SELECT game_name
        FROM solo_backlogs
        WHERE user_id = ?
          AND status IN ("not started", "in progress")
    ''', (user_id,))

    candidates = []
    for (game_name,) in c.fetchall():
        normalised = normalise_title_for_az(game_name)
        if normalised and normalised[0].upper() == letter:
            candidates.append(game_name)

    if not candidates:
        return None

    return random.choice(candidates)


@bot.tree.command(name="azhunts", description="Create (if needed) and view your A–Z hunts list.")
async def az_hunts(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    ensure_challenge_stats_row(user_id)

    c.execute("SELECT 1 FROM az_lists WHERE user_id = ?", (user_id,))
    has_list = c.fetchone() is not None

    if not has_list:
        c.execute("INSERT INTO az_lists (user_id) VALUES (?)", (user_id,))
        for letter in string.ascii_uppercase:
            game = pick_game_for_letter(user_id, letter)
            c.execute(
                "INSERT OR REPLACE INTO az_items (user_id, letter, game_name) VALUES (?, ?, ?)",
                (user_id, letter, game)  # game can be None => NA
            )
        conn.commit()
    else:
        # Try to populate any NAs
        c.execute('''
            SELECT letter
            FROM az_items
            WHERE user_id = ? AND (game_name IS NULL OR game_name = "")
        ''', (user_id,))
        na_letters = [r[0] for r in c.fetchall()]
        changed = False
        for letter in na_letters:
            game = pick_game_for_letter(user_id, letter)
            if game:
                c.execute('''
                    UPDATE az_items
                    SET game_name = ?
                    WHERE user_id = ? AND letter = ?
                ''', (game, user_id, letter))
                changed = True
        if changed:
            conn.commit()

    # Load list A–Z
    c.execute('''
        SELECT letter, game_name
        FROM az_items
        WHERE user_id = ?
        ORDER BY letter ASC
    ''', (user_id,))
    rows = c.fetchall()

    lines = []
    playable_total = 0
    playable_done = 0

    for letter, game_name in rows:
        if not game_name:
            lines.append(f"**{letter}:** NA")
            continue

        playable_total += 1
        if is_completed_for_user(user_id, game_name):
            playable_done += 1
            lines.append(f"**{letter}:** ~~{game_name}~~ ✅")
        else:
            lines.append(f"**{letter}:** {game_name}")

    if playable_total > 0 and playable_done == playable_total:
        c.execute('''
            UPDATE challenge_stats
            SET az_completed_count = az_completed_count + 1
            WHERE user_id = ?
        ''', (user_id,))
        conn.commit()

        c.execute("SELECT az_completed_count FROM challenge_stats WHERE user_id = ?", (user_id,))
        count = c.fetchone()[0]
        await interaction.response.send_message(
            f"🏁 **A–Z complete!** You’ve finished your A–Z list **{count}** time(s).\n"
            f"Run `/resetaz` to generate a fresh A–Z list.",
            ephemeral=True
        )
        return

    header = f"🔤 **{interaction.user.display_name}'s A–Z Hunts** — {playable_done}/{playable_total} completed (excluding NA)"
    await _send_long(interaction, header, lines)


@bot.tree.command(name="resetaz", description="Delete your current A–Z list so you can generate a new one.")
async def reset_az(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    c.execute("DELETE FROM az_items WHERE user_id = ?", (user_id,))
    c.execute("DELETE FROM az_lists WHERE user_id = ?", (user_id,))
    conn.commit()

    await interaction.response.send_message(
        "✅ Your A–Z list has been cleared. Run `/azhunts` to generate a new one.",
        ephemeral=True
    )

# Hunter's Marks

def seed_hunting_marks():
    marks = [
        # key, slot_index, is_hidden
        ("MARK_FIRST_BLOOD", 0, 0),
        ("MARK_50",          1, 0),
        ("MARK_100",         2, 0),
        ("MARK_150",         3, 0),
        ("MARK_FOCUSED_MONTH", 4, 0),
        ("MARK_NEXT10",        5, 0),
        ("MARK_AZ",            6, 0),
        ("MARK_RELENTLESS",    7, 0),
        ("MARK_LONG_HUNT",     8, 0),
        ("MARK_HAVEN_TOUCHED", 9, 0),

        # Hidden 11th
        ("MARK_BROKEN_OATH", 10, 1),
    ]
    for key, slot, hidden in marks:
        c.execute(
            "INSERT OR IGNORE INTO hunting_marks (key, slot_index, is_hidden) VALUES (?, ?, ?)",
            (key, slot, hidden)
        )
    conn.commit()

seed_hunting_marks()

from datetime import datetime, timedelta

def get_total_completed_hunts(user_id: str) -> int:
    c.execute("""
        SELECT COUNT(*)
        FROM solo_backlogs
        WHERE user_id = ? AND status = 'completed'
    """, (user_id,))
    return int(c.fetchone()[0] or 0)

def get_total_abandoned_hunts(user_id: str) -> int:
    c.execute("""
        SELECT COUNT(*)
        FROM solo_backlogs
        WHERE user_id = ? AND status = 'abandoned'
    """, (user_id,))
    return int(c.fetchone()[0] or 0)

def get_completed_in_month(user_id: str, year: int, month: int) -> int:
    c.execute("""
        SELECT COUNT(*)
        FROM solo_backlogs
        WHERE user_id = ?
          AND status = 'completed'
          AND completion_date IS NOT NULL
          AND strftime('%Y', completion_date) = ?
          AND strftime('%m', completion_date) = ?
    """, (user_id, str(year), f"{month:02d}"))
    return int(c.fetchone()[0] or 0)

def get_next10_completed_count(user_id: str) -> int:
    # from challenge_stats you already added
    c.execute("""
        SELECT next10_completed_count
        FROM challenge_stats
        WHERE user_id = ?
    """, (user_id,))
    row = c.fetchone()
    return int(row[0] or 0) if row else 0

def get_az_completed_count(user_id: str) -> int:
    c.execute("""
        SELECT az_completed_count
        FROM challenge_stats
        WHERE user_id = ?
    """, (user_id,))
    row = c.fetchone()
    return int(row[0] or 0) if row else 0

def get_months_with_any_completion(user_id: str) -> int:
    c.execute("""
        SELECT COUNT(DISTINCT strftime('%Y-%m', completion_date))
        FROM solo_backlogs
        WHERE user_id = ?
          AND status = 'completed'
          AND completion_date IS NOT NULL
    """, (user_id,))
    return int(c.fetchone()[0] or 0)

def get_longest_weekly_streak(user_id: str) -> int:
    """
    Simple streak measure: number of consecutive weeks with >=1 completion,
    ending at the most recent completed week.

    You can swap this later for daily streaks; this is more forgiving and realistic.
    """
    c.execute("""
        SELECT completion_date
        FROM solo_backlogs
        WHERE user_id = ?
          AND status = 'completed'
          AND completion_date IS NOT NULL
        ORDER BY completion_date ASC
    """, (user_id,))
    dates = [r[0] for r in c.fetchall()]
    if not dates:
        return 0

    # map to ISO year-week
    weeks = []
    for d in dates:
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
        except Exception:
            continue
        weeks.append(dt.isocalendar()[:2])  # (year, week)

    weeks = sorted(set(weeks))
    if not weeks:
        return 0

    # compute longest consecutive run overall
    longest = 1
    cur = 1

    def week_index(yw):
        y, w = yw
        return y * 53 + w  # safe monotonic-ish index

    for i in range(1, len(weeks)):
        if week_index(weeks[i]) == week_index(weeks[i-1]) + 1:
            cur += 1
            longest = max(longest, cur)
        else:
            cur = 1
    return longest

def unlock_mark(user_id: str, key: str) -> bool:
    c.execute("""
        INSERT OR IGNORE INTO user_hunting_marks (user_id, key)
        VALUES (?, ?)
    """, (user_id, key))
    conn.commit()
    return c.rowcount > 0

def evaluate_and_unlock_marks(user_id: str) -> list[str]:
    """
    Secret rules live here. This function can be called:
    - after /finishhunt
    - after /giveup
    - whenever user runs /myhuntingmarks
    so it supports retroactive unlocks naturally.
    """
    newly = []

    total_completed = get_total_completed_hunts(user_id)
    total_abandoned = get_total_abandoned_hunts(user_id)

    now = datetime.utcnow()
    # current month in UTC (fine for “calendar month” unless you want local time)
    month_completed = get_completed_in_month(user_id, now.year, now.month)

    next10_count = get_next10_completed_count(user_id)
    az_count = get_az_completed_count(user_id)

    months_with_completions = get_months_with_any_completion(user_id)
    weekly_streak = get_longest_weekly_streak(user_id)

    # --- Public marks ---
    if total_completed >= 1:
        if unlock_mark(user_id, "MARK_FIRST_BLOOD"):
            newly.append("MARK_FIRST_BLOOD")

    if total_completed >= 50:
        if unlock_mark(user_id, "MARK_50"):
            newly.append("MARK_50")

    if total_completed >= 100:
        if unlock_mark(user_id, "MARK_100"):
            newly.append("MARK_100")

    if total_completed >= 150:
        if unlock_mark(user_id, "MARK_150"):
            newly.append("MARK_150")

    if month_completed >= 10:
        if unlock_mark(user_id, "MARK_FOCUSED_MONTH"):
            newly.append("MARK_FOCUSED_MONTH")

    if next10_count >= 1:
        if unlock_mark(user_id, "MARK_NEXT10"):
            newly.append("MARK_NEXT10")

    if az_count >= 1:
        if unlock_mark(user_id, "MARK_AZ"):
            newly.append("MARK_AZ")

    # “Relentless” – stick with it over time (example: 6 distinct months)
    if months_with_completions >= 6:
        if unlock_mark(user_id, "MARK_RELENTLESS"):
            newly.append("MARK_RELENTLESS")

    # “Long Hunt” – example: 8-week streak
    if weekly_streak >= 8:
        if unlock_mark(user_id, "MARK_LONG_HUNT"):
            newly.append("MARK_LONG_HUNT")

    # “Haven Touched” – composite prestige (example)
    # (This one is secret by design; users just see it appear eventually.)
    if (
        total_completed >= 100
        and next10_count >= 1
        and az_count >= 1
        and months_with_completions >= 6
    ):
        if unlock_mark(user_id, "MARK_HAVEN_TOUCHED"):
            newly.append("MARK_HAVEN_TOUCHED")

    # --- Hidden mark (negative behaviour / spice) ---
    # Example: abandon 20+ hunts
    if total_abandoned >= 20:
        if unlock_mark(user_id, "MARK_BROKEN_OATH"):
            newly.append("MARK_BROKEN_OATH")

    return newly

MARK_SLOTS = {
    0: (120, 140),
    1: (320, 140),
    2: (520, 140),
    3: (720, 140),
    4: (120, 340),
    5: (320, 340),
    6: (520, 340),
    7: (720, 340),
    8: (220, 540),
    9: (620, 540),
    10: (420, 540),  # hidden mark slot (example placement)
}

from PIL import Image, ImageDraw, ImageFont
import os

RES_MARKS_DIR = os.path.join("resources", "marks")

def build_hunting_marks_board(unlocked_keys: list[str]) -> str:
    board_path = os.path.join(RES_MARKS_DIR, "board.png")
    if not os.path.exists(board_path):
        raise FileNotFoundError("Missing resources/marks/board.png")

    board = Image.open(board_path).convert("RGBA")
    draw = ImageDraw.Draw(board)

    # If nothing unlocked, add the single line of text
    if not unlocked_keys:
        msg = "Your marks are earned through dedication, not disclosure."
        # Pick a font you already ship, or use a default
        font_path = os.path.join("resources", "fonts", "Cinzel-Regular.ttf")
        font = ImageFont.truetype(font_path, 34) if os.path.exists(font_path) else ImageFont.load_default()

        # center it
        w, h = board.size
        tw, th = draw.textbbox((0, 0), msg, font=font)[2:]
        x = (w - tw) // 2
        y = h - 120
        # subtle outline for readability
        for ox, oy in [(-2,0),(2,0),(0,-2),(0,2)]:
            draw.text((x+ox, y+oy), msg, font=font, fill="black")
        draw.text((x, y), msg, font=font, fill="white")
    else:
        # Draw unlocked badges
        # Load slot indexes for each key
        c.execute("SELECT key, slot_index FROM hunting_marks")
        slot_map = {k: i for (k, i) in c.fetchall()}

        for key in unlocked_keys:
            slot = slot_map.get(key)
            if slot is None:
                continue
            pos = MARK_SLOTS.get(slot)
            if not pos:
                continue

            badge_path = os.path.join(RES_MARKS_DIR, f"{key}.png")
            if not os.path.exists(badge_path):
                # If badge missing, just skip (so you can add art later)
                continue

            badge = Image.open(badge_path).convert("RGBA")
            board.alpha_composite(badge, dest=pos)

    out_path = os.path.join("temp", f"hunting_marks_{os.urandom(6).hex()}.png")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    board.save(out_path, "PNG")
    return out_path

#@bot.tree.command(name="myhuntingmarks", description="View your Marks of the Hunt.")
#async def my_hunting_marks(interaction: discord.Interaction):
#    user_id = str(interaction.user.id)
#
#    await interaction.response.defer(ephemeral=True)
#
#    # retroactive + current evaluation
#    evaluate_and_unlock_marks(user_id)
#
#    c.execute("""
#        SELECT key
#        FROM user_hunting_marks
#        WHERE user_id = ?
#    """, (user_id,))
#    unlocked = [r[0] for r in c.fetchall()]
#
#    try:
#        img_path = build_hunting_marks_board(unlocked)
#    except Exception as e:
#        await interaction.followup.send(f"Error generating marks board: {e}", ephemeral=True)
#        return
#
#    await interaction.followup.send(
#        file=discord.File(img_path),
#        ephemeral=True
#    )
#
#    try:
#        os.remove(img_path)
#    except OSError:
#        pass


# Run the bot
bot.run(TOKEN)
