"""Focused tests for official goal schema and moderator rename behavior."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
import sqlite3
import tempfile
import unittest

import goal_system
from goal_system import GOAL_OWNER_USER_ID, GOAL_TYPES, GoalSystem, normalize_game_name


class FakeResponse:
    def __init__(self):
        self.messages = []

    async def send_message(self, content, **kwargs):
        self.messages.append((content, kwargs))


def run_immediate(coroutine):
    """Run a coroutine whose test doubles complete without an event loop."""
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    raise AssertionError("Test coroutine unexpectedly waited on asynchronous I/O")


class GoalSystemTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.gettempdir()) / f"hunters_ledger_goal_test_{uuid4().hex}.db"
        with patch.object(goal_system, "DB_PATH", str(self.path)):
            self.cog = GoalSystem(SimpleNamespace())

    def tearDown(self):
        self.cog.cog_unload()
        self.path.unlink(missing_ok=True)

    def test_developer_is_a_supported_goal_type(self):
        self.assertIn("developer", GOAL_TYPES)
        self.cog.db.execute(
            """INSERT INTO goal_templates
               (goal_type, title, created_by_user_id, created_by_user_name)
               VALUES ('developer', 'Remedy', '1', 'Tester')"""
        )
        self.cog.db.execute(
            """INSERT INTO user_goals (user_id, user_name, goal_type, title)
               VALUES ('2', 'Hunter', 'developer', 'Remedy Games')"""
        )
        self.cog.db.commit()

    def test_existing_goal_schema_migrates_to_developer_type(self):
        legacy_path = Path(tempfile.gettempdir()) / f"hunters_ledger_legacy_goal_{uuid4().hex}.db"
        database = sqlite3.connect(legacy_path)
        database.executescript(
            """
            CREATE TABLE goal_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_type TEXT NOT NULL CHECK(goal_type IN ('series', 'az', 'genre', 'event', 'personal')),
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
            CREATE TABLE user_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                user_name TEXT NOT NULL,
                goal_type TEXT NOT NULL CHECK(goal_type IN ('series', 'az', 'genre', 'event', 'personal')),
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
            """
        )
        database.close()

        try:
            with patch.object(goal_system, "DB_PATH", str(legacy_path)):
                migrated = GoalSystem(SimpleNamespace())
            migrated.db.execute(
                """INSERT INTO goal_templates
                   (goal_type, title, created_by_user_id, created_by_user_name)
                   VALUES ('developer', 'Double Fine', '1', 'Tester')"""
            )
            migrated.db.execute(
                """INSERT INTO user_goals (user_id, user_name, goal_type, title)
                   VALUES ('2', 'Hunter', 'developer', 'Double Fine Games')"""
            )
            migrated.db.commit()
            self.assertEqual(migrated.db.execute("PRAGMA foreign_key_check").fetchall(), [])
            migrated.cog_unload()
        finally:
            legacy_path.unlink(missing_ok=True)

    def test_moderator_can_rename_game_in_template_and_linked_copy(self):
        template = self.cog.db.execute(
            """INSERT INTO goal_templates
               (goal_type, title, created_by_user_id, created_by_user_name)
               VALUES ('developer', 'Remedy', '1', 'Tester')"""
        )
        template_id = template.lastrowid
        template_item = self.cog.db.execute(
            """INSERT INTO goal_template_items
               (template_id, game_name, normalized_game_name)
               VALUES (?, 'Alan Wake', ?)""",
            (template_id, normalize_game_name("Alan Wake")),
        )
        user_goal = self.cog.db.execute(
            """INSERT INTO user_goals
               (user_id, user_name, goal_type, title, source_template_id, is_template_copy)
               VALUES ('2', 'Hunter', 'developer', 'Remedy', ?, 1)""",
            (template_id,),
        )
        self.cog.db.execute(
            """INSERT INTO user_goal_items
               (user_goal_id, source_template_item_id, game_name, normalized_game_name)
               VALUES (?, ?, 'Alan Wake', ?)""",
            (user_goal.lastrowid, template_item.lastrowid, normalize_game_name("Alan Wake")),
        )
        self.cog.db.commit()

        interaction = SimpleNamespace(
            user=SimpleNamespace(id=GOAL_OWNER_USER_ID),
            response=FakeResponse(),
        )
        run_immediate(
            GoalSystem.modrenamegameingoal.callback(
                self.cog, interaction, "Remedy", "Alan Wake", "Alan Wake Remastered"
            )
        )

        template_name = self.cog.db.execute(
            "SELECT game_name FROM goal_template_items WHERE id = ?", (template_item.lastrowid,)
        ).fetchone()[0]
        copy_name = self.cog.db.execute(
            "SELECT game_name FROM user_goal_items WHERE source_template_item_id = ?",
            (template_item.lastrowid,),
        ).fetchone()[0]
        self.assertEqual(template_name, "Alan Wake Remastered")
        self.assertEqual(copy_name, "Alan Wake Remastered")
        self.assertEqual(len(interaction.response.messages), 1)


if __name__ == "__main__":
    unittest.main()
