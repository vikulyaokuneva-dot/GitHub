from __future__ import annotations



import json

from datetime import datetime, timezone

from pathlib import Path

from typing import Any, Dict, List, Mapping



from .coefficients import resolve_effective_date, resolve_threshold

from .irp_calculator import estimate_irp_penalty, resolve_average_retail_price

from .localization_calculator import build_localization_rows

from .models import DistributionEngineOutput, SkuDistributionMetrics

from .signals import build_distribution_signals





DEFAULT_DISTRIBUTION_CONFIG: Dict[str, Any] = {

    'enable_territorial_distribution_engine': True,

    'wb_irp_effective_date': '2026-03-23',

    'distribution_profit_leak_threshold': 5000.0,

    'localization_watch_threshold': 60.0,

    'localization_weak_threshold': 40.0,

    'localization_critical_threshold': 20.0,

}





_STATE_LABELS_RU = {

    'no_orders': '\u043d\u0435\u0442 \u0437\u0430\u043a\u0430\u0437\u043e\u0432',

    'strong': '\u0440\u0430\u0441\u043f\u0440\u0435\u0434\u0435\u043b\u0435\u043d\u0438\u0435 \u0445\u043e\u0440\u043e\u0448\u0435\u0435',

    'watch': '\u0437\u043e\u043d\u0430 \u043d\u0430\u0431\u043b\u044e\u0434\u0435\u043d\u0438\u044f',

    'weak': '\u0441\u043b\u0430\u0431\u0430\u044f \u043b\u043e\u043a\u0430\u043b\u0438\u0437\u0430\u0446\u0438\u044f',

    'critical': '\u043a\u0440\u0438\u0442\u0438\u0447\u043d\u043e \u043d\u0438\u0437\u043a\u0430\u044f \u043b\u043e\u043a\u0430\u043b\u0438\u0437\u0430\u0446\u0438\u044f',

}





def _utc_now_iso() -> str:

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')





def _as_float(value: Any) -> float:

    try:

        if value is None:

            return 0.0

        return float(value)

    except (TypeError, ValueError):

        return 0.0





def _extract_sku_metrics_index(metrics: Any) -> Dict[str, Dict[str, Any]]:

    if not isinstance(metrics, dict):

        return {}

    rows = metrics.get('sku_metrics')

    if not isinstance(rows, list):

        return {}

    out: Dict[str, Dict[str, Any]] = {}

    for row in rows:

        if not isinstance(row, dict):

            continue

        sku = str(row.get('sku') or '').strip().lower()

        if sku:

            out[sku] = row

    return out





def _resolve_config(cfg: Mapping[str, Any] | None) -> Dict[str, Any]:

    resolved = dict(DEFAULT_DISTRIBUTION_CONFIG)

    if not isinstance(cfg, Mapping):

        return resolved



    section = cfg.get('territorial_distribution')

    if isinstance(section, Mapping):

        for key in resolved.keys():

            if key in section:

                resolved[key] = section.get(key)



    for key in resolved.keys():

        if key in cfg:

            resolved[key] = cfg.get(key)



    resolved['enable_territorial_distribution_engine'] = bool(resolved.get('enable_territorial_distribution_engine', True))

    resolved['wb_irp_effective_date'] = resolve_effective_date(resolved.get('wb_irp_effective_date'))

    resolved['distribution_profit_leak_threshold'] = resolve_threshold(

        resolved.get('distribution_profit_leak_threshold'),

        DEFAULT_DISTRIBUTION_CONFIG['distribution_profit_leak_threshold'],

    )

    resolved['localization_watch_threshold'] = resolve_threshold(

        resolved.get('localization_watch_threshold'),

        DEFAULT_DISTRIBUTION_CONFIG['localization_watch_threshold'],

    )

    resolved['localization_weak_threshold'] = resolve_threshold(

        resolved.get('localization_weak_threshold'),

        DEFAULT_DISTRIBUTION_CONFIG['localization_weak_threshold'],

    )

    resolved['localization_critical_threshold'] = resolve_threshold(

        resolved.get('localization_critical_threshold'),

        DEFAULT_DISTRIBUTION_CONFIG['localization_critical_threshold'],

    )

    return resolved





def _distribution_state(localization_share: float | None, total_orders: float, cfg: Mapping[str, Any]) -> str:

    if total_orders <= 0:

        return 'no_orders'

    if localization_share is None:

        return 'no_orders'

    watch = float(cfg.get('localization_watch_threshold', 60.0))

    weak = float(cfg.get('localization_weak_threshold', 40.0))

    critical = float(cfg.get('localization_critical_threshold', 20.0))



    if localization_share >= watch:

        return 'strong'

    if localization_share >= weak:

        return 'watch'

    if localization_share >= critical:

        return 'weak'

    return 'critical'





