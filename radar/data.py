import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import pandas as pd
import psycopg

TABLES = {
    "vendors": ["vendor_id", "name"],
    "products": ["sku", "vendor_id", "category"],
    "order_items": ["order_item_id", "sku", "size", "delivered_at"],
    "returns": ["return_id", "order_item_id", "requested_at", "reason_code", "reason_text"],
    "reviews": ["review_id", "sku", "order_item_id", "created_at", "rating", "text"],
}


@dataclass
class Dataset:
    tables: dict[str, pd.DataFrame]

    def counts(self) -> pd.DataFrame:
        return pd.DataFrame(
            [{"table": name, "rows": len(frame)} for name, frame in self.tables.items()]
        )


def validate_tables(tables: dict[str, pd.DataFrame]) -> Dataset:
    cleaned = {}
    for name, columns in TABLES.items():
        if name not in tables:
            raise ValueError(f"Missing table: {name}.csv")
        frame = tables[name].copy().astype(object)
        frame = frame.where(frame.notna(), "").astype(str)
        missing = set(columns) - set(frame.columns)
        if missing:
            raise ValueError(f"{name}: missing columns {', '.join(sorted(missing))}.")
        frame = frame[columns].copy()
        primary_key = columns[0]
        if frame[primary_key].eq("").any() or frame[primary_key].duplicated().any():
            raise ValueError(f"{name}: IDs must be nonempty and unique.")
        if len(frame) > 100_000:
            raise ValueError(f"{name}: MVP limit is 100,000 rows per table.")
        for column in columns:
            optional = column in {"delivered_at", "reason_text"} or (
                name == "reviews" and column == "order_item_id"
            )
            if not optional and frame[column].str.strip().eq("").any():
                raise ValueError(f"{name}.{column}: empty values are not allowed.")
        for column in [value for value in columns if value.endswith("_at")]:
            original = frame[column]
            parsed = pd.to_datetime(
                original.replace("", None), utc=True, errors="coerce", format="mixed"
            )
            if (original.ne("") & parsed.isna()).any():
                raise ValueError(f"{name}.{column}: use valid ISO timestamps.")
            frame[column] = parsed
        cleaned[name] = frame

    relationships = [
        ("products", "vendor_id", "vendors", "vendor_id"),
        ("order_items", "sku", "products", "sku"),
        ("returns", "order_item_id", "order_items", "order_item_id"),
        ("reviews", "sku", "products", "sku"),
        ("reviews", "order_item_id", "order_items", "order_item_id"),
    ]
    for child, field, parent, key in relationships:
        values = cleaned[child][field]
        if (~values[values.ne("")].isin(cleaned[parent][key])).any():
            raise ValueError(f"{child}.{field}: reference to a missing {parent} row.")
    if cleaned["returns"]["order_item_id"].duplicated().any():
        raise ValueError("returns: only one return per physical order item is supported.")
    ratings = pd.to_numeric(cleaned["reviews"]["rating"], errors="coerce")
    if (ratings.isna() | ~ratings.between(1, 5) | ratings.mod(1).ne(0)).any():
        raise ValueError("reviews.rating: expected an integer from 1 to 5.")
    cleaned["reviews"]["rating"] = ratings.astype(int)

    items = cleaned["order_items"]
    returned = cleaned["returns"].merge(items, on="order_item_id", validate="one_to_one")
    if (
        returned["delivered_at"].isna() | (returned["requested_at"] < returned["delivered_at"])
    ).any():
        raise ValueError("returns: items must have been delivered before the return.")
    linked_reviews = (
        cleaned["reviews"]
        .query("order_item_id != ''")
        .merge(items, on="order_item_id", suffixes=("_review", "_item"), validate="many_to_one")
    )
    if (
        linked_reviews["sku_review"].ne(linked_reviews["sku_item"])
        | linked_reviews["delivered_at"].isna()
        | (linked_reviews["created_at"] < linked_reviews["delivered_at"])
    ).any():
        raise ValueError("reviews: linked item must match SKU and precede the review.")
    return Dataset(cleaned)


def load_csv_bundle(filename: str) -> Dataset:
    if Path(filename).stat().st_size > 25_000_000:
        raise ValueError("CSV bundle exceeds 25 MB.")
    with zipfile.ZipFile(filename) as archive:
        entries = [entry for entry in archive.infolist() if not entry.is_dir()]
        names = [entry.filename for entry in entries]
        expected = {f"{name}.csv" for name in TABLES}
        if len(names) != len(expected) or set(names) != expected:
            raise ValueError("ZIP must contain exactly the five named CSV files at its root.")
        if sum(entry.file_size for entry in entries) > 50_000_000:
            raise ValueError("Uncompressed CSV bundle exceeds 50 MB.")
        tables = {
            name: pd.read_csv(
                io.BytesIO(archive.read(f"{name}.csv")), dtype=str, keep_default_na=False
            )
            for name in TABLES
        }
    return validate_tables(tables)


def load_postgres(database_url: str) -> Dataset:
    if not database_url:
        raise ValueError("DATABASE_URL is not configured on the server.")
    tables = {}
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            connection.execute("SET LOCAL statement_timeout = '15s'")
            for name, columns in TABLES.items():
                query = psycopg.sql.SQL("SELECT {} FROM {} LIMIT 100001").format(
                    psycopg.sql.SQL(", ").join(map(psycopg.sql.Identifier, columns)),
                    psycopg.sql.Identifier(name),
                )
                cursor = connection.execute(query)
                tables[name] = pd.DataFrame(cursor.fetchall(), columns=columns)
    return validate_tables(tables)


def redact(text: str) -> str:
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email]", text)
    text = re.sub(r"(?<!\w)(?:\+\d{1,3}[ -]?)?\d[\d -]{8,}\d(?!\w)", "[phone]", text)
    return re.sub(r"(?im)^\s*(?:address|pata)\s*[:=-].*$", "[address]", text)


def prepare(dataset: Dataset, as_of: str, period_days: int, maturity_days: int) -> dict:
    cutoff = pd.to_datetime(as_of, utc=True, errors="raise").to_pydatetime()
    if period_days < 1 or maturity_days < 0:
        raise ValueError("Period must be positive and maturity cannot be negative.")
    current_end = cutoff - timedelta(days=maturity_days)
    current_start = current_end - timedelta(days=period_days)
    previous_start = current_start - timedelta(days=period_days)
    tables = dataset.tables
    items = tables["order_items"].merge(tables["products"], on="sku", validate="many_to_one")
    items = items.merge(tables["vendors"], on="vendor_id", validate="many_to_one")
    items["group_id"] = [
        json.dumps([row.vendor_id, row.category, row.size]) for row in items.itertuples()
    ]
    items = items.loc[
        items["delivered_at"].between(previous_start, current_end, inclusive="left")
    ].copy()
    items["period"] = (
        items["delivered_at"].ge(current_start).map({True: "current", False: "previous"})
    )
    records = []
    returned = (
        tables["returns"]
        .loc[tables["returns"]["requested_at"] < cutoff]
        .merge(items, on="order_item_id", validate="one_to_one")
    )
    for _, row in returned.iterrows():
        records.append(
            {
                "record_id": f"return:{row['return_id']}",
                "source_type": "return",
                "group_id": row["group_id"],
                "vendor": row["name"],
                "category": row["category"],
                "size": row["size"],
                "period": row["period"],
                "text": redact(row["reason_text"]),
                "reason_code": row["reason_code"],
            }
        )
    reviews = tables["reviews"].loc[
        tables["reviews"]["created_at"].between(previous_start, cutoff, inclusive="left")
    ]
    all_items = tables["order_items"].set_index("order_item_id")
    products = tables["products"].set_index("sku")
    vendors = tables["vendors"].set_index("vendor_id")
    for _, row in reviews.iterrows():
        product = products.loc[row["sku"]]
        size = all_items.loc[row["order_item_id"], "size"] if row["order_item_id"] else "Unknown"
        records.append(
            {
                "record_id": f"review:{row['review_id']}",
                "source_type": "review",
                "group_id": json.dumps([product["vendor_id"], product["category"], size]),
                "vendor": vendors.loc[product["vendor_id"], "name"],
                "category": product["category"],
                "size": size,
                "period": "supporting",
                "text": redact(row["text"]),
                "reason_code": "",
            }
        )
    return {
        "items": items,
        "records": records,
        "window": {
            "as_of": cutoff.isoformat(),
            "current_start": current_start.isoformat(),
            "current_end": current_end.isoformat(),
            "period_days": period_days,
            "maturity_days": maturity_days,
        },
    }
