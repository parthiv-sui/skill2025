import streamlit as st
import pandas as pd
import json
import firebase_admin
from firebase_admin import credentials, firestore

# ---------------------------------------------------------------
# FIREBASE INITIALIZATION
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

st.set_page_config(page_title="Faculty Evaluation", layout="wide")
st.title("🧑‍🏫 Faculty Evaluation – Text Questions")

# ---------------------------------------------------------------
# LOAD CSV FILES
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
    v = int(v)
    return v - 1   # 1→0, 2→1, 3→2, 4→3, 5→4

def calc_mcq(df, responses):
    score = 0
    for r in responses:
        qid = str(r["QuestionID"]).strip()
        student_ans = str(r["Response"]).strip()
        row_df = df[df["QuestionID"].astype(str).str.strip() == qid]
        if row_df.empty:
            continue
        row = row_df.iloc[0]
        if row["Type"] != "mcq":
            continue
        correct = get_correct_answer(row)
        if correct and student_ans == correct:
            score += 1
    return score

def calc_likert(df, responses):
    total = 0
    for r in responses:
        qid = str(r["QuestionID"]).strip()
        ans = r["Response"]
        row_df = df[df["QuestionID"].astype(str).str.strip() == qid]
        if row_df.empty:
            continue
        row = row_df.iloc[0]
        if row["Type"].lower() != "likert":
            continue
        total += likert_to_score(int(ans))
    return total

def auto_evaluate_test(section, doc_id, df, responses):
    mcq_total = calc_mcq(df, responses)
    likert_total = calc_likert(df, responses)
    final_total = mcq_total + likert_total

    db.collection("student_responses").document(doc_id).set({
        "Evaluation": {
            "mcq_total": mcq_total,
            "likert_total": likert_total,
            "text_total": 0,
            "text_marks": {},
            "final_total": final_total
        }
    }, merge=True)

    return final_total

# ---------------------------------------------------------------
# READ STUDENT RESPONSES
# ---------------------------------------------------------------
docs = db.collection("student_responses").stream()
student_map = {}

for doc in docs:
    data = doc.to_dict()
    roll = data.get("Roll")
    section = data.get("Section")
    if roll not in student_map:
        student_map[roll] = []
    student_map[roll].append((section, doc.id))

# ---------------------------------------------------------------
# BUILD STUDENT STATUS FOR DROPDOWN
# ---------------------------------------------------------------
def student_status(roll):
    sections = dict(student_map[roll])
    completed = 0

    for test in ALL_TESTS:
        if test in sections:
            doc = db.collection("student_responses").document(sections[test]).get().to_dict()
            eval_data = doc.get("Evaluation", {})
            if "final_total" in eval_data:
                completed += 1

    if completed == len(ALL_TESTS):
        return "✅ Completed"
    elif completed == 0:
        return "❌ Not Started"
    else:
        return "⏳ Partial"

# dropdown values
student_choices = [
    f"{roll} — {student_status(roll)}"
    for roll in sorted(student_map.keys())
]

selected_display = st.selectbox("Select Student", student_choices)
selected_roll = selected_display.split("—")[0].strip()

# ---------------------------------------------------------------
# AUTO-EVALUATE NECESSARY TESTS
# ---------------------------------------------------------------
for section, doc_id in student_map[selected_roll]:
    if section in AUTO_EVAL_TESTS:
        doc_data = db.collection("student_responses").document(doc_id).get().to_dict()
        df = question_banks[section]
        responses = doc_data["Responses"]
        auto_evaluate_test(section, doc_id, df, responses)

# ---------------------------------------------------------------
# MANUAL TEST SELECTION
# ---------------------------------------------------------------
tests_taken = [
    sec for sec, doc_id in student_map[selected_roll]
    if sec in MANUAL_EVAL_TESTS
]

selected_test = st.selectbox("Select Manual Evaluation Test", tests_taken)

# Get that doc
doc_id = dict(student_map[selected_roll])[selected_test]
doc_data = db.collection("student_responses").document(doc_id).get().to_dict()
responses = doc_data["Responses"]
df = question_banks[selected_test]
short_df = df[df["Type"] == "short"]

# ---------------------------------------------------------------
# SESSION STATE FOR UNSAVED MARKS
# ---------------------------------------------------------------
if "pending_marks" not in st.session_state:
    st.session_state["pending_marks"] = {}

if selected_test not in st.session_state["pending_marks"]:
    st.session_state["pending_marks"][selected_test] = {}

pending = st.session_state["pending_marks"][selected_test]

# ---------------------------------------------------------------
# MANUAL TEXT EVALUATION UI
# ---------------------------------------------------------------
marks_given = {}
text_total = 0

for _, row in short_df.iterrows():
    qid = str(row["QuestionID"])
    qtext = str(row["Question"])
    student_ans = next(
        (r["Response"] for r in responses if str(r["QuestionID"]) == qid),
        "(no answer)"
    )

    # scale logic
    qlower = qtext.lower()
    is_three_point = (" 3 " in qlower) or ("three" in qlower)
    scale = [0, 1, 2, 3] if is_three_point else [0, 1]

    # prefill pending value
    default = pending.get(qid, 0)

    with st.expander(f"Q{qid}: {qtext}", expanded=True):
        colA, colB = st.columns([3, 1])
        with colA:
            st.markdown(f"**Student Answer:** {student_ans}")
        with colB:
            mark = st.radio(
                "Marks:",
                scale,
                horizontal=True,
                index=scale.index(default),
                key=f"{selected_test}_{qid}"
            )

    pending[qid] = mark
    marks_given[qid] = mark
    text_total += mark

# ---------------------------------------------------------------
# AUTO SCORES FOR DISPLAY
# ---------------------------------------------------------------
global_mcq = 0
global_likert = 0

for sec, did in student_map[selected_roll]:
    doc = db.collection("student_responses").document(did).get().to_dict()
    eval_data = doc.get("Evaluation", {})
    global_mcq += eval_data.get("mcq_total", 0)
    global_likert += eval_data.get("likert_total", 0)

# ---------------------------------------------------------------
# DISPLAY SCORES
# ---------------------------------------------------------------
st.subheader(f"MCQ Score (Auto): {global_mcq}")
st.subheader(f"Likert Score (Auto): {global_likert}")
st.subheader(f"Text Marks (This Test): {text_total}")

grand_total = global_mcq + global_likert + text_total
st.subheader(f"GRAND TOTAL (All Tests) = {grand_total}")

# ---------------------------------------------------------------
# SAVE BUTTON
# ---------------------------------------------------------------
if st.button("💾 Save Evaluation"):
    db.collection("student_responses").document(doc_id).set({
        "Evaluation": {
            "text_marks": marks_given,
            "text_total": text_total,
            "final_total": global_mcq + global_likert + text_total
        }
    }, merge=True)

    # propagate to all tests
    for sec, did in student_map[selected_roll]:
        db.collection("student_responses").document(did).set({
            "Evaluation": {"grand_total": grand_total}
        }, merge=True)

    # clear pending marks
    st.session_state["pending_marks"][selected_test] = {}

    st.success("Evaluation Saved Successfully ✓")
