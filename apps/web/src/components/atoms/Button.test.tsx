import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { Button } from "./Button";

describe("Button", () => {
  it("renders the label with primary styling by default", () => {
    render(<Button>Start run</Button>);
    const btn = screen.getByRole("button", { name: /start run/i });
    expect(btn).toBeInTheDocument();
    expect(btn).toHaveClass("btn-primary");
  });

  it("applies the ghost variant class", () => {
    render(<Button variant="ghost">Secondary</Button>);
    expect(screen.getByRole("button", { name: /secondary/i })).toHaveClass("btn-ghost");
  });

  it("renders as a Link when asChild is set to link", () => {
    render(
      <MemoryRouter>
        <Button asChild as="link" to="/datasets">
          Datasets
        </Button>
      </MemoryRouter>,
    );
    const link = screen.getByRole("link", { name: /datasets/i });
    expect(link).toHaveAttribute("href", "/datasets");
  });
});
