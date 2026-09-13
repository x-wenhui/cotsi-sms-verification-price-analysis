"""Prepare and validate the Facebook vendor-day analytical dataset.

Input
-----
The unchanged COTSI replication archive placed at data/raw/verifications data_final.zip.

Outputs
-------
1. data/processed/facebook_vendor_day_analytical.csv
2. output/tables/data_preparation_audit.csv

The script stops with a clear error if a required validation check fails.
The descriptive decomposition is performed separately in R.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd


# -----------------------------------------------------------------------------
# 1. Fixed research scope and repository paths
# -----------------------------------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parents[1]

ARCHIVE_PATH = (
    PROJECT_DIR
    / "data"
    / "raw"
    / "verifications data_final.zip"
)

PROCESSED_DIR = PROJECT_DIR / "data" / "processed"
AUDIT_DIR = PROJECT_DIR / "output" / "tables"
OUTPUT_CSV = PROCESSED_DIR / "facebook_vendor_day_analytical.csv"
AUDIT_CSV = AUDIT_DIR / "data_preparation_audit.csv"

START_DATE = pd.Timestamp("2024-08-01")
END_DATE = pd.Timestamp("2025-07-27")
COUNTRY_ORDER = ["GB", "US", "ID"]
COUNTRY_NAMES = {
    "GB": "United Kingdom",
    "US": "United States",
    "ID": "Indonesia",
}

SERVICE_ID = "fb"
SERVICE_NAME = "Facebook"
CHUNK_SIZE = 250_000

# Fixed reconstruction tolerance:
# absolute difference <= 1e-10 + 1e-8 * abs(source price)
PRICE_ABSOLUTE_TOLERANCE = 1e-10
PRICE_RELATIVE_TOLERANCE = 1e-8
SHARE_SUM_TOLERANCE = 1e-12

MONTHLY_MEMBERS = [
    "verifications_2024-08.csv",
    "verifications_2024-09.csv",
    "verifications_2024-10.csv",
    "verifications_2024-11.csv",
    "verifications_2024-12.csv",
    "verifications_2025-01.csv",
    "verifications_2025-02.csv",
    "verifications_2025-03.csv",
    "verifications_2025-04.csv",
    "verifications_2025-05.csv",
    "verifications_2025-06.csv",
    "verifications_2025-07.csv",
]

REQUIRED_COLUMNS = [
    "date",
    "serviceID",
    "serviceName",
    "countryID",
    "exchangeRate",
    "count",
    "priceUSD",
    "smspva_count",
    "smspva_priceUSD",
    "smshub_count",
    "smshub_priceUSD",
    "sms_activate_count",
    "sms_activate_priceRUB",
    "5sim_count",
    "5sim_priceRUB",
]

NUMERIC_COLUMNS = [
    "exchangeRate",
    "count",
    "priceUSD",
    "smspva_count",
    "smspva_priceUSD",
    "smshub_count",
    "smshub_priceUSD",
    "sms_activate_count",
    "sms_activate_priceRUB",
    "5sim_count",
    "5sim_priceRUB",
]

VENDORS = [
    {
        "vendor": "SMSPVA",
        "stock_column": "smspva_count",
        "price_column": "smspva_priceUSD",
        "currency": "USD",
    },
    {
        "vendor": "SMSHub",
        "stock_column": "smshub_count",
        "price_column": "smshub_priceUSD",
        "currency": "USD",
    },
    {
        "vendor": "SMS-Activate",
        "stock_column": "sms_activate_count",
        "price_column": "sms_activate_priceRUB",
        "currency": "RUB",
    },
    {
        "vendor": "5SIM",
        "stock_column": "5sim_count",
        "price_column": "5sim_priceRUB",
        "currency": "RUB",
    },
]
VENDOR_ORDER = [vendor["vendor"] for vendor in VENDORS]

EXPECTED_SOURCE_ROWS = {"GB": 360, "US": 360, "ID": 360}
EXPECTED_VALID_ADJACENT_PAIRS = {"GB": 358, "US": 358, "ID": 358}
EXPECTED_PRIMARY_PAIRS = {"GB": 325, "US": 326, "ID": 350}
EXPECTED_VENDOR_SET_CHANGE_PAIRS = {"GB": 33, "US": 32, "ID": 8}
EXPECTED_MISSING_DATES = {country: ["2024-12-30"] for country in COUNTRY_ORDER}


# -----------------------------------------------------------------------------
# 2. Provenance and audit helpers
# -----------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    """Return a SHA-256 file hash without loading the whole file into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def add_audit(
    audit_rows: list[dict[str, object]],
    section: str,
    check: str,
    expected: object,
    actual: object,
    passed: bool | None,
    note: str,
) -> None:
    """Append one readable audit result."""

    if passed is None:
        status = "INFO"
    else:
        status = "PASS" if passed else "FAIL"

    audit_rows.append(
        {
            "section": section,
            "check": check,
            "expected": expected,
            "actual": actual,
            "status": status,
            "note": note,
        }
    )


def audit_frame(audit_rows: list[dict[str, object]]) -> pd.DataFrame:
    """Create the audit table in a consistent column order."""

    return pd.DataFrame(
        audit_rows,
        columns=["section", "check", "expected", "actual", "status", "note"],
    )


def save_audit(audit_rows: list[dict[str, object]]) -> pd.DataFrame:
    """Save and return the current audit table."""

    audit = audit_frame(audit_rows)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    audit.to_csv(AUDIT_CSV, index=False)
    return audit


def stop_if_failed(audit_rows: list[dict[str, object]], phase: str) -> None:
    """Save the audit and stop before invalid data move farther downstream."""

    audit = save_audit(audit_rows)
    failures = audit.loc[audit["status"].eq("FAIL"), "check"].tolist()
    if failures:
        print("\nDATA PREPARATION VALIDATION FAILED")
        print(audit.to_string(index=False))
        raise RuntimeError(
            f"{phase} failed {len(failures)} validation check(s): "
            + ", ".join(failures)
        )


