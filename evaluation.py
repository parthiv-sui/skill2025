import json
from typing import Dict, List, Tuple

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
# FIREBASE INITIALIZATION
# ---------------------------------------------------------------
@st.cache_resource
def init_firebase():
    try:
        if firebase_admin._apps:
            return firestore.client()

        if "firebase" in st.secrets:
            cfg = dict(st.secrets["firebase"])
        else:
            with open("firebase_key.json", "r") as f:
                cfg = json.load(f)

        cred = credentials.Certificate(cfg)
        firebase_admin.initialize_app(cred)
        return firestore.client()

    except Exception as e:
        st.error(f"❌ Firebase initialization failed: {e}")
        return None

db = init_firebase()
if db is None:
    st.stop()

# ---------------------------------------------------------------
# QUESTION BANKS
# ---------------------------------------------------------------
QUESTION_FILES = {
    "Aptitude Test": "aptitude.csv",
    "Adaptability & Learning": "adaptability_learning.csv",
    "Communication Skills - Objective": "communication_skills_objective.csv",
    "Communication Skills - Descriptive": "communication_skills_descriptive.csv",
}

@st.cache_data
def load_question_banks():
    banks = {}
    for section, fname in QUESTION_FILES.items():
        try:
            df = pd.read_csv(fname)
            df.columns = [c.strip() for c in df.columns]
            df["Type"] = df["Type"].astype(str).str.lower()
            banks[section] = df
        except Exception as e:
            st.error(f"Error loading CSV '{fname}': {e}")
            banks[section] = pd.DataFrame()
    return banks

question_banks = load_question_banks()

AUTO_TESTS = ["Adaptability & Learning", "Communication Skills - Objective"]
MANUAL_TESTS = ["Aptitude Test", "Communication Skills - Descriptive"]

# ---------------------------------------------------------------
# FIXED MARKING QID LISTS (YOUR METHOD A)
# ---------------------------------------------------------------
FOUR_MARK_QIDS = {12, 13, 14, 16, 17, 18}
THREE_MARK_QIDS = {22, 23, 24, 25, 28, 29, 30, 34}

def parse_qid(q):
    s = str(q).replace("Q", "").strip()
    try:
        return int(s)
    except:
        return -1

def scale_for_qid(qid):
    q = parse_qid(qid)
    if q in FOUR_MARK_QIDS:
        return [0, 1, 2, 3]
    if q in THREE_MARK_QIDS:
        return [0, 1, 2]
    return [0, 1]

# ---------------------------------------------------------------
# LOAD STUDENT RESPONSES FROM FIRESTORE
# ---------------------------------------------------------------
def load_students():
    roll_map = {}
    try:
        doc_refs = list(db.collection("student_responses").list_documents())
    except Exception as e:
        st.error(f"Error loading Firestore: {e}")
        return {}

    for ref in doc_refs:
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

roll_to_docs = load_students()
if not roll_to_docs:
    st.warning("No student responses found.")
    st.stop()

# Student dropdown
rolls_sorted = sorted(roll_to_docs.keys())
selected_roll = st.selectbox("Select Student Roll Number", rolls_sorted)

docs_for_roll = roll_to_docs[selected_roll]


# ---------------------------------------------------------------
# SCORING FUNCTIONS (FINAL, CORRECTED)
# ---------------------------------------------------------------

def get_correct_answer(row: pd.Series):
    """Return correct MCQ answer from any supported column name."""
    for col in ["Answer", "CorrectAnswer", "Correct", "Ans", "AnswerKey", "RightAnswer"]:
        if col in row and pd.notna(row[col]):
            return str(row[col]).strip()
    return None


def calc_mcq(df: pd.DataFrame, responses: List[Dict]) -> int:
    """
    Final MCQ scoring:
    - Matches QuestionID EXACTLY (string comparison)
    - Uses Answer column from CSV
    - Only Type='mcq' questions counted
    """
    if df is None or len(df) == 0:
        return 0
    if responses is None:
        return 0

    score = 0
    df_idx = df.set_index(df["QuestionID"].astype(str), drop=False)

    for r in responses:
        qid = str(r.get("QuestionID", "")).strip()
        stu_ans = str(r.get("Response", "")).strip()

        if not qid or not stu_ans:
            continue

        if qid not in df_idx.index:  # IMPORTANT: earlier bug fixed
            continue

        row = df_idx.loc[qid]
        if str(row.get("Type", "")).lower() != "mcq":
            continue

        correct = get_correct_answer(row)
        if correct and stu_ans == correct:
            score += 1

    return score


