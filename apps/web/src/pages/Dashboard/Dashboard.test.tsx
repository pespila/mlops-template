import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Dashboard } from "./index";

describe("Dashboard", () => {
  it("renders the hero headline", () => {
    render(<Dashboard />);
    expect(
      screen.getByRole("heading", { level: 1, name: /train, deploy, and query/i }),
    ).toBeInTheDocument();
  });
});
