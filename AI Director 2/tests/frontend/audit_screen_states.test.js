/*
 * Regression-тест состояний экрана аудита (node, без сборки и зависимостей):
 *
 *   успешный аудит -> запрос с HTTP 500 -> старые цифры обязаны исчезнуть
 *   -> виден только error state -> «Повторить» -> данные снова показаны
 *
 * Запуск:  node tests/frontend/audit_screen_states.test.js
 * Выход   : 0 — пройдено, 1 — есть провалы.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..", "..");
const APP_JS = path.join(ROOT, "apps", "web", "static", "app.js");

function makeEl(tag) {
  const el = {
    tagName: tag,
    children: [],
    className: "",
    dataset: {},
    hidden: false,
    disabled: false,
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

function auditFixture(revenue, options = {}) {
  const traces = options.traces === undefined
    ? [
        { component: "cogs", status: "missing" },
        { component: "tax", status: "missing" },
      ]
    : options.traces;
  const netProfit = options.netProfit === undefined ? null : options.netProfit;  // метрики cogs/tax держим согласованными с traces, как это делает backend
  const traceStatus = Object.fromEntries(traces.map((trace) => [trace.component, trace.status]));
  const metric = (key, value, status) => ({ key, owner: "finance", value, status });
  return {
    account_id: "62b0754c-d359-4072-b432-239bcc0856f9",
    seller_id: "seller_Sergey",
    operational_date: "2026-09-02",
    data_origin: "real_wb_data",
    ingestion_status: "ingested:daily+finance_detail",
    finance_status: options.auditStatus ? "complete" : "partial",
    audit_status: options.auditStatus || "partial",
    diagnostics: ["diagnostic: technical line"],
    raw_references: { objects: [{ object_type: "sales", object_id: "abc", payload_sha256: "a".repeat(64) }] },
    report_artifact: { pdf_path: "runtime/reports/x/report.pdf" },
    analysis: {
      status: "partial",
      diagnostics: [],
      products: options.products || [],
      artifact: { pdf_path: "runtime/reports/x/report.pdf" },
      pipeline: {
        report_payload: {
          metrics: [
            metric("sales", "2", "complete"),
            metric("orders", null, "missing"),
            metric("available_stock", null, "missing"),
            metric("funnel_opens", "211", "complete"),
            metric("funnel_carts", "11", "complete"),
            metric("funnel_orders", "0", "complete"),
            metric("realized_revenue", String(revenue), "available"),
            metric("advertising", "-77.04", "available"),
            metric("cogs", traceStatus.cogs === "available" ? "500" : null, traceStatus.cogs || "missing"),
            metric("tax", traceStatus.tax === "available" ? "54" : null, traceStatus.tax || "missing"),
            metric("net_profit", netProfit === null ? null : String(netProfit), netProfit === null ? "partial" : "available"),
            metric("profit_margin", null, "partial"),
            metric("advertising_direct_sku", "77.04", "available"),
            ...(options.extraMetrics || []).map(([key, value, status]) => metric(key, value, status)),
          ],
        },
        financial_flow: {
          financial_result: {
            component_traces: traces,
          },
          finality_assessment: { finality: options.finality || "unknown", status: options.auditStatus || "partial" },
        },
      },
    },
  };
}

const registry = new Map();
let serverMode = "ok";
let revenue = 1439;
let custom = null;
let auditCalls = 0;
let settingsCalls = 0;

/*
 * Заглушка backend'а пользовательских параметров: хранит объявления продавца и
 * пересчитывает аудит так же, как это делает настоящий Finance Kernel —
 * то есть только по сохранённым значениям.
 */
let settingsStore = { tax_rate: null, tax_rate_unit: "percent", tax_basis: "realized_revenue", finality_confirmed: false, cogs: [] };
let soldProducts = [];

const ok = (payload) => ({ ok: true, status: 200, json: async () => payload });
const fail = (status, detail) => ({ ok: false, status, json: async () => ({ detail }) });

function settingsSnapshot() {
  return { ...settingsStore, operational_date: "2026-09-02" };
}

