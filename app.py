import csv
import io

import pandas as pd
import streamlit as st

import profiler as P

st.set_page_config(page_title="Dynamix BI", page_icon="📊", layout="wide")

st.title("Dynamix BI")
st.caption("Upload a CSV. Dynamix BI checks your data before it charts it.")


@st.cache_data(show_spinner="Reading your file…")
def read_csv(data: bytes) -> pd.DataFrame:
    # Try common encodings, and work out whether it uses commas, semicolons or tabs
    for enc in ("utf-8-sig", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        sep = csv.Sniffer().sniff(text[:65536], delimiters=",;\t|").delimiter
    except csv.Error:
        sep = ","
    return pd.read_csv(io.StringIO(text), sep=sep, dtype=str, keep_default_na=False)


@st.cache_data(show_spinner="Working out your column types…")
def profile(df: pd.DataFrame) -> pd.DataFrame:
    return P.profile(df)


uploaded = st.file_uploader("Upload a CSV file", type=["csv"])
if uploaded is None:
    st.info("Upload a CSV to get started.")
    st.stop()

raw = read_csv(uploaded.getvalue())
prof = profile(raw)

c1, c2, c3 = st.columns(3)
c1.metric("Rows", f"{len(raw):,}")
c2.metric("Columns", len(raw.columns))
c3.metric("Measures found", int((prof["role"] == "Measure").sum()))

st.subheader("Your columns")
st.write("Dynamix BI has worked out what each column is and how it should be added up. "
         "If something looks wrong, change it in the table.")

edited = st.data_editor(
    prof,
    hide_index=True,
    use_container_width=True,
    disabled=["column", "role", "missing_pct", "unique", "example"],
    column_config={
        "column": "Column",
        "type": st.column_config.SelectboxColumn("Type", options=P.TYPES, required=True),
        "role": "Role",
        "summarise_by": st.column_config.SelectboxColumn(
            "Summarise by", options=P.SUMMARIES, required=True,
            help="Sum adds values up. Average is for rates, prices and percentages. "
                 "Latest value is for snapshots like population or stock, which must not be added up over time."),
        "missing_pct": st.column_config.NumberColumn("Missing", format="%.1f%%"),
        "unique": "Unique values",
        "example": "Example",
    },
    key="column_editor",
)
edited["role"] = edited["type"].map(P.role)

with st.expander("What do the summaries mean?"):
    st.markdown(
        "- **Sum**: add the values up, e.g. sales, crimes, units sold\n"
        "- **Average**: for rates, percentages, prices and scores. Adding these up gives nonsense\n"
        "- **Latest value**: for snapshots that repeat over time, e.g. population or stock. "
        "Adding population up every month would count the same people many times\n"
        "- **Count**: for text and categories, e.g. how many orders or areas\n"
        "- **Don't summarise**: IDs, dates, years and coordinates"
    )

data = P.apply_types(raw, edited)
st.session_state["data"] = data
st.session_state["profile"] = edited

st.subheader("Preview")
st.dataframe(data[[c for c in data.columns if not c.startswith("__")]].head(100), use_container_width=True)
