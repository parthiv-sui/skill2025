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
        firebase_config = st.secrets["firebase"]
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
# DEBUG: CHECK WHAT'S IN FIRESTORE
# ---------------------------------------------------------------
st.subheader("🔍 Database Debug Info")

try:
    # Get all collections
    collections = db.collections()
    collection_names = [col.id for col in collections]
    st.write(f"**Collections in database:** {collection_names}")
    
    # Check student_responses collection
    docs = list(db.collection("student_responses").stream())
    st.write(f"**Documents in 'student_responses':** {len(docs)}")
    
    if docs:
        st.write("**Sample document:**")
        sample_doc = docs[0].to_dict()
        st.json(sample_doc)
    else:
        st.warning("❌ No student responses found in Firestore!")
        st.info("""
        **Students need to submit their responses first:**
        
        1. Make sure students are using the **student submission app**
        2. Students should complete tests and click "Submit"
        3. Their data will appear here automatically
        """)
        
except Exception as e:
    st.error(f"Error checking database: {e}")

# ---------------------------------------------------------------
# LOAD STUDENT RESPONSES (IF ANY EXIST)
# ---------------------------------------------------------------
def load_student_responses():
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

student_data = load_student_responses()

# Only show evaluation interface if we have data
if student_data:
    # Group by roll number
    student_map = {}
    for data in student_data:
        roll = data["roll"]
        if roll not in student_map:
            student_map[roll] = []
        student_map[roll].append(data)

    # Load question banks
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
    MANUAL_EVAL_TESTS = ["Aptitude Test", "Communication Skills - Descriptive"]

    # ---------------------------------------------------------------
    # EVALUATION INTERFACE
    # ---------------------------------------------------------------
    st.subheader("📝 Student Evaluation")
    
    all_students = sorted(student_map.keys())
    selected_roll = st.selectbox("Select Student Roll Number", all_students)
    
    if selected_roll:
        student_sections_data = student_map[selected_roll]
        student_name = student_sections_data[0].get("name", "Unknown")
        
        st.write(f"**Student:** {student_name}")
        st.write(f"**Roll:** {selected_roll}")
        
        # Get sections that need manual evaluation
        manual_eval_sections = []
        for data in student_sections_data:
            section = data["section"]
            if section in MANUAL_EVAL_TESTS:
                manual_eval_sections.append(section)
        
        if manual_eval_sections:
            selected_section = st.selectbox("Select Section to Evaluate", manual_eval_sections)
            
            # Find the selected section data
            selected_section_data = None
            for data in student_sections_data:
                if data["section"] == selected_section:
                    selected_section_data = data
                    break
            
            if selected_section_data and selected_section in question_banks:
                st.subheader(f"Evaluating: {selected_section}")
                
                df = question_banks[selected_section]
                short_questions = df[df["Type"].str.lower() == "short"]
                
                if not short_questions.empty:
                    # Evaluation interface here...
                    st.info(f"Found {len(short_questions)} questions to evaluate")
                    # Add your evaluation code here
                else:
                    st.info("No descriptive questions in this section")
            else:
                st.error("Could not load section data")
        else:
            st.info("No sections require manual evaluation for this student")
else:
    st.info("👆 Waiting for student submissions...")

# ---------------------------------------------------------------
# INSTRUCTIONS
# ---------------------------------------------------------------
st.markdown("---")
st.subheader("📋 Instructions")

st.info("""
**For Faculty:**
1. Students must submit their responses using the student portal first
2. Once students submit, their data will appear here automatically
3. Select a student and section to begin evaluation
4. Use the 0/1 or 0/1/2/3 scoring system as appropriate

**For Students:**
- Make sure you're using the correct student submission app
- Complete all questions and click "Submit"
- Your data will be available for faculty evaluation immediately
""")