function dynamicAudit() {
  if (custom) return custom;
  const traces = [
    { component: "cogs", status: settingsStore.cogs.length > 0 ? "available" : "missing" },
    { component: "tax", status: settingsStore.tax_rate !== null ? "available" : "missing" },
  ];
  const complete = settingsStore.cogs.length > 0 && settingsStore.tax_rate !== null && settingsStore.finality_confirmed;
  return auditFixture(revenue, {
    traces,
    netProfit: complete ? 862 : null,
    products: soldProducts,
    auditStatus: complete ? "complete" : "partial",
    finality: complete ? "final" : "unknown",
  });
}

function putTaxRate(body) {
  const raw = body.tax_rate;
  if (typeof raw !== "string" || raw.trim() === "" || !Number.isFinite(Number(raw.replace(",", ".")))) {
    return fail(400, "«Налоговая ставка» должно быть числом");
  }
  if (Number(raw.replace(",", ".")) < 0) return fail(400, "Налоговая ставка не может быть отрицательной");
  settingsStore.tax_rate = raw;
  return ok(settingsSnapshot());
}

function putCogs(body) {
  if (typeof body.sku !== "string" || !/^\d+$/.test(body.sku)) return fail(400, "Артикул товара должен содержать только цифры");
  const raw = body.cogs_per_unit;
  if (typeof raw !== "string" || raw.trim() === "" || !Number.isFinite(Number(raw.replace(",", ".")))) {
    return fail(400, "«Себестоимость» должно быть числом");
  }
  if (Number(raw.replace(",", ".")) < 0) return fail(400, "Себестоимость не может быть отрицательной");
  settingsStore.cogs = [{ sku: body.sku, cogs_per_unit: raw, seller_sku: body.seller_sku || null }];
  return ok(settingsSnapshot());
}

function putFinality(body) {
  settingsStore.finality_confirmed = Boolean(body.confirmed);
  return ok(settingsSnapshot());
}

/* id -> тег: у <select> значение появляется только после добавления option,
   поэтому заглушка обязана знать настоящие теги из index.html. */
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
  fetch: async (url, options) => {
    const target = String(url);
    if (target.startsWith("/api/accounts") && !target.includes("/financial-settings")) {
      return { ok: true, status: 200, json: async () => ({ accounts: [{ account_id: "62b0754c-d359-4072-b432-239bcc0856f9", seller_id: "seller_Sergey", active: true }] }) };
    }
    if (target.includes("/financial-settings")) {
      settingsCalls += 1;
      const method = ((options && options.method) || "GET").toUpperCase();
      const body = options && options.body ? JSON.parse(options.body) : {};
      if (method !== "PUT") return ok(settingsSnapshot());
      if (target.endsWith("/tax")) return putTaxRate(body);
      if (target.endsWith("/cogs")) return putCogs(body);
      if (target.endsWith("/finality")) return putFinality(body);
      return fail(404, "неизвестный параметр");
    }
    auditCalls += 1;
    if (serverMode === "500") {
      return { ok: false, status: 500, json: async () => ({ detail: "Internal Server Error" }) };
    }
    if (serverMode === "500-empty") {
      return { ok: false, status: 500, json: async () => { throw new Error("not json"); } };
    }
    return { ok: true, status: 200, json: async () => dynamicAudit() };
  },
};

vm.createContext(context);
vm.runInContext(fs.readFileSync(APP_JS, "utf8"), context, { filename: "app.js" });

const settle = () => new Promise((resolve) => setTimeout(resolve, 60));
const el = (id) => registry.get(id);
const rows = (id) => (el(id)?.children || []).map((r) => `${r.children[0]?.textContent || ""}${r.children[1] ? ": " + r.children[1].textContent : ""}`);
// toLocaleString("ru-RU") вставляет неразрывные пробелы — для сравнений нормализуем их
const text = (id) => (el(id) ? el(id).textContent.trim().replace(/[\u00A0\u202F]/g, " ") : "(нет элемента)");

let failures = 0;
function check(name, condition, detail = "") {
  const ok = Boolean(condition);
  if (!ok) failures += 1;
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
}