def likert_to_score(value: int) -> int:
    """
    Likert mapping (YOUR CHOICE):
        1 → 0
        2 → 1
        3 → 2
        4 → 3
        5 → 4
    """
    try:
        v = int(value)
        return max(0, min(4, v - 1))
    except:
        return 0


def calc_likert(df: pd.DataFrame, responses: List[Dict]) -> int:
    """
    Final Likert scoring:
    - Only Type='likert'
    - Uses exact QuestionID match
    - Applies mapping above
    """
    if df is None or len(df) == 0:
        return 0
    if responses is None:
        return 0

    total = 0
    df_idx = df.set_index(df["QuestionID"].astype(str), drop=False)

    for r in responses:
        qid = str(r.get("QuestionID", "")).strip()
        raw = r.get("Response", "")

        if not qid or qid not in df_idx.index:
            continue

        row = df_idx.loc[qid]
        if str(row.get("Type", "")).lower() != "likert":
            continue

        try:
            val = int(raw)
            total += likert_to_score(val)
        except:
            continue

    return total


# ---------------------------------------------------------------
# AUTO-SCORE ALL TESTS FOR THIS STUDENT (IN-MEMORY ONLY)
# ---------------------------------------------------------------
def compute_auto_totals(doc_list: List[Tuple[str, Dict]]):
    total_mcq = 0
    total_likert = 0
    per_doc = {}

    for doc_id, data in doc_list:
        section = data.get("Section")
        df = question_banks.get(section, pd.DataFrame())
        responses = data.get("Responses") or []

        mcq = calc_mcq(df, responses)
        likert = calc_likert(df, responses)

        per_doc[doc_id] = (mcq, likert)
        total_mcq += mcq
        total_likert += likert

    return total_mcq, total_likert, per_doc

# ---------------------------------------------------------------
# MANUAL EVALUATION UI — FAST, NO AUTO CALCULATION
# ---------------------------------------------------------------

# Which manual tests exist for this student?
manual_tests_available = []
for doc_id, data in docs_for_roll:
    section = data.get("Section")
    if section in MANUAL_TESTS:
        manual_tests_available.append(section)

manual_tests_available = sorted(set(manual_tests_available))

if not manual_tests_available:
    st.info("This student has no manually evaluated tests.")
    st.subheader(f"Auto MCQ Score: {auto_mcq_total}")
    st.subheader(f"Auto Likert Score: {auto_likert_total}")
    st.stop()

# ---------------------------------------------
# Select the manual test to evaluate
# ---------------------------------------------
selected_test = st.selectbox("Select Test for Manual Evaluation", manual_tests_available)

# Find the document for this test
selected_doc_id = None
selected_doc_data = None
for doc_id, data in docs_for_roll:
    if data.get("Section") == selected_test:
        selected_doc_id = doc_id
        selected_doc_data = data
        break

df_test = question_banks.get(selected_test)
responses_test = selected_doc_data.get("Responses", [])
eval_saved = selected_doc_data.get("Evaluation", {})

saved_text_marks = eval_saved.get("text_marks", {})
saved_text_total = int(eval_saved.get("text_total", 0))

# ---------------------------------------------
# Build UI for short (descriptive) questions ONLY
# ---------------------------------------------
short_df = df_test[df_test["Type"].astype(str).str.lower() == "short"]

marks_given = {}
text_current_total = 0

st.markdown("## ✍️ Manual Text Evaluation")

if short_df.empty:
    st.info("No descriptive questions in this test.")
else:
    for _, row in short_df.iterrows():
        qid = str(row["QuestionID"])
        qtext = str(row["Question"])
        
        # get student's answer
        stu_ans = "(no answer)"
        for r in responses_test:
            if str(r.get("QuestionID")) == qid:
                stu_ans = str(r.get("Response", "(no answer)"))
                break

        # marking scale → using your QID lists
        scale = scale_for_qid(qid)

        # default = previously saved or 0
        default = saved_text_marks.get(qid, 0)
        if default not in scale:
            default = 0
        default_index = scale.index(default)

        # --------------------------------------
        # Expander (always expanded)
        # --------------------------------------
        with st.expander(f"Q{qid}: {qtext}", expanded=True):

            col1, col2 = st.columns([3, 1])

            with col1:
                st.markdown(f"**Student Answer:** {stu_ans}")

            with col2:
                mark = st.radio(
                    "Marks:",
                    scale,
                    index=default_index,
                    horizontal=True,
                    key=f"{selected_roll}_{selected_test}_{qid}"
                )

        marks_given[qid] = mark
        text_current_total += mark

