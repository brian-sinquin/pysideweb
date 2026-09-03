const {defineConfig} = require("@playwright/test");

module.exports = defineConfig({
    testDir: __dirname,
    testMatch: "*.spec.cjs",
    timeout: 30_000,
    workers: 1,
    retries: 0,
    use: {
        baseURL: "http://127.0.0.1:18765",
        headless: true,
        viewport: {width: 1100, height: 800},
    },
    webServer: {
        command: "PYSIDEWEB_PORT=18765 PYSIDEWEB_NO_BROWSER=1 uv run python tests_browser/browser_app.py",
        url: "http://127.0.0.1:18765",
        timeout: 20_000,
        reuseExistingServer: false,
        stdout: "pipe",
        stderr: "pipe",
    },
});
