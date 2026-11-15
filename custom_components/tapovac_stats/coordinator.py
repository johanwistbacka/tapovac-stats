"""Read source changes and recalculate time-dependent statistics."""
from datetime import timedelta
import logging
from zoneinfo import ZoneInfo

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_SOURCE, SOURCE_DOMAIN
from .statistics import calculate, newest_first
from .upstream import UpstreamUnavailable, read_rooms

_LOGGER = logging.getLogger(__name__)

class TapoStatsCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(hass, _LOGGER, name=entry.title)
        self.source_entry_id = entry.data[CONF_SOURCE]
        self._source = None
        self._remove_source_listener = None

    @callback
    def start(self):
        remove_timer = async_track_time_interval(self.hass, self._tick, timedelta(minutes=1))
        self._bind_source()

        @callback
        def stop():
            remove_timer()
            if self._remove_source_listener:
                self._remove_source_listener()
                self._remove_source_listener = None
            self._source = None
        return stop

    @callback
    def _bind_source(self):
        source = self.hass.data.get(SOURCE_DOMAIN, {}).get(self.source_entry_id)
        if source is self._source:
            return source
        if self._remove_source_listener:
            self._remove_source_listener()
            self._remove_source_listener = None
        self._source = source
        if source is not None and hasattr(source, "async_add_listener"):
            self._remove_source_listener = source.async_add_listener(self._source_changed)
        return source

    @callback
    def _source_changed(self):
        self.hass.async_create_task(self.async_refresh())

    async def _tick(self, now):
        await self.async_refresh()

    async def _async_update_data(self):
        source = self._bind_source()
        if source is None:
            raise UpdateFailed("TapoVac-ADV source is not loaded")
        try:
            rooms = read_rooms(source, self.source_entry_id)
            now = dt_util.utcnow()
            zone = ZoneInfo(self.hass.config.time_zone)
            rows = newest_first([calculate(room, now, zone) for room in rooms])
        except (UpstreamUnavailable, ValueError, OverflowError) as exc:
            raise UpdateFailed(str(exc)) from exc
        return {(row.room.map_id, row.room.room_id): row for row in rows}
