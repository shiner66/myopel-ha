"""Tests for the MyOpel IMAP fetcher."""
from __future__ import annotations

import json
import socket
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import MagicMock

from custom_components.myopel import imap_fetcher
from custom_components.myopel.const import (
    CONF_IMAP_PASSWORD,
    CONF_IMAP_SERVER,
    CONF_IMAP_USERNAME,
)


class TestCleanupStaleSnapshots:
    def test_removes_other_myop_files(self, tmp_path: Path):
        keep = tmp_path / "current.myop"
        old_a = tmp_path / "old-a.myop"
        old_b = tmp_path / "old-b.myop"
        for path in (keep, old_a, old_b):
            path.write_bytes(b"snapshot")

        removed = imap_fetcher._cleanup_stale_snapshots(tmp_path, keep.name)

        assert removed == 2
        assert keep.exists()
        assert not old_a.exists()
        assert not old_b.exists()

    def test_does_not_touch_non_myop_files(self, tmp_path: Path):
        keep = tmp_path / "current.myop"
        unrelated = tmp_path / "trips.json"
        export = tmp_path / "trips.export"
        for path in (keep, unrelated, export):
            path.write_bytes(b"data")

        imap_fetcher._cleanup_stale_snapshots(tmp_path, keep.name)

        assert keep.exists()
        assert unrelated.exists()
        assert export.exists()

    def test_case_insensitive_cleanup(self, tmp_path: Path):
        keep = tmp_path / "current.myop"
        old = tmp_path / "OLD.MYOP"
        keep.write_bytes(b"current")
        old.write_bytes(b"old")

        assert imap_fetcher._cleanup_stale_snapshots(tmp_path, keep.name) == 1
        assert not old.exists()


def _message(payload: bytes, filename: str = "export.myop") -> bytes:
    message = EmailMessage()
    message["From"] = "sender@example.com"
    message["To"] = "owner@example.com"
    message.set_content("MyOpel export")
    message.add_attachment(
        payload,
        maintype="application",
        subtype="octet-stream",
        filename=filename,
    )
    return message.as_bytes()


def _valid_payload(vin: str = "VIN123") -> bytes:
    return json.dumps(
        [{"vin": vin, "trips": [{"id": 1, "end": {"date": "2026-01-01T10:00:00Z"}}]}]
    ).encode()


def _fake_imap(messages: dict[bytes, bytes], unseen: list[bytes], recent: list[bytes]):
    class FakeImap:
        instance = None

        def __init__(self, _server, _port, *, timeout=None):
            type(self).instance = self
            self.timeout = timeout
            self.fetch_calls = []
            self.store_calls = []

        def login(self, _username, _password):
            return "OK", []

        def select(self, _folder):
            return "OK", []

        def search(self, _charset, *criteria):
            ids = unseen if criteria and criteria[0] == "UNSEEN" else recent
            return "OK", [b" ".join(ids)]

        def fetch(self, message_id, query):
            self.fetch_calls.append((message_id, query))
            return "OK", [(b"message", messages[message_id])]

        def store(self, message_id, operation, flag):
            self.store_calls.append((message_id, operation, flag))
            return "OK", []

        def logout(self):
            return "BYE", []

    return FakeImap


def _config() -> dict:
    return {
        CONF_IMAP_SERVER: "imap.example.com",
        CONF_IMAP_USERNAME: "owner@example.com",
        CONF_IMAP_PASSWORD: "secret",
    }


def test_fetch_unions_searches_peeks_and_normalizes_suffix(tmp_path: Path, monkeypatch):
    fake = _fake_imap(
        {
            b"1": _message(_valid_payload(), "old.myop"),
            b"2": _message(_valid_payload(), "EXPORT.MYOP"),
        },
        unseen=[b"1"],
        recent=[b"2"],
    )
    monkeypatch.setattr(imap_fetcher.imaplib, "IMAP4_SSL", fake)

    saved = imap_fetcher._fetch_myop_attachments(_config(), str(tmp_path), "VIN123")

    assert saved == [str(tmp_path / "EXPORT.myop")]
    assert (tmp_path / "EXPORT.myop").is_file()
    assert fake.instance.fetch_calls == [(b"2", "(BODY.PEEK[])")]
    assert fake.instance.store_calls == [(b"2", "+FLAGS", "\\Seen")]
    assert fake.instance.timeout == imap_fetcher.IMAP_CONNECTION_TIMEOUT


def test_invalid_attachment_keeps_last_good_snapshot(tmp_path: Path, monkeypatch):
    old = tmp_path / "last-good.myop"
    old.write_bytes(_valid_payload())
    fake = _fake_imap(
        {b"1": _message(b"not json", "new.myop")},
        unseen=[b"1"],
        recent=[],
    )
    monkeypatch.setattr(imap_fetcher.imaplib, "IMAP4_SSL", fake)

    saved = imap_fetcher._fetch_myop_attachments(_config(), str(tmp_path), "VIN123")

    assert saved == []
    assert old.read_bytes() == _valid_payload()
    assert fake.instance.store_calls == []


def test_idle_worker_stop_interrupts_socket_before_join():
    worker = imap_fetcher._IdleWorker(_config(), lambda: None)
    connection = MagicMock()
    network_socket = MagicMock()
    connection.socket.return_value = network_socket
    thread = MagicMock()
    worker._connection = connection
    worker._thread = thread

    worker.stop()

    network_socket.shutdown.assert_called_once_with(socket.SHUT_RDWR)
    connection.shutdown.assert_not_called()
    thread.join.assert_called_once_with(timeout=5)
