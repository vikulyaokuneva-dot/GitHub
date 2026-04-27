# Testing

## Stable baseline

Ozon audit is currently disabled from the stable pytest baseline because that area is unfinished and not under active development.

Run the stable baseline with:

```bash
python -m pytest -m "not ozon_audit" -q
```

## Full test suite

Run the full suite, including Ozon audit tests, with:

```bash
python -m pytest -q
```

## Report v2

Report v2 should remain green independently:

```bash
python -m pytest report_v2\tests -q
```
