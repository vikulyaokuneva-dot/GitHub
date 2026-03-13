from __future__ import annotations

from typing import Any, Dict, List, Mapping


def _as_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _top_rows(rows: List[Dict[str, Any]], key: str, limit: int = 5, reverse: bool = True) -> List[Dict[str, Any]]:
    return sorted(
        [row for row in rows if isinstance(row, dict)],
        key=lambda row: (_as_float(row.get(key)), str(row.get('sku') or '')),
        reverse=reverse,
    )[:limit]


def _signal(
    *,
    signal_type: str,
    entity_type: str,
    entity_id: str,
    severity: str,
    title: str,
    description: str,
    evidence: Dict[str, Any],
    recommendation: str,
    impact_score: float,
) -> Dict[str, Any]:
    return {
        'signal_type': signal_type,
        'entity_type': entity_type,
        'entity_id': entity_id,
        'severity': severity,
        'title': title,
        'description': description,
        'evidence': evidence,
        'recommendation': recommendation,
        'impact_score': round(float(max(0.0, min(100.0, impact_score))), 2),
    }


def build_distribution_signals(
    sku_items: List[Dict[str, Any]],
    summary: Mapping[str, Any],
    *,
    profit_leak_threshold: float,
    weak_threshold: float,
    critical_threshold: float,
) -> List[Dict[str, Any]]:
    signals: List[Dict[str, Any]] = []

    for row in sku_items:
        if not isinstance(row, dict):
            continue
        sku = str(row.get('sku') or '').strip()
        if not sku:
            continue
        state = str(row.get('distribution_state') or '').strip().lower()
        localization_share = _as_float(row.get('localization_share'))
        ktr = _as_float(row.get('ktr'))
        krp = _as_float(row.get('krp'))
        irp_penalty_total = _as_float(row.get('estimated_irp_penalty_total'))

        if state == 'critical':
            signals.append(
                _signal(
                    signal_type='distribution_critical_sku',
                    entity_type='sku',
                    entity_id=sku,
                    severity='high',
                    title='Критично низкая локализация SKU',
                    description='Локализация заказов SKU находится в критической зоне.',
                    evidence={
                        'sku': sku,
                        'localization_share': localization_share,
                        'ktr': ktr,
                        'krp': krp,
                        'estimated_irp_penalty_total': irp_penalty_total,
                    },
                    recommendation='Приоритетно перераспределить остатки по складам с высоким спросом.',
                    impact_score=max(0.0, 100.0 - localization_share),
                )
            )
        elif state == 'weak':
            signals.append(
                _signal(
                    signal_type='distribution_weak_sku',
                    entity_type='sku',
                    entity_id=sku,
                    severity='medium',
                    title='Слабая локализация SKU',
                    description='Локализация SKU в зоне повышенного логистического риска.',
                    evidence={
                        'sku': sku,
                        'localization_share': localization_share,
                        'ktr': ktr,
                        'krp': krp,
                        'estimated_irp_penalty_total': irp_penalty_total,
                    },
                    recommendation='Увеличить наличие в регионах с устойчивым спросом.',
                    impact_score=max(0.0, weak_threshold - localization_share + 20.0),
                )
            )
        elif state == 'watch':
            signals.append(
                _signal(
                    signal_type='distribution_watch_sku',
                    entity_type='sku',
                    entity_id=sku,
                    severity='low',
                    title='Зона наблюдения по локализации SKU',
                    description='Локализация SKU ниже целевого уровня и требует контроля.',
                    evidence={
                        'sku': sku,
                        'localization_share': localization_share,
                        'ktr': ktr,
                        'krp': krp,
                        'estimated_irp_penalty_total': irp_penalty_total,
                    },
                    recommendation='Мониторить локализацию и корректировать запасы точечно.',
                    impact_score=max(0.0, 60.0 - localization_share),
                )
            )

        if irp_penalty_total >= float(profit_leak_threshold):
            signals.append(
                _signal(
                    signal_type='distribution_profit_leak',
                    entity_type='sku',
                    entity_id=sku,
                    severity='high',
                    title='Потенциальная IRP-утечка прибыли по SKU',
                    description='Оценочная IRP-нагрузка по SKU превышает порог.',
                    evidence={
                        'sku': sku,
                        'estimated_irp_penalty_total': irp_penalty_total,
                        'threshold': float(profit_leak_threshold),
                        'localization_share': localization_share,
                    },
                    recommendation='Перераспределить запасы и сократить долю заказов из нелокальных регионов.',
                    impact_score=min(100.0, irp_penalty_total / max(1.0, float(profit_leak_threshold)) * 40.0 + 40.0),
                )
            )

    weighted_localization = _as_float(summary.get('weighted_average_localization_share'))
    problematic = int(summary.get('skus_below_60_localization', 0) or 0)
    sku_total = int(summary.get('total_skus_analyzed', 0) or 0)
    aggregate_penalty = _as_float(summary.get('aggregate_estimated_irp_penalty_total'))
    problematic_share = (problematic / sku_total) if sku_total > 0 else 0.0

    portfolio_risk = (
        weighted_localization < weak_threshold
        or problematic_share >= 0.50
        or aggregate_penalty >= float(profit_leak_threshold) * 3.0
    )
    if portfolio_risk:
        signals.append(
            _signal(
                signal_type='distribution_portfolio_risk',
                entity_type='portfolio',
                entity_id='seller',
                severity='high' if weighted_localization < critical_threshold else 'medium',
                title='Портфельный риск территориального распределения',
                description='Портфель демонстрирует повышенный риск логистической неэффективности и IRP-нагрузки.',
                evidence={
                    'weighted_average_localization_share': weighted_localization,
                    'problematic_skus': problematic,
                    'total_skus': sku_total,
                    'problematic_share': round(problematic_share, 4),
                    'aggregate_estimated_irp_penalty_total': aggregate_penalty,
                },
                recommendation='Сфокусироваться на SKU с высоким спросом и низкой локализацией, перераспределить остатки по регионам спроса.',
                impact_score=min(100.0, max(40.0, (100.0 - weighted_localization) + problematic_share * 30.0)),
            )
        )

    # Keep the output compact for downstream AI stage.
    return _top_rows(signals, key='impact_score', limit=40, reverse=True)

