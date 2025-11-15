import streamlit as st
import pandas as pd
import json
import firebase_admin
from firebase_admin import credentials, firestore

# ---------------------------------------------------------------
#                FIREBASE INITIALIZATION
# ---------------------------------------------------------------
@st.cache_resource
def init_firebase():
    if firebase_admin._apps:
        return firestore.client()

    try:
        # Streamlit Cloud
        if "firebase" in st.secrets:
            cfg = dict(st.secrets["firebase"])
            cred = credentials.Certificate(cfg)
            firebase_admin.initialize_app(cred)

        # Local development
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
#                PAGE CONFIG
# ---------------------------------------------------------------
st.set_page_config(page_title="Faculty Evaluation", layout="wide")
st.title("🧑‍🏫 Faculty Evaluation – Text Questions")

# ---------------------------------------------------------------
#                LOAD QUESTION BANKS
# ---------------------------------------------------------------
@st.cache_data
def load_questions():
    return {
        "Aptitude Test": pd.read_csv("aptitude.csv"),
        "Adaptability & Learning": pd.read_csv("adaptability_learning.csv"),
        "Communication Skills - Objective": pd.read_csv("communication_skills_objective.csv"),
        "Communication Skills - Descriptive": pd.read_csv("communication_skills_descriptive.csv")
    }

question_banks = load_questions()

# ---------------------------------------------------------------
#                READ ALL STUDENT RESPONSES
# ---------------------------------------------------------------
docs = db.collection("student_responses").stream()

# student_map = { Roll: [ (Section, doc_id) ] }
student_map = {}
# evaluated_map = { doc_id: True/False }
evaluated_map = {}

for doc in docs:
    doc_id = doc.id
    data = doc.to_dict()

    roll = data.get("Roll")
    section = data.get("Section")

    if roll not in student_map:
        student_map[roll] = []

    student_map[roll].append((section, doc_id))

    evaluated_map[doc_id] = "Evaluation" in data

# ---------------------------------------------------------------
#                UI: SELECT STUDENT
# ---------------------------------------------------------------
all_students = sorted(student_map.keys())
selected_roll = st.selectbox("Select Student Roll Number", all_students)

# ---------------------------------------------------------------
#                UI: SELECT TEST TAKEN BY THAT STUDENT
# ---------------------------------------------------------------
tests_taken = [t[0] for t in student_map[selected_roll]]
selected_test = st.selectbox("Select Test", tests_taken)

# Retrieve the correct doc_id
doc_id = None
for sec, d_id in student_map[selected_roll]:
    if sec == selected_test:
        doc_id = d_id
        break

# Load that student's response document
doc_data = db.collection("student_responses").document(doc_id).get().to_dict()

# ---------------------------------------------------------------
#                SHOW EVALUATION STATUS
# ---------------------------------------------------------------
if "Evaluation" in doc_data:
    st.success("This student is ALREADY evaluated ✓")
else:
    st.warning("Not evaluated yet ❗")

st.markdown("---")

# ---------------------------------------------------------------
#                GET QUESTION BANK
# ---------------------------------------------------------------
df = question_banks[selected_test]
responses = doc_data["Responses"]

# ---------------------------------------------------------------
#                FILTER SHORT QUESTIONS ONLY
# ---------------------------------------------------------------
short_df = df[df["Type"] == "short"]


# ---------------------------------------------------------------
#                FUNCTION TO DETECT CORRECT ANSWER
# ---------------------------------------------------------------
def get_correct_answer(row):
    possible_cols = ["Answer", "CorrectAnswer", "Correct", "Ans", "AnswerKey", "RightAnswer"]
    for col in possible_cols:
        if col in row and not pd.isna(row[col]):
            return str(row[col]).strip()
    return None


# ---------------------------------------------------------------
#                MCQ SCORING
# ---------------------------------------------------------------
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


# ---------------------------------------------------------------
#                TEXT QUESTION EVALUATION UI
# ---------------------------------------------------------------
marks_given = {}
text_total = 0

for _, row in short_df.iterrows():
    qid = str(row["QuestionID"])
    qtext = row["Question"]

    # Get student's answer from Firestore
    student_ans = "(no answer)"
    for r in responses:
        if str(r["QuestionID"]) == qid:
            student_ans = r["Response"]
            break

    # Marking scale (0/1 or 0/1/2/3)
    if any(term in qtext.lower() for term in ["3 sentences", "three sentences", "3 points"]):
        scale = [0, 1, 2, 3]
    else:
        scale = [0, 1]

    # Expanded by default
    with st.expander(f"Q{qid}: {qtext}", expanded=True):

        colA, colB = st.columns([3, 1])

        with colA:
            st.markdown(f"**Student Answer:** {student_ans}")

        with colB:
            mark = st.radio(
                "Marks",
                scale,
                horizontal=True,
                key=f"mark_{qid}"
            )

        marks_given[qid] = mark
        text_total += mark

st.markdown("---")
st.subheader(f"Text Marks Total = {text_total}")

# ---------------------------------------------------------------
#                CALCULATE MCQ + FINAL TOTAL
# ---------------------------------------------------------------
mcq_total = calc_mcq(df, responses)
st.write(f"MCQ Score = {mcq_total}")

final_total = mcq_total + text_total
st.subheader(f"FINAL TOTAL = {final_total}")

# ---------------------------------------------------------------
#                SAVE TO FIRESTORE
# ---------------------------------------------------------------
if st.button("💾 Save Evaluation"):
    db.collection("student_responses").document(doc_id).set({
        "Evaluation": {
            "text_marks": marks_given,
            "text_total": text_total,
            "mcq_total": mcq_total,
            "final_total": final_total
        }
    }, merge=True)

    st.success("Evaluation Saved Successfully ✓")
