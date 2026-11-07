
import re
import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="Telegram Member Manager", page_icon="📊", layout="wide")

MAX_RECORDS = 10000
TABLE = "telegram_contacts"
COLUMNS = [
    "Mobile Number",
    "Telegram account verified",
    "Permission confirmed",
    "Joined @SignalsFreeIndia",
    "Notes"
]

def clean_number(value):
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits if len(digits) == 10 else ""

def to_choice(value):
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "Unknown"

def from_choice(value):
    value = str(value or "").strip().lower()
    if value == "yes":
        return True
    if value == "no":
        return False
    return None

@st.cache_resource
def get_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

def load_records():
    client = get_supabase()
    response = client.table(TABLE).select("*").limit(MAX_RECORDS).execute()
    rows = response.data or []
    result = []
    for row in rows:
        result.append({
            "Mobile Number": str(row.get("mobile_number") or ""),
            "Telegram account verified": to_choice(row.get("telegram_verified")),
            "Permission confirmed": to_choice(row.get("permission_confirmed")),
            "Joined @SignalsFreeIndia": to_choice(row.get("joined_channel")),
            "Notes": row.get("notes") or ""
        })
    return pd.DataFrame(result, columns=COLUMNS)

def save_records(frame):
    client = get_supabase()
    for _, row in frame.iterrows():
        number = clean_number(row["Mobile Number"])
        if not number:
            continue
        payload = {
            "mobile_number": number,
            "telegram_verified": from_choice(row["Telegram account verified"]),
            "permission_confirmed": from_choice(row["Permission confirmed"]),
            "joined_channel": from_choice(row["Joined @SignalsFreeIndia"]),
            "notes": str(row["Notes"] or "")
        }
        client.table(TABLE).upsert(
            payload, on_conflict="mobile_number"
        ).execute()

def normalize_frame(frame):
    if frame is None or frame.empty:
        return pd.DataFrame(columns=COLUMNS)
    number_col = next(
        (c for c in frame.columns if str(c).strip().lower()
         in ["mobile number", "phone", "phone number", "mobile", "number"]),
        frame.columns[0]
    )
    out = pd.DataFrame()
    out["Mobile Number"] = frame[number_col].map(clean_number)
    for col in COLUMNS[1:]:
        out[col] = frame[col].fillna("").astype(str) if col in frame.columns else ""
    out = out[out["Mobile Number"] != ""]
    return out.drop_duplicates("Mobile Number").reset_index(drop=True)

def csv_bytes(frame):
    return frame.to_csv(index=False).encode("utf-8-sig")

st.title("📊 Telegram Member Manager")
st.caption("Supabase database connected | Up to 10,000 unique records")
st.info("हा अॅप संपर्क आणि संमतीची नोंद ठेवतो. फोन नंबरवरून Telegram खाते असल्याची खात्री करत नाही किंवा परवानगीशिवाय सदस्य जोडत नाही.")

try:
    if "records" not in st.session_state:
        st.session_state.records = load_records()
    st.success("Supabase database connected")
except Exception as exc:
    st.error("Supabase connection failed. Streamlit Secrets आणि database तपासा.")
    st.code(str(exc))
    st.stop()

st.subheader("📥 नवीन नंबर जोडा")
left, right = st.columns(2)

with left:
    upload = st.file_uploader("CSV फाइल अपलोड करा", type=["csv"])
    if upload is not None and st.button("अपलोडमधील नंबर जोडा"):
        try:
            incoming = normalize_frame(pd.read_csv(upload, dtype=str).fillna(""))
            current = st.session_state.records
            merged = pd.concat([current, incoming], ignore_index=True)
            merged = merged.drop_duplicates("Mobile Number", keep="first")
            if len(merged) > MAX_RECORDS:
                st.error("10,000 नोंदींची मर्यादा पूर्ण झाली.")
            else:
                save_records(incoming)
                st.session_state.records = load_records()
                st.success("नवीन नोंदी Supabase मध्ये सेव्ह झाल्या.")
        except Exception as exc:
            st.error(f"Import error: {exc}")

with right:
    pasted = st.text_area("नंबर पेस्ट करा", height=120)
    if st.button("पेस्ट केलेले नंबर जोडा"):
        nums = [clean_number(x) for x in re.split(r"[,;\s]+", pasted) if x.strip()]
        incoming = pd.DataFrame({"Mobile Number": [n for n in nums if n]})
        for col in COLUMNS[1:]:
            incoming[col] = ""
        incoming = incoming.drop_duplicates("Mobile Number")
        try:
            merged = pd.concat([st.session_state.records, incoming])
            merged = merged.drop_duplicates("Mobile Number", keep="first")
            if len(merged) > MAX_RECORDS:
                st.error("10,000 नोंदींची मर्यादा पूर्ण झाली.")
            else:
                save_records(incoming)
                st.session_state.records = load_records()
                st.success("नवीन नोंदी Supabase मध्ये सेव्ह झाल्या.")
        except Exception as exc:
            st.error(f"Save error: {exc}")

df = st.session_state.records.copy()
st.divider()
st.subheader("📋 Contact Records")

a, b, c = st.columns(3)
a.metric("एकूण नंबर", len(df))
b.metric("Permission confirmed", int((df["Permission confirmed"] == "Yes").sum()))
c.metric("Joined channel", int((df["Joined @SignalsFreeIndia"] == "Yes").sum()))

search = st.text_input("🔎 नंबर किंवा Notes शोधा")
view = df
if search:
    view = df[df.astype(str).apply(
        lambda row: row.str.contains(search, case=False, regex=False).any(),
        axis=1
    )]

edited = st.data_editor(
    view,
    use_container_width=True,
    hide_index=True,
    num_rows="fixed",
    column_config={
        "Mobile Number": st.column_config.TextColumn(disabled=True),
        "Telegram account verified": st.column_config.SelectboxColumn(
            options=["", "Yes", "No", "Unknown"]),
        "Permission confirmed": st.column_config.SelectboxColumn(
            options=["", "Yes", "No"]),
        "Joined @SignalsFreeIndia": st.column_config.SelectboxColumn(
            options=["", "Yes", "No"]),
        "Notes": st.column_config.TextColumn()
    },
    key="records_editor"
)

if st.button("💾 बदल सेव्ह करा", type="primary"):
    try:
        updated = st.session_state.records.copy().set_index("Mobile Number")
        changes = edited.set_index("Mobile Number")
        for idx in changes.index:
            if idx in updated.index:
                for col in COLUMNS[1:]:
                    updated.loc[idx, col] = changes.loc[idx, col]
        updated = updated.reset_index()[COLUMNS]
        save_records(updated)
        st.session_state.records = load_records()
        st.success("बदल Supabase मध्ये कायमचे सेव्ह झाले.")
        st.rerun()
    except Exception as exc:
        st.error(f"Save failed: {exc}")

st.download_button(
    "⬇️ पूर्ण CSV डाउनलोड करा",
    csv_bytes(st.session_state.records),
    file_name="telegram_member_tracker_updated.csv",
    mime="text/csv"
    )
    
