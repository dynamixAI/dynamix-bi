import pandas as pd
import streamlit as st

st.set_page_config(page_title="Dynamix BI", page_icon="📊", layout="wide")

st.title("Dynamix BI")
st.caption("Upload a CSV. Dynamix BI checks your data before it charts it.")

uploaded = st.file_uploader("Upload a CSV file", type=["csv"])

if uploaded is None:
    st.info("Upload a CSV to get started.")
    st.stop()

# Read everything as text first; type detection comes in the next step
df = pd.read_csv(uploaded, dtype=str, keep_default_na=False)

c1, c2 = st.columns(2)
c1.metric("Rows", f"{len(df):,}")
c2.metric("Columns", len(df.columns))

st.subheader("Preview")
st.dataframe(df.head(100), use_container_width=True)
