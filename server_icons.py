"""Per-server seasonal icons, editable through /servericon commands."""
from __future__ import annotations

import asyncio
import hashlib
from io import BytesIO
import logging
import os
from pathlib import Path
import re
import sqlite3
from datetime import date, datetime
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks
from PIL import Image, ImageOps, UnidentifiedImageError

log = logging.getLogger(__name__)
UK_TIME = ZoneInfo("Europe/London")
MAX_UPLOAD = 8 * 1024 * 1024
ICON_DIRECTORY = Path(__file__).resolve().parent / "resources" / "server_icons"
ICON_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
TIDE44_ID = 420996360699904000


def theme_name(value: str) -> str:
    value = value.strip().lower().replace(" ", "_")
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", value):
        raise ValueError("Use 1-40 letters, numbers, underscores or hyphens, starting with a letter.")
    return value


def validate_window(start: str, end: str) -> None:
    """End is exclusive; annual ranges may cross New Year."""
    if re.fullmatch(r"\d{2}-\d{2}", start) and re.fullmatch(r"\d{2}-\d{2}", end):
        date.fromisoformat("2000-" + start)
        date.fromisoformat("2000-" + end)
        if start == end:
            raise ValueError("Start and end must differ; the end date is the first day back.")
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", start) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", end):
        if date.fromisoformat(start) >= date.fromisoformat(end):
            raise ValueError("The end date must be after the start date.")
    else:
        raise ValueError("Use MM-DD for both dates (annual), or YYYY-MM-DD for both (one-off).")


def window_active(today: date, start: str, end: str) -> bool:
    if len(start) == 10:
        return start <= today.isoformat() < end
    current = today.strftime("%m-%d")
    return start <= current < end if start < end else current >= start or current < end


def scheduled_theme(windows, today: date) -> str:
    # One-off events beat annual events; then higher priority, then theme name.
    active = [row for row in windows if window_active(today, row["start"], row["end"])]
    if not active:
        return "default"
    return sorted(active, key=lambda row: (-int(len(row["start"]) == 10), -row["priority"], row["theme"]))[0]["theme"]


def normalize_icon(data: bytes) -> bytes:
    if len(data) > MAX_UPLOAD:
        raise ValueError("Upload an image smaller than 8 MiB.")
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"} or getattr(image, "is_animated", False):
                raise ValueError("Upload a static PNG, JPEG or WebP image.")
            image = ImageOps.exif_transpose(image)
            image = ImageOps.fit(image.convert("RGBA"), (512, 512), method=Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="PNG", optimize=True)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError("That file could not be read as a safe image.") from error


