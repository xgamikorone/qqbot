// Run with: node --test tests/admin_ui.test.cjs
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function element(tag) {
  return {
    tag, children: [], dataset: {}, classList: { add() {} },
    append(child) { this.children.push(child); },
    addEventListener() {},
  };
}

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
