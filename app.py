import re
import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(
    page_title="Telegram Member Manager",
    page_icon="📊",
    layout="wide"
)

MAX_RECORDS = 10000
TABLE = "telegram_contacts"
BATCH_SIZE = 500

COLUMNS = [
    "Mobile Number",
    "Telegram account verified",
    "Permission confirmed",
    "Joined @SignalsFreeIndia",
    "Notes"
]

STATUS_COLUMNS = COLUMNS[1:4]
CHOICES = ["Unknown", "Yes", "No"]


def clean_number(value):
    if pd.isna(value):
        return ""
    digits = re.sub(r"\D", "", str(value))

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

    if isinstance(value, str):
        value = value.strip().lower()
        if value in ["true", "t", "1", "yes", "y"]:
            return "Yes"
        if value in ["false", "f", "0", "no", "n"]:
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
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"]
    )


def fetch_all(columns="*"):
    client = get_supabase()
    rows = []

    for start in range(0, MAX_RECORDS, BATCH_SIZE):
        response = (
            client.table(TABLE)
            .select(columns)
            .order("id")
            .range(start, start + BATCH_SIZE - 1)
            .execute()
        )

        batch = response.data or []
        rows.extend(batch)

        if len(batch) < BATCH_SIZE:
            break

    return rows


def load_records():
    rows = fetch_all("*")
    result = []

    for row in rows:
        result.append({
            "Mobile Number": str(row.get("mobile_number") or ""),
            "Telegram account verified": to_choice(
                row.get("telegram_verified")
            ),
            "Permission confirmed": to_choice(
                row.get("permission_confirmed")
            ),
            "Joined @SignalsFreeIndia": to_choice(
                row.get("joined_channel")
            ),
            "Notes": row.get("notes") or ""
        })

    return pd.DataFrame(result, columns=COLUMNS)


def existing_numbers():
    return {
        str(row["mobile_number"])
        for row in fetch_all("mobile_number")
        if row.get("mobile_number")
    }


def prepare_import(frame):
    if frame is None or frame.empty:
        return pd.DataFrame(columns=COLUMNS), 0, 0

    frame = frame.copy()

    number_col = next(
        (
            col for col in frame.columns
            if str(col).strip().lower() in [
                "mobile number",
                "phone",
                "phone number",
                "mobile",
                "number"
            ]
        ),
        frame.columns[0]
    )

    raw = frame[number_col].tolist()
    cleaned = [clean_number(x) for x in raw]

    nonblank = sum(
        1 for x in raw
        if not pd.isna(x) and str(x).strip()
    )

    valid = [x for x in cleaned if x]
    invalid_count = nonblank - len(valid)
    duplicate_count = len(valid) - len(set(valid))

    output = pd.DataFrame()
    output["Mobile Number"] = cleaned

    for col in STATUS_COLUMNS:
        if col in frame.columns:
            output[col] = frame[col].map(to_choice)
        else:
            output[col] = "Unknown"

    if "Notes" in frame.columns:
        output["Notes"] = frame["Notes"].fillna("").astype(str)
    else:
        output["Notes"] = ""

    output = output[output["Mobile Number"] != ""]
    output = output.drop_duplicates(
        "Mobile Number",
        keep="first"
    )

    return output[COLUMNS].reset_index(drop=True), invalid_count, duplicate_count


def insert_new_records(frame):
    client = get_supabase()
    current = existing_numbers()

    new_rows = frame[
        ~frame["Mobile Number"].isin(current)
    ].copy()

    duplicate_count = len(frame) - len(new_rows)

    if len(current) + len(new_rows) > MAX_RECORDS:
        raise ValueError("10,000 records limit reached.")

    payload = []

    for _, row in new_rows.iterrows():
        payload.append({
            "mobile_number": row["Mobile Number"],
            "telegram_verified": from_choice(
                row["Telegram account verified"]
            ),
            "permission_confirmed": from_choice(
                row["Permission confirmed"]
            ),
            "joined_channel": from_choice(
                row["Joined @SignalsFreeIndia"]
            ),
            "notes": str(row["Notes"] or "")
        })

    inserted = 0

    for start in range(0, len(payload), BATCH_SIZE):
        batch = payload[start:start + BATCH_SIZE]

        if batch:
            response = (
                client.table(TABLE)
                .insert(batch)
                .execute()
            )
            inserted += len(response.data or [])

    return inserted, duplicate_count


def save_changed_records(original, edited):
    client = get_supabase()
    old_data = original.set_index("Mobile Number")
    changed = 0

    for _, row in edited.iterrows():
        number = clean_number(row["Mobile Number"])

        if not number or number not in old_data.index:
            continue

        old = old_data.loc[number]

        payload = {
            "telegram_verified": from_choice(
                row["Telegram account verified"]
            ),
            "permission_confirmed": from_choice(
                row["Permission confirmed"]
            ),
            "joined_channel": from_choice(
                row["Joined @SignalsFreeIndia"]
            ),
            "notes": str(row["Notes"] or "")
        }

        new_values = {
            "Telegram account verified": to_choice(
                payload["telegram_verified"]
            ),
            "Permission confirmed": to_choice(
                payload["permission_confirmed"]
            ),
            "Joined @SignalsFreeIndia": to_choice(
                payload["joined_channel"]
            ),
            "Notes": payload["notes"]
        }

        if all(
            str(old[col]) == str(new_values[col])
            for col in STATUS_COLUMNS + ["Notes"]
        ):
            continue

        (
            client.table(TABLE)
            .update(payload)
            .eq("mobile_number", number)
            .execute()
        )

        changed += 1

    return changed


