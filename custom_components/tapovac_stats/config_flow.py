"""Select an existing TapoVac-ADV installation."""
from homeassistant import config_entries
import voluptuous as vol
from .const import CONF_SOURCE, DOMAIN, SOURCE_DOMAIN

class TapoStatsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        sources = {entry.entry_id: entry.title for entry in
                   self.hass.config_entries.async_entries(SOURCE_DOMAIN)}
        if not sources:
            return self.async_abort(reason="no_source")
        errors = {}
        if user_input is not None:
            source_id = user_input[CONF_SOURCE]
            if source_id not in sources:
                errors["base"] = "source_missing"
            else:
                await self.async_set_unique_id(source_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"TapoVac Stats – {sources[source_id]}",
                                               data={CONF_SOURCE: source_id})
        return self.async_show_form(step_id="user", errors=errors,
                                    data_schema=vol.Schema({vol.Required(CONF_SOURCE): vol.In(sources)}))
