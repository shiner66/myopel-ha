"""IMAP fetcher for MyOpel: downloads .myop attachments from email.

Supports two modes:
  - IDLE (push): persistent connection, server notifies on new mail instantly.
  - Polling (fallback): periodic check every N seconds.

IDLE is used when available (most modern IMAP servers support RFC 2177).
Falls back to polling if IDLE is not supported or the connection drops.
"""
from __future__ import annotations

import email
import imaplib
import logging
import re
import socket
import threading
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

# Max IDLE duration before re-issuing (RFC recommends < 29 min)
_IDLE_TIMEOUT_S = 25 * 60


def _decode_header_value(raw: str) -> str:
    parts = decode_header(raw)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _fetch_myop_attachments(config: dict, save_folder: str) -> list[str]:
    """Connect to IMAP, find unread + recent emails with .myop attachments, save them."""
    server       = config[CONF_IMAP_SERVER]
    port         = config.get(CONF_IMAP_PORT, DEFAULT_IMAP_PORT)
    username     = config[CONF_IMAP_USERNAME]
    password     = config[CONF_IMAP_PASSWORD]
    imap_folder  = config.get(CONF_IMAP_FOLDER, DEFAULT_IMAP_FOLDER)
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

        # 1. Unread first
        message_ids = _search("UNSEEN", f'FROM "{sender_filter}"') if sender_filter \
                 else _search("UNSEEN")

        # 2. Fallback: last 7 days (catches already-read emails)
        if not message_ids:
            import datetime as _dt
            since = (_dt.date.today() - _dt.timedelta(days=7)).strftime("%d-%b-%Y")
            message_ids = _search(f'SINCE {since}', f'FROM "{sender_filter}"') if sender_filter \
                     else _search(f'SINCE {since}')
            if message_ids:
                _LOGGER.debug("MyOpel IMAP: nessuna UNSEEN, trovati %d msg negli ultimi 7gg",
                              len(message_ids))

        for msg_id in message_ids:
            status, msg_data = conn.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            found = False
            for part in msg.walk():
                if "attachment" not in part.get("Content-Disposition", ""):
                    continue
                filename_raw = part.get_filename()
                if not filename_raw:
                    continue
                filename = _decode_header_value(filename_raw)
                if not filename.lower().endswith(".myop"):
                    continue
                safe_name = re.sub(r'[^\w.\-]', '_', filename)
                dest = save_path / safe_name
                payload = part.get_payload(decode=True)
                if payload:
                    dest.write_bytes(payload)
                    saved.append(str(dest))
                    found = True
                    _LOGGER.info("MyOpel IMAP: salvato → %s", dest)
            if found:
                conn.store(msg_id, "+FLAGS", "\\Seen")

        conn.logout()
    except imaplib.IMAP4.error as err:
        _LOGGER.error("MyOpel IMAP error: %s", err)
    except OSError as err:
        _LOGGER.error("MyOpel IMAP connessione fallita: %s", err)

    return saved


# ── IDLE worker (runs in a background thread) ─────────────────────────────────

