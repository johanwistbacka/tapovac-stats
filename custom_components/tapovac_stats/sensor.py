"""Room sensors and a compact table data source."""
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

METRICS = {"last_cleaned": "Senast städat", "today": "Städningar idag",
           "last_seven_days": "Städningar senaste 7 dagarna"}

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    known = set()

    @callback
    def add_rooms():
        new = set(coordinator.data or {}) - known
        if not new:
            return
        known.update(new)
        async_add_entities([RoomSensor(coordinator, entry, key, metric)
                            for key in sorted(new) for metric in METRICS])

    async_add_entities([SummarySensor(coordinator, entry)])
    entry.async_on_unload(coordinator.async_add_listener(add_rooms))
    add_rooms()

class StatsEntity(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self):
        return {"identifiers": {(DOMAIN, self._entry.entry_id)},
                "name": self._entry.title, "manufacturer": "TapoVac Stats"}

class RoomSensor(StatsEntity):
    def __init__(self, coordinator, entry, key, metric):
        super().__init__(coordinator, entry)
        self._key, self._metric = key, metric
        row = coordinator.data[key]
        self._room_name = row.room.name
        self._attr_unique_id = f"{coordinator.source_entry_id}_{key[0]}_{key[1]}_{metric}"
        self._attr_icon = "mdi:history" if metric == "last_cleaned" else "mdi:counter"
        if metric == "last_cleaned":
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        else:
            self._attr_native_unit_of_measurement = "städningar"

    @property
    def name(self):
        row = (self.coordinator.data or {}).get(self._key)
        if row:
            self._room_name = row.room.name
        return f"{self._room_name} {METRICS[self._metric]}"

    @property
    def available(self):
        return super().available and self._key in (self.coordinator.data or {})

    @property
    def native_value(self):
        row = (self.coordinator.data or {}).get(self._key)
        return getattr(row, self._metric) if row else None

    @property
    def extra_state_attributes(self):
        row = (self.coordinator.data or {}).get(self._key)
        return {"source_entry_id": self.coordinator.source_entry_id,
                "map_id": self._key[0], "room_id": self._key[1],
                "metric": self._metric, "coverage": row.room.coverage if row else None}

class SummarySensor(StatsEntity):
    _attr_name = "Rumsöversikt"
    _attr_icon = "mdi:table"
    _unrecorded_attributes = frozenset({"rooms"})

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{coordinator.source_entry_id}_room_summary"

    @property
    def native_value(self):
        return len(self.coordinator.data or {})

    @property
    def extra_state_attributes(self):
        return {"source_entry_id": self.coordinator.source_entry_id,
                "rooms": [{"name": row.room.name, "map_id": row.room.map_id,
                           "room_id": row.room.room_id,
                           "last_cleaned": row.last_cleaned.isoformat() if row.last_cleaned else None,
                           "today": row.today, "last_seven_days": row.last_seven_days}
                          for row in (self.coordinator.data or {}).values()]}
