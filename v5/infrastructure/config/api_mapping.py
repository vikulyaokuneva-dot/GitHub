"""
API Mapping and Documentation.

This file documents WB API endpoints and how they map to RawData contracts.
Use this as reference when debugging data loading or adding new fields.
"""

# =============================================================================
# WB API ENDPOINTS
# =============================================================================

WB_API_ENDPOINTS = {
    "adverts": {
        "url": "/api/advert/v2/adverts",
        "base_url": "https://advert-api.wildberries.ru",
        "method": "GET",
        "purpose": "Get list of all advertiser campaigns/ads",
        "response": {
            "adverts": [
                {
                    "id": 123,          # Ad ID
                    "advertId": 123,    # Same (WB uses both)
                    "name": "My Ad",
                    "status": "active",
                    "budget": 1000.50,  # Daily budget
                    "articlesWb": [     # SKU IDs linked to this ad
                        {"nmId": 123456, "id": 123456}
                    ]
                }
            ]
        },
        "maps_to": ["RawAdsData.ad_id", "RawAdsData.name", "RawAdsData.budget_daily"],
    },
    
    "ads_fullstats": {
        "url": "/adv/v3/fullstats",
        "base_url": "https://advert-api.wildberries.ru",
        "method": "GET",
        "params": {
            "ids": "123,456",  # Comma-separated ad IDs (max 50 per request)
            "beginDate": "2024-01-01",
            "endDate": "2024-01-31",
        },
        "purpose": "Get detailed statistics for specific ads",
        "response": [
            {
                "advertId": 123,
                "advertName": "My Ad",
                "status": "active",
                "budget": 1000.50,
                "statistic": [
                    {
                        "date": "2024-01-15T00:00:00",
                        "shows": 1000,          # Impressions/views
                        "clicks": 50,
                        "spend": 500.25,        # Cost
                        "conversionPercent": 5.0,
                    }
                ],
                "articlesWb": [
                    {"nmId": 123456, "id": 123456}
                ]
            }
        ],
        "maps_to": [
            "RawAdsData.views",
            "RawAdsData.clicks",
            "RawAdsData.spend",
            "RawAdsData.sku_ids",
        ],
    },
    
    "sales_funnel": {
        "url": "/api/analytics/v3/sales-funnel/products",
        "base_url": "https://seller-analytics-api.wildberries.ru",
        "method": "POST",
        "body": {
            "selectedPeriod": {"start": "2024-01-01", "end": "2024-01-31"},
            "nmIds": [],  # Empty = all products
            "limit": 1000,
            "offset": 0,
        },
        "purpose": "Get product conversion funnel (impressions → orders)",
        "response": {
            "data": {
                "products": [
                    {
                        "nmId": 123456,  # SKU ID
                        "title": "Product Name",
                        "imprCount": 5000,      # Impressions
                        "addToCartCount": 200,
                        "orderCount": 50,       # Orders
                        "revenue": 10000.00,    # orderSum
                        "commission": 1000.00,
                        "rating": 4.5,
                        "feedbackCount": 100,
                    }
                ]
            }
        },
        "maps_to": [
            "RawOrdersData.sku_id",
            "RawOrdersData.quantity",
            "RawOrdersData.revenue",
            "RawOrdersData.commission",
            "RawRatingsData.rating",
            "RawRatingsData.review_count",
        ],
    },
    
    "realization_report": {
        "url": "/api/v5/supplier/reportDetailByPeriod",
        "base_url": "https://statistics-api.wildberries.ru",
        "method": "GET",
        "params": {
            "dateFrom": "2024-01-01",
            "dateTo": "2024-01-31",
            "limit": 100000,
            "rrdid": 0,
        },
        "purpose": "Get detailed order info (most comprehensive)",
        "response": [
            {
                "rrdId": 123456789,     # Unique return/report record ID
                "supplierSkuId": "SKU123",
                "nmId": 123456,         # WB product ID
                "date": "2024-01-15",
                "quantity": 2,          # Units sold
                "saleSum": 5000.00,     # Revenue
                "commission": 500.00,
                "orderSum": 5000.00,
                "returnSum": 0.00,
                "price": 2500.00,       # Unit price
                "costPrice": 1500.00,   # Cost per unit
                "status": "продажа",    # Or "возврат" (return)
                "reasonReturn": null,   # Reason if return
            }
        ],
        "maps_to": [
            "RawOrdersData.order_id",
            "RawOrdersData.sku_id",
            "RawOrdersData.quantity",
            "RawOrdersData.revenue",
            "RawOrdersData.commission",
            "RawMarginsData.cost_price",
            "RawMarginsData.selling_price",
            "RawMarginsData.margin_percent",
            "RawReturnsData.return_id",
            "RawReturnsData.reason",
            "RawReturnsData.revenue_lost",
        ],
    },
    
    "stocks": {
        "url": "/api/v1/supplier/stocks",
        "base_url": "https://statistics-api.wildberries.ru",
        "method": "GET",
        "params": {
            "dateFrom": "2024-01-01",  # Gets stocks as of this date
        },
        "purpose": "Get current inventory levels",
        "response": [
            {
                "nmId": 123456,
                "skuID": 123456789,
                "warehouseId": 507,  # WB warehouse
                "inWareHouse": 100,  # Stock at warehouse
                "inTransit": 10,     # Stock in transit
                "price": 2500.00,
                "discount": 10,
                "supplierSku": "SKU123",
            }
        ],
        "maps_to": None,  # Not directly used in current RawData model
    },
}


# =============================================================================
# DATA MAPPING: WB API → RawData Contracts
# =============================================================================

