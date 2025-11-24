import json
import pandas as pd
import streamlit as st

import firebase_admin
from firebase_admin import credentials, firestore

# ---------------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------------
st.set_page_config(page_title="Faculty Evaluation Dashboard", layout="wide")
st.title("👩‍🏫 Faculty Evaluation Dashboard")


# ---------------------------------------------------------------
# FIREBASE INIT
# ---------------------------------------------------------------
@st.cache_resource
def init_firebase():
    if firebase_admin._apps:
        return firestore.client()

    # Load firebase_key.json from deployment folder
    try:
        if "firebase" in st.secrets:
            cfg = dict(st.secrets["firebase"])
        else:
            with open("firebase_key.json", "r") as f:
                cfg = json.load(f)

        cred = credentials.Certificate(cfg)
        firebase_admin.initialize_app(cred)
        return firestore.client()

    except Exception as e:
        st.error(f"Firebase init failed: {e}")
        return None


db = init_firebase()
if db is None:
    st.stop()


# ---------------------------------------------------------------
# LOAD CSV QUESTION BANKS
# ---------------------------------------------------------------
QUESTION_FILES = {
    "Aptitude Test": "aptitude.csv",
    "Adaptability & Learning": "adaptability_learning.csv",
    "Communication Skills - Objective": "communication_skills_objective.csv",
    "Communication Skills - Descriptive": "communication_skills_descriptive.csv",
}

@st.cache_data
def load_banks():
    banks = {}
    for section, fname in QUESTION_FILES.items():
        try:
            df = pd.read_csv(fname)
            df.columns = [c.strip() for c in df.columns]
            df["Type"] = df["Type"].astype(str).str.lower()
            banks[section] = df
        except Exception as e:
            st.error(f"Error loading {fname}: {e}")
            banks[section] = pd.DataFrame()
    return banks

question_banks = load_banks()


# ---------------------------------------------------------------
# FIXED MARK SCALES
# ---------------------------------------------------------------
FOUR_MARK_QIDS = {12, 13, 14, 16, 17, 18}
THREE_MARK_QIDS = {22, 23, 24, 25, 28, 29, 30, 34}

def parse_qid(q):
    try:
        return int(str(q).replace("Q", "").strip())
    except:
        return -1

def scale_for_qid(q):
    x = parse_qid(q)
    if x in FOUR_MARK_QIDS:
        return [0, 1, 2, 3]
    if x in THREE_MARK_QIDS:
        return [0, 1, 2]
    return [0, 1]


# ---------------------------------------------------------------
# FIRESTORE → LOAD ALL STUDENT RESPONSES
# ---------------------------------------------------------------
def load_students():
    roll_map = {}
    try:
        docs = list(db.collection("student_responses").list_documents())
    except:
        return {}

    for ref in docs:
        snap = ref.get()
        if not snap.exists:
            continue

        data = snap.to_dict()
        roll = data.get("Roll")
        section = data.get("Section")
        if not roll or not section:
            continue

        responses = data.get("Responses")
        if not isinstance(responses, list):
            responses = []

        data["Responses"] = responses

        if roll not in roll_map:
            roll_map[roll] = []

        roll_map[roll].append((ref.id, data))

    return roll_map


roll_map = load_students()
if not roll_map:
    st.warning("No student responses found.")
    st.stop()


# ---------------------------------------------------------------
# STUDENT DROPDOWN
# ---------------------------------------------------------------
rolls = sorted(roll_map.keys())
selected_roll = st.selectbox("Select Student Roll Number", rolls)

docs_for_roll = roll_map[selected_roll]


# ---------------------------------------------------------------
# FINAL SCORING FUNCTIONS
# ---------------------------------------------------------------
def get_correct_answer(row):
    for col in ["Answer", "CorrectAnswer", "Correct", "Ans", "AnswerKey", "RightAnswer"]:
        if col in row and pd.notna(row[col]):
            return str(row[col]).strip()
    return None


def calc_mcq(df, responses):
    if df.empty:
        return 0
    total = 0
    df_index = df.set_index(df["QuestionID"].astype(str), drop=False)
    for r in responses:
        qid = str(r.get("QuestionID", "")).strip()
        ans = str(r.get("Response", "")).strip()
        if qid in df_index.index:
            row = df_index.loc[qid]
            if row["Type"] == "mcq":
                if ans == get_correct_answer(row):
                    total += 1
    return total


