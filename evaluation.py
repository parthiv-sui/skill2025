import streamlit as st
import pandas as pd
import json
import firebase_admin
from firebase_admin import credentials, firestore

# ---------------------------------------------------------------
# FIREBASE INIT
# ---------------------------------------------------------------
@st.cache_resource
def init_firebase():
    if firebase_admin._apps:
        return firestore.client()
    try:
        if "firebase" in st.secrets:
            cfg = dict(st.secrets["firebase"])
            cred = credentials.Certificate(cfg)
            firebase_admin.initialize_app(cred)
        else:
            with open("firebase_key.json", "r") as f:
                cfg = json.load(f)
            cred = credentials.Certificate(cfg)
            firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Firebase initialization failed: {e}")
        return None
    return firestore.client()


db = init_firebase()
if db is None:
    st.stop()

# ---------------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------------
st.set_page_config(page_title="Faculty Evaluation", layout="wide")
st.title("🧑‍🏫 Faculty Evaluation – Text Questions")

# ---------------------------------------------------------------
# LOAD QUESTION BANKS
# ---------------------------------------------------------------
@st.cache_data
def load_questions():
    return {
        "Aptitude Test": pd.read_csv("aptitude.csv"),
        "Adaptability & Learning": pd.read_csv("adaptability_learning.csv"),
        "Communication Skills - Objective": pd.read_csv("communication_skills_objective.csv"),
        "Communication Skills - Descriptive": pd.read_csv("communication_skills_descriptive.csv"),
    }


question_banks = load_questions()

AUTO_EVAL_TESTS = [
    "Adaptability & Learning",
    "Communication Skills - Objective",
]

MANUAL_EVAL_TESTS = [
    "Aptitude Test",
    "Communication Skills - Descriptive",
]

ALL_TESTS = AUTO_EVAL_TESTS + MANUAL_EVAL_TESTS

# ---------------------------------------------------------------
# SCORING HELPERS
# ---------------------------------------------------------------
def get_correct_answer(row):
    for col in ["Answer", "CorrectAnswer", "Correct", "Ans", "AnswerKey"]:
        if col in row and not pd.isna(row[col]):
            return str(row[col]).strip()
    return None


def likert_to_score(v):
    try:
        v = int(v)
    except Exception:
        return 0
    # 1→0, 2→1, 3→2, 4→3, 5→4
    return max(0, v - 1)


def calc_mcq(df, responses):
    total = 0
    for r in responses:
        qid = str(r.get("QuestionID", "")).strip()
        ans = str(r.get("Response", "")).strip()
        row_df = df[df["QuestionID"].astype(str).str.strip() == qid]
        if row_df.empty:
            continue
        row = row_df.iloc[0]
        if str(row["Type"]).strip().lower() != "mcq":
            continue
        correct = get_correct_answer(row)
        if correct and ans == correct:
            total += 1
    return total


def calc_likert(df, responses):
    total = 0
    for r in responses:
        qid = str(r.get("QuestionID", "")).strip()
        ans = r.get("Response", None)
        row_df = df[df["QuestionID"].astype(str).str.strip() == qid]
        if row_df.empty:
            continue
        row = row_df.iloc[0]
        if str(row["Type"]).strip().lower() != "likert":
            continue
        total += likert_to_score(ans)
    return total


# ---------------------------------------------------------------
# BUILD STUDENT MAP
# ---------------------------------------------------------------
docs = db.collection("student_responses").stream()
student_map = {}          # roll -> list of (section, doc_id)
doc_cache = {}            # doc_id -> dict

for d in docs:
    data = d.to_dict()
    doc_cache[d.id] = data
    roll = data.get("Roll")
    section = data.get("Section")
    if not roll or not section:
        continue
    if roll not in student_map:
        student_map[roll] = []
    student_map[roll].append((section, d.id))

if not student_map:
    st.error("No student_responses documents found.")
    st.stop()

# ---------------------------------------------------------------
# SELECT STUDENT
# ---------------------------------------------------------------
all_rolls = sorted(student_map.keys())
selected_roll = st.selectbox("Select Student Roll Number", all_rolls)

# ---------------------------------------------------------------
# PRECOMPUTE PER-TEST INFO FOR THIS STUDENT
# ---------------------------------------------------------------
per_section_info = {}   # section -> dict with mcq, likert, short_df, text_marks, etc.
total_mcq = 0
total_likert = 0
section_text_totals = {}   # section -> text_total (from session_state + saved)

