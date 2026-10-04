CREATE TABLE IF NOT EXISTS vendors (
    vendor_id TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    sku TEXT PRIMARY KEY,
    vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
    category TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    order_item_id TEXT PRIMARY KEY,
    sku TEXT NOT NULL REFERENCES products(sku),
    size TEXT NOT NULL,
    delivered_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS returns (
    return_id TEXT PRIMARY KEY,
    order_item_id TEXT NOT NULL UNIQUE REFERENCES order_items(order_item_id),
    requested_at TIMESTAMPTZ NOT NULL,
    reason_code TEXT NOT NULL,
    reason_text TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id TEXT PRIMARY KEY,
    sku TEXT NOT NULL REFERENCES products(sku),
    order_item_id TEXT REFERENCES order_items(order_item_id),
    created_at TIMESTAMPTZ NOT NULL,
    rating SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    text TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS order_items_delivery_idx ON order_items(delivered_at);
CREATE INDEX IF NOT EXISTS returns_requested_idx ON returns(requested_at);
CREATE INDEX IF NOT EXISTS reviews_created_idx ON reviews(created_at);