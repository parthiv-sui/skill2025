import streamlit as st
import pandas as pd
import json
import firebase_admin
from firebase_admin import credentials, firestore

# ---------------------------------------------------------------
# SIMPLE FIREBASE INIT
# ---------------------------------------------------------------
st.set_page_config(page_title="Faculty Evaluation", layout="wide")
st.title("🧑‍🏫 Faculty Evaluation Dashboard")

# Initialize Firebase
try:
    if not firebase_admin._apps:
        # Use the correct secret name - 'firebase' not 'firebase_key'
        firebase_config = st.secrets["firebase"]
        
        # Parse if it's a string
        if isinstance(firebase_config, str):
            firebase_config = json.loads(firebase_config)
        
        cred = credentials.Certificate(firebase_config)
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
    st.success("✅ Connected to Firebase!")
    
except Exception as e:
    st.error(f"❌ Firebase initialization failed: {e}")
    st.stop()

# ---------------------------------------------------------------
# LOAD STUDENT RESPONSES
# ---------------------------------------------------------------
def load_student_responses():
    """Load all student responses from Firestore"""
    try:
        docs = db.collection("student_responses").stream()
        student_data = []
        
        for doc in docs:
            data = doc.to_dict()
            student_data.append({
                "doc_id": doc.id,
                "name": data.get("Name", ""),
                "roll": data.get("Roll", ""),
                "section": data.get("Section", ""),
                "responses": data.get("Responses", []),
                "evaluation": data.get("Evaluation", {})
            })
        
        return student_data
        
    except Exception as e:
        st.error(f"Error loading student data: {e}")
        return []

# Load student data
student_data = load_student_responses()

if not student_data:
    st.info("No student responses found in Firestore.")
    st.stop()

# Group by roll number
student_map = {}
for data in student_data:
    roll = data["roll"]
    if roll not in student_map:
        student_map[roll] = []
    student_map[roll].append(data)

# ---------------------------------------------------------------
# LOAD QUESTION BANKS
# ---------------------------------------------------------------
@st.cache_data
def load_questions():
    question_banks = {}
    csv_files = {
        "Aptitude Test": "aptitude.csv",
        "Adaptability & Learning": "adaptability_learning.csv", 
        "Communication Skills - Objective": "communcation_skills_objective.csv",
        "Communication Skills - Descriptive": "communcation_skills_descriptive.csv",
    }
    
    for section, filename in csv_files.items():
        try:
            question_banks[section] = pd.read_csv(filename)
        except Exception as e:
            st.error(f"Error loading {filename}: {e}")
    
    return question_banks

question_banks = load_questions()

# Manual evaluation sections
MANUAL_EVAL_TESTS = [
    "Aptitude Test", 
    "Communication Skills - Descriptive"
]

# ---------------------------------------------------------------
# STUDENT SELECTION
# ---------------------------------------------------------------
st.subheader("Select Student")

all_students = sorted(student_map.keys())
if not all_students:
    st.info("No students found.")
    st.stop()

selected_roll = st.selectbox("Select Student Roll Number", all_students)

# Get selected student's data
student_sections_data = student_map[selected_roll]

# Show student info
if student_sections_data:
    student_name = student_sections_data[0].get("name", "Unknown")
    st.write(f"**Student:** {student_name}")
    st.write(f"**Roll:** {selected_roll}")
    st.write(f"**Tests Taken:** {len(student_sections_data)}")

# ---------------------------------------------------------------
# SECTION SELECTION
# ---------------------------------------------------------------
st.subheader("Select Test for Evaluation")

# Get sections that need manual evaluation
manual_eval_sections = []
for data in student_sections_data:
    section = data["section"]
    if section in MANUAL_EVAL_TESTS:
        manual_eval_sections.append(section)

if not manual_eval_sections:
    st.info("No manual evaluation needed for this student.")
    st.stop()

selected_section = st.selectbox("Select Section", manual_eval_sections)

# Get the selected section data
selected_section_data = None
for data in student_sections_data:
    if data["section"] == selected_section:
        selected_section_data = data
        break

if not selected_section_data:
    st.error("Selected section data not found.")
    st.stop()

# ---------------------------------------------------------------
# EVALUATION INTERFACE
# ---------------------------------------------------------------
st.subheader(f"Evaluation: {selected_section}")

# Load questions for this section
if selected_section not in question_banks:
    st.error(f"Question bank not found for {selected_section}")
    st.stop()

df = question_banks[selected_section]
short_questions = df[df["Type"].str.lower() == "short"]

if short_questions.empty:
    st.info("No descriptive questions to evaluate in this section.")
    st.stop()

# Get existing evaluation marks
existing_marks = selected_section_data.get("evaluation", {}).get("text_marks", {})
current_responses = selected_section_data.get("responses", [])

# Evaluation interface
marks_given = {}
total_marks = 0

for _, row in short_questions.iterrows():
    qid = str(row["QuestionID"])
    qtext = str(row["Question"])
    
    # Find student's response
    student_response = "(No response)"
    for resp in current_responses:
        if str(resp.get("QuestionID", "")) == qid:
            student_response = str(resp.get("Response", "(No response)"))
            break
    
    # Determine marking scale
    if "3" in qtext.lower():
        scale = [0, 1, 2, 3]
    else:
        scale = [0, 1]
    
    # Get previous mark if exists
    previous_mark = existing_marks.get(qid, 0)
    
    with st.expander(f"Q{qid}: {qtext}", expanded=True):
        st.write(f"**Student's Answer:** {student_response}")
        
        mark = st.radio(
            "Score:",
            options=scale,
            index=scale.index(previous_mark) if previous_mark in scale else 0,
            horizontal=True,
            key=f"mark_{selected_roll}_{selected_section}_{qid}"
        )
        
        marks_given[qid] = mark
        total_marks += mark

# Display totals
st.subheader("Marks Summary")
st.write(f"**Total Marks for {selected_section}:** {total_marks}")

# ---------------------------------------------------------------
# SAVE EVALUATION
# ---------------------------------------------------------------
if st.button("💾 Save Evaluation"):
    try:
        # Update evaluation data
        evaluation_data = selected_section_data.get("evaluation", {})
        evaluation_data["text_marks"] = marks_given
        evaluation_data["text_total"] = total_marks
        
        # Calculate final total (you can add MCQ and Likert here later)
        evaluation_data["final_total"] = total_marks
        
        # Save to Firestore
        doc_ref = db.collection("student_responses").document(selected_section_data["doc_id"])
        doc_ref.set({
            "Evaluation": evaluation_data
        }, merge=True)
        
        st.success("✅ Evaluation saved successfully!")
        
    except Exception as e:
        st.error(f"❌ Error saving evaluation: {e}")

# ---------------------------------------------------------------
# SHOW ALL EVALUATIONS FOR THIS STUDENT
# ---------------------------------------------------------------
st.subheader("All Evaluations for This Student")

for data in student_sections_data:
    section = data["section"]
    evaluation = data.get("evaluation", {})
    text_total = evaluation.get("text_total", 0)
    mcq_total = evaluation.get("mcq_total", 0)
    likert_total = evaluation.get("likert_total", 0)
    final_total = evaluation.get("final_total", 0)
    
    st.write(f"**{section}:** Text={text_total}, MCQ={mcq_total}, Likert={likert_total}, Total={final_total}")
