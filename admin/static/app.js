const state = { token: sessionStorage.getItem("botAdminToken") || "", operations: [] };

const loginView = document.querySelector("#login-view");
const consoleView = document.querySelector("#console-view");
const resultStatus = document.querySelector("#result-status");
const resultOutput = document.querySelector("#result-output");

function api(path, options = {}) {
  return fetch(path, {
    ...options,
    headers: { "Authorization": `Bearer ${state.token}`, "Content-Type": "application/json", ...(options.headers || {}) },
  });
}

function showResult(status, value) {
  resultStatus.textContent = status;
  resultOutput.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

async function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function panelConfiguration(original, rows, remark) {
  return {
    ...original,
    items: rows.map((row) => {
      const item = { ...row.original, type: row.type, name: row.name, desc: row.desc, only_admin: row.only_admin };
      if (row.type === "link") item.link = row.link;
      else delete item.link;
      return item;
    }),
    remark,
  };
}

function parsePanel(text) {
  const value = JSON.parse(text);
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("面板配置必须是 JSON 对象");
  return value;
}

function createPanelEditor(definition) {
  const root = document.createElement("fieldset");
  root.className = "panel-editor";
  const legend = document.createElement("legend");
  legend.textContent = definition.label;
  const modeField = createField({ name: "", label: "编辑方式", kind: "select", choices: [["visual", "表单编辑（推荐）"], ["json", "高级 JSON / 粘贴已有配置"]] });
  const mode = modeField.querySelector("select");
  mode.remove(0);
  mode.value = "visual";
  const visual = document.createElement("fieldset");
  visual.className = "panel-visual";
  const list = document.createElement("div");
  list.className = "panel-items";
  const remarkField = createField({ name: "", label: "面板备注（仅自己可见）", kind: "text" });
  const remark = remarkField.querySelector("input");
  remark.maxLength = 255;
  const add = document.createElement("button");
  add.type = "button";
  add.className = "quiet";
  const hint = document.createElement("p");
  hint.className = "editor-hint";
  hint.textContent = "按添加顺序展示，最多 20 项。指令名称即点击后填入聊天框的文本。修改会完整覆盖，请先导入原配置。";
  const rawField = createField({ name: "", label: "面板 JSON（无需外层 panel）", kind: "json" });
  const raw = rawField.querySelector("textarea");
  raw.disabled = true;
  rawField.hidden = true;
  const error = document.createElement("p");
  error.className = "error";
  error.setAttribute("role", "alert");
  let original = {};
  let rows = [];
  function refresh() {
    add.disabled = rows.length >= 20;
    add.textContent = `添加一项（${rows.length}/20）`;
  }
  function addRow(item = {}) {
    if (rows.length >= 20) return;
    const block = document.createElement("div");
    block.className = "panel-item";
    const controls = {};
    const definitions = [
      { name: "type", label: "类型", kind: "select", choices: [["command", "指令"], ["link", "链接"]] },
      { name: "name", label: "指令文本 / 链接名称", kind: "text", placeholder: "/help" },
      { name: "desc", label: "功能说明", kind: "text" },
      { name: "only_admin", label: "仅管理员可用", kind: "boolean" },
      { name: "link", label: "跳转链接", kind: "text", placeholder: "https://example.com" },
    ];
    const fields = {};
    for (const def of definitions) {
      const field = createField({ ...def, name: "", required: false });
      const input = field.querySelector("input, select");
      controls[def.name] = input;
      fields[def.name] = field;
      if (def.kind === "boolean") input.checked = item[def.name] === true;
      else input.value = item[def.name] || (def.name === "type" ? "command" : "");
      block.append(field);
    }
    controls.type.remove(0);
    controls.name.required = true;
    controls.desc.maxLength = 30;
    controls.link.type = "url";
    function updateType() {
      const isLink = controls.type.value === "link";
      controls.link.disabled = !isLink;
      controls.link.required = isLink;
      fields.link.hidden = !isLink;
    }
    controls.type.addEventListener("change", updateType);
    updateType();
    const row = { original: item, controls };
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "quiet";
    remove.textContent = "移除此项";
    remove.addEventListener("click", () => { rows = rows.filter((entry) => entry !== row); block.remove(); refresh(); });
    block.append(remove);
    rows.push(row);
    list.append(block);
    refresh();
  }
  function readVisual() {
    return panelConfiguration(original, rows.map((row) => ({
      original: row.original,
      ...Object.fromEntries(Object.entries(row.controls).map(([key, input]) => [key, key === "only_admin" ? input.checked : input.value])),
    })), remark.value);
  }
  mode.addEventListener("change", () => {
    error.textContent = "";
    try {
      if (mode.value === "json") raw.value = JSON.stringify(readVisual(), null, 2);
      else {
        const value = parsePanel(raw.value);
        const items = value.items || [];
        if (!Array.isArray(items) || items.length > 20 || items.some((item) => !item || !["command", "link"].includes(item.type))) throw new Error("表单仅支持最多 20 项指令或链接，请在高级 JSON 中编辑此配置");
        original = value;
        rows = [];
        list.replaceChildren();
        remark.value = value.remark || "";
        items.forEach(addRow);
        refresh();
      }
    } catch (failure) {
      mode.value = "json";
      error.textContent = failure.message;
    }
    const isRaw = mode.value === "json";
    visual.disabled = isRaw;
    visual.hidden = isRaw;
    raw.disabled = !isRaw;
    raw.required = isRaw;
    rawField.hidden = !isRaw;
  });
  add.addEventListener("click", () => addRow());
  visual.append(hint, list, add, remarkField);
  root.append(legend, modeField, visual, rawField, error);
  addRow();
  root.readValue = () => mode.value === "json" ? parsePanel(raw.value) : readVisual();
  return root;
}

function createField(definition) {
  if (definition.kind === "panel") return createPanelEditor(definition);
  const label = document.createElement("label");
  label.textContent = definition.label + (definition.required ? " *" : "");
  let input;
  if (definition.kind === "select") {
    input = document.createElement("select");
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = definition.required ? "请选择…" : "不指定（使用默认值）";
    input.append(empty);
    for (const [value, caption] of definition.choices || []) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = caption;
      input.append(option);
    }
  } else if (definition.kind === "textarea" || definition.kind === "json" || definition.kind === "permission") {
    input = document.createElement("textarea");
  } else {
    input = document.createElement("input");
    input.type = definition.kind === "number" ? "number" : definition.kind === "boolean" ? "checkbox" : definition.kind === "file" ? "file" : "text";
  }
  input.name = definition.name;
  input.dataset.kind = definition.kind;
  input.required = Boolean(definition.required);
  input.placeholder = definition.placeholder || "";
  if (definition.kind === "file") input.accept = "image/*";
  if (definition.kind === "boolean") label.classList.add("checkbox");
  label.append(input);
  return label;
}

