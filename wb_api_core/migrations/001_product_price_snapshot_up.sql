CREATE TABLE IF NOT EXISTS product_price_snapshot (
    seller_id TEXT NOT NULL,
    nm_id TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    seller_base_price NUMERIC(18, 2),
    seller_discount_percent NUMERIC(7, 2),
    seller_discounted_price NUMERIC(18, 2),
    club_discounted_price NUMERIC(18, 2),
    buyer_price_before_wallet NUMERIC(18, 2),
    buyer_final_price NUMERIC(18, 2),
    platform_discount_percent NUMERIC(7, 2),
    wallet_discount_percent NUMERIC(7, 2),
    source TEXT NOT NULL,
    data_quality_status TEXT NOT NULL,
    order_id TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (seller_id, nm_id, captured_at, source, order_id)
);

CREATE INDEX IF NOT EXISTS idx_product_price_snapshot_temporal
    ON product_price_snapshot (seller_id, nm_id, captured_at);
