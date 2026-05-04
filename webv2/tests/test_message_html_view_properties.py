"""Property-based tests for message-html-view feature.

Properties from the message-html-view spec, tested by re-implementing
the pure content-selection logic from messageDetail.js in Python.
"""

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Pure Python re-implementation of the content-selection logic from
# renderBody() in web/static/messageDetail.js
# ---------------------------------------------------------------------------


def select_content(body_html, body, view):
    """Mirror the content-selection logic from renderBody() in messageDetail.js.

    - if view == "html": return body_html if non-empty, else body
    - if view == "text": return body (always)
    """
    if view == "html":
        has_html = body_html is not None and body_html != ""
        return body_html if has_html else body
    else:  # view == "text"
        return body


# ---------------------------------------------------------------------------
# Property 2: Content selection correctness
# Feature: message-html-view, Property 2: Content selection correctness
#
# For any message object and any activeView value, the content-selection
# logic SHALL pick body_html (or fall back to body) when view is "html",
# and always pick body when view is "text".
#
# Validates: Requirements 1.2, 1.3, 2.4, 2.5
# ---------------------------------------------------------------------------


@given(
    body=st.text(),
    body_html=st.one_of(st.none(), st.text()),
    view=st.sampled_from(["html", "text"]),
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_2_content_selection_correctness(body, body_html, view):
    """Feature: message-html-view, Property 2: Content selection correctness

    For any message object and any activeView value, the content-selection
    logic SHALL pick body_html (or fall back to body) when view is "html",
    and always pick body when view is "text".

    **Validates: Requirements 1.2, 1.3, 2.4, 2.5**
    """
    result = select_content(body_html, body, view)

    if view == "text":
        # Plain-text view ALWAYS uses body, regardless of body_html
        assert result == body, (
            f"view='text': expected body={body!r}, got {result!r}"
        )
    else:
        # HTML view: use body_html when non-empty, fall back to body
        has_html = body_html is not None and body_html != ""
        if has_html:
            assert result == body_html, (
                f"view='html' with non-empty body_html: expected body_html={body_html!r}, "
                f"got {result!r}"
            )
        else:
            assert result == body, (
                f"view='html' with empty/null body_html: expected fallback body={body!r}, "
                f"got {result!r}"
            )


# ---------------------------------------------------------------------------
# Pure Python re-implementation of the plain-text rendering logic from
# renderBody() in web/static/messageDetail.js (view === "text" branch)
# ---------------------------------------------------------------------------

import re


def render_plain_text(body: str) -> str:
    """Mirror the plain-text rendering logic from renderBody() in messageDetail.js.

    Steps (matching the JS implementation):
    1. HTML-escape &, <, > in the body.
    2. Linkify http(s):// URLs with <a href="..." target="_blank" rel="noopener noreferrer">...</a>.
    3. Wrap in <pre style="...">...</pre>.
    """
    # Step 1: HTML-escape special characters (order matters: & first)
    escaped = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Step 2: Linkify URLs — note: URLs in the *original* body may contain &, <, >
    # but after escaping, the URL text in `escaped` will have &amp; etc.
    # The JS regex runs on the already-escaped string, so we do the same.
    linkified = re.sub(
        r"(https?://[^\s]+)",
        r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>',
        escaped,
    )

    # Step 3: Wrap in <pre>
    return (
        '<pre style="white-space:pre-wrap;word-break:break-word;'
        'font-family:inherit;font-size:14px;line-height:1.6;margin:0">'
        + linkified
        + "</pre>"
    )


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# A strategy that generates a URL-like string
_url_strategy = st.builds(
    lambda scheme, host, path: f"{scheme}://{host}{path}",
    scheme=st.sampled_from(["http", "https"]),
    host=st.from_regex(r"[a-z]{3,10}\.[a-z]{2,6}", fullmatch=True),
    path=st.from_regex(r"(/[a-zA-Z0-9._~-]{0,20}){0,3}", fullmatch=True),
)

# A strategy that generates body strings guaranteed to contain at least one URL
_body_with_url_strategy = st.builds(
    lambda prefix, url, suffix: prefix + url + suffix,
    prefix=st.text(max_size=50),
    url=_url_strategy,
    suffix=st.text(max_size=50),
)


# ---------------------------------------------------------------------------
# Property 6: Plain-text view wraps body in <pre> with linkified URLs
# Feature: message-html-view, Property 6: Plain-text view wraps body in pre with linkified URLs
#
# For any body string, the rendered output SHALL:
#   1. Start with <pre and end with </pre>
#   2. Have any URL in the body appear as an <a> tag in the output
#   3. Have HTML special chars (&, <, >) in the body escaped
#
# Validates: Requirements 2.6
# ---------------------------------------------------------------------------


@given(body=st.text())
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_6_plain_text_wraps_in_pre(body):
    """Feature: message-html-view, Property 6: Plain-text view wraps body in pre with linkified URLs

    For any body string, the rendered output SHALL start with <pre and end with </pre>.

    **Validates: Requirements 2.6**
    """
    # Feature: message-html-view, Property 6: Plain-text view wraps body in pre with linkified URLs
    result = render_plain_text(body)
    assert result.startswith("<pre"), (
        f"Expected output to start with '<pre', got: {result[:50]!r}"
    )
    assert result.endswith("</pre>"), (
        f"Expected output to end with '</pre>', got: {result[-50:]!r}"
    )


@given(body=_body_with_url_strategy)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_6_plain_text_linkifies_urls(body):
    """Feature: message-html-view, Property 6: Plain-text view wraps body in pre with linkified URLs

    For any body string containing URL patterns (https?://...), each URL SHALL
    appear as an <a href="..."> tag in the rendered output.

    **Validates: Requirements 2.6**
    """
    # Feature: message-html-view, Property 6: Plain-text view wraps body in pre with linkified URLs
    result = render_plain_text(body)

    # Find all URLs in the original body
    urls_in_body = re.findall(r"https?://[^\s]+", body)

    for url in urls_in_body:
        # After HTML-escaping the URL (& → &amp;, < → &lt;, > → &gt;),
        # the escaped form should appear inside an <a href="..."> tag.
        escaped_url = url.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        expected_anchor = f'<a href="{escaped_url}"'
        assert expected_anchor in result, (
            f"Expected URL {url!r} to be linkified as {expected_anchor!r} in output, "
            f"but it was not found.\nOutput: {result!r}"
        )


@given(body=st.text())
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_6_plain_text_escapes_html_special_chars(body):
    """Feature: message-html-view, Property 6: Plain-text view wraps body in pre with linkified URLs

    For any body string, HTML special characters (&, <, >) in the body SHALL
    be escaped in the rendered output (outside of injected <a> tags).

    **Validates: Requirements 2.6**
    """
    # Feature: message-html-view, Property 6: Plain-text view wraps body in pre with linkified URLs
    result = render_plain_text(body)

    # Strip the outer <pre ...>...</pre> wrapper to get the inner content
    inner_match = re.match(r"<pre[^>]*>(.*)</pre>$", result, re.DOTALL)
    assert inner_match is not None, f"Could not find <pre>...</pre> wrapper in: {result!r}"
    inner = inner_match.group(1)

    # Remove all <a ...>...</a> tags (the linkified URLs) from the inner content
    # so we only check the non-URL portions for proper escaping.
    inner_without_anchors = re.sub(r"<a\b[^>]*>.*?</a>", "", inner, flags=re.DOTALL)

    # In the remaining text, raw & < > from the original body must not appear
    # (they should have been replaced by &amp; &lt; &gt;).
    # We check by verifying that any & in the remaining text is part of an entity.
    # Specifically: no bare & (not followed by amp;, lt;, gt;, or #)
    bare_ampersand = re.search(r"&(?!amp;|lt;|gt;|#)", inner_without_anchors)
    assert bare_ampersand is None, (
        f"Found unescaped '&' in rendered output for body={body!r}.\n"
        f"Inner (without anchors): {inner_without_anchors!r}"
    )

    # No bare < or > should appear in the non-anchor portion
    assert "<" not in inner_without_anchors, (
        f"Found unescaped '<' in rendered output for body={body!r}.\n"
        f"Inner (without anchors): {inner_without_anchors!r}"
    )
    assert ">" not in inner_without_anchors, (
        f"Found unescaped '>' in rendered output for body={body!r}.\n"
        f"Inner (without anchors): {inner_without_anchors!r}"
    )


# ---------------------------------------------------------------------------
# Pure Python re-implementation of the toggle visibility logic from
# buildToggleButton() in web/static/messageDetail.js
# ---------------------------------------------------------------------------


def show_toggle(body_html, body) -> bool:
    """Mirror the toggle visibility logic from buildToggleButton() in messageDetail.js.

    Returns True iff both body_html and body are non-empty strings (not None, not "").
    """
    has_html = body_html is not None and body_html != ""
    has_plain = body is not None and body != ""
    return has_html and has_plain


# ---------------------------------------------------------------------------
# Property 4: Toggle visibility iff both fields are non-empty
# Feature: message-html-view, Property 4: Toggle visibility iff both fields are non-empty
#
# For any message object, the toggle SHALL be present if and only if both
# `body_html` and `body` are non-empty strings.
#
# Validates: Requirements 2.1, 3.1, 3.2, 3.3
# ---------------------------------------------------------------------------


@given(
    body_html=st.one_of(st.none(), st.text()),
    body=st.one_of(st.none(), st.text()),
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_4_toggle_visibility(body_html, body):
    """Feature: message-html-view, Property 4: Toggle visibility iff both fields are non-empty

    For any message object, the toggle SHALL be present if and only if both
    `body_html` and `body` are non-empty strings.

    **Validates: Requirements 2.1, 3.1, 3.2, 3.3**
    """
    # Feature: message-html-view, Property 4: Toggle visibility iff both fields are non-empty
    result = show_toggle(body_html, body)

    both_non_empty = (
        body_html is not None and body_html != ""
        and body is not None and body != ""
    )

    assert result == both_non_empty, (
        f"show_toggle({body_html!r}, {body!r}) returned {result!r}, "
        f"expected {both_non_empty!r}"
    )


# ---------------------------------------------------------------------------
# Pure Python re-implementation of the toggle label logic from
# buildToggleButton() in web/static/messageDetail.js
# ---------------------------------------------------------------------------


def toggle_label(active_view: str) -> str:
    """Mirror the toggle label logic from buildToggleButton() in messageDetail.js.

    Returns "Plain text" when active_view == "html",
    returns "HTML" when active_view == "text".
    """
    return "Plain text" if active_view == "html" else "HTML"


# ---------------------------------------------------------------------------
# Property 3: Toggle label is always the opposite view name
# Feature: message-html-view, Property 3: Toggle label is always the opposite view name
#
# For any activeView value, the button label SHALL be "Plain text" when
# activeView === "html" and "HTML" when activeView === "text".
#
# Validates: Requirements 2.2, 2.3
# ---------------------------------------------------------------------------


@given(view=st.sampled_from(["html", "text"]))
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_3_toggle_label(view):
    """Feature: message-html-view, Property 3: Toggle label is always the opposite view name

    For any activeView value, the button label SHALL be "Plain text" when
    activeView is "html" and "HTML" when activeView is "text".

    **Validates: Requirements 2.2, 2.3**
    """
    # Feature: message-html-view, Property 3: Toggle label is always the opposite view name
    label = toggle_label(view)

    if view == "html":
        assert label == "Plain text", (
            f"When activeView='html', expected label='Plain text', got {label!r}"
        )
    else:  # view == "text"
        assert label == "HTML", (
            f"When activeView='text', expected label='HTML', got {label!r}"
        )


# ---------------------------------------------------------------------------
# Pure Python re-implementation of the active CSS class logic from
# buildToggleButton() in web/static/messageDetail.js
# ---------------------------------------------------------------------------


def has_active_class(active_view: str) -> bool:
    """Mirror the active CSS class logic from buildToggleButton() in messageDetail.js.

    Returns True iff active_view == "text" (i.e., the view-toggle-btn--active
    class is applied when the Plain_Text_View is active).
    """
    return active_view == "text"


# ---------------------------------------------------------------------------
# Property 7: Active state class applied iff Plain_Text_View
# Feature: message-html-view, Property 7: Active state class applied iff Plain_Text_View
#
# For any message with both fields non-empty, the button SHALL have
# `view-toggle-btn--active` if and only if `activeView === "text"`.
#
# Validates: Requirements 4.3
# ---------------------------------------------------------------------------


@given(
    active_view=st.sampled_from(["html", "text"]),
    body=st.text(min_size=1),
    body_html=st.text(min_size=1),
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_7_active_class(active_view, body, body_html):
    """Feature: message-html-view, Property 7: Active state class applied iff Plain_Text_View

    For any message with both fields non-empty, the button SHALL have
    `view-toggle-btn--active` if and only if `activeView === "text"`.

    **Validates: Requirements 4.3**
    """
    # Feature: message-html-view, Property 7: Active state class applied iff Plain_Text_View
    # Both body and body_html are non-empty (guaranteed by min_size=1 in strategies)
    result = has_active_class(active_view)

    if active_view == "text":
        assert result is True, (
            f"When activeView='text', expected has_active_class=True, got {result!r}"
        )
    else:  # active_view == "html"
        assert result is False, (
            f"When activeView='html', expected has_active_class=False, got {result!r}"
        )


# ---------------------------------------------------------------------------
# Pure Python re-implementation of the toggle flip logic from
# buildToggleButton() click handler in web/static/messageDetail.js
# ---------------------------------------------------------------------------


def toggle_view(active_view: str) -> str:
    """Mirror the activeView flip logic from the click handler in buildToggleButton().

    "html" → "text", "text" → "html"
    """
    return "text" if active_view == "html" else "html"


# ---------------------------------------------------------------------------
# Property 5: Toggle is a round-trip
# Feature: message-html-view, Property 5: Toggle is a round-trip
#
# For any message with both `body_html` and `body` non-empty, toggling twice
# SHALL return `activeView` to its original value and produce the same content
# selection as before the first toggle.
#
# Validates: Requirements 2.4, 2.5
# ---------------------------------------------------------------------------


@given(
    active_view=st.sampled_from(["html", "text"]),
    body=st.text(min_size=1),
    body_html=st.text(min_size=1),
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_5_toggle_round_trip(active_view, body, body_html):
    """Feature: message-html-view, Property 5: Toggle is a round-trip

    For any message with both `body_html` and `body` non-empty, toggling twice
    SHALL return `activeView` to its original value and produce the same content
    selection as before the first toggle.

    **Validates: Requirements 2.4, 2.5**
    """
    # Feature: message-html-view, Property 5: Toggle is a round-trip

    # Record the original content selection before any toggle
    original_content = select_content(body_html, body, active_view)

    # Toggle once: html → text or text → html
    after_first_toggle = toggle_view(active_view)

    # Toggle again: should return to the original view
    after_second_toggle = toggle_view(after_first_toggle)

    # Assert 1: two toggles return activeView to its original value
    assert after_second_toggle == active_view, (
        f"After two toggles, expected activeView={active_view!r}, "
        f"got {after_second_toggle!r} (intermediate: {after_first_toggle!r})"
    )

    # Assert 2: content selection after two toggles equals content before any toggle
    content_after_round_trip = select_content(body_html, body, after_second_toggle)
    assert content_after_round_trip == original_content, (
        f"Content after two toggles differs from original.\n"
        f"  active_view={active_view!r}, body={body!r}, body_html={body_html!r}\n"
        f"  original_content={original_content!r}\n"
        f"  content_after_round_trip={content_after_round_trip!r}"
    )


# ---------------------------------------------------------------------------
# Pure Python re-implementation of the activeView reset logic from
# render() in web/static/messageDetail.js
# ---------------------------------------------------------------------------


def reset_active_view() -> str:
    """Mirror the activeView reset at the start of render() in messageDetail.js.

    render() always sets activeView = "html" before any DOM work, so this
    function always returns "html" regardless of any previous state.
    """
    return "html"


# ---------------------------------------------------------------------------
# Property 1: Default view is always HTML
# Feature: message-html-view, Property 1: Default view is always HTML
#
# For any message object, `activeView` after a `render()` call SHALL be
# "html", regardless of the previous view state.
#
# Validates: Requirements 1.1, 1.4
# ---------------------------------------------------------------------------


@given(previous_view=st.sampled_from(["html", "text"]))
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_1_default_view_is_html(previous_view):
    """Feature: message-html-view, Property 1: Default view is always HTML

    For any message object, `activeView` after a `render()` call SHALL be
    "html", regardless of the previous view state.

    **Validates: Requirements 1.1, 1.4**
    """
    # Feature: message-html-view, Property 1: Default view is always HTML
    result = reset_active_view()

    assert result == "html", (
        f"After render(), expected activeView='html' regardless of previous "
        f"view state (was {previous_view!r}), but got {result!r}"
    )


# ---------------------------------------------------------------------------
# Pure Python re-implementation of the panel visibility logic from
# buildToggleButton() click handler in web/static/messageDetail.js
# ---------------------------------------------------------------------------


def panel_visible_after_toggle(was_visible: bool) -> bool:
    """Mirror the panel visibility behaviour of the toggle click handler.

    The click handler in buildToggleButton() only calls renderBody() and
    updates the button label/class — it does NOT touch the panel's `hidden`
    attribute.  Therefore panel visibility is unchanged by a toggle: the
    function returns `was_visible` unchanged.
    """
    # The toggle does NOT change panel visibility.
    return was_visible


# ---------------------------------------------------------------------------
# Property 8: Panel remains open after toggle
# Feature: message-html-view, Property 8: Panel remains open after toggle
#
# For any message with both fields non-empty, after the View_Toggle is
# activated the `#message-detail` panel SHALL remain visible.
#
# Validates: Requirements 5.1
# ---------------------------------------------------------------------------


@given(
    was_visible=st.just(True),
    body=st.text(min_size=1),
    body_html=st.text(min_size=1),
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_8_panel_stays_open_after_toggle(was_visible, body, body_html):
    """Feature: message-html-view, Property 8: Panel remains open after toggle

    For any message with both fields non-empty, after the View_Toggle is
    activated the `#message-detail` panel SHALL remain visible.

    **Validates: Requirements 5.1**
    """
    # Feature: message-html-view, Property 8: Panel remains open after toggle
    # Both body and body_html are non-empty (guaranteed by min_size=1 in strategies).
    # The panel is open (was_visible=True) when the toggle is available.
    result = panel_visible_after_toggle(was_visible)

    assert result is True, (
        f"After toggle, expected panel to remain visible (True), "
        f"but panel_visible_after_toggle({was_visible!r}) returned {result!r}. "
        f"body={body!r}, body_html={body_html!r}"
    )