def _legacy_status_from_state(state: str) -> str:

    if state == 'strong':

        return 'balanced'

    if state == 'watch':

        return 'moderate_mismatch'

    if state in {'weak', 'critical'}:

        return 'misallocated'

    if state == 'no_orders':

        return 'no_demand_data'

    return 'insufficient_distribution_data'





def _summary(items: List[Dict[str, Any]]) -> Dict[str, Any]:

    total_skus = len(items)

    total_orders = sum(_as_float(row.get('total_orders')) for row in items)

    weighted_localization_sum = sum(_as_float(row.get('localization_share')) * _as_float(row.get('total_orders')) for row in items)

    weighted_localization = round(weighted_localization_sum / total_orders, 4) if total_orders > 0 else 0.0



    skus_with_irp_penalty = sum(1 for row in items if _as_float(row.get('estimated_irp_penalty_total')) > 0)

    below_60 = sum(1 for row in items if _as_float(row.get('localization_share')) < 60.0 and _as_float(row.get('total_orders')) > 0)

    below_40 = sum(1 for row in items if _as_float(row.get('localization_share')) < 40.0 and _as_float(row.get('total_orders')) > 0)

    below_20 = sum(1 for row in items if _as_float(row.get('localization_share')) < 20.0 and _as_float(row.get('total_orders')) > 0)



    aggregate_penalty = round(sum(_as_float(row.get('estimated_irp_penalty_total')) for row in items), 2)



    ktr_values = [_as_float(row.get('ktr')) for row in items if row.get('ktr') is not None]

    avg_ktr = round(sum(ktr_values) / len(ktr_values), 4) if ktr_values else 0.0



    state_counts = {

        'no_orders': sum(1 for row in items if str(row.get('distribution_state') or '') == 'no_orders'),

        'strong': sum(1 for row in items if str(row.get('distribution_state') or '') == 'strong'),

        'watch': sum(1 for row in items if str(row.get('distribution_state') or '') == 'watch'),

        'weak': sum(1 for row in items if str(row.get('distribution_state') or '') == 'weak'),

        'critical': sum(1 for row in items if str(row.get('distribution_state') or '') == 'critical'),

    }



    top_worst_localization = [

        {

            'sku': str(row.get('sku') or ''),

            'localization_share': row.get('localization_share'),

            'total_orders': row.get('total_orders'),

        }

        for row in sorted(items, key=lambda r: (_as_float(r.get('localization_share')) if r.get('localization_share') is not None else 10**9, -_as_float(r.get('total_orders'))))

        if _as_float(row.get('total_orders')) > 0

    ][:10]

    top_irp_penalty = [

        {

            'sku': str(row.get('sku') or ''),

            'estimated_irp_penalty_total': row.get('estimated_irp_penalty_total'),

            'localization_share': row.get('localization_share'),

        }

        for row in sorted(items, key=lambda r: (_as_float(r.get('estimated_irp_penalty_total')), str(r.get('sku') or '')), reverse=True)

        if _as_float(row.get('estimated_irp_penalty_total')) > 0

    ][:10]



    return {

        'total_skus_analyzed': total_skus,

        'skus_with_irp_penalty': skus_with_irp_penalty,

        'skus_below_60_localization': below_60,

        'skus_below_40_localization': below_40,

        'skus_critical_below_20_localization': below_20,

        'aggregate_estimated_irp_penalty_total': aggregate_penalty,

        'weighted_average_localization_share': weighted_localization,

        'distribution_efficiency_score': round(max(0.0, min(100.0, weighted_localization)), 2),

        'distribution_state_counts': state_counts,

        'top_weak_localization_skus': top_worst_localization,

        'top_irp_penalty_skus': top_irp_penalty,

        # Backward-compatible aliases for existing facts/report blocks.

        'sku_total': total_skus,

        'sku_with_ktr': total_skus,

        'balanced_count': state_counts['strong'],

        'moderate_mismatch_count': state_counts['watch'],

        'misallocated_count': state_counts['weak'] + state_counts['critical'],

        'insufficient_distribution_data_count': state_counts['no_orders'],

        'no_stock_data_count': 0,

        'insufficient_total_count': state_counts['no_orders'],

        'avg_ktr': avg_ktr,

        'top_misaligned_skus': [

            str(item.get('sku') or '') for item in top_worst_localization[:5] if str(item.get('sku') or '').strip()

        ],

    }





