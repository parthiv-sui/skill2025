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

# Which tests are auto vs manual
AUTO_EVAL_TESTS = [
    "Adaptability & Learning",
    "Communication Skills - Objective",
]

MANUAL_EVAL_TESTS = [
    "Aptitude Test",
    "Communication Skills - Descriptive",
]

ALL_TESTS = [
    "Aptitude Test",
    "Adaptability & Learning",
    "Communication Skills - Objective",
    "Communication Skills - Descriptive",
]

# ---------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------
def get_correct_answer(row):
    for col in ["Answer", "CorrectAnswer", "Correct", "Ans", "AnswerKey", "RightAnswer"]:
        if col in row and not pd.isna(row[col]):
            return str(row[col]).strip()
    return None


def likert_to_score(v):
    # Scoring: 1->0, 2->1, 3->2, 4->3, 5->4
    v = int(v)
    return max(0, min(v - 1, 4))


def calc_mcq(df, responses):
    score = 0
    for r in responses:
        qid = str(r["QuestionID"])
        student_ans = str(r["Response"]).strip()
        row_df = df[df["QuestionID"].astype(str) == qid]
        if row_df.empty:
            continue
        row = row_df.iloc[0]
        if str(row["Type"]).lower() != "mcq":
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
        if str(row["Type"]).lower() != "likert":
            continue
        try:
            total += likert_to_score(int(ans))
        except:
            total += 0
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


# ---------------------------------------------------------------
# READ STUDENT RESPONSE DOCS
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
# UI – SELECT STUDENT
# ---------------------------------------------------------------
all_students = sorted(student_map.keys())
selected_roll = st.selectbox("Select Student Roll Number", all_students)

# ---------------------------------------------------------------
# AUTO-EVALUATE MCQ + LIKERT TESTS
# ---------------------------------------------------------------
for section, doc_id in student_map[selected_roll]:
    if section in AUTO_EVAL_TESTS:
        doc_data = db.collection("student_responses").document(doc_id).get().to_dict()
        df = question_banks[section]
        responses = doc_data["Responses"]
        auto_evaluate_test(section, doc_id, df, responses)

# ---------------------------------------------------------------
# GLOBAL MCQ + LIKERT TOTALS (AUTO)
# ---------------------------------------------------------------
global_mcq = 0
global_likert = 0

for section, doc_id in student_map[selected_roll]:
    doc_data = db.collection("student_responses").document(doc_id).get().to_dict()
    if "Evaluation" in doc_data:
        global_mcq += doc_data["Evaluation"].get("mcq_total", 0)
        global_likert += doc_data["Evaluation"].get("likert_total", 0)

# ---------------------------------------------------------------
# MANUAL TEST SELECTION
# ---------------------------------------------------------------
tests_taken = [t[0] for t in student_map[selected_roll] if t[0] in MANUAL_EVAL_TESTS]

selected_test = st.selectbox("Select Test for Manual Evaluation", tests_taken)

doc_id = None
for sec, d_id in student_map[selected_roll]:
    if sec == selected_test:
        doc_id = d_id
        break

doc_data = db.collection("student_responses").document(doc_id).get().to_dict()
df = question_banks[selected_test]
responses = doc_data["Responses"]
short_df = df[df["Type"] == "short"]

# ---------------------------------------------------------------
# FACULTY TEXT EVALUATION (WITH CORRECT MARK SCALES)
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

    # ✅ IMPORTANT: decide marking scale
    # If question asks for 3 points (contains "3" or "three"), give 0–3.
    # Otherwise simple factual question → 0–1.
    qlower = qtext.lower()
    is_three_point = (" 3 " in qlower) or ("three" in qlower) or ("any 3" in qlower) or ("three points" in qlower)
    scale = [0, 1, 2, 3] if is_three_point else [0, 1]

    with st.expander(f"Q{qid}: {qtext}", expanded=True):
        colA, colB = st.columns([3, 1])
        with colA:
            st.markdown(f"**Student Answer:** {student_ans}")
        with colB:
            mark = st.radio("Marks:", scale, horizontal=True, key=f"mark_{qid}")

        marks_given[qid] = mark
        text_total += mark

st.markdown("---")

# ---------------------------------------------------------------
# FINAL DISPLAY (AUTO + TEXT + GRAND TOTAL)
# ---------------------------------------------------------------
st.subheader(f"MCQ Score (Auto): {global_mcq}")
st.subheader(f"Likert Score (Auto): {global_likert}")
st.subheader(f"Text Marks (This Test): {text_total}")

grand_total = global_mcq + global_likert + text_total
st.subheader(f"GRAND TOTAL (All Tests) = {grand_total}")

# ---------------------------------------------------------------
# SAVE EVALUATION
# ---------------------------------------------------------------
if st.button("💾 Save Evaluation"):
    db.collection("student_responses").document(doc_id).set({
        "Evaluation": {
            "text_marks": marks_given,
            "text_total": text_total,
            "grand_total": grand_total
        }
    }, merge=True)

    st.success("Evaluation + Grand Total Saved Successfully ✓")
