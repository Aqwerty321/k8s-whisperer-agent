import { expect, test } from "@playwright/test";

async function waitForHealth(request) {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    try {
      const response = await request.get("http://127.0.0.1:4173/health");
      if (response.ok()) {
        return;
      }
    } catch (_error) {
      // wait and retry until the helper stack is fully ready
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("Backend bridge did not become healthy in time.");
}

async function seedIncident(request) {
  const response = await request.post("http://127.0.0.1:4173/api/incidents/run-once", {
    data: {
      namespace: "default",
      seed_events: [
        {
          type: "Warning",
          reason: "BackOff",
          message: "Back-off restarting failed container",
          namespace: "default",
          resource_name: "demo-crashloop",
          resource_kind: "Pod",
        },
      ],
    },
  });

  expect(response.ok()).toBeTruthy();
  return response.json();
}

test("operator can anchor and verify an incident proof", async ({ page, request }) => {
  await waitForHealth(request);
  const seeded = await seedIncident(request);

  await page.goto("/");

  await page.getByPlaceholder("Search incident payloads").fill(seeded.incident_id);
  await page.getByRole("button", { name: "Apply" }).click();
  await page.getByRole("button", { name: seeded.incident_id }).click();

  await expect(page.getByText(seeded.incident_id).first()).toBeVisible();
  await expect(page.getByText("Selected Incident", { exact: true })).toBeVisible();
  await expect(page.getByText(seeded.status).nth(1)).toBeVisible();

  await page.getByRole("button", { name: "Anchor Incident" }).click();
  await expect(page.getByText("Anchored on Soroban", { exact: true })).toBeVisible();
  await expect(page.getByText("Incident hash anchored on Soroban.", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Verify Proof" }).click();
  await expect(page.getByText("Proof Verified", { exact: true })).toBeVisible();
  await expect(page.getByText("On-chain incident hash matches.", { exact: true })).toBeVisible();
});
