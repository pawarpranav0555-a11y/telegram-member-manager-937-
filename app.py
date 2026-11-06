import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Telegram Member Manager", page_icon="📊", layout="wide")
MAX_RECORDS = 10000
COLUMNS = ["Mobile Number", "Telegram account verified", "Permission confirmed", "Joined @SignalsFreeIndia", "Notes"]

def clean_number(value):
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits if len(digits) == 10 else ""

def normalize_frame(frame):
    if frame is None or frame.empty:
        return pd.DataFrame(columns=COLUMNS)
    frame = frame.copy()
    number_col = next((c for c in frame.columns if str(c).strip().lower() in
        ["mobile number", "phone", "phone number", "mobile", "number"]), frame.columns[0])
    out = pd.DataFrame()
    out["Mobile Number"] = frame[number_col].map(clean_number)
    for col in COLUMNS[1:]:
        out[col] = frame[col].fillna("").astype(str) if col in frame.columns else ""
    out = out[out["Mobile Number"] != ""]
    return out.drop_duplicates(subset=["Mobile Number"], keep="first")[COLUMNS].reset_index(drop=True)

def csv_bytes(frame):
    return frame.to_csv(index=False).encode("utf-8-sig")

st.title("📊 Telegram Member Manager")
st.caption("Contact records, consent tracking and CSV management. Supports up to 10,000 unique numbers.")
st.info("हा अॅप नंबरची यादी व्यवस्थापित करतो. फोन नंबरवरून Telegram खाते आहे का हे खात्रीने शोधत नाही आणि Telegram ची सदस्य-जोडण्याची मर्यादा बायपास करत नाही.")

if "records" not in st.session_state:
    try:
        st.session_state.records = normalize_frame(pd.read_csv("telegram_member_tracker.csv", dtype=str).fillna(""))
    except FileNotFoundError:
        st.session_state.records = pd.DataFrame(columns=COLUMNS)

st.subheader("📥 नवीन नंबर जोडा")
left, right = st.columns(2)
with left:
    upload = st.file_uploader("CSV फाइल अपलोड करा", type=["csv"])
    if upload is not None and st.button("अपलोडमधील नंबर जोडा"):
        try:
            incoming = normalize_frame(pd.read_csv(upload, dtype=str).fillna(""))
            before = len(st.session_state.records)
            merged = pd.concat([st.session_state.records, incoming], ignore_index=True).drop_duplicates("Mobile Number")
            if len(merged) > MAX_RECORDS:
                st.error(f"मर्यादा {MAX_RECORDS:,} आहे.")
            else:
                st.session_state.records = merged[COLUMNS].reset_index(drop=True)
                st.success(f"{len(merged)-before} नवीन नंबर जोडले. डुप्लिकेट वगळले.")
        except Exception as exc:
            st.error(f"CSV वाचता आली नाही: {exc}")
with right:
    pasted = st.text_area("नंबर इथे पेस्ट करा (comma, space किंवा नवीन ओळ चालेल)", height=120)
    if st.button("पेस्ट केलेले नंबर जोडा"):
        nums = [clean_number(x) for x in re.split(r"[,;\s]+", pasted) if x.strip()]
        incoming = pd.DataFrame({"Mobile Number": [n for n in nums if n]})
        for col in COLUMNS[1:]:
            incoming[col] = ""
        before = len(st.session_state.records)
        merged = pd.concat([st.session_state.records, incoming], ignore_index=True).drop_duplicates("Mobile Number")
        if len(merged) > MAX_RECORDS:
            st.error(f"एकूण नोंदी {MAX_RECORDS:,} पेक्षा जास्त होऊ शकत नाहीत.")
        else:
            st.session_state.records = merged[COLUMNS].reset_index(drop=True)
            st.success(f"{len(merged)-before} नवीन नंबर जोडले. चुकीचे/डुप्लिकेट नंबर वगळले.")

df = st.session_state.records.copy()
st.divider()
st.subheader("📋 Contact Records")
a, b, c = st.columns(3)
a.metric("एकूण नंबर", f"{len(df):,}")
b.metric("Permission confirmed", int((df["Permission confirmed"].str.strip().str.lower() == "yes").sum()))
c.metric("Joined channel", int((df["Joined @SignalsFreeIndia"].str.strip().str.lower() == "yes").sum()))

search = st.text_input("🔎 नंबर किंवा Notes शोधा")
view = df
if search:
    view = df[df.astype(str).apply(lambda row: row.str.contains(search, case=False, regex=False).any(), axis=1)]

edited = st.data_editor(view, use_container_width=True, hide_index=True, num_rows="fixed",
    column_config={
        "Mobile Number": st.column_config.TextColumn("Mobile Number", disabled=True),
        "Telegram account verified": st.column_config.SelectboxColumn("Telegram account verified", options=["", "Yes", "No", "Unknown"]),
        "Permission confirmed": st.column_config.SelectboxColumn("Permission confirmed", options=["", "Yes", "No"]),
        "Joined @SignalsFreeIndia": st.column_config.SelectboxColumn("Joined @SignalsFreeIndia", options=["", "Yes", "No"]),
        "Notes": st.column_config.TextColumn("Notes"),
    }, key="records_editor")

if st.button("💾 बदल सेव्ह करा", type="primary"):
    base = st.session_state.records.set_index("Mobile Number")
    changes = edited.set_index("Mobile Number")
    for idx in changes.index:
        if idx in base.index:
            for col in COLUMNS[1:]:
                base.loc[idx, col] = changes.loc[idx, col]
    st.session_state.records = base.reset_index()[COLUMNS]
    st.success("बदल या सत्रात सेव्ह झाले. कायमची प्रत ठेवण्यासाठी CSV डाउनलोड करा.")

st.download_button("⬇️ पूर्ण CSV डाउनलोड करा", csv_bytes(st.session_state.records),
    file_name="telegram_member_tracker_updated.csv", mime="text/csv")
st.caption("टीप: अॅप रीस्टार्ट/री-डिप्लॉय झाल्यावर सत्रातील बदल टिकतीलच याची हमी नाही. प्रत्येक अपडेटनंतर CSV डाउनलोड करून ठेवा आणि पुढच्या वेळी तीच CSV अपलोड करा.")
