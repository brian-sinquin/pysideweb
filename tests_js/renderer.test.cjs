// Execute the real renderer with a minimal DOM/transport boundary. Full layout
// and rich-text browser coverage belongs in the planned browser test suite.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../pysideweb/static/renderer.js'), 'utf8');

function renderer(protocol = 'http:') {
    const elements = new Map([['app', {}], ['connection-status', {}]]);
    let socket;
    class Socket {
        constructor(url) { this.url = url; socket = this; }
    }
    const document = {
        getElementById: id => elements.get(id),
        createElement: () => ({remove() { elements.delete(this.id); }}),
        head: {appendChild: element => elements.set(element.id, element)},
    };
    vm.runInNewContext(source, {
        window: {location: {host: 'localhost:8765', protocol}}, document,
        WebSocket: Socket, console,
        requestAnimationFrame: () => 1, setTimeout: () => 1,
    });
    return {
        socket, elements,
        receive: message => socket.onmessage({data: JSON.stringify(message)}),
    };
}

test('full-tree application CSS is applied, replaced, and cleared', () => {
    const app = renderer();
    const receive = css => app.receive({type: 'full_tree', roots: [], appStyleSheetCss: css});
    receive('#app .qlabel { color: red }');
    const first = app.elements.get('pysideweb-app-qss');
    assert.equal(first.textContent, '#app .qlabel { color: red }');
    receive('#app .qlabel { color: red }');
    assert.equal(app.elements.get('pysideweb-app-qss'), first);
    receive('#app { color: blue }');
    assert.equal(app.elements.get('pysideweb-app-qss').textContent, '#app { color: blue }');
    receive('');
    assert.equal(app.elements.has('pysideweb-app-qss'), false);
});

test('updates arriving before the deferred full-tree frame are preserved', () => {
    let frame;
    let socket;

    class Element {
        constructor(tagName = 'DIV') {
            this.tagName = tagName.toUpperCase();
            this.children = [];
            this.dataset = {};
            this.style = {};
            this.classList = {add() {}, remove() {}, toggle() {}};
        }
        appendChild(child) { this.children.push(child); child.parentElement = this; return child; }
        replaceChildren(...children) {
            this.children = children;
            for (const child of children) child.parentElement = this;
        }
        removeAttribute() {}
        querySelector(selector) {
            const wid = selector.match(/^\[data-wid="(.+)"\]$/)?.[1];
            if (!wid) return null;
            const stack = [...this.children];
            while (stack.length) {
                const child = stack.pop();
                if (child.dataset.wid === wid) return child;
                stack.push(...child.children);
            }
            return null;
        }
    }

    const app = new Element();
    const statusText = new Element('span');
    const status = new Element();
    status.querySelector = selector => selector === '.status-text' ? statusText : null;
    class Socket {
        constructor() { socket = this; }
    }
    Socket.OPEN = 1;
    const document = {
        activeElement: null,
        getElementById: id => id === 'app' ? app :
            (id === 'connection-status' ? status : null),
        createElement: tag => new Element(tag),
        head: {appendChild() {}, querySelectorAll: () => []},
    };
    vm.runInNewContext(source, {
        window: {location: {host: 'localhost:8765', protocol: 'http:'}},
        document, WebSocket: Socket, console,
        requestAnimationFrame: callback => { frame = callback; return 1; },
        cancelAnimationFrame() {}, setTimeout: () => 2, clearTimeout() {},
    });

    const receive = message => socket.onmessage({data: JSON.stringify(message)});
    receive({
        type: 'full_tree',
        appStyleSheetCss: '',
        roots: [{
            id: 'w1', type: 'QLabel', children: [],
            props: {text: 'before', visible: true, enabled: true, objectName: ''},
        }],
    });
    receive({type: 'updates', updates: [{id: 'w1', prop: 'text', value: 'after'}]});
    frame();

    assert.equal(app.querySelector('[data-wid="w1"]').textContent, 'after');
});
