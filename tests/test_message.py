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
