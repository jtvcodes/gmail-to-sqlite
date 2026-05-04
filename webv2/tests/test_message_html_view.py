"""Example-based unit tests for message-html-view feature.

Tests the content-selection helper (select_content) and toggle visibility
helper (show_toggle) for all relevant combinations of body_html/body
nullability and view states.

Requirements: 1.2, 1.3, 3.1, 3.2, 3.3
"""

from web.tests.test_message_html_view_properties import select_content, show_toggle


# ---------------------------------------------------------------------------
# Content-selection tests — 8 cases
# (4 combinations of body_html/body nullability × 2 view states)
# ---------------------------------------------------------------------------


class TestSelectContent:
    """Tests for the content-selection logic mirroring renderBody() in messageDetail.js."""

    # --- view="html" cases ---

    def test_html_view_with_body_html_and_body_returns_body_html(self):
        """Case 1: view="html", body_html non-empty, body non-empty → returns body_html.

        Validates: Requirements 1.2
        """
        result = select_content(body_html="<b>html</b>", body="plain", view="html")
        assert result == "<b>html</b>"

    def test_html_view_with_none_body_html_falls_back_to_body(self):
        """Case 2: view="html", body_html=None, body non-empty → falls back to body.

        Validates: Requirements 1.3
        """
        result = select_content(body_html=None, body="plain", view="html")
        assert result == "plain"

    def test_html_view_with_empty_body_html_falls_back_to_body(self):
        """Case 3: view="html", body_html="" (empty string), body non-empty → falls back to body.

        Validates: Requirements 1.3
        """
        result = select_content(body_html="", body="plain", view="html")
        assert result == "plain"

    def test_html_view_with_body_html_and_none_body_returns_body_html(self):
        """Case 4: view="html", body_html non-empty, body=None → returns body_html.

        Validates: Requirements 1.2
        """
        result = select_content(body_html="<b>html</b>", body=None, view="html")
        assert result == "<b>html</b>"

    # --- view="text" cases ---

    def test_text_view_with_both_fields_returns_body(self):
        """Case 5: view="text", body_html non-empty, body non-empty → returns body.

        Validates: Requirements 1.3, 2.4
        """
        result = select_content(body_html="<b>html</b>", body="plain", view="text")
        assert result == "plain"

    def test_text_view_with_none_body_html_returns_body(self):
        """Case 6: view="text", body_html=None, body non-empty → returns body.

        Validates: Requirements 2.4
        """
        result = select_content(body_html=None, body="plain", view="text")
        assert result == "plain"

    def test_text_view_with_none_body_returns_none(self):
        """Case 7: view="text", body_html non-empty, body=None → returns None.

        Validates: Requirements 2.4
        """
        result = select_content(body_html="<b>html</b>", body=None, view="text")
        assert result is None

    def test_text_view_with_empty_body_returns_empty_string(self):
        """Case 8: view="text", body_html="" (empty), body="" (empty) → returns "" (body).

        Validates: Requirements 2.4
        """
        result = select_content(body_html="", body="", view="text")
        assert result == ""


# ---------------------------------------------------------------------------
# Toggle visibility tests — 4 cases
# ---------------------------------------------------------------------------


class TestShowToggle:
    """Tests for the toggle visibility logic mirroring buildToggleButton() in messageDetail.js."""

    def test_both_non_empty_shows_toggle(self):
        """Both body_html and body are non-empty → show_toggle returns True.

        Validates: Requirements 3.1
        """
        assert show_toggle(body_html="<b>html</b>", body="plain") is True

    def test_empty_body_html_hides_toggle(self):
        """body_html is empty/None, body is non-empty → show_toggle returns False.

        Validates: Requirements 3.2
        """
        assert show_toggle(body_html=None, body="plain") is False
        assert show_toggle(body_html="", body="plain") is False

    def test_empty_body_hides_toggle(self):
        """body_html is non-empty, body is empty/None → show_toggle returns False.

        Validates: Requirements 3.3
        """
        assert show_toggle(body_html="<b>html</b>", body=None) is False
        assert show_toggle(body_html="<b>html</b>", body="") is False

    def test_both_empty_hides_toggle(self):
        """Both body_html and body are empty/None → show_toggle returns False.

        Validates: Requirements 3.2, 3.3
        """
        assert show_toggle(body_html=None, body=None) is False
        assert show_toggle(body_html="", body="") is False
        assert show_toggle(body_html=None, body="") is False
        assert show_toggle(body_html="", body=None) is False
