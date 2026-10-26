"""Run with: python -m unittest discover -s tests -v (no live Discord needed)."""
import asyncio
from datetime import date
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import discord
from discord.ext import commands
from PIL import Image

from server_icons import IconStore, ServerIcons, normalize_icon, scheduled_theme, validate_window, window_active


def window(theme, start, end, priority=0):
    return dict(theme=theme, start=start, end=end, priority=priority)


class CalendarTests(unittest.TestCase):
    def test_requested_boundaries(self):
        windows = [window('halloween', '10-14', '11-01'), window('bonfire', '11-01', '11-06')]
        for day, expected in [('10-13', 'default'), ('10-14', 'halloween'), ('10-31', 'halloween'), ('11-01', 'bonfire'), ('11-05', 'bonfire'), ('11-06', 'default')]:
            with self.subTest(day=day):
                self.assertEqual(scheduled_theme(windows, date.fromisoformat('2026-' + day)), expected)
                self.assertEqual(scheduled_theme(windows, date.fromisoformat('2027-' + day)), expected)

    def test_year_crossing_and_one_off_easter(self):
        for day, expected in [('2026-12-30', False), ('2026-12-31', True), ('2027-01-01', True), ('2027-01-03', False)]:
            self.assertEqual(window_active(date.fromisoformat(day), '12-31', '01-03'), expected)
        self.assertTrue(window_active(date(2027, 3, 28), '2027-03-26', '2027-03-30'))
        self.assertFalse(window_active(date(2028, 3, 28), '2027-03-26', '2027-03-30'))

    def test_overlaps(self):
        windows = [window('autumn', '09-01', '12-01'), window('halloween', '10-14', '11-01', 10)]
        self.assertEqual(scheduled_theme(windows, date(2026, 10, 20)), 'halloween')
        windows.append(window('wedding', '2026-10-20', '2026-10-21'))
        self.assertEqual(scheduled_theme(windows, date(2026, 10, 20)), 'wedding')

    def test_reject_invalid_dates(self):
        for start, end in [('10-14', '2026-11-01'), ('02-30', '03-01'), ('11-06', '11-06'), ('2026-11-06', '2026-11-01'), ('1-1', '01-02')]:
            with self.subTest(start=start), self.assertRaises(ValueError):
                validate_window(start, end)
        validate_window('12-31', '01-03')
        validate_window('02-29', '03-01')

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

    async def test_auto_uses_today_and_falls_back_for_missing_asset(self):
        with patch('server_icons.datetime') as clock:
            clock.now.return_value.date.return_value = date(2026, 11, 1)
            await self.cog.apply_icon(self.guild, 'auto')
            self.assertEqual(self.guild.edit.call_args.kwargs['icon'], b'bonfire')
            self.cog.store.db.execute("DELETE FROM server_icon_assets WHERE theme = 'bonfire'")
            self.cog.store.db.commit()
            result = await self.cog.apply_icon(self.guild)
            self.assertIn('Missing bonfire', result)
            self.assertEqual(self.guild.edit.call_args.kwargs['icon'], b'default')
            clock.now.return_value.date.return_value = date(2026, 11, 6)
            await self.cog.apply_icon(self.guild)
            self.assertIsNone(self.cog.store.ensure(123)['last_error'])

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
        interaction = SimpleNamespace(guild=self.guild, permissions=SimpleNamespace(manage_guild=False), response=SimpleNamespace(send_message=AsyncMock()))
        with self.assertRaises(discord.app_commands.MissingPermissions):
            await self.cog.interaction_check(interaction)
        interaction.permissions.manage_guild = True
        self.assertTrue(await self.cog.interaction_check(interaction))

    async def test_extension_registers_and_unloads(self):
        with patch.dict('os.environ', {'HUNTERS_LEDGER_DB': ':memory:'}):
            await self.bot.load_extension('server_icons')
            group = self.bot.tree.get_command('servericon')
            self.assertEqual({command.name for command in group.commands}, {'set', 'upload', 'schedule', 'unschedule', 'status'})
            self.assertTrue(group.guild_only)
            self.assertTrue(group.default_permissions.manage_guild)
            self.assertTrue(self.bot.get_cog('ServerIcons').check_icons.is_running())
            await self.bot.unload_extension('server_icons')
            self.assertIsNone(self.bot.tree.get_command('servericon'))
            await asyncio.sleep(0)


if __name__ == '__main__':
    unittest.main()
