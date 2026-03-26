"""Config flow for MyOpel integration."""
from __future__ import annotations

import imaplib
import json
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_FILE_PATH,
    CONF_IMAP_DISABLED,
    CONF_IMAP_FOLDER,
    CONF_IMAP_INTERVAL,
    CONF_IMAP_PASSWORD,
    CONF_IMAP_PORT,
    CONF_IMAP_SENDER,
    CONF_IMAP_SERVER,
    CONF_IMAP_USERNAME,
    CONF_MIN_TRIP_DISTANCE,
    CONF_MIN_TRIP_DISTANCE_ENABLED,
    CONF_SCAN_INTERVAL,
    DEFAULT_IMAP_FOLDER,
    DEFAULT_IMAP_INTERVAL,
    DEFAULT_IMAP_PORT,
    DEFAULT_MIN_TRIP_DISTANCE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

DEFAULT_FOLDER = "/config/myopel/"


# ── Validators ────────────────────────────────────────────────────────────────

def _validate_trip_folder(path: str) -> dict | None:
    """
    Validate the folder path.
    Accepts both .myop (legacy) and trips.json (native app format).
    Returns parsed data from the newest file, or None if folder is empty
    (acceptable when IMAP / manual copy will populate it later).
    Raises on invalid path or bad JSON.
    """
    p = Path(path)
    if not p.exists():
        p.mkdir(parents=True, exist_ok=True)

    if not p.is_dir():
        raise NotADirectoryError

    candidates = list(p.glob("*.myop")) + list(p.glob("trips.json")) + (
        [p / "trips"] if (p / "trips").is_file() else []
    ) + (
        [p / "trips.export"] if (p / "trips.export").is_file() else []
    )
    if not candidates:
        return None  # empty folder — ok if IMAP configured or file copied later

    candidates.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    try:
        data = json.loads(candidates[0].read_text(encoding="utf-8"))
        if not isinstance(data, list) or not data or "vin" not in data[0]:
            raise ValueError("invalid_format")
        return data
    except json.JSONDecodeError as err:
        raise ValueError("invalid_json") from err


def _validate_imap(server: str, port: int, username: str, password: str, folder: str) -> None:
    """Try to connect and login to verify credentials. Raises on failure."""
    conn = imaplib.IMAP4_SSL(server, port)
    try:
        conn.login(username, password)
        status, _ = conn.select(folder)
        if status != "OK":
            raise ValueError("imap_folder_not_found")
    finally:
        try:
            conn.logout()
        except Exception:
            pass


# ── Config Flow ───────────────────────────────────────────────────────────────

