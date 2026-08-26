/**
 * PySideWeb — DOM Renderer & WebSocket Client
 *
 * Receives a JSON widget tree from the Python server via WebSocket,
 * and efficiently renders it into semantic HTML elements. User interactions
 * are sent back as events.
 *
 * Key anti-flicker strategy:
 *  - requestAnimationFrame coalescing: multiple WS messages in one frame → one render
 *  - DocumentFragment: build new DOM off-screen, then atomic swap via replaceChildren
 *  - Input preservation: focused inputs are never replaced mid-typing
 */

(function () {
    "use strict";

    // ── Configuration ──────────────────────────────────────────
    const WS_URL = `ws://${window.location.host}/ws`;
    const RECONNECT_DELAY = 1500;
    const MAX_RECONNECT_DELAY = 10000;

    // ── State ──────────────────────────────────────────────────
    let ws = null;
    let reconnectDelay = RECONNECT_DELAY;
    let pendingRoots = null;
    let rafId = null;
    let isFirstRender = true;
    const appEl = document.getElementById("app");
    const statusEl = document.getElementById("connection-status");

    // Element cache: widgetId → DOM element (for focused-input preservation)
    const focusCache = new Map();

    // ── Rich text sanitization ────────────────────────────────
    //
    // QLabel/QPushButton text containing "<...>" is treated as Qt-style rich
    // text (mirroring QLabel's own auto-detection of HTML content) and
    // rendered via innerHTML rather than textContent. Text reaching a label
    // often originates from data the Python app didn't author itself (a
    // network response, a file, user input echoed back), so it must never
    // be assigned to innerHTML verbatim — that's a direct DOM XSS sink,
    // unlike real Qt's rich text renderer which never executes script.
    // Only a small allowlist of formatting tags/attributes survives; every
    // other tag is unwrapped (dropped, its content kept) and every
    // non-allowlisted attribute is stripped.
    const RICH_TEXT_ALLOWED_TAGS = new Set([
        "B", "STRONG", "I", "EM", "U", "S", "BR", "P", "SPAN", "A", "SMALL",
        "SUB", "SUP", "CODE", "PRE", "UL", "OL", "LI",
        "H1", "H2", "H3", "H4", "H5", "H6", "DIV", "IMG",
    ]);
    const RICH_TEXT_ALLOWED_ATTRS = { A: new Set(["href"]), IMG: new Set(["src", "alt"]) };
    const RICH_TEXT_SAFE_URL = /^(https?:|mailto:|data:image\/|#)/i;

    function sanitizeRichText(html) {
        const template = document.createElement("template");
        template.innerHTML = String(html);
        for (const el of Array.from(template.content.querySelectorAll("*"))) {
            if (!RICH_TEXT_ALLOWED_TAGS.has(el.tagName)) {
                el.replaceWith(...el.childNodes);
                continue;
            }
            const allowedAttrs = RICH_TEXT_ALLOWED_ATTRS[el.tagName];
            for (const attr of Array.from(el.attributes)) {
                const name = attr.name.toLowerCase();
                const isUrlAttr = name === "href" || name === "src";
                const keep = allowedAttrs && allowedAttrs.has(name) &&
                    (!isUrlAttr || RICH_TEXT_SAFE_URL.test(attr.value.trim()));
                if (!keep) el.removeAttribute(attr.name);
            }
        }
        return template.innerHTML;
    }

    // ── WebSocket ──────────────────────────────────────────────

    function connect() {
        ws = new WebSocket(WS_URL);

        ws.onopen = () => {
            console.log("[PySideWeb] Connected");
            reconnectDelay = RECONNECT_DELAY;
            setStatus("connected");
        };

        ws.onclose = () => {
            console.log("[PySideWeb] Disconnected, reconnecting...");
            setStatus("disconnected");
            setTimeout(connect, reconnectDelay);
            reconnectDelay = Math.min(reconnectDelay * 1.5, MAX_RECONNECT_DELAY);
        };

        ws.onerror = (err) => {
            console.error("[PySideWeb] WebSocket error:", err);
            ws.close();
        };

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                handleMessage(msg);
            } catch (e) {
                console.error("[PySideWeb] Parse error:", e);
            }
        };
    }

    function sendEvent(id, eventType, value) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ id, event: eventType, value }));
        }
    }

    function setStatus(state) {
        const textEl = statusEl.querySelector(".status-text");
        statusEl.className = state === "connected" ? "status-connected" : "status-disconnected";
        textEl.textContent = state === "connected" ? "Connected" : "Reconnecting...";
    }

    // ── Message Handler (coalesced via rAF) ─────────────────────

    function handleMessage(msg) {
        if (msg.type === "full_tree") {
            pendingRoots = msg.roots;
            if (!rafId) {
                rafId = requestAnimationFrame(flushRender);
            }
        } else if (msg.type === "updates") {
            // Apply property updates directly (no rAF delay or DOM rebuild)
            applyUpdates(msg.updates);
        }
    }

    function flushRender() {
        rafId = null;
        if (pendingRoots) {
            renderTree(pendingRoots);
            pendingRoots = null;
        }
    }

    function applyUpdates(updates) {
        if (!updates) return;
        for (const update of updates) {
            const el = appEl.querySelector(`[data-wid="${update.id}"]`);
            if (!el) continue;

            const prop = update.prop;
            const val = update.value;

            // Direct DOM property patching
            if (prop === "text") {
                if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
                    if (el.value !== val) {
                        el.value = val;
                    }
                } else if (el.classList.contains("qprogressbar")) {
                    // Update progress bar fill and text
                    const fill = el.querySelector(".progress-fill");
                    const text = el.querySelector(".progress-text");
                    const min = parseFloat(el.dataset.min ?? 0);
                    const max = parseFloat(el.dataset.max ?? 100);
                    const pct = max > min ? ((parseFloat(val) - min) / (max - min)) * 100 : 0;
                    if (fill) fill.style.width = `${pct}%`;
                    if (text) text.textContent = `${Math.round(pct)}%`;
                } else {
                    // QLabel, QPushButton, etc.
                    if (val.includes("<") && val.includes(">")) {
                        el.innerHTML = sanitizeRichText(val);
                    } else {
                        // Check if it has a text container child or update directly
                        const textSpan = el.querySelector("span:not(.btn-icon)");
                        if (textSpan) {
                            textSpan.textContent = val;
                        } else {
                            el.textContent = val;
                        }
                    }
                }
            } else if (prop === "value") {
                if (el.tagName === "INPUT" && el.type === "range") {
                    el.value = val;
                    const valLbl = el.parentElement.querySelector(".slider-value");
                    if (valLbl) valLbl.textContent = val;
                } else if (el.classList.contains("qprogressbar")) {
                    const fill = el.querySelector(".progress-fill");
                    const text = el.querySelector(".progress-text");
                    const min = parseFloat(el.dataset.min ?? 0);
                    const max = parseFloat(el.dataset.max ?? 100);
                    const pct = max > min ? ((parseFloat(val) - min) / (max - min)) * 100 : 0;
                    if (fill) fill.style.width = `${pct}%`;
                    if (text) text.textContent = `${Math.round(pct)}%`;
                } else if (el.classList.contains("qspinbox")) {
                    const input = el.querySelector("input");
                    if (input) input.value = val;
                }
            } else if (prop === "visible") {
                if (val) {
                    el.classList.remove("widget-hidden");
                } else {
                    el.classList.add("widget-hidden");
                }
            } else if (prop === "enabled") {
                if (val) {
                    el.classList.remove("widget-disabled");
                    if (el.disabled !== undefined) el.disabled = false;
                } else {
                    el.classList.add("widget-disabled");
                    if (el.disabled !== undefined) el.disabled = true;
                }
            } else if (prop === "styleSheet") {
                applyStyleSheet(el, val);
            } else if (prop === "currentIndex") {
                if (el.classList.contains("qtabwidget")) {
                    // Tab layout index switch
                    const tabItems = el.querySelectorAll(".tab-bar .tab-item");
                    const tabPages = el.querySelectorAll(".tab-content .tab-page");
                    tabItems.forEach((item, idx) => {
                        if (idx === val) item.classList.add("active");
                        else item.classList.remove("active");
                    });
                    tabPages.forEach((page, idx) => {
                        if (idx === val) page.classList.add("active");
                        else page.classList.remove("active");
                    });
                } else if (el.classList.contains("qstackedwidget")) {
                    const pages = el.querySelectorAll(".stacked-page");
                    pages.forEach((page, idx) => {
                        if (idx === val) page.classList.add("active");
                        else page.classList.remove("active");
                    });
                } else if (el.tagName === "SELECT") {
                    el.value = val;
                }
            } else if (prop === "items") {
                if (el.tagName === "SELECT") {
                    el.innerHTML = "";
                    val.forEach((item, idx) => {
                        const opt = document.createElement("option");
                        opt.value = idx;
                        opt.textContent = item;
                        el.appendChild(opt);
                    });
                } else if (el.classList.contains("qlistwidget")) {
                    el.innerHTML = "";
                    val.forEach((item, idx) => {
                        const row = document.createElement("div");
                        row.className = "list-item";
                        if (item.selected) row.classList.add("selected");
                        if (item.icon) {
                            const icon = document.createElement("span");
                            icon.className = "item-icon";
                            icon.textContent = item.icon;
                            row.appendChild(icon);
                        }
                        const text = document.createElement("span");
                        text.textContent = item.text || "";
                        row.appendChild(text);
                        row.addEventListener("click", () => {
                            sendEvent(update.id, "currentRowChanged", idx);
                        });
                        el.appendChild(row);
                    });
                }
            } else if (prop === "currentRow") {
                if (el.classList.contains("qlistwidget")) {
                    const listItems = el.querySelectorAll(".list-item");
                    listItems.forEach((item, idx) => {
                        if (idx === val) item.classList.add("selected");
                        else item.classList.remove("selected");
                    });
                }
            } else if (prop === "message") {
                if (el.classList.contains("qstatusbar")) {
                    el.textContent = val;
                }
            }
        }
    }

    // ── Tree Renderer (atomic swap) ────────────────────────────

    function renderTree(roots) {
        if (!roots || roots.length === 0) return;

        // Remember which element is focused and its caret/selection
        const focused = saveFocus();

        // Reconcile each root node with the DOM
        const reconciledRoots = [];
        for (const root of roots) {
            const el = reconcileNode(root);
            if (el) reconciledRoots.push(el);
        }

        // replaceChildren on appEl with the reconciled root elements
        appEl.replaceChildren(...reconciledRoots);

        if (isFirstRender) {
            isFirstRender = false;
        }

        // Restore focus + caret position
        restoreFocus(focused);
    }

    // ── Incremental DOM Reconciliation ──────────────────────────

    function reconcileNode(node) {
        if (!node || !node.type) return null;

        // Find if the element already exists in the document
        let el = appEl.querySelector(`[data-wid="${node.id}"]`);
        let isNew = false;

        if (!el) {
            // Create a new element
            const known = Object.prototype.hasOwnProperty.call(RENDERERS, node.type);
            el = (known ? RENDERERS[node.type] : renderGenericWidget)(node);
            el.dataset.wid = node.id;
            if (!known) {
                el.classList.add("widget-unsupported");
                el.title = `${node.type}: not implemented by pysideweb`;
            }
            isNew = true;
        }

        // Apply common props (both new and existing)
        el.id = node.props.objectName || node.id;

        if (node.props.visible) {
            el.classList.remove("widget-hidden");
        } else {
            el.classList.add("widget-hidden");
        }

        if (node.props.enabled) {
            el.classList.remove("widget-disabled");
            if (el.disabled !== undefined) el.disabled = false;
        } else {
            el.classList.add("widget-disabled");
            if (el.disabled !== undefined) el.disabled = true;
        }

        applyStyleSheet(el, node.props.styleSheet || "");

        if (node.props.font) {
            applyFont(el, node.props.font);
        }

        if (node.props.tooltip) {
            el.title = node.props.tooltip;
        } else {
            el.removeAttribute("title");
        }

        // Update widget-specific properties that could have changed
        updateWidgetSpecific(el, node);

        // Reconcile children
        reconcileChildrenForNode(el, node);

        return el;
    }

    function reconcileChildrenForNode(el, node) {
        // Skip for specialized widgets that handle their own child reconciliation
        if (node.type === "QTabWidget" || node.type === "QStackedWidget" || node.type === "QMainWindow" || node.type === "QDialog") {
            return;
        }

        const children = node.children || [];
        if (children.length === 0) {
            // Remove layout wrapper if empty
            const wrapper = el.querySelector(":scope > .layout-vbox, :scope > .layout-hbox, :scope > .layout-grid, :scope > .layout-form, :scope > .layout-stacked");
            if (wrapper) wrapper.remove();
            return;
        }

        let wrapper = el.querySelector(":scope > .layout-vbox, :scope > .layout-hbox, :scope > .layout-grid, :scope > .layout-form, :scope > .layout-stacked");
        if (!wrapper) {
            wrapper = document.createElement("div");
            el.appendChild(wrapper);
        }

        if (node.layout) {
            applyLayout(wrapper, node.layout);
        } else {
            wrapper.className = "layout-vbox";
        }

        const reconciledElements = [];
        let stretchCount = 0;

        for (const child of children) {
            if (child.type === "Stretch") {
                const existingSpacers = wrapper.querySelectorAll(":scope > .stretch-spacer");
                let spacer = existingSpacers[stretchCount];
                if (!spacer) {
                    spacer = document.createElement("div");
                    spacer.className = "stretch-spacer";
                }
                if (child.props && child.props.factor > 1) {
                    spacer.style.flex = child.props.factor;
                } else {
                    spacer.style.flex = "";
                }
                reconciledElements.push(spacer);
                stretchCount++;
                continue;
            }

            const childEl = reconcileNode(child);
            if (childEl) {
                if (node.layout && node.layout.type === "QGridLayout" && node.layout.gridItems) {
                    const gridInfo = node.layout.gridItems.find(g => g.id === child.id);
                    if (gridInfo) {
                        childEl.style.gridRow = `${gridInfo.row + 1} / span ${gridInfo.rowSpan}`;
                        childEl.style.gridColumn = `${gridInfo.col + 1} / span ${gridInfo.colSpan}`;
                    }
                }
                reconciledElements.push(childEl);
            }
        }

        wrapper.replaceChildren(...reconciledElements);
    }

    function updateWidgetSpecific(el, node) {
        switch (node.type) {
            case "QMainWindow":
                updateMainWindow(el, node);
                break;
            case "QPushButton":
                updatePushButton(el, node);
                break;
            case "QLabel":
                updateLabel(el, node);
                break;
            case "QLineEdit":
            case "QTextEdit":
                updateLineEdit(el, node);
                break;
            case "QComboBox":
                updateComboBox(el, node);
                break;
            case "QCheckBox":
                updateCheckBox(el, node);
                break;
            case "QRadioButton":
                updateRadioButton(el, node);
                break;
            case "QSlider":
                updateSlider(el, node);
                break;
            case "QProgressBar":
                updateProgressBar(el, node);
                break;
            case "QSpinBox":
            case "QDoubleSpinBox":
                updateSpinBox(el, node);
                break;
            case "QTabWidget":
                updateTabWidget(el, node);
                break;
            case "QGroupBox":
                updateGroupBox(el, node);
                break;
            case "QListWidget":
                updateListWidget(el, node);
                break;
            case "QSplitter":
                updateSplitter(el, node);
                break;
            case "QMenuBar":
                updateMenuBar(el, node);
                break;
            case "QStatusBar":
                updateStatusBar(el, node);
                break;
            case "QDialog":
                updateDialog(el, node);
                break;
        }
    }

    function updateMainWindow(el, node) {
        const title = el.querySelector(".window-title");
        if (title) {
            title.textContent = node.props.windowTitle || "PySideWeb Application";
        }

        const menuBarNode = node.children.find(c => c.type === "QMenuBar");
        const existingMenuBar = el.querySelector(":scope > .qmenubar");
        if (menuBarNode) {
            const menuBarEl = reconcileNode(menuBarNode);
            if (menuBarEl && menuBarEl !== existingMenuBar) {
                const titleBar = el.querySelector(".window-title-bar");
                if (titleBar) titleBar.after(menuBarEl);
                else el.prepend(menuBarEl);
            }
        } else if (existingMenuBar) {
            existingMenuBar.remove();
        }

        const content = el.querySelector(".window-content");
        if (content) {
            const centralId = node.props.centralWidgetId;
            if (centralId) {
                const centralNode = node.children.find(c => c.id === centralId);
                if (centralNode) {
                    const centralEl = reconcileNode(centralNode);
                    if (centralEl) {
                        centralEl.style.width = "100%";
                        centralEl.style.height = "100%";
                        if (centralEl.parentElement !== content) {
                            content.replaceChildren(centralEl);
                        }
                    }
                } else {
                    content.innerHTML = "";
                }
            } else {
                const nonCentralEls = [];
                for (const child of node.children) {
                    if (child.type !== "QMenuBar" && child.type !== "QStatusBar") {
                        const childEl = reconcileNode(child);
                        if (childEl) nonCentralEls.push(childEl);
                    }
                }
                content.replaceChildren(...nonCentralEls);
            }
        }

        const statusNode = node.children.find(c => c.type === "QStatusBar");
        const existingStatusBar = el.querySelector(":scope > .qstatusbar");
        if (statusNode) {
            const statusBarEl = reconcileNode(statusNode);
            if (statusBarEl && statusBarEl !== existingStatusBar) {
                el.appendChild(statusBarEl);
            }
        } else if (existingStatusBar) {
            existingStatusBar.remove();
        }
    }

    function updatePushButton(el, node) {
        if (node.props.flat) el.classList.add("flat");
        else el.classList.remove("flat");

        const iconSpan = el.querySelector(".btn-icon");
        if (node.props.icon) {
            if (iconSpan) {
                iconSpan.textContent = node.props.icon;
            } else {
                const newIcon = document.createElement("span");
                newIcon.className = "btn-icon";
                newIcon.textContent = node.props.icon;
                el.prepend(newIcon);
            }
        } else if (iconSpan) {
            iconSpan.remove();
        }

        const textSpan = el.querySelector("span:not(.btn-icon)");
        if (node.props.text) {
            if (textSpan) {
                textSpan.textContent = node.props.text;
            } else {
                const newText = document.createElement("span");
                newText.textContent = node.props.text;
                el.appendChild(newText);
            }
        } else if (textSpan) {
            textSpan.remove();
        }
    }

    function updateLabel(el, node) {
        const text = node.props.text || "";
        if (text.includes("<") && text.includes(">")) {
            el.innerHTML = sanitizeRichText(text);
        } else {
            el.textContent = text;
        }

        applyAlignment(el, node.props.alignment);

        if (node.props.wordWrap) {
            el.style.wordWrap = "break-word";
            el.style.whiteSpace = "normal";
        } else {
            el.style.wordWrap = "";
            el.style.whiteSpace = "";
        }
    }

    function updateLineEdit(el, node) {
        if (document.activeElement !== el) {
            el.value = node.props.text || "";
        }
        el.placeholder = node.props.placeholder || "";
        el.readOnly = node.props.readOnly || false;
    }

    function updateComboBox(el, node) {
        const items = node.props.items || [];
        const currentIndex = node.props.currentIndex ?? -1;

        const options = el.querySelectorAll("option");
        let needsRebuild = options.length !== items.length;
        if (!needsRebuild) {
            for (let i = 0; i < items.length; i++) {
                if (options[i].textContent !== items[i]) {
                    needsRebuild = true;
                    break;
                }
            }
        }
        if (needsRebuild) {
            el.innerHTML = "";
            for (let i = 0; i < items.length; i++) {
                const option = document.createElement("option");
                option.value = i;
                option.textContent = items[i];
                if (i === currentIndex) option.selected = true;
                el.appendChild(option);
            }
        } else {
            el.value = currentIndex;
        }
    }

    function updateCheckBox(el, node) {
        const input = el.querySelector("input");
        if (input) {
            input.checked = node.props.checked || false;
        }
        const textSpan = el.querySelector("span");
        if (textSpan) {
            textSpan.textContent = node.props.text || "";
        }
    }

    function updateRadioButton(el, node) {
        const input = el.querySelector("input");
        if (input) {
            input.checked = node.props.checked || false;
        }
        const textSpan = el.querySelector("span");
        if (textSpan) {
            textSpan.textContent = node.props.text || "";
        }
    }

    function updateSlider(el, node) {
        const input = el.querySelector("input");
        if (input) {
            input.min = node.props.minimum ?? 0;
            input.max = node.props.maximum ?? 99;
            if (document.activeElement !== input) {
                input.value = node.props.value ?? 0;
            }
            input.step = node.props.singleStep ?? 1;
        }
        const valueLabel = el.querySelector(".slider-value");
        if (valueLabel) {
            valueLabel.textContent = node.props.value ?? 0;
        }
    }

    function updateProgressBar(el, node) {
        const min = node.props.minimum ?? 0;
        const max = node.props.maximum ?? 100;
        const val = node.props.value ?? 0;
        const pct = max > min ? ((val - min) / (max - min)) * 100 : 0;

        el.dataset.min = min;
        el.dataset.max = max;

        const fill = el.querySelector(".progress-fill");
        if (fill) {
            fill.style.width = `${pct}%`;
        }

        const text = el.querySelector(".progress-text");
        if (node.props.textVisible !== false) {
            if (text) {
                text.textContent = `${Math.round(pct)}%`;
            } else {
                const newText = document.createElement("span");
                newText.className = "progress-text";
                newText.textContent = `${Math.round(pct)}%`;
                el.appendChild(newText);
            }
        } else if (text) {
            text.remove();
        }
    }

    function updateSpinBox(el, node) {
        const input = el.querySelector("input");
        if (input) {
            input.min = node.props.minimum ?? 0;
            input.max = node.props.maximum ?? 99;
            if (document.activeElement !== input) {
                input.value = node.props.value ?? 0;
            }
            input.step = node.props.singleStep ?? 1;
        }
    }

    function updateTabWidget(el, node) {
        const tabs = node.props.tabs || [];
        const currentIndex = node.props.currentIndex ?? 0;

        const tabBar = el.querySelector(".tab-bar") || document.createElement("div");
        tabBar.className = "tab-bar";
        if (!tabBar.parentElement) el.prepend(tabBar);

        tabBar.innerHTML = "";
        for (let i = 0; i < tabs.length; i++) {
            const tab = tabs[i];
            const tabItem = document.createElement("div");
            tabItem.className = "tab-item" + (i === currentIndex ? " active" : "");

            if (tab.icon) {
                const icon = document.createElement("span");
                icon.className = "tab-icon";
                icon.textContent = tab.icon;
                tabItem.appendChild(icon);
            }

            const text = document.createTextNode(tab.text || `Tab ${i + 1}`);
            tabItem.appendChild(text);

            tabItem.addEventListener("click", () => {
                sendEvent(node.id, "currentChanged", i);
            });

            tabBar.appendChild(tabItem);
        }

        const content = el.querySelector(".tab-content") || document.createElement("div");
        content.className = "tab-content";
        if (!content.parentElement) el.appendChild(content);

        let pages = content.querySelectorAll(".tab-page");
        while (pages.length < tabs.length) {
            const page = document.createElement("div");
            content.appendChild(page);
            pages = content.querySelectorAll(".tab-page");
        }
        while (pages.length > tabs.length) {
            pages[pages.length - 1].remove();
            pages = content.querySelectorAll(".tab-page");
        }

        for (let i = 0; i < tabs.length; i++) {
            const page = pages[i];
            page.className = "tab-page" + (i === currentIndex ? " active" : "");

            const childNode = node.children.find(c => c.id === tabs[i].widgetId);
            if (childNode) {
                const childEl = reconcileNode(childNode);
                if (childEl && childEl.parentElement !== page) {
                    childEl.style.height = "100%";
                    page.replaceChildren(childEl);
                }
            } else {
                page.innerHTML = "";
            }
        }
    }

    function updateGroupBox(el, node) {
        const title = el.querySelector(".group-title");
        if (node.props.title) {
            if (title) {
                title.textContent = node.props.title;
            } else {
                const newTitle = document.createElement("span");
                newTitle.className = "group-title";
                newTitle.textContent = node.props.title;
                el.prepend(newTitle);
            }
        } else if (title) {
            title.remove();
        }
    }

    function updateStackedWidget(el, node) {
        const currentIndex = node.props.currentIndex ?? 0;
        let pages = el.querySelectorAll(".stacked-page");
        
        while (pages.length < node.children.length) {
            const page = document.createElement("div");
            el.appendChild(page);
            pages = el.querySelectorAll(".stacked-page");
        }
        while (pages.length > node.children.length) {
            pages[pages.length - 1].remove();
            pages = el.querySelectorAll(".stacked-page");
        }

        for (let i = 0; i < node.children.length; i++) {
            const page = pages[i];
            page.className = "stacked-page" + (i === currentIndex ? " active" : "");
            
            const childNode = node.children[i];
            const childEl = reconcileNode(childNode);
            if (childEl && childEl.parentElement !== page) {
                page.replaceChildren(childEl);
            }
        }
    }

    function updateListWidget(el, node) {
        const items = node.props.items || [];
        const currentRow = node.props.currentRow ?? -1;

        el.innerHTML = "";
        for (let i = 0; i < items.length; i++) {
            const item = items[i];
            const row = document.createElement("div");
            row.className = "list-item" + (i === currentRow ? " selected" : "");

            if (item.icon) {
                const icon = document.createElement("span");
                icon.className = "item-icon";
                icon.textContent = item.icon;
                row.appendChild(icon);
            }

            const text = document.createElement("span");
            text.textContent = item.text || "";
            row.appendChild(text);

            row.addEventListener("click", () => {
                sendEvent(node.id, "currentRowChanged", i);
            });

            el.appendChild(row);
        }
    }

    function updateSplitter(el, node) {
        if (node.props.orientation === 2) {
            el.classList.add("vertical");
        } else {
            el.classList.remove("vertical");
        }
    }

    function updateMenuBar(el, node) {
        const menus = node.props.menus || [];
        el.innerHTML = "";
        for (const menu of menus) {
            const item = document.createElement("div");
            item.className = "menu-item";
            item.textContent = menu.title || "";
            el.appendChild(item);
        }
    }

    function updateStatusBar(el, node) {
        let textNode = Array.from(el.childNodes).find(n => n.nodeType === Node.TEXT_NODE);
        const msg = node.props.message || "";
        if (textNode) {
            textNode.nodeValue = msg;
        } else {
            el.prepend(document.createTextNode(msg));
        }
    }

    function updateDialog(el, node) {
        if (!node.props.visible) {
            el.classList.add("widget-hidden");
        } else {
            el.classList.remove("widget-hidden");
        }
        const dialog = el.querySelector(".qdialog");
        if (dialog) {
            reconcileChildrenForNode(dialog, node);
        }
    }

    // ── Focus Preservation ─────────────────────────────────────

    function saveFocus() {
        const active = document.activeElement;
        if (!active || active === document.body) return null;

        const wid = active.dataset?.wid || active.closest?.("[data-wid]")?.dataset?.wid;
        if (!wid) return null;

        return {
            wid,
            tag: active.tagName,
            selStart: active.selectionStart ?? null,
            selEnd: active.selectionEnd ?? null,
            value: active.value ?? null,
        };
    }

    function restoreFocus(saved) {
        if (!saved) return;

        // Find the element by data-wid
        const el = appEl.querySelector(`[data-wid="${saved.wid}"]`);
        if (!el) return;

        // Find the actual focusable child (input, textarea, select)
        const focusable = (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT")
            ? el
            : el.querySelector("input, textarea, select");

        if (!focusable) return;

        focusable.focus({ preventScroll: true });

        // Restore caret / selection
        if (saved.selStart !== null && typeof focusable.setSelectionRange === "function") {
            try {
                focusable.setSelectionRange(saved.selStart, saved.selEnd);
            } catch (e) {
                // Some input types don't support setSelectionRange
            }
        }
    }

    // ── Widget Renderers ───────────────────────────────────────

    function renderWidget(node) {
        if (!node || !node.type) return null;

        const known = Object.prototype.hasOwnProperty.call(RENDERERS, node.type);
        const el = (known ? RENDERERS[node.type] : renderGenericWidget)(node);

        if (!el) return null;

        // A type pysideweb doesn't implement (third-party PySide6 code
        // routinely uses classes far outside pysideweb's supported set --
        // see interceptor.py's unknown-class fallback) still renders --
        // as an empty box via renderGenericWidget -- but is marked so it's
        // visually distinguishable from an intentionally empty QWidget
        // rather than looking like a bug.
        if (!known) {
            el.classList.add("widget-unsupported");
            el.title = `${node.type}: not implemented by pysideweb`;
        }

        // Apply common props
        el.dataset.wid = node.id;
        el.id = node.props.objectName || node.id;

        if (!node.props.visible) {
            el.classList.add("widget-hidden");
        }

        if (!node.props.enabled) {
            el.classList.add("widget-disabled");
        }

        if (node.props.styleSheet) {
            applyStyleSheet(el, node.props.styleSheet);
        }

        if (node.props.font) {
            applyFont(el, node.props.font);
        }

        if (node.props.tooltip) {
            el.title = node.props.tooltip;
        }

        return el;
    }

    function renderChildren(container, node) {
        if (!node.children || node.children.length === 0) return;

        const layout = node.layout;
        const wrapper = document.createElement("div");

        if (layout) {
            applyLayout(wrapper, layout);
        }

        for (const child of node.children) {
            if (child.type === "Stretch") {
                const spacer = document.createElement("div");
                spacer.className = "stretch-spacer";
                if (child.props && child.props.factor > 1) {
                    spacer.style.flex = child.props.factor;
                }
                wrapper.appendChild(spacer);
                continue;
            }
            const childEl = renderWidget(child);
            if (childEl) {
                if (layout && layout.type === "QGridLayout" && layout.gridItems) {
                    const gridInfo = layout.gridItems.find(g => g.id === child.id);
                    if (gridInfo) {
                        childEl.style.gridRow = `${gridInfo.row + 1} / span ${gridInfo.rowSpan}`;
                        childEl.style.gridColumn = `${gridInfo.col + 1} / span ${gridInfo.colSpan}`;
                    }
                }
                wrapper.appendChild(childEl);
            }
        }

        container.appendChild(wrapper);
    }

    // ── Specific Widget Renderers ──────────────────────────────

    const RENDERERS = {
        QMainWindow: renderMainWindow,
        QWidget: renderGenericWidget,
        QFrame: renderFrame,
        QPushButton: renderPushButton,
        QLabel: renderLabel,
        QLineEdit: renderLineEdit,
        QTextEdit: renderTextEdit,
        QComboBox: renderComboBox,
        QCheckBox: renderCheckBox,
        QRadioButton: renderRadioButton,
        QSlider: renderSlider,
        QProgressBar: renderProgressBar,
        QSpinBox: renderSpinBox,
        QDoubleSpinBox: renderSpinBox,
        QTabWidget: renderTabWidget,
        QGroupBox: renderGroupBox,
        QScrollArea: renderScrollArea,
        QStackedWidget: renderStackedWidget,
        QListWidget: renderListWidget,
        QSplitter: renderSplitter,
        QMenuBar: renderMenuBar,
        QStatusBar: renderStatusBar,
        QDialog: renderDialog,
    };

    function renderMainWindow(node) {
        const el = document.createElement("div");
        el.className = "qmainwindow";

        // Title bar
        const titleBar = document.createElement("div");
        titleBar.className = "window-title-bar";

        const dots = document.createElement("div");
        dots.className = "window-dots";
        dots.innerHTML = `<span class="window-dot close"></span><span class="window-dot minimize"></span><span class="window-dot maximize"></span>`;
        titleBar.appendChild(dots);

        const title = document.createElement("span");
        title.className = "window-title";
        title.textContent = node.props.windowTitle || "PySideWeb Application";
        titleBar.appendChild(title);

        el.appendChild(titleBar);

        // Menu bar
        const menuBarNode = node.children.find(c => c.type === "QMenuBar");
        if (menuBarNode) {
            el.appendChild(renderMenuBar(menuBarNode));
        }

        // Content area
        const content = document.createElement("div");
        content.className = "window-content";

        const centralId = node.props.centralWidgetId;
        if (centralId) {
            const centralNode = node.children.find(c => c.id === centralId);
            if (centralNode) {
                const centralEl = renderWidget(centralNode);
                if (centralEl) {
                    centralEl.style.width = "100%";
                    centralEl.style.height = "100%";
                    content.appendChild(centralEl);
                }
            }
        } else {
            for (const child of node.children) {
                if (child.type !== "QMenuBar" && child.type !== "QStatusBar") {
                    const childEl = renderWidget(child);
                    if (childEl) content.appendChild(childEl);
                }
            }
        }

        el.appendChild(content);

        // Status bar
        const statusNode = node.children.find(c => c.type === "QStatusBar");
        if (statusNode) {
            el.appendChild(renderStatusBar(statusNode));
        }

        return el;
    }

    function renderGenericWidget(node) {
        const el = document.createElement("div");
        el.className = "qwidget";

        if (node.props.extraClasses) {
            for (const cls of node.props.extraClasses) {
                el.classList.add(cls);
            }
        }

        renderChildren(el, node);
        return el;
    }

    function renderFrame(node) {
        const el = document.createElement("div");
        const shape = node.props.frameShape || 0;

        if (shape === 4) {
            el.className = "qframe-hline";
            return el;
        }
        if (shape === 5) {
            el.className = "qframe-vline";
            return el;
        }

        el.className = "qwidget qframe";
        renderChildren(el, node);
        return el;
    }

    function renderPushButton(node) {
        const btn = document.createElement("button");
        btn.className = "qpushbutton";

        if (node.props.flat) btn.classList.add("flat");
        if (node.props.extraClasses) {
            for (const cls of node.props.extraClasses) {
                btn.classList.add(cls);
            }
        }

        if (node.props.icon) {
            const icon = document.createElement("span");
            icon.className = "btn-icon";
            icon.textContent = node.props.icon;
            btn.appendChild(icon);
        }

        if (node.props.text) {
            const text = document.createElement("span");
            text.textContent = node.props.text;
            btn.appendChild(text);
        }

        if (!node.props.enabled) {
            btn.disabled = true;
        }

        btn.addEventListener("click", () => {
            sendEvent(node.id, "clicked", null);
        });

        return btn;
    }

    function renderLabel(node) {
        const el = document.createElement("span");
        el.className = "qlabel";

        if (node.props.extraClasses) {
            for (const cls of node.props.extraClasses) {
                el.classList.add(cls);
            }
        }

        const text = node.props.text || "";
        if (text.includes("<") && text.includes(">")) {
            el.innerHTML = sanitizeRichText(text);
        } else {
            el.textContent = text;
        }

        applyAlignment(el, node.props.alignment);

        if (node.props.wordWrap) {
            el.style.wordWrap = "break-word";
            el.style.whiteSpace = "normal";
        }

        return el;
    }

    function renderLineEdit(node) {
        const input = document.createElement("input");
        input.className = "qlineedit";
        input.type = node.props.echoMode === 2 ? "password" : "text";
        input.value = node.props.text || "";
        input.placeholder = node.props.placeholder || "";

        if (node.props.readOnly) input.readOnly = true;
        if (!node.props.enabled) input.disabled = true;

        input.addEventListener("input", (e) => {
            sendEvent(node.id, "textChanged", e.target.value);
        });

        input.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                sendEvent(node.id, "returnPressed", null);
            }
        });

        input.addEventListener("blur", () => {
            sendEvent(node.id, "editingFinished", null);
        });

        return input;
    }

    function renderTextEdit(node) {
        const textarea = document.createElement("textarea");
        textarea.className = "qtextedit";
        textarea.value = node.props.text || "";
        textarea.placeholder = node.props.placeholder || "";

        if (node.props.readOnly) textarea.readOnly = true;

        textarea.addEventListener("input", (e) => {
            sendEvent(node.id, "textChanged", e.target.value);
        });

        return textarea;
    }

    function renderComboBox(node) {
        const select = document.createElement("select");
        select.className = "qcombobox";

        const items = node.props.items || [];
        const currentIndex = node.props.currentIndex ?? -1;

        for (let i = 0; i < items.length; i++) {
            const option = document.createElement("option");
            option.value = i;
            option.textContent = items[i];
            if (i === currentIndex) option.selected = true;
            select.appendChild(option);
        }

        select.addEventListener("change", (e) => {
            sendEvent(node.id, "currentIndexChanged", e.target.value);
        });

        return select;
    }

    function renderCheckBox(node) {
        const label = document.createElement("label");
        label.className = "qcheckbox";

        const input = document.createElement("input");
        input.type = "checkbox";
        input.checked = node.props.checked || false;

        input.addEventListener("change", (e) => {
            sendEvent(node.id, "toggled", e.target.checked);
        });

        label.appendChild(input);

        const text = document.createElement("span");
        text.textContent = node.props.text || "";
        label.appendChild(text);

        return label;
    }

    function renderRadioButton(node) {
        const label = document.createElement("label");
        label.className = "qradiobutton";

        const input = document.createElement("input");
        input.type = "radio";
        input.name = node.props.objectName ? `radio_${node.props.objectName}` : `radio_group`;
        input.checked = node.props.checked || false;

        input.addEventListener("change", (e) => {
            sendEvent(node.id, "toggled", e.target.checked);
        });

        label.appendChild(input);

        const text = document.createElement("span");
        text.textContent = node.props.text || "";
        label.appendChild(text);

        return label;
    }

    function renderSlider(node) {
        const container = document.createElement("div");
        container.className = "qslider";

        const input = document.createElement("input");
        input.type = "range";
        input.min = node.props.minimum ?? 0;
        input.max = node.props.maximum ?? 99;
        input.value = node.props.value ?? 0;
        input.step = node.props.singleStep ?? 1;

        const valueLabel = document.createElement("span");
        valueLabel.className = "slider-value";
        valueLabel.textContent = node.props.value ?? 0;

        input.addEventListener("input", (e) => {
            valueLabel.textContent = e.target.value;
            sendEvent(node.id, "valueChanged", e.target.value);
        });

        if (node.props.orientation === 2) {
            container.style.flexDirection = "column";
            container.style.height = "150px";
            input.style.writingMode = "vertical-lr";
            input.style.direction = "rtl";
        }

        container.appendChild(input);
        container.appendChild(valueLabel);

        return container;
    }

    function renderProgressBar(node) {
        const container = document.createElement("div");
        container.className = "qprogressbar";

        const min = node.props.minimum ?? 0;
        const max = node.props.maximum ?? 100;
        const val = node.props.value ?? 0;
        const pct = max > min ? ((val - min) / (max - min)) * 100 : 0;

        container.dataset.min = min;
        container.dataset.max = max;

        const fill = document.createElement("div");
        fill.className = "progress-fill";
        fill.style.width = `${pct}%`;

        container.appendChild(fill);

        if (node.props.textVisible !== false) {
            const text = document.createElement("span");
            text.className = "progress-text";
            text.textContent = `${Math.round(pct)}%`;
            container.appendChild(text);
        }

        return container;
    }

    function renderSpinBox(node) {
        const container = document.createElement("div");
        container.className = "qspinbox";

        const input = document.createElement("input");
        input.type = "number";
        input.min = node.props.minimum ?? 0;
        input.max = node.props.maximum ?? 99;
        input.value = node.props.value ?? 0;
        input.step = node.props.singleStep ?? 1;

        const btnDown = document.createElement("button");
        btnDown.className = "spin-btn";
        btnDown.textContent = "\u2212";
        btnDown.addEventListener("click", () => {
            const newVal = Math.max(parseInt(input.min), parseInt(input.value) - parseInt(input.step));
            input.value = newVal;
            sendEvent(node.id, "valueChanged", newVal);
        });

        const btnUp = document.createElement("button");
        btnUp.className = "spin-btn";
        btnUp.textContent = "+";
        btnUp.addEventListener("click", () => {
            const newVal = Math.min(parseInt(input.max), parseInt(input.value) + parseInt(input.step));
            input.value = newVal;
            sendEvent(node.id, "valueChanged", newVal);
        });

        input.addEventListener("change", (e) => {
            sendEvent(node.id, "valueChanged", e.target.value);
        });

        container.appendChild(btnDown);
        container.appendChild(input);
        container.appendChild(btnUp);

        return container;
    }

    function renderTabWidget(node) {
        const el = document.createElement("div");
        el.className = "qtabwidget";

        const tabs = node.props.tabs || [];
        const currentIndex = node.props.currentIndex ?? 0;

        // Tab bar
        const tabBar = document.createElement("div");
        tabBar.className = "tab-bar";

        for (let i = 0; i < tabs.length; i++) {
            const tab = tabs[i];
            const tabItem = document.createElement("div");
            tabItem.className = "tab-item" + (i === currentIndex ? " active" : "");

            if (tab.icon) {
                const icon = document.createElement("span");
                icon.className = "tab-icon";
                icon.textContent = tab.icon;
                tabItem.appendChild(icon);
            }

            const text = document.createTextNode(tab.text || `Tab ${i + 1}`);
            tabItem.appendChild(text);

            tabItem.addEventListener("click", () => {
                sendEvent(node.id, "currentChanged", i);
            });

            tabBar.appendChild(tabItem);
        }

        el.appendChild(tabBar);

        // Tab content
        const content = document.createElement("div");
        content.className = "tab-content";

        for (let i = 0; i < tabs.length; i++) {
            const page = document.createElement("div");
            page.className = "tab-page" + (i === currentIndex ? " active" : "");

            const childNode = node.children.find(c => c.id === tabs[i].widgetId);
            if (childNode) {
                const childEl = renderWidget(childNode);
                if (childEl) {
                    childEl.style.height = "100%";
                    page.appendChild(childEl);
                }
            }

            content.appendChild(page);
        }

        el.appendChild(content);

        return el;
    }

    function renderGroupBox(node) {
        const el = document.createElement("div");
        el.className = "qgroupbox";

        if (node.props.title) {
            const title = document.createElement("span");
            title.className = "group-title";
            title.textContent = node.props.title;
            el.appendChild(title);
        }

        renderChildren(el, node);
        return el;
    }

    function renderScrollArea(node) {
        const el = document.createElement("div");
        el.className = "qscrollarea";

        if (node.children && node.children.length > 0) {
            for (const child of node.children) {
                const childEl = renderWidget(child);
                if (childEl) el.appendChild(childEl);
            }
        }

        return el;
    }

    function renderStackedWidget(node) {
        const el = document.createElement("div");
        el.className = "qstackedwidget";

        const currentIndex = node.props.currentIndex ?? 0;

        for (let i = 0; i < node.children.length; i++) {
            const page = document.createElement("div");
            page.className = "stacked-page" + (i === currentIndex ? " active" : "");

            const childEl = renderWidget(node.children[i]);
            if (childEl) page.appendChild(childEl);

            el.appendChild(page);
        }

        return el;
    }

    function renderListWidget(node) {
        const el = document.createElement("div");
        el.className = "qlistwidget";

        const items = node.props.items || [];
        const currentRow = node.props.currentRow ?? -1;

        for (let i = 0; i < items.length; i++) {
            const item = items[i];
            const row = document.createElement("div");
            row.className = "list-item" + (i === currentRow ? " selected" : "");

            if (item.icon) {
                const icon = document.createElement("span");
                icon.className = "item-icon";
                icon.textContent = item.icon;
                row.appendChild(icon);
            }

            const text = document.createElement("span");
            text.textContent = item.text || "";
            row.appendChild(text);

            row.addEventListener("click", () => {
                sendEvent(node.id, "currentRowChanged", i);
            });

            el.appendChild(row);
        }

        return el;
    }

    function renderSplitter(node) {
        const el = document.createElement("div");
        el.className = "qsplitter";

        if (node.props.orientation === 2) {
            el.classList.add("vertical");
        }

        for (const child of node.children) {
            const childEl = renderWidget(child);
            if (childEl) el.appendChild(childEl);
        }

        return el;
    }

    function renderMenuBar(node) {
        const el = document.createElement("div");
        el.className = "qmenubar";

        const menus = node.props.menus || [];
        for (const menu of menus) {
            const item = document.createElement("div");
            item.className = "menu-item";
            item.textContent = menu.title || "";
            el.appendChild(item);
        }

        return el;
    }

    function renderStatusBar(node) {
        const el = document.createElement("div");
        el.className = "qstatusbar";
        el.textContent = node.props.message || "";

        if (node.children) {
            for (const child of node.children) {
                const childEl = renderWidget(child);
                if (childEl) el.appendChild(childEl);
            }
        }

        return el;
    }

    function renderDialog(node) {
        const overlay = document.createElement("div");
        overlay.className = "qdialog-overlay";
        if (!node.props.visible) {
            overlay.classList.add("widget-hidden");
        }

        const dialog = document.createElement("div");
        dialog.className = "qdialog";
        overlay.appendChild(dialog);

        renderChildren(dialog, node);

        return overlay;
    }

    // ── Layout Application ─────────────────────────────────────

    function applyLayout(el, layout) {
        const type = layout.type;
        const spacing = layout.spacing ?? 6;
        const margins = layout.margins || [9, 9, 9, 9];

        el.style.padding = `${margins[1]}px ${margins[2]}px ${margins[3]}px ${margins[0]}px`;

        switch (type) {
            case "QVBoxLayout":
                el.className = "layout-vbox";
                el.style.gap = `${spacing}px`;
                break;
            case "QHBoxLayout":
                el.className = "layout-hbox";
                el.style.gap = `${spacing}px`;
                break;
            case "QGridLayout":
                el.className = "layout-grid";
                el.style.gap = `${spacing}px`;
                const cols = layout.cols || 1;
                const colStretches = layout.colStretches || {};
                const colTemplate = [];
                for (let c = 0; c < cols; c++) {
                    colTemplate.push(colStretches[c] ? `${colStretches[c]}fr` : "auto");
                }
                el.style.gridTemplateColumns = colTemplate.join(" ");
                break;
            case "QFormLayout":
                el.className = "layout-form";
                el.style.gap = `${spacing}px ${spacing * 2}px`;
                break;
            case "QStackedLayout":
                el.className = "layout-stacked";
                break;
            default:
                el.className = "layout-vbox";
                el.style.gap = `${spacing}px`;
        }
    }

    // ── Style Helpers ──────────────────────────────────────────

    function applyStyleSheet(el, css) {
        if (el._appliedStyles) {
            for (const prop of el._appliedStyles) {
                el.style[prop] = "";
            }
        }
        el._appliedStyles = [];

        const propertyRegex = /([a-zA-Z-]+)\s*:\s*([^;]+)/g;
        let match;
        while ((match = propertyRegex.exec(css)) !== null) {
            const prop = match[1].trim();
            const val = match[2].trim();
            const cssProp = prop.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
            try {
                el.style[cssProp] = val;
                el._appliedStyles.push(cssProp);
            } catch (e) {
                // Ignore invalid properties
            }
        }
    }

    function applyFont(el, font) {
        if (font.fontFamily) el.style.fontFamily = font.fontFamily;
        if (font.fontSize) el.style.fontSize = font.fontSize;
        if (font.fontWeight) el.style.fontWeight = font.fontWeight;
        if (font.fontStyle) el.style.fontStyle = font.fontStyle;
        if (font.textDecoration) el.style.textDecoration = font.textDecoration;
    }

    function applyAlignment(el, alignment) {
        if (!alignment) return;

        el.style.display = "block";

        if (alignment & 0x0004) el.style.textAlign = "center";
        else if (alignment & 0x0002) el.style.textAlign = "right";
        else if (alignment & 0x0001) el.style.textAlign = "left";

        if (alignment & 0x0080) el.style.alignSelf = "center";
        else if (alignment & 0x0040) el.style.alignSelf = "flex-end";
        else if (alignment & 0x0020) el.style.alignSelf = "flex-start";
    }

    // ── Initialize ─────────────────────────────────────────────

    connect();

})();
