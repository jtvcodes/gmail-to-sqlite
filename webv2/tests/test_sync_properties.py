"""Property-based tests for the sync API endpoint.

Tests use a Flask test client with a patched subprocess.run so that no real
main.py is required.  The tests focus purely on the command-building logic
inside run_sync().
"""

import json
import os
import tempfile
import unittest.mock as mock

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from web.server import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client():
    """Return a Flask test client backed by a temporary (empty) DB path.

    The DB file does not need to exist because the sync endpoint only reads
    current_app.config["DB_PATH"] to derive the workspace root; it never
    opens the DB itself.
    """
    # Use a temp directory so that os.path.dirname chains work correctly.
    tmp_dir = tempfile.mkdtemp()
    data_dir = os.path.join(tmp_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    db_path = os.path.join(data_dir, "messages.db")

    # Create a dummy main.py so the "not found" guard passes.
    main_py = os.path.join(tmp_dir, "main.py")
    with open(main_py, "w") as f:
        f.write("# dummy\n")

    flask_app = create_app(db_path=db_path)
    flask_app.config["TESTING"] = True
    client = flask_app.test_client()
    return client, tmp_dir


def _post_sync(client, body: dict):
    """POST /api/sync with a JSON body and return the response."""
    return client.post(
        "/api/sync",
        data=json.dumps(body),
        content_type="application/json",
    )


# ---------------------------------------------------------------------------
# Property 2: Backend mode routing correctness
# Validates: Requirements 3.3, 4.2, 5.2, 6.2, 6.3, 6.4
# ---------------------------------------------------------------------------

@given(
    mode=st.sampled_from(["delta", "force", "missing"]),
    data_dir=st.text(min_size=1, max_size=50),
)
@settings(
    max_examples=20,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_property_2_backend_mode_routing_correctness(mode, data_dir):
    """**Validates: Requirements 3.3, 4.2, 5.2, 6.2, 6.3, 6.4**

    For any valid mode in {'delta', 'force', 'missing'} and any data_dir,
    the subprocess command built by run_sync() SHALL contain exactly the
    flags that correspond to that mode:
      - delta   → --delta present, --force absent
      - force   → --force present, --delta absent
      - missing → neither --delta nor --force present
    """
    client, _ = _make_client()

    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        result = mock.MagicMock()
        result.returncode = 0
        result.stdout = "ok"
        result.stderr = ""
        return result

    with mock.patch("web.api.sync.subprocess.run", side_effect=fake_run):
        resp = _post_sync(client, {"mode": mode})

    # The endpoint should succeed (subprocess was mocked to return 0)
    assert resp.status_code == 200, (
        f"Expected 200 for mode={mode!r}, got {resp.status_code}: {resp.get_json()}"
    )
    assert len(captured_cmd) > 0, "subprocess.run was not called"

    if mode == "delta":
        assert "--delta" in captured_cmd, (
            f"mode='delta': expected --delta in cmd {captured_cmd}"
        )
        assert "--force" not in captured_cmd, (
            f"mode='delta': unexpected --force in cmd {captured_cmd}"
        )
    elif mode == "force":
        assert "--force" in captured_cmd, (
            f"mode='force': expected --force in cmd {captured_cmd}"
        )
        assert "--delta" not in captured_cmd, (
            f"mode='force': unexpected --delta in cmd {captured_cmd}"
        )
    else:  # missing
        assert "--delta" not in captured_cmd, (
            f"mode='missing': unexpected --delta in cmd {captured_cmd}"
        )
        assert "--force" not in captured_cmd, (
            f"mode='missing': unexpected --force in cmd {captured_cmd}"
        )


# ---------------------------------------------------------------------------
# Property 3: Invalid mode values are rejected
# Validates: Requirements 6.1, 6.5
# ---------------------------------------------------------------------------

_VALID_MODES = {"delta", "force", "missing"}

invalid_mode_strategy = st.text().filter(lambda s: s not in _VALID_MODES)


@given(mode=invalid_mode_strategy)
@settings(
    max_examples=20,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    deadline=None,
)
def test_property_3_invalid_mode_rejection(mode):
    """**Validates: Requirements 6.1, 6.5**

    For any string value not in {'delta', 'force', 'missing'}, the Sync_API
    SHALL return HTTP 400 with a non-empty error message body.
    """
    client, _ = _make_client()

    # subprocess should never be called for invalid modes
    with mock.patch("web.api.sync.subprocess.run") as mock_run:
        resp = _post_sync(client, {"mode": mode})
        mock_run.assert_not_called()

    assert resp.status_code == 400, (
        f"Expected HTTP 400 for invalid mode={mode!r}, got {resp.status_code}"
    )

    body = resp.get_json()
    assert body is not None, "Response body should be JSON"
    assert "error" in body, f"Response JSON missing 'error' key: {body}"
    assert len(body["error"]) > 0, (
        f"Error message should be non-empty for mode={mode!r}"
    )


# ---------------------------------------------------------------------------
# Property 8: Subprocess output is captured and returned for all sync modes
# Validates: Requirements 3.4, 4.3, 5.3
# ---------------------------------------------------------------------------


@given(
    mode=st.sampled_from(["delta", "force", "missing"]),
    stdout_text=st.text(min_size=1, max_size=200),
    stderr_text=st.text(min_size=1, max_size=200),
)
@settings(
    max_examples=20,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_property_8_subprocess_output_captured_success(mode, stdout_text, stderr_text):
    """**Validates: Requirements 3.4, 4.3, 5.3**

    For any valid mode in {'delta', 'force', 'missing'} and any stdout/stderr
    content, the JSON response SHALL include an `output` field containing the
    combined stdout+stderr.  The subprocess SHALL always be invoked with
    ``capture_output=True`` so that output is always redirectable.
    """
    client, _ = _make_client()

    fake_result = mock.MagicMock()
    fake_result.returncode = 0
    fake_result.stdout = stdout_text
    fake_result.stderr = stderr_text

    with mock.patch("web.api.sync.subprocess.run", return_value=fake_result) as mock_run:
        resp = _post_sync(client, {"mode": mode})

    assert resp.status_code == 200, (
        f"Expected 200 for mode={mode!r}, got {resp.status_code}: {resp.get_json()}"
    )

    body = resp.get_json()
    assert body is not None, "Response body should be JSON"
    assert "output" in body, f"Response JSON missing 'output' key: {body}"

    expected_output = (stdout_text + stderr_text).strip()
    assert body["output"] == expected_output, (
        f"output mismatch for mode={mode!r}: expected {expected_output!r}, got {body['output']!r}"
    )

    # Confirm subprocess.run was called with capture_output=True
    mock_run.assert_called_once()
    _, call_kwargs = mock_run.call_args
    assert call_kwargs.get("capture_output") is True, (
        f"subprocess.run was not called with capture_output=True; kwargs={call_kwargs}"
    )


@given(
    mode=st.sampled_from(["delta", "force", "missing"]),
    stdout_text=st.text(min_size=1, max_size=200),
    stderr_text=st.text(min_size=1, max_size=200),
)
@settings(
    max_examples=20,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_property_8_subprocess_output_captured_error(mode, stdout_text, stderr_text):
    """**Validates: Requirements 3.4, 4.3, 5.3**

    When the subprocess exits with a non-zero return code, the response SHALL
    be HTTP 500 and the JSON body SHALL include both an ``error`` field and an
    ``output`` field containing the combined stdout+stderr.
    """
    client, _ = _make_client()

    fake_result = mock.MagicMock()
    fake_result.returncode = 1
    fake_result.stdout = stdout_text
    fake_result.stderr = stderr_text

    with mock.patch("web.api.sync.subprocess.run", return_value=fake_result):
        resp = _post_sync(client, {"mode": mode})

    assert resp.status_code == 500, (
        f"Expected 500 for failed subprocess with mode={mode!r}, got {resp.status_code}"
    )

    body = resp.get_json()
    assert body is not None, "Response body should be JSON"
    assert "error" in body, f"Response JSON missing 'error' key: {body}"
    assert "output" in body, f"Response JSON missing 'output' key: {body}"

    expected_output = (stdout_text + stderr_text).strip()
    assert body["output"] == expected_output, (
        f"output mismatch for mode={mode!r}: expected {expected_output!r}, got {body['output']!r}"
    )
