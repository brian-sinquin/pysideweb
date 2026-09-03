const {test, expect} = require("@playwright/test");
const {spawn} = require("node:child_process");
const net = require("node:net");
const exerciseShowcase = require("./showcase.cjs");

test("input, rich text, styles, painting, disposal, reconnect, and ordering", async ({page}) => {
    const errors = [];
    page.on("pageerror", error => errors.push(String(error)));
    page.on("console", message => {
        if (message.type() === "error") errors.push(message.text());
    });

    // Force the full tree and the fixture's first incremental update to queue
    // before the renderer builds the DOM.
    await page.addInitScript(() => {
        const nativeTimeout = window.setTimeout.bind(window);
        window.requestAnimationFrame = callback => nativeTimeout(callback, 300);
        const originalTimeout = window.setTimeout.bind(window);
        window.setTimeout = (callback, delay, ...args) =>
            originalTimeout(callback, delay === 100 ? 300 : delay, ...args);

        const NativeWebSocket = window.WebSocket;
        window.WebSocket = class extends NativeWebSocket {
            constructor(...args) {
                super(...args);
                let delivered = false;
                Object.defineProperty(this, "onmessage", {
                    set: handler => this.addEventListener("message", event => {
                        handler(event);
                        const message = JSON.parse(event.data);
                        if (delivered || message.type !== "full_tree") return;
                        const stack = [...message.roots];
                        let button;
                        while (stack.length) {
                            const node = stack.pop();
                            if (node.props?.objectName === "ordering-button") button = node;
                            stack.push(...(node.children || []));
                        }
                        if (button) {
                            delivered = true;
                            this.send(JSON.stringify({id: button.id, event: "clicked", value: null}));
                        }
                    }),
                });
            }
        };
    });
    await page.goto("/");
    await expect(page.locator("#ordering-status")).toHaveText("update-preserved");

    const editor = page.locator("#editor");
    await editor.fill("focused value");
    await expect(page.locator("#echo")).toHaveText("focused value");
    await expect(editor).toBeFocused();
    await expect(editor).toHaveValue("focused value");

    await page.locator("#rich-button").click();
    const rich = page.locator("#rich-output");
    await expect(rich.locator("b")).toHaveText("safe");
    await expect(rich.locator("script")).toHaveCount(0);
    await expect(rich.locator("a")).not.toHaveAttribute("href", /.+/);
    await expect(rich.locator("a")).not.toHaveAttribute("onclick", /.+/);
    await expect(rich).toContainText("bad()");

    await expect(page.locator("#pysideweb-app-qss")).toHaveCount(1);
    await page.locator("#style-button").click();
    await expect(page.locator("#pysideweb-app-qss")).toHaveCount(0);

    const canvas = page.locator("#paint-probe canvas");
    await expect(canvas).toHaveCount(1);
    expect(await canvas.getAttribute("width")).not.toBe("0");

    await page.locator("#dispose-button").click();
    await expect(page.locator("#disposable")).toHaveCount(0);

    await page.reload();
    await expect(page.locator("#connection-status .status-text")).toHaveText("Connected");
    await expect(page.locator("#ordering-status")).toHaveText("update-preserved");
    expect(errors).toEqual([]);
});

async function freePort() {
    return new Promise((resolve, reject) => {
        const server = net.createServer();
        server.once("error", reject);
        server.listen(0, "127.0.0.1", () => {
            const {port} = server.address();
            server.close(error => error ? reject(error) : resolve(port));
        });
    });
}

async function waitForServer(url, child) {
    const deadline = Date.now() + 15_000;
    while (Date.now() < deadline) {
        if (child.exitCode !== null) throw new Error(`example exited with ${child.exitCode}`);
        try {
            const response = await fetch(url);
            if (response.ok) return;
        } catch {}
        await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw new Error(`timed out waiting for ${url}`);
}

for (const example of ["preferences.py", "contacts.py", "custom_paint.py", "data_browser.py", "showcase.py"]) {
    test(`example smoke: ${example}`, async ({browser}) => {
        const port = await freePort();
        const child = spawn("uv", ["run", "python", `examples/${example}`], {
            cwd: process.cwd(),
            env: {...process.env, PYSIDEWEB_PORT: String(port), PYSIDEWEB_NO_BROWSER: "1"},
            stdio: ["ignore", "pipe", "pipe"],
        });
        let output = "";
        child.stdout.on("data", chunk => { output += chunk; });
        child.stderr.on("data", chunk => { output += chunk; });
        try {
            const url = `http://127.0.0.1:${port}`;
            await waitForServer(url, child);
            const page = await browser.newPage();
            const errors = [];
            page.on("pageerror", error => errors.push(String(error)));
            await page.goto(url);
            await expect(page.locator("#connection-status .status-text")).toHaveText("Connected");
            await expect(page.locator("#app > *")).not.toHaveCount(0);
            if (example === "custom_paint.py") {
                await expect(page.locator("canvas").first()).toBeVisible();
            }
            if (example === "showcase.py") await exerciseShowcase(page);
            expect(errors).toEqual([]);
            await page.close();
        } catch (error) {
            throw new Error(`${error.message}\n${output}`);
        } finally {
            child.kill("SIGTERM");
            await new Promise(resolve => {
                if (child.exitCode !== null) resolve();
                else {
                    child.once("exit", resolve);
                    setTimeout(() => { child.kill("SIGKILL"); resolve(); }, 2_000);
                }
            });
        }
    });
}
