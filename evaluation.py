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
# STREAMLIT CONFIG
# ---------------------------------------------------------------
st.set_page_config(page_title="Faculty Evaluation", layout="wide")
st.title("🧑‍🏫 Faculty Evaluation")


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
    "Communication Skills - Objective"
]

MANUAL_EVAL_TESTS = [
    "Aptitude Test",
    "Communication Skills - Descriptive"
]

ALL_TESTS = AUTO_EVAL_TESTS + MANUAL_EVAL_TESTS


# ---------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------
def get_correct_answer(row):
    for col in ["Answer", "Correct", "CorrectAnswer", "Ans", "AnswerKey"]:
        if col in row and not pd.isna(row[col]):
            return str(row[col]).strip()
    return None


def likert_to_score(val):
    try:
        val = int(val)
        return val - 1    # 1→0, 2→1, 3→2, 4→3, 5→4
    except:
        return 0


def calc_mcq(df, responses):
    total = 0
    for r in responses:
        qid = str(r["QuestionID"])
        ans = str(r["Response"]).strip()

        row_df = df[df["QuestionID"].astype(str) == qid]
        if row_df.empty:
            continue

        row = row_df.iloc[0]
        if row["Type"].strip().lower() != "mcq":
            continue

        correct = get_correct_answer(row)
        if correct and ans == correct:
            total += 1

    return total


def calc_likert(df, responses):
    total = 0
    for r in responses:
        qid = str(r["QuestionID"]).strip()
        ans = r["Response"]

        row_df = df[df["QuestionID"].astype(str).str.strip() == qid]
        if row_df.empty:
            continue

        row = row_df.iloc[0]
        if row["Type"].strip().lower() != "likert":
            continue

        total += likert_to_score(ans)

    return total


def auto_evaluate(section, doc_id, df, responses):
    mcq = calc_mcq(df, responses)
    likert = calc_likert(df, responses)
    final_total = mcq + likert

    db.collection("student_responses").document(doc_id).set({
        "Evaluation": {
            "mcq_total": mcq,
            "likert_total": likert,
            "text_total": 0,
            "text_marks": {},
            "final_total": final_total
        }
    }, merge=True)

    return final_total


def compute_grand_total(roll):
    total = 0
    for _, doc_id in student_map[roll]:
        d = db.collection("student_responses").document(doc_id).get().to_dict()
        if d and "Evaluation" in d and "final_total" in d["Evaluation"]:
            total += d["Evaluation"]["final_total"]
    return total


def save_grand_total(roll, total):
    for _, doc_id in student_map[roll]:
        db.collection("student_responses").document(doc_id).set({
            "Evaluation": {"grand_total": total}
        }, merge=True)


# ---------------------------------------------------------------
# LOAD STUDENT RESPONSE MAP
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
# STUDENT DROPDOWN WITH ✓ / ✗ STATUS
# ---------------------------------------------------------------
status_list = []
for roll in sorted(student_map.keys()):
    eval_done = True
    for sec, d_id in student_map[roll]:
        d = db.collection("student_responses").document(d_id).get().to_dict()
        if "Evaluation" not in d:
            eval_done = False
            break
    symbol = "✓" if eval_done else "✗"
    status_list.append(f"{symbol}  {roll}")

selected_display = st.selectbox("Select Student", status_list)
selected_roll = selected_display.split()[-1]


# ---------------------------------------------------------------
# AUTO-EVALUATE MCQ + LIKERT
# ---------------------------------------------------------------
for section, doc_id in student_map[selected_roll]:
    if section in AUTO_EVAL_TESTS:
        doc_data = db.collection("student_responses").document(doc_id).get().to_dict()
        df = question_banks[section]
        auto_evaluate(section, doc_id, df, doc_data["Responses"])


# ---------------------------------------------------------------
# LIST ONLY MANUAL TESTS FOR MARK ENTRY
# ---------------------------------------------------------------
tests_taken = [
    sec for sec, _ in student_map[selected_roll]
    if sec in MANUAL_EVAL_TESTS
]

if not tests_taken:
    st.success("All tests are fully auto-evaluated ✓")
    total = compute_grand_total(selected_roll)
    st.subheader(f"GRAND TOTAL = {total}")
    st.stop()

selected_test = st.selectbox("Select Test for Manual Evaluation", tests_taken)


# ---------------------------------------------------------------
# LOAD SELECTED TEST
# ---------------------------------------------------------------
doc_id = None
for sec, d in student_map[selected_roll]:
    if sec == selected_test:
        doc_id = d
        break

doc_data = db.collection("student_responses").document(doc_id).get().to_dict()
df = question_banks[selected_test]
responses = doc_data["Responses"]
short_df = df[df["Type"].str.lower() == "short"]


# ---------------------------------------------------------------
# MANUAL TEXT EVALUATION
# ---------------------------------------------------------------
marks_given = {}
text_total = 0

for _, row in short_df.iterrows():
    qid = str(row["QuestionID"])
    qtext = row["Question"]

    student_ans = next(
        (r["Response"] for r in responses if str(r["QuestionID"]) == qid),
        "(no answer)"
    )

    scale = [0, 1, 2, 3] if "3" in qtext.lower() else [0, 1]

    with st.expander(f"{qid}: {qtext}", expanded=True):
        colA, colB = st.columns([3, 1])

        with colA:
            st.markdown(f"**Student Answer:** {student_ans}")

        with colB:
            mark = st.radio(
                "Marks:",
                scale,
                horizontal=True,
                key=f"mark_{selected_test}_{qid}"
            )

        marks_given[qid] = mark
        text_total += mark


# ---------------------------------------------------------------
# DISPLAY TOTALS
# ---------------------------------------------------------------
mcq_total = 0
likert_total = 0

for sec, d_id in student_map[selected_roll]:
    if sec in AUTO_EVAL_TESTS:
        d = db.collection("student_responses").document(d_id).get().to_dict()
        mcq_total += d["Evaluation"]["mcq_total"]
        likert_total += d["Evaluation"]["likert_total"]

st.subheader(f"MCQ Score (Auto): {mcq_total}")
st.subheader(f"Likert Score (Auto): {likert_total}")
st.subheader(f"Text Marks (This Test): {text_total}")

updated_total = (
    compute_grand_total(selected_roll)
    - doc_data.get("Evaluation", {}).get("text_total", 0)
    + text_total
)

st.subheader(f"GRAND TOTAL (All Tests) = {updated_total}")


# ---------------------------------------------------------------
# SAVE BUTTON
# ---------------------------------------------------------------
if st.button("💾 Save Evaluation"):
    db.collection("student_responses").document(doc_id).set({
        "Evaluation": {
            "text_marks": marks_given,
            "text_total": text_total,
            "mcq_total": mcq_total,
            "likert_total": likert_total,
            "final_total": mcq_total + likert_total + text_total
        }
    }, merge=True)

    save_grand_total(selected_roll, updated_total)
    st.success("Saved Successfully ✓")