def finite(series: pd.Series) -> pd.Series:
    """Return True only for non-missing finite numeric values."""

    return series.notna() & np.isfinite(series)


def price_tolerance(source_price: pd.Series) -> pd.Series:
    """Apply the fixed absolute-plus-relative price tolerance."""

    return PRICE_ABSOLUTE_TOLERANCE + (
        PRICE_RELATIVE_TOLERANCE * source_price.abs()
    )


# -----------------------------------------------------------------------------
# 3. Chunked ingestion and fixed-scope filtering
# -----------------------------------------------------------------------------

def read_scoped_archive(
    audit_rows: list[dict[str, object]],
) -> pd.DataFrame:
    """Read every intended archive member in chunks and retain the fixed scope."""

    if not ARCHIVE_PATH.exists():
        raise FileNotFoundError(f"Archive not found: {ARCHIVE_PATH}")

    archive_relative = ARCHIVE_PATH.relative_to(PROJECT_DIR).as_posix()
    add_audit(
        audit_rows,
        "provenance",
        "source_archive",
        "specified local archive",
        archive_relative,
        True,
        "The raw archive is read only and is never overwritten.",
    )
    add_audit(
        audit_rows,
        "provenance",
        "source_archive_sha256",
        "recorded for reproducibility",
        sha256_file(ARCHIVE_PATH),
        None,
        "Hash identifies the exact local archive used for this run.",
    )

    retained_chunks: list[pd.DataFrame] = []
    raw_rows_by_member: dict[str, int] = {}
    retained_rows_by_member: dict[str, int] = {}
    invalid_target_dates = 0
    target_rows_outside_date_scope = 0
    literal_na_country_rows = 0

    with ZipFile(ARCHIVE_PATH) as archive:
        archive_members = set(archive.namelist())
        missing_members = [
            member for member in MONTHLY_MEMBERS if member not in archive_members
        ]
        add_audit(
            audit_rows,
            "provenance",
            "intended_archive_members_present",
            len(MONTHLY_MEMBERS),
            len(MONTHLY_MEMBERS) - len(missing_members),
            len(missing_members) == 0,
            "Missing members: " + (", ".join(missing_members) or "none"),
        )
        stop_if_failed(audit_rows, "Archive member check")

        schema_problems: list[str] = []
        for member in MONTHLY_MEMBERS:
            with archive.open(member) as member_file:
                header = pd.read_csv(
                    member_file,
                    nrows=0,
                    keep_default_na=False,
                ).columns.tolist()
            missing_fields = [field for field in REQUIRED_COLUMNS if field not in header]
            if missing_fields:
                schema_problems.append(f"{member}: {missing_fields}")

        add_audit(
            audit_rows,
            "schema_keys",
            "required_fields_in_every_member",
            0,
            len(schema_problems),
            len(schema_problems) == 0,
            "Schema problems: " + ("; ".join(schema_problems) or "none"),
        )
        stop_if_failed(audit_rows, "Schema check")

        for member in MONTHLY_MEMBERS:
            member_raw_rows = 0
            member_retained_rows = 0

            with archive.open(member) as member_file:
                chunks = pd.read_csv(
                    member_file,
                    usecols=REQUIRED_COLUMNS,
                    chunksize=CHUNK_SIZE,
                    dtype={
                        "countryID": "string",
                        "serviceID": "string",
                        "serviceName": "string",
                    },
                    keep_default_na=False,
                )

                for chunk in chunks:
                    member_raw_rows += len(chunk)
                    literal_na_country_rows += int(chunk["countryID"].eq("NA").sum())

                    identifier_scope = (
                        chunk["serviceID"].eq(SERVICE_ID)
                        & chunk["countryID"].isin(COUNTRY_ORDER)
                    )
                    scoped = chunk.loc[identifier_scope].copy()

                    # Parse dates explicitly only after the cheap identifier filter.
                    scoped["date"] = pd.to_datetime(
                        scoped["date"],
                        format="%Y-%m-%d",
                        errors="coerce",
                    )
                    invalid_target_dates += int(scoped["date"].isna().sum())

                    date_scope = scoped["date"].between(
                        START_DATE,
                        END_DATE,
                        inclusive="both",
                    )
                    target_rows_outside_date_scope += int((~date_scope).sum())
                    scoped = scoped.loc[date_scope].copy()
                    scoped["source_member"] = member

                    member_retained_rows += len(scoped)
                    retained_chunks.append(scoped)

            raw_rows_by_member[member] = member_raw_rows
            retained_rows_by_member[member] = member_retained_rows

    raw_rows_read = sum(raw_rows_by_member.values())
    retained = pd.concat(retained_chunks, ignore_index=True)

    add_audit(
        audit_rows,
        "provenance",
        "intended_members_read",
        len(MONTHLY_MEMBERS),
        len(raw_rows_by_member),
        list(raw_rows_by_member) == MONTHLY_MEMBERS,
        "Every intended member was read completely in chunks.",
    )
    add_audit(
        audit_rows,
        "provenance",
        "raw_rows_read",
        "all rows in 12 intended members",
        raw_rows_read,
        None,
        "; ".join(
            f"{member}={count}" for member, count in raw_rows_by_member.items()
        ),
    )
    add_audit(
        audit_rows,
        "provenance",
        "retained_rows_by_member",
        "fixed identifier and date scope",
        len(retained),
        None,
        "; ".join(
            f"{member}={count}" for member, count in retained_rows_by_member.items()
        ),
    )
    add_audit(
        audit_rows,
        "provenance",
        "scope_excluded_rows",
        "reported, not silently discarded",
        raw_rows_read - len(retained),
        None,
        "Rows outside the fixed service, country or date scope.",
    )
    add_audit(
        audit_rows,
        "schema_keys",
        "invalid_dates_in_target_identifier_scope",
        0,
        invalid_target_dates,
        invalid_target_dates == 0,
        "Dates are parsed with the exact YYYY-MM-DD format.",
    )
    add_audit(
        audit_rows,
        "schema_keys",
        "target_rows_outside_fixed_dates",
        0,
        target_rows_outside_date_scope,
        target_rows_outside_date_scope == 0,
        "The intended monthly files contain no target rows outside the fixed dates.",
    )
    add_audit(
        audit_rows,
        "schema_keys",
        "literal_NA_country_code_preserved",
        "read as text, not missing",
        literal_na_country_rows,
        None,
        "keep_default_na=False preserves the literal country code NA during import.",
    )

    numeric_parse_failures: dict[str, int] = {}
    for column in NUMERIC_COLUMNS:
        original = retained[column].astype("string")
        nonblank = original.str.strip().ne("")
        converted = pd.to_numeric(retained[column], errors="coerce")
        numeric_parse_failures[column] = int((nonblank & converted.isna()).sum())
        retained[column] = converted

    total_numeric_parse_failures = sum(numeric_parse_failures.values())
    add_audit(
        audit_rows,
        "schema_keys",
        "numeric_parse_failures",
        0,
        total_numeric_parse_failures,
        total_numeric_parse_failures == 0,
        "; ".join(
            f"{column}={count}"
            for column, count in numeric_parse_failures.items()
            if count > 0
        )
        or "No nonblank numeric value failed parsing.",
    )

    expected_total_source_rows = sum(EXPECTED_SOURCE_ROWS.values())
    add_audit(
        audit_rows,
        "sample_accounting",
        "retained_source_rows",
        expected_total_source_rows,
        len(retained),
        len(retained) == expected_total_source_rows,
        "Expected country-platform-date rows before reshaping.",
    )

    duplicate_source_keys = int(
        retained.duplicated(["countryID", "serviceID", "date"]).sum()
    )
    add_audit(
        audit_rows,
        "schema_keys",
        "duplicate_country_platform_date_keys",
        0,
        duplicate_source_keys,
        duplicate_source_keys == 0,
        "The source-row key must be unique before reshaping.",
    )

    facebook_mappings = (
        retained[["serviceID", "serviceName"]]
        .drop_duplicates()
        .sort_values(["serviceID", "serviceName"])
    )
    mapping_records = facebook_mappings.to_dict("records")
    mapping_ok = mapping_records == [
        {"serviceID": SERVICE_ID, "serviceName": SERVICE_NAME}
    ]
    add_audit(
        audit_rows,
        "schema_keys",
        "facebook_identifier_name_mapping",
        "fb=Facebook",
        mapping_records,
        mapping_ok,
        "The service ID and name must map consistently.",
    )

    member_month = retained["source_member"].str.extract(
        r"verifications_(\d{4}-\d{2})\.csv",
        expand=False,
    )
    date_month = retained["date"].dt.strftime("%Y-%m")
    member_date_mismatches = int(member_month.ne(date_month).sum())
    add_audit(
        audit_rows,
        "temporal",
        "date_matches_source_member_month",
        0,
        member_date_mismatches,
        member_date_mismatches == 0,
        "Guards against a date being stored in the wrong monthly member.",
    )

    for country in COUNTRY_ORDER:
        country_rows = int(retained["countryID"].eq(country).sum())
        add_audit(
            audit_rows,
            "sample_accounting",
            f"source_rows_{country}",
            EXPECTED_SOURCE_ROWS[country],
            country_rows,
            country_rows == EXPECTED_SOURCE_ROWS[country],
            COUNTRY_NAMES[country],
        )

    stop_if_failed(audit_rows, "Ingestion and source-key checks")
    return retained


# -----------------------------------------------------------------------------
# 4. Reshape four vendor columns, convert currencies and validate each day
# -----------------------------------------------------------------------------

def prepare_vendor_days(
    source: pd.DataFrame,
    audit_rows: list[dict[str, object]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create the calendar-complete vendor-day table and day-level checks."""

    expected_pre_calendar_vendor_rows = len(source) * len(VENDORS)
    add_audit(
        audit_rows,
        "sample_accounting",
        "vendor_rows_before_calendar_completion",
        4_320,
        expected_pre_calendar_vendor_rows,
        expected_pre_calendar_vendor_rows == 4_320,
        "Each of 1,080 source rows contains four vendor records.",
    )

    source = source.rename(
        columns={
            "countryID": "country_id",
            "serviceID": "service_id",
            "serviceName": "service_name",
            "exchangeRate": "exchange_rate_rub_per_usd",
            "count": "source_combined_stock",
            "priceUSD": "source_combined_price_usd",
        }
    )

    full_dates = pd.date_range(START_DATE, END_DATE, freq="D")
    calendar = pd.MultiIndex.from_product(
        [COUNTRY_ORDER, full_dates],
        names=["country_id", "date"],
    ).to_frame(index=False)

    calendar_days = calendar.merge(
        source,
        on=["country_id", "date"],
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    calendar_days["row_observed"] = calendar_days["_merge"].eq("both")
    calendar_days = calendar_days.drop(columns="_merge")
    calendar_days["country_name"] = calendar_days["country_id"].map(COUNTRY_NAMES)
    calendar_days["service_id"] = calendar_days["service_id"].fillna(SERVICE_ID)
    calendar_days["service_name"] = calendar_days["service_name"].fillna(
        SERVICE_NAME
    )

    for country in COUNTRY_ORDER:
        missing_dates = (
            calendar_days.loc[
                calendar_days["country_id"].eq(country)
                & ~calendar_days["row_observed"],
                "date",
            ]
            .dt.strftime("%Y-%m-%d")
            .tolist()
        )
        add_audit(
            audit_rows,
            "temporal",
            f"missing_calendar_dates_{country}",
            EXPECTED_MISSING_DATES[country],
            missing_dates,
            missing_dates == EXPECTED_MISSING_DATES[country],
            "Missing dates remain explicit calendar rows.",
        )

    long_parts: list[pd.DataFrame] = []
    common_columns = [
        "date",
        "country_id",
        "country_name",
        "service_id",
        "service_name",
        "source_member",
        "row_observed",
        "exchange_rate_rub_per_usd",
        "source_combined_stock",
        "source_combined_price_usd",
    ]

    for vendor_definition in VENDORS:
        vendor = calendar_days[common_columns].copy()
        vendor["vendor"] = vendor_definition["vendor"]
        vendor["stock_count"] = calendar_days[vendor_definition["stock_column"]]
        vendor["price_original"] = calendar_days[
            vendor_definition["price_column"]
        ]
        vendor["price_currency"] = vendor_definition["currency"]

        if vendor_definition["currency"] == "USD":
            vendor["price_usd"] = vendor["price_original"]
        else:
            # The archive records RUB per USD, so RUB quotes are divided by the
            # recorded exchange rate. No external exchange-rate data are used.
            valid_denominator = (
                finite(vendor["exchange_rate_rub_per_usd"])
                & vendor["exchange_rate_rub_per_usd"].gt(0)
            )
            vendor["price_usd"] = np.where(
                valid_denominator,
                vendor["price_original"]
                / vendor["exchange_rate_rub_per_usd"],
                np.nan,
            )

        long_parts.append(vendor)

    vendor_days = pd.concat(long_parts, ignore_index=True)
    vendor_rank = {vendor: position for position, vendor in enumerate(VENDOR_ORDER)}
    country_rank = {
        country: position for position, country in enumerate(COUNTRY_ORDER)
    }
    vendor_days["_vendor_rank"] = vendor_days["vendor"].map(vendor_rank)
    vendor_days["_country_rank"] = vendor_days["country_id"].map(country_rank)
    vendor_days = vendor_days.sort_values(
        ["_country_rank", "date", "_vendor_rank"]
    ).reset_index(drop=True)

    expected_calendar_vendor_rows = len(COUNTRY_ORDER) * len(full_dates) * len(VENDORS)
    add_audit(
        audit_rows,
        "sample_accounting",
        "calendar_complete_vendor_rows",
        expected_calendar_vendor_rows,
        len(vendor_days),
        len(vendor_days) == expected_calendar_vendor_rows,
        "Includes four explicit missing-date vendor rows per country.",
    )

    vendor_days["stock_valid"] = (
        finite(vendor_days["stock_count"])
        & vendor_days["stock_count"].ge(0)
    )
    vendor_days["positive_stock"] = (
        vendor_days["stock_valid"] & vendor_days["stock_count"].gt(0)
    )
    vendor_days["active_price_valid"] = (
        ~vendor_days["positive_stock"]
        | (
            finite(vendor_days["price_usd"])
            & vendor_days["price_usd"].gt(0)
        )
    )
    vendor_days["vendor_measurement_valid"] = (
        vendor_days["row_observed"]
        & vendor_days["stock_valid"]
        & vendor_days["active_price_valid"]
    )

    vendor_days["exchange_rate_valid"] = (
        finite(vendor_days["exchange_rate_rub_per_usd"])
        & vendor_days["exchange_rate_rub_per_usd"].gt(0)
    )
    vendor_days["source_stock_valid"] = (
        finite(vendor_days["source_combined_stock"])
        & vendor_days["source_combined_stock"].ge(0)
    )
    vendor_days["source_price_valid"] = (
        finite(vendor_days["source_combined_price_usd"])
        & vendor_days["source_combined_price_usd"].gt(0)
    )

    vendor_days["weighted_value_usd"] = np.where(
        vendor_days["stock_valid"] & vendor_days["stock_count"].eq(0),
        0.0,
        np.where(
            vendor_days["positive_stock"]
            & vendor_days["active_price_valid"],
            vendor_days["stock_count"] * vendor_days["price_usd"],
            np.nan,
        ),
    )

    day_keys = ["country_id", "date"]
    day_metrics = (
        vendor_days.groupby(day_keys, as_index=False, sort=False)
        .agg(
            row_observed=("row_observed", "first"),
            source_member=("source_member", "first"),
            exchange_rate_rub_per_usd=(
                "exchange_rate_rub_per_usd",
                "first",
            ),
            source_combined_stock=("source_combined_stock", "first"),
            source_combined_price_usd=("source_combined_price_usd", "first"),
            exchange_rate_valid=("exchange_rate_valid", "first"),
            source_stock_valid=("source_stock_valid", "first"),
            source_price_valid=("source_price_valid", "first"),
            all_vendor_stocks_valid=("stock_valid", "all"),
            all_active_prices_valid=("active_price_valid", "all"),
            total_vendor_stock=("stock_count", lambda values: values.sum(min_count=4)),
            positive_vendor_count=("positive_stock", "sum"),
            weighted_value_total_usd=(
                "weighted_value_usd",
                lambda values: values.sum(min_count=4),
            ),
        )
    )

    positive_sets = (
        vendor_days.loc[vendor_days["positive_stock"]]
        .sort_values(["_country_rank", "date", "_vendor_rank"])
        .groupby(day_keys, as_index=False, sort=False)["vendor"]
        .agg(lambda values: "|".join(values))
        .rename(columns={"vendor": "positive_vendor_set"})
    )
    day_metrics = day_metrics.merge(
        positive_sets,
        on=day_keys,
        how="left",
        validate="one_to_one",
    )
    day_metrics["positive_vendor_set"] = day_metrics[
        "positive_vendor_set"
    ].fillna("")

    day_metrics["pre_reconstruction_valid"] = (
        day_metrics["row_observed"]
        & day_metrics["exchange_rate_valid"]
        & day_metrics["source_stock_valid"]
        & day_metrics["source_price_valid"]
        & day_metrics["all_vendor_stocks_valid"]
        & day_metrics["all_active_prices_valid"]
        & day_metrics["total_vendor_stock"].gt(0)
    )
    day_metrics["reconstructed_price_usd"] = (
        day_metrics["weighted_value_total_usd"]
        / day_metrics["total_vendor_stock"]
    ).where(day_metrics["pre_reconstruction_valid"])

    day_metrics["count_reconstruction_ok"] = (
        day_metrics["pre_reconstruction_valid"]
        & day_metrics["total_vendor_stock"].eq(
            day_metrics["source_combined_stock"]
        )
    )
    reconstruction_difference = (
        day_metrics["reconstructed_price_usd"]
        - day_metrics["source_combined_price_usd"]
    ).abs()
    day_metrics["price_reconstruction_ok"] = (
        day_metrics["pre_reconstruction_valid"]
        & reconstruction_difference.le(
            price_tolerance(day_metrics["source_combined_price_usd"])
        )
    )

    vendor_days = vendor_days.merge(
        day_metrics[
            day_keys
            + [
                "total_vendor_stock",
                "positive_vendor_count",
                "positive_vendor_set",
                "pre_reconstruction_valid",
                "reconstructed_price_usd",
                "count_reconstruction_ok",
                "price_reconstruction_ok",
            ]
        ],
        on=day_keys,
        how="left",
        validate="many_to_one",
    )
    vendor_days["stock_share"] = np.where(
        vendor_days["pre_reconstruction_valid"],
        vendor_days["stock_count"] / vendor_days["total_vendor_stock"],
        np.nan,
    )

    share_sums = (
        vendor_days.groupby(day_keys, as_index=False, sort=False)["stock_share"]
        .agg(lambda values: values.sum(min_count=4))
        .rename(columns={"stock_share": "stock_share_sum"})
    )
    day_metrics = day_metrics.merge(
        share_sums,
        on=day_keys,
        how="left",
        validate="one_to_one",
    )
    day_metrics["share_sum_ok"] = (
        day_metrics["pre_reconstruction_valid"]
        & day_metrics["stock_share_sum"].sub(1.0).abs().le(SHARE_SUM_TOLERANCE)
    )
    day_metrics["country_day_valid"] = (
        day_metrics["pre_reconstruction_valid"]
        & day_metrics["count_reconstruction_ok"]
        & day_metrics["price_reconstruction_ok"]
        & day_metrics["share_sum_ok"]
    )

    vendor_days = vendor_days.merge(
        day_metrics[day_keys + ["stock_share_sum", "share_sum_ok", "country_day_valid"]],
        on=day_keys,
        how="left",
        validate="many_to_one",
    )

    observed_vendor_rows = vendor_days["row_observed"]
    observed_days = day_metrics["row_observed"]
    add_audit(
        audit_rows,
        "validity",
        "invalid_or_unknown_vendor_stocks",
        0,
        int((observed_vendor_rows & ~vendor_days["stock_valid"]).sum()),
        int((observed_vendor_rows & ~vendor_days["stock_valid"]).sum()) == 0,
        "Stock must be known, finite and nonnegative.",
    )
    add_audit(
        audit_rows,
        "validity",
        "invalid_positive_stock_vendor_prices",
        0,
        int(
            (
                observed_vendor_rows
                & vendor_days["positive_stock"]
                & ~vendor_days["active_price_valid"]
            ).sum()
        ),
        int(
            (
                observed_vendor_rows
                & vendor_days["positive_stock"]
                & ~vendor_days["active_price_valid"]
            ).sum()
        )
        == 0,
        "An active vendor must have a positive finite USD price.",
    )
    add_audit(
        audit_rows,
        "validity",
        "invalid_exchange_rate_days",
        0,
        int((observed_days & ~day_metrics["exchange_rate_valid"]).sum()),
        int((observed_days & ~day_metrics["exchange_rate_valid"]).sum()) == 0,
        "The recorded RUB-per-USD factor must be positive and finite.",
    )
    add_audit(
        audit_rows,
        "validity",
        "invalid_source_combined_measurements",
        0,
        int(
            (
                observed_days
                & ~(
                    day_metrics["source_stock_valid"]
                    & day_metrics["source_price_valid"]
                )
            ).sum()
        ),
        int(
            (
                observed_days
                & ~(
                    day_metrics["source_stock_valid"]
                    & day_metrics["source_price_valid"]
                )
            ).sum()
        )
        == 0,
        "Source combined stock and price must also be valid.",
    )
    add_audit(
        audit_rows,
        "reconstruction",
        "combined_stock_reconstruction_failures",
        0,
        int(
            (
                day_metrics["pre_reconstruction_valid"]
                & ~day_metrics["count_reconstruction_ok"]
            ).sum()
        ),
        int(
            (
                day_metrics["pre_reconstruction_valid"]
                & ~day_metrics["count_reconstruction_ok"]
            ).sum()
        )
        == 0,
        "Four vendor stocks must sum exactly to source count.",
    )
    add_audit(
        audit_rows,
        "reconstruction",
        "combined_price_reconstruction_failures",
        0,
        int(
            (
                day_metrics["pre_reconstruction_valid"]
                & ~day_metrics["price_reconstruction_ok"]
            ).sum()
        ),
        int(
            (
                day_metrics["pre_reconstruction_valid"]
                & ~day_metrics["price_reconstruction_ok"]
            ).sum()
        )
        == 0,
        "Uses 1e-10 + 1e-8 * abs(source price).",
    )
    add_audit(
        audit_rows,
        "reconstruction",
        "stock_share_sum_failures",
        0,
        int(
            (
                day_metrics["pre_reconstruction_valid"]
                & ~day_metrics["share_sum_ok"]
            ).sum()
        ),
        int(
            (
                day_metrics["pre_reconstruction_valid"]
                & ~day_metrics["share_sum_ok"]
            ).sum()
        )
        == 0,
        f"Valid-day shares must sum to one within {SHARE_SUM_TOLERANCE:g}.",
    )
    add_audit(
        audit_rows,
        "validity",
        "invalid_observed_country_days",
        0,
        int((observed_days & ~day_metrics["country_day_valid"]).sum()),
        int((observed_days & ~day_metrics["country_day_valid"]).sum()) == 0,
        "Invalid observed days remain explicit and cannot enter a pair.",
    )

    for country in COUNTRY_ORDER:
        exchange_rate_100_days = int(
            (
                day_metrics["country_id"].eq(country)
                & day_metrics["row_observed"]
                & day_metrics["exchange_rate_rub_per_usd"].eq(100)
            ).sum()
        )
        add_audit(
            audit_rows,
            "currency",
            f"exchange_rate_equals_100_days_{country}",
            175,
            exchange_rate_100_days,
            exchange_rate_100_days == 175,
            "Archive rate is used as recorded; RUB price / exchangeRate = USD price.",
        )

    stop_if_failed(audit_rows, "Reshaping, validity and reconstruction checks")
    return vendor_days, day_metrics


# -----------------------------------------------------------------------------
# 5. Calendar-day lags and vendor-set eligibility
# -----------------------------------------------------------------------------

def add_temporal_eligibility(
    vendor_days: pd.DataFrame,
    day_metrics: pd.DataFrame,
    audit_rows: list[dict[str, object]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Add checked previous-day values and fixed pair classifications."""

    country_rank = {
        country: position for position, country in enumerate(COUNTRY_ORDER)
    }
    day_metrics["_country_rank"] = day_metrics["country_id"].map(country_rank)
    day_metrics = day_metrics.sort_values(["_country_rank", "date"]).reset_index(
        drop=True
    )

    by_country = day_metrics.groupby("country_id", sort=False)
    day_metrics["previous_date"] = by_country["date"].shift(1)
    day_metrics["previous_row_observed"] = (
        by_country["row_observed"].shift(1).fillna(False).astype(bool)
    )
    day_metrics["previous_country_day_valid"] = (
        by_country["country_day_valid"].shift(1).fillna(False).astype(bool)
    )
    day_metrics["previous_positive_vendor_count"] = by_country[
        "positive_vendor_count"
    ].shift(1)
    day_metrics["previous_positive_vendor_set"] = by_country[
        "positive_vendor_set"
    ].shift(1)
    day_metrics["previous_source_combined_price_usd"] = by_country[
        "source_combined_price_usd"
    ].shift(1)

    day_metrics["calendar_day_difference"] = (
        day_metrics["date"] - day_metrics["previous_date"]
    ).dt.days
    day_metrics["one_calendar_day_after_previous_row"] = day_metrics[
        "calendar_day_difference"
    ].eq(1)
    day_metrics["valid_adjacent_pair"] = (
        day_metrics["country_day_valid"]
        & day_metrics["previous_country_day_valid"]
        & day_metrics["one_calendar_day_after_previous_row"]
    )
    day_metrics["vendor_set_unchanged"] = (
        day_metrics["valid_adjacent_pair"]
        & day_metrics["positive_vendor_set"].eq(
            day_metrics["previous_positive_vendor_set"]
        )
    )
    day_metrics["primary_pair_eligible"] = (
        day_metrics["vendor_set_unchanged"]
        & day_metrics["positive_vendor_count"].ge(2)
        & day_metrics["previous_positive_vendor_count"].ge(2)
    )
    day_metrics["vendor_set_change_pair"] = (
        day_metrics["valid_adjacent_pair"]
        & ~day_metrics["vendor_set_unchanged"]
    )
    day_metrics["net_combined_price_change_usd"] = (
        day_metrics["source_combined_price_usd"]
        - day_metrics["previous_source_combined_price_usd"]
    ).where(day_metrics["valid_adjacent_pair"])

    no_previous = day_metrics["previous_date"].isna()
    current_missing = ~day_metrics["row_observed"]
    current_invalid = day_metrics["row_observed"] & ~day_metrics["country_day_valid"]
    previous_missing = ~day_metrics["previous_row_observed"]
    previous_invalid = (
        day_metrics["previous_row_observed"]
        & ~day_metrics["previous_country_day_valid"]
    )
    stable_too_small = (
        day_metrics["valid_adjacent_pair"]
        & day_metrics["vendor_set_unchanged"]
        & ~day_metrics["primary_pair_eligible"]
    )

    day_metrics["pair_status"] = np.select(
        [
            no_previous,
            current_missing,
            current_invalid,
            previous_missing,
            previous_invalid,
            day_metrics["primary_pair_eligible"],
            day_metrics["vendor_set_change_pair"],
            stable_too_small,
        ],
        [
            "no_previous_calendar_day",
            "current_day_missing",
            "current_day_invalid",
            "previous_day_missing",
            "previous_day_invalid",
            "eligible_stable_vendor_set",
            "vendor_set_changed",
            "stable_set_fewer_than_two_vendors",
        ],
        default="unclassified",
    )

    nonfirst_day_steps = day_metrics["previous_date"].notna()
    calendar_step_failures = int(
        (
            nonfirst_day_steps
            & ~day_metrics["one_calendar_day_after_previous_row"]
        ).sum()
    )
    add_audit(
        audit_rows,
        "temporal",
        "calendar_lag_step_failures",
        0,
        calendar_step_failures,
        calendar_step_failures == 0,
        "Lags are created after calendar completion and sorting within country.",
    )

    unclassified_valid_pairs = int(
        (
            day_metrics["valid_adjacent_pair"]
            & ~day_metrics["primary_pair_eligible"]
            & ~day_metrics["vendor_set_change_pair"]
        ).sum()
    )
    add_audit(
        audit_rows,
        "sample_accounting",
        "valid_adjacent_pairs_outside_two_classification_groups",
        0,
        unclassified_valid_pairs,
        unclassified_valid_pairs == 0,
        "Checks for a stable set with fewer than two positive-stock vendors.",
    )

    for country in COUNTRY_ORDER:
        country_days = day_metrics["country_id"].eq(country)
        valid_pairs = int(
            (country_days & day_metrics["valid_adjacent_pair"]).sum()
        )
        primary_pairs = int(
            (country_days & day_metrics["primary_pair_eligible"]).sum()
        )
        change_pairs = int(
            (country_days & day_metrics["vendor_set_change_pair"]).sum()
        )

        add_audit(
            audit_rows,
            "sample_accounting",
            f"valid_adjacent_pairs_{country}",
            EXPECTED_VALID_ADJACENT_PAIRS[country],
            valid_pairs,
            valid_pairs == EXPECTED_VALID_ADJACENT_PAIRS[country],
            COUNTRY_NAMES[country],
        )
        add_audit(
            audit_rows,
            "sample_accounting",
            f"primary_stable_set_pairs_{country}",
            EXPECTED_PRIMARY_PAIRS[country],
            primary_pairs,
            primary_pairs == EXPECTED_PRIMARY_PAIRS[country],
            "Valid adjacent days, identical vendor set and at least two vendors.",
        )
        add_audit(
            audit_rows,
            "sample_accounting",
            f"vendor_set_change_pairs_{country}",
            EXPECTED_VENDOR_SET_CHANGE_PAIRS[country],
            change_pairs,
            change_pairs == EXPECTED_VENDOR_SET_CHANGE_PAIRS[country],
            "Retained for the vendor-set selection check, not decomposed.",
        )

    vendor_days = vendor_days.sort_values(
        ["_country_rank", "_vendor_rank", "date"]
    ).reset_index(drop=True)
    by_country_vendor = vendor_days.groupby(
        ["country_id", "vendor"],
        sort=False,
    )
    vendor_days["previous_stock_count"] = by_country_vendor["stock_count"].shift(1)
    vendor_days["previous_price_usd"] = by_country_vendor["price_usd"].shift(1)
    vendor_days["previous_stock_share"] = by_country_vendor["stock_share"].shift(1)
    vendor_days["previous_positive_stock"] = (
        by_country_vendor["positive_stock"].shift(1).fillna(False).astype(bool)
    )

    pair_columns = [
        "previous_date",
        "calendar_day_difference",
        "previous_row_observed",
        "previous_country_day_valid",
        "previous_positive_vendor_count",
        "previous_positive_vendor_set",
        "previous_source_combined_price_usd",
        "valid_adjacent_pair",
        "vendor_set_unchanged",
        "primary_pair_eligible",
        "vendor_set_change_pair",
        "pair_status",
        "net_combined_price_change_usd",
    ]
    vendor_days = vendor_days.merge(
        day_metrics[["country_id", "date"] + pair_columns],
        on=["country_id", "date"],
        how="left",
        validate="many_to_one",
    )

    # Audit-only decomposition check. The R analysis calculates and reports the
    # components. Here we verify that the prepared lags and shares can
    # reproduce the accounting identity on every eligible pair.
    active_eligible_rows = (
        vendor_days["primary_pair_eligible"]
        & (vendor_days["positive_stock"] | vendor_days["previous_positive_stock"])
    )
    decomposition_rows = vendor_days.loc[active_eligible_rows].copy()
    decomposition_rows["price_component_term"] = (
        (decomposition_rows["stock_share"] + decomposition_rows["previous_stock_share"])
        / 2
        * (decomposition_rows["price_usd"] - decomposition_rows["previous_price_usd"])
    )
    decomposition_rows["weight_component_term"] = (
        (decomposition_rows["price_usd"] + decomposition_rows["previous_price_usd"])
        / 2
        * (
            decomposition_rows["stock_share"]
            - decomposition_rows["previous_stock_share"]
        )
    )

    decomposition_checks = (
        decomposition_rows.groupby(["country_id", "date"], as_index=False)
        .agg(
            price_component_usd=("price_component_term", "sum"),
            weight_component_usd=("weight_component_term", "sum"),
            net_combined_price_change_usd=(
                "net_combined_price_change_usd",
                "first",
            ),
            source_combined_price_usd=("source_combined_price_usd", "first"),
            previous_source_combined_price_usd=(
                "previous_source_combined_price_usd",
                "first",
            ),
        )
    )
    decomposition_checks["component_sum_usd"] = (
        decomposition_checks["price_component_usd"]
        + decomposition_checks["weight_component_usd"]
    )
    decomposition_checks["identity_difference_usd"] = (
        decomposition_checks["component_sum_usd"]
        - decomposition_checks["net_combined_price_change_usd"]
    )
    decomposition_checks["identity_tolerance_usd"] = (
        2 * PRICE_ABSOLUTE_TOLERANCE
        + PRICE_RELATIVE_TOLERANCE
        * (
            decomposition_checks["source_combined_price_usd"].abs()
            + decomposition_checks["previous_source_combined_price_usd"].abs()
        )
    )
    decomposition_checks["identity_ok"] = decomposition_checks[
        "identity_difference_usd"
    ].abs().le(decomposition_checks["identity_tolerance_usd"])

    identity_failures = int((~decomposition_checks["identity_ok"]).sum())
    add_audit(
        audit_rows,
        "output_validation",
        "eligible_pair_decomposition_identity_failures",
        0,
        identity_failures,
        identity_failures == 0,
        "Components are audit-only here. R will calculate the reported components.",
    )

    decomposition_checks["_country_rank"] = decomposition_checks["country_id"].map(
        country_rank
    )
    first_pair = decomposition_checks.sort_values(["_country_rank", "date"]).iloc[0]
    first_country = first_pair["country_id"]
    first_date = first_pair["date"]
    hand_check = decomposition_rows.loc[
        decomposition_rows["country_id"].eq(first_country)
        & decomposition_rows["date"].eq(first_date),
        [
            "vendor",
            "previous_price_usd",
            "price_usd",
            "previous_stock_share",
            "stock_share",
            "price_component_term",
            "weight_component_term",
        ],
    ].sort_values("vendor")

    hand_difference = float(first_pair["identity_difference_usd"])
    hand_tolerance = float(first_pair["identity_tolerance_usd"])
    add_audit(
        audit_rows,
        "output_validation",
        "printed_hand_check_identity",
        f"abs(difference) <= {hand_tolerance:.12g}",
        f"difference={hand_difference:.12g}",
        abs(hand_difference) <= hand_tolerance,
        f"First eligible pair: {first_country}, {first_date:%Y-%m-%d}.",
    )

    vendor_days = vendor_days.sort_values(
        ["_country_rank", "date", "_vendor_rank"]
    ).reset_index(drop=True)
    stop_if_failed(audit_rows, "Temporal eligibility and identity checks")
    return vendor_days, hand_check


# -----------------------------------------------------------------------------
# 6. Export, re-read and reconcile the final analytical CSV
# -----------------------------------------------------------------------------

def export_and_recheck(
    vendor_days: pd.DataFrame,
    hand_check: pd.DataFrame,
    audit_rows: list[dict[str, object]],
) -> None:
    """Write the analytical CSV, re-read it, and verify its keys and counts."""

    output_columns = [
        "date",
        "country_id",
        "country_name",
        "service_id",
        "service_name",
        "vendor",
        "source_member",
        "row_observed",
        "exchange_rate_rub_per_usd",
        "source_combined_stock",
        "source_combined_price_usd",
        "source_stock_valid",
        "source_price_valid",
        "exchange_rate_valid",
        "stock_count",
        "stock_valid",
        "positive_stock",
        "price_original",
        "price_currency",
        "price_usd",
        "active_price_valid",
        "vendor_measurement_valid",
        "total_vendor_stock",
        "positive_vendor_count",
        "positive_vendor_set",
        "pre_reconstruction_valid",
        "reconstructed_price_usd",
        "count_reconstruction_ok",
        "price_reconstruction_ok",
        "stock_share",
        "stock_share_sum",
        "share_sum_ok",
        "country_day_valid",
        "previous_date",
        "calendar_day_difference",
        "previous_row_observed",
        "previous_country_day_valid",
        "previous_positive_vendor_count",
        "previous_positive_vendor_set",
        "previous_source_combined_price_usd",
        "previous_stock_count",
        "previous_price_usd",
        "previous_stock_share",
        "previous_positive_stock",
        "valid_adjacent_pair",
        "vendor_set_unchanged",
        "primary_pair_eligible",
        "vendor_set_change_pair",
        "pair_status",
        "net_combined_price_change_usd",
    ]

    final_data = vendor_days[output_columns].copy()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    final_data.to_csv(
        OUTPUT_CSV,
        index=False,
        date_format="%Y-%m-%d",
        na_rep="",
    )

    reloaded = pd.read_csv(
        OUTPUT_CSV,
        dtype={
            "country_id": "string",
            "country_name": "string",
            "service_id": "string",
            "service_name": "string",
            "vendor": "string",
        },
        parse_dates=["date", "previous_date"],
    )

    expected_rows = len(COUNTRY_ORDER) * 361 * len(VENDORS)
    add_audit(
        audit_rows,
        "output_validation",
        "reloaded_output_rows",
        expected_rows,
        len(reloaded),
        len(reloaded) == expected_rows,
        "CSV is re-read from disk rather than checked only in memory.",
    )
    duplicate_output_keys = int(
        reloaded.duplicated(["country_id", "service_id", "vendor", "date"]).sum()
    )
    add_audit(
        audit_rows,
        "output_validation",
        "reloaded_duplicate_vendor_day_keys",
        0,
        duplicate_output_keys,
        duplicate_output_keys == 0,
        "Final key is country-platform-vendor-date.",
    )
    add_audit(
        audit_rows,
        "output_validation",
        "reloaded_date_coverage",
        "2024-08-01 to 2025-07-27",
        f"{reloaded['date'].min():%Y-%m-%d} to {reloaded['date'].max():%Y-%m-%d}",
        reloaded["date"].min() == START_DATE
        and reloaded["date"].max() == END_DATE,
        "The missing date remains an explicit row inside this range.",
    )

    reloaded_days = reloaded.drop_duplicates(["country_id", "date"])
    for country in COUNTRY_ORDER:
        country_days = reloaded_days["country_id"].eq(country)
        primary_pairs = int(
            (country_days & reloaded_days["primary_pair_eligible"]).sum()
        )
        change_pairs = int(
            (country_days & reloaded_days["vendor_set_change_pair"]).sum()
        )
        add_audit(
            audit_rows,
            "output_validation",
            f"reloaded_primary_pairs_{country}",
            EXPECTED_PRIMARY_PAIRS[country],
            primary_pairs,
            primary_pairs == EXPECTED_PRIMARY_PAIRS[country],
            COUNTRY_NAMES[country],
        )
        add_audit(
            audit_rows,
            "output_validation",
            f"reloaded_vendor_set_change_pairs_{country}",
            EXPECTED_VENDOR_SET_CHANGE_PAIRS[country],
            change_pairs,
            change_pairs == EXPECTED_VENDOR_SET_CHANGE_PAIRS[country],
            COUNTRY_NAMES[country],
        )

    add_audit(
        audit_rows,
        "output_validation",
        "analytical_csv_sha256",
        "recorded for reproducibility",
        sha256_file(OUTPUT_CSV),
        None,
        "Hash identifies the exact processed CSV created by this run.",
    )

    current_audit = audit_frame(audit_rows)
    no_failures = not current_audit["status"].eq("FAIL").any()
    add_audit(
        audit_rows,
        "output_validation",
        "overall_preparation_checks",
        "all required checks PASS",
        "all required checks PASS" if no_failures else "one or more checks FAIL",
        no_failures,
        "Passing code checks still requires review of the actual console output.",
    )
    stop_if_failed(audit_rows, "Export and re-read checks")

    final_audit = save_audit(audit_rows)
    print("\nDATA PREPARATION AUDIT")
    print(final_audit.to_string(index=False))
    print("\nHAND CHECK: FIRST ELIGIBLE COUNTRY-DAY PAIR")
    print(hand_check.to_string(index=False, float_format=lambda value: f"{value:.12f}"))
    print("\nOUTPUT FILES")
    print(f"Analytical data: {OUTPUT_CSV}")
    print(f"Audit table:     {AUDIT_CSV}")
    print(
        "\nThe script checks passed. Review the reported counts and hand check "
        "before using the analytical dataset in R."
    )


def main() -> None:
    """Run the complete data-preparation pipeline."""

    audit_rows: list[dict[str, object]] = []
    source = read_scoped_archive(audit_rows)
    vendor_days, day_metrics = prepare_vendor_days(source, audit_rows)
    vendor_days, hand_check = add_temporal_eligibility(
        vendor_days,
        day_metrics,
        audit_rows,
    )
    export_and_recheck(vendor_days, hand_check, audit_rows)


if __name__ == "__main__":
    main()
