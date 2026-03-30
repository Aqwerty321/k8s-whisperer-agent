import { defineConfig, devices } from "@playwright/test";

const isWSL = Boolean(process.env.WSL_DISTRO_NAME);

export default defineConfig({
  testDir: "./tests",
  timeout: 120000,
  expect: {
    timeout: 10000,
  },
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    launchOptions: {
      args: isWSL
        ? [
            "--use-angle=swiftshader",
            "--enable-webgl",
            "--ignore-gpu-blocklist",
            "--disable-dev-shm-usage",
          ]
        : [],
    },
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1600, height: 1000 },
      },
    },
  ],
  webServer: {
    command: "bash ../scripts/run_frontend_e2e_stack.sh",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: false,
    timeout: 120000,
  },
});
