import streamlit as st
import pandas as pd
import json
import firebase_admin
from firebase_admin import credentials, firestore

# ---------------- FIREBASE INIT ----------------
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
            with open("firebase_key.json") as f:
                cred = credentials.Certificate(json.load(f))
                firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Firebase init failed: {e}")
        return None

    return firestore.client()

db = init_firebase()
if db is None:
    st.stop()

st.title("🧑‍🏫 Faculty Evaluation – Text Questions")

# ---------------- LOAD QUESTION BANKS ----------------
@st.cache_data
def load_questions():
    return {
        "Aptitude Test": pd.read_csv("aptitude.csv"),
        "Adaptability & Learning": pd.read_csv("adaptability_learning.csv"),
        "Communication Skills - Objective": pd.read_csv("communication_skills_objective.csv"),
        "Communication Skills - Descriptive": pd.read_csv("communication_skills_descriptive.csv")
    }

question_banks = load_questions()

# ---------------- FETCH ALL STUDENT DOCUMENTS ----------------
docs = db.collection("student_responses").stream()

student_map = {}   # { roll: [ (section, doc_id) ] }
evaluated_map = {} # { doc_id: True/False }

for doc in docs:
    doc_id = doc.id
    data = doc.to_dict()
    roll = data.get("Roll")
    section = data.get("Section")

    if roll not in student_map:
        student_map[roll] = []

    student_map[roll].append((section, doc_id))
    evaluated_map[doc_id] = "Evaluation" in data

# ---------------- UI: SELECT STUDENT ----------------
all_students = sorted(student_map.keys())
selected_roll = st.selectbox("Select Student Roll Number", all_students)

# list available tests
tests = [s[0] for s in student_map[selected_roll]]
selected_test = st.selectbox("Select Test Taken", tests)

# get the doc_id
doc_id = None
for section, d_id in student_map[selected_roll]:
    if section == selected_test:
        doc_id = d_id
        break

# load that student’s document
doc_data = db.collection("student_responses").document(doc_id).get().to_dict()

# show evaluation status
if "Evaluation" in doc_data:
    st.success("This student is ALREADY evaluated ✓")
else:
    st.warning("Not Evaluated Yet ❗")

st.markdown("---")

df = question_banks[selected_test]
responses = doc_data["Responses"]

# filter only SHORT questions
short_df = df[df["Type"] == "short"]

marks_given = {}
text_total = 0

for _, row in short_df.iterrows():
    qid = str(row["QuestionID"])
    qtext = row["Question"]

    student_ans = "(no answer)"
    for r in responses:
        if str(r["QuestionID"]) == qid:
            student_ans = r["Response"]
            break

    # mark scale
    if any(term in qtext.lower() for term in ["3 sentences", "three sentences", "3 points"]):
        scale = [0,1,2,3]
    else:
        scale = [0,1]

    with st.expander(f"Q{qid}: {qtext}"):
        st.write("**Student Answer:**")
        st.write(student_ans)
        mark = st.radio("Marks:", scale, horizontal=True, key=f"m_{qid}")
        marks_given[qid] = mark
        text_total += mark

st.markdown("---")
st.subheader(f"Text Marks Total = {text_total}")

# ---------------- MCQ SCORING FUNCTION ----------------
def calc_mcq(df, responses):
    score = 0
    for r in responses:
        qid = str(r["QuestionID"])
        ans = str(r["Response"]).strip()

        row = df[df["QuestionID"].astype(str) == qid]
        if row.empty:
            continue
        row = row.iloc[0]

        if row["Type"] != "mcq":
            continue

        correct = str(row["Answer"]).strip()
        if ans == correct:
            score += 1
    return score

mcq_total = calc_mcq(df, responses)
st.write(f"MCQ Score (auto) = {mcq_total}")

final_total = mcq_total + text_total
st.subheader(f"FINAL TOTAL = {final_total}")

# ---------------- SAVE ----------------
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
