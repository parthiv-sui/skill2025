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

# ---------------- LOAD CSV METADATA ----------------
@st.cache_data
def load_questions():
    return {
        "Aptitude Test": pd.read_csv("aptitude.csv"),
        "Adaptability & Learning": pd.read_csv("adaptability_learning.csv"),
        "Communication Skills - Objective": pd.read_csv("communication_skills_objective.csv"),
        "Communication Skills - Descriptive": pd.read_csv("communication_skills_descriptive.csv")
    }

question_banks = load_questions()

st.title("🧑‍🏫 Faculty Evaluation – Text Questions")

# ---------------- FETCH LIST OF STUDENT DOCUMENTS ----------------
docs = db.collection("student_responses").stream()
student_docs = {doc.id: doc.to_dict() for doc in docs}

if not student_docs:
    st.error("No student responses found.")
    st.stop()

selected_id = st.selectbox("Select a student response:", list(student_docs.keys()))
student = student_docs[selected_id]

st.subheader(f"Evaluating: {student['Name']} ({student['Roll']})")
section = student["Section"]
st.info(f"Test: **{section}**")

df = question_banks[section]

# ---------------- FILTER ONLY SHORT QUESTIONS ----------------
short_questions = df[df["Type"] == "short"]

responses = student["Responses"]   # This is your stored list

# ---------------- UI FOR EVALUATION ----------------
marks_given = {}
total_text_score = 0

st.markdown("---")

for qid, qrow in short_questions.iterrows():

    qnum = qrow["QuestionID"]
    qtext = qrow["Question"]

    # find matching response from firebase
    student_answer = ""
    for r in responses:
        if str(r["QuestionID"]) == str(qnum):
            student_answer = r["Response"]
            break

    if not student_answer:
        student_answer = "(no answer)"

    # mark scale
    if any(keyword in qtext.lower() for keyword in ["3 sentences", "three sentences", "3 points"]):
        scale = [0,1,2,3]
    else:
        scale = [0,1]

    with st.expander(f"Q{qnum}: {qtext}"):
        st.write("**Student Answer:**")
        st.write(student_answer)

        mark = st.radio(f"Marks:", scale, horizontal=True, key=f"mark_{qnum}")
        marks_given[str(qnum)] = mark
        total_text_score += mark

st.markdown("---")
st.subheader(f"Text Score: {total_text_score}")

# ---------------- CALCULATE MCQ FROM FIRESTORE DATA ----------------
def calculate_mcq_score(section, responses, df):
    score = 0
    for r in responses:
        qid = str(r["QuestionID"])

        # find correct row
        match = df[df["QuestionID"].astype(str) == qid]
        if match.empty: 
            continue

        row = match.iloc[0]
        if row["Type"] != "mcq":
            continue

        correct = str(row["Answer"]).strip()
        student_ans = str(r["Response"]).strip()

        if student_ans == correct:
            score += 1
    return score

mcq_total = calculate_mcq_score(section, responses, df)
st.write(f"MCQ Score (auto): {mcq_total}")

final_total = mcq_total + total_text_score
st.subheader(f"FINAL TOTAL = {final_total}")

# ---------------- SAVE BACK TO FIRESTORE ----------------
if st.button("💾 Save Evaluation"):
    db.collection("student_responses").document(selected_id).set({
        "Evaluation": {
            "text_marks": marks_given,
            "text_total": total_text_score,
            "mcq_total": mcq_total,
            "final_total": final_total,
        }
    }, merge=True)

    st.success("Evaluation saved successfully!")
