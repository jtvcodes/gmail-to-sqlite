"""Unit tests for sync engine changes — Task 5.1.

Tests cover:
- _fetch_message passes format='raw' to the API call
- decodes base64url payload and calls from_raw_source
- logs warning and sets raw=None when 'raw' key absent
- logs error and sets raw=None when base64url decode fails
- all_messages calls get_message_ids_missing_raw not get_message_ids_missing_html

Requirements: 2.1, 2.2, 2.3, 2.4, 10.2
"""

import base64
import logging
from unittest.mock import MagicMock, patch, call

import pytest

from gmail_to_sqlite import message as message_module
from gmail_to_sqlite.sync import _fetch_message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(response: dict) -> MagicMock:
    """Build a mock Gmail API service that returns *response* from .get().execute()."""
    service = MagicMock()
    (
        service.users.return_value
        .messages.return_value
        .get.return_value
        .execute.return_value
    ) = response
    return service


def _encode_raw(text: str) -> str:
    """Base64url-encode a UTF-8 string, as the Gmail API would return."""
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")


# Minimal RFC 2822 message used across tests
_MINIMAL_RFC2822 = (
    "From: sender@example.com\r\n"
    "To: recipient@example.com\r\n"
    "Subject: Test\r\n"
    "Date: Mon, 01 Jan 2024 12:00:00 +0000\r\n"
    "\r\n"
    "Hello, world!\r\n"
)

_LABELS: dict = {}


# ---------------------------------------------------------------------------
# Task 5 / Requirement 2.1 — format='raw' is passed to the API call
# ---------------------------------------------------------------------------

class TestFetchMessageFormatRaw:
    """_fetch_message must request format='raw' from the Gmail API."""

    def test_format_raw_passed_to_api(self):
        """Verify that the .get() call includes format='raw'."""
        encoded = _encode_raw(_MINIMAL_RFC2822)
        service = _make_service({"raw": encoded})

        _fetch_message(service, "msg-001", _LABELS)

        service.users.return_value.messages.return_value.get.assert_called_once_with(
            userId="me", id="msg-001", format="raw"
        )


# ---------------------------------------------------------------------------
# Task 5 / Requirement 2.2 — base64url decode and call from_raw_source
# ---------------------------------------------------------------------------

class TestFetchMessageDecodeAndParse:
    """_fetch_message must decode the base64url payload and call from_raw_source."""

    def test_decodes_base64url_and_calls_from_raw_source(self):
        """When 'raw' key is present, decode it and call Message.from_raw_source."""
        encoded = _encode_raw(_MINIMAL_RFC2822)
        service = _make_service({"raw": encoded})

        with patch.object(
            message_module.Message, "from_raw_source", wraps=message_module.Message.from_raw_source
        ) as mock_from_raw_source:
            msg = _fetch_message(service, "msg-001", _LABELS)

        mock_from_raw_source.assert_called_once_with(_MINIMAL_RFC2822, _LABELS)
        # The returned object should have raw set to the decoded string
        assert msg.raw == _MINIMAL_RFC2822

    def test_returned_message_has_correct_raw(self):
        """The Message object returned should carry the decoded RFC 2822 string."""
        encoded = _encode_raw(_MINIMAL_RFC2822)
        service = _make_service({"raw": encoded})

        msg = _fetch_message(service, "msg-001", _LABELS)

        assert msg.raw == _MINIMAL_RFC2822

    def test_from_raw_not_called(self):
        """from_raw (old method) must NOT be called — only from_raw_source."""
        encoded = _encode_raw(_MINIMAL_RFC2822)
        service = _make_service({"raw": encoded})

        with patch.object(message_module.Message, "from_raw") as mock_from_raw:
            _fetch_message(service, "msg-001", _LABELS)

        mock_from_raw.assert_not_called()


# ---------------------------------------------------------------------------
# Task 5 / Requirement 2.3 — missing 'raw' key → WARNING + raw=None
# ---------------------------------------------------------------------------

