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
        else:
            with open("firebase_key.json", "r") as f:
                cfg = json.load(f)

        cred = credentials.Certificate(cfg)
        firebase_admin.initialize_app(cred)
        return firestore.client()

    except Exception as e:
        st.error(f"Firebase Init Failed: {e}")
        return None


db = init_firebase()
if db is None:
    st.stop()

# ---------------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------------
st.set_page_config(page_title="Faculty Evaluation", layout="wide")
st.title("🧑‍🏫 Faculty Evaluation Dashboard")

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
# FETCH ALL STUDENT DOCUMENTS
# ---------------------------------------------------------------
docs = db.collection("student_responses").stream()

student_map = {}
for doc in docs:
    data = doc.to_dict()
    roll = data.get("Roll")
    section = data.get("Section")
    if roll:
        student_map.setdefault(roll, []).append((section, doc.id))

all_students = sorted(student_map.keys())

# ---------------------------------------------------------------
# SELECT STUDENT
# ---------------------------------------------------------------
st.subheader("Select Student")

def is_evaluated(doc_id):
    d = db.collection("student_responses").document(doc_id).get().to_dict()
    return d and "Evaluation" in d

def student_label(roll):
    marks_done = sum(
        1 for section, doc_id in student_map[roll]
        if is_evaluated(doc_id)
    )
    total = len(student_map[roll])
    return f"{roll}   ({marks_done}/{total} evaluated)"

selected_roll = st.selectbox(
    "Choose Roll Number",
    all_students,
    format_func=student_label
)

# ---------------------------------------------------------------
# AUTO EVALUATION FOR MCQ + LIKERT
# ---------------------------------------------------------------
def get_correct_answer(row):
    for c in ["Answer", "CorrectAnswer", "Correct", "Ans", "AnswerKey"]:
        if c in row and pd.notna(row[c]):
            return str(row[c]).strip()
    return None

def likert_to_score(v):
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
        if correct == student_ans:
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

        if row["Type"].lower().strip() != "likert":
            continue

        try:
            total += likert_to_score(ans)
        except:
            pass

    return total

# Run auto-eval for all MCQ/Likert tests (fast + clean)
for section, doc_id in student_map[selected_roll]:
    if section in AUTO_EVAL_TESTS:
        doc = db.collection("student_responses").document(doc_id).get().to_dict()
        df = question_banks[section]
        responses = doc.get("Responses", [])

        mcq = calc_mcq(df, responses)
        likert = calc_likert(df, responses)

        db.collection("student_responses").document(doc_id).set({
            "Evaluation": {
                "mcq_total": mcq,
                "likert_total": likert,
            }
        }, merge=True)

# ---------------------------------------------------------------
# SELECT MANUAL TEST (APTITUDE / DESCRIPTIVE)
# ---------------------------------------------------------------
tests_taken = [
    sec for sec, _ in student_map[selected_roll]
    if sec in MANUAL_EVAL_TESTS
]

if not tests_taken:
    st.success("All tests auto-evaluated ✓")
    st.stop()

def section_label(section):
    # Show if evaluated
    doc_id = [d for s, d in student_map[selected_roll] if s == section][0]
    return f"{section}   ({'✔' if is_evaluated(doc_id) else '✖'})"

selected_test = st.selectbox(
    "Select Test for Manual Evaluation",
    tests_taken,
    format_func=section_label
)

# ---------------------------------------------------------------
# MANUAL MARK ENTRY
# ---------------------------------------------------------------
doc_id = [d for s, d in student_map[selected_roll] if s == selected_test][0]
doc = db.collection("student_responses").document(doc_id).get().to_dict()

df = question_banks[selected_test]
responses = doc.get("Responses", [])

short_df = df[df["Type"] == "short"]

st.subheader(f"Manual Evaluation – {selected_test}")

marks_given = {}
text_total_display = 0

for _, row in short_df.iterrows():
    qid = str(row["QuestionID"])
    qtext = row["Question"]

    student_ans = next(
        (r["Response"] for r in responses if str(r["QuestionID"]) == qid),
        "(no answer)"
    )

    # AUTO-DETECT SCALE (This is your ORIGINAL rule)
    if "3" in qtext.lower():
        scale = [0, 1, 2, 3]
    else:
        scale = [0, 1]

    with st.expander(f"Q{qid}: {qtext}", expanded=True):
        st.markdown(f"**Student Answer:** {student_ans}")
        mark = st.radio("Marks:", scale, horizontal=True, key=f"mark_{selected_test}_{qid}")
        marks_given[qid] = mark
        text_total_display += mark

# ---------------------------------------------------------------
# SHOW AUTO SCORES + TEXT MARKS + GRAND TOTAL
# ---------------------------------------------------------------
st.markdown("---")

# COMPUTE mcq + likert total across ALL TESTS
def compute_auto_totals(roll):
    mcq_sum = 0
    likert_sum = 0
    for section, docid in student_map[roll]:
        data = db.collection("student_responses").document(docid).get().to_dict()
        if not data or "Evaluation" not in data:
            continue
        ev = data["Evaluation"]
        mcq_sum += ev.get("mcq_total", 0)
        likert_sum += ev.get("likert_total", 0)
    return mcq_sum, likert_sum

mcq_total, likert_total = compute_auto_totals(selected_roll)

st.write(f"**MCQ Score (Auto): {mcq_total}**")
st.write(f"**Likert Score (Auto): {likert_total}**")
st.write(f"**Text Marks (This Test): {text_total_display}**")

grand_total = mcq_total + likert_total + text_total_display

st.subheader(f"GRAND TOTAL (All Tests) = {grand_total}")

# ---------------------------------------------------------------
# SAVE TO FIRESTORE
# ---------------------------------------------------------------
if st.button("💾 Save Evaluation for this Test"):
    db.collection("student_responses").document(doc_id).set({
        "Evaluation": {
            "text_marks": marks_given,
            "text_total": text_total_display
        }
    }, merge=True)

    st.success("Saved Successfully ✓")
