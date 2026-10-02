/*
 * Regression-тест состояния кнопки «Скачать PDF» (node, без сборки и зависимостей):
 *
 *   A. в index.html у #pdfLink есть атрибут hidden;
 *   B. CSS не должен позволять классу .btn-secondary переопределять hidden-состояние:
 *      либо у правил, применимых к кнопке, вообще нет display,
 *      либо добавлен guard-правило вида `.btn-secondary[hidden] { display: none; }`;
 *   C. после сброса/ошибки href кнопки не должен оставаться URL предыдущего PDF,
 *      после успешного аудита href обязан указывать на отчёт именно этой даты.
 *
 * Запуск:  node tests/frontend/pdf_link_hidden_render.test.js
 * Выход   : 0 — пройдено, 1 — есть провалы.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..", "..");
const STATIC = path.join(ROOT, "apps", "web", "static");
const APP_JS = path.join(STATIC, "app.js");
const INDEX_HTML = path.join(STATIC, "index.html");
const STYLES_CSS = path.join(STATIC, "styles.css");

let failures = 0;
function check(name, condition, detail = "") {
  const ok = Boolean(condition);
  if (!ok) failures += 1;
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
}

/* ------------------------------------------------------------------ A. разметка */

console.log("A) разметка #pdfLink");
const html = fs.readFileSync(INDEX_HTML, "utf8");
const anchorTag = html.match(/<a\b[^>]*\bid="pdfLink"[^>]*>/i);
check("A1: #pdfLink объявлен как <a>", Boolean(anchorTag));
check("A2: у #pdfLink есть атрибут hidden", Boolean(anchorTag && /\bhidden\b/.test(anchorTag[0])), anchorTag ? anchorTag[0] : "элемент не найден");

/* ------------------------------------------------------------------ B. CSS-каскад */

