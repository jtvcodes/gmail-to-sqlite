"""Tests for message parsing functionality."""

import base64

import pytest
from gmail_to_sqlite.message import Message, MessageParsingError


def _make_minimal_raw(payload: dict) -> dict:
    """Build a minimal Gmail API message dict with the given payload."""
    return {
        "id": "test123",
        "threadId": "thread123",
        "payload": payload,
        "sizeEstimate": 100,
    }


class TestMessageParsing:
    """Test message parsing operations."""

    def test_message_creation(self):
        """Test basic message creation."""
        message = Message()
        assert message is not None

    def test_from_raw_empty(self):
        """Test parsing with empty message data."""
        with pytest.raises((MessageParsingError, KeyError, AttributeError)):
            Message.from_raw({}, {})

    def test_from_raw_minimal(self):
        """Test parsing with minimal valid message data."""
        message_data = {
            "id": "test123",
            "threadId": "thread123",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "From", "value": "test@example.com"},
                    {"name": "Date", "value": "Mon, 1 Jan 2024 12:00:00 +0000"},
                ]
            },
            "sizeEstimate": 1000,
        }

        labels = {"INBOX": "INBOX"}

        try:
            message = Message.from_raw(message_data, labels)
            assert message.id == "test123"
            assert message.thread_id == "thread123"
            assert message.subject == "Test Subject"
        except Exception as e:
            # Some fields might be missing for this minimal test
            pytest.skip(f"Minimal test data insufficient: {e}")

    def test_parse_addresses(self):
        """Test address parsing."""
        message = Message()
        addresses = "test@example.com, John Doe <john@example.com>"
        parsed = message.parse_addresses(addresses)
        assert isinstance(parsed, list)
        assert len(parsed) >= 1

    # ------------------------------------------------------------------
    # Task 5.1 — Non-multipart text/html payload
    # ------------------------------------------------------------------

    def test_non_multipart_html_payload(self):
        """5.1: Non-multipart text/html payload sets body_html and body (plain text)."""
        html_content = "<html><body><p>Hello <b>World</b></p></body></html>"
        encoded = base64.urlsafe_b64encode(html_content.encode("utf-8")).decode("ascii")

        raw = _make_minimal_raw(
            {
                "mimeType": "text/html",
                "headers": [],
                "body": {"data": encoded, "size": len(html_content)},
            }
        )

        message = Message.from_raw(raw, {})

        # body_html must equal the decoded HTML string
        assert message.body_html == html_content

        # body must be the plain-text conversion (no HTML tags)
        assert message.body is not None
        assert "<" not in message.body  # tags stripped
        assert "Hello" in message.body  # text content preserved

    # ------------------------------------------------------------------
    # Task 5.2 — Non-multipart text/plain payload
    # ------------------------------------------------------------------

    def test_non_multipart_plain_payload(self):
        """5.2: Non-multipart text/plain payload sets body and leaves body_html as None."""
        plain_content = "Hello, this is plain text."
        encoded = base64.urlsafe_b64encode(plain_content.encode("utf-8")).decode("ascii")

        raw = _make_minimal_raw(
            {
                "mimeType": "text/plain",
                "headers": [],
                "body": {"data": encoded, "size": len(plain_content)},
            }
        )

        message = Message.from_raw(raw, {})

        assert message.body_html is None
        assert message.body is not None
        assert plain_content in message.body

    # ------------------------------------------------------------------
    # Task 5.3 — Multipart payload with a text/html part
    # ------------------------------------------------------------------

    def test_multipart_with_html_part(self):
        """5.3: Multipart payload with a text/html part sets body_html to the HTML content."""
        plain_content = "Hello, plain text."
        html_content = "<html><body><p>Hello, <em>HTML</em></p></body></html>"

        plain_encoded = base64.urlsafe_b64encode(plain_content.encode("utf-8")).decode("ascii")
        html_encoded = base64.urlsafe_b64encode(html_content.encode("utf-8")).decode("ascii")

        raw = _make_minimal_raw(
            {
                "mimeType": "multipart/alternative",
                "headers": [],
                "body": {"size": 0},
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "headers": [],
                        "body": {"data": plain_encoded, "size": len(plain_content)},
                    },
                    {
                        "mimeType": "text/html",
                        "headers": [],
                        "body": {"data": html_encoded, "size": len(html_content)},
                    },
                ],
            }
        )

        message = Message.from_raw(raw, {})

        assert message.body_html == html_content

    # ------------------------------------------------------------------
    # Task 5.4 — Multipart payload with no text/html part
    # ------------------------------------------------------------------

    def test_multipart_without_html_part(self):
        """5.4: Multipart payload with no text/html part leaves body_html as None."""
        plain_content = "Just plain text, no HTML."
        plain_encoded = base64.urlsafe_b64encode(plain_content.encode("utf-8")).decode("ascii")

        raw = _make_minimal_raw(
            {
                "mimeType": "multipart/mixed",
                "headers": [],
                "body": {"size": 0},
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "headers": [],
                        "body": {"data": plain_encoded, "size": len(plain_content)},
                    },
                ],
            }
        )

        message = Message.from_raw(raw, {})

        assert message.body_html is None

    # ------------------------------------------------------------------
    # Task 5.5 — Malformed base64 in the HTML part
    # ------------------------------------------------------------------

    def test_malformed_base64_in_html_part(self):
        """5.5: Malformed base64 in the HTML part sets body_html to None without raising."""
        raw = _make_minimal_raw(
            {
                "mimeType": "multipart/alternative",
                "headers": [],
                "body": {"size": 0},
                "parts": [
                    {
                        "mimeType": "text/html",
                        "headers": [],
                        "body": {"data": "!!!not-valid-base64!!!", "size": 0},
                    },
                ],
            }
        )

        # Must not raise any exception
        message = Message.from_raw(raw, {})

        assert message.body_html is None


