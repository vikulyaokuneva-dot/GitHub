"""
WB API Loader Implementation Guide and Usage.

Phase 2 Implementation: Data Loaders
====================================

COMPLETED:
✅ AsyncWBClient - async wrapper for WB API with retry logic
✅ AdsParser, OrdersParser, MarginsParser, ReturnsParser, RatingsParser
✅ WBAPILoader.load_data() - full implementation
✅ api_mapping.py - documentation of all WB API endpoints
✅ tests/test_wb_api_loader.py - comprehensive test suite
✅ requirements.txt - updated with async dependencies

WHAT IT DOES:
=============

WBAPILoader loads data from Wildberries API for a specific date and returns
a RawDataBundle with all raw data (ads, orders, margins, returns, ratings).

It uses multiple WB API endpoints in parallel:
  1. /api/advert/v2/adverts - list of ads
  2. /adv/v3/fullstats - detailed ad statistics (views, clicks, spend)
  3. /api/analytics/v3/sales-funnel/products - funnel data (orders, conversions)
  4. /api/v5/supplier/reportDetailByPeriod - detailed orders, returns, margins
  5. /api/v1/supplier/stocks - inventory levels

All data is parsed into domain contracts and returned in RawDataBundle.


USAGE:
======

Basic usage:

    import asyncio
    from datetime import date
    from infrastructure.sources.wb_api_loader import WBAPILoader
    from domain.cabinet import Cabinet, CabinetConfig, CabinetContext
    from pathlib import Path
    
    async def main():
        # 1. Create cabinet with API key
        cabinet = Cabinet(
            id="seller_001",
            name="My Store",
            api_key="your_wb_api_key_here",
            wb_seller_id="12345"
        )
        
        # 2. Create cabinet context
        ctx = CabinetContext(
            cabinet=cabinet,
            config=CabinetConfig(),
            cabinet_root=Path("cabinets/seller_001")
        )
        
        # 3. Load data from API
        loader = WBAPILoader(timeout=60)  # timeout in seconds
        raw_bundle = await loader.load_data(ctx, date(2024, 1, 15))
        
        # 4. Access data
        print(f"Loaded {len(raw_bundle.ads)} ads")
        print(f"Loaded {len(raw_bundle.orders)} orders")
        print(f"Loaded {len(raw_bundle.margins)} margins")
        print(f"Loaded {len(raw_bundle.returns)} returns")
    
    asyncio.run(main())


IMPORTANT DETAILS:
==================

1. API KEY:
   - Get it from WB seller cabinet at https://seller.willow.wildberries.ru/
   - Should be stored securely (use environment variables, not hardcoded)
   - Cabinet.api_key must be set, or ValueError is raised

2. ASYNC USAGE:
   - load_data() is async, must be called with await or asyncio.run()
   - Allows parallel API requests for faster loading
   - All network operations respect rate limiting

3. ERROR HANDLING:
   - 403 Forbidden: Access to ads API might be restricted (returns empty)
   - 204 No Content: No data for period (returns empty list)
   - 429 Too Many Requests: Rate limit hit (auto-retried with backoff)
   - Other errors: Raised as RuntimeError after retries exhausted

4. DATA QUALITY:
   - parse_ads_stats() handles WB's inconsistent field names
   - Parsers skip invalid records (e.g., cost_price=0)
   - Date filtering ensures only requested date is included
   - Aggregation of per-date stats (WB returns daily breakdowns)

5. CABINET ISOLATION:
   - Each cabinet gets its own API context (separate api_key)
   - Data is isolated per cabinet_id
   - Multiple cabinets can be processed in parallel

6. PERFORMANCE:
   - Typical load time: 5-30 seconds depending on data volume
   - Parallel requests share aiohttp ClientSession for efficiency
   - Can load multiple dates in parallel using asyncio.gather()

7. RATE LIMITING:
   - WB API: ~1000 requests/minute limit
   - AsyncWBClient: min 0.2s between requests (tunable)
   - Exponential backoff on 429 errors
   - Batch ad requests (50 ads per request max)


TESTING:
========

Run tests:
    pytest v5/tests/test_wb_api_loader.py -v

Run specific test:
    pytest v5/tests/test_wb_api_loader.py::TestAdsParser::test_parse_ads_stats -v

Run with coverage:
    pytest v5/tests/test_wb_api_loader.py --cov=infrastructure.sources --cov-report=html


NEXT STEPS (Phase 2 continuation):
===================================

1. Integration with CabinetStorage (save RawDataBundle)
2. Implement FileReportLoader (parallel to WBAPILoader)
3. Add config loading (read cabinet info from YAML)
4. Create CLI entry point to test loading
5. Move to Phase 3: Normalization


DATA FLOW DIAGRAM:
==================

    Cabinet (id, api_key, seller_id)
          ↓
    CabinetContext (cabinet + config + paths)
          ↓
    WBAPILoader.load_data(ctx, date)
          ↓
    AsyncWBClient (HTTP requests with retry)
          ↓
    WB API (5 endpoints in parallel)
          ↓
    Parsers (AdsParser, OrdersParser, etc.)
          ↓
    RawDataBundle (ads, orders, margins, returns, ratings)
          ↓
    CabinetStorage.save_raw(bundle)  [Phase 2b]
          ↓
    JSON files in cabinets/{id}/data/raw/{date}.json


DEBUGGING TIPS:
===============

1. Check API key:
    from domain.cabinet import Cabinet
    cabinet = Cabinet(id="test", name="test", api_key="...", wb_seller_id="...")
    assert cabinet.api_key, "API key not set!"

2. Enable logging:
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
3. Mock API for testing:
    Use @patch('infrastructure.sources.wb_api_loader.AsyncWBClient')
    See test_wb_api_loader.py for examples

4. Check date format:
    WB API expects ISO dates: "2024-01-15"
    Always use date.isoformat()

5. Inspect raw responses:
    Access raw_data in parsers to see exact WB API format
    Compare with infrastructure/config/api_mapping.py

6. Check cabinet paths:
    CabinetContext.raw_data_dir = cabinet_root / "data" / "raw"
    Create this directory before saving


COMMON ISSUES:
==============

Issue: RuntimeError: WB API failed after 5 retries
  → Check API key validity
  → Verify internet connection
  → Check WB API status page

Issue: ValueError: Cabinet has no API key configured
  → Set cabinet.api_key before calling load_data()

Issue: Empty results (no ads, orders, etc.)
  → Cabinet may have ads disabled (check WB seller cabinet)
  → Date may have no data (check WB dashboard for activity)
  → 403 Forbidden is returned as empty (not an error)

Issue: KeyError when accessing bundle.ads
  → RawDataBundle is @dataclass, fields are always defined
  → Check that load_data() completed successfully

Issue: Test failures with asyncio
  → Make sure pytest-asyncio is installed
  → Mark async tests with @pytest.mark.asyncio
  → Use async fixtures with @pytest.fixture


REFERENCES:
===========

- WB Seller API docs: https://openapi.wildberries.ru/
- API mapping: v5/infrastructure/config/api_mapping.py
- Tests: v5/tests/test_wb_api_loader.py
- Requirements: v5/requirements.txt
"""