def build_territorial_distribution(

    metrics: Dict[str, Any],

    stocks_raw: Dict[str, Any] | List[Dict[str, Any]] | None = None,

    seller_id: str | None = None,

    run_date: str | None = None,

    config: Mapping[str, Any] | None = None,

) -> Dict[str, Any]:

    cfg = _resolve_config(config)

    resolved_seller_id = str(seller_id or (metrics.get('seller_id') if isinstance(metrics, dict) else '') or '').strip()

    resolved_run_date = str(run_date or (metrics.get('run_date') if isinstance(metrics, dict) else '') or '').strip()



    if not bool(cfg.get('enable_territorial_distribution_engine', True)):

        payload = DistributionEngineOutput(

            seller_id=resolved_seller_id,

            report_date=resolved_run_date,

            status='disabled',

            warnings=[{'code': 'territorial_distribution_disabled', 'message': 'Territorial distribution engine is disabled by config.'}],

            metadata={

                'engine': 'territorial_distribution_engine',

                'version': '2.0',

                'seller_id': resolved_seller_id,

                'run_date': resolved_run_date,

                'generated_at': _utc_now_iso(),

                'wb_irp_effective_date': str(cfg.get('wb_irp_effective_date') or ''),

            },

            summary={'total_skus_analyzed': 0, 'distribution_efficiency_score': 0.0, 'aggregate_estimated_irp_penalty_total': 0.0},

            signals=[],

            sku_metrics=[],

        )

        return payload.to_dict()



    localization_rows, warnings = build_localization_rows(metrics if isinstance(metrics, dict) else {}, stocks_raw=stocks_raw)

    sku_metrics_index = _extract_sku_metrics_index(metrics if isinstance(metrics, dict) else {})

    sku_items: List[SkuDistributionMetrics] = []



    effective_date = str(cfg.get('wb_irp_effective_date') or '2026-03-23')



    for row in localization_rows:

        sku = str(row.get('sku') or '').strip()

        if not sku:

            continue

        total_orders = max(0.0, _as_float(row.get('total_orders')))

        local_orders = max(0.0, _as_float(row.get('local_orders')))

        localization_share = row.get('localization_share')

        if localization_share is not None:

            localization_share = round(float(localization_share), 6)



        metric_row = sku_metrics_index.get(sku.lower(), {})

        average_price, price_source, price_warning = resolve_average_retail_price(metric_row, total_orders=total_orders)



        irp = estimate_irp_penalty(

            localization_share=localization_share,

            total_orders=total_orders,

            average_retail_price=average_price,

            report_date=resolved_run_date,

            effective_date=effective_date,

        )



        state = _distribution_state(localization_share, total_orders, cfg)

        notes: List[str] = []

        if price_warning:

            notes.append(str(price_warning))

        if not bool(irp.get('effective_date_applied', False)):

            notes.append('irp_effect_not_applied_yet')

        if _as_float(localization_share) >= 60.0:

            notes.append('krp_zero_due_to_localization_60_plus')



        diagnostics = {

            'price_source': price_source,

            'local_orders_source': row.get('local_orders_source'),

            'distribution_gap': row.get('distribution_gap'),

            'locality_score': row.get('locality_score'),

            'demand_by_warehouse': row.get('demand_by_warehouse', {}),

            'stock_by_warehouse': row.get('stock_by_warehouse', {}),

            'demand_share_by_warehouse': row.get('demand_share_by_warehouse', {}),

            'stock_share_by_warehouse': row.get('stock_share_by_warehouse', {}),

            'dominant_demand_warehouses': row.get('dominant_demand_warehouses', []),

            'dominant_stock_warehouses': row.get('dominant_stock_warehouses', []),

            'reverse_logistics_modeling': 'deferred_until_volume_fields_available',

        }



        sku_items.append(

            SkuDistributionMetrics(

                sku=sku,

                total_orders=round(total_orders, 6),

                local_orders=round(local_orders, 6),

                localization_share=localization_share,

                ktr=round(_as_float(irp.get('ktr')), 4),

                krp=round(_as_float(irp.get('krp')), 6),

                average_retail_price=round(float(average_price), 4) if average_price is not None else None,

                irp_penalty_per_order=(round(_as_float(irp.get('irp_penalty_per_order')), 6) if irp.get('irp_penalty_per_order') is not None else None),

                estimated_irp_penalty_total=round(_as_float(irp.get('estimated_irp_penalty_total')), 6),

                distribution_state=state,

                distribution_state_label_ru=_STATE_LABELS_RU.get(state, state),

                effective_date_applied=bool(irp.get('effective_date_applied', False)),

                confidence=str(row.get('confidence') or 'low'),

                diagnostics=diagnostics,

                notes=notes,

            )

        )



    items_dict: List[Dict[str, Any]] = []

    for item in sku_items:

        row = item.to_dict()

        row['status'] = _legacy_status_from_state(item.distribution_state)

        row['distribution_gap'] = row.get('diagnostics', {}).get('distribution_gap', row.get('distribution_gap'))

        row['demand_by_warehouse'] = row.get('diagnostics', {}).get('demand_by_warehouse', {}) or {}

        row['stock_by_warehouse'] = row.get('diagnostics', {}).get('stock_by_warehouse', {}) or {}

        row['demand_share_by_warehouse'] = row.get('diagnostics', {}).get('demand_share_by_warehouse', {}) or {}

        row['stock_share_by_warehouse'] = row.get('diagnostics', {}).get('stock_share_by_warehouse', {}) or {}

        row['dominant_demand_warehouses'] = row.get('diagnostics', {}).get('dominant_demand_warehouses') or sorted(

            [str(k) for k, v in row['demand_share_by_warehouse'].items() if _as_float(v) > 0.2],

            key=lambda k: -_as_float(row['demand_share_by_warehouse'].get(k)),

        )

        row['dominant_stock_warehouses'] = row.get('diagnostics', {}).get('dominant_stock_warehouses') or sorted(

            [str(k) for k, v in row['stock_share_by_warehouse'].items() if _as_float(v) > 0.2],

            key=lambda k: -_as_float(row['stock_share_by_warehouse'].get(k)),

        )

        row['locality_score'] = row.get('diagnostics', {}).get('locality_score')

        if row['locality_score'] is None:

            row['locality_score'] = round(

                sum(

                    min(

                        _as_float(row['demand_share_by_warehouse'].get(k)),

                        _as_float(row['stock_share_by_warehouse'].get(k)),

                    )

                    for k in set(row['demand_share_by_warehouse']) | set(row['stock_share_by_warehouse'])

                ),

                6,

            )

        row['total_buys'] = int(round(_as_float(row.get('total_orders', 0.0))))

        row['total_stock'] = int(round(sum(_as_float(v) for v in row['stock_by_warehouse'].values())))

        row['low_sample_warning'] = str(row.get('confidence') or '').strip().lower() == 'low'

        row['relocation_hint'] = (

            'priority_relocation' if row.get('distribution_state') in {'critical', 'weak'}

            else ('monitor' if row.get('distribution_state') == 'watch' else None)

        )

        items_dict.append(row)



    summary = _summary(items_dict)

    signals = build_distribution_signals(

        items_dict,

        summary,

        profit_leak_threshold=float(cfg.get('distribution_profit_leak_threshold', 5000.0)),

        weak_threshold=float(cfg.get('localization_weak_threshold', 40.0)),

        critical_threshold=float(cfg.get('localization_critical_threshold', 20.0)),

    )



    if not items_dict:

        status = 'insufficient_data'

    elif warnings:

        status = 'partial'

    else:

        status = 'ok'



    metadata = {

        'engine': 'territorial_distribution_engine',

        'version': '2.0',

        'seller_id': resolved_seller_id,

        'run_date': resolved_run_date,

        'generated_at': _utc_now_iso(),

        'wb_irp_effective_date': effective_date,

        'source_artifacts': ['metrics.json'],

        'reverse_logistics': {

            'mode': 'deferred',

            'details': 'Volume-based reverse logistics can be added when liters/volume fields become available.',

        },

        'config': {

            'enable_territorial_distribution_engine': bool(cfg.get('enable_territorial_distribution_engine', True)),

            'distribution_profit_leak_threshold': float(cfg.get('distribution_profit_leak_threshold', 5000.0)),

            'localization_watch_threshold': float(cfg.get('localization_watch_threshold', 60.0)),

            'localization_weak_threshold': float(cfg.get('localization_weak_threshold', 40.0)),

            'localization_critical_threshold': float(cfg.get('localization_critical_threshold', 20.0)),

        },

    }



    payload = DistributionEngineOutput(

        seller_id=resolved_seller_id,

        report_date=resolved_run_date,

        status=status,

        warnings=list(warnings),

        metadata=metadata,

        summary=summary,

        signals=signals,

        sku_metrics=sku_items,

    ).to_dict()



    payload['aggregate_estimated_irp_penalty_total'] = summary.get('aggregate_estimated_irp_penalty_total', 0.0)

    payload['distribution_efficiency_score'] = summary.get('distribution_efficiency_score', 0.0)

    return payload





def save_territorial_distribution(output_path: Path, data: Dict[str, Any]) -> None:

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open('w', encoding='utf-8') as file:

        json.dump(data, file, ensure_ascii=False, indent=2)