for section, doc_id in student_map[selected_roll]:
    data = doc_cache.get(doc_id) or db.collection("student_responses").document(doc_id).get().to_dict()
    doc_cache[doc_id] = data
    responses = data.get("Responses", [])

    df = question_banks[section]

    # Auto MCQ + Likert from CSV + responses
    mcq_score = calc_mcq(df, responses)
    likert_score = calc_likert(df, responses)
    total_mcq += mcq_score
    total_likert += likert_score

    # Short questions for this test
    short_df = df[df["Type"].astype(str).str.lower() == "short"]

    # Saved marks from Firestore (if any)
    saved_eval = data.get("Evaluation", {})
    saved_marks = saved_eval.get("text_marks", {}) or {}

    text_marks_this_section = {}
    text_total_this_section = 0

    for _, row in short_df.iterrows():
        qid = str(row["QuestionID"])
        key = f"{selected_roll}__{section}__{qid}"

        if key in st.session_state:
            mark = st.session_state[key]
        elif qid in saved_marks:
            # convert to int safely
            try:
                mark = int(saved_marks[qid])
            except Exception:
                mark = 0
            st.session_state[key] = mark
        else:
            mark = 0
            st.session_state.setdefault(key, 0)

        text_marks_this_section[qid] = mark
        text_total_this_section += mark

    per_section_info[section] = {
        "doc_id": doc_id,
        "df": df,
        "responses": responses,
        "mcq": mcq_score,
        "likert": likert_score,
        "short_df": short_df,
        "text_marks": text_marks_this_section,
    }
    section_text_totals[section] = text_total_this_section

# ---------------------------------------------------------------
# SELECT TEST FOR MANUAL EVALUATION
# ---------------------------------------------------------------
tests_taken = [sec for sec, _ in student_map[selected_roll] if sec in MANUAL_EVAL_TESTS]

if not tests_taken:
    st.success("All tests for this student are auto-evaluated (no short questions).")
    grand_total_all = total_mcq + total_likert + sum(section_text_totals.values())
    st.subheader(f"GRAND TOTAL (All Tests) = {grand_total_all}")
    st.stop()

selected_test = st.selectbox("Select Test for Manual Evaluation", tests_taken)

info = per_section_info[selected_test]
short_df = info["short_df"]
responses = info["responses"]

# ---------------------------------------------------------------
# MANUAL TEXT EVALUATION UI (for selected_test)
# ---------------------------------------------------------------
marks_given = {}
text_total_this_test = 0

st.markdown(f"### Manual Evaluation – {selected_test}")

for _, row in short_df.iterrows():
    qid = str(row["QuestionID"])
    qtext = str(row["Question"])
    student_ans = next(
        (r.get("Response", "") for r in responses if str(r.get("QuestionID", "")) == qid),
        "(no answer)"
    )

    # Decide 0/1 or 0–3 scale based on question text
    qlower = qtext.lower()
    is_three_point = (" 3 " in qlower) or ("three" in qlower) or ("any 3" in qlower)
    scale = [0, 1, 2, 3] if is_three_point else [0, 1]

    key = f"{selected_roll}__{selected_test}__{qid}"
    current_default = st.session_state.get(key, 0)
    # ensure default is valid in scale
    if current_default not in scale:
        current_default = 0
        st.session_state[key] = 0

    with st.expander(f"{qid}: {qtext}", expanded=True):
        colA, colB = st.columns([3, 1])
        with colA:
            st.markdown(f"**Student Answer:** {student_ans}")
        with colB:
            # Initialize session_state key if needed
            if key not in st.session_state:
                st.session_state[key] = current_default
            mark = st.radio(
                "Marks:",
                scale,
                horizontal=True,
                key=key
            )

    mark_value = st.session_state[key]
    marks_given[qid] = mark_value
    text_total_this_test += mark_value

# Update section_text_totals for this test with current UI values
section_text_totals[selected_test] = text_total_this_test

# Recompute grand total text across all tests from section_text_totals
total_text_all_tests = sum(section_text_totals.values())

# ---------------------------------------------------------------
# DISPLAY TOTALS
# ---------------------------------------------------------------
st.markdown("---")
st.subheader(f"MCQ Score (Auto): {total_mcq}")
st.subheader(f"Likert Score (Auto): {total_likert}")
st.subheader(f"Text Marks (This Test): {text_total_this_test}")

grand_total_all = total_mcq + total_likert + total_text_all_tests
st.subheader(f"GRAND TOTAL (All Tests) = {grand_total_all}")

# ---------------------------------------------------------------
# SAVE BUTTON – saves ONLY the selected_test text marks
# ---------------------------------------------------------------
if st.button("💾 Save Evaluation for this Test"):
    # Build text_marks for this test from session_state
    text_marks_to_save = {}
    for _, row in short_df.iterrows():
        qid = str(row["QuestionID"])
        key = f"{selected_roll}__{selected_test}__{qid}"
        text_marks_to_save[qid] = int(st.session_state.get(key, 0))

    doc_id = info["doc_id"]
    db.collection("student_responses").document(doc_id).set({
        "Evaluation": {
            "text_marks": text_marks_to_save,
            "text_total": int(text_total_this_test),
        }
    }, merge=True)

    st.success("Evaluation saved for this test ✔")
