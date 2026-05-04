import base64
import email
import email.header
import email.message
import logging
from dataclasses import dataclass
from datetime import datetime
from email.utils import parseaddr, parsedate_to_datetime
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from .constants import SUPPORTED_MIME_TYPES

logger = logging.getLogger(__name__)


def _decode_header(value: Optional[str]) -> Optional[str]:
    """
    Decode an RFC 2047 encoded header value (e.g. =?UTF-8?Q?...?=) to a
    plain Unicode string. Returns the value unchanged if it is already plain
    text or if decoding fails.
    """
    if not value:
        return value
    try:
        parts = email.header.decode_header(value)
        decoded_parts = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded_parts.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                decoded_parts.append(part)
        return "".join(decoded_parts)
    except Exception:
        return value


@dataclass
class Attachment:
    """Represents an email attachment extracted from a Gmail API payload."""

    filename: Optional[str]
    mime_type: str
    size: int
    data: Optional[bytes]
    attachment_id: Optional[str]
    content_id: Optional[str] = None


class MessageParsingError(Exception):
    """Custom exception for message parsing errors."""

    pass


class Message:
    """
    Represents a Gmail message with all its attributes and parsing capabilities.

    Attributes:
        id (Optional[str]): Message ID
        thread_id (Optional[str]): Thread ID
        sender (Dict): Sender information with name and email
        recipients (Dict): Recipients organized by type (to, cc, bcc)
        labels (List[str]): List of label names
        subject (Optional[str]): Message subject
        body (Optional[str]): Message body text
        size (int): Message size in bytes
        timestamp (Optional[datetime]): Message timestamp
        is_read (bool): Whether message has been read
        is_outgoing (bool): Whether message was sent by user
    """

    def __init__(self) -> None:
        self.id: Optional[str] = None
        self.thread_id: Optional[str] = None
        self.sender: Dict[str, str] = {}
        self.recipients: Dict[str, List[Dict[str, str]]] = {}
        self.labels: List[str] = []
        self.subject: Optional[str] = None
        self.body: Optional[str] = None
        self.body_html: Optional[str] = None
        self.raw: Optional[str] = None
        self.received_date: Optional[datetime] = None
        self.size: int = 0
        self.timestamp: Optional[datetime] = None
        self.is_read: bool = False
        self.is_outgoing: bool = False
        self.attachments: List[Attachment] = []

    @classmethod
    def from_raw(cls, raw: Dict, labels: Dict[str, str]) -> "Message":
        """
        Create a Message object from a raw Gmail API response.

        Args:
            raw (Dict): The raw message data from Gmail API.
            labels (Dict[str, str]): Mapping of label IDs to label names.

        Returns:
            Message: The parsed Message object.

        Raises:
            MessageParsingError: If message parsing fails.
        """
        try:
            msg = cls()
            msg.parse(raw, labels)
            return msg
        except Exception as e:
            raise MessageParsingError(f"Failed to parse message: {e}")

    @classmethod
    def from_raw_source(cls, raw_str: str, labels: Dict[str, str]) -> "Message":
        """
        Create a Message object from a decoded RFC 2822 email string.

        Args:
            raw_str (str): The decoded RFC 2822 email string.
            labels (Dict[str, str]): Mapping of label IDs to label names.

        Returns:
            Message: The parsed Message object.

        Raises:
            MessageParsingError: If message parsing fails.
        """
        try:
            parsed = email.message_from_string(raw_str)
            msg = cls()

            # Extract standard headers
            from_header = _decode_header(parsed.get("From", ""))
            addr = parseaddr(from_header)
            msg.sender = {"name": _decode_header(addr[0]) or "", "email": addr[1]}

            to_header = parsed.get("To", "")
            if to_header:
                msg.recipients["to"] = msg.parse_addresses(to_header)

            cc_header = parsed.get("Cc", "")
            if cc_header:
                msg.recipients["cc"] = msg.parse_addresses(cc_header)

            bcc_header = parsed.get("Bcc", "")
            if bcc_header:
                msg.recipients["bcc"] = msg.parse_addresses(bcc_header)

            msg.subject = _decode_header(parsed.get("Subject"))

            date_header = parsed.get("Date", "")
            if date_header:
                try:
                    msg.timestamp = parsedate_to_datetime(date_header)
                except Exception:
                    msg.timestamp = None

            # Extract plain-text body by walking MIME parts
            plain_body: Optional[str] = None
            html_body: Optional[str] = None

            if parsed.is_multipart():
                for part in parsed.walk():
                    content_type = part.get_content_type()
                    if content_type == "text/plain" and plain_body is None:
                        try:
                            payload = part.get_payload(decode=True)
                            if payload is not None:
                                charset = part.get_content_charset() or "utf-8"
                                plain_body = payload.decode(charset, errors="replace")
                        except Exception:
                            pass
                    elif content_type == "text/html" and html_body is None:
                        try:
                            payload = part.get_payload(decode=True)
                            if payload is not None:
                                charset = part.get_content_charset() or "utf-8"
                                html_body = payload.decode(charset, errors="replace")
                        except Exception:
                            pass
            else:
                content_type = parsed.get_content_type()
                try:
                    payload = parsed.get_payload(decode=True)
                    if payload is not None:
                        charset = parsed.get_content_charset() or "utf-8"
                        decoded = payload.decode(charset, errors="replace")
                        if content_type == "text/plain":
                            plain_body = decoded
                        elif content_type == "text/html":
                            html_body = decoded
                except Exception:
                    pass

            if plain_body is not None:
                msg.body = plain_body
            elif html_body is not None:
                msg.body = msg.html2text(html_body)

            # Store the full raw RFC 2822 string
            msg.raw = raw_str

            # Extract received_date
            msg.received_date = msg._parse_received_date(parsed)

            # Extract attachments from the RFC 2822 MIME parts
            msg.attachments = msg._extract_attachments_from_mime(parsed)

            # Labels are passed in as a mapping; RFC 2822 source has no label IDs
            # so we leave msg.labels empty (caller can set them if needed)
            msg.labels = []
            msg.is_read = False
            msg.is_outgoing = False
            msg.size = len(raw_str.encode("utf-8"))

            return msg
        except MessageParsingError:
            raise
        except Exception as e:
            raise MessageParsingError(f"Failed to parse raw RFC 2822 message: {e}")

    def _parse_received_date(self, parsed_email) -> Optional[datetime]:
        """
        Extract received_date from the last Received: header, falling back
        to the last X-Received: header.

        Received headers are prepended by each hop, so the last one in the
        list is the final delivery server (closest to the recipient's mailbox).

        Header format example:
          Received: by 2002:a05:6214:2582:b0:88a:3657:d3e2 with SMTP id
                    fq2csp778250qvb; Sat, 31 Jan 2026 05:37:01 -0800 (PST)

        The date is the substring after the final semicolon (;).

        Args:
            parsed_email: A parsed email.message.Message object.

        Returns:
            Optional[datetime]: The parsed received date, or None.
        """
        for header_name in ("received", "x-received"):
            values = parsed_email.get_all(header_name) or []
            # get_all() returns in header order (top to bottom);
            # last element = last Received: = final delivery hop
            for value in reversed(values):
                if ";" in value:
                    date_str = value.rsplit(";", 1)[-1].strip()
                    try:
                        return parsedate_to_datetime(date_str)
                    except Exception:
                        logger.debug(
                            f"Could not parse date from {header_name}: {date_str!r}"
                        )
                        continue
        return None

    def parse_addresses(self, addresses: str) -> List[Dict[str, str]]:
        """
        Parse a comma-separated list of email addresses.

        Args:
            addresses (str): The comma-separated email addresses.

        Returns:
            List[Dict[str, str]]: List of parsed addresses with 'name' and 'email' keys.
        """
        parsed_addresses: List[Dict[str, str]] = []
        if not addresses:
            return parsed_addresses

        for address in addresses.split(","):
            name, email_addr = parseaddr(address.strip())
            if email_addr:
                parsed_addresses.append(
                    {"email": email_addr.lower(), "name": _decode_header(name).strip() if name else ""}
                )

        return parsed_addresses

    def decode_body(self, part: Dict) -> str:
        """
        Recursively decode the body of a message part.

        Args:
            part (Dict): The message part to decode.

        Returns:
            str: The decoded body text, or empty string if not found.
        """
        try:
            if "data" in part.get("body", {}):
                return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
            elif "parts" in part:
                for subpart in part["parts"]:
                    decoded_body = self.decode_body(subpart)
                    if decoded_body:
                        return decoded_body
        except Exception:
            # If decoding fails, return empty string
            pass

        return ""

    def html2text(self, html: str) -> str:
        """
        Convert HTML content to plain text.

        Args:
            html (str): The HTML content to convert.

        Returns:
            str: The plain text content.
        """
        if not html:
            return ""

        try:
            soup = BeautifulSoup(html, features="html.parser")
            text_content: str = soup.get_text()
            return text_content
        except Exception:
            # If HTML parsing fails, return the original text
            return html

    def parse(self, msg: Dict, labels: Dict[str, str]) -> None:
        """
        Parses a raw Gmail message and populates the Message object.

        Args:
            msg (Dict): The raw message data from Gmail API.
            labels (Dict[str, str]): Mapping of label IDs to label names.

        Raises:
            MessageParsingError: If critical message data cannot be parsed.
        """
        try:
            # Basic message info
            self.id = msg["id"]
            self.thread_id = msg["threadId"]
            self.size = msg.get("sizeEstimate", 0)

            # Parse timestamp - prefer internal date
            if "internalDate" in msg:
                internal_date_secs = int(msg["internalDate"]) / 1000
                self.timestamp = datetime.fromtimestamp(internal_date_secs)

            # Parse headers
            headers = msg.get("payload", {}).get("headers", [])
            for header in headers:
                name = header["name"].lower()
                value = header["value"]

                if name == "from":
                    addr = parseaddr(value)
                    self.sender = {"name": addr[0], "email": addr[1]}
                elif name == "to":
                    self.recipients["to"] = self.parse_addresses(value)
                elif name == "cc":
                    self.recipients["cc"] = self.parse_addresses(value)
                elif name == "bcc":
                    self.recipients["bcc"] = self.parse_addresses(value)
                elif name == "subject":
                    self.subject = value
                elif name == "date" and self.timestamp is None:
                    try:
                        self.timestamp = parsedate_to_datetime(value) if value else None
                    except Exception:
                        # If date parsing fails, leave timestamp as None
                        pass

            # Parse labels
            if "labelIds" in msg:
                for label_id in msg["labelIds"]:
                    if label_id in labels:
                        self.labels.append(labels[label_id])

                self.is_read = "UNREAD" not in msg["labelIds"]
                self.is_outgoing = "SENT" in msg["labelIds"]

            # Extract message body
            self._extract_body(msg.get("payload", {}))

        except Exception as e:
            raise MessageParsingError(
                f"Failed to parse message {msg.get('id', 'unknown')}: {e}"
            )

    def _extract_html_body(self, payload: Dict) -> Optional[str]:
        """
        Extract the raw HTML body from a message payload.

        Recursively walks the payload looking for a ``text/html`` part,
        decodes it from base64url, and returns the resulting string.
        Returns ``None`` when no HTML part is present or when decoding fails.

        Args:
            payload (Dict): The message payload from Gmail API.

        Returns:
            Optional[str]: The decoded HTML string, or ``None``.
        """
        try:
            mime_type = payload.get("mimeType", "")

            # Non-multipart payload — check if it's text/html directly
            if "parts" not in payload:
                if mime_type == "text/html":
                    data = payload.get("body", {}).get("data")
                    if data is not None:
                        return base64.urlsafe_b64decode(data).decode("utf-8")
                return None

            # Multipart payload — walk parts, recurse into nested multipart
            for part in payload["parts"]:
                part_mime = part.get("mimeType", "")
                if part_mime == "text/html":
                    data = part.get("body", {}).get("data")
                    if data is not None:
                        try:
                            return base64.urlsafe_b64decode(data).decode("utf-8")
                        except Exception:
                            return None
                elif part_mime.startswith("multipart/"):
                    # Recurse into nested multipart (e.g. multipart/alternative
                    # inside multipart/mixed)
                    result = self._extract_html_body(part)
                    if result is not None:
                        return result

        except Exception:
            pass

        return None

    def _extract_attachments_from_mime(self, parsed_email) -> List["Attachment"]:
        """
        Extract attachments from a parsed RFC 2822 email.message.Message object.

        Walks all MIME parts and collects non-body parts that have a filename
        or a Content-ID (inline images).  The binary data is NOT loaded here —
        it will be fetched from the Gmail API by _save_attachments_to_disk
        using the attachment_id.  We only need the metadata (filename,
        mime_type, content_id) plus the attachment_id so the downloader knows
        which Gmail API token to use.

        Note: RFC 2822 parts do not carry a Gmail attachment_id — that comes
        from the Gmail API JSON payload.  We set attachment_id to None here;
        _save_attachments_to_disk will match by filename when the id is absent.
        """
        attachments: List[Attachment] = []
        if not parsed_email.is_multipart():
            return attachments

        for part in parsed_email.walk():
            mime_type = part.get_content_type()
            # Skip body parts and multipart containers
            if mime_type in ("text/plain", "text/html") or mime_type.startswith("multipart/"):
                continue

            # Filename from Content-Disposition or Content-Type name param
            filename: Optional[str] = part.get_filename()
            if not filename:
                filename = part.get_param("name")
            if filename:
                filename = _decode_header(filename)

            # Content-ID for inline images (cid: references)
            content_id: Optional[str] = None
            raw_cid = part.get("Content-ID", "")
            if raw_cid:
                content_id = raw_cid.strip("<>")

            # Skip parts with neither a filename nor a content_id — nothing useful
            if not filename and not content_id:
                continue

            size: int = 0
            payload = part.get_payload(decode=True)
            if payload:
                size = len(payload)

            attachments.append(
                Attachment(
                    filename=filename,
                    mime_type=mime_type,
                    size=size,
                    data=None,          # fetched on demand from Gmail API
                    attachment_id=None, # not available from RFC 2822; matched by filename
                    content_id=content_id,
                )
            )

        return attachments

    def _extract_attachments(self, payload: Dict) -> List[Attachment]:
        """
        Walk a multipart payload and extract attachment parts.

        Skips ``text/plain`` and ``text/html`` parts (body parts).  For every
        remaining part, extracts filename, mime_type, size, data, and
        attachment_id.  Non-multipart payloads return an empty list.  Any
        per-part decoding failure sets ``data = None`` for that part and
        continues without propagating the exception.

        Args:
            payload (Dict): The message payload from Gmail API.

        Returns:
            List[Attachment]: Extracted attachment objects.
        """
        if "parts" not in payload:
            return []

        attachments: List[Attachment] = []
        for part in payload["parts"]:
            mime_type = part.get("mimeType", "")
            if mime_type in ("text/plain", "text/html"):
                continue

            # --- filename extraction (task 10.4) ---
            filename: Optional[str] = None
            headers = part.get("headers", [])

            # Build a lookup dict for quick access
            header_map: Dict[str, str] = {}
            for h in headers:
                header_map[h["name"].lower()] = h["value"]

            # Try Content-Disposition filename parameter first
            content_disposition = header_map.get("content-disposition", "")
            if content_disposition:
                msg = email.message.Message()
                msg["Content-Disposition"] = content_disposition
                filename = msg.get_param("filename", header="content-disposition")

            # Fall back to Content-Type name parameter
            if filename is None:
                content_type = header_map.get("content-type", "")
                if content_type:
                    msg = email.message.Message()
                    msg["Content-Type"] = content_type
                    filename = msg.get_param("name")

            # --- size ---
            size: int = part.get("body", {}).get("size", 0)

            # --- data decoding (task 10.5) ---
            data: Optional[bytes] = None
            raw_data = part.get("body", {}).get("data")
            if raw_data is not None:
                try:
                    data = base64.urlsafe_b64decode(raw_data)
                except Exception:
                    data = None

            # --- attachment_id (task 10.6) ---
            attachment_id: Optional[str] = part.get("body", {}).get("attachmentId")

            # --- content_id (for cid: inline image resolution) ---
            content_id: Optional[str] = None
            raw_cid = header_map.get("content-id", "")
            if raw_cid:
                # Strip angle brackets: <ii_abc123> → ii_abc123
                content_id = raw_cid.strip("<>")

            attachments.append(
                Attachment(
                    filename=filename,
                    mime_type=mime_type,
                    size=size,
                    data=data,
                    attachment_id=attachment_id,
                    content_id=content_id,
                )
            )

        return attachments

    def _extract_body(self, payload: Dict) -> None:
        """
        Extract the body text from message payload.

        Args:
            payload (Dict): The message payload from Gmail API.
        """
        # Extract raw HTML body (sub-task 1.3)
        self.body_html = self._extract_html_body(payload)

        # For non-multipart messages
        if "body" in payload and "data" in payload["body"]:
            try:
                self.body = base64.urlsafe_b64decode(payload["body"]["data"]).decode(
                    "utf-8"
                )
                self.body = self.html2text(self.body)
                return
            except Exception:
                pass

        # For multipart messages
        if "parts" in payload and self.body is None:
            for part in payload["parts"]:
                mime_type = part.get("mimeType", "")
                if mime_type in SUPPORTED_MIME_TYPES:
                    body_text = self.decode_body(part)
                    if body_text:
                        self.body = self.html2text(body_text)
                        break

        # Extract attachments from the payload (task 10.7)
        self.attachments = self._extract_attachments(payload)


