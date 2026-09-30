import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Progress } from "./index";

describe("Progress", () => {
  it("reports a real percentage when known", () => {
    render(<Progress value={0.42} label="Gen" />);
    const bar = screen.getByRole("progressbar", { name: "Gen" });
    expect(bar.getAttribute("aria-valuenow")).toBe("42");
  });
  it("is indeterminate (no fake number) when progress is unknown", () => {
    render(<Progress value={null} label="Load" />);
    const bar = screen.getByRole("progressbar", { name: "Load" });
    expect(bar.getAttribute("aria-valuenow")).toBeNull();
    expect(bar.getAttribute("aria-valuetext")).toBe("In progress");
  });
});
