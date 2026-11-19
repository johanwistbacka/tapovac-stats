"""Readable card behavior using synthetic Home Assistant states."""
from datetime import datetime
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

HAS_HA = importlib.util.find_spec('homeassistant') is not None
ROOT = Path(__file__).parents[1]


@unittest.skipUnless(HAS_HA, 'Home Assistant is not installed')
class ReadableCardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import yaml
        from homeassistant.core import HomeAssistant
        from homeassistant.helpers import entity_registry
        from homeassistant.helpers.template import Template
        from homeassistant.util import dt as dt_util

        self.temp = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.temp.name)
        self.hass.config.time_zone = 'Europe/Stockholm'
        self.addCleanup(dt_util.set_default_time_zone, dt_util.DEFAULT_TIME_ZONE)
        dt_util.set_default_time_zone(ZoneInfo('Europe/Stockholm'))
        self.now = datetime(2026, 11, 19, 12, tzinfo=ZoneInfo('Europe/Stockholm'))
        clock = patch('homeassistant.util.dt.now', side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.entries = {
            key: SimpleNamespace(entry_id=key, title=title, pref_disable_new_entities=False)
            for key, title in [('stats', 'Statistik'), ('source', 'Robot'), ('other', 'Annan robot')]
        }
        self.hass.config_entries = SimpleNamespace(
            async_entries=lambda: list(self.entries.values()),
            async_get_entry=self.entries.get,
        )
        await entity_registry.async_load(self.hass)
        self.registry = entity_registry.async_get(self.hass)
        self.rooms = [
            {'name': 'Hall', 'last_cleaned': '2026-11-19T09:00:00+00:00',
             'today': 2, 'last_seven_days': 4},
            {'name': 'Kök', 'last_cleaned': '2026-11-18T08:00:00+00:00',
             'today': 0, 'last_seven_days': 3},
        ]
        self.summary = self.set_entity('sensor', 'summary', '2',
                                      {'rooms': self.rooms, 'source_entry_id': 'source'},
                                      entry='stats')
        self.robot = self.set_entity('vacuum', 'robot', 'cleaning', {'current_room': 'Hall'})
        self.charger = self.set_entity('binary_sensor', 'charger', 'off',
                                      {'device_class': 'battery_charging'})
        self.battery = self.set_entity('sensor', 'battery', '74', {'device_class': 'battery'})
        card = yaml.safe_load((ROOT / 'examples/room_statistics_card.yaml').read_text())
        self.template = Template(card['content'], self.hass)

    async def asyncTearDown(self):
        await self.hass.async_stop()
        self.temp.cleanup()

    def set_entity(self, domain, key, state, attributes, entry='source'):
        from homeassistant.helpers.entity import entity_sources
        integration = 'tapovac_stats' if entry == 'stats' else 'tapo_rv30'
        entity = self.registry.async_get_or_create(
            domain, integration, f'{entry}_{key}', config_entry=self.entries[entry],
            suggested_object_id=f'renamed_{entry}_{key}',
        )
        entity_sources(self.hass)[entity.entity_id] = {'domain': integration}
        self.hass.states.async_set(entity.entity_id, state, attributes)
        return entity.entity_id

    def render(self):
        return self.template.async_render(strict=True)

    def set_rooms(self):
        self.hass.states.async_set(self.summary, str(len(self.rooms)),
                                   {'rooms': self.rooms, 'source_entry_id': 'source'})

    async def test_summary_counts_distinct_rooms_and_marks_only_cleaning(self):
        rendered = self.render()
        self.assertIn('Idag: 1 av 2 rum städade.', rendered)
        self.assertIn('| ▶ **Hall** | Idag 10:00 | 2 | 4 |', rendered)
        self.assertIn('| Kök | Igår 09:00 |', rendered)
        for state in ['paused', 'idle', 'returning', 'docked', 'unavailable']:
            self.hass.states.async_set(self.robot, state, {'current_room': 'Hall'})
            self.assertNotIn('▶', self.render())
        self.hass.states.async_set(self.robot, 'cleaning', {'current_room': 'Hall'})
        self.rooms[1]['name'] = 'Hall'
        self.set_rooms()
        self.assertNotIn('▶', self.render())

    async def test_partial_history_does_not_claim_exact_counts(self):
        self.rooms[1]['today'] = None
        self.set_rooms()
        self.assertIn('Idag: minst 1 av 2 rum städade · ofullständig historik.', self.render())
        self.rooms[0]['today'] = None
        self.set_rooms()
        self.assertIn('Idag: statistik saknas.', self.render())

    async def test_relative_dates_follow_local_midnight_and_change_with_time(self):
        self.now = datetime(2026, 11, 19, 0, 10, tzinfo=ZoneInfo('Europe/Stockholm'))
        self.rooms[0]['last_cleaned'] = '2026-11-18T23:05:00+00:00'
        self.rooms[1]['last_cleaned'] = '2026-11-18T22:45:00+00:00'
        self.set_rooms()
        self.assertIn('Idag 00:05', self.render())
        self.assertIn('Igår 23:45', self.render())
        self.now = self.now.replace(day=20)
        self.assertIn('Igår 00:05', self.render())
        self.assertIn('18/11 23:45', self.render())
        self.rooms[1]['last_cleaned'] = '2025-12-31T09:00:00+00:00'
        self.set_rooms()
        self.assertIn('31/12 2025 10:00', self.render())

    async def test_battery_colors_and_charging_override(self):
        for value, color in [(0, '#e53935'), (19, '#e53935'), (20, '#fb8c00'),
                             (40, '#fb8c00'), (41, '#607d8b'), (100, '#607d8b')]:
            self.hass.states.async_set(self.battery, str(value), {'device_class': 'battery'})
            self.assertIn(f'<font color="{color}">', self.render())
        self.hass.states.async_set(self.charger, 'on', {'device_class': 'battery_charging'})
        self.assertIn('<font color="#43a047">', self.render())
        self.hass.states.async_set(self.battery, 'unavailable', {'device_class': 'battery'})
        self.assertNotIn('<font', self.render())

    async def test_fault_is_conditional_escaped_and_isolated_from_other_robots(self):
        self.set_entity('binary_sensor', 'problem', 'on', {'code': 2, 'error': 'Fel robot'}, entry='other')
        self.set_entity('binary_sensor', 'maintenance', 'on', {'device_class': 'problem'})
        fault = self.set_entity('binary_sensor', 'problem', 'off', {'code': 0, 'error': None})
        self.assertNotIn('<ha-alert', self.render())
        self.hass.states.async_set(fault, 'on', {'code': 4, 'error': '<Lyft roboten>'})
        self.assertIn('<ha-alert alert-type="error">Fel: &lt;Lyft roboten&gt;</ha-alert>', self.render())
        self.assertNotIn('Fel robot', self.render())
        for state in ['off', 'unknown', 'unavailable']:
            self.hass.states.async_set(fault, state, {'code': 4, 'error': 'Gammalt fel'})
            self.assertNotIn('<ha-alert', self.render())
        for message in [None, '', '  ']:
            self.hass.states.async_set(fault, 'on', {'code': 4, 'error': message})
            self.assertNotIn('<ha-alert', self.render())

    async def test_run_details_are_closed_below_table_and_respect_area_units(self):
        self.assertNotIn('<details', self.render())
        self.hass.states.async_set(self.robot, 'cleaning',
                                   {'current_room': 'Hall', 'clean_time_min': 24, 'clean_percent': 68})
        area = self.set_entity('sensor', 'area', '30.5', {'unit_of_measurement': 'm²'})
        rendered = self.render()
        self.assertIn('<details>\n<summary>Städinformation</summary>', rendered)
        self.assertNotIn('<details open', rendered)
        self.assertIn('Pågående körning', rendered)
        self.assertIn('Tid: 24 min', rendered)
        self.assertIn('Städad yta: 30,5 m²', rendered)
        self.assertIn('Förlopp: 68 %', rendered)
        self.assertGreater(rendered.index('<details>'), rendered.index('| Kök |'))
        self.hass.states.async_set(area, '328', {'unit_of_measurement': 'ft²'})
        self.assertIn('Städad yta: 328 ft²', self.render())
        self.hass.states.async_set(area, 'unavailable', {'unit_of_measurement': 'ft²'})
        self.assertNotIn('Städad yta:', self.render())
        self.hass.states.async_set(self.robot, 'docked', {'clean_time_min': 24})
        self.assertIn('Senast rapporterade körning', self.render())
        self.hass.states.async_set(self.robot, 'unavailable', {'clean_time_min': 24})
        self.assertNotIn('<details', self.render())

    async def test_planner_due_rooms_are_not_presented_as_robot_queue(self):
        self.set_entity('sensor', 'planner', 'Waiting for battery',
                        {'due_rooms': ['Kök', 'Hall'], 'waiting_for': 'battery', 'running': False})
        self.hass.states.async_set(self.robot, 'returning', {'current_room': 'Hall'})
        rendered = self.render()
        self.assertIn('Återvänder till laddstationen', rendered)
        for claim in ['Nästa rum', 'Fortsätter efter laddning', 'Städningen avslutad']:
            self.assertNotIn(claim, rendered)

    async def test_grid_example_contains_same_template_and_robot_controls(self):
        import yaml
        grid = yaml.safe_load((ROOT / 'examples/room_statistics_grid.yaml').read_text())
        standalone = yaml.safe_load((ROOT / 'examples/room_statistics_card.yaml').read_text())
        self.assertEqual(grid['cards'][0], standalone)
        self.assertEqual(grid['columns'], 1)
        self.assertFalse(grid['square'])
        self.assertEqual(grid['cards'][1], {
            'type': 'custom:mushroom-vacuum-card', 'entity': 'vacuum.sisyfos_ii',
            'fill_container': True, 'icon_animation': True,
        })
