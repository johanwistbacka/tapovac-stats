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
        from homeassistant.helpers import entity_registry
        from homeassistant.helpers.entity import entity_sources
        from homeassistant.helpers.template import Template
        from custom_components.tapovac_stats.const import DOMAIN
        from custom_components.tapovac_stats.sensor import SummarySensor

        self.entry.pref_disable_new_entities = False
        source_entry = SimpleNamespace(entry_id='source', title='Robot',
                                       pref_disable_new_entities=False)
        entries = {self.entry.entry_id: self.entry, source_entry.entry_id: source_entry}
        self.hass.config_entries = SimpleNamespace(
            async_entries=lambda: list(entries.values()),
            async_get_entry=entries.get,
        )
        await entity_registry.async_load(self.hass)
        registry = entity_registry.async_get(self.hass)

        def register_sensor(entry, unique_id, object_id):
            sensor = registry.async_get_or_create(
                'sensor', DOMAIN, unique_id, config_entry=entry,
                suggested_object_id=object_id,
            )
            entity_sources(self.hass)[sensor.entity_id] = {'domain': DOMAIN}
            return sensor.entity_id

        self.source.rooms_named = lambda: [{'id': 1, 'name_text': 'Kök'}, {'id': 2, 'name_text': 'Hall'}]
        await self.coordinator.async_refresh()
        summary = SummarySensor(self.coordinator, self.entry)
        summary_id = register_sensor(self.entry, summary.unique_id, 'robotens_statistik')
        room_id = register_sensor(self.entry, 'kitchen_today', 'kok_idag')
        self.hass.states.async_set(room_id, '1')
        self.hass.states.async_set('sensor.annan_rumsoversikt', '0', {'rooms': []})
        card = yaml.safe_load((Path(__file__).parents[1] / 'examples/room_statistics_card.yaml').read_text())
        template = Template(card['content'], self.hass)
        self.assertIn('inte tillgänglig', template.async_render())
        self.hass.states.async_set(summary_id, '2', summary.extra_state_attributes)
        lines = template.async_render().splitlines()
        self.assertEqual(lines[0], '**Robotstatus inte tillgänglig**')
        self.assertIn('Idag: 1 av 2 rum städade.', lines)
        table = [line for line in lines if line.startswith('|')]
        self.assertEqual(len(table), 4)
        self.assertEqual(table[1], '| :--- | :--- | ---: | ---: |')
        self.assertTrue(table[2].startswith('| Kök | Idag '))
        self.assertTrue(table[2].endswith('| 1 | 1 |'))
        self.assertEqual(table[3], '| Hall | Okänt | 0 | 0 |')

        vacuum = registry.async_get_or_create(
            'vacuum', 'tapo_rv30', 'robot', config_entry=source_entry,
            suggested_object_id='omdopt_robot',
        ).entity_id
        charger = registry.async_get_or_create(
            'binary_sensor', 'tapo_rv30', 'charging', config_entry=source_entry,
            suggested_object_id='omdopt_laddning',
        ).entity_id
        for entity_id in [vacuum, charger]:
            entity_sources(self.hass)[entity_id] = {'domain': 'tapo_rv30'}
        # An unrelated robot must never supply the status or room.
        self.hass.states.async_set('vacuum.annan_robot', 'cleaning', {'current_room': 'Fel rum'})
        self.hass.states.async_set('binary_sensor.annan_laddning', 'on',
                                   {'device_class': 'battery_charging'})
        for state, label in [('cleaning', 'Städar'), ('paused', 'Paus'),
                             ('returning', 'Återvänder till laddstationen'),
                             ('idle', 'Vilar'), ('error', 'Fel'),
                             ('docked', 'Vid laddstationen')]:
            with self.subTest(state=state):
                self.hass.states.async_set(vacuum, state, {'current_room': 'Hall'})
                rendered = template.async_render()
                self.assertEqual(rendered.splitlines()[0], f'**{label}:** Hall')
                self.assertIn('| Kök |', rendered)
        self.hass.states.async_set(charger, 'on', {'device_class': 'battery_charging'})
        self.assertEqual(template.async_render().splitlines()[0], '**Laddar:** Hall')
        for charger_state in ['off', 'unknown', 'unavailable']:
            self.hass.states.async_set(charger, charger_state, {'device_class': 'battery_charging'})
            self.assertEqual(template.async_render().splitlines()[0], '**Vid laddstationen:** Hall')
        for room in [None, '', '   ']:
            self.hass.states.async_set(vacuum, 'paused', {'current_room': room})
            self.assertEqual(template.async_render().splitlines()[0], '**Paus**')
        self.hass.states.async_set(vacuum, 'cleaning')
        self.assertEqual(template.async_render().splitlines()[0], '**Städar**')
        self.hass.states.async_set(vacuum, 'cleaning', {'current_room': '<Hall>\nKök'})
        self.assertEqual(template.async_render().splitlines()[0], '**Städar:** &lt;Hall&gt; Kök')
        for state, label in [('unknown', 'Status okänd'),
                             ('unavailable', 'Robotstatus inte tillgänglig')]:
            self.hass.states.async_set(vacuum, state, {'current_room': 'Gammalt rum'})
            rendered = template.async_render()
            self.assertEqual(rendered.splitlines()[0], f'**{label}**')
            self.assertNotIn('Gammalt rum', rendered)
            self.assertIn('| Kök |', rendered)

        battery = registry.async_get_or_create(
            'sensor', 'tapo_rv30', 'battery', config_entry=source_entry,
            suggested_object_id='omdopt_batteri',
        ).entity_id
        entity_sources(self.hass)[battery] = {'domain': 'tapo_rv30'}
        entity_sources(self.hass)['sensor.annat_batteri'] = {'domain': 'tapo_rv30'}
        self.hass.states.async_set('sensor.annat_batteri', '99', {'device_class': 'battery'})
        self.hass.states.async_set(vacuum, 'cleaning', {'current_room': 'Hall'})
        for value, icon in [(0, 'mdi:battery-outline'), (74, 'mdi:battery-70'),
                            (100, 'mdi:battery')]:
            self.hass.states.async_set(battery, str(value), {'device_class': 'battery'})
            rendered = template.async_render(strict=True)
            self.assertEqual(rendered.splitlines()[0],
                             '**Städar:** Hall · '
                             f'<font color="{"#e53935" if value < 20 else "#607d8b"}">'
                             f'<ha-icon icon="{icon}"></ha-icon></font> {value} %')
            self.assertIn('| Kök |', rendered)
        self.hass.states.async_set(vacuum, 'docked', {'current_room': 'Vardagsrum'})
        self.hass.states.async_set(charger, 'on', {'device_class': 'battery_charging'})
        for value, icon in [(0, 'mdi:battery-charging-outline'),
                            (35, 'mdi:battery-charging-30'),
                            (74, 'mdi:battery-charging-70'),
                            (100, 'mdi:battery-charging-100')]:
            self.hass.states.async_set(battery, str(value), {'device_class': 'battery'})
            self.assertEqual(template.async_render(strict=True).splitlines()[0],
                             '**Laddar:** Vardagsrum · <font color="#43a047">'
                             f'<ha-icon icon="{icon}"></ha-icon></font> {value} %')
        self.hass.states.async_set(charger, 'off', {'device_class': 'battery_charging'})
        self.assertIn('<ha-icon icon="mdi:battery"></ha-icon></font> 100 %',
                      template.async_render(strict=True))
        self.hass.states.async_set(vacuum, 'cleaning', {'current_room': 'Hall'})
        for value in ['unknown', 'unavailable', '', '-1', '101', 'nan', 'inf']:
            self.hass.states.async_set(battery, value, {'device_class': 'battery'})
            self.assertEqual(template.async_render(strict=True).splitlines()[0], '**Städar:** Hall')
        self.hass.states.async_set(summary_id, '0', {'rooms': []})
        self.assertIn('Inga rum', template.async_render())
        self.hass.states.async_set(summary_id, 'unavailable')
        self.assertIn('inte tillgänglig', template.async_render())

        other = SimpleNamespace(entry_id='other', title='TapoVac Stats – Robot två',
                                pref_disable_new_entities=False)
        entries[other.entry_id] = other
        other_id = register_sensor(other, 'other_room_summary', 'robot_tva_statistik')
        self.hass.states.async_set(other_id, '2', summary.extra_state_attributes)
        self.assertIn('Flera TapoVac Stats-källor', template.async_render())
        selected = Template(card['content'].replace("'tapovac_stats'", f"'{other.title}'", 1), self.hass)
        self.assertIn('| Kök |', selected.async_render())

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
