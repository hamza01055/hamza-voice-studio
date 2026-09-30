import { describe, expect, it } from "vitest";
import { fmtBytes, fmtDuration, hasRtl, wordCount } from "./format";
import { parseHash } from "./router";

describe("format helpers", () => {
  it("formats durations", () => {
    expect(fmtDuration(4.5)).toBe("0:04.5");
    expect(fmtDuration(65)).toBe("1:05.0");
    expect(fmtDuration(3725)).toBe("1:02:05");
    expect(fmtDuration(null)).toBe("–");
  });
  it("formats bytes", () => {
    expect(fmtBytes(349906910)).toBe("334 MB");
    expect(fmtBytes(null)).toBe("unknown");
  });
  it("counts words in mixed scripts", () => {
    expect(wordCount("AI ki training  15 October")).toBe(5);
    expect(wordCount("آپ کیسے ہیں")).toBe(3);
    expect(wordCount("   ")).toBe(0);
  });
  it("detects right-to-left text", () => {
    expect(hasRtl("Hello آپ")).toBe(true);
    expect(hasRtl("Hello")).toBe(false);
  });
});

describe("router", () => {
  it("parses hash routes", () => {
    expect(parseHash("#/studio/abc")).toEqual({ page: "studio", projectId: "abc" });
    expect(parseHash("#/studio")).toEqual({ page: "studio", projectId: null });
    expect(parseHash("#token=xyz")).toEqual({ page: "projects" });
    expect(parseHash("#/models")).toEqual({ page: "models" });
  });
});