class IconStore:
    def __init__(self, path: str, icon_directory: Path | None = None):
        self.icon_directory = icon_directory if icon_directory is not None else ICON_DIRECTORY
        self.file_cache = {}
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS server_icon_settings (
                guild_id INTEGER PRIMARY KEY, mode TEXT NOT NULL DEFAULT 'paused',
                applied_digest TEXT, discord_icon_key TEXT, last_error TEXT
            );
            CREATE TABLE IF NOT EXISTS server_icon_assets (
                guild_id INTEGER NOT NULL, theme TEXT NOT NULL, image BLOB NOT NULL,
                PRIMARY KEY (guild_id, theme)
            );
            CREATE TABLE IF NOT EXISTS server_icon_windows (
                guild_id INTEGER NOT NULL, theme TEXT NOT NULL, start TEXT NOT NULL,
                end TEXT NOT NULL, priority INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, theme)
            );
        """)

    def ensure(self, guild_id: int):
        with self.db:
            created = self.db.execute("INSERT OR IGNORE INTO server_icon_settings (guild_id) VALUES (?)", (guild_id,)).rowcount
            if created:
                self.db.executemany("INSERT INTO server_icon_windows VALUES (?, ?, ?, ?, 0)", [
                    (guild_id, "halloween", "10-14", "11-01"),
                    (guild_id, "bonfire", "11-01", "11-06"),
                ])
        return self.db.execute("SELECT * FROM server_icon_settings WHERE guild_id = ?", (guild_id,)).fetchone()

    def windows(self, guild_id: int):
        return self.db.execute("SELECT * FROM server_icon_windows WHERE guild_id = ? ORDER BY start, theme", (guild_id,)).fetchall()

    def file_assets(self) -> dict[str, Path]:
        if not self.icon_directory.is_dir():
            return {}
        assets = {}
        for path in sorted(self.icon_directory.iterdir(), key=lambda p: p.name):
            if (path.is_file() and path.suffix.lower() in ICON_EXTENSIONS
                    and re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", path.stem)
                    and path.stem not in {"auto", "paused"}):
                previous = assets.get(path.stem)
                if previous is None or ICON_EXTENSIONS.index(path.suffix.lower()) < ICON_EXTENSIONS.index(previous.suffix.lower()):
                    assets[path.stem] = path
        return assets

    def themes(self, guild_id: int) -> list[str]:
        uploaded = {row[0] for row in self.db.execute(
            "SELECT theme FROM server_icon_assets WHERE guild_id = ?", (guild_id,))}
        return sorted(uploaded | self.file_assets().keys())

    def asset(self, guild_id: int, theme: str):
        # Repository files take precedence so redeploying a file replaces old uploads.
        path = self.file_assets().get(theme)
        if path is not None:
            stat = path.stat()
            if stat.st_size > MAX_UPLOAD:
                raise ValueError(f"The {theme} file must be smaller than 8 MiB.")
            signature = (str(path), stat.st_mtime_ns, stat.st_size)
            cached = self.file_cache.get(theme)
            if cached is None or cached[0] != signature:
                cached = (signature, normalize_icon(path.read_bytes()))
                self.file_cache[theme] = cached
            return cached[1]
        self.file_cache.pop(theme, None)
        row = self.db.execute("SELECT image FROM server_icon_assets WHERE guild_id = ? AND theme = ?", (guild_id, theme)).fetchone()
        return row[0] if row else None


class ServerIcons(commands.Cog):
    servericon = app_commands.Group(
        name="servericon", description="Seasonal server icons and manual overrides",
        guild_only=True,
    )

    def __init__(self, bot: commands.Bot, db_path: str | None = None):
        self.bot = bot
        self.store = IconStore(db_path or os.getenv("HUNTERS_LEDGER_DB", "hunters_ledger.db"))
        self.locks: dict[int, asyncio.Lock] = {}

    async def cog_load(self):
        self.check_icons.start()

    def cog_unload(self):
        self.check_icons.cancel()
        self.store.db.close()

    def lock(self, guild_id: int) -> asyncio.Lock:
        return self.locks.setdefault(guild_id, asyncio.Lock())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not (
                interaction.user.id == TIDE44_ID or interaction.permissions.administrator):
            raise app_commands.MissingPermissions(["administrator"])
        return True

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        original = getattr(error, "original", error)
        if isinstance(original, app_commands.MissingPermissions):
            message = "Only Tide44 or server administrators can use these commands."
        elif isinstance(original, discord.Forbidden):
            message = "Discord denied the change. Give the bot Manage Server permission, then try again."
        elif isinstance(original, discord.HTTPException):
            message = "Discord could not complete the change. Try again shortly."
        elif isinstance(original, ValueError):
            message = str(original)
        else:
            log.error("Server icon command failed", exc_info=error)
            message = "The icon command failed. Check the bot logs for details."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    async def apply_icon(self, guild: discord.Guild, mode: str | None = None) -> str:
        """Caller holds the guild lock. Save an override only after success."""
        settings = self.store.ensure(guild.id)
        selected_mode = mode or settings["mode"]
        if selected_mode == "paused":
            return "Paused; upload your icons and use /servericon set theme:auto to start."
        if self.store.asset(guild.id, "default") is None:
            raise ValueError("First add resources/server_icons/default.png or upload theme:default with /servericon upload.")
        target = scheduled_theme(self.store.windows(guild.id), datetime.now(UK_TIME).date()) if selected_mode == "auto" else selected_mode
        image = self.store.asset(guild.id, target)
        warning = None
        if image is None:
            if selected_mode != "auto":
                raise ValueError(f"Add a {target} icon file in resources/server_icons or use /servericon upload first.")
            warning = f"Missing {target} icon; using default. Add its icon file or use /servericon upload."
            target, image = "default", self.store.asset(guild.id, "default")
        digest = hashlib.sha256(image).hexdigest()
        icon_key = guild.icon.key if guild.icon else None
        if digest != settings["applied_digest"] or icon_key != settings["discord_icon_key"]:
            updated = await guild.edit(icon=image, reason=f"Hunter's Ledger server icon: {selected_mode} / {target}")
            icon_key = updated.icon.key if updated.icon else None
        with self.store.db:
            self.store.db.execute("""UPDATE server_icon_settings
                SET mode = ?, applied_digest = ?, discord_icon_key = ?, last_error = ? WHERE guild_id = ?""",
                (selected_mode, digest, icon_key, warning, guild.id))
        return f"Mode: {selected_mode}. Icon: {target}." + (f" {warning}" if warning else "")

    @tasks.loop(minutes=1)
    async def check_icons(self):
        rows = self.store.db.execute("SELECT guild_id FROM server_icon_settings WHERE mode != 'paused'").fetchall()
        for row in rows:
            guild = self.bot.get_guild(row["guild_id"])
            if guild is None or guild.unavailable:
                continue
            async with self.lock(guild.id):
                try:
                    await self.apply_icon(guild)
                except Exception as error:
                    # One guild's failure must not stop checks for other guilds.
                    log.exception("Could not update server icon for guild %s", guild.id)
                    with self.store.db:
                        self.store.db.execute("UPDATE server_icon_settings SET last_error = ? WHERE guild_id = ?", (str(error)[:500], guild.id))

    @check_icons.before_loop
    async def before_check_icons(self):
        await self.bot.wait_until_ready()

    @servericon.command(name="set", description="Choose auto, default, or a holiday; overrides last until changed")
    @app_commands.describe(theme="auto resumes dates; default pins your normal icon; a holiday pins that icon")
    async def set_icon(self, interaction: discord.Interaction, theme: str):
        theme = theme_name(theme)
        if theme == "paused":
            raise ValueError("Choose auto, default or an uploaded holiday name.")
        await interaction.response.defer(ephemeral=True)
        async with self.lock(interaction.guild_id):
            result = await self.apply_icon(interaction.guild, theme)
        await interaction.followup.send(result, ephemeral=True)

    @set_icon.autocomplete("theme")
    async def theme_choices(self, interaction: discord.Interaction, current: str):
        names = dict.fromkeys(["auto", "default"] + self.store.themes(interaction.guild_id))
        return [app_commands.Choice(name=name, value=name) for name in names if current.lower() in name][:25]

    @servericon.command(name="upload", description="Save or replace an icon for default or any named holiday")
    @app_commands.describe(theme="For example: default, halloween, bonfire, christmas, easter, wedding", image="A single static PNG, JPEG or WebP icon image, up to 8 MiB")
    async def upload_icon(self, interaction: discord.Interaction, theme: str, image: discord.Attachment):
        theme = theme_name(theme)
        if theme in {"auto", "paused"}:
            raise ValueError("auto and paused are reserved names.")
        if image.size > MAX_UPLOAD:
            raise ValueError("Upload an image smaller than 8 MiB.")
        await interaction.response.defer(ephemeral=True)
        data = await asyncio.to_thread(normalize_icon, await image.read())
        async with self.lock(interaction.guild_id):
            self.store.ensure(interaction.guild_id)
            with self.store.db:
                self.store.db.execute("INSERT OR REPLACE INTO server_icon_assets VALUES (?, ?, ?)", (interaction.guild_id, theme, data))
            result = await self.apply_icon(interaction.guild)
        source_note = " Repository file takes precedence over this upload." if theme in self.store.file_assets() else ""
        await interaction.followup.send(f"Saved {theme}.{source_note} {result}", ephemeral=True)

    @servericon.command(name="schedule", description="Add or replace a holiday window; end is the first day back")
    @app_commands.describe(theme="Holiday name matching an uploaded icon", start="MM-DD annually, or YYYY-MM-DD for a one-off", end="Exclusive end date, in the same format as start", priority="Higher wins overlaps; one-off windows beat annual ones")
    async def schedule_icon(self, interaction: discord.Interaction, theme: str, start: str, end: str, priority: app_commands.Range[int, 0, 100] = 0):
        theme = theme_name(theme)
        if theme in {"auto", "default", "paused"}:
            raise ValueError("Choose a holiday name; default applies outside holiday windows.")
        validate_window(start, end)
        await interaction.response.defer(ephemeral=True)
        async with self.lock(interaction.guild_id):
            self.store.ensure(interaction.guild_id)
            with self.store.db:
                self.store.db.execute("INSERT OR REPLACE INTO server_icon_windows VALUES (?, ?, ?, ?, ?)", (interaction.guild_id, theme, start, end, priority))
            result = await self.apply_icon(interaction.guild)
        await interaction.followup.send(f"Scheduled {theme}: {start} to {end} (end excluded). {result}", ephemeral=True)

    @servericon.command(name="unschedule", description="Remove a holiday window, keeping its uploaded icon")
    async def unschedule_icon(self, interaction: discord.Interaction, theme: str):
        theme = theme_name(theme)
        await interaction.response.defer(ephemeral=True)
        async with self.lock(interaction.guild_id):
            self.store.ensure(interaction.guild_id)
            with self.store.db:
                removed = self.store.db.execute("DELETE FROM server_icon_windows WHERE guild_id = ? AND theme = ?", (interaction.guild_id, theme)).rowcount
            result = await self.apply_icon(interaction.guild)
        await interaction.followup.send((f"Removed {theme}. " if removed else f"No window found for {theme}. ") + result, ephemeral=True)

    @servericon.command(name="status", description="View icon mode, holiday dates, missing images and recent errors")
    async def icon_status(self, interaction: discord.Interaction):
        settings = self.store.ensure(interaction.guild_id)
        today = datetime.now(UK_TIME).date()
        windows = self.store.windows(interaction.guild_id)
        assets = set(self.store.themes(interaction.guild_id))
        files = self.store.file_assets()
        lines = [f"Mode: **{settings['mode']}**", f"Today: {today} (Europe/London)", f"Scheduled today: **{scheduled_theme(windows, today)}**", "Overrides remain until `/servericon set theme:auto`."]
        lines.append("\nAvailable icons: " + (", ".join(f"{name} (file)" if name in files else f"{name} (upload)" for name in sorted(assets)) or "none"))
        lines.append("\nHoliday windows (end excluded):")
        lines.extend(f"- {row['theme']}: {row['start']} to {row['end']} (priority {row['priority']})" + (" [image missing]" if row['theme'] not in assets else "") for row in windows)
        if "default" not in assets:
            lines.append("\nAdd resources/server_icons/default.png or upload your default icon before enabling changes.")
        if settings["last_error"]:
            lines.append(f"\nLast issue: {settings['last_error']}")
        # Split even long asset lists so calendars stay within Discord limits.
        content = "\n".join(lines)
        pages = [content[index:index + 1900] for index in range(0, len(content), 1900)]
        await interaction.response.send_message(pages[0], ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
        for page in pages[1:]:
            await interaction.followup.send(page, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerIcons(bot))
