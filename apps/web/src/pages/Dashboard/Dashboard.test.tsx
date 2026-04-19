import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { Dashboard } from "./index";

describe("Dashboard", () => {
  it("renders the hero headline", () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("heading", { level: 1, name: /train, deploy, and query/i }),
    ).toBeInTheDocument();
  });
});
