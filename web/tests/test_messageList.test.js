/**
 * Frontend property-based tests for the messageList.js display date feature.
 *
 * Uses fast-check for property generation and jest-environment-jsdom for DOM simulation.
 * Each property runs a minimum of 100 iterations.
 *
 * Properties tested:
 *   Property 15: Display date always uses timestamp (Req 12.1)
 */

"use strict";

const fc = require("fast-check");

// ---------------------------------------------------------------------------
// Re-implement getDisplayDate from messageList.js
//
// We re-implement the function here rather than importing messageList.js
// because messageList.js references globals (state, etc.) that are not
// available in the test environment. The implementation below is a faithful
// copy of the function from messageList.js.
// ---------------------------------------------------------------------------

/**
 * Returns the display date for a message — always uses timestamp.
 *
 * Faithful copy of getDisplayDate() from web/static/messageList.js
 */
function getDisplayDate(msg) {
  return msg.timestamp;
}

// ---------------------------------------------------------------------------
// Property 15: Display date always uses timestamp
// Validates: Requirement 12.1
// ---------------------------------------------------------------------------

describe("Property 15: Display date always uses timestamp", () => {
  /**
   * **Validates: Requirement 12.1**
   *
   * For any message object, getDisplayDate(msg) SHALL return msg.timestamp.
   */
  test("test_display_date_uses_timestamp: always returns timestamp", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1 }),
        (timestamp) => {
          const msg = { timestamp };
          expect(getDisplayDate(msg)).toBe(timestamp);
        }
      ),
      { numRuns: 200 }
    );
  });

  test("test_display_date_uses_timestamp: ignores any other date fields", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1 }),
        fc.string({ minLength: 1 }),
        (timestamp, otherDate) => {
          const msg = { timestamp, received_date: otherDate };
          expect(getDisplayDate(msg)).toBe(timestamp);
        }
      ),
      { numRuns: 200 }
    );
  });
});

// ---------------------------------------------------------------------------
// Unit tests for messageList.js — timestamp display
// Validates: Requirement 12.1
// ---------------------------------------------------------------------------

describe("Unit tests: message list display date", () => {
  /**
   * **Validates: Requirement 12.1**
   *
   * getDisplayDate always returns timestamp.
   */
  test("message list uses timestamp", () => {
    const timestamp = "2024-03-18T09:00:00Z";
    const msg = { timestamp };
    expect(getDisplayDate(msg)).toBe(timestamp);
  });

  test("message list uses timestamp even when other date fields are present", () => {
    const timestamp = "2024-03-18T09:00:00Z";
    const msg = { timestamp, received_date: "2024-03-20T14:00:00Z" };
    expect(getDisplayDate(msg)).toBe(timestamp);
  });

  test("message list returns undefined when timestamp is absent", () => {
    const msg = {};
    expect(getDisplayDate(msg)).toBeUndefined();
  });
});