def calc_likert(df, responses):
    if df.empty:
        return 0
    total = 0
    df_index = df.set_index(df["QuestionID"].astype(str), drop=False)
    for r in responses:
        qid = str(r.get("QuestionID", "")).strip()
        raw = r.get("Response", None)
        if qid in df_index.index:
            row = df_index.loc[qid]
            if row["Type"] == "likert":
                try:
                    v = int(raw)
                    total += max(0, min(4, v - 1))  # 1→0 … 5→4
                except:
                    pass
    return total


# ---------------------------------------------------------------
# MANUAL TEST SELECTION
# ---------------------------------------------------------------
MANUAL_TESTS = ["Aptitude Test", "Communication Skills - Descriptive"]

manual_tests_available = sorted([
    data.get("Section")
    for _, data in docs_for_roll
    if data.get("Section") in MANUAL_TESTS
])

selected_test = st.selectbox("Select Test for Manual Evaluation", manual_tests_available)


# ---------------------------------------------------------------
# GET DOCUMENT FOR THIS TEST
# ---------------------------------------------------------------
selected_doc_id = None
selected_doc_data = None

for doc_id, data in docs_for_roll:
    if data.get("Section") == selected_test:
        selected_doc_id = doc_id
        selected_doc_data = data
        break

df_test = question_banks[selected_test]
responses_test = selected_doc_data.get("Responses", [])
existing_eval = selected_doc_data.get("Evaluation", {})
saved_marks = existing_eval.get("text_marks", {})
saved_text_total = existing_eval.get("text_total", 0)


# ---------------------------------------------------------------
# MANUAL MARK ENTRY (NO AUTO UPDATE)
# ---------------------------------------------------------------
st.markdown("## ✍️ Manual Text Evaluation")

short_df = df_test[df_test["Type"] == "short"]

marks_given = {}
text_total = 0

for _, row in short_df.iterrows():
    qid = str(row["QuestionID"])
    qtext = row["Question"]

    # student's answer
    answer = "(no answer)"
    for r in responses_test:
        if str(r["QuestionID"]) == qid:
            answer = str(r.get("Response", "(no answer)"))

    scale = scale_for_qid(qid)
    default = saved_marks.get(qid, 0)
    if default not in scale:
        default = 0

    with st.expander(f"Q{qid}: {qtext}", expanded=True):
        st.markdown(f"**Student Answer:** {answer}")
        mark = st.radio(
            "Marks:",
            scale,
            index=scale.index(default),
            horizontal=True,
            key=f"{selected_roll}_{selected_test}_{qid}"
        )
        marks_given[qid] = mark
        text_total += mark


st.markdown("---")


# ---------------------------------------------------------------
# CALCULATE MARKS BUTTON
# ---------------------------------------------------------------
st.markdown("## 🧮 Calculate Marks (Preview Only)")

if st.button("📌 Calculate Marks"):
    mcq_sel = calc_mcq(df_test, responses_test)
    likert_sel = calc_likert(df_test, responses_test)
    final_sel = mcq_sel + likert_sel + text_total

    st.success(
        f"""
### ✔ Preview Marks
**MCQ (This Test):** {mcq_sel}  
**Likert (This Test):** {likert_sel}  
**Text Marks:** {text_total}  

### 👉 Final Score (This Test): **{final_sel}**
*(Not saved yet.)*
"""
    )


# ---------------------------------------------------------------
# SAVE BUTTON
# ---------------------------------------------------------------
st.markdown("## 💾 Save Final Evaluation")

if st.button("💾 Save Evaluation for This Test"):

    mcq_sel = calc_mcq(df_test, responses_test)
    likert_sel = calc_likert(df_test, responses_test)
    final_sel = mcq_sel + likert_sel + text_total

    # Save into this doc
    db.collection("student_responses").document(selected_doc_id).set(
        {
            "Evaluation": {
                "text_marks": marks_given,
                "text_total": text_total,
                "mcq_total": mcq_sel,
                "likert_total": likert_sel,
                "final_total": final_sel,
            }
        },
        merge=True,
    )

    # Compute grand total (saved values)
    grand_total = 0
    for doc_id, data in docs_for_roll:
        ev = data.get("Evaluation", {})
        if doc_id == selected_doc_id:
            grand_total += final_sel
        else:
            grand_total += ev.get("final_total", 0)

    # Save grand total in all docs
    for doc_id, _ in docs_for_roll:
        db.collection("student_responses").document(doc_id).set(
            {"Evaluation": {"grand_total": grand_total}},
            merge=True
        )

    st.success(
        f"""
### 🎉 Evaluation Saved Successfully!
**Final Score (This Test): {final_sel}**  
**👉 Updated GRAND TOTAL (All Tests): {grand_total}**
"""
    )