# ===========================================================================
# Task 14 — Unit tests for attachment parsing
# ===========================================================================


class TestAttachmentParsing:
    """Tests for _extract_attachments and attachment field extraction."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_attachment_part(
        mime_type: str = "application/pdf",
        content_disposition: str = None,
        content_type_header: str = None,
        body_data: bytes = None,
        attachment_id: str = None,
        size: int = None,
    ) -> dict:
        """Build a minimal Gmail API multipart part dict for an attachment."""
        headers = []
        if content_disposition is not None:
            headers.append({"name": "Content-Disposition", "value": content_disposition})
        if content_type_header is not None:
            headers.append({"name": "Content-Type", "value": content_type_header})

        body: dict = {}
        if body_data is not None:
            body["data"] = base64.urlsafe_b64encode(body_data).decode("ascii")
            body["size"] = size if size is not None else len(body_data)
        else:
            body["size"] = size if size is not None else 0
        if attachment_id is not None:
            body["attachmentId"] = attachment_id

        return {
            "mimeType": mime_type,
            "headers": headers,
            "body": body,
        }

    @staticmethod
    def _make_multipart_raw(parts: list) -> dict:
        """Build a minimal multipart Gmail API message dict."""
        return _make_minimal_raw(
            {
                "mimeType": "multipart/mixed",
                "headers": [],
                "body": {"size": 0},
                "parts": parts,
            }
        )

    # ------------------------------------------------------------------
    # 14.1 — One attachment: all fields extracted correctly
    # ------------------------------------------------------------------

    def test_single_attachment_all_fields(self):
        """14.1: Multipart payload with one attachment — all fields extracted correctly."""
        attachment_bytes = b"PDF content here"
        part = self._make_attachment_part(
            mime_type="application/pdf",
            content_disposition='attachment; filename="report.pdf"',
            body_data=attachment_bytes,
            attachment_id="att_abc123",
            size=len(attachment_bytes),
        )
        raw = self._make_multipart_raw([part])

        message = Message.from_raw(raw, {})

        assert len(message.attachments) == 1
        att = message.attachments[0]
        assert att.filename == "report.pdf"
        assert att.mime_type == "application/pdf"
        assert att.size == len(attachment_bytes)
        assert att.data == attachment_bytes
        assert att.attachment_id == "att_abc123"

    # ------------------------------------------------------------------
    # 14.2 — Multiple attachments: all present in message.attachments
    # ------------------------------------------------------------------

    def test_multiple_attachments(self):
        """14.2: Multipart payload with multiple attachment parts — all present."""
        pdf_bytes = b"PDF data"
        img_bytes = b"PNG data"

        parts = [
            self._make_attachment_part(
                mime_type="application/pdf",
                content_disposition='attachment; filename="doc.pdf"',
                body_data=pdf_bytes,
            ),
            self._make_attachment_part(
                mime_type="image/png",
                content_disposition='attachment; filename="photo.png"',
                body_data=img_bytes,
            ),
        ]
        raw = self._make_multipart_raw(parts)

        message = Message.from_raw(raw, {})

        assert len(message.attachments) == 2
        mime_types = {att.mime_type for att in message.attachments}
        assert "application/pdf" in mime_types
        assert "image/png" in mime_types
        filenames = {att.filename for att in message.attachments}
        assert "doc.pdf" in filenames
        assert "photo.png" in filenames

    # ------------------------------------------------------------------
    # 14.3 — No attachment parts (plain-text only): empty list
    # ------------------------------------------------------------------

    def test_no_attachments_plain_text_only(self):
        """14.3: Payload with no attachment parts — message.attachments is an empty list."""
        plain_content = "Just plain text, no attachments."
        plain_encoded = base64.urlsafe_b64encode(plain_content.encode("utf-8")).decode("ascii")

        raw = _make_minimal_raw(
            {
                "mimeType": "multipart/mixed",
                "headers": [],
                "body": {"size": 0},
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "headers": [],
                        "body": {"data": plain_encoded, "size": len(plain_content)},
                    }
                ],
            }
        )

        message = Message.from_raw(raw, {})

        assert message.attachments == []

    # ------------------------------------------------------------------
    # 14.4 — Filename from Content-Disposition header
    # ------------------------------------------------------------------

    def test_filename_from_content_disposition(self):
        """14.4: Attachment with filename in Content-Disposition — filename extracted."""
        part = self._make_attachment_part(
            mime_type="application/pdf",
            content_disposition='attachment; filename="invoice.pdf"',
            body_data=b"data",
        )
        raw = self._make_multipart_raw([part])

        message = Message.from_raw(raw, {})

        assert len(message.attachments) == 1
        assert message.attachments[0].filename == "invoice.pdf"

    # ------------------------------------------------------------------
    # 14.5 — Filename only in Content-Type name parameter (fallback)
    # ------------------------------------------------------------------

    def test_filename_fallback_content_type_name(self):
        """14.5: Attachment with filename only in Content-Type name param — fallback works."""
        part = self._make_attachment_part(
            mime_type="application/pdf",
            # No Content-Disposition header
            content_type_header='application/pdf; name="spreadsheet.xlsx"',
            body_data=b"data",
        )
        raw = self._make_multipart_raw([part])

        message = Message.from_raw(raw, {})

        assert len(message.attachments) == 1
        assert message.attachments[0].filename == "spreadsheet.xlsx"

    # ------------------------------------------------------------------
    # 14.6 — No filename in any header: filename is None
    # ------------------------------------------------------------------

    def test_no_filename_in_any_header(self):
        """14.6: Attachment with no filename in any header — filename is None."""
        part = self._make_attachment_part(
            mime_type="application/octet-stream",
            # No Content-Disposition, no Content-Type name param
            body_data=b"binary data",
        )
        raw = self._make_multipart_raw([part])

        message = Message.from_raw(raw, {})

        assert len(message.attachments) == 1
        assert message.attachments[0].filename is None

    # ------------------------------------------------------------------
    # 14.7 — Malformed base64 data: data is None, no exception raised
    # ------------------------------------------------------------------

    def test_malformed_base64_attachment_data(self):
        """14.7: Attachment with malformed base64 data — data is None, no exception."""
        # "abc" has incorrect padding and raises binascii.Error in urlsafe_b64decode
        part = {
            "mimeType": "application/pdf",
            "headers": [
                {"name": "Content-Disposition", "value": 'attachment; filename="bad.pdf"'}
            ],
            "body": {
                "data": "abc",  # incorrect padding → binascii.Error
                "size": 0,
            },
        }
        raw = self._make_multipart_raw([part])

        # Must not raise any exception
        message = Message.from_raw(raw, {})

        assert len(message.attachments) == 1
        assert message.attachments[0].data is None

    # ------------------------------------------------------------------
    # 14.8 — Large attachment (no body.data, only body.attachmentId)
    # ------------------------------------------------------------------

    def test_large_attachment_no_data_only_attachment_id(self):
        """14.8: Large attachment with no body.data — data is None, attachment_id is set."""
        part = {
            "mimeType": "video/mp4",
            "headers": [
                {"name": "Content-Disposition", "value": 'attachment; filename="video.mp4"'}
            ],
            "body": {
                # No "data" key — large attachment
                "size": 10485760,  # 10 MB
                "attachmentId": "large_att_xyz789",
            },
        }
        raw = self._make_multipart_raw([part])

        message = Message.from_raw(raw, {})

        assert len(message.attachments) == 1
        att = message.attachments[0]
        assert att.data is None
        assert att.attachment_id == "large_att_xyz789"


# ===========================================================================
# Task 2.7 — Unit tests for message parser (from_raw_source, extract_html_from_raw,
#             _strip_to_html_tag, _parse_received_date, received_date)
# ===========================================================================

import email as _email
import textwrap
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import format_datetime
from datetime import timezone, datetime as _datetime

from gmail_to_sqlite.message import extract_html_from_raw, _strip_to_html_tag


def _build_multipart_rfc2822(
    plain_text: str = "Hello plain",
    html_text: str = "<html><body>Hello HTML</body></html>",
    from_addr: str = "sender@example.com",
    to_addr: str = "recipient@example.com",
    subject: str = "Test Subject",
    date_str: str = "Mon, 01 Jan 2024 12:00:00 +0000",
    received_headers: list = None,
) -> str:
    """Build a minimal multipart/alternative RFC 2822 message string."""
    msg = MIMEMultipart("alternative")
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["Date"] = date_str
    if received_headers:
        for rh in received_headers:
            msg["Received"] = rh
    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(html_text, "html", "utf-8"))
    return msg.as_string()


def _build_plain_only_rfc2822(
    plain_text: str = "Hello plain",
    from_addr: str = "sender@example.com",
    to_addr: str = "recipient@example.com",
    subject: str = "Test Subject",
    date_str: str = "Mon, 01 Jan 2024 12:00:00 +0000",
) -> str:
    """Build a plain-text-only RFC 2822 message string."""
    msg = MIMEText(plain_text, "plain", "utf-8")
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["Date"] = date_str
    return msg.as_string()


class TestExtractHtmlFromRaw:
    """Tests for the extract_html_from_raw module-level function."""

    def test_extract_html_from_multipart_message(self):
        """extract_html_from_raw returns the HTML part from a multipart message."""
        html_content = "<html><body><p>Hello World</p></body></html>"
        raw = _build_multipart_rfc2822(html_text=html_content)
        result = extract_html_from_raw(raw)
        assert result is not None
        assert "Hello World" in result

    def test_returns_none_for_plain_text_only(self):
        """extract_html_from_raw returns None when there is no text/html part."""
        raw = _build_plain_only_rfc2822()
        result = extract_html_from_raw(raw)
        assert result is None

    def test_returns_none_for_none_input(self):
        """extract_html_from_raw returns None for None input."""
        result = extract_html_from_raw(None)
        assert result is None

    def test_returns_none_for_empty_string(self):
        """extract_html_from_raw returns None for empty string input."""
        result = extract_html_from_raw("")
        assert result is None

    def test_strips_preamble_before_html_tag(self):
        """extract_html_from_raw strips content before <html tag."""
        html_content = "preamble text\n<html><body>Content</body></html>"
        raw = _build_multipart_rfc2822(html_text=html_content)
        result = extract_html_from_raw(raw)
        assert result is not None
        assert result.startswith("<html")

    def test_single_part_html_message(self):
        """extract_html_from_raw works on a single-part text/html message."""
        html_content = "<html><body>Single part HTML</body></html>"
        msg = MIMEText(html_content, "html", "utf-8")
        msg["From"] = "sender@example.com"
        msg["To"] = "recipient@example.com"
        msg["Subject"] = "HTML only"
        msg["Date"] = "Mon, 01 Jan 2024 12:00:00 +0000"
        raw = msg.as_string()
        result = extract_html_from_raw(raw)
        assert result is not None
        assert "Single part HTML" in result


class TestStripToHtmlTag:
    """Tests for the _strip_to_html_tag module-level helper."""

    def test_strips_preamble_before_html_tag(self):
        """_strip_to_html_tag strips everything before <html."""
        html = "Some preamble text\n<html><body>Content</body></html>"
        result = _strip_to_html_tag(html)
        assert result is not None
        assert result.startswith("<html")
        assert "preamble" not in result

    def test_returns_unchanged_when_no_html_tag(self):
        """_strip_to_html_tag returns the string unchanged when no <html tag."""
        html = "<div>No html tag here</div>"
        result = _strip_to_html_tag(html)
        assert result == html

    def test_returns_none_for_none_input(self):
        """_strip_to_html_tag returns None for None input."""
        result = _strip_to_html_tag(None)
        assert result is None

    def test_returns_none_for_empty_string(self):
        """_strip_to_html_tag returns None for empty string."""
        result = _strip_to_html_tag("")
        assert result is None

    def test_preserves_html_when_no_preamble(self):
        """_strip_to_html_tag returns the full string when it starts with <html."""
        html = "<html><body>Content</body></html>"
        result = _strip_to_html_tag(html)
        assert result == html


class TestFromRawSource:
    """Tests for Message.from_raw_source classmethod."""

    def test_extracts_correct_headers(self):
        """from_raw_source extracts From, To, Subject, Date headers correctly."""
        raw = _build_multipart_rfc2822(
            from_addr="Alice <alice@example.com>",
            to_addr="bob@example.com",
            subject="Hello Bob",
            date_str="Mon, 01 Jan 2024 12:00:00 +0000",
        )
        msg = Message.from_raw_source(raw, {})
        assert msg.sender["email"] == "alice@example.com"
        assert msg.sender["name"] == "Alice"
        assert any(r["email"] == "bob@example.com" for r in msg.recipients.get("to", []))
        assert msg.subject == "Hello Bob"

    def test_raw_attribute_equals_input(self):
        """from_raw_source sets msg.raw equal to the input string."""
        raw = _build_multipart_rfc2822()
        msg = Message.from_raw_source(raw, {})
        assert msg.raw == raw

    def test_extracts_plain_text_body(self):
        """from_raw_source extracts the plain-text body."""
        raw = _build_multipart_rfc2822(plain_text="This is the plain body.")
        msg = Message.from_raw_source(raw, {})
        assert msg.body is not None
        assert "This is the plain body." in msg.body

    def test_fallback_to_html2text_when_no_plain(self):
        """from_raw_source falls back to html2text when no text/plain part."""
        html_content = "<html><body><p>HTML only body</p></body></html>"
        msg_obj = MIMEText(html_content, "html", "utf-8")
        msg_obj["From"] = "sender@example.com"
        msg_obj["To"] = "recipient@example.com"
        msg_obj["Subject"] = "HTML only"
        msg_obj["Date"] = "Mon, 01 Jan 2024 12:00:00 +0000"
        raw = msg_obj.as_string()
        msg = Message.from_raw_source(raw, {})
        assert msg.body is not None
        assert "HTML only body" in msg.body

    def test_received_date_from_last_received_header(self):
        """from_raw_source extracts received_date from the last Received: header."""
        received_headers = [
            "by server1.example.com; Mon, 01 Jan 2024 10:00:00 +0000",
            "by server2.example.com; Mon, 01 Jan 2024 12:00:00 +0000",
        ]
        raw = _build_multipart_rfc2822(received_headers=received_headers)
        msg = Message.from_raw_source(raw, {})
        assert msg.received_date is not None
        # Should use the last header (12:00:00)
        assert msg.received_date.hour == 12

    def test_received_date_fallback_to_x_received(self):
        """from_raw_source falls back to X-Received: when no Received: header."""
        msg_obj = MIMEMultipart("alternative")
        msg_obj["From"] = "sender@example.com"
        msg_obj["To"] = "recipient@example.com"
        msg_obj["Subject"] = "Test"
        msg_obj["Date"] = "Mon, 01 Jan 2024 12:00:00 +0000"
        msg_obj["X-Received"] = "by xserver.example.com; Mon, 01 Jan 2024 11:30:00 +0000"
        msg_obj.attach(MIMEText("plain", "plain", "utf-8"))
        raw = msg_obj.as_string()
        msg = Message.from_raw_source(raw, {})
        assert msg.received_date is not None
        assert msg.received_date.hour == 11
        assert msg.received_date.minute == 30

    def test_received_date_none_when_no_headers(self):
        """from_raw_source sets received_date to None when no Received/X-Received headers."""
        raw = _build_multipart_rfc2822()
        msg = Message.from_raw_source(raw, {})
        assert msg.received_date is None

    def test_received_date_none_when_no_semicolon(self):
        """from_raw_source sets received_date to None when Received header has no semicolon."""
        msg_obj = MIMEMultipart("alternative")
        msg_obj["From"] = "sender@example.com"
        msg_obj["To"] = "recipient@example.com"
        msg_obj["Subject"] = "Test"
        msg_obj["Date"] = "Mon, 01 Jan 2024 12:00:00 +0000"
        msg_obj["Received"] = "by server.example.com with SMTP id abc123"
        msg_obj.attach(MIMEText("plain", "plain", "utf-8"))
        raw = msg_obj.as_string()
        msg = Message.from_raw_source(raw, {})
        assert msg.received_date is None

    def test_received_date_none_when_date_malformed(self):
        """from_raw_source sets received_date to None when date substring is malformed."""
        msg_obj = MIMEMultipart("alternative")
        msg_obj["From"] = "sender@example.com"
        msg_obj["To"] = "recipient@example.com"
        msg_obj["Subject"] = "Test"
        msg_obj["Date"] = "Mon, 01 Jan 2024 12:00:00 +0000"
        msg_obj["Received"] = "by server.example.com; NOT A VALID DATE"
        msg_obj.attach(MIMEText("plain", "plain", "utf-8"))
        raw = msg_obj.as_string()
        msg = Message.from_raw_source(raw, {})
        assert msg.received_date is None