function createOperationCard(operation) {
  const article = document.createElement("article");
  article.className = "operation-card";
  article.innerHTML = `<h4></h4><p></p>`;
  article.querySelector("h4").textContent = operation.title;
  article.querySelector("p").textContent = operation.description;
  const form = document.createElement("form");
  const editors = new Map();
  operation.fields.forEach((field) => {
    const control = createField(field);
    if (field.kind === "panel") editors.set(field.name, control);
    form.append(control);
  });
  const button = document.createElement("button");
  button.type = "submit";
  button.textContent = "执行";
  form.append(button);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const panelId = form.elements.namedItem("panel_id");
    const detail = panelId ? `\n面板 ID：${panelId.value}` : "";
    if (operation.confirmation && !window.confirm(operation.confirmation + detail)) return;
    button.disabled = true;
    showResult(`正在调用：${operation.title}`, {});
    try {
      const payload = {};
      for (const field of operation.fields) {
        if (field.kind === "panel") { payload[field.name] = editors.get(field.name).readValue(); continue; }
        const input = form.elements.namedItem(field.name);
        if (field.kind === "boolean") { if (input.checked) payload[field.name] = true; continue; }
        if (field.kind === "file") { if (input.files[0]) payload[field.name] = await readFileAsDataUrl(input.files[0]); continue; }
        if (input.value !== "") payload[field.name] = input.value;
      }
      const response = await api(`/api/operations/${operation.id}`, { method: "POST", body: JSON.stringify(payload) });
      const body = await response.text();
      if (!response.ok) throw new Error(body || `请求失败 (${response.status})`);
      showResult(`调用成功：${operation.title}`, JSON.parse(body));
    } catch (error) {
      showResult(`调用失败：${operation.title}`, error.message);
    } finally {
      button.disabled = false;
    }
  });
  article.append(form);
  return article;
}

function renderOperations() {
  const query = document.querySelector("#search-input").value.trim().toLowerCase();
  const grouped = new Map();
  state.operations.filter((operation) => !query || `${operation.title} ${operation.description} ${operation.category}`.toLowerCase().includes(query)).forEach((operation) => {
    if (!grouped.has(operation.category)) grouped.set(operation.category, []);
    grouped.get(operation.category).push(operation);
  });
  const root = document.querySelector("#operation-list");
  root.replaceChildren();
  grouped.forEach((operations, category) => {
    const section = document.createElement("section");
    section.className = "operation-group";
    const heading = document.createElement("h3");
    heading.textContent = category;
    const grid = document.createElement("div");
    grid.className = "operation-grid";
    operations.forEach((operation) => grid.append(createOperationCard(operation)));
    section.append(heading, grid);
    root.append(section);
  });
}

async function loadConsole() {
  const [statusResponse, operationsResponse] = await Promise.all([api("/api/status"), api("/api/operations")]);
  if (!statusResponse.ok || !operationsResponse.ok) throw new Error("管理令牌无效或 Bot 控制台尚未启动");
  const status = await statusResponse.json();
  const body = await operationsResponse.json();
  state.operations = body.operations;
  document.querySelector("#operation-count").textContent = status.operations;
  loginView.classList.add("hidden");
  consoleView.classList.remove("hidden");
  renderOperations();
}

document.querySelector("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  state.token = document.querySelector("#token-input").value;
  try {
    await loadConsole();
    sessionStorage.setItem("botAdminToken", state.token);
  } catch (error) {
    document.querySelector("#login-error").textContent = error.message;
  }
});
document.querySelector("#search-input").addEventListener("input", renderOperations);
document.querySelector("#refresh-button").addEventListener("click", () => loadConsole().catch((error) => showResult("刷新失败", error.message)));
document.querySelector("#logout-button").addEventListener("click", () => { sessionStorage.removeItem("botAdminToken"); state.token = ""; consoleView.classList.add("hidden"); loginView.classList.remove("hidden"); });
document.querySelector("#clear-result").addEventListener("click", () => showResult("选择并执行一个操作后，结果会显示在这里。", {}));
if (state.token) loadConsole().catch(() => sessionStorage.removeItem("botAdminToken"));
