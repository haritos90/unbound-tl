import { existsSync, readFileSync } from "node:fs";

import { createRequire } from "node:module";

let JSDOM = null;

try { ({ JSDOM } = createRequire(import.meta.url)("jsdom")); }
catch (error) { if (error.code !== "MODULE_NOT_FOUND") throw error; }

export const NEEDS_DOM = JSDOM ? false : "jsdom is unavailable";

export function domPage(context, page, hash = "") {
  const dom = new JSDOM(readFileSync(new URL(`${page}.html`, process.env.GEN3TL_WEB_ROOT_URL), "utf8"), {
    url: `https://site.test/${page === "index" ? "" : page}${hash}`, pretendToBeVisual: true,
  });
  const win = dom.window;
  const keys = ["window", "document", "location", "history", "localStorage", "getComputedStyle", "requestAnimationFrame", "fetch"];
  const saved = keys.map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]);
  for (const key of keys.filter((key) => key !== "fetch")) {
    const value = key === "window" ? win : typeof win[key] === "function" ? win[key].bind(win) : win[key];
    Object.defineProperty(globalThis, key, { value, configurable: true, writable: true });
  }
  win.scrollTo = (x, y) => { win.scrollX = x; win.scrollY = y; };
  Object.defineProperty(win.HTMLElement.prototype, "clientHeight", { get: () => 348 });
  win.HTMLCanvasElement.prototype.getContext = () => null;
  context.after(() => {
    win.close();
    for (const [key, descriptor] of saved) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else delete globalThis[key];
    }
  });
  return win;
}

const UNBOUND_DATASET = new URL("../../data/pokedex/pokedex.json", import.meta.url);

const { decodeDataset } = await import(new URL("js/pokedexstore.js", process.env.GEN3TL_WEB_ROOT_URL));

/** A tracked dataset file as the page decodes it. */
export const trackedDataset = (name) => decodeDataset(JSON.parse(readFileSync(new URL(name, UNBOUND_DATASET), "utf8")));

export const UNBOUND = existsSync(UNBOUND_DATASET) ? trackedDataset("pokedex.json") : null;

export const NEEDS_UNBOUND = UNBOUND ? false : "no Unbound project at the repository root";

export const TRAINER_DIFFICULTY = {
  settings: ["difficult", "vanilla", "expert", "insane"],
  default: 0, order: [1, 0, 2, 3], labels: ["Difficult", "Vanilla", "Expert", "Insane"],
};

export const STANDALONE_LABELS = {
  labels: { "Flinch chance": "s0000001@B_ATK_NAME_WITH_PREFIX+", sleep: "s0000002",
    paralysis: "s0000003", burn: "s0000004", poison: "s0000005", Sentence: "s0000001" },
  texts: [
    ["s0000001", "{B_ATK_NAME_WITH_PREFIX} flinched!", "{B_ATK_NAME_WITH_PREFIX} вздрагивает!"],
    ["s0000002", "sleep", "сон"], ["s0000003", "paralysis", "паралич"],
    ["s0000004", "burn", "ожог"], ["s0000005", "poison", "отравление"],
  ],
  languages: [
    { code: "ru", translated: true, labels: ["Вздрагивает", "Сон", "Паралич", "Ожог", "Отравление"] },
    ...["en", "es", "de", "fr"].map((code) => ({ code, translated: false,
      labels: ["Flinched", "Sleep", "Paralysis", "Burn", "Poison"] })),
  ],
};

export const FLINCH_MOVES = {
  13: 1, 23: 31, 27: 31, 29: 31, 44: 31, 125: 11, 127: 21,
  157: 31, 158: 11, 173: 31, 239: 21, 252: 100, 290: 31,
  302: 31, 310: 31, 326: 11, 356: 31, 367: 21, 382: 31,
  401: 21, 408: 31, 413: 31, 420: 1, 431: 11, 432: 11,
  433: 11, 486: 31, 624: 31, 673: 31, 737: 21, 751: 31,
};

