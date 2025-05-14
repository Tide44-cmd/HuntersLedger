import discord
from discord.ext import commands
from discord import Interaction
from discord import ButtonStyle
from discord.ui import Button, View
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
    # Check if the game is already in the database
    c.execute("SELECT * FROM games WHERE game_name = ?", (game_name,))
    if c.fetchone():
        await interaction.response.send_message(f"The game '{game_name}' is already being tracked.")
    else:
        # Insert the game into the database
        c.execute("INSERT INTO games (game_name) VALUES (?)", (game_name,))
        conn.commit()
        await interaction.response.send_message(f"Game '{game_name}' has been added to the list.")


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
async def who_hunts(interaction: discord.Interaction, game_name: str):
    c.execute("SELECT id FROM games WHERE game_name = ?", (game_name,))
    game = c.fetchone()
    if game:
        game_id = game[0]
        c.execute("SELECT user_name FROM user_games WHERE game_id = ?", (game_id,))
        users = c.fetchall()
        if users:
            user_list = "\n".join([user[0] for user in users])
            await interaction.response.send_message(
                f"**Players for '{game_name}' ({len(users)} hunters):**\n{user_list}"
            )
        else:
            await interaction.response.send_message(f"No one is currently signed up to hunt '{game_name}'.")
    else:
        await interaction.response.send_message(f"Game '{game_name}' not found.")

# Command: Join a hunt
@bot.tree.command(name="joinhunt", description="Add yourself to a game's player list")
async def join_hunt(interaction: discord.Interaction, game_name: str):
    user_id = str(interaction.user.id)
    user_name = str(interaction.user)
    c.execute("SELECT id FROM games WHERE game_name = ?", (game_name,))
    game = c.fetchone()
    if game:
        game_id = game[0]
        c.execute(
            "SELECT * FROM user_games WHERE user_id = ? AND game_id = ?",
            (user_id, game_id)
        )
        if not c.fetchone():
            c.execute(
                "INSERT INTO user_games (user_id, user_name, game_id) VALUES (?, ?, ?)",
                (user_id, user_name, game_id)
            )
            conn.commit()
            await interaction.response.send_message(
                f"{interaction.user.mention}, you've joined the hunt for '{game_name}'."
            )
        else:
            await interaction.response.send_message(
                f"{interaction.user.mention}, you're already hunting '{game_name}'."
            )
    else:
        await interaction.response.send_message(f"Game '{game_name}' not found.")

# Command: Leave a hunt
@bot.tree.command(name="leavehunt", description="Remove yourself from a game's player list")
async def leave_hunt(interaction: discord.Interaction, game_name: str):
    user_id = str(interaction.user.id)
    c.execute("SELECT id FROM games WHERE game_name = ?", (game_name,))
    game = c.fetchone()
    if game:
        game_id = game[0]
        c.execute("DELETE FROM user_games WHERE user_id = ? AND game_id = ?", (user_id, game_id))
        conn.commit()
        await interaction.response.send_message(f"{interaction.user.mention}, you've left the hunt for '{game_name}'.")
    else:
        await interaction.response.send_message(f"Game '{game_name}' not found.")

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
@bot.tree.command(name="forgethunt", description="Remove a game from the list (Admin Only)")
@commands.has_permissions(administrator=True)
async def forget_hunt(interaction: Interaction, game_name: str):
    c.execute("DELETE FROM games WHERE game_name = ?", (game_name,))
    conn.commit()
    await interaction.response.send_message(f"Game '{game_name}' has been removed.")

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
**Haven's Helper Commands:**

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
@bot.tree.command(name="callhunters", description="Tag all users signed up to a specific game")
async def call_hunters(interaction: Interaction, game_name: str):
    c.execute('''SELECT ug.user_id 
                 FROM user_games ug 
                 JOIN games g ON g.id = ug.game_id 
                 WHERE g.game_name = ?''', (game_name,))
    users = c.fetchall()
    if users:
        mentions = " ".join([f"<@{user[0]}>" for user in users])
        await interaction.response.send_message(f"Calling all hunters for '{game_name}':\n{mentions}")
    else:
        await interaction.response.send_message(f"No hunters are signed up for '{game_name}'.")

# Command: Tags all users singed up for any game with a custom message
@bot.tree.command(name="remindhunters", description="Tag all unique users signed up for any game with an optional message.")
async def remind_hunters(interaction: discord.Interaction, message: str = "Hi hunters, please review your backlog and remove any invalid entries!"):
    # Query unique users from the user_games table
    c.execute('SELECT DISTINCT user_id FROM user_games')
    users = c.fetchall()

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
        comp_banner = comp_banner.resize((450, 100), Image.LANCZOS)

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
