"""IMAP fetcher for MyOpel: downloads .myop attachments from email.

Supports two modes:
  - IDLE (push): persistent connection, server notifies on new mail instantly.
  - Polling (fallback): periodic check every N seconds.

IDLE is used when available (most modern IMAP servers support RFC 2177).
Falls back to polling if IDLE is not supported or the connection drops.
"""
from __future__ import annotations

import asyncio
import email
import imaplib
import json
import logging
import os
import re
import socket
import tempfile
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
    IMAP_CONNECTION_TIMEOUT,
    MAX_IMAP_ATTACHMENT_BYTES,
)
from .snapshot import InvalidSnapshotError, normalize_vin, parse_snapshot

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


def _cleanup_stale_snapshots(save_path: Path, keep_name: str) -> int:
    """Remove every .myop file in `save_path` except the one named `keep_name`.

    MyOpel snapshots are cumulative, so holding on to older files would only
    feed the parser's safety-net merge with stale data and waste disk space.
    """
    removed = 0
    for old in save_path.iterdir():
        if not old.is_file() or old.suffix.lower() != ".myop":
            continue
        if old.name == keep_name:
            continue
        try:
            old.unlink()
            removed += 1
            _LOGGER.debug("MyOpel IMAP: rimosso snapshot obsoleto %s", old.name)
        except OSError as err:
            _LOGGER.debug("MyOpel IMAP: impossibile rimuovere %s (%s)", old.name, err)
    return removed


def _safe_attachment_name(filename: str) -> str:
    """Return a filesystem-safe name with a normalized lowercase suffix."""
    safe_name = re.sub(r"[^\w.\-]", "_", filename)
    return f"{safe_name[:-5]}.myop"


def _validate_attachment_payload(payload: bytes, expected_vin: str | None) -> str | None:
    """Validate an attachment before it can replace the last good snapshot."""
    if len(payload) > MAX_IMAP_ATTACHMENT_BYTES:
        _LOGGER.warning(
            "MyOpel IMAP: allegato ignorato perché supera %d byte",
            MAX_IMAP_ATTACHMENT_BYTES,
        )
        return None
    try:
        vin, _ = parse_snapshot(payload, require_trips=True)
    except (InvalidSnapshotError, json.JSONDecodeError, UnicodeDecodeError) as err:
        _LOGGER.warning("MyOpel IMAP: allegato .myop non valido, ignorato (%s)", err)
        return None

    normalized_expected = normalize_vin(expected_vin)
    if normalized_expected is not None and vin != normalized_expected:
        _LOGGER.warning(
            "MyOpel IMAP: allegato per VIN %s ignorato (atteso %s)",
            vin,
            normalized_expected,
        )
        return None
    return vin


