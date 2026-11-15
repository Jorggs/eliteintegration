"""Config flow for the Elite Dangerous Telemetry integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries

from .const import CONF_ROOT_TOPIC, DEFAULT_ROOT_TOPIC, DOMAIN


class EliteDangerousConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            root_topic = user_input[CONF_ROOT_TOPIC].strip().rstrip("/")
            if not root_topic:
                errors["base"] = "invalid_topic"
            else:
                await self.async_set_unique_id(f"elite_dangerous_{root_topic}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Elite Dangerous ({root_topic})",
                    data={CONF_ROOT_TOPIC: root_topic},
                )

        schema = vol.Schema(
            {vol.Required(CONF_ROOT_TOPIC, default=DEFAULT_ROOT_TOPIC): str}
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