console.log("\nB) CSS не переопределяет hidden-состояние");
const css = fs.readFileSync(STYLES_CSS, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

/* Минимальный разбор CSS: поднимаемся по скобкам, at-правила разворачиваем,
   чтобы получить пары «селектор — тело». */
function parseRules(source) {
  const rules = [];
  let selector = "";
  let depth = 0;
  let buffer = "";
  for (const ch of source) {
    if (depth === 0 && (ch === "{" || ch === "}")) {
      if (ch === "}") {
        // закрытие at-блока: его содержимое уже разобрано
        selector = "";
        buffer = "";
        continue;
      }
      selector = buffer.trim();
      buffer = "";
      depth = 1;
      continue;
    }
    if (depth === 1 && ch === "}") {
      const body = buffer.trim();
      if (selector && !selector.startsWith("@")) rules.push({ selector, body });
      selector = "";
      buffer = "";
      depth = 0;
      continue;
    }
    if (depth === 0 && ch !== "{" && ch !== "}") {
      buffer += ch;
      continue;
    }
    if (depth >= 1) {
      if (ch === "{") depth += 1;
      if (ch === "}") depth -= 1;
      if (depth >= 1) buffer += ch;
    }
  }
  return rules;
}

/* Кнопка: <a id="pdfLink" class="btn-secondary">. Совпадение проверяем по последнему
   compound-селектору (то, к чему применяется display): чужие id отсекаем, тег/классы
   кнопки — допускаем, наследники/предки не учитываем (консервативно). */
function lastCompound(selector) {
  const parts = selector.split(/\s*[>+~]\s*/);
  return parts[parts.length - 1].trim();
}

function compoundMatchesAnchor(compound) {
  const ids = compound.match(/#[\w-]+/g) || [];
  if (ids.some((id) => id.toLowerCase() !== "#pdflink")) return false;
  const types = (compound.match(/(^|[.#:\[])[a-zA-Z][\w-]*/g) || [])
    .filter((token) => !/^[.#]/.test(token) && !/^\[/.test(token) && !/^(hover|focus|active|visited|disabled|first-child|last-child|not|is|where)$/i.test(token));
  const tagOk = types.length === 0 || types.some((t) => t.toLowerCase() === "a");
  const classOk = !/\.btn-secondary/.test(compound) || true;
  const idOk = ids.length === 0 || ids.some((id) => id.toLowerCase() === "#pdflink");
  const explicit = /#pdflink/i.test(compound) || /\.btn-secondary/.test(compound);
  const generic = /^(a|\*|\[hidden\]|a:root|\[hidden\][\w-]*)$/.test(compound.replace(/\s+/g, ""));
  return tagOk && classOk && idOk && (explicit || generic);
}

const rules = parseRules(css);
const displayRules = rules.filter(
  (r) => /\bdisplay\s*:/.test(r.body) && compoundMatchesAnchor(lastCompound(r.selector)),
);
const guardRules = rules.filter(
  (r) => /\bdisplay\s*:\s*none\b/i.test(r.body)
    && /\[hidden\]/.test(r.selector)
    && compoundMatchesAnchor(lastCompound(r.selector)),
);

check(
  "B1: hidden кнопки не перебивается display-правилами",
  displayRules.length === 0 || guardRules.length > 0,
  displayRules.length
    ? `правила с display, применимые к кнопке: ${displayRules.map((r) => `${r.selector.replace(/\s+/g, " ")}{display}`).join(" | ")}; guard: ${guardRules.length ? guardRules.map((r) => r.selector).join(" | ") : "нет"}`
    : "display-правил, применимых к кнопке, нет",
);
check(
  "B2: для .btn-secondary задан hidden-guard (`.btn-secondary[hidden]{display:none}`) либо display убран",
  guardRules.some((r) => /\.btn-secondary\s*\[hidden\]/.test(r.selector.replace(/\s+/g, "")) && /\[hidden\]/.test(r.selector))
    || !displayRules.some((r) => /\.btn-secondary/.test(r.selector)),
  guardRules.length ? `guard: ${guardRules.map((r) => r.selector.replace(/\s+/g, " ")).join(" | ")}` : "guard-правило не найдено",
);

/* ------------------------------------------------- C. поведение href после сброса */

console.log("\nC) href после сброса/ошибки и после успешного аудита");

function makeEl(tag) {
  const el = {
    tagName: tag,
    children: [],
    className: "",
    dataset: {},
    hidden: false,
    disabled: false,
    checked: false,
    href: "",
    value: undefined,
    _ownText: "",
    _listeners: {},
    appendChild(child) {
      this.children.push(child);
      if (this.tagName === "select" && child.tagName === "option" && !this.value) this.value = child.value;
      return child;
    },
    append(...cs) { cs.forEach((c) => this.appendChild(c)); },
    replaceChildren(...cs) { this.children = cs.slice(); this._ownText = ""; },
    addEventListener(type, fn) { this._listeners[type] = fn; },
  };
  Object.defineProperty(el, "textContent", {
    get() { return this.children.length ? this.children.map((c) => c.textContent).join(" ") : this._ownText; },
    set(v) { this._ownText = String(v); this.children = []; },
  });
  return el;
}

const ACCOUNT = "00000000-0000-4000-8000-000000000001";
const metric = (key, value, status) => ({ key, owner: "finance", value, status });

/* Фикстура повторяет shapes, которые отдаёт backend (см. audit_screen_states.test.js):
   renderAudit обязан отработать без исключений. */
function auditFixture(operationalDate, options = {}) {
  const traces = [
    { component: "cogs", status: "missing" },
    { component: "tax", status: "missing" },
  ];
  const withArtifact = options.withArtifact !== false;
  const artifact = withArtifact ? { pdf_path: `runtime/reports/${ACCOUNT}/${operationalDate}/report.pdf` } : {};
  return {
    account_id: ACCOUNT,
    seller_id: "seller_demo",
    operational_date: operationalDate,
    data_origin: "real_wb_data",
    ingestion_status: "ingested:daily+finance_detail",
    finance_status: "partial",
    audit_status: "partial",
    diagnostics: ["diagnostic: technical line"],
    raw_references: { objects: [{ object_type: "sales", object_id: "abc", payload_sha256: "a".repeat(64) }] },
    report_artifact: artifact,
    analysis: {
      status: "partial",
      diagnostics: [],
      products: [],
      artifact,
      pipeline: {
        report_payload: {
          metrics: [
            metric("sales", "2", "complete"),
            metric("orders", null, "missing"),
            metric("available_stock", null, "missing"),
            metric("funnel_opens", "211", "complete"),
            metric("funnel_carts", "11", "complete"),
            metric("funnel_orders", "0", "complete"),
            metric("realized_revenue", "1500", "available"),
            metric("advertising", "-90", "available"),
            metric("cogs", null, "missing"),
            metric("tax", null, "missing"),
            metric("net_profit", null, "partial"),
            metric("profit_margin", null, "partial"),
            metric("advertising_direct_sku", "90", "available"),
          ],
        },
        financial_flow: {
          financial_result: { component_traces: traces },
          finality_assessment: { finality: "unknown", status: "partial" },
        },
      },
    },
  };
}

const registry = new Map();
let serverMode = "ok";        // "ok" | "500"
let payloadDate = "2026-09-30";
let payloadWithArtifact = true;
let auditCalls = 0;

const ok = (payload) => ({ ok: true, status: 200, json: async () => payload });
const fail = (status, detail) => ({ ok: false, status, json: async () => ({ detail }) });

function tagFor(id) {
  if (id.endsWith("Select")) return "select";
  if (id.endsWith("Input")) return "input";
  if (id.endsWith("Btn")) return "button";
  if (id === "pdfLink") return "a";
  return "div";
}

const context = {
  console,
  URLSearchParams,
  Object, Math, Number, String, JSON, Array, Date, Error, Boolean, RegExp, setTimeout, Map, Promise,
  document: {
    getElementById(id) { if (!registry.has(id)) registry.set(id, makeEl(tagFor(id))); return registry.get(id); },
    createElement(tag) { return makeEl(tag); },
  },
  fetch: async (url) => {
    const target = String(url);
    if (target.startsWith("/api/accounts") && !target.includes("/financial-settings")) {
      return ok({ accounts: [{ account_id: ACCOUNT, seller_id: "seller_demo", active: true }] });
    }
    if (target.includes("/financial-settings")) {
      return ok({ tax_rate: null, tax_rate_unit: "percent", tax_basis: "realized_revenue", finality_confirmed: false, cogs: [], operational_date: payloadDate });
    }
    auditCalls += 1;
    if (serverMode === "500") return fail(500, "Internal Server Error");
    return ok(auditFixture(payloadDate, { withArtifact: payloadWithArtifact }));
  },
};

vm.createContext(context);
vm.runInContext(fs.readFileSync(APP_JS, "utf8"), context, { filename: "app.js" });

const settle = () => new Promise((resolve) => setTimeout(resolve, 60));
const el = (id) => registry.get(id);
const submit = () => el("auditForm")._listeners.submit({ preventDefault() {} });

(async () => {
  await settle();   // boot(): loadAccounts + авто-аудит D-1

  const expectedUrl = (date) => `/api/reports/${ACCOUNT}/${date}/report.pdf`;
  const isStalePdfUrl = (href) => typeof href === "string" && href.includes("/api/reports/");

  check("C1: успешный аудит 2026-09-30 — кнопка показана", el("pdfLink").hidden === false);
  check(
    "C2: успешный аудит 2026-09-30 — href ведёт на отчёт этой даты",
    el("pdfLink").href === expectedUrl("2026-09-30"),
    `href = "${el("pdfLink").href}"`,
  );

  serverMode = "500";
  payloadDate = "2026-09-10";
  await submit();
  await settle();

  check("C3: ошибка аудита — кнопка скрыта", el("pdfLink").hidden === true);
  check(
    "C4: ошибка аудита — старый URL предыдущего PDF не остался",
    !isStalePdfUrl(el("pdfLink").href),
    `href = "${el("pdfLink").href}"`,
  );

  serverMode = "ok";
  payloadDate = "2026-09-10";
  await submit();
  await settle();

  check("C5: новый успешный аудит — кнопка снова показана", el("pdfLink").hidden === false);
  check(
    "C6: href обновлён на дату нового аудита",
    el("pdfLink").href === expectedUrl("2026-09-10"),
    `href = "${el("pdfLink").href}"`,
  );

  payloadDate = "2026-09-29";
  payloadWithArtifact = false;   // успешный ответ без report_artifact.pdf_path
  await submit();
  await settle();

  check("C7: аудит без report_artifact — кнопка скрыта", el("pdfLink").hidden === true);
  check(
    "C8: аудит без report_artifact — старый URL не остался",
    !isStalePdfUrl(el("pdfLink").href),
    `href = "${el("pdfLink").href}"`,
  );

  check("C9: запросы к backend реально выполнялись", auditCalls >= 4, `audit calls = ${auditCalls}`);

  console.log(`\nИтог: ${failures === 0 ? "все проверки пройдены" : `провалено ${failures}`} (A/B/C pdf-link)`);
  process.exit(failures === 0 ? 0 : 1);
})().catch((error) => {
  console.error("Тест упал с исключением:", error);
  process.exit(1);
});
