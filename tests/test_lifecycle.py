"""Integration checks against real Home Assistant APIs, when installed."""
import importlib.util
import inspect
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

HAS_HA = importlib.util.find_spec('homeassistant') is not None


@unittest.skipUnless(HAS_HA, 'Home Assistant is not installed')
class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from homeassistant.core import HomeAssistant
        from custom_components.tapovac_stats.coordinator import TapoStatsCoordinator
        self.temp = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.temp.name)
        self.hass.config.time_zone = 'Europe/Stockholm'
        self.listeners = []
        self.removed = []

        def listen(callback):
            self.listeners.append(callback)
            def remove():
                self.removed.append(callback)
            return remove

        stamp = int(datetime.now(timezone.utc).timestamp())
        self.source = SimpleNamespace(
            last_update_success=True, _freshness_loaded=True, map_id=1,
            rooms_named=lambda: [{'id': 1, 'name_text': 'Kök'}],
            rooms_last_cleaned={'1:1': {'last_cleaned': stamp, 'coverage': 80}},
            rooms_clean_log={'1:1': [stamp]}, async_add_listener=listen)
        self.hass.data['tapo_rv30'] = {'source': self.source}
        self.entry = SimpleNamespace(title='Test', entry_id='stats', data={'source_entry_id': 'source'},
                                     async_on_unload=lambda callback: None, pref_disable_polling=False)
        self.coordinator = TapoStatsCoordinator(self.hass, self.entry)
        self.stop = self.coordinator.start()

    async def asyncTearDown(self):
        self.stop()
        await self.hass.async_stop()
        self.temp.cleanup()

    async def test_source_failure_recovery_and_unload(self):
        await self.coordinator.async_refresh()
        self.assertTrue(self.coordinator.last_update_success)
        self.assertEqual(self.coordinator.data[(1, 1)].today, 1)
        self.source.last_update_success = False
        await self.coordinator.async_refresh()
        self.assertFalse(self.coordinator.last_update_success)
        self.source.last_update_success = True
        await self.coordinator.async_refresh()
        self.assertTrue(self.coordinator.last_update_success)
        del self.hass.data['tapo_rv30']['source']
        await self.coordinator.async_refresh()
        self.assertFalse(self.coordinator.last_update_success)
        self.assertEqual(len(self.removed), 1)
        self.hass.data['tapo_rv30']['source'] = self.source
        await self.coordinator.async_refresh()
        self.assertTrue(self.coordinator.last_update_success)
        self.assertEqual(len(self.listeners), 2)

    async def test_sensors_and_map_switch(self):
        from custom_components.tapovac_stats.sensor import RoomSensor, SummarySensor
        await self.coordinator.async_refresh()
        sensor = RoomSensor(self.coordinator, self.entry, (1, 1), 'today')
        summary = SummarySensor(self.coordinator, self.entry)
        self.assertTrue(sensor.available)
        self.assertEqual(sensor.native_value, 1)
        self.assertEqual(summary.extra_state_attributes['rooms'][0]['name'], 'Kök')
        self.source.map_id = 2
        await self.coordinator.async_refresh()
        self.assertFalse(sensor.available)
        self.assertIsNone(sensor.native_value)
        self.assertIn((2, 1), self.coordinator.data)

    async def test_card_template(self):
        from pathlib import Path
        import yaml
        from homeassistant.helpers.template import Template
        await self.coordinator.async_refresh()
        from custom_components.tapovac_stats.sensor import SummarySensor
        summary = SummarySensor(self.coordinator, self.entry)
        self.hass.states.async_set('sensor.byt_till_din_rumsoversikt', '1', summary.extra_state_attributes)
        card = yaml.safe_load((Path(__file__).parents[1] / 'examples/room_statistics_card.yaml').read_text())
        rendered = Template(card['content'], self.hass).async_render()
        self.assertIn('| Kök |', rendered)
        self.assertIn('| 1 | 1 |', rendered)
        self.hass.states.async_set('sensor.byt_till_din_rumsoversikt', 'unavailable')
        rendered = Template(card['content'], self.hass).async_render()
        self.assertIn('inte tillgänglig', rendered)

    async def test_source_listener_updates_counts(self):
        import asyncio
        await self.coordinator.async_refresh()
        stamp = int(datetime.now(timezone.utc).timestamp())
        self.source.rooms_clean_log['1:1'] = [stamp - 60, stamp]
        self.listeners[-1]()
        await asyncio.sleep(0)
        await self.hass.async_block_till_done()
        self.assertEqual(self.coordinator.data[(1, 1)].today, 2)

    async def test_discover_new_rooms_without_duplicate_sensors(self):
        from custom_components.tapovac_stats.const import DOMAIN
        from custom_components.tapovac_stats.sensor import async_setup_entry
        self.hass.data[DOMAIN] = {'stats': self.coordinator}
        removers = []
        self.entry.async_on_unload = removers.append
        entities = []
        await self.coordinator.async_refresh()
        await async_setup_entry(self.hass, self.entry, entities.extend)
        self.assertEqual(len(entities), 4)
        await self.coordinator.async_refresh()
        self.assertEqual(len(entities), 4)
        self.source.rooms_named = lambda: [{'id': 1, 'name_text': 'Kök'}, {'id': 2, 'name_text': 'Hall'}]
        await self.coordinator.async_refresh()
        self.assertEqual(len(entities), 7)
        for remove in removers:
            result = remove()
            if inspect.isawaitable(result):
                await result

    async def test_configuration_source_selection(self):
        from unittest.mock import patch, AsyncMock, Mock
        from custom_components.tapovac_stats.config_flow import TapoStatsConfigFlow
        flow = TapoStatsConfigFlow()
        flow.hass = SimpleNamespace(config_entries=SimpleNamespace(async_entries=Mock()))
        source_entry = SimpleNamespace(entry_id='source', title='Robot')
        with patch.object(flow.hass.config_entries, 'async_entries', return_value=[]):
            result = await flow.async_step_user()
            self.assertEqual(result['reason'], 'no_source')
        with patch.object(flow.hass.config_entries, 'async_entries', return_value=[source_entry]):
            result = await flow.async_step_user({'source_entry_id': 'gone'})
            self.assertEqual(result['errors']['base'], 'source_missing')
            with patch.object(flow, 'async_set_unique_id', new=AsyncMock()), patch.object(flow, '_abort_if_unique_id_configured'):
                result = await flow.async_step_user({'source_entry_id': 'source'})
                self.assertEqual(result['data'], {'source_entry_id': 'source'})

    async def test_timer_recalculates_midnight_without_source_change(self):
        from unittest.mock import patch
        before = datetime(2026, 11, 15, 22, 59, tzinfo=timezone.utc)
        after = datetime(2026, 11, 15, 23, 1, tzinfo=timezone.utc)
        self.source.rooms_clean_log['1:1'] = [int(before.timestamp())]
        self.source.rooms_last_cleaned['1:1']['last_cleaned'] = int(before.timestamp())
        with patch('custom_components.tapovac_stats.coordinator.dt_util.utcnow', return_value=before):
            await self.coordinator.async_refresh()
            self.assertEqual(self.coordinator.data[(1, 1)].today, 1)
        with patch('custom_components.tapovac_stats.coordinator.dt_util.utcnow', return_value=after):
            await self.coordinator._tick(after)
            self.assertEqual(self.coordinator.data[(1, 1)].today, 0)
            self.assertEqual(self.coordinator.data[(1, 1)].last_seven_days, 1)

    async def test_missing_source_on_initial_setup_then_recovery(self):
        from custom_components.tapovac_stats import async_setup_entry, async_unload_entry
        from unittest.mock import AsyncMock
        from custom_components.tapovac_stats.const import DOMAIN
        removers = []
        self.entry.async_on_unload = removers.append
        self.hass.config_entries = SimpleNamespace(
            async_forward_entry_setups=AsyncMock(),
            async_unload_platforms=AsyncMock(return_value=True))
        del self.hass.data['tapo_rv30']['source']
        self.assertTrue(await async_setup_entry(self.hass, self.entry))
        coordinator = self.hass.data[DOMAIN]['stats']
        self.assertFalse(coordinator.last_update_success)
        self.hass.data['tapo_rv30']['source'] = self.source
        await coordinator._tick(None)
        self.assertTrue(coordinator.last_update_success)
        self.assertTrue(await async_unload_entry(self.hass, self.entry))
        self.assertNotIn('stats', self.hass.data[DOMAIN])
        for remove in removers:
            result = remove()
            if inspect.isawaitable(result):
                await result
        self.assertIsNone(coordinator._source)
