"""Run with: python -m unittest discover -s tests -v (no live Discord needed)."""
import asyncio
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import discord
from discord.ext import commands
from PIL import Image

from server_icons import IconStore, ServerIcons, normalize_icon


class ImageTests(unittest.TestCase):
    def test_image_validation_and_resize(self):
        data = BytesIO()
        Image.new('RGB', (1000, 600), 'teal').save(data, format='JPEG')
        with Image.open(BytesIO(normalize_icon(data.getvalue()))) as result:
            self.assertEqual(result.size, (512, 512))
            self.assertEqual(result.format, 'PNG')
        with self.assertRaises(ValueError):
            normalize_icon(b'not an image')


class RepositoryIconTests(unittest.TestCase):
    def setUp(self):
        self.theme = 'test_' + uuid4().hex
        self.path = Path.cwd() / (self.theme + '.png')
        self.store = IconStore(':memory:', icon_directory=Path.cwd())
        self.store.ensure(123)

    def tearDown(self):
        self.store.db.close()
        self.path.unlink(missing_ok=True)
        self.path.with_suffix('.jpg').unlink(missing_ok=True)

    def test_file_discovery_precedence_replacement_and_upload_fallback(self):
        self.store.db.execute('INSERT INTO server_icon_assets VALUES (?, ?, ?)', (123, self.theme, b'uploaded'))
        self.store.db.commit()
        Image.new('RGB', (20, 20), 'red').save(self.path)
        first = self.store.asset(123, self.theme)
        self.assertNotEqual(first, b'uploaded')
        self.assertIn(self.theme, self.store.themes(123))
        self.assertIn(self.theme, self.store.themes(456))
        with Image.open(BytesIO(first)) as image:
            self.assertEqual(image.size, (512, 512))
        # A replacement on disk must invalidate the resized-image cache.
        Image.new('RGB', (30, 30), 'blue').save(self.path)
        self.assertNotEqual(self.store.asset(123, self.theme), first)
        self.path.unlink()
        self.assertEqual(self.store.asset(123, self.theme), b'uploaded')
        self.assertIsNone(self.store.asset(456, self.theme))

    def test_png_preferred_and_invalid_file_is_reported(self):
        Image.new('RGB', (20, 20), 'red').save(self.path)
        Image.new('RGB', (20, 20), 'blue').save(self.path.with_suffix('.jpg'))
        self.assertEqual(self.store.file_assets()[self.theme], self.path)
        self.path.write_bytes(b'invalid image')
        with self.assertRaises(ValueError):
            self.store.asset(123, self.theme)


class IconIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.path = str(Path.cwd() / f'server_icon_test_{uuid4().hex}.db')
        self.bot = commands.Bot(command_prefix='!', intents=discord.Intents.none())
        self.cog = ServerIcons(self.bot, self.path)
        self.guild = SimpleNamespace(id=123, icon=None, unavailable=False)
        async def edit(**kwargs):
            self.guild.icon = SimpleNamespace(key=__import__('hashlib').sha256(kwargs['icon']).hexdigest())
            return self.guild
        self.guild.edit = AsyncMock(side_effect=edit)
        self.cog.store.ensure(123)
        for theme in ['default', 'halloween', 'bonfire']:
            self.cog.store.db.execute('INSERT INTO server_icon_assets VALUES (?, ?, ?)', (123, theme, theme.encode()))
        self.cog.store.db.commit()

    async def asyncTearDown(self):
        self.cog.store.db.close()
        await self.bot.close()
        Path(self.path).unlink(missing_ok=True)

    async def test_default_override_restart_and_skip_unchanged(self):
        await self.cog.apply_icon(self.guild, 'halloween')
        await self.cog.apply_icon(self.guild, 'default')
        await self.cog.apply_icon(self.guild)
        self.assertEqual(self.guild.edit.await_count, 2)
        self.cog.store.db.close()
        self.cog.store = IconStore(self.path)
        await self.cog.apply_icon(self.guild)
        self.assertEqual(self.cog.store.ensure(123)['mode'], 'default')
        self.assertEqual(self.guild.edit.await_count, 2)
        self.assertEqual(self.cog.store.ensure(456)['mode'], 'paused')
        self.assertIsNone(self.cog.store.asset(456, 'default'))

    async def test_failed_override_keeps_previous_mode_and_retries(self):
        await self.cog.apply_icon(self.guild, 'halloween')
        self.guild.edit.side_effect = discord.Forbidden(SimpleNamespace(status=403, reason='Forbidden'), 'Missing permissions')
        with self.assertRaises(discord.Forbidden):
            await self.cog.apply_icon(self.guild, 'default')
        self.assertEqual(self.cog.store.ensure(123)['mode'], 'halloween')
        with self.assertRaises(ValueError):
            await self.cog.apply_icon(self.guild, 'wedding')
        self.assertEqual(self.cog.store.ensure(123)['mode'], 'halloween')

    async def test_manual_selection_requires_an_available_asset(self):
        await self.cog.apply_icon(self.guild, 'bonfire')
        self.assertEqual(self.guild.edit.call_args.kwargs['icon'], b'bonfire')
        self.cog.store.db.execute("DELETE FROM server_icon_assets WHERE theme = 'bonfire'")
        self.cog.store.db.commit()
        with self.assertRaises(ValueError):
            await self.cog.apply_icon(self.guild, 'bonfire')
        self.assertEqual(self.cog.store.ensure(123)['mode'], 'bonfire')

    async def test_old_auto_mode_is_migrated_to_paused(self):
        self.cog.store.db.execute("UPDATE server_icon_settings SET mode = 'auto' WHERE guild_id = 123")
        self.cog.store.db.commit()
        self.cog.store.db.close()
        self.cog.store = IconStore(self.path)
        self.assertEqual(self.cog.store.ensure(123)['mode'], 'paused')
        self.assertIn('No icon is selected', await self.cog.apply_icon(self.guild))

    async def test_image_replacement_and_external_change_reapply(self):
        await self.cog.apply_icon(self.guild, 'default')
        self.cog.store.db.execute("UPDATE server_icon_assets SET image = ? WHERE theme = 'default'", (b'new-default',))
        self.cog.store.db.commit()
        await self.cog.apply_icon(self.guild)
        self.assertEqual(self.guild.edit.call_args.kwargs['icon'], b'new-default')
        self.guild.icon = SimpleNamespace(key='externally-changed')
        await self.cog.apply_icon(self.guild)
        self.assertEqual(self.guild.edit.await_count, 3)

    async def test_permission_check(self):
        interaction = SimpleNamespace(
            guild=self.guild, user=SimpleNamespace(id=999),
            permissions=SimpleNamespace(manage_guild=True, administrator=False))
        # Manage Server alone must not authorize any icon command.
        with self.assertRaises(discord.app_commands.MissingPermissions):
            await self.cog.interaction_check(interaction)
        # Administrator is sufficient.
        interaction.permissions.administrator = True
        self.assertTrue(await self.cog.interaction_check(interaction))
        # Tide44 is allowed even without Administrator or Manage Server.
        interaction.user.id = 420996360699904000
        interaction.permissions.administrator = False
        interaction.permissions.manage_guild = False
        self.assertTrue(await self.cog.interaction_check(interaction))
        # Commands remain server-only, including for the owner.
        interaction.guild = None
        with self.assertRaises(discord.app_commands.MissingPermissions):
            await self.cog.interaction_check(interaction)

    async def test_extension_registers_and_unloads(self):
        with patch.dict('os.environ', {'HUNTERS_LEDGER_DB': ':memory:'}):
            await self.bot.load_extension('server_icons')
            group = self.bot.tree.get_command('servericon')
            self.assertEqual({command.name for command in group.commands}, {'set', 'upload', 'status'})
            self.assertTrue(group.guild_only)
            self.assertIsNone(group.default_permissions)
            # Every registered subcommand must enforce the runtime restriction.
            denied = SimpleNamespace(guild=self.guild, user=SimpleNamespace(id=999),
                                     permissions=SimpleNamespace(administrator=False))
            for command in group.commands:
                with self.assertRaises(discord.app_commands.MissingPermissions):
                    await command._check_can_run(denied)
            await self.bot.unload_extension('server_icons')
            self.assertIsNone(self.bot.tree.get_command('servericon'))
            await asyncio.sleep(0)


if __name__ == '__main__':
    unittest.main()
