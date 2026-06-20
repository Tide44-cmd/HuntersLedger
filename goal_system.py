"""Goal tracking commands for A Hunter's Ledger.

Goals sit above the solo backlog: goal items are matched live against
``solo_backlogs`` and official templates can be copied and synchronised.
"""

from __future__ import annotations

import os
import re
import sqlite3
import unicodedata
from collections import defaultdict
from typing import Iterable

import discord
from discord import app_commands
from discord.ext import commands


DB_PATH = os.getenv("HUNTERS_LEDGER_DB", "hunters_ledger.db")
GOAL_TYPES = ("series", "az", "genre")
DEFAULT_MOD_ROLES = ("admin", "administrator", "moderator", "leader", "event staff")


def normalize_game_name(value: str) -> str:
    """Return a conservative comparison key without losing platform labels."""
    value = unicodedata.normalize("NFKC", value or "").casefold().strip()
    value = value.replace("’", "'").replace("–", "-").replace("—", "-")
    value = re.sub(r"[^\w\s()]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def make_progress_bar(completed: int, total: int, length: int = 18) -> str:
    percentage = round((completed / total) * 100) if total else 0
    filled = round((completed / total) * length) if total else 0
    return f"{'█' * filled}{'░' * (length - filled)} {percentage}%"


def parse_goal_items(raw: str, goal_type: str) -> tuple[list[tuple[str | None, str]], list[str]]:
    """Parse modal lines into (slot, game) pairs and report skipped duplicates."""
    parsed: list[tuple[str | None, str]] = []
    skipped: list[str] = []
    seen_names: set[str] = set()
    used_slots: set[str] = set()

    for raw_line in (raw or "").splitlines():
        line = raw_line.strip().lstrip("•*- ").strip()
        if not line:
            continue
        slot = None
        game = line
        if goal_type == "az":
            match = re.match(r"^([A-Za-z])\s*[-:.)]\s*(.+)$", line)
            if match:
                slot, game = match.group(1).upper(), match.group(2).strip()
            else:
                first = game[0].upper() if game else ""
                if first in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" and first not in used_slots:
                    slot = first
                else:
                    slot = next((letter for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if letter not in used_slots), None)
            if slot:
                used_slots.add(slot)

        normalized = normalize_game_name(game)
        if not normalized or normalized in seen_names:
            skipped.append(game)
            continue
        seen_names.add(normalized)
        parsed.append((slot, game[:250]))
    return parsed, skipped


def chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def chunk_lines(values: list[str], max_chars: int = 1000) -> list[list[str]]:
    """Split lines without exceeding Discord's 1,024-character field limit."""
    pages: list[list[str]] = []
    current: list[str] = []
    current_length = 0
    for value in values:
        value = value[:max_chars]
        added_length = len(value) + (1 if current else 0)
        if current and current_length + added_length > max_chars:
            pages.append(current)
            current = []
            current_length = 0
        current.append(value)
        current_length += len(value) + (1 if current_length else 0)
    if current:
        pages.append(current)
    return pages


def summarize_names(names: list[str], max_chars: int = 1200) -> str:
    summary = ""
    for index, name in enumerate(names):
        candidate = (", " if summary else "") + name
        if len(summary) + len(candidate) > max_chars:
            return summary + f" … and {len(names) - index} more"
        summary += candidate
    return summary


class GoalItemsModal(discord.ui.Modal):
    games = discord.ui.TextInput(
        label="Games (one per line)",
        style=discord.TextStyle.paragraph,
        placeholder="Resident Evil 4\nResident Evil Village",
        max_length=4000,
    )

    def __init__(self, cog: "GoalSystem", goal_type: str, title: str, template: bool = False):
        super().__init__(title=("Create official goal" if template else "Create personal goal"))
        self.cog = cog
        self.goal_type = goal_type
        self.goal_title = title
        self.template = template
        if goal_type == "az":
            self.games.placeholder = "A - Alan Wake\nB - BioShock\nC - Control"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.template:
            await self.cog.create_template(interaction, self.goal_type, self.goal_title, str(self.games))
        else:
            await self.cog.create_user_goal(interaction, self.goal_type, self.goal_title, str(self.games))


class AddGoalItemsModal(discord.ui.Modal, title="Add games to goal"):
    games = discord.ui.TextInput(
        label="Games (one per line)",
        style=discord.TextStyle.paragraph,
        max_length=4000,
    )

    def __init__(self, cog: "GoalSystem", record_id: int, goal_type: str, template: bool = False):
        super().__init__()
        self.cog = cog
        self.record_id = record_id
        self.goal_type = goal_type
        self.template = template

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.template:
            await self.cog.add_template_items(interaction, self.record_id, self.goal_type, str(self.games))
        else:
            await self.cog.add_user_items(interaction, self.record_id, self.goal_type, str(self.games))


class AddMissingHuntsView(discord.ui.View):
    def __init__(self, cog: "GoalSystem", user_goal_id: int, owner_id: str):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_goal_id = user_goal_id
        self.owner_id = owner_id

    @discord.ui.button(label="Add Missing Hunts", style=discord.ButtonStyle.success)
    async def add_missing(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if str(interaction.user.id) != self.owner_id:
            await interaction.response.send_message("This button belongs to another hunter.", ephemeral=True)
            return
        count, names = self.cog.add_missing_to_backlog(self.user_goal_id, interaction.user)
        button.disabled = True
        await interaction.response.edit_message(view=self)
        summary = summarize_names(names)
        await interaction.followup.send(
            f"Added {count} missing hunt{'s' if count != 1 else ''} as **Not Started**."
            + (f"\n{summary}" if summary else ""),
            ephemeral=True,
        )

    @discord.ui.button(label="No Thanks", style=discord.ButtonStyle.secondary)
    async def dismiss(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if str(interaction.user.id) != self.owner_id:
            await interaction.response.send_message("This button belongs to another hunter.", ephemeral=True)
            return
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)


class ConfirmDeleteGoalView(discord.ui.View):
    def __init__(self, cog: "GoalSystem", goal_id: int, owner_id: str, title: str):
        super().__init__(timeout=60)
        self.cog = cog
        self.goal_id = goal_id
        self.owner_id = owner_id
        self.goal_title = title

    @discord.ui.button(label="Delete Goal", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if str(interaction.user.id) != self.owner_id:
            await interaction.response.send_message("This confirmation belongs to another hunter.", ephemeral=True)
            return
        self.cog.db.execute("DELETE FROM user_goals WHERE id = ? AND user_id = ?", (self.goal_id, self.owner_id))
        self.cog.db.commit()
        await interaction.response.edit_message(content=f"Deleted **{self.goal_title}**.", embed=None, view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if str(interaction.user.id) != self.owner_id:
            await interaction.response.send_message("This confirmation belongs to another hunter.", ephemeral=True)
            return
        await interaction.response.edit_message(content="Goal deletion cancelled.", embed=None, view=None)


class GoalSystem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = sqlite3.connect(DB_PATH)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def cog_unload(self) -> None:
        self.db.close()

    def _create_schema(self) -> None:
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS goal_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_type TEXT NOT NULL CHECK(goal_type IN ('series', 'az', 'genre')),
                title TEXT NOT NULL COLLATE NOCASE,
                description TEXT,
                created_by_user_id TEXT NOT NULL,
                created_by_user_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER NOT NULL DEFAULT 1,
                sync_enabled_by_default INTEGER NOT NULL DEFAULT 1,
                allow_personal_additions INTEGER NOT NULL DEFAULT 1,
                UNIQUE(goal_type, title)
            );

            CREATE TABLE IF NOT EXISTS goal_template_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id INTEGER NOT NULL REFERENCES goal_templates(id) ON DELETE CASCADE,
                game_name TEXT NOT NULL,
                normalized_game_name TEXT NOT NULL,
                slot_label TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                platform TEXT,
                notes TEXT,
                is_optional INTEGER NOT NULL DEFAULT 0,
                is_unobtainable INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(template_id, normalized_game_name)
            );

            CREATE TABLE IF NOT EXISTS user_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                user_name TEXT NOT NULL,
                goal_type TEXT NOT NULL CHECK(goal_type IN ('series', 'az', 'genre')),
                title TEXT NOT NULL COLLATE NOCASE,
                description TEXT,
                source_template_id INTEGER REFERENCES goal_templates(id) ON DELETE SET NULL,
                is_template_copy INTEGER NOT NULL DEFAULT 0,
                sync_enabled INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_synced_at TIMESTAMP,
                is_active INTEGER NOT NULL DEFAULT 1,
                UNIQUE(user_id, title)
            );

            CREATE TABLE IF NOT EXISTS user_goal_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_goal_id INTEGER NOT NULL REFERENCES user_goals(id) ON DELETE CASCADE,
                source_template_item_id INTEGER REFERENCES goal_template_items(id) ON DELETE SET NULL,
                game_name TEXT NOT NULL,
                normalized_game_name TEXT NOT NULL,
                slot_label TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                platform TEXT,
                notes TEXT,
                is_personal_addition INTEGER NOT NULL DEFAULT 0,
                is_hidden INTEGER NOT NULL DEFAULT 0,
                manual_status TEXT,
                linked_solo_backlog_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_goal_id, normalized_game_name)
            );

            CREATE INDEX IF NOT EXISTS idx_user_goals_owner ON user_goals(user_id, is_active);
            CREATE INDEX IF NOT EXISTS idx_user_goals_template ON user_goals(source_template_id, sync_enabled);
            CREATE INDEX IF NOT EXISTS idx_user_goal_items_goal ON user_goal_items(user_goal_id, is_hidden);
            """
        )
        self.db.commit()

    @staticmethod
    def _goal_type_value(value: object) -> str:
        return str(getattr(value, "value", value) or "").lower()

    @staticmethod
    def _clean_title(value: str) -> str:
        return re.sub(r"\s+", " ", (value or "").strip())[:100]

    def _is_mod(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return False
        if interaction.user.guild_permissions.administrator:
            return True
        configured = os.getenv("GOAL_MOD_ROLES", "")
        allowed = {name.strip().casefold() for name in configured.split(",") if name.strip()}
        if not allowed:
            allowed = set(DEFAULT_MOD_ROLES)
        return any(role.name.casefold() in allowed for role in interaction.user.roles)

    async def _require_mod(self, interaction: discord.Interaction) -> bool:
        if self._is_mod(interaction):
            return True
        await interaction.response.send_message(
            "You need an approved goal moderator role to change official templates.", ephemeral=True
        )
        return False

    def _find_user_goal(self, user_id: str, title: str) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM user_goals WHERE user_id = ? AND title = ? COLLATE NOCASE AND is_active = 1",
            (user_id, title.strip()),
        ).fetchone()

    def _find_template(self, goal_type: str, title: str, active_only: bool = True) -> sqlite3.Row | None:
        suffix = " AND is_active = 1" if active_only else ""
        return self.db.execute(
            f"SELECT * FROM goal_templates WHERE goal_type = ? AND title = ? COLLATE NOCASE{suffix}",
            (goal_type, title.strip()),
        ).fetchone()

    def _insert_user_items(
        self, goal_id: int, items: list[tuple[str | None, str]], personal: bool,
    ) -> tuple[int, list[str]]:
        existing = {
            row[0] for row in self.db.execute(
                "SELECT normalized_game_name FROM user_goal_items WHERE user_goal_id = ?", (goal_id,)
            )
        }
        added = 0
        skipped: list[str] = []
        next_order = self.db.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM user_goal_items WHERE user_goal_id = ?", (goal_id,)
        ).fetchone()[0]
        for offset, (slot, game) in enumerate(items):
            normalized = normalize_game_name(game)
            if normalized in existing:
                skipped.append(game)
                continue
            self.db.execute(
                """INSERT INTO user_goal_items
                   (user_goal_id, game_name, normalized_game_name, slot_label, sort_order, is_personal_addition)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (goal_id, game, normalized, slot, next_order + offset, int(personal)),
            )
            existing.add(normalized)
            added += 1
        return added, skipped

    def _goal_items_with_status(self, goal_id: int, user_id: str) -> list[dict]:
        backlog_rows = self.db.execute(
            "SELECT id, game_name, status FROM solo_backlogs WHERE user_id = ?", (user_id,)
        ).fetchall()
        by_id = {row["id"]: row for row in backlog_rows}
        by_name = {normalize_game_name(row["game_name"]): row for row in backlog_rows}
        results: list[dict] = []
        rows = self.db.execute(
            """SELECT * FROM user_goal_items
               WHERE user_goal_id = ? AND is_hidden = 0
               ORDER BY CASE WHEN slot_label IS NULL THEN 1 ELSE 0 END, slot_label, sort_order, id""",
            (goal_id,),
        ).fetchall()
        for row in rows:
            backlog = by_id.get(row["linked_solo_backlog_id"])
            if backlog is None:
                backlog = by_name.get(row["normalized_game_name"])
            results.append({
                **dict(row),
                "status": row["manual_status"] or (backlog["status"] if backlog else "missing"),
                "backlog_id": backlog["id"] if backlog else None,
            })
        return results

    def _progress(self, goal: sqlite3.Row) -> tuple[int, int, list[dict]]:
        items = self._goal_items_with_status(goal["id"], goal["user_id"])
        completed = sum(item["status"] == "completed" for item in items)
        total = max(26, len(items)) if goal["goal_type"] == "az" else len(items)
        return completed, total, items

    def _missing_items(self, goal_id: int, user_id: str) -> list[dict]:
        return [item for item in self._goal_items_with_status(goal_id, user_id) if item["status"] == "missing"]

    def add_missing_to_backlog(self, goal_id: int, user: discord.abc.User) -> tuple[int, list[str]]:
        user_id = str(user.id)
        goal = self.db.execute("SELECT * FROM user_goals WHERE id = ? AND user_id = ?", (goal_id, user_id)).fetchone()
        if not goal:
            return 0, []
        names: list[str] = []
        for item in self._missing_items(goal_id, user_id):
            exists = self.db.execute(
                "SELECT 1 FROM solo_backlogs WHERE user_id = ? AND LOWER(game_name) = LOWER(?)",
                (user_id, item["game_name"]),
            ).fetchone()
            if exists:
                continue
            self.db.execute(
                "INSERT INTO solo_backlogs (user_id, user_name, game_name, status) VALUES (?, ?, ?, 'not started')",
                (user_id, str(user), item["game_name"]),
            )
            names.append(item["game_name"])
        self.db.commit()
        return len(names), names

    def _sync_goal(self, goal: sqlite3.Row) -> tuple[list[str], list[str]]:
        added: list[str] = []
        newly_completed: list[str] = []
        before = {item["normalized_game_name"]: item["status"] for item in self._goal_items_with_status(goal["id"], goal["user_id"])}
        template_id = goal["source_template_id"]
        if template_id and goal["sync_enabled"]:
            template_items = self.db.execute(
                "SELECT * FROM goal_template_items WHERE template_id = ? AND is_active = 1 ORDER BY sort_order, id",
                (template_id,),
            ).fetchall()
            existing = {
                row[0] for row in self.db.execute(
                    "SELECT normalized_game_name FROM user_goal_items WHERE user_goal_id = ?", (goal["id"],)
                )
            }
            for item in template_items:
                if item["normalized_game_name"] in existing:
                    continue
                self.db.execute(
                    """INSERT INTO user_goal_items
                       (user_goal_id, source_template_item_id, game_name, normalized_game_name, slot_label, sort_order)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (goal["id"], item["id"], item["game_name"], item["normalized_game_name"], item["slot_label"], item["sort_order"]),
                )
                existing.add(item["normalized_game_name"])
                added.append(item["game_name"])
        self.db.execute(
            "UPDATE user_goals SET user_name = ?, updated_at = CURRENT_TIMESTAMP, last_synced_at = CURRENT_TIMESTAMP WHERE id = ?",
            (goal["user_name"], goal["id"]),
        )
        self.db.commit()
        after = self._goal_items_with_status(goal["id"], goal["user_id"])
        newly_completed = [
            item["game_name"] for item in after
            if item["status"] == "completed" and before.get(item["normalized_game_name"]) != "completed"
        ]
        return added, newly_completed

    def _goal_embeds(self, goal: sqlite3.Row, user: discord.abc.User) -> tuple[list[discord.Embed], int]:
        completed, total, items = self._progress(goal)
        template = None
        if goal["source_template_id"]:
            template = self.db.execute("SELECT title FROM goal_templates WHERE id = ?", (goal["source_template_id"],)).fetchone()
        source = f"Official template: {template['title']}" if template else "Custom goal"
        lines: list[str] = []
        slot_groups: dict[str, list[dict]] = defaultdict(list)
        if goal["goal_type"] == "az":
            for item in items:
                slot_groups[item["slot_label"] or "?"].append(item)
            for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                letter_items = slot_groups.get(letter, [])
                if not letter_items:
                    lines.append(f"**{letter}:** ⬜ Empty")
                    continue
                for item in letter_items:
                    lines.append(f"**{letter}:** {self._format_item(item)}")
            for item in slot_groups.get("?", []):
                lines.append(f"**?:** {self._format_item(item)}")
        else:
            lines = [self._format_item(item) for item in items]
        if not lines:
            lines = ["No games have been added yet."]

        header = (
            f"**Owned by:** {discord.utils.escape_markdown(getattr(user, 'display_name', str(user)))}\n"
            f"**Goal type:** {goal['goal_type'].upper() if goal['goal_type'] == 'az' else goal['goal_type'].title()}\n"
            f"**Source:** {discord.utils.escape_markdown(source)}\n"
            f"**Progress:** {completed}/{total} completed\n`{make_progress_bar(completed, total)}`"
        )
        all_pages = chunk_lines(lines)
        pages = all_pages[:10]
        embeds: list[discord.Embed] = []
        for index, page in enumerate(pages):
            embed = discord.Embed(
                title=goal["title"] if index == 0 else f"{goal['title']} — {index + 1}",
                description=header if index == 0 else None,
                color=0x4F8CFF if completed < total else 0x57F287,
            )
            embed.add_field(name="Games", value="\n".join(page), inline=False)
            if index == 0:
                embed.set_thumbnail(url=user.display_avatar.url)
            synced = goal["last_synced_at"] or "Live from solo backlog"
            embed.set_footer(text=f"Last sync: {synced}")
            embeds.append(embed)
        shown_lines = sum(len(page) for page in pages)
        if len(lines) > shown_lines:
            embeds[-1].add_field(name="Display limit", value=f"{len(lines) - shown_lines} more items are not shown.", inline=False)
        missing = sum(item["status"] == "missing" for item in items)
        return embeds, missing

    @staticmethod
    def _format_item(item: dict) -> str:
        name = discord.utils.escape_markdown(item["game_name"])
        personal = " ➕" if item["is_personal_addition"] else ""
        if item["status"] == "completed":
            return f"✅ ~~{name}~~{personal}"
        if item["status"] == "in progress":
            return f"🟡 {name}{personal}"
        if item["status"] == "not started":
            return f"⬜ {name}{personal}"
        return f"❔ {name}{personal}"

    async def _send_goal(self, interaction: discord.Interaction, goal: sqlite3.Row) -> None:
        embeds, missing = self._goal_embeds(goal, interaction.user)
        view = AddMissingHuntsView(self, goal["id"], str(interaction.user.id)) if missing else None
        await interaction.response.send_message(embeds=embeds, view=view, ephemeral=True)

    async def create_user_goal(self, interaction: discord.Interaction, goal_type: str, title: str, raw: str) -> None:
        items, skipped = parse_goal_items(raw, goal_type)
        if not items:
            await interaction.response.send_message("Add at least one valid game to create the goal.", ephemeral=True)
            return
        try:
            cursor = self.db.execute(
                """INSERT INTO user_goals (user_id, user_name, goal_type, title, sync_enabled)
                   VALUES (?, ?, ?, ?, 0)""",
                (str(interaction.user.id), str(interaction.user), goal_type, title),
            )
            self._insert_user_items(cursor.lastrowid, items, personal=False)
            self.db.commit()
        except sqlite3.IntegrityError:
            self.db.rollback()
            await interaction.response.send_message("You already have a goal with that title.", ephemeral=True)
            return
        goal = self.db.execute("SELECT * FROM user_goals WHERE id = ?", (cursor.lastrowid,)).fetchone()
        await self._send_goal(interaction, goal)

    async def create_template(self, interaction: discord.Interaction, goal_type: str, title: str, raw: str) -> None:
        if not self._is_mod(interaction):
            await interaction.response.send_message("You no longer have permission to create official goals.", ephemeral=True)
            return
        items, skipped = parse_goal_items(raw, goal_type)
        if not items:
            await interaction.response.send_message("Add at least one valid game to create the template.", ephemeral=True)
            return
        try:
            cursor = self.db.execute(
                """INSERT INTO goal_templates
                   (goal_type, title, created_by_user_id, created_by_user_name)
                   VALUES (?, ?, ?, ?)""",
                (goal_type, title, str(interaction.user.id), str(interaction.user)),
            )
            for order, (slot, game) in enumerate(items):
                self.db.execute(
                    """INSERT INTO goal_template_items
                       (template_id, game_name, normalized_game_name, slot_label, sort_order)
                       VALUES (?, ?, ?, ?, ?)""",
                    (cursor.lastrowid, game, normalize_game_name(game), slot, order),
                )
            self.db.commit()
        except sqlite3.IntegrityError:
            self.db.rollback()
            await interaction.response.send_message("An official goal with that type and title already exists.", ephemeral=True)
            return
        note = f" Skipped {len(skipped)} duplicate line(s)." if skipped else ""
        await interaction.response.send_message(
            f"Created official **{title}** with {len(items)} game{'s' if len(items) != 1 else ''}.{note}", ephemeral=True
        )

    async def add_user_items(self, interaction: discord.Interaction, goal_id: int, goal_type: str, raw: str) -> None:
        goal = self.db.execute(
            "SELECT * FROM user_goals WHERE id = ? AND user_id = ? AND is_active = 1",
            (goal_id, str(interaction.user.id)),
        ).fetchone()
        if not goal:
            await interaction.response.send_message("That goal is no longer available.", ephemeral=True)
            return
        if goal["is_template_copy"]:
            template = self.db.execute("SELECT allow_personal_additions FROM goal_templates WHERE id = ?", (goal["source_template_id"],)).fetchone()
            if template and not template[0]:
                await interaction.response.send_message("That official template does not allow personal additions.", ephemeral=True)
                return
        items, parse_skipped = parse_goal_items(raw, goal_type)
        added, duplicate_skipped = self._insert_user_items(goal_id, items, personal=bool(goal["is_template_copy"]))
        self.db.execute("UPDATE user_goals SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (goal_id,))
        self.db.commit()
        await interaction.response.send_message(
            f"Added {added} game{'s' if added != 1 else ''} to **{goal['title']}**."
            + (f" Skipped {len(parse_skipped) + len(duplicate_skipped)} duplicate/invalid line(s)." if parse_skipped or duplicate_skipped else ""),
            ephemeral=True,
        )

    async def add_template_items(self, interaction: discord.Interaction, template_id: int, goal_type: str, raw: str) -> None:
        if not self._is_mod(interaction):
            await interaction.response.send_message("You no longer have permission to edit official goals.", ephemeral=True)
            return
        template = self.db.execute("SELECT * FROM goal_templates WHERE id = ? AND is_active = 1", (template_id,)).fetchone()
        if not template:
            await interaction.response.send_message("That official goal is no longer available.", ephemeral=True)
            return
        items, parse_skipped = parse_goal_items(raw, goal_type)
        existing = {
            row[0] for row in self.db.execute(
                "SELECT normalized_game_name FROM goal_template_items WHERE template_id = ?", (template_id,)
            )
        }
        next_order = self.db.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM goal_template_items WHERE template_id = ?", (template_id,)
        ).fetchone()[0]
        new_template_items: list[sqlite3.Row] = []
        duplicate_count = len(parse_skipped)
        for offset, (slot, game) in enumerate(items):
            normalized = normalize_game_name(game)
            if normalized in existing:
                duplicate_count += 1
                continue
            cursor = self.db.execute(
                """INSERT INTO goal_template_items
                   (template_id, game_name, normalized_game_name, slot_label, sort_order)
                   VALUES (?, ?, ?, ?, ?)""",
                (template_id, game, normalized, slot, next_order + offset),
            )
            new_template_items.append(self.db.execute("SELECT * FROM goal_template_items WHERE id = ?", (cursor.lastrowid,)).fetchone())
            existing.add(normalized)

        synced_goals: set[int] = set()
        user_duplicate_count = 0
        subscribed = self.db.execute(
            "SELECT id FROM user_goals WHERE source_template_id = ? AND sync_enabled = 1 AND is_active = 1",
            (template_id,),
        ).fetchall()
        for user_goal in subscribed:
            user_existing = {
                row[0] for row in self.db.execute(
                    "SELECT normalized_game_name FROM user_goal_items WHERE user_goal_id = ?", (user_goal["id"],)
                )
            }
            for item in new_template_items:
                if item["normalized_game_name"] in user_existing:
                    user_duplicate_count += 1
                    continue
                self.db.execute(
                    """INSERT INTO user_goal_items
                       (user_goal_id, source_template_item_id, game_name, normalized_game_name, slot_label, sort_order)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (user_goal["id"], item["id"], item["game_name"], item["normalized_game_name"], item["slot_label"], item["sort_order"]),
                )
                synced_goals.add(user_goal["id"])
        self.db.execute("UPDATE goal_templates SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (template_id,))
        self.db.commit()
        await interaction.response.send_message(
            f"Added {len(new_template_items)} game{'s' if len(new_template_items) != 1 else ''} to official **{template['title']}**.\n"
            f"Synced to {len(synced_goals)} user goal{'s' if len(synced_goals) != 1 else ''}; "
            f"skipped {duplicate_count} template and {user_duplicate_count} user duplicate{'s' if user_duplicate_count != 1 else ''}.",
            ephemeral=True,
        )

    @app_commands.command(name="newgoal", description="Create a custom series, A–Z, or genre goal.")
    @app_commands.choices(goaltype=[
        app_commands.Choice(name="Series", value="series"),
        app_commands.Choice(name="A–Z", value="az"),
        app_commands.Choice(name="Genre", value="genre"),
    ])
    async def newgoal(self, interaction: discord.Interaction, goaltype: app_commands.Choice[str], goaltitle: str) -> None:
        title = self._clean_title(goaltitle)
        if not title:
            await interaction.response.send_message("Give your goal a title.", ephemeral=True)
            return
        if self._find_user_goal(str(interaction.user.id), title):
            await interaction.response.send_message("You already have a goal with that title.", ephemeral=True)
            return
        await interaction.response.send_modal(GoalItemsModal(self, goaltype.value, title))

    @app_commands.command(name="mygoals", description="Show all of your personal goals and progress.")
    async def mygoals(self, interaction: discord.Interaction) -> None:
        goals = self.db.execute(
            "SELECT * FROM user_goals WHERE user_id = ? AND is_active = 1 ORDER BY goal_type, title",
            (str(interaction.user.id),),
        ).fetchall()
        if not goals:
            await interaction.response.send_message("You do not have any goals yet. Try `/newgoal` or `/copygoal`.", ephemeral=True)
            return
        grouped: dict[str, list[str]] = defaultdict(list)
        for goal in goals:
            completed, total, _ = self._progress(goal)
            grouped[goal["goal_type"]].append(f"**{goal['title']}** — {completed}/{total} complete")
        embed = discord.Embed(title=f"{interaction.user.display_name}'s Goals", color=0x4F8CFF)
        labels = {"series": "Series Goals", "az": "A–Z Goals", "genre": "Genre Goals"}
        for goal_type in GOAL_TYPES:
            for index, page in enumerate(chunk_lines(grouped[goal_type])):
                name = labels[goal_type] if index == 0 else f"{labels[goal_type]} (continued)"
                embed.add_field(name=name, value="\n".join(page), inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="mygoal", description="Show one of your goals with live backlog progress.")
    async def mygoal(self, interaction: discord.Interaction, goaltitle: str) -> None:
        goal = self._find_user_goal(str(interaction.user.id), goaltitle)
        if not goal:
            await interaction.response.send_message("I could not find that goal in your list.", ephemeral=True)
            return
        await self._send_goal(interaction, goal)

    @mygoal.autocomplete("goaltitle")
    async def mygoal_title_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._user_goal_choices(interaction, current)

    @app_commands.command(name="copygoal", description="Copy an official goal template into your goals.")
    @app_commands.choices(goaltype=[
        app_commands.Choice(name="Series", value="series"), app_commands.Choice(name="A–Z", value="az"),
        app_commands.Choice(name="Genre", value="genre"),
    ])
    async def copygoal(self, interaction: discord.Interaction, goaltype: app_commands.Choice[str], goaltitle: str) -> None:
        template = self._find_template(goaltype.value, goaltitle)
        if not template:
            await interaction.response.send_message("I could not find that official goal template.", ephemeral=True)
            return
        if self._find_user_goal(str(interaction.user.id), template["title"]):
            await interaction.response.send_message("You already have a goal with that title.", ephemeral=True)
            return
        cursor = self.db.execute(
            """INSERT INTO user_goals
               (user_id, user_name, goal_type, title, source_template_id, is_template_copy, sync_enabled)
               VALUES (?, ?, ?, ?, ?, 1, ?)""",
            (str(interaction.user.id), str(interaction.user), template["goal_type"], template["title"], template["id"], template["sync_enabled_by_default"]),
        )
        goal_id = cursor.lastrowid
        template_items = self.db.execute(
            "SELECT * FROM goal_template_items WHERE template_id = ? AND is_active = 1 ORDER BY sort_order, id", (template["id"],)
        ).fetchall()
        for item in template_items:
            self.db.execute(
                """INSERT INTO user_goal_items
                   (user_goal_id, source_template_item_id, game_name, normalized_game_name, slot_label, sort_order)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (goal_id, item["id"], item["game_name"], item["normalized_game_name"], item["slot_label"], item["sort_order"]),
            )
        self.db.commit()
        goal = self.db.execute("SELECT * FROM user_goals WHERE id = ?", (goal_id,)).fetchone()
        await self._send_goal(interaction, goal)

    @copygoal.autocomplete("goaltitle")
    async def copygoal_title_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._template_choices(interaction, current)

    @app_commands.command(name="addtogoal", description="Add one or more games to one of your goals.")
    async def addtogoal(self, interaction: discord.Interaction, goaltitle: str) -> None:
        goal = self._find_user_goal(str(interaction.user.id), goaltitle)
        if not goal:
            await interaction.response.send_message("I could not find that goal in your list.", ephemeral=True)
            return
        await interaction.response.send_modal(AddGoalItemsModal(self, goal["id"], goal["goal_type"]))

    @addtogoal.autocomplete("goaltitle")
    async def addgoal_title_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._user_goal_choices(interaction, current)

    @app_commands.command(name="removefromgoal", description="Remove a custom item or hide an official item from your goal.")
    async def removefromgoal(self, interaction: discord.Interaction, goaltitle: str, game: str) -> None:
        goal = self._find_user_goal(str(interaction.user.id), goaltitle)
        if not goal:
            await interaction.response.send_message("I could not find that goal in your list.", ephemeral=True)
            return
        item = self.db.execute(
            """SELECT * FROM user_goal_items WHERE user_goal_id = ?
               AND game_name = ? COLLATE NOCASE AND is_hidden = 0""", (goal["id"], game.strip())
        ).fetchone()
        if not item:
            await interaction.response.send_message("I could not find that game in the goal.", ephemeral=True)
            return
        if item["source_template_item_id"]:
            self.db.execute("UPDATE user_goal_items SET is_hidden = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (item["id"],))
            action = "Hidden"
        else:
            self.db.execute("DELETE FROM user_goal_items WHERE id = ?", (item["id"],))
            action = "Removed"
        self.db.commit()
        await interaction.response.send_message(f"{action} **{item['game_name']}** from **{goal['title']}**.", ephemeral=True)

    @removefromgoal.autocomplete("goaltitle")
    async def removegoal_title_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._user_goal_choices(interaction, current)

    @removefromgoal.autocomplete("game")
    async def removegoal_game_autocomplete(self, interaction: discord.Interaction, current: str):
        title = getattr(interaction.namespace, "goaltitle", "")
        goal = self._find_user_goal(str(interaction.user.id), title) if title else None
        if not goal:
            return []
        rows = self.db.execute(
            """SELECT game_name FROM user_goal_items WHERE user_goal_id = ? AND is_hidden = 0
               AND game_name LIKE ? COLLATE NOCASE ORDER BY sort_order, game_name LIMIT 25""",
            (goal["id"], f"%{current}%"),
        ).fetchall()
        return [app_commands.Choice(name=row[0][:100], value=row[0]) for row in rows]

    @app_commands.command(name="renamegoal", description="Rename one of your personal goals.")
    async def renamegoal(self, interaction: discord.Interaction, oldtitle: str, newtitle: str) -> None:
        goal = self._find_user_goal(str(interaction.user.id), oldtitle)
        title = self._clean_title(newtitle)
        if not goal or not title:
            await interaction.response.send_message("Check the old goal title and provide a valid new title.", ephemeral=True)
            return
        try:
            self.db.execute("UPDATE user_goals SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (title, goal["id"]))
            self.db.commit()
        except sqlite3.IntegrityError:
            self.db.rollback()
            await interaction.response.send_message("You already have a goal with that title.", ephemeral=True)
            return
        await interaction.response.send_message(f"Renamed **{goal['title']}** to **{title}**.", ephemeral=True)

    @renamegoal.autocomplete("oldtitle")
    async def renamegoal_title_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._user_goal_choices(interaction, current)

    @app_commands.command(name="deletegoal", description="Delete or abandon one of your goals.")
    async def deletegoal(self, interaction: discord.Interaction, goaltitle: str) -> None:
        goal = self._find_user_goal(str(interaction.user.id), goaltitle)
        if not goal:
            await interaction.response.send_message("I could not find that goal in your list.", ephemeral=True)
            return
        view = ConfirmDeleteGoalView(self, goal["id"], str(interaction.user.id), goal["title"])
        await interaction.response.send_message(f"Delete **{goal['title']}**? Your solo backlog will not be changed.", view=view, ephemeral=True)

    @deletegoal.autocomplete("goaltitle")
    async def deletegoal_title_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._user_goal_choices(interaction, current)

    @app_commands.command(name="syncgoal", description="Refresh a goal from your backlog and its official template.")
    async def syncgoal(self, interaction: discord.Interaction, goaltitle: str) -> None:
        goal = self._find_user_goal(str(interaction.user.id), goaltitle)
        if not goal:
            await interaction.response.send_message("I could not find that goal in your list.", ephemeral=True)
            return
        added, completed = self._sync_goal(goal)
        refreshed = self.db.execute("SELECT * FROM user_goals WHERE id = ?", (goal["id"],)).fetchone()
        done, total, _ = self._progress(refreshed)
        parts = [f"Synced **{goal['title']}**.", f"Current progress: **{done}/{total} completed**"]
        if completed:
            parts.append("New completions found: " + ", ".join(completed))
        if added:
            parts.append("New template games added: " + ", ".join(added))
        if not completed and not added:
            parts.append("Everything was already up to date.")
        await interaction.response.send_message("\n".join(parts), ephemeral=True)

    @syncgoal.autocomplete("goaltitle")
    async def syncgoal_title_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._user_goal_choices(interaction, current)

    @app_commands.command(name="addmissinghunts", description="Add a goal's missing games to your solo backlog.")
    async def addmissinghunts(self, interaction: discord.Interaction, goaltitle: str) -> None:
        goal = self._find_user_goal(str(interaction.user.id), goaltitle)
        if not goal:
            await interaction.response.send_message("I could not find that goal in your list.", ephemeral=True)
            return
        count, names = self.add_missing_to_backlog(goal["id"], interaction.user)
        await interaction.response.send_message(
            f"Added {count} missing hunt{'s' if count != 1 else ''} to your solo backlog as **Not Started**."
            + ("\n" + summarize_names(names) if names else ""), ephemeral=True
        )

    @addmissinghunts.autocomplete("goaltitle")
    async def missing_title_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._user_goal_choices(interaction, current)

    @app_commands.command(name="goallibrary", description="Browse official goals that you can copy.")
    async def goallibrary(self, interaction: discord.Interaction) -> None:
        await self._send_template_list(interaction, moderator=False)

    @app_commands.command(name="modgoal", description="Create an official goal template (goal moderators only).")
    @app_commands.choices(goaltype=[
        app_commands.Choice(name="Series", value="series"), app_commands.Choice(name="A–Z", value="az"),
        app_commands.Choice(name="Genre", value="genre"),
    ])
    async def modgoal(self, interaction: discord.Interaction, goaltype: app_commands.Choice[str], goaltitle: str) -> None:
        if not await self._require_mod(interaction):
            return
        title = self._clean_title(goaltitle)
        if not title:
            await interaction.response.send_message("Give the official goal a title.", ephemeral=True)
            return
        await interaction.response.send_modal(GoalItemsModal(self, goaltype.value, title, template=True))

    @app_commands.command(name="modaddtogoal", description="Add games to an official goal and sync copies.")
    @app_commands.choices(goaltype=[
        app_commands.Choice(name="Series", value="series"), app_commands.Choice(name="A–Z", value="az"),
        app_commands.Choice(name="Genre", value="genre"),
    ])
    async def modaddtogoal(self, interaction: discord.Interaction, goaltype: app_commands.Choice[str], goaltitle: str) -> None:
        if not await self._require_mod(interaction):
            return
        template = self._find_template(goaltype.value, goaltitle)
        if not template:
            await interaction.response.send_message("I could not find that official goal.", ephemeral=True)
            return
        await interaction.response.send_modal(AddGoalItemsModal(self, template["id"], template["goal_type"], template=True))

    @modaddtogoal.autocomplete("goaltitle")
    async def modadd_title_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._template_choices(interaction, current)

    @app_commands.command(name="modremovefromgoal", description="Archive a game in an official goal template.")
    @app_commands.choices(goaltype=[
        app_commands.Choice(name="Series", value="series"), app_commands.Choice(name="A–Z", value="az"),
        app_commands.Choice(name="Genre", value="genre"),
    ])
    async def modremovefromgoal(self, interaction: discord.Interaction, goaltype: app_commands.Choice[str], goaltitle: str, game: str) -> None:
        if not await self._require_mod(interaction):
            return
        template = self._find_template(goaltype.value, goaltitle)
        if not template:
            await interaction.response.send_message("I could not find that official goal.", ephemeral=True)
            return
        item = self.db.execute(
            """SELECT * FROM goal_template_items WHERE template_id = ? AND game_name = ? COLLATE NOCASE
               AND is_active = 1""", (template["id"], game.strip())
        ).fetchone()
        if not item:
            await interaction.response.send_message("I could not find that active game in the template.", ephemeral=True)
            return
        self.db.execute("UPDATE goal_template_items SET is_active = 0 WHERE id = ?", (item["id"],))
        cursor = self.db.execute(
            "UPDATE user_goal_items SET is_hidden = 1, updated_at = CURRENT_TIMESTAMP WHERE source_template_item_id = ?",
            (item["id"],),
        )
        self.db.commit()
        await interaction.response.send_message(
            f"Archived **{item['game_name']}** in **{template['title']}** and hid it from {cursor.rowcount} linked goal copy/copies. Solo backlogs were unchanged.",
            ephemeral=True,
        )

    @modremovefromgoal.autocomplete("goaltitle")
    async def modremove_title_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._template_choices(interaction, current)

    @modremovefromgoal.autocomplete("game")
    async def modremove_game_autocomplete(self, interaction: discord.Interaction, current: str):
        goal_type = self._goal_type_value(getattr(interaction.namespace, "goaltype", ""))
        title = getattr(interaction.namespace, "goaltitle", "")
        template = self._find_template(goal_type, title) if goal_type and title else None
        if not template:
            return []
        rows = self.db.execute(
            """SELECT game_name FROM goal_template_items WHERE template_id = ? AND is_active = 1
               AND game_name LIKE ? COLLATE NOCASE ORDER BY sort_order, game_name LIMIT 25""",
            (template["id"], f"%{current}%"),
        ).fetchall()
        return [app_commands.Choice(name=row[0][:100], value=row[0]) for row in rows]

    @app_commands.command(name="modrenamegoal", description="Rename an official goal without breaking linked copies.")
    async def modrenamegoal(self, interaction: discord.Interaction, oldtitle: str, newtitle: str) -> None:
        if not await self._require_mod(interaction):
            return
        templates = self.db.execute(
            "SELECT * FROM goal_templates WHERE title = ? COLLATE NOCASE AND is_active = 1", (oldtitle.strip(),)
        ).fetchall()
        if len(templates) != 1:
            await interaction.response.send_message("The old title must identify exactly one active official goal.", ephemeral=True)
            return
        template = templates[0]
        title = self._clean_title(newtitle)
        try:
            self.db.execute("UPDATE goal_templates SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (title, template["id"]))
            self.db.execute(
                """UPDATE user_goals SET title = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE source_template_id = ? AND title = ? COLLATE NOCASE""",
                (title, template["id"], template["title"]),
            )
            self.db.commit()
        except sqlite3.IntegrityError:
            self.db.rollback()
            await interaction.response.send_message("That rename would create a duplicate template or user goal title.", ephemeral=True)
            return
        await interaction.response.send_message(f"Renamed official **{template['title']}** to **{title}**; personal custom names were preserved.", ephemeral=True)

    @app_commands.command(name="modgoals", description="List official goal templates and copy counts.")
    async def modgoals(self, interaction: discord.Interaction) -> None:
        if not await self._require_mod(interaction):
            return
        await self._send_template_list(interaction, moderator=True)

    async def _send_template_list(self, interaction: discord.Interaction, moderator: bool) -> None:
        rows = self.db.execute(
            """SELECT t.*, COUNT(DISTINCT i.id) AS item_count, COUNT(DISTINCT ug.id) AS copy_count
               FROM goal_templates t
               LEFT JOIN goal_template_items i ON i.template_id = t.id AND i.is_active = 1
               LEFT JOIN user_goals ug ON ug.source_template_id = t.id AND ug.is_active = 1
               WHERE t.is_active = 1 GROUP BY t.id ORDER BY t.goal_type, t.title"""
        ).fetchall()
        if not rows:
            await interaction.response.send_message("There are no official goal templates yet.", ephemeral=True)
            return
        grouped: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            copies = f" — {row['copy_count']} copied" if moderator else ""
            grouped[row["goal_type"]].append(f"**{row['title']}** — {row['item_count']} games{copies}")
        embed = discord.Embed(title="Official Hunter's Haven Goal Library", color=0xF1C40F)
        labels = {"series": "Series", "az": "A–Z", "genre": "Genre"}
        for goal_type in GOAL_TYPES:
            for index, page in enumerate(chunk_lines(grouped[goal_type])):
                name = labels[goal_type] if index == 0 else f"{labels[goal_type]} (continued)"
                embed.add_field(name=name, value="\n".join(page), inline=False)
        embed.set_footer(text="Use /copygoal to start tracking an official goal.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _user_goal_choices(self, interaction: discord.Interaction, current: str):
        rows = self.db.execute(
            """SELECT title FROM user_goals WHERE user_id = ? AND is_active = 1
               AND title LIKE ? COLLATE NOCASE ORDER BY title LIMIT 25""",
            (str(interaction.user.id), f"%{current}%"),
        ).fetchall()
        return [app_commands.Choice(name=row[0][:100], value=row[0]) for row in rows]

    async def _template_choices(self, interaction: discord.Interaction, current: str):
        goal_type = self._goal_type_value(getattr(interaction.namespace, "goaltype", ""))
        if goal_type not in GOAL_TYPES:
            return []
        rows = self.db.execute(
            """SELECT title FROM goal_templates WHERE goal_type = ? AND is_active = 1
               AND title LIKE ? COLLATE NOCASE ORDER BY title LIMIT 25""",
            (goal_type, f"%{current}%"),
        ).fetchall()
        return [app_commands.Choice(name=row[0][:100], value=row[0]) for row in rows]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GoalSystem(bot))