(async () => {
  await settle();

  console.log("1) первый успешный аудит");
  check("dashboard виден", el("dashboard").hidden === false);
  check("выручка отображена", text("kpiRevenue") === "1 439 ₽", text("kpiRevenue"));
  check("главный вывод собран", text("verdictHeadline") === "11 корзин → 0 заказов", text("verdictHeadline"));
  check("severity-чип заполнен текстом", text("verdictSeverityText") === "Критическая проблема", text("verdictSeverityText"));
  check("воронка отрендерена", el("funnelSteps").children.length === 5);
  check("PDF-ссылка доступна", el("pdfLink").hidden === false);

  console.log("\n2) новый запрос падает с HTTP 500");
  serverMode = "500";
  revenue = 999;
  await el("auditForm")._listeners.submit({ preventDefault() {} });
  await settle();

  check("dashboard скрыт", el("dashboard").hidden === true);
  check("баннер ошибки показан", el("errorBanner").hidden === false);
  check("текст ошибки из API", text("errorDetail") === "Internal Server Error", text("errorDetail"));
  check("loading скрыт", el("loadingState").hidden === true);
  check("старая выручка очищена", text("kpiRevenue") === "", `"${text("kpiRevenue")}"`);
  check("старые продажи очищены", text("kpiSales") === "", `"${text("kpiSales")}"`);
  check("старый вывод очищен", text("verdictHeadline") === "", `"${text("verdictHeadline")}"`);
  check("старая воронка очищена", el("funnelSteps").children.length === 0);
  check("старые финансы очищены", el("financeRows").children.length === 0);
  check("старые рекомендации очищены", el("actionList").children.length === 0);
  check("старый статус очищен", text("statusLabel") === "", `"${text("statusLabel")}"`);
  check("старая техническая сводка очищена", el("techDiagnostics").children.length === 0);
  check("PDF-ссылка спрятана", el("pdfLink").hidden === true);
  check("дата в шапке сброшена", text("auditDateCaption") === "· —", text("auditDateCaption"));

  console.log("\n3) «Повторить» после восстановления API");
  serverMode = "ok";
  await el("retryBtn")._listeners.click();
  await settle();

  check("dashboard снова виден", el("dashboard").hidden === false);
  check("баннер ошибки убран", el("errorBanner").hidden === true);
  check("показан новый ответ, а не старый", text("kpiRevenue") === "999 ₽", text("kpiRevenue"));
  check("воронка восстановлена", el("funnelSteps").children.length === 5);
  check("статус восстановлен", text("statusLabel") === "PARTIAL", text("statusLabel"));
  check("повторный запрос реально ушёл", auditCalls >= 3, `audit calls = ${auditCalls}`);

  console.log("\n4) HTTP 500 без detail -> показывается код ответа");
  serverMode = "500-empty";
  await el("auditForm")._listeners.submit({ preventDefault() {} });
  await settle();
  check("ошибка показана", el("errorBanner").hidden === false);
  check("текст содержит код 500", text("errorDetail") === "API error 500", text("errorDetail"));
  check("данные не показаны", el("dashboard").hidden === true);
  check("старая выручка не вернулась", text("kpiRevenue") === "", `"${text("kpiRevenue")}"`);

  console.log("\n5) объяснение «почему прибыль не рассчитана»");
  serverMode = "ok";
  const bullets = () => (el("financeMissingList").children || []).map((li) => li.textContent.replace("• ", ""));

  custom = auditFixture(1439);
  await el("auditForm")._listeners.submit({ preventDefault() {} });
  await settle();
  check("объяснение показано", el("financeExplain").hidden === false);
  check("ровно два пункта", bullets().length === 2, bullets().join(" | "));
  check("пункт 1 — себестоимость", bullets()[0] === "себестоимости товара", bullets()[0]);
  check("пункт 2 — налог", bullets()[1] === "данных для расчёта налога", bullets()[1]);
  check("технических имён нет", !bullets().some((b) => /cogs|tax|missing|MISSING/i.test(b)), bullets().join(" | "));
  check("причина в статусе", text("statusReason") === "Причина: не задана себестоимость и налог.", text("statusReason"));

  custom = auditFixture(1439, { traces: [{ component: "cogs", status: "available" }, { component: "tax", status: "missing" }] });
  await el("auditForm")._listeners.submit({ preventDefault() {} });
  await settle();
  check("COGS появился — пункт исчез сам", bullets().length === 1 && bullets()[0] === "данных для расчёта налога", bullets().join(" | "));
  check("себестоимость показана числом", rows("financeRows")[2] === "Себестоимость: 500 ₽", rows("financeRows")[2]);

  custom = auditFixture(1439, { traces: [{ component: "rebill_logistic_cost", status: "missing" }] });
  await el("auditForm")._listeners.submit({ preventDefault() {} });
  await settle();
  check("неизвестный компонент не протекает в UI", !bullets().some((b) => b.includes("rebill_logistic_cost")), bullets().join(" | "));
  check("общая человеческая формулировка", bullets().length === 1 && bullets()[0] === "обязательных финансовых данных", bullets().join(" | "));

  /*
   * Новые marketplace-компоненты: «не хватает» и «данные есть, но методика не
   * подтверждена» — два разных состояния, и UI обязан не смешивать их.
   */
  custom = auditFixture(1439, {
    traces: [
      { component: "marketplace_commission", status: "available" },
      { component: "logistics", status: "available" },
      { component: "rebill_logistics", status: "unresolved" },
      { component: "cogs", status: "missing" },
    ],
  });
  await el("auditForm")._listeners.submit({ preventDefault() {} });
  await settle();
  check(
    "неподтверждённое удержание названо по-человечески",
    bullets().includes("подтверждённой методики по корректировкам логистики WB"),
    bullets().join(" | "),
  );
  check("нехватка себестоимости осталась отдельным пунктом", bullets().includes("себестоимости товара"), bullets().join(" | "));
  check(
    "смешанные состояния не подписаны одной нехваткой",
    text("financeExplainLead") === "Прибыль не рассчитана: не хватает данных и есть неподтверждённые удержания:",
    text("financeExplainLead"),
  );
  check(
    "технических имён компонентов в списке нет",
    !bullets().some((b) => /rebill|logistics|commission|unresolved|marketplace/i.test(b)),
    bullets().join(" | "),
  );
  check(
    "причина в статусе называет оба факта",
    text("statusReason") === "Причина: не задана себестоимость и нет подтверждённой методики для корректировок логистики WB.",
    text("statusReason"),
  );

  custom = auditFixture(1439, { traces: [{ component: "rebill_logistics", status: "unresolved" }] });
  await el("auditForm")._listeners.submit({ preventDefault() {} });
  await settle();
  check(
    "только неподтверждённое удержание — отдельная подсказка",
    text("financeExplainLead") === "Прибыль не рассчитана: по этим удержаниям WB нет подтверждённой методики:",
    text("financeExplainLead"),
  );
  check(
    "причина в статусе про методику",
    text("statusReason") === "Причина: нет подтверждённой методики для корректировок логистики WB.",
    text("statusReason"),
  );

  custom = auditFixture(1439, { traces: [{ component: "marketplace_commission", status: "missing" }] });
  await el("auditForm")._listeners.submit({ preventDefault() {} });
  await settle();
  check("комиссия WB названа прямо", bullets()[0] === "данных по комиссии WB", bullets().join(" | "));
  check("подсказка осталась про нехватку", text("financeExplainLead") === "Для расчёта не хватает:", text("financeExplainLead"));

  custom = auditFixture(1439, { traces: [], finality: "final" });
  await el("auditForm")._listeners.submit({ preventDefault() {} });
  await settle();
  check("объяснение есть даже без traces", el("financeExplain").hidden === false && bullets().length === 1, bullets().join(" | "));

  custom = auditFixture(1439, { traces: [{ component: "cogs", status: "available" }, { component: "tax", status: "available" }] });
  await el("auditForm")._listeners.submit({ preventDefault() {} });
  await settle();
  check("данные полны, но день открыт — про нехватку не врём", bullets()[0] === "подтверждения, что день закрыт финансово", bullets().join(" | "));
  check("подсказка переключилась на подтверждение", text("financeExplainLead") === "Все финансовые данные заданы. Прибыль появится после:", text("financeExplainLead"));
  check("причина в статусе — про закрытие дня", text("statusReason") === "Причина: день не подтверждён как закрытый финансово.", text("statusReason"));

  custom = auditFixture(1439, { traces: [{ component: "cogs", status: "available" }, { component: "tax", status: "available" }], netProfit: 862, finality: "final" });
  await el("auditForm")._listeners.submit({ preventDefault() {} });
  await settle();
  check("при рассчитанной прибыли блока нет", el("financeExplain").hidden === true);
  check("прибыль показана числом", text("kpiProfit") === "862 ₽", text("kpiProfit"));
  check("причина в статусе пуста", text("statusReason") === "", `"${text("statusReason")}"`);

  /*
   * Полностью закрытый реальный день: экран обязан показать все удержания WB
   * знаковыми числами из backend и не показать ни одного технического имени.
   */
  const CLOSED_DAY = [
    ["realized_revenue", "1439", "available"],
    ["marketplace_commission", "-325.57", "available"],
    ["logistics", "-75.4", "available"],
    ["storage", "-5.89", "available"],
    ["acceptance", "-10", "available"],
    ["acquiring", "-57.56", "available"],
    ["penalties", "0", "available"],
    ["other_marketplace_deductions", "0", "available"],
    ["rebill_logistics", "-76.92", "available"],
    ["advertising", "-77.04", "available"],
    ["cogs", "-550", "available"],
    ["tax", "-86.34", "available"],
    ["net_profit", "174.28", "available"],
  ];
  custom = auditFixture(1439, {
    traces: CLOSED_DAY.map(([component, , status]) => ({ component, status })),
    netProfit: 174.28,
    finality: "final",
    auditStatus: "complete",
    extraMetrics: CLOSED_DAY,
  });
  await el("auditForm")._listeners.submit({ preventDefault() {} });
  await settle();
  const financeLines = rows("financeRows");
  check("группа удержаний WB показана", financeLines.includes("Удержания WB"), financeLines.join(" | "));
  check("комиссия WB знаковая", financeLines.includes("Комиссия WB: −325,57 ₽"), financeLines.join(" | "));
  check("логистика знаковая", financeLines.includes("Логистика: −75,40 ₽"), financeLines.join(" | "));
  check("корректировки логистики показаны", financeLines.includes("Корректировки логистики WB: −76,92 ₽"), financeLines.join(" | "));
  check("себестоимость и налог знаковые", financeLines.includes("Себестоимость: −550 ₽") && financeLines.includes("Налог: −86,34 ₽"), financeLines.join(" | "));
  check("чистая прибыль показана с копейками", financeLines[financeLines.length - 1] === "Чистая прибыль: 174,28 ₽", financeLines[financeLines.length - 1]);
  check(
    "ни одного технического имени компонента на экране",
    !financeLines.some((line) => /rebill|logistics|commission|acquiring|acceptance|penalt|marketplace|unresolved|available/i.test(line)),
    financeLines.join(" | "),
  );
  check("объяснение нехватки скрыто на закрытом дне", el("financeExplain").hidden === true);
  // независимая проверка: то, что показал экран, сходится к показанной прибыли
  const shown = financeLines
    .filter((line) => line.includes(": ") && !line.startsWith("Удержания"))
    .map((line) => Number(line.split(": ")[1].replace(/[^\d.,−-]/g, "").replace("−", "-").replace(",", ".")));
  const profit = shown[shown.length - 1];
  const sum = shown.slice(0, -1).reduce((acc, v) => acc + v, 0);
  check("строки экрана сходятся в прибыль", Math.abs(sum - profit) < 0.005, `${sum} vs ${profit}`);
  custom = null;

  console.log("\n6) пользовательские финансовые параметры (себестоимость и налог)");
  soldProducts = [
    { nm_id: "333615320", seller_sku: "ART-320", sales_quantity: "1" },
    { nm_id: "739384273", seller_sku: null, sales_quantity: "2" },
    { nm_id: "ABC-1", seller_sku: null, sales_quantity: "1" },
  ];
  settingsStore = { tax_rate: null, tax_rate_unit: "percent", tax_basis: "realized_revenue", finality_confirmed: false, cogs: [] };
  await el("auditForm")._listeners.submit({ preventDefault() {} });
  await settle();

  const cogsRow = (index) => el("cogsRows").children[index];
  check("экран не в состоянии ошибки", el("errorBanner").hidden === true, text("errorDetail"));
  check("карточка параметров показана", el("settingsCard").hidden === false);
  check("строки по проданным товарам", el("cogsRows").children.length === 3, `${el("cogsRows").children.length}`);
  check("пустая себестоимость — не ноль", cogsRow(0).children[2].value === "", `"${cogsRow(0).children[2].value}"`);
  check("объяснение нехватки на месте", bullets().length === 2, bullets().join(" | "));

  el("taxRateInput").value = "6";
  await el("saveTaxBtn")._listeners.click();
  await settle();
  check("ставка сохранена и показана", el("taxRateInput").value === "6", `"${el("taxRateInput").value}"`);
  check("пункт про налог исчез автоматически", bullets().length === 1 && bullets()[0] === "себестоимости товара", bullets().join(" | "));

  el("taxRateInput").value = "-6";
  await el("saveTaxBtn")._listeners.click();
  await settle();
  check("отрицательная ставка отклонена по-человечески", text("taxError") === "Налоговая ставка не может быть отрицательной", text("taxError"));
  check("отрицательная ставка не попала в backend", settingsStore.tax_rate === "6", `"${settingsStore.tax_rate}"`);
  check("финансовый блок не перерисовался ошибочно", bullets().length === 1, bullets().join(" | "));

  el("taxRateInput").value = "шесть";
  await el("saveTaxBtn")._listeners.click();
  await settle();
  check("нечисловая ставка отклонена", text("taxError") === "«Налоговая ставка» должно быть числом", text("taxError"));

  cogsRow(0).children[2].value = "500";
  await cogsRow(0).children[3]._listeners.click();
  await settle();
  check("себестоимость сохранена и показана", cogsRow(0).children[2].value === "500", `"${cogsRow(0).children[2].value}"`);
  check("объяснение перешло на закрытие дня", bullets().length === 1 && bullets()[0] === "подтверждения, что день закрыт финансово", bullets().join(" | "));
  check("прибыль не выдумана до закрытия дня", text("kpiProfit") === "Не рассчитана", text("kpiProfit"));
  check("себестоимость показана в финансах", rows("financeRows")[2] === "Себестоимость: 500 ₽", rows("financeRows")[2]);

  const badRow = cogsRow(1);
  badRow.children[2].value = "-10";
  await badRow.children[3]._listeners.click();
  await settle();
  check("отрицательная себестоимость отклонена", badRow.children[4].hidden === false && badRow.children[4].textContent === "Себестоимость не может быть отрицательной", badRow.children[4].textContent);
  check("отрицательная себестоимость не сохранена", settingsStore.cogs.length === 1, `${settingsStore.cogs.length}`);

  const corruptRow = cogsRow(2);
  corruptRow.children[2].value = "100";
  await corruptRow.children[3]._listeners.click();
  await settle();
  check("некорректный SKU не принимается", corruptRow.children[4].textContent === "Артикул товара должен содержать только цифры", corruptRow.children[4].textContent);

  el("finalityInput").checked = true;
  await el("saveFinalityBtn")._listeners.click();
  await settle();
  check("подтверждение сохранено", el("finalityInput").checked === true);
  check("прибыль посчитал backend", text("kpiProfit") === "862 ₽", text("kpiProfit"));
  check("статус стал COMPLETE", text("statusLabel") === "COMPLETE", text("statusLabel"));
  check("объяснение исчезло после закрытия дня", el("financeExplain").hidden === true);
  check("причина в статусе пуста после закрытия", text("statusReason") === "", `"${text("statusReason")}"`);

  serverMode = "500";
  await el("auditForm")._listeners.submit({ preventDefault() {} });
  await settle();
  check("при ошибке карточка параметров скрыта", el("settingsCard").hidden === true);
  check("значения не остались на экране", el("taxRateInput").value === "", `"${el("taxRateInput").value}"`);

  serverMode = "ok";
  await el("retryBtn")._listeners.click();
  await settle();
  check("значения возвращены с backend, не из памяти экрана", el("taxRateInput").value === "6" && cogsRow(0).children[2].value === "500", `${el("taxRateInput").value} / ${cogsRow(0).children[2].value}`);
  check("настройки запрашивались у API", settingsCalls >= 3, `settings calls = ${settingsCalls}`);
  soldProducts = [];

  console.log(`\n${failures === 0 ? "РЕГРЕССИЯ ПРОЙДЕНА" : `ПРОВАЛЕНО ПРОВЕРОК: ${failures}`}`);
  process.exitCode = failures === 0 ? 0 : 1;
})();