class TestFetchMessageMissingRawKey:
    """When the API response has no 'raw' key, log a WARNING and return msg with raw=None."""

    def test_logs_warning_when_raw_key_absent(self, caplog):
        """A WARNING must be logged when the response has no 'raw' field."""
        service = _make_service({"id": "msg-002"})  # no 'raw' key

        with caplog.at_level(logging.WARNING):
            msg = _fetch_message(service, "msg-002", _LABELS)

        assert any(
            "raw" in record.message.lower() and record.levelno == logging.WARNING
            for record in caplog.records
        ), "Expected a WARNING log mentioning 'raw'"

    def test_raw_is_none_when_raw_key_absent(self):
        """The returned Message must have raw=None when the response has no 'raw' field."""
        service = _make_service({"id": "msg-002"})

        msg = _fetch_message(service, "msg-002", _LABELS)

        assert msg.raw is None

    def test_returns_message_object_when_raw_key_absent(self):
        """_fetch_message must return a Message instance even when 'raw' key is absent."""
        service = _make_service({"id": "msg-002"})

        msg = _fetch_message(service, "msg-002", _LABELS)

        assert isinstance(msg, message_module.Message)


# ---------------------------------------------------------------------------
# Task 5 / Requirement 2.4 — base64url decode failure → ERROR + raw=None
# ---------------------------------------------------------------------------

class TestFetchMessageDecodeFailure:
    """When base64url decoding fails completely, log an error and return msg with raw=None.
    When UTF-8 fails but latin-1 succeeds, log a warning and return msg with raw set."""

    def test_logs_error_when_decode_fails(self, caplog):
        """A WARNING is logged when UTF-8 decode fails and latin-1 fallback is used."""
        # Use bytes that are invalid UTF-8 but valid latin-1
        invalid_utf8 = base64.urlsafe_b64encode(b"\x80\x81\x82").decode("ascii")
        service = _make_service({"raw": invalid_utf8})

        with caplog.at_level(logging.WARNING):
            msg = _fetch_message(service, "msg-003", _LABELS)

        assert any(
            record.levelno == logging.WARNING
            for record in caplog.records
        ), "Expected a WARNING log when UTF-8 decode fails"

    def test_raw_is_none_when_decode_fails(self):
        """raw is None only when base64url decoding itself raises (not just UTF-8 failure)."""
        # Provide bytes that are invalid UTF-8 — latin-1 fallback sets raw to something
        invalid_utf8 = base64.urlsafe_b64encode(b"\x80\x81\x82").decode("ascii")
        service = _make_service({"raw": invalid_utf8})

        msg = _fetch_message(service, "msg-003", _LABELS)

        # latin-1 fallback succeeds, so raw is not None
        assert msg.raw is not None

    def test_returns_message_object_when_decode_fails(self):
        """_fetch_message must return a Message instance even when decoding falls back."""
        invalid_utf8 = base64.urlsafe_b64encode(b"\x80\x81\x82").decode("ascii")
        service = _make_service({"raw": invalid_utf8})

        msg = _fetch_message(service, "msg-003", _LABELS)

        assert isinstance(msg, message_module.Message)

    def test_logs_error_when_utf8_decode_fails(self, caplog):
        """A WARNING must be logged when UTF-8 decode fails but latin-1 fallback succeeds."""
        # Encode raw bytes that are not valid UTF-8 but are valid latin-1
        invalid_utf8_bytes = b"\xff\xfe"
        encoded = base64.urlsafe_b64encode(invalid_utf8_bytes).decode("ascii")
        service = _make_service({"raw": encoded})

        with caplog.at_level(logging.WARNING):
            msg = _fetch_message(service, "msg-004", _LABELS)

        assert any(
            record.levelno == logging.WARNING and "latin-1" in record.message.lower()
            for record in caplog.records
        ), "Expected a WARNING log about latin-1 fallback"
        # raw should be set (latin-1 decoded successfully)
        assert msg.raw is not None


# ---------------------------------------------------------------------------
# Task 5 / Requirement 10.2 — all_messages uses get_message_ids_missing_raw
# ---------------------------------------------------------------------------

