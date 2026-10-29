"""Per-server icons changed manually through /servericon commands."""
from __future__ import annotations

import asyncio
import hashlib
from io import BytesIO
import logging
import os
from pathlib import Path
import re
import sqlite3

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageOps, UnidentifiedImageError

log = logging.getLogger(__name__)
MAX_UPLOAD = 8 * 1024 * 1024
ICON_DIRECTORY = Path(__file__).resolve().parent / "resources" / "server_icons"
ICON_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
TIDE44_ID = 420996360699904000


def theme_name(value: str) -> str:
    value = value.strip().lower().replace(" ", "_")
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", value):
        raise ValueError("Use 1-40 letters, numbers, underscores or hyphens, starting with a letter.")
    return value


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
        """)
        # Automatic scheduling was removed. Preserve Discord's current icon and
        # require a deliberate manual selection before making another change.
        with self.db:
            self.db.execute(
                "UPDATE server_icon_settings SET mode = 'paused', last_error = NULL WHERE mode = 'auto'"
            )

    def ensure(self, guild_id: int):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO server_icon_settings (guild_id) VALUES (?)", (guild_id,))
        return self.db.execute("SELECT * FROM server_icon_settings WHERE guild_id = ?", (guild_id,)).fetchone()

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
        name="servericon", description="Manually manage the server icon",
        guild_only=True,
    )

    def __init__(self, bot: commands.Bot, db_path: str | None = None):
        self.bot = bot
        self.store = IconStore(db_path or os.getenv("HUNTERS_LEDGER_DB", "hunters_ledger.db"))
        self.locks: dict[int, asyncio.Lock] = {}

    def cog_unload(self):
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

    async def apply_icon(self, guild: discord.Guild, theme: str | None = None) -> str:
        """Apply one manually selected icon. The caller holds the guild lock."""
        settings = self.store.ensure(guild.id)
        target = theme or settings["mode"]
        if target == "paused":
            return "No icon is selected yet. Use /servericon set to choose one manually."
        image = self.store.asset(guild.id, target)
        if image is None:
            raise ValueError(f"Add a {target} icon file in resources/server_icons or use /servericon upload first.")
        digest = hashlib.sha256(image).hexdigest()
        icon_key = guild.icon.key if guild.icon else None
        if digest != settings["applied_digest"] or icon_key != settings["discord_icon_key"]:
            updated = await guild.edit(icon=image, reason=f"Hunter's Ledger manual server icon: {target}")
            icon_key = updated.icon.key if updated.icon else None
        with self.store.db:
            self.store.db.execute("""UPDATE server_icon_settings
                SET mode = ?, applied_digest = ?, discord_icon_key = ?, last_error = ? WHERE guild_id = ?""",
                (target, digest, icon_key, None, guild.id))
        return f"Server icon changed to {target}."

    @servericon.command(name="set", description="Manually change the server icon")
    @app_commands.describe(theme="Choose default or any available named icon")
    async def set_icon(self, interaction: discord.Interaction, theme: str):
        theme = theme_name(theme)
        if theme in {"auto", "paused"}:
            raise ValueError("Choose default or an available named icon.")
        await interaction.response.defer(ephemeral=True)
        async with self.lock(interaction.guild_id):
            result = await self.apply_icon(interaction.guild, theme)
        await interaction.followup.send(result, ephemeral=True)

    @set_icon.autocomplete("theme")
    async def theme_choices(self, interaction: discord.Interaction, current: str):
        names = dict.fromkeys(["default"] + self.store.themes(interaction.guild_id))
        return [app_commands.Choice(name=name, value=name) for name in names if current.lower() in name][:25]

    @servericon.command(name="upload", description="Save or replace a named server icon")
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

    @servericon.command(name="status", description="View the selected icon and available manual choices")
    async def icon_status(self, interaction: discord.Interaction):
        settings = self.store.ensure(interaction.guild_id)
        assets = set(self.store.themes(interaction.guild_id))
        files = self.store.file_assets()
        selected = settings["mode"]
        lines = [
            f"Selected icon: **{selected if selected != 'paused' else 'none'}**",
            "Icons change only when `/servericon set` is used.",
        ]
        lines.append("\nAvailable icons: " + (", ".join(f"{name} (file)" if name in files else f"{name} (upload)" for name in sorted(assets)) or "none"))
        if "default" not in assets:
            lines.append("\nAdd resources/server_icons/default.png or upload a default icon if you want a normal icon choice.")
        content = "\n".join(lines)
        pages = [content[index:index + 1900] for index in range(0, len(content), 1900)]
        await interaction.response.send_message(pages[0], ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
        for page in pages[1:]:
            await interaction.followup.send(page, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerIcons(bot))