export function projectLabelEntries(code) {
  const root = new URL("../../", import.meta.url);
  const projects = readFileSync(new URL("projects.toml", root), "utf8").split(/^\[\[project\]\]\s*$/m);
  const value = (block, key) => JSON.parse(block.match(new RegExp(`^${key} = (".*")$`, "m"))[1]);
  const language = code === "en" ? value(projects[0], "language") : code;
  const project = projects.slice(1).find((block) => value(block, "language") === language);
  const policy = new URL(value(project, "policy"), new URL(`${value(project, "root")}/`, root));
  const path = new URL("pokedex-labels.po", policy);
  const po = readFileSync(path, "utf8");
  return Object.fromEntries([...po.matchAll(/^msgctxt ("page:[^"]+")\nmsgid (".*")\nmsgstr (".*")$/gm)]
    .map(([, key, english, translated]) => [JSON.parse(key), [JSON.parse(english), JSON.parse(translated)]]));
}

export function flinchLabels(code) {
  return Object.fromEntries(Object.entries(projectLabelEntries(code)).filter(([key]) => key.startsWith("page:mechanics:flinch:")));
}

class Node {
  constructor(doc) {
    this.ownerDocument = doc;
    this.parentNode = null;
  }

  get nextSibling() {
    const k = this.parentNode?.childNodes;
    return k ? k[k.indexOf(this) + 1] ?? null : null;
  }
}

class Text extends Node {
  constructor(doc, data) {
    super(doc);
    this.nodeType = 3;
    this.data = data;
  }

  get textContent() {
    return this.data;
  }
}

class Element extends Node {
  constructor(doc, tag) {
    super(doc);
    this.nodeType = 1;
    this.tagName = tag.toUpperCase();
    this.childNodes = [];
    this.dataset = {};
    this.className = "";
    this.title = "";
    this.contentEditable = "inherit";
  }

  get firstChild() {
    return this.childNodes[0] ?? null;
  }

  append(...kids) {
    for (const k of kids) {
      const n = typeof k === "string" ? new Text(this.ownerDocument, k) : k;
      n.parentNode = this;
      this.childNodes.push(n);
    }
  }

  replaceChildren(...kids) {
    this.childNodes = [];
    this.append(...kids);
  }

  prepend(...kids) {
    this.replaceChildren(...kids, ...this.childNodes);
  }

  get textContent() {
    return this.childNodes.map((c) => c.textContent).join("");
  }

  set textContent(t) {
    this.replaceChildren(t);
  }

  contains(n) {
    for (let x = n; x; x = x.parentNode) if (x === this) return true;
    return false;
  }
}

export function fakeDocument() {
  const doc = {
    createElement: (tag) => new Element(doc, tag),
    createTextNode: (data) => new Text(doc, data),
  };
  return doc;
}

export function stubPage(context, page, hash = "", source = null) {
  const doc = fakeDocument(), create = doc.createElement;
  const matches = (node, selector) => {
    if (selector.startsWith(".")) return node.className.split(" ").includes(selector.slice(1));
    const attr = selector.match(/^(\w+)?\[([\w-]+)(?:="([^"]*)")?\]$/);
    if (attr) {
      const value = attr[2].startsWith("data-")
        ? node.dataset[attr[2].slice(5).replace(/-([a-z])/g, (_, char) => char.toUpperCase())] ?? null
        : node.getAttribute(attr[2]);
      return (!attr[1] || node.tagName === attr[1].toUpperCase()) && value !== null
        && (attr[3] === undefined || value === attr[3]);
    }
    return node.tagName === selector.toUpperCase();
  };
  doc.createElement = (tag) => {
    const node = create(tag), attrs = new Map();
    Object.assign(node, { value: "", hidden: false, disabled: false,
      style: { setProperty(key, value) { this[key] = String(value); }, getPropertyValue(key) { return this[key] ?? ""; } },
      scrollTop: 0, clientHeight: 0,
      listeners: {}, classList: { toggle() {}, add() {}, remove() {} },
      addEventListener(event, fn) { this.listeners[event] = fn; },
      setAttribute(key, value) {
        attrs.set(key, String(value));
        if (key === "class") this.className = String(value);
        if (key.startsWith("data-")) this.dataset[key.slice(5).replace(/-([a-z])/g, (_, char) => char.toUpperCase())] = String(value);
      },
      getAttribute(key) { return key === "class" ? this.className || null : attrs.get(key) ?? null; },
      hasAttribute(key) { return attrs.has(key); },
      removeAttribute(key) {
        attrs.delete(key);
        if (key.startsWith("data-")) delete node.dataset[key.slice(5).replace(/-([a-z])/g, (_, char) => char.toUpperCase())];
      },
      querySelectorAll(selector) { return this.children.flatMap((child) =>
        [...(matches(child, selector) ? [child] : []), ...child.querySelectorAll(selector)]); },
      querySelector(selector) { return this.querySelectorAll(selector)[0] ?? null; },
      closest(selector) { return matches(this, selector) ? this : this.parentNode?.closest?.(selector) ?? null; },
      cloneNode(deep = false) {
        const copy = doc.createElement(tag);
        for (const [key, value] of attrs) copy.setAttribute(key, value);
        copy.namespaceURI = this.namespaceURI;
        if (deep) copy.append(...this.childNodes.map((child) => child.nodeType === 3
          ? doc.createTextNode(child.data) : child.cloneNode(true)));
        return copy;
      },
    });
    Object.defineProperties(node, {
      children: { get: () => node.childNodes.filter((child) => child.nodeType === 1) },
      options: { get: () => node.querySelectorAll("option") },
      attributes: { get: () => [...attrs].map(([name, value]) => ({ name, value })) },
    });
    if (tag === "template") node.content = doc.createElement("fragment");
    return node;
  };
  doc.createElementNS = (namespace, tag) => Object.assign(doc.createElement(tag), { namespaceURI: namespace });
  const nodes = [], ids = new Map();
  const html = source ?? readFileSync(new URL(`${page}.html`, process.env.GEN3TL_WEB_ROOT_URL), "utf8");
  const element = (tag, attributes) => {
    const node = doc.createElement(tag);
    for (const attr of attributes.matchAll(/\s([\w-]+)(?:="([^"]*)")?/g)) {
      const value = attr[2] ?? "";
      node.setAttribute(attr[1], value);
      if (attr[1] === "id") ids.set(value, node);
      if (attr[1].startsWith("data-")) {
        node.dataset[attr[1].slice(5).replace(/-([a-z])/g, (_, char) => char.toUpperCase())] = value;
      }
    }
    node.hidden = /\bhidden\b/.test(attributes);
    return node;
  };
  // Static controls need their parsed descendants.
  const remainder = html.replace(/<(header|footer)\b[^>]*data-site-(?:mast|footer)[^>]*>[^]*?<\/\1>|<template\b[^>]*>[^]*?<\/template>/g, (fragment) => {
    const stack = [];
    for (const token of fragment.match(/<[^>]+>|[^<]+/g)) {
      if (token.startsWith("</")) stack.pop();
      else if (token.startsWith("<")) {
        const [, tag, attributes] = token.match(/^<([\w-]+)([^>]*)>/);
        const node = element(tag, attributes);
        if (tag === "svg" || stack.at(-1)?.namespaceURI === "http://www.w3.org/2000/svg") {
          node.namespaceURI = "http://www.w3.org/2000/svg";
        }
        if (stack.length) stack.at(-1).append(node);
        else nodes.push(node);
        if (!token.endsWith("/>")) stack.push(node.content ?? node);
      } else stack.at(-1)?.append(token);
    }
    return "";
  });
  for (const match of remainder.matchAll(/<([a-z][a-z0-9]*)\b([^>]*)>/g)) {
    nodes.push(element(match[1], match[2]));
  }
  const walk = (node) => [node, ...node.children.flatMap(walk)];
  const all = () => nodes.flatMap(walk);
  Object.assign(doc, { baseURI: "https://site.test/", URL: `https://site.test/${page === "index" ? "" : page}`,
    body: doc.createElement("body"),
    documentElement: doc.createElement("html"), listeners: {},
    getElementById: (id) => ids.get(id) ?? null,
    querySelector: (selector) => nodes.find((node) => node.tagName === selector.toUpperCase()) ?? null,
    querySelectorAll: (selector) => /^\[data-[\w-]+\]$/.test(selector) || selector === "a[href]"
      ? all().filter((node) => matches(node, selector)) : [],
    addEventListener(event, fn) { this.listeners[event] = fn; },
  });
  const location = { hash }, storage = fakeStorage();
  const history = { state: null,
    replaceState(state, _title, hash) { this.state = state; location.hash = hash; },
    pushState(state, title, hash) { this.replaceState(state, title, hash); },
  };
  const values = { document: doc, window: { addEventListener() {} }, location, history,
    localStorage: storage, requestAnimationFrame: (fn) => fn(), fetch: undefined,
    Option: function(text, value) { return Object.assign(doc.createElement("option"), { textContent: text, value }); } };
  const saved = Object.keys(values).map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]);
  for (const [key, value] of Object.entries(values)) Object.defineProperty(globalThis, key,
    { value, configurable: true, writable: true });
  context.after(() => {
    for (const [key, descriptor] of saved) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else delete globalThis[key];
    }
  });
  return { $: doc.getElementById, storage, choose(code) {
    const button = { dataset: { siteLang: code }, closest: (selector) => selector === "[data-site-lang]" ? button : null };
    doc.listeners.click({ target: button });
  } };
}

export function fakeFetch(files) {
  const f = async (url) => {
    f.calls.push(url);
    if (!(url in files)) return { ok: false, status: 404, json: async () => null };
    return { ok: true, status: 200, json: async () => structuredClone(files[url]) };
  };
  f.calls = [];
  return f;
}

export function fakeStorage(broken = false) {
  const m = new Map();
  return {
    map: m,
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => {
      if (broken) throw new Error("QuotaExceededError");
      m.set(k, String(v));
    },
    removeItem: (k) => m.delete(k),
  };
}
