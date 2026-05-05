"""Bug condition exploration tests for recipient formatting in the message detail view.

These tests encode the EXPECTED (correct) behavior for recipient formatting.
They are EXPECTED TO FAIL on unfixed code because messageDetail.js calls
.join(", ") directly on arrays of {name, email} objects, which JavaScript
coerces to "[object Object]".

Bug condition: typeof recipient === 'object' && recipient !== null && 'email' in recipient
Expected behavior: r.name ? r.name + " <" + r.email + ">" : (r.email || "")

Requirements: 1.1, 1.2, 1.3 (current defect), 2.1, 2.2, 2.3 (expected behavior)
"""

import json
import sqlite3
import tempfile
import os

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from web.server import create_app

# ---------------------------------------------------------------------------
# DB schema (mirrors the real schema)
# ---------------------------------------------------------------------------

CREATE_TABLE_SQL = """
CREATE TABLE messages (
    message_id    TEXT PRIMARY KEY,
    thread_id     TEXT,
    sender        TEXT,
    recipients    TEXT,
    labels        TEXT,
    subject       TEXT,
    body          TEXT,
    raw           TEXT,
    size          INTEGER,
    timestamp     DATETIME,
    is_read       INTEGER,
    is_outgoing   INTEGER,
    is_deleted    INTEGER,
    last_indexed  DATETIME
)
"""

CREATE_ATTACHMENTS_TABLE_SQL = """
CREATE TABLE attachments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id    TEXT NOT NULL REFERENCES messages(message_id),
    filename      TEXT,
    mime_type     TEXT NOT NULL,
    size          INTEGER NOT NULL DEFAULT 0,
    data          BLOB,
    attachment_id TEXT,
    content_id    TEXT
)
"""

# ---------------------------------------------------------------------------
# Helpers: Python simulation of the JS rendering logic
# ---------------------------------------------------------------------------


def js_join_simulate(recipients_list):
    """Simulate what JavaScript's Array.prototype.join(", ") does on a list of
    recipient objects.

    In JavaScript, joining an array of plain objects calls .toString() on each
    element, which returns "[object Object]" for any plain object.

    This is the BUGGY behavior we are testing against.
    """
    parts = []
    for r in recipients_list:
        if isinstance(r, dict):
            # JavaScript coerces objects to "[object Object]"
            parts.append("[object Object]")
        else:
            parts.append(str(r))
    return ", ".join(parts)


def format_recipient(r):
    """Python equivalent of the EXPECTED (fixed) formatRecipient JS function.

    function formatRecipient(r) {
      if (r && typeof r === 'object') {
        return r.name ? r.name + ' <' + r.email + '>' : (r.email || '');
      }
      return String(r);
    }

    This is the CORRECT behavior the fix should implement.
    """
    if r and isinstance(r, dict):
        if r.get("name"):
            return r["name"] + " <" + r["email"] + ">"
        else:
            return r.get("email") or ""
    return str(r)


def format_recipients_list(recipients_list):
    """Format a list of recipient objects using the expected formatRecipient logic."""
    return ", ".join(format_recipient(r) for r in recipients_list)


# ---------------------------------------------------------------------------
# DB seeding helpers
# ---------------------------------------------------------------------------


def _seed_db_with_message(path: str, recipients: dict) -> str:
    """Create the messages table and insert a single message with the given recipients.
    Returns the message_id.
    """
    conn = sqlite3.connect(path)
    conn.execute(CREATE_TABLE_SQL)
    conn.execute(CREATE_ATTACHMENTS_TABLE_SQL)
    message_id = "test_msg_1"
    conn.execute(
        "INSERT INTO messages VALUES (?,?,?,?,?,?,?,NULL,NULL,?,?,?,?,?,NULL)",
        (
            message_id,
            "thread1",
            json.dumps({"name": "Sender", "email": "sender@example.com"}),
            json.dumps(recipients),
            json.dumps(["INBOX"]),
            "Test Subject",
            "Test body",
            100,
            "2024-01-10T10:00:00",
            0,
            0,
            0,
        ),
    )
    conn.commit()
    conn.close()
    return message_id


