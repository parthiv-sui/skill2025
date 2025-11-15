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


# ---------------------------------------------------------------
# TEST CATEGORIES
# ---------------------------------------------------------------
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


def likert_to_score(v):  # MODEL 3
    v = int(v)
    if v == 1: return 0
    if v == 2: return 1
    if v == 3: return 2
    if v in [4, 5]: return 3
    return 0


def calc_mcq(df, responses):
    score = 0
    for r in responses:
        qid = str(r["QuestionID"])
        student_ans = str(r["Response"]).strip()
        row_df = df[df["QuestionID"].astype(str) == qid]
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
        qid = str(r["QuestionID"])
        ans = r["Response"]
        row_df = df[df["QuestionID"].astype(str) == qid]
        if row_df.empty:
            continue
        row = row_df.iloc[0]
        if row["Type"] != "likert":
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

    return final_total


def compute_grand_total(roll):
    total = 0
    for section_name in ALL_TESTS:
        for section, doc_id in student_map[roll]:
            if section == section_name:
                doc = db.collection("student_responses").document(doc_id).get().to_dict()
                if doc and "Evaluation" in doc and "final_total" in doc["Evaluation"]:
                    total += doc["Evaluation"]["final_total"]
    return total


def save_grand_total_to_all_tests(roll, grand_total):
    for section, doc_id in student_map[roll]:
        db.collection("student_responses").document(doc_id).set({
            "Evaluation": {
                "grand_total": grand_total
            }
        }, merge=True)


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
# UI: SELECT STUDENT
# ---------------------------------------------------------------
all_students = sorted(student_map.keys())
selected_roll = st.selectbox("Select Student Roll Number", all_students)


# ---------------------------------------------------------------
# ALWAYS AUTO-EVALUATE MCQ + LIKERT TESTS
# ---------------------------------------------------------------
for section, doc_id in student_map[selected_roll]:
    if section in AUTO_EVAL_TESTS:
        doc_data = db.collection("student_responses").document(doc_id).get().to_dict()
        df = question_banks[section]
        responses = doc_data["Responses"]
        auto_evaluate_test(section, doc_id, df, responses)


# ---------------------------------------------------------------
# FILTER ONLY MANUAL EVALUATION TESTS
# ---------------------------------------------------------------
tests_taken = [
    t[0] for t in student_map[selected_roll]
    if t[0] in MANUAL_EVAL_TESTS
]

if len(tests_taken) == 0:
    st.success("All tests auto-evaluated ✓")
    grand_total = compute_grand_total(selected_roll)
    st.subheader(f"GRAND TOTAL (All Tests) = {grand_total}")
    st.stop()

selected_test = st.selectbox("Select Test for Manual Evaluation", tests_taken)


# FIND DOCUMENT FOR SELECTED TEST
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
# FACULTY TEXT EVALUATION
# ---------------------------------------------------------------
marks_given = {}
text_total = 0

for _, row in short_df.iterrows():
    qid = str(row["QuestionID"])
    qtext = row["Question"]
    student_ans = next((r["Response"] for r in responses if str(r["QuestionID"]) == qid), "(no answer)")

    scale = [0, 1, 2, 3] if "3" in qtext.lower() else [0, 1]

    with st.expander(f"Q{qid}: {qtext}", expanded=True):
        colA, colB = st.columns([3, 1])
        with colA:
            st.markdown(f"**Student Answer:** {student_ans}")
        with colB:
            mark = st.radio("Marks:", scale, horizontal=True, key=f"mark_{qid}")
        marks_given[qid] = mark
        text_total += mark


st.markdown("---")
st.subheader(f"Text Marks (This Test) = {text_total}")

mcq_total = calc_mcq(df, responses)
likert_total = calc_likert(df, responses)
final_total = mcq_total + likert_total + text_total

st.write(f"MCQ Score = {mcq_total}")
st.write(f"Likert Score = {likert_total}")
st.subheader(f"FINAL TOTAL (This Test) = {final_total}")

# GRAND TOTAL
previous_total = compute_grand_total(selected_roll)
grand_total = previous_total - doc_data.get("Evaluation", {}).get("final_total", 0) + final_total

st.subheader(f"GRAND TOTAL (All Tests) = {grand_total}")


# SAVE
if st.button("💾 Save Evaluation"):
    db.collection("student_responses").document(doc_id).set({
        "Evaluation": {
            "text_marks": marks_given,
            "text_total": text_total,
            "mcq_total": mcq_total,
            "likert_total": likert_total,
            "final_total": final_total,
            "grand_total": grand_total
        }
    }, merge=True)

    save_grand_total_to_all_tests(selected_roll, grand_total)
    st.success("Evaluation + Grand Total Saved Successfully ✓")
