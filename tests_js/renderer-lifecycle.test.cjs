const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const {documentFixture} = require('./helpers/dom.cjs');

function renderer() {
    const fixture = documentFixture();
    const source = fs.readFileSync(path.join(__dirname, '../pysideweb/static/renderer.js'), 'utf8');
    // Expose existing entry points only inside this test VM; production has no
    // debug globals. Both factories and updates execute the real source.
    const context = {
        ...fixture, console, Node: {TEXT_NODE: 3},
        window: {location: {host: 'localhost:8765'}},
    };
    vm.runInNewContext(source.replace(/    connect\(\);\s*\n\}\)\(\);\s*$/,
        '    globalThis.renderer = {renderWidget, renderTree, applyUpdates};\n})();'), context);
    return {...context.renderer, app: fixture.app};
}

let id = 0;
function node(type, props = {}, children = []) {
    return {id: `w${++id}`, type, props: {visible: true, enabled: true, ...props}, children};
}

test('shared text factories preserve initial content and incremental updates', () => {
    for (const type of ['QLabel', 'QPushButton', 'QCheckBox', 'QRadioButton']) {
        const view = renderer();
        const data = node(type, {text: 'initial', checked: true});
        view.renderTree([data]);
        const el = view.app.querySelector(`[data-wid="${data.id}"]`);
        assert.equal(el.textContent, 'initial');
        view.applyUpdates([{id: data.id, prop: 'text', value: 'changed'}]);
        assert.equal(el.textContent, 'changed');
        if (type === 'QCheckBox' || type === 'QRadioButton') {
            assert.equal(el.querySelector('input').checked, true);
            assert.equal(typeof el.querySelector('input').events.change, 'function');
        }
    }
});

test('progress and list factories share state updates', () => {
    const view = renderer();
    const progress = node('QProgressBar', {value: 25, minimum: 0, maximum: 100});
    const list = node('QListWidget', {items: [{text: 'one'}, {text: 'two'}]});
    view.renderTree([progress, list]);
    assert.equal(view.app.querySelector('.progress-fill').style.width, '25%');
    assert.equal(view.app.querySelectorAll('.list-item').length, 2);
    view.applyUpdates([{id: progress.id, prop: 'value', value: 80}]);
    assert.equal(view.app.querySelector('.progress-fill').style.width, '80%');
});

for (const type of ['QTabWidget', 'QStackedWidget']) {
    test(`${type} can create, grow, and shrink pages`, () => {
        const view = renderer();
        const children = [node('QLabel', {text: 'one'}), node('QLabel', {text: 'two'})];
        const data = node(type, {currentIndex: 0}, children);
        const updateTabs = () => { data.props.tabs = data.children.map(child => ({text: child.id, widgetId: child.id})); };
        const selector = type === 'QTabWidget' ? '.tab-page' : '.stacked-page';
        updateTabs();
        view.renderTree([data]);
        assert.equal(view.app.querySelectorAll(selector).length, 2);
        data.children.push(node('QLabel', {text: 'three'}));
        updateTabs();
        view.renderTree([data]);
        assert.equal(view.app.querySelectorAll(selector).length, 3);
        data.children = data.children.slice(0, 1);
        updateTabs();
        view.renderTree([data]);
        assert.equal(view.app.querySelectorAll(selector).length, 1);
    });
}

test('fallback tooltip survives the shared common-property path', () => {
    const view = renderer();
    const unknown = node('ThirdPartyControl');
    const created = view.renderWidget(unknown);
    assert.equal(created.title, 'ThirdPartyControl: not implemented by pysideweb');
    view.renderTree([unknown]);
    assert.equal(view.app.children[0].title, created.title);
});

test('text-area server updates use the same text field as initial rendering', () => {
    const view = renderer();
    const data = node('QTextEdit', {text: 'before'});
    view.renderTree([data]);
    const el = view.app.querySelector(`[data-wid="${data.id}"]`);
    assert.equal(el.value, 'before');
    view.applyUpdates([{id: data.id, prop: 'text', value: 'after\nUnicode 日本語'}]);
    assert.equal(el.value, 'after\nUnicode 日本語');
});

test('double spin box buttons retain fractional steps and clamp at bounds', () => {
    const view = renderer();
    const data = node('QDoubleSpinBox', {minimum: 1, maximum: 1.5, value: 1.25, singleStep: 0.25});
    view.renderTree([data]);
    const el = view.app.querySelector(`[data-wid="${data.id}"]`);
    const [down, up] = el.querySelectorAll('button');
    const input = el.querySelector('input');
    up.events.click();
    assert.equal(input.value, 1.5);
    up.events.click();
    assert.equal(input.value, 1.5);
    down.events.click();
    assert.equal(input.value, 1.25);
    down.events.click();
    down.events.click();
    assert.equal(input.value, 1);
});

for (const type of ['QTabWidget', 'QStackedWidget']) {
    test(`${type} only counts its own pages when containers are nested`, () => {
        const view = renderer();
        const container = children => node(type, {
            currentIndex: 0, tabs: children.map(child => ({text: child.id, widgetId: child.id})),
        }, children);
        const inner = container([node('QLabel', {text: 'inner one'}), node('QLabel', {text: 'inner two'})]);
        const outer = container([inner, node('QLabel', {text: 'outer two'})]);
        const selector = type === 'QTabWidget' ? '.tab-page' : '.stacked-page';
        view.renderTree([outer]);
        for (let index = 0; index < 3; index++) {
            view.renderTree([outer]);
            view.applyUpdates([{id: outer.id, prop: 'currentIndex', value: index % 2}]);
            assert.equal(view.app.querySelectorAll(selector).length, 4);
            assert.ok(view.app.textContent.includes('inner two'));
            assert.ok(view.app.textContent.includes('outer two'));
        }
    });
}
