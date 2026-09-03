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
    let pendingUpdates = [];
    let rafId = null;
    let renderFallbackId = null;
    // id -> the node object from the last full_tree. Incremental `updates`
    // messages patch a prop on the cached node and re-run the widget's
    // update(el, node), so there is exactly one place that knows how to draw
    // each widget type (WIDGETS[type].update), not two.
    let nodesById = {};
    const appEl = document.getElementById("app");
    const statusEl = document.getElementById("connection-status");

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
            // A newer full tree supersedes updates queued for an older one.
            pendingUpdates = [];
            applyAppStyleSheet(msg.appStyleSheetCss || "");
            if (!rafId) {
                rafId = requestAnimationFrame(flushRender);
            }
            // requestAnimationFrame is throttled to ~never while the tab is
            // hidden or not compositing (background tab, some headless/embedded
            // views). Without a fallback the very first tree would never paint
            // there. setTimeout keeps firing regardless, so whichever lands
            // first renders and cancels the other.
            if (!renderFallbackId) {
                renderFallbackId = setTimeout(flushRender, 100);
            }
        } else if (msg.type === "updates") {
            if (pendingRoots) {
                // The initial/full render is deferred to requestAnimationFrame.
                // Preserve updates received before that frame and apply them
                // immediately after the tree has built nodesById + the DOM.
                pendingUpdates.push(...(msg.updates || []));
            } else {
                applyUpdates(msg.updates);
            }
        }
    }

    function flushRender() {
        if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
        if (renderFallbackId) { clearTimeout(renderFallbackId); renderFallbackId = null; }
        if (pendingRoots) {
            renderTree(pendingRoots);
            pendingRoots = null;
            if (pendingUpdates.length) {
                const updates = pendingUpdates;
                pendingUpdates = [];
                applyUpdates(updates);
            }
        }
    }

    function applyUpdates(updates) {
        if (!updates) return;
        for (const update of updates) {
            const node = nodesById[update.id];
            const el = appEl.querySelector(`[data-wid="${update.id}"]`);
            if (!node || !el) continue;

            // Patch the cached node, then redraw it through the one code path
            // that knows this widget type. No per-prop DOM surgery here.
            node.props[update.prop] = update.value;
            applyCommonProps(el, node);
            applyWidgetUpdate(el, node);
            applyPaint(el, node);
        }
    }

    // ── Tree Renderer (atomic swap) ────────────────────────────

    function renderTree(roots) {
        if (!roots || roots.length === 0) return;

        // Remember which element is focused and its caret/selection
        const focused = saveFocus();

        // Rebuilt as reconcileNode visits every node; incremental `updates`
        // then patch these in place.
        nodesById = {};

        // Reconcile each root node with the DOM
        const reconciledRoots = [];
        for (const root of roots) {
            const el = reconcileNode(root);
            if (el) reconciledRoots.push(el);
        }

        // replaceChildren on appEl with the reconciled root elements
        appEl.replaceChildren(...reconciledRoots);

        // Restore focus + caret position
        restoreFocus(focused);
    }

    // ── Incremental DOM Reconciliation ──────────────────────────

    function reconcileNode(node) {
        if (!node || !node.type) return null;
        nodesById[node.id] = node;

        // Find if the element already exists in the document
        let el = appEl.querySelector(`[data-wid="${node.id}"]`);

        if (!el) el = createWidgetElement(node);

        applyCommonProps(el, node);
        applyWidgetUpdate(el, node);
        applyPaint(el, node);          // custom paintEvent output → <canvas>
        reconcileChildrenForNode(el, node);

        return el;
    }

    // visible / enabled / stylesheet / font / tooltip — shared by the reconcile
    // pass and the incremental-update pass.
    function applyCommonProps(el, node) {
        el.id = node.props.objectName || node.id;

        el.classList.toggle("widget-hidden", !node.props.visible);
        el.classList.toggle("widget-disabled", !node.props.enabled);
        if (el.disabled !== undefined) el.disabled = !node.props.enabled;

        applyStyleSheet(el, node);
        if (node.props.font) applyFont(el, node.props.font);
        if (node.props.tooltip) el.title = node.props.tooltip;
        else if (!WIDGETS[node.type] && !node.props.paint) {
            el.title = `${node.type}: not implemented by pysideweb`;
        } else el.removeAttribute("title");
    }

    function applyWidgetUpdate(el, node) {
        const spec = WIDGETS[node.type];
        if (spec && spec.update) spec.update(el, node);
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
                const newIcon = makeElement("span", "btn-icon");
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


    function updateSlider(el, node) {
        updateSpinBox(el, node);
        const valueLabel = el.querySelector(".slider-value");
        if (valueLabel) valueLabel.textContent = node.props.value ?? 0;
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
                const newText = makeElement("span", "progress-text");
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
            const tabItem = makeElement("div", "tab-item" + (i === currentIndex ? " active" : ""));

            if (tab.icon) {
                const icon = makeElement("span", "tab-icon");
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

        let pages = content.querySelectorAll(":scope > .tab-page");
        while (pages.length < tabs.length) {
            const page = makeElement("div", "tab-page");
            content.appendChild(page);
            pages = content.querySelectorAll(":scope > .tab-page");
        }
        while (pages.length > tabs.length) {
            pages[pages.length - 1].remove();
            pages = content.querySelectorAll(":scope > .tab-page");
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
                const newTitle = makeElement("span", "group-title");
                newTitle.textContent = node.props.title;
                el.prepend(newTitle);
            }
        } else if (title) {
            title.remove();
        }
    }

    function updateStackedWidget(el, node) {
        const currentIndex = node.props.currentIndex ?? 0;
        let pages = el.querySelectorAll(":scope > .stacked-page");
        
        while (pages.length < node.children.length) {
            const page = makeElement("div", "stacked-page");
            el.appendChild(page);
            pages = el.querySelectorAll(":scope > .stacked-page");
        }
        while (pages.length > node.children.length) {
            pages[pages.length - 1].remove();
            pages = el.querySelectorAll(":scope > .stacked-page");
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
            const row = makeElement("div", "list-item" + (i === currentRow ? " selected" : ""));

            if (item.icon) {
                const icon = makeElement("span", "item-icon");
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
            const item = makeElement("div", "menu-item");
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
            selStart: active.selectionStart ?? null,
            selEnd: active.selectionEnd ?? null,
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

    function makeElement(tag, className) {
        const el = document.createElement(tag);
        el.className = className;
        return el;
    }

    function createWidgetElement(node) {
        const spec = WIDGETS[node.type];
        const el = (spec ? spec.create : renderGenericWidget)(node);
        el.dataset.wid = node.id;
        if (!spec && !node.props.paint) el.classList.add("widget-unsupported");
        return el;
    }

    function renderWidget(node) {
        if (!node || !node.type) return null;
        const el = createWidgetElement(node);
        applyCommonProps(el, node);
        applyPaint(el, node);
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
                const spacer = makeElement("div", "stretch-spacer");
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

    // One entry per widget type: { create(node) -> el, update(el, node) }.
    // Used for element creation (reconcile + renderWidget), reconcile updates,
    // and incremental `updates` messages — so there's a single place that
    // knows how to draw each type, not three that drift apart.
    const WIDGETS = {
        QMainWindow:    { create: renderMainWindow,    update: updateMainWindow },
        QWidget:        { create: renderGenericWidget, update: null },
        QFrame:         { create: renderFrame,         update: null },
        QPushButton:    { create: renderPushButton,    update: updatePushButton },
        QLabel:         { create: renderLabel,         update: updateLabel },
        QLineEdit:      { create: renderLineEdit,      update: updateLineEdit },
        QTextEdit:      { create: renderTextEdit,      update: updateLineEdit },
        QComboBox:      { create: renderComboBox,      update: updateComboBox },
        QCheckBox:      { create: renderToggle,      update: updateCheckBox },
        QRadioButton:   { create: node => renderToggle(node, true),   update: updateCheckBox },
        QSlider:        { create: renderSlider,        update: updateSlider },
        QProgressBar:   { create: renderProgressBar,   update: updateProgressBar },
        QSpinBox:       { create: renderSpinBox,       update: updateSpinBox },
        QDoubleSpinBox: { create: renderSpinBox,       update: updateSpinBox },
        QTabWidget:     { create: renderTabWidget,     update: updateTabWidget },
        QGroupBox:      { create: renderGroupBox,      update: updateGroupBox },
        QScrollArea:    { create: renderScrollArea,    update: null },
        QStackedWidget: { create: renderStackedWidget, update: updateStackedWidget },
        QListWidget:    { create: renderListWidget,    update: updateListWidget },
        QDial:          { create: renderDial,          update: updateDial },
        QTableWidget:   { create: renderTableWidget,   update: buildTable },
        QTreeWidget:    { create: renderTreeWidget,    update: buildTree },
        QSplitter:      { create: renderSplitter,      update: updateSplitter },
        QMenuBar:       { create: renderMenuBar,       update: updateMenuBar },
        QStatusBar:     { create: renderStatusBar,     update: updateStatusBar },
        QDialog:        { create: renderDialog,        update: updateDialog },
    };

    function renderMainWindow(node) {
        const el = makeElement("div", "qmainwindow");
        const titleBar = makeElement("div", "window-title-bar");
        const dots = makeElement("div", "window-dots");
        dots.innerHTML = `<span class="window-dot close"></span><span class="window-dot minimize"></span><span class="window-dot maximize"></span>`;
        titleBar.appendChild(dots);
        const title = makeElement("span", "window-title");
        titleBar.appendChild(title);
        el.appendChild(titleBar);
        const content = makeElement("div", "window-content");
        el.appendChild(content);
        updateMainWindow(el, node);
        return el;
    }

    function renderGenericWidget(node) {
        const el = makeElement("div", "qwidget");

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
        const btn = makeElement("button", "qpushbutton");
        for (const cls of node.props.extraClasses || []) btn.classList.add(cls);
        btn.disabled = !node.props.enabled;
        updatePushButton(btn, node);
        btn.addEventListener("click", () => sendEvent(node.id, "clicked", null));
        return btn;
    }

    function renderLabel(node) {
        const el = makeElement("span", "qlabel");
        for (const cls of node.props.extraClasses || []) el.classList.add(cls);
        updateLabel(el, node);
        return el;
    }

    function renderLineEdit(node) {
        const input = makeElement("input", "qlineedit");
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
        const textarea = makeElement("textarea", "qtextedit");
        textarea.value = node.props.text || "";
        textarea.placeholder = node.props.placeholder || "";

        if (node.props.readOnly) textarea.readOnly = true;

        textarea.addEventListener("input", (e) => {
            sendEvent(node.id, "textChanged", e.target.value);
        });

        return textarea;
    }

    function renderComboBox(node) {
        const select = makeElement("select", "qcombobox");
        updateComboBox(select, node);
        select.addEventListener("change", e => {
            sendEvent(node.id, "currentIndexChanged", e.target.value);
        });
        return select;
    }

    function renderToggle(node, radio = false) {
        const label = makeElement("label", radio ? "qradiobutton" : "qcheckbox");
        const input = document.createElement("input");
        input.type = radio ? "radio" : "checkbox";
        if (radio) input.name = node.props.objectName ? `radio_${node.props.objectName}` : "radio_group";
        input.addEventListener("change", e => sendEvent(node.id, "toggled", e.target.checked));
        label.appendChild(input);
        label.appendChild(document.createElement("span"));
        updateCheckBox(label, node);
        return label;
    }


    function renderSlider(node) {
        const container = makeElement("div", "qslider");

        const input = document.createElement("input");
        input.type = "range";
        input.min = node.props.minimum ?? 0;
        input.max = node.props.maximum ?? 99;
        input.value = node.props.value ?? 0;
        input.step = node.props.singleStep ?? 1;

        const valueLabel = makeElement("span", "slider-value");
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
        const container = makeElement("div", "qprogressbar");
        const fill = makeElement("div", "progress-fill");
        container.appendChild(fill);
        updateProgressBar(container, node);
        return container;
    }

    function renderSpinBox(node) {
        const container = makeElement("div", "qspinbox");

        const input = document.createElement("input");
        input.type = "number";
        input.min = node.props.minimum ?? 0;
        input.max = node.props.maximum ?? 99;
        input.value = node.props.value ?? 0;
        input.step = node.props.singleStep ?? 1;

        const btnDown = makeElement("button", "spin-btn");
        btnDown.textContent = "\u2212";
        btnDown.addEventListener("click", () => {
            const newVal = Math.max(parseFloat(input.min), parseFloat(input.value) - parseFloat(input.step));
            input.value = newVal;
            sendEvent(node.id, "valueChanged", newVal);
        });

        const btnUp = makeElement("button", "spin-btn");
        btnUp.textContent = "+";
        btnUp.addEventListener("click", () => {
            const newVal = Math.min(parseFloat(input.max), parseFloat(input.value) + parseFloat(input.step));
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
        const el = makeElement("div", "qtabwidget");
        updateTabWidget(el, node);
        return el;
    }

    function renderGroupBox(node) {
        const el = makeElement("div", "qgroupbox");
        updateGroupBox(el, node);
        renderChildren(el, node);
        return el;
    }

    function renderScrollArea(node) {
        const el = makeElement("div", "qscrollarea");

        if (node.children && node.children.length > 0) {
            for (const child of node.children) {
                const childEl = renderWidget(child);
                if (childEl) el.appendChild(childEl);
            }
        }

        return el;
    }

    function renderStackedWidget(node) {
        const el = makeElement("div", "qstackedwidget");
        updateStackedWidget(el, node);
        return el;
    }

    function renderListWidget(node) {
        const el = makeElement("div", "qlistwidget");
        updateListWidget(el, node);
        return el;
    }

    // ── QDial ──────────────────────────────────────────────────

    const DIAL_MIN_ANGLE = -140;   // degrees, from vertical; matches Qt's look
    const DIAL_MAX_ANGLE = 140;

    function dialFraction(node) {
        const min = node.props.minimum ?? 0;
        const max = node.props.maximum ?? 99;
        const val = node.props.value ?? 0;
        return max > min ? (val - min) / (max - min) : 0;
    }

    function renderDial(node) {
        const el = makeElement("div", "qdial");
        el.innerHTML = `
            <svg viewBox="0 0 100 100" class="qdial-svg">
                <circle class="qdial-track" cx="50" cy="50" r="42"></circle>
                <path class="qdial-arc" fill="none"></path>
                <circle class="qdial-knob" r="7"></circle>
            </svg>
            <span class="qdial-value"></span>`;
        paintDial(el, node);

        const svg = el.querySelector("svg");
        const setFromPointer = (ev) => {
            const rect = svg.getBoundingClientRect();
            const cx = rect.left + rect.width / 2;
            const cy = rect.top + rect.height / 2;
            let deg = Math.atan2(ev.clientX - cx, cy - ev.clientY) * 180 / Math.PI;
            deg = Math.max(DIAL_MIN_ANGLE, Math.min(DIAL_MAX_ANGLE, deg));
            const frac = (deg - DIAL_MIN_ANGLE) / (DIAL_MAX_ANGLE - DIAL_MIN_ANGLE);
            const min = node.props.minimum ?? 0;
            const max = node.props.maximum ?? 99;
            const v = Math.round(min + frac * (max - min));
            sendEvent(node.id, "valueChanged", v);
        };
        let dragging = false;
        svg.addEventListener("pointerdown", (e) => {
            dragging = true; svg.setPointerCapture(e.pointerId); setFromPointer(e);
        });
        svg.addEventListener("pointermove", (e) => { if (dragging) setFromPointer(e); });
        svg.addEventListener("pointerup", (e) => {
            dragging = false; try { svg.releasePointerCapture(e.pointerId); } catch (_) {}
        });
        return el;
    }

    function paintDial(el, node) {
        const arc = el.querySelector(".qdial-arc");
        const knob = el.querySelector(".qdial-knob");
        if (!arc || !knob) return;   // SVG not built yet
        const frac = Math.max(0, Math.min(1, dialFraction(node)));
        const a0 = (DIAL_MIN_ANGLE - 90) * Math.PI / 180;
        const a1 = (DIAL_MIN_ANGLE + frac * (DIAL_MAX_ANGLE - DIAL_MIN_ANGLE) - 90) * Math.PI / 180;
        const r = 42;
        const x0 = 50 + r * Math.cos(a0), y0 = 50 + r * Math.sin(a0);
        const x1 = 50 + r * Math.cos(a1), y1 = 50 + r * Math.sin(a1);
        const large = (frac * (DIAL_MAX_ANGLE - DIAL_MIN_ANGLE)) > 180 ? 1 : 0;
        arc.setAttribute("d", `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`);
        const kr = 30;
        knob.setAttribute("cx", (50 + kr * Math.cos(a1)).toFixed(2));
        knob.setAttribute("cy", (50 + kr * Math.sin(a1)).toFixed(2));
        const label = el.querySelector(".qdial-value");
        if (label) label.textContent = node.props.value ?? 0;
    }

    function updateDial(el, node) {
        paintDial(el, node);
    }

    // ── QTableWidget ───────────────────────────────────────────

    function buildTable(el, node) {
        const cells = node.props.cells || [];
        const hHeaders = node.props.hHeaders || [];
        const vHeaders = node.props.vHeaders || [];
        const cols = node.props.cols ?? (cells[0] ? cells[0].length : 0);
        const curRow = node.props.currentRow ?? -1;
        const curCol = node.props.currentColumn ?? -1;

        const table = makeElement("table", "qtable");

        if (hHeaders.length || vHeaders.length) {
            const thead = document.createElement("thead");
            const tr = document.createElement("tr");
            if (vHeaders.length) tr.appendChild(document.createElement("th"));
            for (let c = 0; c < cols; c++) {
                const th = document.createElement("th");
                th.textContent = hHeaders[c] || "";
                tr.appendChild(th);
            }
            thead.appendChild(tr);
            table.appendChild(thead);
        }

        const tbody = document.createElement("tbody");
        cells.forEach((row, r) => {
            const tr = document.createElement("tr");
            if (vHeaders.length) {
                const th = document.createElement("th");
                th.scope = "row";
                th.textContent = vHeaders[r] || (r + 1);
                tr.appendChild(th);
            }
            for (let c = 0; c < cols; c++) {
                const cell = row[c];
                const td = document.createElement("td");
                td.textContent = cell ? (cell.text || "") : "";
                if (r === curRow && c === curCol) td.classList.add("selected");
                if (cell && cell.align) applyAlignment(td, cell.align);
                if (cell && cell.editable) {
                    td.contentEditable = "true";
                    td.addEventListener("blur", () => {
                        sendEvent(node.id, "cellChanged", { row: r, col: c, text: td.textContent });
                    });
                }
                td.addEventListener("click", () => {
                    sendEvent(node.id, "cellClicked", { row: r, col: c });
                });
                tr.appendChild(td);
            }
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);

        el.replaceChildren(table);
    }

    function renderTableWidget(node) {
        const el = makeElement("div", "qtablewidget");
        buildTable(el, node);
        return el;
    }


    // ── QTreeWidget ────────────────────────────────────────────

    function buildTree(el, node) {
        const headers = node.props.headers || [];
        const tree = node.props.tree || [];
        el.replaceChildren();

        if (headers.length) {
            const head = makeElement("div", "qtree-head");
            for (const h of headers) {
                const c = makeElement("span", "qtree-hcell");
                c.textContent = h;
                head.appendChild(c);
            }
            el.appendChild(head);
        }

        const makeRows = (items, path, depth, container) => {
            items.forEach((it, i) => {
                const here = path.concat(i);
                const rowEl = makeElement("div", "qtree-row" + (it.selected ? " selected" : ""));
                rowEl.style.paddingLeft = (depth * 16 + 6) + "px";

                const twisty = makeElement("span", "qtree-twisty");
                if (it.children && it.children.length) {
                    twisty.textContent = it.expanded ? "▾" : "▸";
                    twisty.addEventListener("click", (e) => {
                        e.stopPropagation();
                        sendEvent(node.id, "itemToggled", { path: here });
                    });
                } else {
                    twisty.classList.add("leaf");
                }
                rowEl.appendChild(twisty);

                (it.texts && it.texts.length ? it.texts : [""]).forEach((t, ci) => {
                    const cell = makeElement("span", "qtree-cell");
                    cell.textContent = t;
                    cell.addEventListener("click", () => {
                        sendEvent(node.id, "itemClicked", { path: here, col: ci });
                    });
                    rowEl.appendChild(cell);
                });

                container.appendChild(rowEl);
                if (it.children && it.children.length && it.expanded) {
                    makeRows(it.children, here, depth + 1, container);
                }
            });
        };

        const body = makeElement("div", "qtree-body");
        makeRows(tree, [], 0, body);
        el.appendChild(body);
    }

    function renderTreeWidget(node) {
        const el = makeElement("div", "qtreewidget");
        buildTree(el, node);
        return el;
    }


    function renderSplitter(node) {
        const el = makeElement("div", "qsplitter");

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
        const el = makeElement("div", "qmenubar");
        updateMenuBar(el, node);
        return el;
    }

    function renderStatusBar(node) {
        const el = makeElement("div", "qstatusbar");
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
        const overlay = makeElement("div", "qdialog-overlay");
        if (!node.props.visible) {
            overlay.classList.add("widget-hidden");
        }

        const dialog = makeElement("div", "qdialog");
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

    // Qt Style Sheets are translated to scoped CSS server-side (pysideweb/
    // qss.py). A widget arrives with node.props.styleSheetCss (already scoped
    // to `[data-wid="wN"]`) when its stylesheet has rule blocks, or just
    // node.props.styleSheet for a bare `prop: value` declaration list, which we
    // apply inline here.

    function applyStyleSheet(el, node) {
        const props = (node && node.props) || {};
        if (el._appliedStyles) {
            for (const prop of el._appliedStyles) el.style[prop] = "";
        }
        el._appliedStyles = [];
        removeScopedStyle(el);

        const css = props.styleSheetCss;
        if (css) {
            const style = document.createElement("style");
            style.dataset.qssFor = el.dataset.wid || node.id;
            style.textContent = css;
            document.head.appendChild(style);
            el._scopedStyle = style;
        } else if (props.styleSheet && props.styleSheet.indexOf("{") === -1) {
            applyDeclarations(el, props.styleSheet);
        }
    }

    let _appQssCache = null;
    function applyAppStyleSheet(css) {
        if (css === _appQssCache) return;
        _appQssCache = css;
        const existing = document.getElementById("pysideweb-app-qss");
        if (existing) existing.remove();
        if (!css) return;
        const style = document.createElement("style");
        style.id = "pysideweb-app-qss";
        style.textContent = css;   // already translated server-side
        document.head.appendChild(style);
    }

    function removeScopedStyle(el) {
        if (el._scopedStyle && el._scopedStyle.parentNode) {
            el._scopedStyle.parentNode.removeChild(el._scopedStyle);
        }
        el._scopedStyle = null;
        const wid = el.dataset && el.dataset.wid;
        if (wid) {
            document.head
                .querySelectorAll(`style[data-qss-for="${wid}"]`)
                .forEach(s => s.remove());
        }
    }

    function applyDeclarations(el, decls) {
        const re = /([a-zA-Z-]+)\s*:\s*([^;]+)/g;
        let m;
        while ((m = re.exec(decls)) !== null) {
            const cssProp = m[1].trim().replace(/-([a-z])/g, (_, c) => c.toUpperCase());
            try {
                el.style[cssProp] = m[2].trim();
                el._appliedStyles.push(cssProp);
            } catch (e) { /* ignore invalid */ }
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

    // ── Virtual painting: replay QPainter commands onto <canvas> ───
    //
    // A QWidget subclass that overrides paintEvent arrives with
    // node.props.paint = { commands: [...], w, h }. pysideweb/painting.py
    // records each QPainter call as one command; here we replay them onto a
    // 2D canvas context sized to the widget.

    const DASH_PATTERNS = {
        solid: [],
        none: [],
        dash: [6, 3],
        dot: [1, 3],
        dashdot: [6, 3, 1, 3],
        dashdotdot: [6, 3, 1, 3, 1, 3],
    };

    // QPainter.CompositionMode_* value → canvas globalCompositeOperation.
    // (see QPainter.CompositionMode_* in pysideweb/painting.py)
    const COMPOSITE_MODES = {
        0: "source-over", 1: "destination-over", 2: "clear", 3: "copy",
        4: "destination", 5: "source-in", 6: "destination-in", 7: "source-out",
        8: "destination-out", 9: "source-atop", 10: "destination-atop",
        11: "xor", 12: "lighter", 13: "multiply", 14: "screen", 15: "overlay",
        16: "darken", 17: "lighten", 18: "color-dodge", 19: "color-burn",
        20: "hard-light", 21: "soft-light", 22: "difference", 23: "exclusion",
    };

    function penStroke(ctx, pen) {
        if (!pen || !pen.color || pen.style === "none") return false;
        ctx.strokeStyle = pen.color;
        ctx.lineWidth = pen.width || 1;
        ctx.lineCap = pen.cap || "butt";
        ctx.lineJoin = pen.join || "miter";
        ctx.setLineDash((DASH_PATTERNS[pen.style] || []).map(v => v * (pen.width || 1)));
        return true;
    }

    function brushFill(ctx, brush) {
        if (!brush) return false;
        if (brush.gradient) {
            ctx.fillStyle = makeGradient(ctx, brush.gradient);
            return true;
        }
        if (!brush.color) return false;
        ctx.fillStyle = brush.color;
        return true;
    }

    function makeGradient(ctx, g) {
        let grad;
        if (g.type === "radial") {
            grad = ctx.createRadialGradient(g.fx, g.fy, 0, g.cx, g.cy, g.r || 1);
        } else {
            grad = ctx.createLinearGradient(g.x1, g.y1, g.x2, g.y2);
        }
        for (const [pos, color] of g.stops || []) {
            if (color) grad.addColorStop(Math.max(0, Math.min(1, pos)), color);
        }
        return grad;
    }

    function fontString(css) {
        if (!css) return "12px sans-serif";
        const parts = [];
        if (css.fontStyle) parts.push(css.fontStyle);
        if (css.fontWeight) parts.push(css.fontWeight);
        parts.push(css.fontSize || "12px");
        parts.push(css.fontFamily || "sans-serif");
        return parts.join(" ");
    }

    function replayPaint(ctx, commands) {
        let pen = { color: "#000", width: 1, style: "solid", cap: "butt", join: "miter" };
        let brush = { color: null, gradient: null };
        let font = null;

        const pathRect = (x, y, w, h) => { ctx.beginPath(); ctx.rect(x, y, w, h); };
        const paintPath = (doFill, doStroke, overrideBrush, overridePen) => {
            if (doFill && brushFill(ctx, overrideBrush || brush)) ctx.fill();
            if (doStroke && penStroke(ctx, overridePen || pen)) ctx.stroke();
        };

        for (const c of commands) {
            switch (c.op) {
                case "pen":
                    pen = c; break;
                case "brush":
                    brush = c; break;
                case "font":
                    font = c.css; ctx.font = fontString(font); break;
                case "opacity":
                    ctx.globalAlpha = c.value; break;
                case "composite":
                    ctx.globalCompositeOperation = COMPOSITE_MODES[c.mode] || "source-over";
                    break;
                case "save":
                    ctx.save(); break;
                case "restore":
                    ctx.restore(); break;
                case "translate":
                    ctx.translate(c.x, c.y); break;
                case "rotate":
                    ctx.rotate(c.deg * Math.PI / 180); break;
                case "scale":
                    ctx.scale(c.x, c.y); break;
                case "shear":
                    ctx.transform(1, c.y, c.x, 1, 0, 0); break;
                case "resetTransform":
                    ctx.setTransform(paintDpr, 0, 0, paintDpr, 0, 0); break;
                case "clipRect":
                    ctx.beginPath(); ctx.rect(c.x, c.y, c.w, c.h); ctx.clip(); break;
                case "resetClip":
                    break;
                case "drawLine":
                    ctx.beginPath(); ctx.moveTo(c.x1, c.y1); ctx.lineTo(c.x2, c.y2);
                    if (penStroke(ctx, pen)) ctx.stroke();
                    break;
                case "drawRect":
                    pathRect(c.x, c.y, c.w, c.h); paintPath(true, true); break;
                case "drawRoundedRect":
                    roundRectPath(ctx, c.x, c.y, c.w, c.h, c.rx, c.ry);
                    paintPath(true, true); break;
                case "fillRect":
                    pathRect(c.x, c.y, c.w, c.h);
                    if (c.brush) { if (brushFill(ctx, c.brush)) ctx.fill(); }
                    else if (c.color) { ctx.fillStyle = c.color; ctx.fill(); }
                    else if (brushFill(ctx, brush)) ctx.fill();
                    break;
                case "clearRect":
                    ctx.clearRect(c.x, c.y, c.w, c.h); break;
                case "drawEllipse":
                    ctx.beginPath();
                    ctx.ellipse(c.x + c.w / 2, c.y + c.h / 2, Math.abs(c.w / 2),
                        Math.abs(c.h / 2), 0, 0, Math.PI * 2);
                    paintPath(true, true); break;
                case "drawArc":
                    ctx.beginPath();
                    ctx.ellipse(c.cx, c.cy, Math.abs(c.rx), Math.abs(c.ry), 0,
                        c.start, c.end, c.anticlockwise);
                    if (penStroke(ctx, pen)) ctx.stroke();
                    break;
                case "drawPie":
                    ctx.beginPath(); ctx.moveTo(c.cx, c.cy);
                    ctx.ellipse(c.cx, c.cy, Math.abs(c.rx), Math.abs(c.ry), 0,
                        c.start, c.end, c.anticlockwise);
                    ctx.closePath(); paintPath(true, true); break;
                case "drawChord":
                    ctx.beginPath();
                    ctx.ellipse(c.cx, c.cy, Math.abs(c.rx), Math.abs(c.ry), 0,
                        c.start, c.end, c.anticlockwise);
                    ctx.closePath(); paintPath(true, true); break;
                case "drawPoint":
                    ctx.beginPath();
                    ctx.arc(c.x, c.y, (pen.width || 1) / 2, 0, Math.PI * 2);
                    if (pen.color) { ctx.fillStyle = pen.color; ctx.fill(); }
                    break;
                case "drawPolyline":
                    polyPath(ctx, c.pts, false);
                    if (penStroke(ctx, pen)) ctx.stroke();
                    break;
                case "drawPolygon":
                    polyPath(ctx, c.pts, true); paintPath(true, true); break;
                case "drawPath":
                    buildPath(ctx, c.segments);
                    paintPath(c.fill, c.stroke, c.brush, c.pen); break;
                case "drawText":
                    if (pen.color) ctx.fillStyle = pen.color;
                    ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
                    ctx.fillText(c.text, c.x, c.y);
                    break;
                case "drawTextRect":
                    drawTextInRect(ctx, c, pen);
                    break;
                case "drawImage":
                case "drawPixmap":
                    drawImageCmd(ctx, c);
                    break;
                default:
                    break;
            }
        }
    }

    function roundRectPath(ctx, x, y, w, h, rx, ry) {
        rx = Math.min(rx || 0, w / 2); ry = Math.min(ry || rx || 0, h / 2);
        ctx.beginPath();
        ctx.moveTo(x + rx, y);
        ctx.lineTo(x + w - rx, y);
        ctx.quadraticCurveTo(x + w, y, x + w, y + ry);
        ctx.lineTo(x + w, y + h - ry);
        ctx.quadraticCurveTo(x + w, y + h, x + w - rx, y + h);
        ctx.lineTo(x + rx, y + h);
        ctx.quadraticCurveTo(x, y + h, x, y + h - ry);
        ctx.lineTo(x, y + ry);
        ctx.quadraticCurveTo(x, y, x + rx, y);
        ctx.closePath();
    }

    function polyPath(ctx, pts, close) {
        ctx.beginPath();
        pts.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]));
        if (close) ctx.closePath();
    }

    function buildPath(ctx, segments) {
        ctx.beginPath();
        for (const s of segments) {
            switch (s[0]) {
                case "M": ctx.moveTo(s[1], s[2]); break;
                case "L": ctx.lineTo(s[1], s[2]); break;
                case "C": ctx.bezierCurveTo(s[1], s[2], s[3], s[4], s[5], s[6]); break;
                case "Q": ctx.quadraticCurveTo(s[1], s[2], s[3], s[4]); break;
                case "E": ctx.ellipse(s[1] + s[3] / 2, s[2] + s[4] / 2,
                    Math.abs(s[3] / 2), Math.abs(s[4] / 2), 0, 0, Math.PI * 2); break;
                case "Z": ctx.closePath(); break;
                default: break;
            }
        }
    }

    function drawTextInRect(ctx, c, pen) {
        const f = c.flags || 0;
        if (pen.color) ctx.fillStyle = pen.color;
        let tx = c.x, ty = c.y;
        if (f & 0x0004) { ctx.textAlign = "center"; tx = c.x + c.w / 2; }
        else if (f & 0x0002) { ctx.textAlign = "right"; tx = c.x + c.w; }
        else { ctx.textAlign = "left"; tx = c.x; }
        if (f & 0x0080) { ctx.textBaseline = "middle"; ty = c.y + c.h / 2; }
        else if (f & 0x0040) { ctx.textBaseline = "bottom"; ty = c.y + c.h; }
        else { ctx.textBaseline = "top"; ty = c.y; }
        ctx.fillText(c.text, tx, ty);
    }

    const _imgCache = {};
    function drawImageCmd(ctx, c) {
        if (!c.src) return;
        let img = _imgCache[c.src];
        if (!img) {
            img = new Image();
            img.src = c.src;
            _imgCache[c.src] = img;
            img.onload = () => scheduleRepaintAll();
        }
        if (img.complete && img.naturalWidth) {
            if (c.w && c.h) ctx.drawImage(img, c.x, c.y, c.w, c.h);
            else ctx.drawImage(img, c.x, c.y);
        }
    }

    let paintDpr = 1;
    const _paintedEls = new Set();

    function scheduleRepaintAll() {
        // An async image finished decoding — re-run every canvas we know about.
        for (const el of _paintedEls) {
            if (!el.isConnected) { _paintedEls.delete(el); continue; }
            if (el.__paintNode) applyPaint(el, el.__paintNode);
        }
    }

    function applyPaint(el, node) {
        const paint = node.props && node.props.paint;
        if (!paint) {
            const stale = el.querySelector(":scope > canvas.pysideweb-canvas");
            if (stale) stale.remove();
            return;
        }

        let canvas = el.querySelector(":scope > canvas.pysideweb-canvas");
        if (!canvas) {
            canvas = document.createElement("canvas");
            canvas.className = "pysideweb-canvas";
            el.insertBefore(canvas, el.firstChild);
        }

        paintDpr = window.devicePixelRatio || 1;
        const w = Math.max(1, paint.w || el.clientWidth || 300);
        const h = Math.max(1, paint.h || el.clientHeight || 150);
        canvas.width = w * paintDpr;
        canvas.height = h * paintDpr;
        canvas.style.width = w + "px";
        canvas.style.height = h + "px";

        const ctx = canvas.getContext("2d");
        ctx.setTransform(paintDpr, 0, 0, paintDpr, 0, 0);
        ctx.clearRect(0, 0, w, h);
        try {
            replayPaint(ctx, paint.commands || []);
        } catch (e) {
            console.warn("[pysideweb] paint replay error", e);
        }

        el.__paintNode = node;
        _paintedEls.add(el);
    }

    // ── Initialize ─────────────────────────────────────────────

    connect();

})();