def _atomic_write(dest: Path, payload: bytes) -> None:
    """Atomically replace ``dest`` with ``payload`` in the same directory."""
    fd, tmp_name = tempfile.mkstemp(
        dir=dest.parent,
        prefix=f".{dest.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(payload)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_name, dest)
    except Exception:
        try:
            Path(tmp_name).unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _fetch_myop_attachments(
    config: dict,
    save_folder: str,
    expected_vin: str | None = None,
) -> list[str]:
    """Connect to IMAP, save the single most recent .myop attachment.

    MyOpel emails carry cumulative snapshots — only the latest one matters.
    We iterate newest → oldest and keep the first email that actually has a
    .myop attachment; everything else is ignored. Older snapshots already on
    disk are deleted afterwards.
    """
    server       = config[CONF_IMAP_SERVER]
    port         = config.get(CONF_IMAP_PORT, DEFAULT_IMAP_PORT)
    username     = config[CONF_IMAP_USERNAME]
    password     = config[CONF_IMAP_PASSWORD]
    imap_folder  = config.get(CONF_IMAP_FOLDER, DEFAULT_IMAP_FOLDER)
    sender_filter = config.get(CONF_IMAP_SENDER, "").strip()

    save_path = Path(save_folder)
    save_path.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    kept_name: str | None = None

    conn: imaplib.IMAP4_SSL | None = None
    try:
        conn = imaplib.IMAP4_SSL(server, port, timeout=IMAP_CONNECTION_TIMEOUT)
        conn.login(username, password)
        status, _ = conn.select(imap_folder)
        if status != "OK":
            raise imaplib.IMAP4.error(f"Cannot select IMAP folder {imap_folder}")

        def _search(*criteria) -> list[bytes]:
            status, data = conn.search(None, *criteria)
            return data[0].split() if status == "OK" and data[0] else []

        # Search both unread and recent messages.  Looking at recent mail only
        # when UNSEEN is empty lets one unrelated unread message hide a newer,
        # already-read MyOpel export forever.
        unseen_ids = _search("UNSEEN", f'FROM "{sender_filter}"') if sender_filter \
                 else _search("UNSEEN")
        import datetime as _dt
        since = (_dt.date.today() - _dt.timedelta(days=7)).strftime("%d-%b-%Y")
        recent_ids = _search(f'SINCE {since}', f'FROM "{sender_filter}"') if sender_filter \
                 else _search(f'SINCE {since}')
        message_ids = list(set(unseen_ids) | set(recent_ids))

        # IMAP assigns sequence numbers in arrival order — highest == newest.
        message_ids_sorted = sorted(message_ids, key=lambda b: int(b), reverse=True)

        for msg_id in message_ids_sorted:
            status, msg_data = conn.fetch(msg_id, "(BODY.PEEK[])")
            if status != "OK":
                continue
            raw_message = next(
                (
                    item[1]
                    for item in msg_data
                    if isinstance(item, tuple)
                    and len(item) > 1
                    and isinstance(item[1], bytes)
                ),
                None,
            )
            if raw_message is None:
                continue
            msg = email.message_from_bytes(raw_message)
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
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                if _validate_attachment_payload(payload, expected_vin) is None:
                    continue
                safe_name = _safe_attachment_name(filename)
                dest = save_path / safe_name
                # Skip the write if the file on disk already matches the payload:
                # rewriting would bump mtime and wake the watchdog for nothing.
                if dest.is_file():
                    try:
                        if dest.read_bytes() == payload:
                            kept_name = safe_name
                            found = True
                            break
                    except OSError:
                        pass
                _atomic_write(dest, payload)
                kept_name = safe_name
                saved.append(str(dest))
                found = True
                _LOGGER.info("MyOpel IMAP: salvato → %s", dest)
                break  # one .myop per email is enough
            if found:
                conn.store(msg_id, "+FLAGS", "\\Seen")
                break  # newest snapshot handled — ignore anything older
    except imaplib.IMAP4.error as err:
        _LOGGER.error("MyOpel IMAP error: %s", err)
    except OSError as err:
        _LOGGER.error("MyOpel IMAP connessione fallita: %s", err)
    finally:
        if conn is not None:
            try:
                conn.logout()
            except (imaplib.IMAP4.error, OSError):
                pass

    if kept_name:
        _cleanup_stale_snapshots(save_path, kept_name)

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
        self._connection: imaplib.IMAP4_SSL | None = None
        self._connection_lock = threading.Lock()

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="myopel-imap-idle")
        self._thread.start()
        _LOGGER.debug("MyOpel IMAP IDLE worker avviato")

    def stop(self) -> None:
        self._stop.set()
        with self._connection_lock:
            connection = self._connection
        if connection is not None:
            try:
                # Interrupt the socket before touching imaplib's buffered file.
                # IMAP4.shutdown() closes that file first and can deadlock when
                # the worker thread is blocked in readline().
                connection.socket().shutdown(socket.SHUT_RDWR)
            except (AttributeError, OSError):
                pass
        if self._thread:
            self._thread.join(timeout=5)
        _LOGGER.debug("MyOpel IMAP IDLE worker fermato")

    def _set_connection(self, connection: imaplib.IMAP4_SSL | None) -> None:
        with self._connection_lock:
            self._connection = connection

    def _clear_connection(self, connection: imaplib.IMAP4_SSL) -> None:
        with self._connection_lock:
            if self._connection is connection:
                self._connection = None

    def _connect(self) -> imaplib.IMAP4_SSL:
        server  = self._config[CONF_IMAP_SERVER]
        port    = self._config.get(CONF_IMAP_PORT, DEFAULT_IMAP_PORT)
        user    = self._config[CONF_IMAP_USERNAME]
        pwd     = self._config[CONF_IMAP_PASSWORD]
        folder  = self._config.get(CONF_IMAP_FOLDER, DEFAULT_IMAP_FOLDER)
        conn = imaplib.IMAP4_SSL(server, port, timeout=IMAP_CONNECTION_TIMEOUT)
        self._set_connection(conn)
        try:
            if self._stop.is_set():
                raise OSError("IMAP worker stopped")
            conn.login(user, pwd)
            status, _ = conn.select(folder)
            if status != "OK":
                raise imaplib.IMAP4.error(f"Cannot select IMAP folder {folder}")
            return conn
        except Exception:
            self._clear_connection(conn)
            try:
                conn.shutdown()
            except (imaplib.IMAP4.error, OSError):
                pass
            raise

    def _run(self) -> None:
        """Main loop: connect → IDLE → on new mail → repeat."""
        while not self._stop.is_set():
            conn = None
            try:
                conn = self._connect()
                if self._stop.is_set():
                    break

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
                                break
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

                    if new_mail and not self._stop.is_set():
                        _LOGGER.info("MyOpel IMAP IDLE: nuova mail rilevata, avvio download")
                        self._on_new_mail()
                        # Reset socket to blocking after notifying
                    conn.socket().settimeout(None)

            except (imaplib.IMAP4.error, OSError) as err:
                if not self._stop.is_set():
                    _LOGGER.warning("MyOpel IMAP IDLE errore connessione: %s — riconnessione in 30s", err)
            finally:
                if conn is not None:
                    self._clear_connection(conn)
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
        self._fetch_lock = asyncio.Lock()
        self._stopping = False
        interval_s = imap_config.get(CONF_IMAP_INTERVAL, DEFAULT_IMAP_INTERVAL)
        self._interval = timedelta(seconds=interval_s)

    async def async_start(self) -> None:
        """Fetch immediately, start IDLE worker and periodic poll."""
        self._stopping = False
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
        if self._stopping:
            return
        self._hass.loop.call_soon_threadsafe(
            lambda: self._hass.async_create_task(self._async_fetch_and_refresh())
        )

    async def _async_poll(self, _now) -> None:
        await self._async_fetch_and_refresh()

    async def _async_fetch_and_refresh(self) -> None:
        async with self._fetch_lock:
            if self._stopping:
                return
            expected_vin = getattr(self._coordinator, "expected_vin", None)
            saved = await self._hass.async_add_executor_job(
                _fetch_myop_attachments,
                self._config,
                self._folder,
                expected_vin,
            )
            if saved and not self._stopping:
                _LOGGER.info("MyOpel IMAP: %d file scaricati, aggiorno sensori", len(saved))
                await self._coordinator.async_request_refresh()

    async def async_stop(self) -> None:
        """Stop polling and IDLE without blocking Home Assistant's event loop."""
        self._stopping = True
        if self._unsub_poll:
            self._unsub_poll()
            self._unsub_poll = None
        if self._idle_worker:
            worker = self._idle_worker
            self._idle_worker = None
            await self._hass.async_add_executor_job(worker.stop)
        # Wait asynchronously for an in-flight fetch to leave its critical
        # section. Queued callbacks see ``_stopping`` and return immediately.
        async with self._fetch_lock:
            pass
