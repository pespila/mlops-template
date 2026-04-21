import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { Dashboard } from "./index";

describe("Dashboard", () => {
  it("renders the hero headline", () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
    });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <Dashboard />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(
      screen.getByRole("heading", { level: 1, name: /train, deploy, and query/i }),
    ).toBeInTheDocument();
  });
});
