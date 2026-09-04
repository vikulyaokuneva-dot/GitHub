/*
 * Экран ежедневного аудита продавца.
 *
 * Слой только отображает существующий результат аудита:
 *   GET /audit/{account_id}  ->  CabinetAuditResult (backend считает всё сам)
 *
 * Здесь нет ни одной финансовой формулы и ни одного решения о статусе:
 * значения берутся из analysis.pipeline.report_payload.metrics,
 * статус — из поля audit_status backend'а.
 * MISSING никогда не отображается как 0.
 */

const state = {
  accounts: [],
  audit: null,
  settings: null,
  lastRequest: null,
};

const MISSING = "Нет данных";

const ids = [
  "connectionStatus", "auditForm", "accountSelect", "auditDateInput", "submitBtn", "pdfLink",
  "errorBanner", "errorDetail", "retryBtn", "loadingState", "dashboard", "auditDateCaption",
  "verdictCard", "verdictHeadline", "verdictDetail", "verdictNote", "verdictSeverity", "verdictSeverityText",
  "kpiSales", "kpiSalesHint", "kpiRevenue", "kpiRevenueHint", "kpiAds", "kpiAdsHint",
  "kpiProfit", "kpiProfitHint", "kpiProfitCard",
  "funnelSteps", "funnelRates",
  "financeRows", "financeExplain", "financeExplainLead", "financeMissingList",
  "adsTotal", "adRows", "adEmpty",
  "settingsCard", "taxRateInput", "saveTaxBtn", "taxError",
  "finalityInput", "saveFinalityBtn", "finalityHint", "finalityError",
  "cogsRows", "cogsEmpty",
  "actionList",
  "statusCard", "statusDot", "statusLabel", "statusDescription", "statusReason",
  "techRows", "techDiagnostics",
];

const ui = Object.fromEntries(ids.map((id) => [id, document.getElementById(id)]));

/* ---------- helpers: форматирование уже посчитанных backend-значений ---------- */

function toNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatCount(value) {
  return value === null ? MISSING : Math.round(value).toLocaleString("ru-RU");
}

/*
 * Деньги показываются ровно теми знаками, какими их отдал Finance Kernel:
 * экран ничего не складывает, не вычитает и не разворачивает знак. Копейки
 * видны, когда они есть, чтобы строки P&L сходились с итогом на глаз.
 */
