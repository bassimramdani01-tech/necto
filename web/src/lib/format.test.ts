import { describe, expect, it } from "vitest";

import {
  absoluteTime,
  formatCompact,
  formatDuration,
  formatMoney,
  formatNumber,
  formatRelative,
  shortId,
} from "./format";

describe("formatMoney", () => {
  it("renders zero and small costs with enough precision", () => {
    expect(formatMoney(0)).toBe("$0");
    expect(formatMoney(0.00003)).toBe("$0.00003");
    expect(formatMoney(0.0005)).toBe("$0.00050");
  });

  it("rounds normal amounts to cents", () => {
    expect(formatMoney(0.5)).toBe("$0.50");
    expect(formatMoney(12.5)).toBe("$12.50");
  });
});

describe("formatNumber / formatCompact", () => {
  it("groups thousands", () => {
    expect(formatNumber(2328)).toBe("2,328");
    expect(formatNumber(0)).toBe("0");
  });

  it("compacts large numbers", () => {
    expect(formatCompact(999)).toBe("999");
    expect(formatCompact(1600)).toBe("1.6K");
    expect(formatCompact(29_300)).toBe("29.3K");
  });
});

describe("formatRelative", () => {
  const ago = (seconds: number) => new Date(Date.now() - seconds * 1000).toISOString();

  it("handles missing and invalid input", () => {
    expect(formatRelative(null)).toBe("—");
    expect(formatRelative("not-a-date")).toBe("—");
  });

  it("picks the right unit", () => {
    expect(formatRelative(ago(0))).toBe("0s ago");
    expect(formatRelative(ago(30))).toBe("30s ago");
    expect(formatRelative(ago(90))).toBe("2m ago");
    expect(formatRelative(ago(3 * 3600))).toBe("3h ago");
    expect(formatRelative(ago(2 * 86_400))).toBe("2d ago");
  });
});

describe("formatDuration", () => {
  const start = "2026-01-01T00:00:00.000Z";

  it("reports a running run", () => {
    expect(formatDuration(start, null)).toBe("running");
  });

  it("picks the right unit", () => {
    expect(formatDuration(start, "2026-01-01T00:00:00.500Z")).toBe("500ms");
    expect(formatDuration(start, "2026-01-01T00:00:02.500Z")).toBe("2.5s");
    expect(formatDuration(start, "2026-01-01T00:01:00.000Z")).toBe("1m");
  });

  it("is defensive about invalid ranges", () => {
    expect(formatDuration(start, "2025-12-31T23:59:00.000Z")).toBe("—");
  });
});

describe("shortId / absoluteTime", () => {
  it("truncates ids", () => {
    expect(shortId("abcdefgh-1234-5678")).toBe("abcdefgh");
  });

  it("formats absolute timestamps and tolerates junk", () => {
    expect(absoluteTime(null)).toBe("");
    expect(absoluteTime("not-a-date")).toBe("");
    expect(absoluteTime("2026-01-01T10:00:00.000Z").length).toBeGreaterThan(0);
  });
});