API_TO_RAW_DATA_MAPPING = {
    "RawAdsData": {
        "ad_id": {
            "sources": [
                ("adverts", "advertId"),
                ("adverts", "id"),
                ("ads_fullstats", "advertId"),
            ]
        },
        "name": {
            "sources": [
                ("adverts", "name"),
                ("ads_fullstats", "advertName"),
            ]
        },
        "sku_ids": {
            "sources": [
                ("ads_fullstats", "articlesWb[].nmId"),
                ("ads_fullstats", "articlesWb[].id"),
            ]
        },
        "budget_daily": {
            "sources": [
                ("adverts", "budget"),
                ("ads_fullstats", "budget"),
            ]
        },
        "status": {
            "sources": [
                ("ads_fullstats", "status"),
                ("adverts", "status"),
            ],
            "default": "active"
        },
        "views": {
            "sources": [
                ("ads_fullstats", "statistic[].shows"),
                ("ads_fullstats", "statistic[].views"),
            ],
            "aggregation": "sum",  # Aggregate per-date stats
        },
        "clicks": {
            "sources": [
                ("ads_fullstats", "statistic[].clicks"),
            ],
            "aggregation": "sum",
        },
        "spend": {
            "sources": [
                ("ads_fullstats", "statistic[].spend"),
            ],
            "aggregation": "sum",
        },
    },
    
    "RawOrdersData": {
        "order_id": {
            "sources": [
                ("realization_report", "rrdId"),
                ("realization_report", "orderId"),
            ],
            "note": "WB doesn't always provide individual order IDs; may need to synthesize"
        },
        "sku_id": {
            "sources": [
                ("realization_report", "nmId"),
                ("sales_funnel", "nmId"),
            ]
        },
        "ad_id": {
            "sources": [
                ("realization_report", "campaignId"),
                ("realization_report", "advertId"),
            ],
            "optional": True
        },
        "quantity": {
            "sources": [
                ("realization_report", "quantity"),
                ("realization_report", "cnt"),
            ]
        },
        "revenue": {
            "sources": [
                ("realization_report", "saleSum"),
                ("realization_report", "orderSum"),
                ("sales_funnel", "revenue"),
            ]
        },
        "commission": {
            "sources": [
                ("realization_report", "commission"),
                ("sales_funnel", "commission"),
            ]
        },
    },
    
    "RawMarginsData": {
        "sku_id": {
            "sources": [
                ("realization_report", "nmId"),
            ]
        },
        "cost_price": {
            "sources": [
                ("realization_report", "costPrice"),
            ]
        },
        "selling_price": {
            "sources": [
                ("realization_report", "price"),
                ("realization_report", "salePrice"),
            ]
        },
        "margin_percent": {
            "sources": [],
            "calculated": "(selling_price - cost_price) / selling_price * 100"
        },
    },
    
    "RawReturnsData": {
        "return_id": {
            "sources": [
                ("realization_report", "rrdId"),
            ],
            "note": "Extract only when status='возврат'"
        },
        "order_id": {
            "sources": [
                ("realization_report", "orderId"),
            ]
        },
        "sku_id": {
            "sources": [
                ("realization_report", "nmId"),
            ]
        },
        "reason": {
            "sources": [
                ("realization_report", "reasonReturn"),
            ]
        },
        "revenue_lost": {
            "sources": [
                ("realization_report", "returnSum"),
                ("realization_report", "saleSum"),
            ]
        },
    },
    
    "RawRatingsData": {
        "sku_id": {
            "sources": [
                ("sales_funnel", "nmId"),
            ]
        },
        "rating": {
            "sources": [
                ("sales_funnel", "rating"),
            ]
        },
        "review_count": {
            "sources": [
                ("sales_funnel", "feedbackCount"),
                ("sales_funnel", "reviewCount"),
            ]
        },
        "negative_reviews": {
            "note": "Not always available in WB API responses"
        },
    },
}


# =============================================================================
# NOTES ON DATA QUALITY & QUIRKS
# =============================================================================

NOTES = """
1. AD ID MAPPING:
   - WB uses both "id" and "advertId" in different endpoints
   - Always prefer "advertId" if available
   - Some responses return nested structures; parse carefully

2. ORDERS:
   - sales-funnel endpoint provides aggregate order counts, not individual orders
   - realization-report provides detailed per-order info
   - Always prefer realization-report when available
   - Some orders may not be attributed to ads (ad_id may be null)

3. MARGINS:
   - Cost price comes from realization-report
   - Check that cost_price > 0 and selling_price > 0
   - If cost_price is missing, margin cannot be calculated

4. RETURNS:
   - WB marks returns with status field (look for "возврат")
   - Not all records in realization are returns
   - Return reason field may be Russian text; normalize if needed

5. RATINGS:
   - Only available from sales-funnel endpoint
   - Ratings are per-SKU aggregate, not per-ad
   - Review count may lag behind actual reviews on WB site

6. DATE FILTERING:
   - WB API typically returns data for requested period
   - Some endpoints (stocks) return current snapshot, not historical
   - Always filter by date when parsing responses

7. RATE LIMITING:
   - WB API has rate limits (typically 100-1000 requests/minute)
   - AsyncWBClient implements exponential backoff
   - Batch ad ID requests in chunks of 50

8. ERROR HANDLING:
   - 403 Forbidden: Access restricted (e.g., ads disabled on account)
   - 204 No Content: No data for period (not an error)
   - 429 Too Many Requests: Rate limit exceeded (retry with backoff)
   - Always handle these gracefully
"""