# ---------------------------------------------------------------------------
# Module-level helper functions
# ---------------------------------------------------------------------------


def _strip_to_html_tag(html: Optional[str]) -> Optional[str]:
    """
    If html contains '<html', return the substring from '<html' onward.
    Otherwise return html unchanged. Returns None for None/empty input.

    Args:
        html (Optional[str]): The HTML string to process.

    Returns:
        Optional[str]: The stripped HTML string, or None.
    """
    if not html:
        return None
    idx = html.find("<html")
    if idx != -1:
        return html[idx:]
    return html


def extract_attachment_from_raw(raw: Optional[str], filename: str) -> Optional[bytes]:
    """
    Extract a named attachment's decoded bytes from a stored RFC 2822 string.

    Walks all MIME parts looking for one whose filename (from Content-Disposition
    or Content-Type name param) matches *filename*.  Returns the decoded payload
    bytes, or None if not found or if decoding fails.

    Args:
        raw (Optional[str]): The decoded RFC 2822 email string stored in the DB.
        filename (str): The attachment filename to look for.

    Returns:
        Optional[bytes]: The decoded attachment bytes, or None.
    """
    if not raw or not filename:
        return None

    try:
        parsed = email.message_from_string(raw)
        for part in parsed.walk():
            mime_type = part.get_content_type()
            if mime_type in ("text/plain", "text/html") or mime_type.startswith("multipart/"):
                continue

            part_filename = part.get_filename()
            if not part_filename:
                part_filename = part.get_param("name")
            if part_filename:
                part_filename = _decode_header(part_filename)

            if part_filename == filename:
                data = part.get_payload(decode=True)
                return data if data else None
    except Exception:
        pass

    return None


