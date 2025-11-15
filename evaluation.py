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
selected_roll = st.selectbox(_