def refresh_records():
    st.session_state.records = load_records()


def csv_bytes(frame):
    return frame.to_csv(index=False).encode("utf-8-sig")


st.title("📊 Telegram Member Manager")

st.caption("Supabase Database | Maximum 10,000 Records")

st.info(
    "हा अॅप संपर्क आणि संमतीची नोंद ठेवतो. "
    "फोन नंबरवरून Telegram खाते असल्याची खात्री करत नाही "
    "किंवा परवानगीशिवाय सदस्य जोडत नाही."
)

try:
    if "records" not in st.session_state:
        refresh_records()

    st.success("Supabase database connected")

except Exception as exc:
    st.error("Supabase connection failed.")
    st.code(str(exc))
    st.stop()


st.subheader("📥 Import New Numbers")

col1, col2 = st.columns(2)

with col1:
    uploaded_file = st.file_uploader(
        "Upload CSV File",
        type=["csv"]
    )

    if st.button("Import CSV Numbers"):
        if uploaded_file is None:
            st.warning("Please select a CSV file.")
        else:
            try:
                raw = pd.read_csv(
                    uploaded_file,
                    dtype=str
                ).fillna("")

                prepared, invalid, file_duplicates = prepare_import(raw)

                if prepared.empty:
                    st.warning("No valid 10-digit numbers found.")
                else:
                    inserted, db_duplicates = insert_new_records(prepared)
                    refresh_records()

                    st.success(
                        f"{inserted} new records saved | "
                        f"{db_duplicates} already existed | "
                        f"{file_duplicates} duplicates in CSV | "
                        f"{invalid} invalid numbers"
                    )

            except Exception as exc:
                st.error(f"CSV import failed: {exc}")


with col2:
    pasted = st.text_area(
        "Paste Mobile Numbers",
        height=120
    )

    if st.button("Import Pasted Numbers"):
        tokens = [
            x for x in re.split(r"[,;\s]+", pasted)
            if x.strip()
        ]

        raw = pd.DataFrame({
            "Mobile Number": tokens
        })

        prepared, invalid, file_duplicates = prepare_import(raw)

        if prepared.empty:
            st.warning("Enter valid 10-digit numbers.")
        else:
            try:
                inserted, db_duplicates = insert_new_records(prepared)
                refresh_records()

                st.success(
                    f"{inserted} new records saved | "
                    f"{db_duplicates} already existed | "
                    f"{file_duplicates} duplicates | "
                    f"{invalid} invalid numbers"
                )

            except Exception as exc:
                st.error(f"Save failed: {exc}")


st.divider()
st.subheader("📋 Contact Records")

df = st.session_state.records.copy()

top1, top2, top3 = st.columns(3)

top1.metric("Total Numbers", len(df))

top2.metric(
    "Permission Confirmed",
    int((df["Permission confirmed"] == "Yes").sum())
)

top3.metric(
    "Joined Channel",
    int((df["Joined @SignalsFreeIndia"] == "Yes").sum())
)


filter_col, search_col = st.columns([1, 2])

with filter_col:
    status_filter = st.selectbox(
        "Permission Filter",
        ["All", "Yes", "No", "Unknown"]
    )

with search_col:
    search = st.text_input("Search Number or Notes")


view = df.copy()

if status_filter != "All":
    view = view[
        view["Permission confirmed"] == status_filter
    ]

if search.strip():
    mask = view.astype(str).apply(
        lambda column: column.str.contains(
            search.strip(),
            case=False,
            regex=False
        )
    ).any(axis=1)

    view = view[mask]


st.caption(f"Showing {len(view)} records")

edited = st.data_editor(
    view,
    use_container_width=True,
    hide_index=True,
    num_rows="fixed",
    disabled=["Mobile Number"],
    column_config={
        "Mobile Number": st.column_config.TextColumn(
            "Mobile Number"
        ),
        "Telegram account verified": st.column_config.SelectboxColumn(
            "Telegram account verified",
            options=CHOICES,
            required=True
        ),
        "Permission confirmed": st.column_config.SelectboxColumn(
            "Permission confirmed",
            options=CHOICES,
            required=True
        ),
        "Joined @SignalsFreeIndia": st.column_config.SelectboxColumn(
            "Joined @SignalsFreeIndia",
            options=CHOICES,
            required=True
        ),
        "Notes": st.column_config.TextColumn("Notes")
    },
    key="records_editor"
)


if st.button("💾 Save Changes", type="primary"):
    try:
        changed = save_changed_records(df, edited)
        refresh_records()

        st.success(
            f"{changed} changed records saved successfully."
        )
        st.rerun()

    except Exception as exc:
        st.error(f"Save failed: {exc}")


if st.button("🔄 Refresh Database"):
    try:
        refresh_records()
        st.success("Database refreshed.")
        st.rerun()
    except Exception as exc:
        st.error(f"Refresh failed: {exc}")


st.download_button(
    "⬇️ Download Complete CSV",
    data=csv_bytes(st.session_state.records),
    file_name="telegram_member_tracker_updated.csv",
    mime="text/csv"
    )