def extract_attachment_by_content_id(raw: Optional[str], content_id: str) -> Optional[bytes]:
    """
    Extract an inline attachment's decoded bytes by Content-ID from a stored RFC 2822 string.

    Args:
        raw (Optional[str]): The decoded RFC 2822 email string stored in the DB.
        content_id (str): The Content-ID value (with or without angle brackets).

    Returns:
        Optional[bytes]: The decoded attachment bytes, or None.
    """
    if not raw or not content_id:
        return None

    # Normalise — strip angle brackets if present
    cid_bare = content_id.strip("<>")

    try:
        parsed = email.message_from_string(raw)
        for part in parsed.walk():
            raw_cid = part.get("Content-ID", "")
            if raw_cid.strip("<>") == cid_bare:
                data = part.get_payload(decode=True)
                return data if data else None
    except Exception:
        pass

    return None


def extract_html_from_raw(raw: Optional[str]) -> Optional[str]:
    """
    Extract the text/html MIME part from a decoded RFC 2822 string.

    Returns None if raw is None/empty or no text/html part exists.
    Applies _strip_to_html_tag to the extracted HTML before returning.

    Args:
        raw (Optional[str]): The decoded RFC 2822 email string.

    Returns:
        Optional[str]: The extracted HTML string, or None.
    """
    if not raw:
        return None

    try:
        parsed = email.message_from_string(raw)

        if parsed.is_multipart():
            for part in parsed.walk():
                if part.get_content_type() == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload is not None:
                        charset = part.get_content_charset() or "utf-8"
                        html = payload.decode(charset, errors="replace")
                        return _strip_to_html_tag(html)
        else:
            if parsed.get_content_type() == "text/html":
                payload = parsed.get_payload(decode=True)
                if payload is not None:
                    charset = parsed.get_content_charset() or "utf-8"
                    html = payload.decode(charset, errors="replace")
                    return _strip_to_html_tag(html)

    except Exception:
        pass

    return None
