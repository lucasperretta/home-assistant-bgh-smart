from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pybgh
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult


class BGHSmartConfigFlow(config_entries.ConfigFlow, domain="bgh_smart"):
    """Handle a config flow for BGH Smart."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Check if already configured
            await self.async_set_unique_id(user_input[CONF_USERNAME])
            self._abort_if_unique_id_configured()

            loop = asyncio.get_running_loop()

            def create_client():
                return pybgh.BghClient(
                    user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )

            # Run in a separate thread to avoid blocking the event loop
            with ThreadPoolExecutor() as pool:
                client = await loop.run_in_executor(pool, create_client)

            if client.token:
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME],
                    data=user_input,
                )

            errors["base"] = "auth"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )
