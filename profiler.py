"""Works out what each column is, and how it should be added up.

Like Power BI, every column gets a data type and a default "summarise by".
Unlike Power BI, it also spots financial years, quarters, UK geography codes,
and numbers that must never be summed (rates, percentages, snapshots like population).
"""
import re
import warnings

import pandas as pd

MISSING = {"", "na", "n/a", "nan", "null", "none", "-", "--", ".."}

# Type names shown to users
TEXT, CATEGORY, ID = "Text", "Category", "ID"
WHOLE, DECIMAL, PERCENT, CURRENCY = "Whole number", "Decimal number", "Percentage", "Currency"
DATE, DATETIME, PERIOD, YEAR = "Date", "Date and time", "Period", "Year"
BOOLEAN = "True/False"
POSTCODE, AREA_CODE, LATITUDE, LONGITUDE = "UK postcode", "Area code", "Latitude", "Longitude"
URL, EMAIL = "Web link", "Email"

TYPES = [TEXT, CATEGORY, ID, WHOLE, DECIMAL, PERCENT, CURRENCY, DATE, DATETIME, PERIOD, YEAR,
         BOOLEAN, POSTCODE, AREA_CODE, LATITUDE, LONGITUDE, URL, EMAIL]
NUMERIC_TYPES = {WHOLE, DECIMAL, PERCENT, CURRENCY}
TIME_TYPES = {DATE, DATETIME, PERIOD, YEAR}

SUM, AVERAGE, LATEST, COUNT, NONE = "Sum", "Average", "Latest value", "Count", "Don't summarise"
SUMMARIES = [SUM, AVERAGE, LATEST, COUNT, NONE]

# Name clues for numbers that should not be added up
AVERAGE_WORDS = ["rate", "per", "pct", "percent", "ratio", "avg", "average", "mean", "median",
                 "price", "score", "index", "temperature", "temp", "age", "share", "proportion"]
SNAPSHOT_WORDS = ["population", "pop", "balance", "stock", "inventory", "headcount", "capacity",
                  "residents", "households", "employees", "staff"]
ID_WORDS = ["id", "code", "ref", "reference", "key", "uuid"]

BOOL_VALUES = {"true", "false", "yes", "no", "y", "n", "t", "f"}

RE_FIN_YEAR = re.compile(r"^(\d{4})\s*[/-]\s*(\d{2}|\d{4})$")
RE_FIN_QTR = re.compile(r"^(\d{4})\s*[/-]\s*(\d{2}|\d{4})\s*[- ]?\s*Q([1-4])$", re.I)
RE_YEAR_QTR = re.compile(r"^(\d{4})\s*[- ]?\s*Q([1-4])$|^Q([1-4])\s*[- ]?\s*(\d{4})$", re.I)
RE_YEAR_MONTH = re.compile(r"^(\d{4})-(\d{1,2})$")
RE_MONTH_YEAR = re.compile(r"^([A-Za-z]{3,9})[\s-]+(\d{4})$")
RE_POSTCODE = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$", re.I)
RE_AREA_CODE = re.compile(r"^[EWSNK]\d{8}$")
RE_URL = re.compile(r"^(https?://|www\.)\S+$", re.I)
RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def words(name):
    return set(re.split(r"[^a-z0-9%]+", name.lower())) - {""}


def has_word(name, options):
    w = words(name)
    return any(o in w for o in options) or ("%" in name)


def clean_number(series):
    # Strip £ $ € , % and spaces, then convert; returns numbers and what was stripped
    s = series.str.strip()
    had_percent = s.str.endswith("%").mean() > 0.5
    had_currency = s.str.match(r"^-?[£$€]").mean() > 0.5
    s = s.str.replace(r"[£$€,%\s]", "", regex=True).str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    return pd.to_numeric(s, errors="coerce"), had_percent, had_currency


def period_key(value):
    # Turns a period label into a sortable date (start of the period)
    v = value.strip()
    m = RE_FIN_QTR.match(v)
    if m:
        y, q = int(m.group(1)), int(m.group(3))
        month = [4, 7, 10, 1][q - 1]           # UK financial year starts in April
        return pd.Timestamp(y + (1 if q == 4 else 0), month, 1)
    m = RE_FIN_YEAR.match(v)
    if m:
        return pd.Timestamp(int(m.group(1)), 4, 1)
    m = RE_YEAR_QTR.match(v)
    if m:
        y = int(m.group(1) or m.group(4))
        q = int(m.group(2) or m.group(3))
        return pd.Timestamp(y, 3 * q - 2, 1)
    m = RE_YEAR_MONTH.match(v)
    if m and 1 <= int(m.group(2)) <= 12:
        return pd.Timestamp(int(m.group(1)), int(m.group(2)), 1)
    m = RE_MONTH_YEAR.match(v)
    if m and m.group(1)[:3].lower() in MONTHS:
        return pd.Timestamp(int(m.group(2)), MONTHS[m.group(1)[:3].lower()], 1)
    return pd.NaT


def share(mask):
    return float(mask.mean()) if len(mask) else 0.0


def detect_type(name, values):
    """values: the non-missing values of one column, as text."""
    if values.empty:
        return TEXT
    low = values.str.strip().str.lower()

    if share(low.isin(BOOL_VALUES)) == 1 and low.nunique() <= 2:
        return BOOLEAN

    # Periods before numbers and dates, so "2024/25" isn't read as a sum or a date
    if share(values.map(period_key).notna()) >= 0.95:
        return PERIOD

    nums, had_percent, had_currency = clean_number(values)
    if share(nums.notna()) >= 0.95:
        n = nums.dropna()
        whole = (n == n.round()).all()
        lname = name.lower()
        if "lat" in words(name) or "latitude" in lname:
            if n.between(-90, 90).all():
                return LATITUDE
        if words(name) & {"lon", "lng", "long", "longitude"}:
            if n.between(-180, 180).all():
                return LONGITUDE
        if whole and n.between(1900, 2100).all() and ("year" in lname or "yr" in words(name)):
            return YEAR
        if had_percent:
            return PERCENT
        if had_currency:
            return CURRENCY
        if whole and has_word(name, ID_WORDS) and n.nunique() > 0.9 * len(n):
            return ID
        return WHOLE if whole else DECIMAL

    if share(values.str.match(RE_AREA_CODE)) >= 0.95:
        return AREA_CODE
    if share(values.str.match(RE_POSTCODE)) >= 0.95:
        return POSTCODE
    if share(values.str.match(RE_URL)) >= 0.95:
        return URL
    if share(values.str.match(RE_EMAIL)) >= 0.95:
        return EMAIL

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        dates = pd.to_datetime(values, errors="coerce", dayfirst=True, format="mixed")
    if share(dates.notna()) >= 0.95:
        d = dates.dropna()
        has_time = ((d.dt.hour != 0) | (d.dt.minute != 0)).any()
        return DATETIME if has_time else DATE

    unique_ratio = values.nunique() / len(values)
    if has_word(name, ID_WORDS) and unique_ratio > 0.9:
        return ID
    if values.nunique() <= 50 or unique_ratio < 0.5:
        return CATEGORY
    return TEXT


def default_summary(name, col_type, numbers, df_numbers=None, category_cols=(), time_cols=()):
    """How a column should be added up by default."""
    if col_type in {ID, YEAR, LATITUDE, LONGITUDE, PERIOD, DATE, DATETIME}:
        return NONE
    if col_type not in NUMERIC_TYPES:
        return COUNT
    if col_type == PERCENT or has_word(name, AVERAGE_WORDS):
        return AVERAGE
    if has_word(name, SNAPSHOT_WORDS):
        return LATEST
    # Behaviour check: a value that stays the same for a category across time periods
    # is a snapshot (like population), not something to add up over time
    if df_numbers is not None and category_cols and time_cols:
        g = df_numbers.groupby(list(category_cols))[name]
        per_group = g.nunique(dropna=True) / g.size()
        if len(per_group) and per_group.median() < 0.5 and df_numbers[time_cols[0]].nunique() > 2:
            return LATEST
    return SUM


def role(col_type):
    if col_type in TIME_TYPES:
        return "Time"
    if col_type in {POSTCODE, AREA_CODE, LATITUDE, LONGITUDE}:
        return "Location"
    if col_type in NUMERIC_TYPES:
        return "Measure"
    if col_type == ID:
        return "Identifier"
    return "Dimension"


def profile(df):
    """df: every column read as text. Returns one row per column describing it."""
    rows = []
    for name in df.columns:
        raw = df[name].astype(str)
        missing = raw.str.strip().str.lower().isin(MISSING)
        values = raw[~missing]
        rows.append({
            "column": name,
            "type": detect_type(name, values),
            "missing_pct": round(missing.mean() * 100, 1),
            "unique": int(values.nunique()),
            "example": values.iloc[0] if len(values) else "",
        })
    prof = pd.DataFrame(rows)

    typed = apply_types(df, prof)
    cats = list(prof.loc[prof["type"].isin([CATEGORY, AREA_CODE, POSTCODE]), "column"])
    times = list(prof.loc[prof["type"].isin(TIME_TYPES), "column"])
    prof["summarise_by"] = [
        default_summary(r.column, r.type, None, typed, cats[:1], times[:1]) for r in prof.itertuples()
    ]
    prof["role"] = prof["type"].map(role)
    return prof[["column", "type", "role", "summarise_by", "missing_pct", "unique", "example"]]


def apply_types(df, prof):
    """Converts text columns into real types. Periods get a hidden sortable column."""
    out = pd.DataFrame(index=df.index)
    for r in prof.itertuples():
        raw = df[r.column].astype(str)
        missing = raw.str.strip().str.lower().isin(MISSING)
        raw = raw.where(~missing)
        if r.type in NUMERIC_TYPES or r.type in {YEAR, LATITUDE, LONGITUDE}:
            out[r.column] = clean_number(raw.fillna(""))[0]
        elif r.type in {DATE, DATETIME}:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                out[r.column] = pd.to_datetime(raw, errors="coerce", dayfirst=True, format="mixed")
        elif r.type == PERIOD:
            out[r.column] = raw
            out[f"__{r.column}_start"] = raw.map(lambda v: period_key(v) if isinstance(v, str) else pd.NaT)
        elif r.type == BOOLEAN:
            out[r.column] = raw.str.strip().str.lower().map(
                lambda v: v in {"true", "yes", "y", "t"} if isinstance(v, str) else None)
        else:
            out[r.column] = raw
    return out
