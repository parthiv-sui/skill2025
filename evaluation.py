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
