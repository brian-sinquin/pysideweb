// Small DOM model for renderer lifecycle tests; not an HTML/CSS implementation.
// Rich-text parsing and visual layout remain covered by the Chromium suite.
class Element {
    constructor(tag, nodeType = 1) {
        this.tagName = tag.toUpperCase();
        this.nodeType = nodeType;
        this.childNodes = [];
        this.parentElement = null;
        this.className = '';
        this.dataset = {};
        this.style = {};
        this.classList = {
            add: name => this.classList.toggle(name, true),
            remove: name => this.classList.toggle(name, false),
            toggle: (name, enabled) => {
                const names = new Set(this.className.split(/\s+/).filter(Boolean));
                const keep = enabled ?? !names.has(name);
                if (keep) names.add(name); else names.delete(name);
                this.className = [...names].join(' ');
                return keep;
            },
        };
    }
    get children() { return this.childNodes.filter(child => child.nodeType === 1); }
    get firstChild() { return this.childNodes[0] || null; }
    get textContent() { return this._text || this.childNodes.map(child => child.textContent).join(''); }
    set textContent(value) { this.replaceChildren(); this._text = String(value); }
    set innerHTML(value) {
        if (value !== '') throw new Error('HTML parsing needs a real browser');
        this.replaceChildren();
    }
    appendChild(child) {
        child.remove();
        child.parentElement = this;
        this.childNodes.push(child);
        return child;
    }
    prepend(child) { this.insertBefore(child, this.firstChild); }
    insertBefore(child, next) {
        child.remove();
        const index = this.childNodes.indexOf(next);
        if (index < 0) return this.appendChild(child);
        child.parentElement = this;
        this.childNodes.splice(index, 0, child);
        return child;
    }
    replaceChildren(...children) {
        for (const child of [...this.childNodes]) child.remove();
        this._text = '';
        for (const child of children) this.appendChild(child);
    }
    remove() {
        if (this.parentElement) {
            const siblings = this.parentElement.childNodes;
            siblings.splice(siblings.indexOf(this), 1);
            this.parentElement = null;
        }
    }
    removeAttribute(name) { delete this[name]; }
    addEventListener(name, callback) { (this.events ??= {})[name] = callback; }
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
    querySelectorAll(selector) {
        const result = new Set();
        for (let part of selector.split(/,\s*/)) {
            const direct = part.startsWith(':scope > ');
            part = part.replace(':scope > ', '');
            const visit = parent => {
                for (const child of parent.children) {
                    if (child.matches(part)) result.add(child);
                    if (!direct) visit(child);
                }
            };
            visit(this);
        }
        return [...result];
    }
    matches(selector) {
        const wid = selector.match(/^\[data-wid="(.+)"\]$/)?.[1];
        if (wid) return this.dataset.wid === wid;
        const excluded = selector.match(/:not\(\.([\w-]+)\)/)?.[1];
        selector = selector.replace(/:not\([^)]*\)/, '');
        const [tag, className] = selector.split('.');
        const classes = this.className.split(/\s+/);
        return (!tag || this.tagName === tag.toUpperCase()) &&
            (!className || classes.includes(className)) &&
            (!excluded || !classes.includes(excluded));
    }
}

function documentFixture() {
    const app = new Element('div');
    const head = new Element('head');
    let created = 0;
    return {
        app,
        document: {
            head, activeElement: null,
            getElementById: id => id === 'app' ? app : null,
            createElement: tag => {
                // Turn unbounded page-growth loops into a deterministic failure.
                if (++created > 500) throw new Error('element creation budget exceeded');
                return new Element(tag);
            },
            createTextNode: text => {
                const node = new Element('#text', 3);
                node.textContent = text;
                return node;
            },
        },
    };
}

module.exports = {documentFixture};
