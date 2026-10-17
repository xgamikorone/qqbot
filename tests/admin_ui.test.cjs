// Run with: node --test tests/admin_ui.test.cjs
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function element(tag) {
  return {
    tag, children: [], dataset: {}, value: "", listeners: {}, classList: { add() {} },
    append(...children) { children.forEach((child) => { child.parent = this; this.children.push(child); }); },
    addEventListener(event, handler) { this.listeners[event] = handler; },
    setAttribute() {},
    remove(index) {
      if (index !== undefined) this.children.splice(index, 1);
      else this.parent.children = this.parent.children.filter((child) => child !== this);
    },
    replaceChildren() { this.children = []; },
    querySelector(selector) { return descendants(this).find((child) => selector.split(",").map((part) => part.trim()).includes(child.tag)); },
  };
}

function descendants(root) {
  return root.children.flatMap((child) => [child, ...descendants(child)]);
}

function plain(value) { return JSON.parse(JSON.stringify(value)); }

function loadUI() {
  const context = vm.createContext({
    document: { createElement: element, querySelector: () => element("div") },
    sessionStorage: { getItem: () => "" },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../admin_ui/app.js"), "utf8"), context);
  return context;
}

test("required selects show an empty prompt and labeled API values", () => {
  const ui = loadUI();
  const label = ui.createField({
    name: "scope", label: "生效场景", kind: "select", required: true,
    choices: [["c2c", "单聊（c2c）"], ["group", "群聊（group）"]],
  });
  const select = label.children[0];
  assert.equal(label.textContent, "生效场景 *");
  assert.equal(select.tag, "select");
  assert.equal(select.name, "scope");
  assert.equal(select.required, true);
  assert.deepEqual(Array.from(select.children, (option) => option.value), ["", "c2c", "group"]);
  assert.equal(select.children[0].textContent, "请选择…");
  assert.equal(select.children[1].textContent, "单聊（c2c）");
});

test("optional selects can be left unspecified", () => {
  const select = loadUI().createField({ name: "optional", kind: "select", choices: [], required: false }).children[0];
  assert.equal(select.required, false);
  assert.equal(select.children[0].value, "");
  assert.equal(select.children[0].textContent, "不指定（使用默认值）");
});

test("ordinary fields still use inputs and textareas", () => {
  const ui = loadUI();
  assert.equal(ui.createField({ name: "panel_id", kind: "text" }).children[0].tag, "input");
  assert.equal(ui.createField({ name: "panel", kind: "json" }).children[0].tag, "textarea");
});

test("panel editor builds configuration without writing JSON", () => {
  const editor = loadUI().createField({ kind: "panel", label: "面板配置" });
  const row = descendants(editor).find((node) => node.className === "panel-item");
  const inputs = descendants(row).filter((node) => node.tag === "input");
  inputs[0].value = "/help";
  inputs[1].value = "使用帮助";
  inputs[2].checked = true;
  assert.equal(inputs[3].disabled, true);
  assert.deepEqual(plain(editor.readValue()), { items: [{ type: "command", name: "/help", desc: "使用帮助", only_admin: true }], remark: "" });
  const type = row.querySelector("select");
  type.value = "link";
  type.listeners.change();
  inputs[3].value = "https://example.com";
  assert.equal(inputs[3].required, true);
  assert.equal(editor.readValue().items[0].link, "https://example.com");
});

test("panel editor limits rows and allows removing all entries", () => {
  const editor = loadUI().createField({ kind: "panel", label: "面板配置" });
  const add = descendants(editor).find((node) => node.tag === "button" && node.textContent.startsWith("添加"));
  for (let i = 0; i < 25; i++) add.listeners.click();
  assert.equal(editor.readValue().items.length, 20);
  assert.equal(add.disabled, true);
  descendants(editor).filter((node) => node.textContent === "移除此项").forEach((button) => button.listeners.click());
  assert.equal(editor.readValue().items.length, 0);
  assert.equal(add.disabled, false);
});

test("imported JSON preserves version and unknown fields across mode changes", () => {
  const editor = loadUI().createField({ kind: "panel", label: "面板配置" });
  const mode = editor.querySelector("select");
  const raw = editor.querySelector("textarea");
  mode.value = "json";
  mode.listeners.change();
  assert.equal(raw.disabled, false);
  const imported = { version: 4, future: "keep", remark: "备注", items: [{ type: "link", name: "网站", desc: "说明", only_admin: false, link: "https://example.com", extra: "keep" }] };
  raw.value = JSON.stringify(imported);
  mode.value = "visual";
  mode.listeners.change();
  assert.deepEqual(plain(editor.readValue()), imported);
  mode.value = "json";
  mode.listeners.change();
  assert.deepEqual(JSON.parse(raw.value), imported);
});

test("invalid or unsupported JSON stays in advanced mode without losing text", () => {
  const editor = loadUI().createField({ kind: "panel", label: "面板配置" });
  const mode = editor.querySelector("select");
  const raw = editor.querySelector("textarea");
  mode.value = "json";
  mode.listeners.change();
  for (const text of ["{broken", '{"items":[{"type":"future"}]}']) {
    raw.value = text;
    mode.value = "visual";
    mode.listeners.change();
    assert.equal(mode.value, "json");
    assert.equal(raw.value, text);
    assert.equal(raw.disabled, false);
    assert.ok(descendants(editor).find((node) => node.className === "error").textContent);
  }
});
