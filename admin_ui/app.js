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

function createField(definition) {
  const label = document.createElement("label");
  label.textContent = definition.label + (definition.required ? " *" : "");
  let input;
  if (definition.kind === "textarea" || definition.kind === "json" || definition.kind === "permission") {
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
  operation.fields.forEach((field) => form.append(createField(field)));
  const button = document.createElement("button");
  button.type = "submit";
  button.textContent = "执行";
  form.append(button);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    button.disabled = true;
    showResult(`正在调用：${operation.title}`, {});
    try {
      const payload = {};
      for (const field of operation.fields) {
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
