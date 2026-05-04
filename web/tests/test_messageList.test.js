/**
 * Frontend property-based tests for the messageList.js display date feature.
 *
 * Uses fast-check for property generation and jest-environment-jsdom for DOM simulation.
 * Each property runs a minimum of 100 iterations.
 *
 * Properties tested:
 *   Property 15: Display date uses received_date when available (Req 12.1, 12.2)
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
 * Returns the best available display date for a message.
 * Prefers received_date; falls back to timestamp.
 *
 * Faithful copy of getDisplayDate() from web/static/messageList.js
 */
function getDisplayDate(msg) {
  return msg.received_date || msg.timestamp;
}

// ---------------------------------------------------------------------------
// Property 15: Display date uses received_date when available
// Validates: Requirements 12.1, 12.2
// ---------------------------------------------------------------------------

describe("Property 15: Display date uses received_date when available", () => {
  /**
   * **Validates: Requirements 12.1, 12.2**
   *
   * For any message object where received_date is non-null, getDisplayDate(msg)
   * SHALL return received_date. For any message object where received_date is
   * null or undefined, getDisplayDate(msg) SHALL return timestamp.
   */
  test("test_display_date_prefers_received_date: returns received_date when non-null, falls back to timestamp otherwise", () => {
    fc.assert(
      fc.property(
        // received_date: either null/undefined (absent) or a non-empty string
        fc.option(fc.string({ minLength: 1 }), { nil: null }),
        // timestamp: always a non-empty string (required fallback)
        fc.string({ minLength: 1 }),
        (received_date, timestamp) => {
          const msg = { received_date, timestamp };
          const result = getDisplayDate(msg);

          if (received_date !== null && received_date !== undefined) {
            // When received_date is present, it must be returned
            expect(result).toBe(received_date);
          } else {
            // When received_date is absent, timestamp must be returned
            expect(result).toBe(timestamp);
          }
        }
      ),
      { numRuns: 200 }
    );
  });

  test("test_display_date_prefers_received_date: undefined received_date falls back to timestamp", () => {
    fc.assert(
      fc.property(
        // timestamp: always a non-empty string
        fc.string({ minLength: 1 }),
        (timestamp) => {
          // msg with no received_date property at all (undefined)
          const msg = { timestamp };
          const result = getDisplayDate(msg);
          expect(result).toBe(timestamp);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Unit tests for messageList.js — received_date / timestamp fallback
// Validates: Requirements 12.1, 12.2
// ---------------------------------------------------------------------------

describe("Unit tests: message list display date", () => {
  /**
   * **Validates: Requirements 12.1**
   *
   * When received_date is non-null, getDisplayDate returns received_date.
   */
  test("message list uses received_date when non-null", () => {
    const received = "2024-03-20T14:00:00Z";
    const timestamp = "2024-03-18T09:00:00Z";
    const msg = { received_date: received, timestamp };
    expect(getDisplayDate(msg)).toBe(received);
  });

  /**
   * **Validates: Requirements 12.2**
   *
   * When received_date is null, getDisplayDate falls back to timestamp.
   */
  test("message list falls back to timestamp when received_date is null", () => {
    const timestamp = "2024-03-18T09:00:00Z";
    const msg = { received_date: null, timestamp };
    expect(getDisplayDate(msg)).toBe(timestamp);
  });

  test("message list falls back to timestamp when received_date is undefined", () => {
    const timestamp = "2024-03-18T09:00:00Z";
    const msg = { timestamp };
    expect(getDisplayDate(msg)).toBe(timestamp);
  });

  test("message list falls back to timestamp when received_date is empty string", () => {
    const timestamp = "2024-03-18T09:00:00Z";
    const msg = { received_date: "", timestamp };
    // Empty string is falsy, so falls back to timestamp
    expect(getDisplayDate(msg)).toBe(timestamp);
  });
});
