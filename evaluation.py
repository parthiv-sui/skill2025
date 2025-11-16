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
st.title("🧑‍🏫 Faculty Evaluation System")


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
    v = int(v)
    return v - 1   # 1→0, 2→1, 3→2, 4→3, 5→4


def calc_mcq(df, responses):
    total = 0
    for r in responses:
        qid = str(r["QuestionID"])
        ans = str(r["Response"]).strip()
        row_df = df[df["QuestionID"].astype(str) == qid]
        if row_df.empty:
            continue
        row = row_df.iloc[0]
        if row["Type"] != "mcq":
            continue
        correct = get_correct_answer(row)
        if correct and ans == correct:
            total += 1
    return total


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
        total += likert_to_score(ans)
    return total


def auto_evaluate_and_save(doc_id, df, responses):
    mcq = calc_mcq(df, responses)
    likert = calc_likert(df, responses)

    db.collection("student_responses").document(doc_id).set({
        "Evaluation": {
            "mcq_total": mcq,
            "likert_total": likert,
            "text_total": 0,
            "text_marks": {}
        }
    }, merge=True)

    return mcq, likert


def compute_grand_total(roll):
    total = 0
    for section, doc_id in student_map[roll]:
        doc = db.collection("student_responses").document(doc_id).get().to_dict()
        if doc and "Evaluation" in doc:
            ev = doc["Evaluation"]
            total += ev.get("mcq_total", 0)
            total += ev.get("likert_total", 0)
            total += ev.get("text_total", 0)
    return total


# ---------------------------------------------------------------
# READ STUDENT RESPONSES
# ---------------------------------------------------------------
docs = db.collection("student_responses").stream()
student_map = {}

for doc in docs:
    d = doc.to_dict()
    roll = d.get("Roll")
    section = d.get("Section")
    if roll is None or section is None:
        continue
    if roll not in student_map:
        student_map[roll] = []
    student_map[roll].append((section, doc.id))


# ---------------------------------------------------------------
# UI — SELECT STUDENT
# ---------------------------------------------------------------
all_students = sorted(student_map.keys())
selected_roll = st.selectbox("Select Student", all_students)


# ---------------------------------------------------------------
# AUTO-EVALUATE FOR MCQ + LIKERT TESTS
# ---------------------------------------------------------------
mcq_auto_sum = 0
likert_auto_sum = 0

for section, doc_id in student_map[selected_roll]:
    if section in AUTO_EVAL_TESTS:
        doc_data = db.collection("student_responses").document(doc_id).get().to_dict()
        df = question_banks[section]
        responses = doc_data["Responses"]
        mcq, likert = auto_evaluate_and_save(doc_id, df, responses)
        mcq_auto_sum += mcq
        likert_auto_sum += likert


# ---------------------------------------------------------------
# MANUAL TEST SELECTOR
# ---------------------------------------------------------------
tests_taken = [t[0] for t in student_map[selected_roll] if t[0] in MANUAL_EVAL_TESTS]

if len(tests_taken) == 0:
    st.success("All tests auto-evaluated.")
    grand = compute_grand_total(selected_roll)
    st.subheader(f"GRAND TOTAL (All Tests) = {grand}")
    st.stop()

selected_test = st.selectbox("Select Test for Manual Evaluation", tests_taken)

# Get document ID
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
# FACULTY TEXT MARK ENTRY
# ---------------------------------------------------------------
text_total = 0
marks_given = {}

st.markdown("### 📝 Manual Marking")

for _, row in short_df.iterrows():
    qid = str(row["QuestionID"])
    question = row["Question"]

    student_ans = next((x["Response"] for x in responses if str(x["QuestionID"]) == qid), "(no answer)")

    with st.expander(f"Q{qid}: {question}", expanded=False):
        st.markdown(f"**Student Answer:** {student_ans}")
        mark = st.radio("Marks:", [0, 1, 2, 3], horizontal=True, key=f"mark_{qid}")
        marks_given[qid] = mark
        text_total += mark


# ---------------------------------------------------------------
# TOTALS DISPLAY
# ---------------------------------------------------------------
grand_total = compute_grand_total(selected_roll)

st.subheader(f"MCQ Score (Auto): {mcq_auto_sum}")
st.subheader(f"Likert Score (Auto): {likert_auto_sum}")
st.subheader(f"Text Marks (This Test): {text_total}")

st.markdown("---")
final_grand = mcq_auto_sum + likert_auto_sum + text_total
st.subheader(f"GRAND TOTAL (All Tests) = {final_grand}")


# ---------------------------------------------------------------
# SAVE EVALUATION
# ---------------------------------------------------------------
if st.button("💾 Save Evaluation"):
    db.collection("student_responses").document(doc_id).set({
        "Evaluation": {
            "text_total": text_total,
            "text_marks": marks_given
        }
    }, merge=True)
    st.success("Saved Successfully!")
