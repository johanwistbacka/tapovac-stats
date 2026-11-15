"""TapoVac Stats setup."""
from __future__ import annotations

async def async_setup_entry(hass, entry):
    from homeassistant.const import Platform
    from .coordinator import TapoStatsCoordinator
    from .const import DOMAIN

    coordinator = TapoStatsCoordinator(hass, entry)
    await coordinator.async_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(coordinator.start())
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])
    return True

async def async_unload_entry(hass, entry):
    from homeassistant.const import Platform
    from .const import DOMAIN

    if await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR]):
        hass.data[DOMAIN].pop(entry.entry_id, None)
        return True
    return False