function formatMoney(value) {
  if (value === null) return null;
  const sign = value < 0 ? "−" : "";
  const digits = Math.abs(value) % 1 === 0 ? 0 : 2;
  const amount = Math.abs(value).toLocaleString("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return `${sign}${amount} ₽`;
}

/*
 * Отношение двух уже существующих метрик для показа (не новый расчёт P&L).
 * Нет числителя, знаменателя или знаменатель равен нулю — значения нет:
 * показывается MISSING, а не 0.
 */
function formatRatio(numerator, denominator) {
  if (numerator === null || denominator === null || denominator === 0) return null;
  const percent = (numerator / denominator) * 100;
  const decimals = Number.isInteger(percent) ? 0 : 1;
  return `${percent.toLocaleString("ru-RU", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}%`;
}

function plural(count, forms) {
  const mod10 = Math.abs(count) % 10;
  const mod100 = Math.abs(count) % 100;
  if (mod10 === 1 && mod100 !== 11) return forms[0];
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return forms[1];
  return forms[2];
}

function joinHuman(parts) {
  if (parts.length <= 1) return parts[0] || "";
  return `${parts.slice(0, -1).join(", ")} и ${parts[parts.length - 1]}`;
}

function setText(id, text) {
  ui[id].textContent = text === null || text === undefined || text === "" ? MISSING : text;
}

function renderRows(container, rows) {
  container.replaceChildren();
  for (const row of rows) {
    const wrapper = document.createElement("div");
    wrapper.className = row.heading ? "row row-heading" : "row";
    const label = document.createElement("dt");
    label.textContent = row.label;
    wrapper.appendChild(label);
    if (row.heading) {
      container.appendChild(wrapper);
      continue;
    }
    const value = document.createElement("dd");
    value.textContent = row.value ?? (row.missingText || MISSING);
    if (row.tone) value.dataset.tone = row.tone;
    wrapper.appendChild(value);
    container.appendChild(wrapper);
  }
}

/* ---------- reading the existing audit contract ---------- */

function metricsByKey(audit) {
  const map = Object.create(null);
  for (const metric of audit?.analysis?.pipeline?.report_payload?.metrics || []) {
    map[metric.key] = metric;
  }
  return map;
}

function readMetrics(audit) {
  const metrics = metricsByKey(audit);
  const value = (key) => (metrics[key] ? toNumber(metrics[key].value) : null);
  return {
    raw: metrics,
    sales: value("sales"),
    orders: value("orders"),
    stock: value("available_stock"),
    opens: value("funnel_opens"),
    carts: value("funnel_carts"),
    funnelOrders: value("funnel_orders"),
    revenue: value("realized_revenue"),
    advertisingExpense: value("advertising"),
    advertisingSpend: value("advertising_direct_sku"),
    advertisingCampaign: value("advertising_campaign"),
    advertisingPeriod: value("advertising_period"),
    advertisingAssociated: value("advertising_associated"),
    advertisingUnknown: value("advertising_unknown"),
    cogs: value("cogs"),
    tax: value("tax"),
    profit: value("net_profit"),
    margin: value("profit_margin"),
  };
}

/*
 * Человеческие формулировки нехваток. Внутренние имена компонентов
 * (cogs, tax, …) нигде не выводятся: они служат только ключом поиска.
 */
const FINANCE_GAP_LABELS = {
  cogs: { explain: "себестоимости товара", reason: "себестоимость" },
  tax: { explain: "данных для расчёта налога", reason: "налог" },
  advertising: { explain: "данных по рекламным расходам", reason: "рекламные расходы" },
  realized_revenue: { explain: "данных по реализованной выручке", reason: "реализованная выручка" },
  logistics: { explain: "данных по логистике", reason: "логистика" },
  storage: { explain: "данных по хранению", reason: "хранение" },
  marketplace_commission: { explain: "данных по комиссии WB", reason: "комиссия WB" },
  acquiring: { explain: "данных по эквайрингу", reason: "эквайринг" },
  acceptance: { explain: "данных по платной обработке товара", reason: "платная обработка товара" },
  penalties: { explain: "данных по штрафам", reason: "штрафы" },
  other_marketplace_deductions: { explain: "данных по прочим удержаниям WB", reason: "прочие удержания WB" },
};

/*
 * Отличается от «не хватает»: строка источника получена и сумма известна, но
 * экономический смысл удержания не подтверждён, поэтому ядро не вправе
 * приплюсовывать его к прибыли. Честный текст — «нет подтверждённой методики»,
 * а не «нет данных».
 */
const FINANCE_UNRESOLVED_LABELS = {
  rebill_logistics: {
    explain: "подтверждённой методики по корректировкам логистики WB",
    reason: "корректировок логистики WB",
  },
};

const GENERIC_GAP = { explain: "обязательных финансовых данных", reason: null };

/*
 * Отдельное состояние: все нужные компоненты заданы, но Wildberries не считает
 * день закрытым. Это не «нехватка данных», и говорить обратное было бы обманом.
 * Финальность берётся из оценки backend'а, на экране она не выводится.
 */
const FINALITY_GAP = { explain: "подтверждения, что день закрыт финансово", reason: null };
const EXPLAIN_LEAD_MISSING = "Для расчёта не хватает:";
const EXPLAIN_LEAD_UNRESOLVED = "Прибыль не рассчитана: по этим удержаниям WB нет подтверждённой методики:";
const EXPLAIN_LEAD_MIXED = "Прибыль не рассчитана: не хватает данных и есть неподтверждённые удержания:";
const EXPLAIN_LEAD_FINALITY = "Все финансовые данные заданы. Прибыль появится после:";

/*
 * Список строится ИСКЛЮЧИТЕЛЬНО из состояния backend: берётся
 * component_traces и его status === "missing" (данных нет) или
 * status === "unresolved" (данные есть, смысл не подтверждён). Как только
 * источник появится (COGS будет задан, налог определится), trace перестанет
 * быть missing — и соответствующий пункт исчезнет сам. На экране нет ни одного
 * захардкоженного «не хватает» и ни одного нуля вместо отсутствующего.
 */
function financeGaps(audit) {
  const traces = audit?.analysis?.pipeline?.financial_flow?.financial_result?.component_traces || [];
  const gaps = [];
  let unmapped = false;
  for (const trace of traces) {
    const unresolved = trace.status === "unresolved";
    if (trace.status !== "missing" && !unresolved) continue;
    const table = unresolved ? FINANCE_UNRESOLVED_LABELS : FINANCE_GAP_LABELS;
    const label = table[trace.component];
    if (!label) {
      unmapped = true;
      continue;
    }
    const item = { explain: label.explain, reason: label.reason, kind: unresolved ? "unresolved" : "missing" };
    if (!gaps.some((gap) => gap.explain === item.explain)) gaps.push(item);
  }
  if (unmapped) gaps.push({ explain: GENERIC_GAP.explain, reason: GENERIC_GAP.reason, kind: "missing" });
  return gaps;
}

function finalityPending(audit) {
  const assessment = audit?.analysis?.pipeline?.financial_flow?.finality_assessment;
  return Boolean(assessment) && assessment.finality !== "final";
}

function explainItems(audit, gaps) {
  if (gaps.length > 0) return gaps;
  if (finalityPending(audit)) return [FINALITY_GAP];
  return [GENERIC_GAP];
}

function explainLead(audit, items) {
  if (items.length === 1 && items[0] === FINALITY_GAP) return EXPLAIN_LEAD_FINALITY;
  const hasMissing = items.some((item) => item.kind === "missing");
  const hasUnresolved = items.some((item) => item.kind === "unresolved");
  if (hasMissing && hasUnresolved) return EXPLAIN_LEAD_MIXED;
  if (hasUnresolved) return EXPLAIN_LEAD_UNRESOLVED;
  return EXPLAIN_LEAD_MISSING;
}

function statusReasonLine(audit, gaps) {
  const missing = gaps.filter((gap) => gap.kind !== "unresolved" && gap.reason !== null);
  const unresolved = gaps.filter((gap) => gap.kind === "unresolved" && gap.reason !== null);
  const hasGeneric = gaps.some((gap) => gap.reason === null && gap.kind !== "unresolved");
  const sentences = [];
  if (missing.length > 0) sentences.push(`не задана ${joinHuman(missing.map((gap) => gap.reason))}`);
  if (unresolved.length > 0) {
    sentences.push(`нет подтверждённой методики для ${joinHuman(unresolved.map((gap) => gap.reason))}`);
  }
  if (sentences.length === 0) {
    if (gaps.length === 0 && finalityPending(audit)) return "Причина: день не подтверждён как закрытый финансово.";
    return hasGeneric ? "Причина: не хватает обязательных финансовых данных." : "";
  }
  const sentence = `Причина: ${joinHuman(sentences)}.`;
  return hasGeneric ? `${sentence} Также не хватает других обязательных данных.` : sentence;
}

/* ---------- block 1: главный вывод ---------- */

const verdictRules = [
  {
    severity: "critical",
    label: "Критическая проблема",
    when: (m) => m.carts !== null && m.carts > 0 && m.funnelOrders !== null && m.funnelOrders === 0,
    build: (m) => ({
      headline: `${formatCount(m.carts)} ${plural(m.carts, ["корзина", "корзины", "корзин"])} → ${formatCount(m.funnelOrders)} ${plural(m.funnelOrders, ["заказ", "заказа", "заказов"])}`,
      detail: `Конверсия корзина → заказ: ${formatRatio(m.funnelOrders, m.carts) ?? MISSING}`,
      note: "Это главная проблема текущего дня.",
    }),
  },
  {
    severity: "critical",
    label: "Критическая проблема",
    when: (m) => m.opens !== null && m.opens > 0 && m.carts !== null && m.carts === 0,
    build: (m) => ({
      headline: `${formatCount(m.opens)} просмотров → 0 корзин`,
      detail: `Конверсия просмотр → корзина: ${formatRatio(m.carts, m.opens) ?? MISSING}`,
      note: "Карточка товара не конвертирует интерес.",
    }),
  },
  {
    severity: "warning",
    label: "Требует внимания",
    when: (m) => m.profit === null && (m.revenue !== null || m.sales !== null),
    build: () => ({
      headline: "Прибыль за день не рассчитана",
      detail: "Операционные данные есть, но финансовый результат закрыть нечем.",
      note: "Нужны себестоимость и налоговые параметры.",
    }),
  },
];

function renderVerdict(audit, m) {
  const rule = verdictRules.find((candidate) => candidate.when(m)) || null;
  ui.verdictCard.dataset.severity = rule ? rule.severity : "neutral";
  ui.verdictSeverity.dataset.severity = rule ? rule.severity : "neutral";
  ui.verdictSeverityText.textContent = rule ? rule.label : "Недостаточно данных";
  if (!rule) {
    ui.verdictHeadline.textContent = "Недостаточно данных для вывода";
    ui.verdictDetail.textContent = "";
    ui.verdictNote.textContent = "";
    return;
  }
  const view = rule.build(m);
  ui.verdictHeadline.textContent = view.headline;
  ui.verdictDetail.textContent = view.detail;
  ui.verdictNote.textContent = view.note;
}

/* ---------- block 2: ключевые показатели ---------- */

function renderKpis(m) {
  setText("kpiSales", m.sales === null ? null : `${formatCount(m.sales)} шт.`);
  ui.kpiSales.dataset.empty = m.sales === null ? "true" : "false";
  ui.kpiSalesHint.textContent = m.sales === null ? "нет данных по продажам" : "за день";

  setText("kpiRevenue", formatMoney(m.revenue));
  ui.kpiRevenue.dataset.empty = m.revenue === null ? "true" : "false";
  ui.kpiRevenueHint.textContent = m.revenue === null ? "нет финансовой реализации" : "реализованная выручка";

  const spend = m.advertisingExpense !== null ? Math.abs(m.advertisingExpense) : m.advertisingSpend;
  setText("kpiAds", formatMoney(spend));
  ui.kpiAds.dataset.empty = spend === null ? "true" : "false";
  ui.kpiAdsHint.textContent = spend === null ? "расходов не зафиксировано" : "расход на рекламу";

  const profitKnown = m.profit !== null;
  setText("kpiProfit", profitKnown ? formatMoney(m.profit) : "Не рассчитана");
  ui.kpiProfit.dataset.textual = profitKnown ? "false" : "true";
  ui.kpiProfitHint.textContent = profitKnown
    ? (m.margin === null ? "" : `маржа ${formatRatio(m.profit, m.revenue) ?? MISSING}`)
    : "не хватает себестоимости и налога";
  ui.kpiProfitCard.dataset.state = profitKnown ? "known" : "unknown";
}

/* ---------- block 3: воронка ---------- */

function renderFunnel(m) {
  const steps = [
    { label: "Просмотры", value: m.opens },
    { label: "Корзины", value: m.carts },
    { label: "Заказы", value: m.funnelOrders },
  ];

  ui.funnelSteps.replaceChildren();
  steps.forEach((step, index) => {
    if (index > 0) {
      const arrow = document.createElement("div");
      arrow.className = "funnel-arrow";
      arrow.textContent = "↓";
      ui.funnelSteps.appendChild(arrow);
    }
    const card = document.createElement("div");
    card.className = "funnel-step";
    const value = document.createElement("p");
    value.className = "funnel-value";
    value.textContent = step.value === null ? MISSING : formatCount(step.value);
    if (step.value === null) value.dataset.empty = "true";
    const label = document.createElement("p");
    label.className = "funnel-label";
    label.textContent = step.label;
    card.append(value, label);
    ui.funnelSteps.appendChild(card);
  });

  const rates = [
    { label: "Просмотр → корзина", value: formatRatio(m.carts, m.opens) },
    { label: "Корзина → заказ", value: formatRatio(m.funnelOrders, m.carts) },
  ];
  ui.funnelRates.replaceChildren();
  for (const rate of rates) {
    const row = document.createElement("div");
    row.className = "funnel-rate";
    const label = document.createElement("span");
    label.textContent = rate.label;
    const value = document.createElement("strong");
    value.textContent = rate.value ?? MISSING;
    if (rate.value === null) value.dataset.empty = "true";
    row.append(label, value);
    ui.funnelRates.appendChild(row);
  }
}

/* ---------- block 4: финансы ---------- */

/*
 * Строки P&L, которые ядро уже посчитало. Экран только выбирает и подписывает
 * их: никакого сложения, вычитания или смены знака здесь нет и быть не должно.
 */
const WB_DEDUCTION_ROWS = [
  ["marketplace_commission", "Комиссия WB"],
  ["logistics", "Логистика"],
  ["storage", "Хранение"],
  ["acceptance", "Обработка товара"],
  ["acquiring", "Эквайринг"],
  ["penalties", "Штрафы"],
  ["other_marketplace_deductions", "Прочие удержания WB"],
  ["rebill_logistics", "Корректировки логистики WB"],
];

function wbDeductionRows(m) {
  const rows = [];
  for (const [key, label] of WB_DEDUCTION_ROWS) {
    const metric = m.raw[key];
    if (!metric || metric.status !== "available") continue;
    rows.push({ label, value: formatMoney(toNumber(metric.value)), tone: "negative" });
  }
  return rows;
}

function renderFinance(audit, m) {
  const deductions = wbDeductionRows(m);
  const rows = [
    { label: "Реализованная выручка", value: formatMoney(m.revenue), tone: "positive" },
  ];
  if (deductions.length > 0) {
    rows.push({ label: "Удержания WB", heading: true });
    rows.push(...deductions);
  }
  rows.push(
    { label: "Реклама", value: formatMoney(m.advertisingExpense), missingText: MISSING, tone: "negative" },
    { label: "Себестоимость", value: formatMoney(m.cogs), missingText: "Не задана", tone: "muted" },
    { label: "Налог", value: formatMoney(m.tax), missingText: "Не задан", tone: "muted" },
    { label: "Чистая прибыль", value: formatMoney(m.profit), missingText: "Не рассчитана", tone: m.profit === null ? "muted" : "strong" },
  );
  renderRows(ui.financeRows, rows);

  const gaps = financeGaps(audit);
  const items = explainItems(audit, gaps);
  const showExplain = m.profit === null;
  ui.financeExplain.hidden = !showExplain;
  if (showExplain) {
    ui.financeExplainLead.textContent = explainLead(audit, items);
    ui.financeMissingList.replaceChildren();
    for (const item of items) {
      const li = document.createElement("li");
      li.textContent = `• ${item.explain}`;
      ui.financeMissingList.appendChild(li);
    }
  }
}

/* ---------- block 5: реклама ---------- */

function renderAds(audit, m) {
  const spend = m.advertisingExpense !== null ? Math.abs(m.advertisingExpense) : m.advertisingSpend;
  setText("adsTotal", formatMoney(spend));

  const extra = [
    { label: "Привязано к товарам", value: m.advertisingSpend },
    { label: "Внутри кампаний", value: m.advertisingCampaign },
    { label: "Общие за период", value: m.advertisingPeriod },
    { label: "Связанные показы", value: m.advertisingAssociated },
    { label: "Не сопоставлено", value: m.advertisingUnknown },
  ].filter((row) => row.value !== null && row.value !== 0);

  renderRows(ui.adRows, extra.map((row) => ({ label: row.label, value: formatMoney(row.value) })));
  ui.adEmpty.hidden = extra.length > 0;

  const perProduct = (audit?.analysis?.products || [])
    .filter((product) => toNumber(product.direct_advertising) !== null)
    .map((product) => ({
      label: `Товар ${product.nm_id}`,
      value: formatMoney(toNumber(product.direct_advertising)),
    }));
  if (perProduct.length > 0) {
    ui.adRows.appendChild(sectionTitle("Распределение по товарам"));
    renderAppendRows(ui.adRows, perProduct.map((row) => ({ ...row, value: row.value })));
    ui.adEmpty.hidden = true;
  }
}

function sectionTitle(text) {
  const row = document.createElement("div");
  row.className = "row row-title";
  const label = document.createElement("dt");
  label.textContent = text;
  row.appendChild(label);
  return row;
}

function renderAppendRows(container, rows) {
  for (const row of rows) {
    const wrapper = document.createElement("div");
    wrapper.className = "row";
    const label = document.createElement("dt");
    label.textContent = row.label;
    const value = document.createElement("dd");
    value.textContent = row.value ?? MISSING;
    wrapper.append(label, value);
    container.appendChild(wrapper);
  }
}

/* ---------- block 6: что нужно сделать ---------- */

const actionRules = [
  {
    when: (m) => m.carts !== null && m.carts > 0 && m.funnelOrders !== null && m.funnelOrders === 0,
    text: (m) => `Проверить, почему ${formatCount(m.carts)} ${plural(m.carts, ["добавление", "добавления", "добавлений"])} в корзину не превращаются в заказы.`,
  },
  {
    when: (m) => m.carts !== null && m.carts > 0 && m.funnelOrders !== null && m.funnelOrders === 0,
    text: () => "Проверить цену и карточку товара.",
  },
  { when: (m) => m.cogs === null, text: () => "Указать себестоимость товара." },
  { when: (m) => m.tax === null, text: () => "Указать налоговые параметры, чтобы директор мог рассчитать чистую прибыль." },
  { when: (m) => m.advertisingUnknown !== null && m.advertisingUnknown > 0, text: () => "Проверить рекламные расходы: часть не сопоставлена с товарами." },
];

function renderActions(m) {
  const actions = actionRules.filter((rule) => rule.when(m)).map((rule) => rule.text(m));
  ui.actionList.replaceChildren();
  if (actions.length === 0) {
    const li = document.createElement("li");
    li.textContent = "Дополнительных действий по данным аудита не требуется.";
    ui.actionList.appendChild(li);
    return;
  }
  for (const action of actions) {
    const li = document.createElement("li");
    li.textContent = action;
    ui.actionList.appendChild(li);
  }
}

/* ---------- block 7: статус (берётся из backend, здесь не вычисляется) ---------- */

const statusViews = {
  complete: { label: "COMPLETE", description: "Данные получены, финансовый результат определён.", severity: "ok" },
  partial: { label: "PARTIAL", description: "Данные получены, но финансовый результат нельзя определить полностью.", severity: "warning" },
  no_data: { label: "НЕТ ДАННЫХ", description: "Финансовых данных за этот день нет.", severity: "neutral" },
  conflict: { label: "CONFLICT", description: "Источники дают противоречивые данные.", severity: "critical" },
};

function renderStatus(audit) {
  const key = audit.audit_status || "no_data";
  const view = statusViews[key] || { label: String(key).toUpperCase(), description: "", severity: "neutral" };
  ui.statusCard.dataset.severity = view.severity;
  ui.statusLabel.textContent = view.label;
  ui.statusDescription.textContent = view.description;

  ui.statusReason.textContent = statusReasonLine(audit, financeGaps(audit));
}

/* ---------- блок 8: финансовые параметры пользователя ---------- */

/*
 * Экран только показывает сохранённые объявления и отправляет введённые значения
 * на backend. Ни себестоимость, ни налог, ни прибыль здесь не вычисляются:
 * пересчёт делает Finance Kernel после перезапуска существующего аудита.
 */

function soldProductRows() {
  const products = state.audit?.analysis?.products || [];
  return products
    .filter((product) => product.nm_id && toNumber(product.sales_quantity) !== null && toNumber(product.sales_quantity) > 0)
    .map((product) => ({ sku: product.nm_id, sellerSku: product.seller_sku || null, quantity: toNumber(product.sales_quantity) }));
}

function settingsRows() {
  const stored = new Map((state.settings?.cogs || []).map((item) => [item.sku, item]));
  const rows = soldProductRows().map((product) => ({ ...product, stored: stored.get(product.sku) || null }));
  for (const [sku, item] of stored) {
    if (!rows.some((row) => row.sku === sku)) {
      rows.push({ sku, sellerSku: item.seller_sku || null, quantity: null, stored: item });
    }
  }
  return rows;
}

function renderCogsRows() {
  const rows = settingsRows();
  ui.cogsRows.replaceChildren();
  ui.cogsEmpty.hidden = rows.length > 0;

  for (const row of rows) {
    const wrapper = document.createElement("div");
    wrapper.className = "cogs-row";

    const name = document.createElement("div");
    name.className = "cogs-name";
    const skuText = document.createElement("strong");
    skuText.textContent = row.sku;
    name.appendChild(skuText);
    if (row.sellerSku) {
      const skuLabel = document.createElement("span");
      skuLabel.className = "cogs-sub";
      skuLabel.textContent = row.sellerSku;
      name.appendChild(skuLabel);
    }

    const quantity = document.createElement("span");
    quantity.className = "cogs-qty";
    quantity.textContent = row.quantity === null ? "нет продаж за день" : `продали ${formatCount(row.quantity)} шт.`;

    const input = document.createElement("input");
    input.className = "text-input";
    input.inputMode = "decimal";
    input.autocomplete = "off";
    input.placeholder = "не задана";
    input.value = row.stored ? row.stored.cogs_per_unit : "";

    const error = document.createElement("p");
    error.className = "field-error";
    error.hidden = true;

    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn-secondary btn-control";
    button.textContent = "Сохранить";
    button.addEventListener("click", () => { void saveProductCost(row, input.value, error, button); });

    wrapper.append(name, quantity, input, button, error);
    ui.cogsRows.appendChild(wrapper);
  }
}

function renderSettings() {
  const settings = state.settings;
  if (!settings) {
    ui.settingsCard.hidden = true;
    return;
  }

  ui.settingsCard.hidden = false;
  ui.taxRateInput.value = settings.tax_rate === null || settings.tax_rate === undefined ? "" : settings.tax_rate;
  ui.taxError.hidden = true;
  ui.finalityInput.checked = Boolean(settings.finality_confirmed);
  ui.finalityError.hidden = true;
  ui.finalityHint.textContent = settings.finality_confirmed
    ? "Вы подтвердили, что день закрыт финансово."
    : "Wildberries не сообщает, закрыт ли день. Пока вы это не подтвердите, прибыль не рассчитывается.";
  renderCogsRows();
}

/* ---------- техническая сводка (свёрнута по умолчанию) ---------- */

function renderTech(audit) {
  const references = audit.raw_references?.objects || [];
  renderRows(ui.techRows, [
    { label: "Операционная дата", value: audit.operational_date },
    { label: "Аккаунт", value: audit.account_id },
    { label: "Продавец", value: audit.seller_id },
    { label: "Источник данных", value: audit.data_origin },
    { label: "Инджест", value: audit.ingestion_status },
    { label: "Финансовый статус", value: audit.finance_status || MISSING },
    { label: "Статус аудита", value: audit.audit_status },
    { label: "Raw-объектов", value: String(references.length) },
    { label: "PDF", value: audit.report_artifact?.pdf_path },
  ]);

  ui.techDiagnostics.replaceChildren();
  const diagnostics = audit.diagnostics || [];
  if (diagnostics.length === 0) {
    const li = document.createElement("li");
    li.textContent = "Диагностических сообщений нет.";
    ui.techDiagnostics.appendChild(li);
    return;
  }
  for (const line of diagnostics) {
    const li = document.createElement("li");
    li.textContent = line;
    ui.techDiagnostics.appendChild(li);
  }
}

/* ---------- rendering the whole audit ---------- */

function renderAudit(audit) {
  state.audit = audit;
  const metrics = readMetrics(audit);

  const dateLabel = formatDateRu(audit.operational_date);
  ui.auditDateCaption.textContent = ` · ${dateLabel}`;
  if (audit.operational_date) ui.auditDateInput.value = audit.operational_date;

  renderVerdict(audit, metrics);
  renderKpis(metrics);
  renderFunnel(metrics);
  renderFinance(audit, metrics);
  renderAds(audit, metrics);
  renderActions(metrics);
  renderStatus(audit);
  renderTech(audit);

  if (audit.report_artifact?.pdf_path) {
    ui.pdfLink.hidden = false;
    ui.pdfLink.href = `/api/reports/${audit.account_id}/${audit.operational_date}/report.pdf`;
  } else {
    ui.pdfLink.hidden = true;
  }

  ui.dashboard.hidden = false;
}

function formatDateRu(isoDate) {
  if (!isoDate) return "—";
  const months = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
  const [year, month, day] = isoDate.split("-").map(Number);
  return `${Number(day)} ${months[month - 1]} ${year}`;
}

/* ---------- сброс экрана ---------- */

/*
 * Полный сброс перед новым запросом.
 * Старый результат не должен переживать ошибку: без этого под баннером
 * «Не удалось получить данные» оставались цифры предыдущего аудита.
 */
function resetDashboard() {
  state.audit = null;
  state.settings = null;
  ui.dashboard.hidden = true;
  ui.pdfLink.hidden = true;
  ui.auditDateCaption.textContent = " · —";
  ui.verdictCard.dataset.severity = "neutral";
  ui.verdictSeverity.dataset.severity = "neutral";
  ui.financeExplain.hidden = true;
  ui.adEmpty.hidden = true;
  ui.settingsCard.hidden = true;
  ui.taxRateInput.value = "";
  ui.finalityInput.checked = false;
  ui.taxError.hidden = true;
  ui.finalityError.hidden = true;
  ui.cogsEmpty.hidden = true;

  for (const id of [
    "verdictSeverityText", "verdictHeadline", "verdictDetail", "verdictNote",
    "kpiSales", "kpiSalesHint", "kpiRevenue", "kpiRevenueHint", "kpiAds", "kpiAdsHint",
    "kpiProfit", "kpiProfitHint", "adsTotal",
    "statusLabel", "statusDescription", "statusReason", "financeExplainLead",
  ]) {
    ui[id].textContent = "";
  }
  for (const id of [
    "funnelSteps", "funnelRates", "financeRows", "adRows", "actionList",
    "financeMissingList", "techRows", "techDiagnostics", "cogsRows",
  ]) {
    ui[id].replaceChildren();
  }
}

/* ---------- доступ к данным ---------- */

async function loadAccounts() {
  const response = await fetch("/api/accounts");
  if (!response.ok) throw new Error(`accounts ${response.status}`);
  const payload = await response.json();
  state.accounts = payload.accounts || [];

  ui.accountSelect.replaceChildren();
  for (const account of state.accounts) {
    const option = document.createElement("option");
    option.value = account.account_id;
    option.textContent = account.seller_id || account.account_id;
    option.disabled = !account.active;
    ui.accountSelect.appendChild(option);
  }
  if (state.accounts.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Зарегистрированных аккаунтов нет";
    ui.accountSelect.appendChild(option);
  }
  return state.accounts.length > 0;
}

async function runAudit(request) {
  state.lastRequest = request;
  resetDashboard();
  ui.errorBanner.hidden = true;
  ui.errorDetail.textContent = "";
  ui.loadingState.hidden = false;
  ui.submitBtn.disabled = true;
  ui.connectionStatus.textContent = "Получаем аудит…";
  try {
    const params = new URLSearchParams();
    if (request.date) params.set("date", request.date);
    params.set("data_origin", "real_wb_data");
    const response = await fetch(`/audit/${request.accountId}?${params.toString()}`);
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(payload?.detail || `API error ${response.status}`);
    }
    if (!payload || typeof payload !== "object") {
      throw new Error("API вернул пустой ответ");
    }
    ui.loadingState.hidden = true;
    renderAudit(payload);
    // Сохранённые параметры — второстепенный блок: он не должен ронять экран аудита.
    try {
      await loadSettings(request.accountId, payload.operational_date);
    } catch {
      state.settings = null;
    }
    renderSettings();
    ui.connectionStatus.textContent = "Данные получены из существующего аудита.";
  } catch (error) {
    ui.loadingState.hidden = true;
    resetDashboard();
    ui.errorBanner.hidden = false;
    ui.errorDetail.textContent = String(error?.message || error);
    ui.connectionStatus.textContent = "Соединение с API потеряно.";
  } finally {
    ui.submitBtn.disabled = false;
  }
}

