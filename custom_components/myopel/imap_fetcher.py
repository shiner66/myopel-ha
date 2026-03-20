"""IMAP fetcher for MyOpel: downloads .myop attachments from email."""
from __future__ import annotations

import email
import imaplib
import logging
import re
from datetime import timedelta
from email.header import decode_header
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_IMAP_FOLDER,
    CONF_IMAP_INTERVAL,
    CONF_IMAP_PASSWORD,
    CONF_IMAP_PORT,
    CONF_IMAP_SENDER,
    CONF_IMAP_SERVER,
    CONF_IMAP_USERNAME,
    CONF_FILE_PATH,
    DEFAULT_IMAP_FOLDER,
    DEFAULT_IMAP_INTERVAL,
    DEFAULT_IMAP_PORT,
)

_LOGGER = logging.getLogger(__name__)


def _decode_header_value(raw: str) -> str:
    """Decode a potentially encoded email header value."""
    parts = decode_header(raw)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _fetch_myop_attachments(config: dict, save_folder: str) -> list[str]:
    """
    Connect to IMAP, find unread emails with .myop attachments, save them.
    Returns list of saved file paths.
    """
    server = config[CONF_IMAP_SERVER]
    port = config.get(CONF_IMAP_PORT, DEFAULT_IMAP_PORT)
    username = config[CONF_IMAP_USERNAME]
    password = config[CONF_IMAP_PASSWORD]
    imap_folder = config.get(CONF_IMAP_FOLDER, DEFAULT_IMAP_FOLDER)
    sender_filter = config.get(CONF_IMAP_SENDER, "").strip()

    save_path = Path(save_folder)
    save_path.mkdir(parents=True, exist_ok=True)

    saved: list[str] = []

    try:
        conn = imaplib.IMAP4_SSL(server, port)
        conn.login(username, password)
        conn.select(imap_folder)

        def _search(*criteria) -> list[bytes]:
            status, data = conn.search(None, *criteria)
            return data[0].split() if status == "OK" and data[0] else []

        # 1. Try unread messages first
        if sender_filter:
            message_ids = _search("UNSEEN", f'FROM "{sender_filter}"')
        else:
            message_ids = _search("UNSEEN")

        # 2. If nothing unread, widen to last 7 days (catches already-read emails)
        if not message_ids:
            import datetime as _dt
            since = (_dt.date.today() - _dt.timedelta(days=7)).strftime("%d-%b-%Y")
            if sender_filter:
                message_ids = _search(f'SINCE {since}', f'FROM "{sender_filter}"')
            else:
                message_ids = _search(f'SINCE {since}')
            _LOGGER.debug("MyOpel IMAP: nessuna UNSEEN, cerco ultimi 7 giorni (%d msg)", len(message_ids))

        _LOGGER.debug("MyOpel IMAP: %d messaggio/i da esaminare", len(message_ids))

        for msg_id in message_ids:
            status, msg_data = conn.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            found_attachment = False

            for part in msg.walk():
                content_disposition = part.get("Content-Disposition", "")
                if "attachment" not in content_disposition:
                    continue

                filename_raw = part.get_filename()
                if not filename_raw:
                    continue

                filename = _decode_header_value(filename_raw)
                if not filename.lower().endswith(".myop"):
                    continue

                # Sanitize filename
                safe_name = re.sub(r'[^\w.\-]', '_', filename)
                dest = save_path / safe_name

                payload = part.get_payload(decode=True)
                if payload:
                    # Skip if an identical filename already exists in the folder
                    if dest.exists():
                        _LOGGER.debug("MyOpel IMAP: %s già presente, salto", safe_name)
                        continue
                    dest.write_bytes(payload)
                    saved.append(str(dest))
                    found_attachment = True
                    _LOGGER.info("MyOpel IMAP: saved attachment → %s", dest)

            if found_attachment:
                # Mark as read only if we actually saved something
                conn.store(msg_id, "+FLAGS", "\\Seen")

        conn.logout()

    except imaplib.IMAP4.error as err:
        _LOGGER.error("MyOpel IMAP error: %s", err)
    except OSError as err:
        _LOGGER.error("MyOpel IMAP connection error: %s", err)

    return saved


class MyOpelImapFetcher:
    """Periodic IMAP poller that downloads new .myop files and triggers coordinator refresh."""

    def __init__(
        self,
        hass: HomeAssistant,
        imap_config: dict,
        save_folder: str,
        coordinator,
    ) -> None:
        self._hass = hass
        self._imap_config = imap_config
        self._save_folder = save_folder
        self._coordinator = coordinator
        self._unsub = None
        interval_s = imap_config.get(CONF_IMAP_INTERVAL, DEFAULT_IMAP_INTERVAL)
        self._interval = timedelta(seconds=interval_s)

    async def async_start(self) -> None:
        """Start periodic IMAP polling."""
        # Run once immediately
        await self._async_poll(None)
        self._unsub = async_track_time_interval(
            self._hass, self._async_poll, self._interval
        )
        _LOGGER.debug("MyOpel IMAP fetcher started (interval=%s)", self._interval)

    async def _async_poll(self, _now) -> None:
        """Run IMAP fetch in executor, then refresh coordinator if new files found."""
        saved = await self._hass.async_add_executor_job(
            _fetch_myop_attachments, self._imap_config, self._save_folder
        )
        if saved:
            _LOGGER.info("MyOpel IMAP: %d new file(s) downloaded, refreshing data", len(saved))
            await self._coordinator.async_request_refresh()

    def async_stop(self) -> None:
        """Stop the periodic polling."""
        if self._unsub:
            self._unsub()
            self._unsub = None
