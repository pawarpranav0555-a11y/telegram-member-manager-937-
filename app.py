import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(
    page_title="Telegram Member Manager",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Telegram Member Manager")
st.caption("937 Contacts Management Dashboard")

FILE = Path("telegram_member_tracker.csv")

if not FILE.exists():
    st.error("telegram_member_tracker.csv file not found!")
    st.stop()

df = pd.read_csv(FILE).fillna("")

st.subheader("📋 Contact Records")
st.metric("Total Records", len(df))

edited_df = st.data_editor(
    df,
    use_container_width=True,
    hide_index=True,
    num_rows="fixed"
)

if st.button("💾 Save Changes"):
    edited_df.to_csv(FILE, index=False)
    st.success("Changes saved!")

st.download_button(
    "⬇️ Download Updated CSV",
    edited_df.to_csv(index=False).encode("utf-8"),
    file_name="telegram_member_tracker_updated.csv",
    mime="text/csv"
)