async function loadSettings(accountId, operationalDate) {
  const params = new URLSearchParams();
  if (operationalDate) params.set("date", operationalDate);
  const response = await fetch(`/api/accounts/${accountId}/financial-settings?${params.toString()}`);
  if (!response.ok) throw new Error(`financial settings ${response.status}`);
  state.settings = await response.json();
}

async function saveFinancialSetting(endpoint, body, errorElement, button, fallbackMessage) {
  const request = currentRequest();
  if (!request) return;
  errorElement.hidden = true;
  if (button) button.disabled = true;
  try {
    const response = await fetch(`/api/accounts/${request.accountId}/financial-settings/${endpoint}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(payload?.detail || fallbackMessage);
    state.settings = payload;
    renderSettings();
    // Значения считает backend: экран только перезапускает существующий аудит.
    await runAudit(request);
  } catch (error) {
    errorElement.hidden = false;
    errorElement.textContent = String(error?.message || error);
  } finally {
    if (button) button.disabled = false;
  }
}

function saveTaxRate() {
  return saveFinancialSetting(
    "tax",
    { tax_rate: ui.taxRateInput.value },
    ui.taxError,
    ui.saveTaxBtn,
    "Не удалось сохранить налоговую ставку",
  );
}

function saveFinalityConfirmation() {
  const operationalDate = state.audit?.operational_date || ui.auditDateInput.value;
  if (!operationalDate) {
    ui.finalityError.hidden = false;
    ui.finalityError.textContent = "Сначала выберите дату аудита.";
    return Promise.resolve();
  }
  return saveFinancialSetting(
    "finality",
    { operational_date: operationalDate, confirmed: ui.finalityInput.checked },
    ui.finalityError,
    ui.saveFinalityBtn,
    "Не удалось сохранить подтверждение",
  );
}

function saveProductCost(row, value, errorElement, button) {
  return saveFinancialSetting(
    "cogs",
    { sku: row.sku, cogs_per_unit: value, seller_sku: row.sellerSku },
    errorElement,
    button,
    "Не удалось сохранить себестоимость",
  );
}

function currentRequest() {
  const accountId = ui.accountSelect.value;
  const date = ui.auditDateInput.value || null;
  return accountId ? { accountId, date } : null;
}

async function boot() {
  ui.auditForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const request = currentRequest();
    if (request) void runAudit(request);
  });
  ui.retryBtn.addEventListener("click", () => {
    void runAudit(state.lastRequest || currentRequest());
  });
  ui.saveTaxBtn.addEventListener("click", () => { void saveTaxRate(); });
  ui.saveFinalityBtn.addEventListener("click", () => { void saveFinalityConfirmation(); });

  try {
    const hasAccounts = await loadAccounts();
    if (!hasAccounts) {
      ui.connectionStatus.textContent = "API доступен, но аккаунтов не найдено.";
      ui.submitBtn.disabled = true;
      return;
    }
    ui.connectionStatus.textContent = "API готов.";
    // Дата не вычисляется на клиенте: без параметра backend сам берёт D-1 Europe/Moscow.
    await runAudit({ accountId: ui.accountSelect.value, date: null });
  } catch (error) {
    ui.connectionStatus.textContent = "API недоступен.";
    ui.errorBanner.hidden = false;
    ui.errorDetail.textContent = String(error?.message || error);
  }
}

boot();
