import assert from "node:assert/strict";

import { test } from "node:test";

const { EntryList, ROW, visibleRange } = await import(new URL("js/listview.js", process.env.GEN3TL_WEB_ROOT_URL));

const HEIGHT = 900;

const WINDOW = Math.ceil(HEIGHT / ROW) + 4;

const DRAFT = 15000;

const UNBOUND = 25829;

const idOf = (p) => `s${String(p).padStart(5, "0")}`;

function fakeList() {
  return {
    scrollTop: 0,
    clientHeight: 0,
    listeners: {},
    addEventListener(ev, fn) { this.listeners[ev] = fn; },
    show(height = HEIGHT) {
      this.clientHeight = height;
    },
    hide() {
      this.clientHeight = 0;
      this.scrollTop = 0;
    },
  };
}

function fakeSpace() {
  return {
    style: { height: "" },
    rows: [],
    replaceChildren(...rows) {
      this.rows = rows;
    },
  };
}

function page(count = 0) {
  const list = fakeList();
  const space = fakeSpace();
  const view = new EntryList(list, space, (p) => ({ p, id: idOf(p) }));
  view.setCount(count);
  return { list, space, view };
}

const positions = (space) => space.rows.map((r) => r.p);

test("the range covers the viewport and nothing without one", () => {
  assert.deepEqual(visibleRange(0, 0, UNBOUND), [0, 0]); // a hidden view
  assert.deepEqual(visibleRange(0, HEIGHT, UNBOUND), [0, WINDOW]);
  assert.deepEqual(visibleRange(100 * ROW, HEIGHT, UNBOUND), [96, 120]); // overscan both ways
  assert.deepEqual(visibleRange(0, HEIGHT, 0), [0, 0]); // an empty filter
  // a scroll past the end clamps to the last window
  assert.deepEqual(visibleRange((UNBOUND + 5) * ROW, HEIGHT, UNBOUND), [UNBOUND - 20, UNBOUND]);
});

test("reload: the list fills once the Texts view is visible", () => {
  // loadLanguage hides the view; setView alone shows the list.
  const { list, space, view } = page(UNBOUND);
  assert.equal(space.style.height, `${UNBOUND * ROW}px`); // the scrollbar spans the catalog
  view.render();
  assert.deepEqual(space.rows, []); // hidden: nothing, not four rows
  list.show();
  assert.deepEqual(view.shown(0), [0, WINDOW]);
  assert.deepEqual(positions(space), [...Array(WINDOW).keys()]);
});

test("a ROM profile change fills the list of the new catalog before any click", () => {
  const { list, space, view } = page(DRAFT);
  list.show();
  view.shown(0);
  assert.equal(space.rows.length, WINDOW);
  // the profile changes: view hidden, count and rows follow
  list.hide();
  view.setCount(UNBOUND);
  view.render();
  assert.deepEqual(positions(space), [...Array(WINDOW).keys()]); // not four rows
  assert.equal(space.style.height, `${UNBOUND * ROW}px`);
  list.show();
  view.shown(0);
  assert.deepEqual(positions(space), [...Array(WINDOW).keys()]);
  // scrolling reaches the last entry of the catalog
  list.scrollTop = (UNBOUND - 1) * ROW;
  const [, last] = view.render();
  assert.equal(last, UNBOUND);
  assert.equal(positions(space).at(-1), UNBOUND - 1);
});

test("the restored entry is in view once the view appears", () => {
  const { list, space, view } = page(UNBOUND);
  view.render(); // hidden: no rows, no scroll
  assert.equal(list.scrollTop, 0);
  list.show();
  const pos = 1200; // the entry named in the URL
  view.shown(pos);
  assert.ok(list.scrollTop <= pos * ROW && pos * ROW < list.scrollTop + list.clientHeight);
  assert.ok(positions(space).includes(pos));
  assert.equal(positions(space)[0], Math.floor(list.scrollTop / ROW) - 4); // the rows match the scroll
});

test("a search with no hits clears the rows of the previous render", () => {
  // an empty result leaves no rows in the space
  const { list, space, view } = page(UNBOUND);
  list.show();
  view.shown(0);
  assert.equal(space.rows.length, WINDOW);
  view.setCount(0);
  assert.deepEqual(view.render(), [0, 0]);
  assert.deepEqual(space.rows, []);
  assert.equal(space.style.height, "0px");
  // a hidden list with entries keeps its rows
  view.setCount(UNBOUND);
  view.shown(0);
  list.hide();
  view.render();
  assert.equal(space.rows.length, WINDOW);
});

test("a render while another view is shown keeps its rows", () => {
  // a check ending under the Pictures view renders the list.
  // the rows stay until the Texts view shows.
  const { list, space, view } = page(UNBOUND);
  list.show();
  view.shown(0);
  list.hide();
  view.render();
  assert.deepEqual(positions(space), [...Array(WINDOW).keys()]);
  list.show();
  view.shown(0);
  assert.deepEqual(positions(space), [...Array(WINDOW).keys()]);
});

test("a filter that shortens the list renders the rows that remain", () => {
  const { list, space, view } = page(UNBOUND);
  list.show();
  list.scrollTop = (UNBOUND - 1) * ROW;
  view.render();
  // a search leaves ten entries; the scroll stays briefly
  view.setCount(10);
  assert.equal(space.style.height, `${10 * ROW}px`);
  assert.deepEqual(view.render(), [0, 10]); // the clamp, not an empty list
  assert.deepEqual(positions(space), [...Array(10).keys()]);
});
