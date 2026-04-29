import base64
import email.message
from dataclasses import dataclass
from datetime import datetime
from email.utils import parseaddr, parsedate_to_datetime
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from .constants import SUPPORTED_MIME_TYPES


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
            name, email = parseaddr(address.strip())
            if email:
                parsed_addresses.append(
                    {"email": email.lower(), "name": name.strip() if name else ""}
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