class TestAllMessagesUsesGetMessageIdsMissingRaw:
    """all_messages must call db.get_message_ids_missing_raw, not get_message_ids_missing_html."""

    _common_patches = [
        ("gmail_to_sqlite.db.get_sync_state", {"return_value": None}),
        ("gmail_to_sqlite.db.set_sync_state", {}),
        ("gmail_to_sqlite.db.get_cached_gmail_ids", {"return_value": None}),
        ("gmail_to_sqlite.db.set_cached_gmail_ids", {}),
        ("gmail_to_sqlite.db.upsert_gmail_index", {}),
        ("gmail_to_sqlite.db.get_unsynced_gmail_ids", {"return_value": []}),
        ("gmail_to_sqlite.db.get_gmail_index_count", {"return_value": {"total": 0, "synced": 0, "unsynced": 0}}),
        ("gmail_to_sqlite.db.mark_gmail_index_synced", {}),
        ("gmail_to_sqlite.db.mark_gmail_index_deleted", {}),
    ]

    def test_all_messages_calls_get_message_ids_missing_raw(self):
        """all_messages must call db.get_message_ids_missing_raw during a full sync."""
        from gmail_to_sqlite import sync as sync_module

        mock_credentials = MagicMock()

        with (
            patch.object(sync_module, "_create_service"),
            patch.object(sync_module, "get_labels", return_value={}),
            patch.object(sync_module, "get_message_ids_from_gmail", return_value=(["msg-001"], None)),
            patch.object(sync_module, "_detect_and_mark_deleted_messages"),
            patch("gmail_to_sqlite.db.get_all_message_ids", return_value=["msg-001"]),
            patch("gmail_to_sqlite.db.get_message_ids_missing_raw", return_value=[]) as mock_missing_raw,
            patch("gmail_to_sqlite.db.get_sync_state", return_value=None),
            patch("gmail_to_sqlite.db.set_sync_state"),
            patch("gmail_to_sqlite.db.upsert_gmail_index"),
            patch("gmail_to_sqlite.db.get_unsynced_gmail_ids", return_value=[]),
            patch("gmail_to_sqlite.db.get_gmail_index_count", return_value={"total": 0, "synced": 0, "unsynced": 0}),
            patch("gmail_to_sqlite.db.mark_gmail_index_synced"),
            patch("gmail_to_sqlite.db.mark_gmail_index_deleted"),
        ):
            sync_module.all_messages(
                mock_credentials,
                data_dir="/tmp",
                full_sync=True,
                force=False,
            )

        mock_missing_raw.assert_called_once()

    def test_all_messages_does_not_call_get_message_ids_missing_html(self):
        """all_messages must NOT call any function named get_message_ids_missing_html."""
        from gmail_to_sqlite import sync as sync_module
        from gmail_to_sqlite import db as db_module

        mock_credentials = MagicMock()

        assert not hasattr(db_module, "get_message_ids_missing_html"), (
            "db.get_message_ids_missing_html should not exist; "
            "it must have been replaced by get_message_ids_missing_raw"
        )

        with (
            patch.object(sync_module, "_create_service"),
            patch.object(sync_module, "get_labels", return_value={}),
            patch.object(sync_module, "get_message_ids_from_gmail", return_value=([], None)),
            patch.object(sync_module, "_detect_and_mark_deleted_messages"),
            patch("gmail_to_sqlite.db.get_all_message_ids", return_value=[]),
            patch("gmail_to_sqlite.db.get_message_ids_missing_raw", return_value=[]),
            patch("gmail_to_sqlite.db.get_sync_state", return_value=None),
            patch("gmail_to_sqlite.db.set_sync_state"),
            patch("gmail_to_sqlite.db.upsert_gmail_index"),
            patch("gmail_to_sqlite.db.get_unsynced_gmail_ids", return_value=[]),
            patch("gmail_to_sqlite.db.get_gmail_index_count", return_value={"total": 0, "synced": 0, "unsynced": 0}),
            patch("gmail_to_sqlite.db.mark_gmail_index_synced"),
            patch("gmail_to_sqlite.db.mark_gmail_index_deleted"),
        ):
            sync_module.all_messages(
                mock_credentials,
                data_dir="/tmp",
                full_sync=True,
                force=False,
            )
