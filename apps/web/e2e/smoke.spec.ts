import { expect, test } from "@playwright/test";

// Minimal smoke: the SPA boots, the router lands the unauthenticated user on
// the login screen, and the form renders. We stub /api/auth/me to return 401
// so RequireAuth redirects before the real backend is touched — the whole
// suite is backend-free on purpose (see playwright.config.ts).

test.beforeEach(async ({ page }) => {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({ status: 401, contentType: "application/json", body: "{}" }),
  );
});

test("login page renders without a backend", async ({ page }) => {
  await page.goto("/");

  // The SPA redirects unauthenticated users to /login; assert both the URL
  // and that the key form controls are in the DOM.
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: /sign in to aipacken/i })).toBeVisible();
  await expect(page.locator('input[type="password"]')).toBeVisible();
  await expect(page.getByRole("button", { name: /(sign in|log in|submit)/i })).toBeVisible();
});

test("login submit surfaces an error on 401", async ({ page }) => {
  await page.route("**/api/auth/login", (route) =>
    route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "invalid" }),
    }),
  );

  await page.goto("/login");
  await page.locator('input[autocomplete="email"]').fill("nobody@example.com");
  await page.locator('input[type="password"]').fill("wrong-password");
  await page.getByRole("button", { name: /(sign in|log in|submit)/i }).click();

  // The Login page maps ApiError(401) to the i18n key auth.invalid; we just
  // assert some inline error block shows up (exact copy would couple the
  // smoke to the i18n catalogue).
  await expect(page.locator(".text-danger")).toBeVisible();
});
