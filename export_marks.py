import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
import json

# ---------------------------------------------------
# FIREBASE INIT
# ---------------------------------------------------
@st.cache_resource
def init_firebase():
    if firebase_admin._apps:
        return firestore.client()

    try:
        if "firebase" in st.secrets:
            cfg = dict(st.secrets["firebase"])
        else:
            with open("firebase_key.json") as f:
                cfg = json.load(f)

        cred = credentials.Certificate(cfg)
        firebase_admin.initialize_app(cred)
        return firestore.client()

    except Exception as e:
        st.error(f"Firebase init failed: {e}")
        return None


db = init_firebase()
if not db:
    st.stop()


# ---------------------------------------------------
# PAGE HEADER
# ---------------------------------------------------
st.title("📤 Export Evaluated Marks (Final)")

# Correct section order in final exported sheet
SECTION_ORDER = [
    "Adaptability & Learning",
    "Aptitude Test",
    "Communication Skills - Descriptive",
    "Communication Skills - Objective",
]


# ---------------------------------------------------
# READ ALL STUDENT DATA
# ---------------------------------------------------
docs = db.collection("student_responses").list_documents()
rows = []

for ref in docs:
    snap = ref.get()
    if not snap.exists:
        continue
    data = snap.to_dict()

    roll = data.get("Roll")
    section = data.get("Section")
    evalb = data.get("Evaluation", {})

    if not roll or not section:
        continue

    # Extract saved values
    mcq = evalb.get("mcq_total")
    likert = evalb.get("likert_total")
    text = evalb.get("text_total")
    final = evalb.get("final_total")     # final score for this test
    grand = evalb.get("grand_total")     # grand total across all tests

    # ---------------------------------------------------
    # Apply N/A logic based on test type
    # ---------------------------------------------------

    # A) Adaptability & Learning  => Likert only
    if section == "Adaptability & Learning":
        mcq_show = "N/A"
        text_show = "N/A"
        likert_show = likert if likert not in (None, "") else "N/A"
        final_show = likert_show

    # B) Aptitude Test  => MCQ + Text
    elif section == "Aptitude Test":
        mcq_show = mcq if mcq not in (None, "") else "N/A"
        likert_show = "N/A"
        text_show = text if text not in (None, "") else "N/A"
        final_show = (mcq or 0) + (text or 0)

    # C) Communication Skills - Descriptive => Text Only
    elif section == "Communication Skills - Descriptive":
        mcq_show = "N/A"
        likert_show = "N/A"
        text_show = text if text not in (None, "") else "N/A"
        final_show = text_show

    # D) Communication Skills - Objective => MCQ Only
    elif section == "Communication Skills - Objective":
        mcq_show = mcq if mcq not in (None, "") else "N/A"
        likert_show = "N/A"
        text_show = "N/A"
        final_show = mcq_show

    else:
        mcq_show = likert_show = text_show = final_show = "N/A"

    # Append extracted row
    rows.append([
        roll,
        section,
        mcq_show,
        likert_show,
        text_show,
        final_show,
        grand
    ])


# ---------------------------------------------------
# BUILD FINAL DATAFRAME
# ---------------------------------------------------
df = pd.DataFrame(rows, columns=[
    "Roll Number",
    "Section",
    "MCQ Score",
    "Likert Score",
    "Text Score",
    "Final Score (This Test)",
    "Grand Total (All Tests)"
])

# Sort rows — by Roll, then by fixed section order
cat = pd.CategoricalDtype(categories=SECTION_ORDER, ordered=True)
df["Section"] = df["Section"].astype(cat)
df = df.sort_values(["Roll Number", "Section"])

# ---------------------------------------------------
# Only show GRAND TOTAL on first section per Roll
# ---------------------------------------------------
clean_rows = []
prev_roll = None

for _, r in df.iterrows():
    row_copy = r.copy()
    if row_copy["Roll Number"] == prev_roll:
        row_copy["Grand Total (All Tests)"] = ""
    else:
        prev_roll = row_copy["Roll Number"]
    clean_rows.append(row_copy)

df_final = pd.DataFrame(clean_rows)


# ---------------------------------------------------
# DISPLAY + DOWNLOAD
# ---------------------------------------------------
st.dataframe(df_final)

csv = df_final.to_csv(index=False).encode("utf-8")

st.download_button(
    "⬇ Download Marks CSV",
    csv,
    "evaluated_marks.csv",
    "text/csv",
)

st.success("✅ Export Complete — Ready to Download!")