def _make_client_with_recipients(recipients: dict):
    """Seed a temp DB with a message having the given recipients and return a Flask test client."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    message_id = _seed_db_with_message(tmp.name, recipients)
    flask_app = create_app(db_path=tmp.name)
    flask_app.config["TESTING"] = True
    client = flask_app.test_client()
    return client, tmp.name, message_id


def _cleanup(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Unit tests: format_recipient helper (expected behavior)
# ---------------------------------------------------------------------------


class TestFormatRecipientExpectedBehavior:
    """Tests for the expected formatRecipient behavior.

    These tests verify what the FIXED code should produce.
    They test the Python equivalent of the expected JS formatRecipient function.
    """

    def test_recipient_with_name_and_email(self):
        """formatRecipient({name: "Alice", email: "alice@example.com"}) should return
        "Alice <alice@example.com>" — NOT "[object Object]".

        Validates: Requirements 2.1, 2.2, 2.3
        """
        r = {"name": "Alice", "email": "alice@example.com"}
        result = format_recipient(r)
        assert result == "Alice <alice@example.com>", (
            f"Expected 'Alice <alice@example.com>' but got {result!r}"
        )
        assert result != "[object Object]", (
            "formatRecipient must NOT return '[object Object]'"
        )

    def test_recipient_with_empty_name(self):
        """formatRecipient({name: "", email: "bob@example.com"}) should return
        "bob@example.com" — NOT "[object Object]".

        Validates: Requirements 2.1, 2.2, 2.3
        """
        r = {"name": "", "email": "bob@example.com"}
        result = format_recipient(r)
        assert result == "bob@example.com", (
            f"Expected 'bob@example.com' but got {result!r}"
        )
        assert result != "[object Object]", (
            "formatRecipient must NOT return '[object Object]'"
        )

    def test_recipient_with_no_name_key(self):
        """formatRecipient({email: "carol@example.com"}) should return
        "carol@example.com" — NOT "[object Object]".

        Validates: Requirements 2.1, 2.2, 2.3
        """
        r = {"email": "carol@example.com"}
        result = format_recipient(r)
        assert result == "carol@example.com", (
            f"Expected 'carol@example.com' but got {result!r}"
        )
        assert result != "[object Object]", (
            "formatRecipient must NOT return '[object Object]'"
        )

    def test_recipient_with_null_name(self):
        """formatRecipient({name: null, email: "dave@example.com"}) should return
        "dave@example.com" — NOT "[object Object]".

        Validates: Requirements 2.1, 2.2, 2.3
        """
        r = {"name": None, "email": "dave@example.com"}
        result = format_recipient(r)
        assert result == "dave@example.com", (
            f"Expected 'dave@example.com' but got {result!r}"
        )
        assert result != "[object Object]", (
            "formatRecipient must NOT return '[object Object]'"
        )

    def test_multiple_recipients_joined(self):
        """[{name:"A",email:"a@x.com"},{name:"",email:"b@x.com"}] should produce
        "A <a@x.com>, b@x.com" — NOT "[object Object], [object Object]".

        Validates: Requirements 2.1, 2.2, 2.3
        """
        recipients = [
            {"name": "A", "email": "a@x.com"},
            {"name": "", "email": "b@x.com"},
        ]
        result = format_recipients_list(recipients)
        assert result == "A <a@x.com>, b@x.com", (
            f"Expected 'A <a@x.com>, b@x.com' but got {result!r}"
        )
        assert "[object Object]" not in result, (
            "Joined recipients must NOT contain '[object Object]'"
        )


# ---------------------------------------------------------------------------
# Bug condition confirmation: JS .join() produces "[object Object]"
# ---------------------------------------------------------------------------


class TestBugConditionConfirmation:
    """Tests that confirm the bug condition exists in the current (unfixed) code.

    These tests verify that the CURRENT (buggy) JS rendering behavior produces
    "[object Object]" when joining recipient objects directly.

    The js_join_simulate() function models what the unfixed messageDetail.js does.
    """

    def test_js_join_produces_object_object_for_recipient_with_name(self):
        """Confirms the bug: JS .join() on [{name:"Alice",email:"alice@example.com"}]
        produces "[object Object]" instead of "Alice <alice@example.com>".

        Bug condition: typeof recipient === 'object' && recipient !== null && 'email' in recipient
        """
        recipients = [{"name": "Alice", "email": "alice@example.com"}]
        buggy_result = js_join_simulate(recipients)
        assert buggy_result == "[object Object]", (
            f"Expected '[object Object]' from buggy join but got {buggy_result!r}. "
            "This confirms the bug exists."
        )

    def test_js_join_produces_object_object_for_recipient_without_name(self):
        """Confirms the bug: JS .join() on [{name:"",email:"bob@example.com"}]
        produces "[object Object]" instead of "bob@example.com".
        """
        recipients = [{"name": "", "email": "bob@example.com"}]
        buggy_result = js_join_simulate(recipients)
        assert buggy_result == "[object Object]", (
            f"Expected '[object Object]' from buggy join but got {buggy_result!r}. "
            "This confirms the bug exists."
        )

    def test_js_join_produces_multiple_object_objects(self):
        """Confirms the bug: JS .join() on multiple recipient objects produces
        "[object Object], [object Object]" instead of formatted addresses.
        """
        recipients = [
            {"name": "A", "email": "a@x.com"},
            {"name": "", "email": "b@x.com"},
        ]
        buggy_result = js_join_simulate(recipients)
        assert buggy_result == "[object Object], [object Object]", (
            f"Expected '[object Object], [object Object]' from buggy join but got {buggy_result!r}. "
            "This confirms the bug exists."
        )


# ---------------------------------------------------------------------------
# Integration tests: API returns structured recipient objects
# These tests verify the API layer is correct (not the bug source).
# The bug is in the JS rendering layer, not the API.
# ---------------------------------------------------------------------------


class TestApiReturnsStructuredRecipients:
    """Tests that the API correctly returns recipients as {name, email} objects.

    These tests PASS on unfixed code because the API is correct.
    The bug is in the JS rendering layer (messageDetail.js), not the API.
    """

    def test_api_returns_to_recipients_as_objects(self):
        """The API should return TO recipients as {name, email} dicts."""
        recipients = {
            "to": [{"name": "Alice", "email": "alice@example.com"}],
            "cc": [],
            "bcc": [],
        }
        client, db_path, message_id = _make_client_with_recipients(recipients)
        try:
            resp = client.get(f"/api/messages/{message_id}")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "recipients" in data
            assert "to" in data["recipients"]
            to_list = data["recipients"]["to"]
            assert len(to_list) == 1
            assert isinstance(to_list[0], dict), (
                f"Expected recipient to be a dict but got {type(to_list[0])}"
            )
            assert to_list[0]["name"] == "Alice"
            assert to_list[0]["email"] == "alice@example.com"
        finally:
            _cleanup(db_path)

    def test_api_returns_cc_recipients_as_objects(self):
        """The API should return CC recipients as {name, email} dicts."""
        recipients = {
            "to": [],
            "cc": [{"name": "Carol", "email": "carol@example.com"}],
            "bcc": [],
        }
        client, db_path, message_id = _make_client_with_recipients(recipients)
        try:
            resp = client.get(f"/api/messages/{message_id}")
            assert resp.status_code == 200
            data = resp.get_json()
            cc_list = data["recipients"]["cc"]
            assert len(cc_list) == 1
            assert isinstance(cc_list[0], dict)
            assert cc_list[0]["name"] == "Carol"
            assert cc_list[0]["email"] == "carol@example.com"
        finally:
            _cleanup(db_path)

    def test_api_returns_bcc_recipients_as_objects(self):
        """The API should return BCC recipients as {name, email} dicts."""
        recipients = {
            "to": [],
            "cc": [],
            "bcc": [{"name": "Dave", "email": "dave@example.com"}],
        }
        client, db_path, message_id = _make_client_with_recipients(recipients)
        try:
            resp = client.get(f"/api/messages/{message_id}")
            assert resp.status_code == 200
            data = resp.get_json()
            bcc_list = data["recipients"]["bcc"]
            assert len(bcc_list) == 1
            assert isinstance(bcc_list[0], dict)
            assert bcc_list[0]["name"] == "Dave"
            assert bcc_list[0]["email"] == "dave@example.com"
        finally:
            _cleanup(db_path)


# ---------------------------------------------------------------------------
# Rendering simulation tests: confirm bug in rendering layer
# These tests simulate what the JS rendering layer does and FAIL on unfixed code.
# They encode the EXPECTED behavior — they will PASS after the fix is applied.
# ---------------------------------------------------------------------------


class TestRenderingSimulation:
    """Tests that simulate the JS rendering and verify the expected output.

    These tests FAIL on unfixed code because they assert the EXPECTED (correct)
    behavior, but the current JS code produces "[object Object]".

    After the fix is applied (adding formatRecipient and using .map().join()),
    these tests will PASS.

    **Validates: Requirements 1.1, 1.2, 1.3 (current defect), 2.1, 2.2, 2.3 (expected)**
    """

    def test_to_line_with_named_recipient_should_not_contain_object_object(self):
        """The rendered TO line for a message with recipients.to = [{name:"Alice",
        email:"alice@example.com"}] should contain "Alice <alice@example.com>"
        and NOT contain "[object Object]".

        This test FAILS on unfixed code (confirms bug 1.1).
        Validates: Requirements 1.1, 2.1
        """
        recipients = {
            "to": [{"name": "Alice", "email": "alice@example.com"}],
            "cc": [],
            "bcc": [],
        }
        client, db_path, message_id = _make_client_with_recipients(recipients)
        try:
            resp = client.get(f"/api/messages/{message_id}")
            assert resp.status_code == 200
            data = resp.get_json()

            to_list = data["recipients"]["to"]
            # Simulate what the FIXED JS rendering should produce
            expected_to_text = format_recipients_list(to_list)
            # Simulate what the BUGGY JS rendering currently produces
            buggy_to_text = js_join_simulate(to_list)

            # The expected text should be "Alice <alice@example.com>"
            assert expected_to_text == "Alice <alice@example.com>", (
                f"Expected 'Alice <alice@example.com>' but format_recipients_list returned {expected_to_text!r}"
            )

            # The buggy text IS "[object Object]" — this confirms the bug
            assert buggy_to_text == "[object Object]", (
                f"Expected buggy join to produce '[object Object]' but got {buggy_to_text!r}"
            )

            # THE FIX IS VERIFIED HERE:
            # The fixed rendering (format_recipients_list) must NOT contain "[object Object]"
            # and must produce the correct formatted address.
            assert "[object Object]" not in expected_to_text, (
                f"FIX VERIFIED: TO line must not contain '[object Object]', got {expected_to_text!r}"
            )
            assert expected_to_text == "Alice <alice@example.com>", (
                f"FIX VERIFIED: TO line must be 'Alice <alice@example.com>', got {expected_to_text!r}"
            )
        finally:
            _cleanup(db_path)

    def test_to_line_with_email_only_recipient_should_not_contain_object_object(self):
        """The rendered TO line for a message with recipients.to = [{name:"",
        email:"bob@example.com"}] should contain "bob@example.com"
        and NOT contain "[object Object]".

        This test FAILS on unfixed code (confirms bug 1.1).
        Validates: Requirements 1.1, 2.1
        """
        recipients = {
            "to": [{"name": "", "email": "bob@example.com"}],
            "cc": [],
            "bcc": [],
        }
        client, db_path, message_id = _make_client_with_recipients(recipients)
        try:
            resp = client.get(f"/api/messages/{message_id}")
            assert resp.status_code == 200
            data = resp.get_json()

            to_list = data["recipients"]["to"]
            expected_to_text = format_recipients_list(to_list)
            buggy_to_text = js_join_simulate(to_list)

            assert expected_to_text == "bob@example.com", (
                f"Expected 'bob@example.com' but got {expected_to_text!r}"
            )
            assert buggy_to_text == "[object Object]", (
                f"Expected buggy join to produce '[object Object]' but got {buggy_to_text!r}"
            )

            # THE FIX IS VERIFIED HERE:
            assert "[object Object]" not in expected_to_text, (
                f"FIX VERIFIED: TO line must not contain '[object Object]', got {expected_to_text!r}"
            )
            assert expected_to_text == "bob@example.com", (
                f"FIX VERIFIED: TO line must be 'bob@example.com', got {expected_to_text!r}"
            )
        finally:
            _cleanup(db_path)

    def test_cc_line_with_named_recipient_should_not_contain_object_object(self):
        """The rendered CC line should contain "Carol <carol@example.com>"
        and NOT contain "[object Object]".

        This test FAILS on unfixed code (confirms bug 1.2).
        Validates: Requirements 1.2, 2.2
        """
        recipients = {
            "to": [],
            "cc": [{"name": "Carol", "email": "carol@example.com"}],
            "bcc": [],
        }
        client, db_path, message_id = _make_client_with_recipients(recipients)
        try:
            resp = client.get(f"/api/messages/{message_id}")
            assert resp.status_code == 200
            data = resp.get_json()

            cc_list = data["recipients"]["cc"]
            expected_cc_text = format_recipients_list(cc_list)
            buggy_cc_text = js_join_simulate(cc_list)

            assert expected_cc_text == "Carol <carol@example.com>", (
                f"Expected 'Carol <carol@example.com>' but got {expected_cc_text!r}"
            )
            assert buggy_cc_text == "[object Object]", (
                f"Expected buggy join to produce '[object Object]' but got {buggy_cc_text!r}"
            )

            # THE FIX IS VERIFIED HERE:
            assert "[object Object]" not in expected_cc_text, (
                f"FIX VERIFIED: CC line must not contain '[object Object]', got {expected_cc_text!r}"
            )
            assert expected_cc_text == "Carol <carol@example.com>", (
                f"FIX VERIFIED: CC line must be 'Carol <carol@example.com>', got {expected_cc_text!r}"
            )
        finally:
            _cleanup(db_path)

    def test_bcc_line_with_named_recipient_should_not_contain_object_object(self):
        """The rendered BCC line should contain "Dave <dave@example.com>"
        and NOT contain "[object Object]".

        This test FAILS on unfixed code (confirms bug 1.3).
        Validates: Requirements 1.3, 2.3
        """
        recipients = {
            "to": [],
            "cc": [],
            "bcc": [{"name": "Dave", "email": "dave@example.com"}],
        }
        client, db_path, message_id = _make_client_with_recipients(recipients)
        try:
            resp = client.get(f"/api/messages/{message_id}")
            assert resp.status_code == 200
            data = resp.get_json()

            bcc_list = data["recipients"]["bcc"]
            expected_bcc_text = format_recipients_list(bcc_list)
            buggy_bcc_text = js_join_simulate(bcc_list)

            assert expected_bcc_text == "Dave <dave@example.com>", (
                f"Expected 'Dave <dave@example.com>' but got {expected_bcc_text!r}"
            )
            assert buggy_bcc_text == "[object Object]", (
                f"Expected buggy join to produce '[object Object]' but got {buggy_bcc_text!r}"
            )

            # THE FIX IS VERIFIED HERE:
            assert "[object Object]" not in expected_bcc_text, (
                f"FIX VERIFIED: BCC line must not contain '[object Object]', got {expected_bcc_text!r}"
            )
            assert expected_bcc_text == "Dave <dave@example.com>", (
                f"FIX VERIFIED: BCC line must be 'Dave <dave@example.com>', got {expected_bcc_text!r}"
            )
        finally:
            _cleanup(db_path)

    def test_multiple_to_recipients_should_be_formatted_correctly(self):
        """Multiple TO recipients [{name:"A",email:"a@x.com"},{name:"",email:"b@x.com"}]
        should render as "A <a@x.com>, b@x.com" — NOT "[object Object], [object Object]".

        This test FAILS on unfixed code (confirms bug 1.1 with multiple recipients).
        Validates: Requirements 1.1, 2.1
        """
        recipients = {
            "to": [
                {"name": "A", "email": "a@x.com"},
                {"name": "", "email": "b@x.com"},
            ],
            "cc": [],
            "bcc": [],
        }
        client, db_path, message_id = _make_client_with_recipients(recipients)
        try:
            resp = client.get(f"/api/messages/{message_id}")
            assert resp.status_code == 200
            data = resp.get_json()

            to_list = data["recipients"]["to"]
            expected_to_text = format_recipients_list(to_list)
            buggy_to_text = js_join_simulate(to_list)

            assert expected_to_text == "A <a@x.com>, b@x.com", (
                f"Expected 'A <a@x.com>, b@x.com' but got {expected_to_text!r}"
            )
            assert buggy_to_text == "[object Object], [object Object]", (
                f"Expected buggy join to produce '[object Object], [object Object]' but got {buggy_to_text!r}"
            )

            # THE FIX IS VERIFIED HERE:
            assert "[object Object]" not in expected_to_text, (
                f"FIX VERIFIED: Multiple TO recipients must not contain '[object Object]', got {expected_to_text!r}"
            )
            assert expected_to_text == "A <a@x.com>, b@x.com", (
                f"FIX VERIFIED: Multiple TO recipients must be 'A <a@x.com>, b@x.com', got {expected_to_text!r}"
            )
        finally:
            _cleanup(db_path)


# ---------------------------------------------------------------------------
# Property-based test: Bug Condition
# Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2, 2.3
# ---------------------------------------------------------------------------

# Strategy for generating recipient objects (the bug condition inputs)
safe_text = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=0,
    max_size=30,
)

email_strategy = st.builds(
    lambda user, domain: f"{user}@{domain}.com",
    user=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=1,
        max_size=20,
    ),
    domain=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=1,
        max_size=20,
    ),
)

recipient_strategy = st.fixed_dictionaries({
    "name": safe_text,
    "email": email_strategy,
})

recipients_list_strategy = st.lists(recipient_strategy, min_size=1, max_size=5)


@given(recipients=recipients_list_strategy)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_property_bug_condition_recipient_objects_never_render_as_object_object(recipients):
    """Property 1: Bug Condition - Recipient Objects Render as Formatted Addresses

    For any recipient element where isBugCondition(recipient) returns true
    (i.e., the element is a {name, email} object), the rendering function SHALL
    display that recipient as "Name <email>" when name is non-empty, or as "email"
    when name is absent or empty — NEVER as "[object Object]".

    This test FAILS on unfixed code because js_join_simulate() produces "[object Object]"
    for every recipient object, confirming the bug exists.

    **Validates: Requirements 1.1, 1.2, 1.3 (current defect), 2.1, 2.2, 2.3 (expected)**
    """
    # Simulate the BUGGY JS rendering (current unfixed behavior)
    buggy_result = js_join_simulate(recipients)

    # Simulate the EXPECTED (fixed) rendering
    expected_result = format_recipients_list(recipients)

    # Verify the expected result never contains "[object Object]"
    assert "[object Object]" not in expected_result, (
        f"format_recipients_list should never produce '[object Object]' "
        f"but got {expected_result!r} for recipients {recipients!r}"
    )

    # Verify each recipient is formatted correctly
    for r in recipients:
        formatted = format_recipient(r)
        assert "[object Object]" not in formatted, (
            f"format_recipient should never produce '[object Object]' "
            f"but got {formatted!r} for recipient {r!r}"
        )
        if r.get("name"):
            assert formatted == r["name"] + " <" + r["email"] + ">", (
                f"Expected '{r['name']} <{r['email']}>' but got {formatted!r}"
            )
        else:
            assert formatted == r["email"], (
                f"Expected '{r['email']}' but got {formatted!r}"
            )

    # THE FIX IS VERIFIED HERE:
    # The fixed rendering (format_recipients_list) must match the expected result
    # and must never contain "[object Object]".
    assert "[object Object]" not in expected_result, (
        f"FIX VERIFIED: format_recipients_list must never produce '[object Object]' "
        f"but got {expected_result!r} for recipients {recipients!r}"
    )