st.markdown("---")
# ---------------------------------------------------------------
# CALCULATE BUTTON — FAST, NO AUTO-UPDATE
# ---------------------------------------------------------------
st.markdown("## 🧮 Calculate Marks (Preview Only)")

if st.button("📌 Calculate Marks"):
    try:
        # Recalculate MCQ & Likert ONLY for this test
        df_this = df_test
        responses_this = responses_test

        mcq_sel = calc_mcq(df_this, responses_this)
        likert_sel = calc_likert(df_this, responses_this)

        final_sel = mcq_sel + likert_sel + text_current_total

        st.success(
            f"""
### ✅ Marks Calculated (Preview)
**MCQ Score (This Test):** {mcq_sel}  
**Likert Score (This Test):** {likert_sel}  
**Text Score (This Test):** {text_current_total}  

### 👉 Final Score (This Test): **{final_sel}**
*(Not saved yet. Press “Save Evaluation for This Test” to store it.)*
"""
        )

    except Exception as e:
        st.error(f"❌ Error while calculating marks: {e}")

# ---------------------------------------------------------------
# SAVE BUTTON — FINAL GRAND TOTAL UPDATE
# ---------------------------------------------------------------
st.markdown("## 💾 Save Final Evaluation")

if st.button("💾 Save Evaluation for This Test"):
    try:
        # -----------------------------------------------------------
        # 1) Recompute MCQ, Likert, Text, Final for THIS TEST
        # -----------------------------------------------------------
        mcq_sel = calc_mcq(df_test, responses_test)
        likert_sel = calc_likert(df_test, responses_test)
        text_sel = text_current_total
        final_sel = mcq_sel + likert_sel + text_sel

        # Update Evaluation block for THIS TEST
        db.collection("student_responses").document(selected_doc_id).set(
            {
                "Evaluation": {
                    "text_marks": marks_given,
                    "text_total": text_sel,
                    "mcq_total": mcq_sel,
                    "likert_total": likert_sel,
                    "final_total": final_sel,
                }
            },
            merge=True,
        )

        # -----------------------------------------------------------
        # 2) Recompute GRAND TOTAL across ALL TESTS FOR THIS STUDENT
        # -----------------------------------------------------------
        new_grand_total = 0

        for doc_id, data in docs_for_roll:
            section = data.get("Section")
            df = question_banks.get(section, pd.DataFrame())
            responses = data.get("Responses", [])

            if doc_id == selected_doc_id:
                # this test uses the newly computed final_sel
                new_grand_total += final_sel
                continue

            # for other tests, use saved final_total if present
            ev = data.get("Evaluation", {})
            if "final_total" in ev:
                new_grand_total += int(ev.get("final_total", 0))
            else:
                # fallback auto-evaluate (rare)
                mcq_x = calc_mcq(df, responses)
                likert_x = calc_likert(df, responses)
                text_x = int(ev.get("text_total", 0))
                new_grand_total += mcq_x + likert_x + text_x

        # -----------------------------------------------------------
        # 3) Save grand_total to ALL documents of this student
        # -----------------------------------------------------------
        batch = db.batch()
        for doc_id, _ in docs_for_roll:
            ref = db.collection("student_responses").document(doc_id)
            batch.set(ref, {"Evaluation": {"grand_total": new_grand_total}}, merge=True)
        batch.commit()

        # -----------------------------------------------------------
        # 4) Popup confirmation
        # -----------------------------------------------------------
        st.success(
            f"""
### 🎉 Evaluation Saved Successfully!
**MCQ (This Test):** {mcq_sel}  
**Likert (This Test):** {likert_sel}  
**Text Marks:** {text_sel}  

### 👉 Final Score (This Test): **{final_sel}**  
### ⭐ Updated GRAND TOTAL (All Tests): **{new_grand_total}**

*(You may switch students or tests to continue.)*
"""
        )

    except Exception as e:
        st.error(f"❌ Error while saving evaluation: {e}")