class _IdleWorker:
    """
    Maintains a persistent IMAP connection in IDLE mode.
    Calls `on_new_mail` (a thread-safe callable) when the server signals new mail.
    Reconnects automatically on errors.
    """

    def __init__(self, config: dict, on_new_mail, on_no_idle=None) -> None:
        self._config      = config
        self._on_new_mail = on_new_mail
        self._on_no_idle  = on_no_idle
        self._stop        = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="myopel-imap-idle")
        self._thread.start()
        _LOGGER.debug("MyOpel IMAP IDLE worker avviato")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        _LOGGER.debug("MyOpel IMAP IDLE worker fermato")

    def _connect(self) -> imaplib.IMAP4_SSL:
        server  = self._config[CONF_IMAP_SERVER]
        port    = self._config.get(CONF_IMAP_PORT, DEFAULT_IMAP_PORT)
        user    = self._config[CONF_IMAP_USERNAME]
        pwd     = self._config[CONF_IMAP_PASSWORD]
        folder  = self._config.get(CONF_IMAP_FOLDER, DEFAULT_IMAP_FOLDER)
        conn = imaplib.IMAP4_SSL(server, port)
        conn.login(user, pwd)
        conn.select(folder)
        return conn

    def _run(self) -> None:
        """Main loop: connect → IDLE → on new mail → repeat."""
        while not self._stop.is_set():
            conn = None
            try:
                conn = self._connect()

                # Check IDLE capability
                _, caps = conn.capability()
                cap_str = (caps[0] if caps else b"").decode(errors="ignore").upper()
                if "IDLE" not in cap_str:
                    _LOGGER.info("MyOpel IMAP: server non supporta IDLE, uso polling")
                    conn.logout()
                    if self._on_no_idle:
                        self._on_no_idle()
                    self._stop.set()
                    return

                _LOGGER.debug("MyOpel IMAP IDLE: connesso, in attesa di nuova mail…")

                while not self._stop.is_set():
                    # Issue IDLE
                    conn.send(b"A001 IDLE\r\n")
                    # Read the "+ idling" continuation
                    conn.readline()

                    # Set socket timeout = IDLE_TIMEOUT so we re-IDLE periodically
                    conn.socket().settimeout(_IDLE_TIMEOUT_S)

                    new_mail = False
                    try:
                        while True:
                            line = conn.readline().strip()
                            if not line:
                                break
                            _LOGGER.debug("MyOpel IDLE line: %s", line)
                            # EXISTS = new message(s) arrived
                            if b"EXISTS" in line or b"RECENT" in line:
                                new_mail = True
                            # Server sent BYE or we hit timeout → break inner loop
                            if line.startswith(b"*") is False and b"IDLE" in line:
                                break
                    except socket.timeout:
                        # Normal: IDLE_TIMEOUT reached, send DONE and re-IDLE
                        pass
                    except (OSError, imaplib.IMAP4.error) as err:
                        _LOGGER.warning("MyOpel IDLE read error: %s", err)
                        break

                    # Send DONE to end IDLE
                    try:
                        conn.send(b"DONE\r\n")
                        conn.readline()  # consume server response to DONE
                    except (OSError, imaplib.IMAP4.error):
                        break

                    if new_mail:
                        _LOGGER.info("MyOpel IMAP IDLE: nuova mail rilevata, avvio download")
                        self._on_new_mail()
                        # Reset socket to blocking after notifying
                    conn.socket().settimeout(None)

            except (imaplib.IMAP4.error, OSError) as err:
                _LOGGER.warning("MyOpel IMAP IDLE errore connessione: %s — riconnessione in 30s", err)
            finally:
                try:
                    conn and conn.logout()
                except Exception:
                    pass

            if not self._stop.is_set():
                # Wait before reconnect, but honour stop signal
                self._stop.wait(timeout=30)


# ── Public class ──────────────────────────────────────────────────────────────

class MyOpelImapFetcher:
    """
    Manages IMAP for MyOpel.

    Strategy:
      1. Attempt IDLE (push). If server supports it, new mail triggers an immediate fetch.
      2. Always keep a periodic polling fallback (default 5 min) to catch edge cases
         (IDLE disconnect, server quirks, already-read emails in 7-day window).
    """

    def __init__(
        self,
        hass: HomeAssistant,
        imap_config: dict,
        save_folder: str,
        coordinator,
        on_no_idle=None,
    ) -> None:
        self._hass        = hass
        self._config      = imap_config
        self._folder      = save_folder
        self._coordinator = coordinator
        self._on_no_idle  = on_no_idle
        self._unsub_poll  = None
        self._idle_worker: _IdleWorker | None = None
        interval_s = imap_config.get(CONF_IMAP_INTERVAL, DEFAULT_IMAP_INTERVAL)
        self._interval = timedelta(seconds=interval_s)

    async def async_start(self) -> None:
        """Fetch immediately, start IDLE worker and periodic poll."""
        # Immediate fetch on startup
        await self._async_fetch_and_refresh()

        # Start IDLE push worker in background thread
        self._idle_worker = _IdleWorker(
            config=self._config,
            on_new_mail=self._on_idle_new_mail,
            on_no_idle=self._on_idle_not_supported,
        )
        self._idle_worker.start()

        # Periodic polling as safety net
        self._unsub_poll = async_track_time_interval(
            self._hass, self._async_poll, self._interval
        )
        _LOGGER.debug("MyOpel IMAP: IDLE + polling ogni %s avviati", self._interval)

    def _on_idle_not_supported(self) -> None:
        """Called from IDLE thread when server lacks RFC 2177 support."""
        if self._on_no_idle:
            self._hass.loop.call_soon_threadsafe(self._on_no_idle)

    def _on_idle_new_mail(self) -> None:
        """Called from IDLE thread when new mail arrives — schedule fetch on event loop."""
        self._hass.loop.call_soon_threadsafe(
            lambda: self._hass.async_create_task(self._async_fetch_and_refresh())
        )

    async def _async_poll(self, _now) -> None:
        await self._async_fetch_and_refresh()

    async def _async_fetch_and_refresh(self) -> None:
        saved = await self._hass.async_add_executor_job(
            _fetch_myop_attachments, self._config, self._folder
        )
        if saved:
            _LOGGER.info("MyOpel IMAP: %d file scaricati, aggiorno sensori", len(saved))
            await self._coordinator.async_request_refresh()

    def async_stop(self) -> None:
        if self._unsub_poll:
            self._unsub_poll()
            self._unsub_poll = None
        if self._idle_worker:
            self._idle_worker.stop()
            self._idle_worker = None