class MyOpelConfigFlow(ConfigFlow, domain=DOMAIN):
    """Two-step config flow: (1) folder path, (2) optional IMAP."""

    VERSION = 1

    def __init__(self) -> None:
        self._folder_path: str = ""
        self._vin: str = ""

    # Step 1 — folder
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            path = user_input[CONF_FILE_PATH].strip()
            try:
                data = await self.hass.async_add_executor_job(
                    _validate_trip_folder, path
                )
            except NotADirectoryError:
                errors[CONF_FILE_PATH] = "not_a_directory"
            except ValueError as err:
                errors[CONF_FILE_PATH] = str(err) if str(err) in (
                    "invalid_format", "invalid_json"
                ) else "invalid_format"
            else:
                self._folder_path = path
                self._vin = data[0].get("vin", "unknown") if data else "unknown"
                if data:
                    await self.async_set_unique_id(self._vin)
                    self._abort_if_unique_id_configured()
                return await self.async_step_imap()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_FILE_PATH, default=DEFAULT_FOLDER): str,
            }),
            errors=errors,
            description_placeholders={"example": DEFAULT_FOLDER},
        )

    # Step 2 — IMAP (optional)
    async def async_step_imap(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            if not user_input.get(CONF_IMAP_SERVER, "").strip():
                return self._create_entry({})

            try:
                await self.hass.async_add_executor_job(
                    _validate_imap,
                    user_input[CONF_IMAP_SERVER].strip(),
                    user_input.get(CONF_IMAP_PORT, DEFAULT_IMAP_PORT),
                    user_input[CONF_IMAP_USERNAME].strip(),
                    user_input[CONF_IMAP_PASSWORD],
                    user_input.get(CONF_IMAP_FOLDER, DEFAULT_IMAP_FOLDER).strip(),
                )
            except imaplib.IMAP4.error:
                errors["base"] = "imap_auth_failed"
            except OSError:
                errors[CONF_IMAP_SERVER] = "imap_cannot_connect"
            except ValueError as err:
                errors[CONF_IMAP_FOLDER] = str(err)
            else:
                return self._create_entry(user_input)

        return self.async_show_form(
            step_id="imap",
            data_schema=vol.Schema({
                vol.Optional(CONF_IMAP_SERVER, default=""): str,
                vol.Optional(CONF_IMAP_PORT, default=DEFAULT_IMAP_PORT): int,
                vol.Optional(CONF_IMAP_USERNAME, default=""): str,
                vol.Optional(CONF_IMAP_PASSWORD, default=""): str,
                vol.Optional(CONF_IMAP_FOLDER, default=DEFAULT_IMAP_FOLDER): str,
                vol.Optional(CONF_IMAP_SENDER, default=""): str,
                vol.Optional(CONF_IMAP_INTERVAL, default=DEFAULT_IMAP_INTERVAL): vol.All(
                    int, vol.Range(min=60, max=86400)
                ),
            }),
            errors=errors,
        )

    def _create_entry(self, imap_data: dict) -> FlowResult:
        entry_data: dict[str, Any] = {CONF_FILE_PATH: self._folder_path}
        if imap_data.get(CONF_IMAP_SERVER, "").strip():
            entry_data.update({
                CONF_IMAP_SERVER: imap_data[CONF_IMAP_SERVER].strip(),
                CONF_IMAP_PORT: imap_data.get(CONF_IMAP_PORT, DEFAULT_IMAP_PORT),
                CONF_IMAP_USERNAME: imap_data[CONF_IMAP_USERNAME].strip(),
                CONF_IMAP_PASSWORD: imap_data[CONF_IMAP_PASSWORD],
                CONF_IMAP_FOLDER: imap_data.get(CONF_IMAP_FOLDER, DEFAULT_IMAP_FOLDER).strip(),
                CONF_IMAP_SENDER: imap_data.get(CONF_IMAP_SENDER, "").strip(),
                CONF_IMAP_INTERVAL: imap_data.get(CONF_IMAP_INTERVAL, DEFAULT_IMAP_INTERVAL),
            })
        vin_short = self._vin[-6:] if self._vin != "unknown" else "???"
        return self.async_create_entry(
            title=f"Opel ({vin_short})",
            data=entry_data,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return MyOpelOptionsFlow()


# ── Options Flow ──────────────────────────────────────────────────────────────

class MyOpelOptionsFlow(OptionsFlow):
    """Options: folder path, polling interval, IMAP settings."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        d = self.config_entry.data
        o = self.config_entry.options

        if user_input is not None:
            # Validate new folder path if changed
            new_path = user_input.get(CONF_FILE_PATH, "").strip()
            if new_path:
                try:
                    await self.hass.async_add_executor_job(
                        _validate_trip_folder, new_path
                    )
                except NotADirectoryError:
                    errors[CONF_FILE_PATH] = "not_a_directory"
                except ValueError as err:
                    errors[CONF_FILE_PATH] = str(err) if str(err) in (
                        "invalid_format", "invalid_json"
                    ) else "invalid_format"

            imap_disabled = user_input.get(CONF_IMAP_DISABLED, False)
            imap_server = user_input.get(CONF_IMAP_SERVER, "").strip()
            if not imap_disabled and imap_server:
                try:
                    await self.hass.async_add_executor_job(
                        _validate_imap,
                        imap_server,
                        user_input.get(CONF_IMAP_PORT, DEFAULT_IMAP_PORT),
                        user_input.get(CONF_IMAP_USERNAME, "").strip(),
                        user_input.get(CONF_IMAP_PASSWORD, ""),
                        user_input.get(CONF_IMAP_FOLDER, DEFAULT_IMAP_FOLDER).strip(),
                    )
                except imaplib.IMAP4.error:
                    errors["base"] = "imap_auth_failed"
                except OSError:
                    errors[CONF_IMAP_SERVER] = "imap_cannot_connect"
                except ValueError as err:
                    errors[CONF_IMAP_FOLDER] = str(err)

            if not errors:
                return self.async_create_entry(title="", data=user_input)

        current_path = o.get(CONF_FILE_PATH, d.get(CONF_FILE_PATH, DEFAULT_FOLDER))

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_FILE_PATH,
                    default=current_path,
                ): str,
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=o.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(int, vol.Range(min=30, max=86400)),
                vol.Optional(
                    CONF_MIN_TRIP_DISTANCE_ENABLED,
                    default=o.get(CONF_MIN_TRIP_DISTANCE_ENABLED, False),
                ): bool,
                vol.Optional(
                    CONF_MIN_TRIP_DISTANCE,
                    default=o.get(CONF_MIN_TRIP_DISTANCE, DEFAULT_MIN_TRIP_DISTANCE),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=50.0)),
                vol.Optional(
                    CONF_IMAP_DISABLED,
                    default=o.get(CONF_IMAP_DISABLED, False),
                ): bool,
                vol.Optional(
                    CONF_IMAP_SERVER,
                    default=o.get(CONF_IMAP_SERVER, d.get(CONF_IMAP_SERVER, "")),
                ): str,
                vol.Optional(
                    CONF_IMAP_PORT,
                    default=o.get(CONF_IMAP_PORT, d.get(CONF_IMAP_PORT, DEFAULT_IMAP_PORT)),
                ): int,
                vol.Optional(
                    CONF_IMAP_USERNAME,
                    default=o.get(CONF_IMAP_USERNAME, d.get(CONF_IMAP_USERNAME, "")),
                ): str,
                vol.Optional(
                    CONF_IMAP_PASSWORD,
                    default=o.get(CONF_IMAP_PASSWORD, d.get(CONF_IMAP_PASSWORD, "")),
                ): str,
                vol.Optional(
                    CONF_IMAP_FOLDER,
                    default=o.get(CONF_IMAP_FOLDER, d.get(CONF_IMAP_FOLDER, DEFAULT_IMAP_FOLDER)),
                ): str,
                vol.Optional(
                    CONF_IMAP_SENDER,
                    default=o.get(CONF_IMAP_SENDER, d.get(CONF_IMAP_SENDER, "")),
                ): str,
                vol.Optional(
                    CONF_IMAP_INTERVAL,
                    default=o.get(CONF_IMAP_INTERVAL, d.get(CONF_IMAP_INTERVAL, DEFAULT_IMAP_INTERVAL)),
                ): vol.All(int, vol.Range(min=60, max=86400)),
            }),
            errors=errors,
        )
