import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RunStatusBadge, type RunStatus } from "./RunStatusBadge";

const ALL_STATUSES: RunStatus[] = [
  "queued",
  "building",
  "running",
  "succeeded",
  "failed",
  "cancelled",
];

describe("RunStatusBadge", () => {
  it.each(ALL_STATUSES)("renders the %s status label", (status) => {
    render(<RunStatusBadge status={status} />);
    expect(
      screen.getByText(new RegExp(status, "i")),
    ).toBeInTheDocument();
  });
});
