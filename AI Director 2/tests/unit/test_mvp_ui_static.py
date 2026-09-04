"""Contract tests for the audit web screen (static layer over the existing API).

The screen must stay a pure presentation layer: it reads the existing
``/audit/{account_id}`` result, never recalculates finance, never leaks
credentials, and never renders MISSING as zero.
"""

from __future__ import annotations

from pathlib import Path


STATIC_ROOT = Path("apps/web/static")


def _index() -> str:
    return (STATIC_ROOT / "index.html").read_text(encoding="utf-8")


def _app() -> str:
    return (STATIC_ROOT / "app.js").read_text(encoding="utf-8")


def test_screen_uses_existing_audit_endpoint_and_never_touches_credentials() -> None:
    app_js = _app()

    assert "/audit/" in app_js, "screen must call the existing audit endpoint"
    assert "/api/accounts" in app_js
    assert "api/reports" in app_js, "PDF must be served by the existing report endpoint"
    for forbidden in ("WB_API_TOKEN", "credential", "Authorization", "api_key", "fetch(\"/analysis"):
        assert forbidden not in app_js


def test_screen_does_not_duplicate_backend_calculations() -> None:
    app_js = _app()

    # No finance arithmetic in the browser: values are read from the audit result.
    assert "report_payload" in app_js and "metrics" in app_js
    assert "audit_status" in app_js, "status must come from the backend field"
    for forbidden in ("net_profit =", "Decimal", "sum(", "reduce("):
        assert forbidden not in app_js


def test_missing_is_never_rendered_as_zero() -> None:
    app_js = _app()

    assert 'const MISSING = "Нет данных"' in app_js
    # a ratio without a usable denominator yields no value instead of 0%
    assert "denominator === 0" in app_js
    # absent finance values keep their own human wording
    for label in ("Не рассчитана", "Не задана", "Не задан", "Недостаточно данных для вывода"):
        assert label in app_js


def test_main_screen_uses_business_language_without_technical_metric_keys() -> None:
    index = _index()

    for block in (
        "ИИ Директор ВБ",
        "Главный вывод",
        "Ключевые показатели",
        "Воронка продаж",
        "Финансы",
        "Реклама",
        "Что нужно сделать",
        "Статус аудита",
    ):
        assert block in index

    for technical in ("realized_revenue", "advertising_direct_sku", "advertising_campaign", "payload_sha256", "raw_object_id"):
        assert technical not in index


def test_technical_diagnostics_are_collapsed_outside_the_main_flow() -> None:
    index = _index()

    assert "<details" in index and "Техническая информация" in index
    assert 'id="techDiagnostics"' in index
    assert index.index('class="tech"') > index.index('id="statusCard"'), "technical block must sit below the audit status"


def test_error_state_resets_previous_result_before_new_request() -> None:
    """Старый аудит не имеет права переживать ошибку нового запроса."""
    app_js = _app()

    assert "function resetDashboard()" in app_js
    assert "state.audit = null;" in app_js
    # сброс обязан произойти до обращения к API
    assert app_js.index("resetDashboard();") < app_js.index("await fetch(`/audit/")
    # и повториться в обработчике ошибки, чтобы частичный рендер не остался на экране
    reset_body = app_js[app_js.index("function resetDashboard() {"):app_js.index("/* ---------- доступ к данным")]
    assert "ui.dashboard.hidden = true;" in reset_body
    catch_block = app_js[app_js.index("  } catch (error) {"):]
    assert "resetDashboard();" in catch_block.split("finally", 1)[0]
    # прежняя условная прячущая строка, из-за которой данные и оставались видимыми
    assert "if (state.audit === null) ui.dashboard.hidden = true;" not in app_js


def test_severity_is_a_text_chip_and_no_emoji_circle_glyphs_remain() -> None:
    index = _index()
    app_js = _app()
    styles = (STATIC_ROOT / "styles.css").read_text(encoding="utf-8")

    for glyph in ("🔴", "🟡", "🟢", "⚪"):
        assert glyph not in app_js, "индикатор severity не должен зависеть от emoji-шрифта"
    assert 'id="verdictBadge"' not in index
    assert ".verdict-badge" not in styles

    assert 'id="verdictSeverity"' in index and 'id="verdictSeverityText"' in index
    assert ".severity-dot" in styles
    for label in ("Критическая проблема", "Требует внимания", "Недостаточно данных"):
        assert label in app_js


def test_profit_explanation_is_human_language_and_state_driven() -> None:
    index = _index()
    app_js = _app()

    assert "Почему прибыль не рассчитана?" in index
    assert "Для расчёта не хватает:" in index
    assert 'id="financeMissingList"' in index

    # список нехваток строится из состояния backend, а не зашит в разметку
    assert "component_traces" in app_js
    assert 'trace.status !== "missing"' in app_js
    for phrase in ("себестоимости товара", "данных для расчёта налога"):
        assert phrase in app_js

    # внутренние идентификаторы компонентов не попадают в текст
    assert "textContent = trace.component" not in app_js
    assert "${trace.component}" not in app_js
    assert "• ${item.explain}" in app_js


def test_error_state_offers_retry_and_date_selection_exists() -> None:
    index = _index()
    app_js = _app()

    assert "Не удалось получить данные" in index
    assert "Проверьте подключение к Wildberries" in index
    assert 'id="retryBtn"' in index
    assert "Повторить" in index
    assert 'id="auditDateInput"' in index and 'type="date"' in index
    # the client does not invent the default day: the backend resolves D-1
    assert "params.set(\"date\", request.date)" in app_js
    assert "date: null" in app_js


def test_financial_settings_block_is_input_only_and_never_calculates() -> None:
    """Себестоимость и налог задаёт человек; экран их только передаёт."""
    index = _index()
    app_js = _app()

    assert 'id="settingsCard"' in index
    assert "Финансовые параметры" in index
    assert "Себестоимость проданных товаров" in index
    assert 'id="taxRateInput"' in index and 'id="cogsRows"' in index
    assert 'id="finalityInput"' in index

    # значения уходят на backend и возвращаются с него
    assert "/financial-settings/" in app_js
    assert 'method: "PUT"' in app_js
    assert "await runAudit(request);" in app_js, "пересчёт делает backend, экран перезапускает аудит"

    # ни одной финансовой формулы в новом коде нет
    for forbidden in ("tax_rate *", "cogs_per_unit *", "* quantity", "net_profit ="):
        assert forbidden not in app_js

    # сохранённые значения читаются из ответа API, а не держатся в памяти экрана
    assert "state.settings = payload;" in app_js
    assert "state.settings = null;" in app_js


def test_explanation_distinguishes_missing_data_from_an_open_period() -> None:
    """Полные данные при незакрытом дне — это не «нехватка данных»."""
    index = _index()
    app_js = _app()

    assert 'id="financeExplainLead"' in index
    assert "finality_assessment" in app_js
    assert "подтверждения, что день закрыт финансово" in app_js
    assert "Все финансовые данные заданы" in app_js
    assert "Причина: день не подтверждён как закрытый финансово." in app_js
