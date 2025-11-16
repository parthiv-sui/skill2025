# @Gemini: Debug this Firebase data loading issue - why is student_data empty?
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
# LOAD STUDENT RESPONSES - FIXED VERSION
# ---------------------------------------------------------------
def load_all_student_responses():
    """Load ALL student responses without filtering"""
    try:
        docs = db.collection("student_responses").stream()
        student_data = []
        
        for doc in docs:
            try:
                data = doc.to_dict()
                st.write(f"📄 Found document: {doc.id}")  # Debug
                
                student_data.append({
                    "doc_id": doc.id,
                    "name": data.get("Name", "Unknown"),
                    "roll": data.get("Roll", "Unknown"),
                    "section": data.get("Section", "Unknown"),
                    "responses": data.get("Responses", []),
                    "evaluation": data.get("Evaluation", {})
                })
            except Exception as doc_error:
                st.error(f"Error processing doc {doc.id}: {doc_error}")
                continue
                
        return student_data
        
    except Exception as e:
        st.error(f"❌ Error loading from Firestore: {e}")
        return []

# Load the data
student_data = load_all_student_responses()
st.write(f"**Total student records loaded:** {len(student_data)}")

if not student_data:
    st.error("""
    ❌ No student data found, but Firebase is connected.
    
    **Possible issues:**
    1. Data is in a different collection name
    2. Different field names in documents
    3. Data structure is different than expected
    
    **Let's debug:**""")
    
    # Debug: Show all collections and sample data
    try:
        collections = list(db.collections())
        st.write("**Available collections:**", [col.id for col in collections])
        
        # Check what's actually in student_responses
        docs = list(db.collection("student_responses").limit(5).stream())
        if docs:
            st.write("**Sample documents in student_responses:**")
            for doc in docs:
                st.json(doc.to_dict())
        else:
            st.write("No documents in student_responses collection")
            
    except Exception as debug_error:
        st.error(f"Debug error: {debug_error}")
    
    st.stop()

# Show what we found
st.success(f"✅ Loaded {len(student_data)} student records!")

# Display all students and their data
st.subheader("📋 All Student Submissions")
for data in student_data:
    with st.expander(f"🎓 {data['name']} ({data['roll']}) - {data['section']}"):
        st.write(f"**Document ID:** {data['doc_id']}")
        st.write(f"**Number of responses:** {len(data['responses'])}")
        st.write(f"**Evaluation data:** {data['evaluation']}")
        
        # Show first few responses
        if data['responses']:
            st.write("**Sample responses:**")
            for i, resp in enumerate(data['responses'][:3]):  # Show first 3
                st.write(f"{i+1}. Q{resp.get('QuestionID', '?')}: {resp.get('Response', 'No response')[:50]}...")

# ---------------------------------------------------------------
# GROUP BY ROLL NUMBER FOR EVALUATION
# ---------------------------------------------------------------
student_map = {}
for data in student_data:
    roll = data["roll"]
    if roll not in student_map:
        student_map[roll] = []
    student_map[roll].append(data)

st.subheader("👥 Students by Roll Number")
st.write(f"**Unique students:** {len(student_map)}")

# ---------------------------------------------------------------
# EVALUATION INTERFACE
# ---------------------------------------------------------------
st.markdown("---")
st.subheader("📝 Evaluation Interface")

# Student selection
all_students = sorted(student_map.keys())
selected_roll = st.selectbox("Select Student Roll Number", all_students)

if selected_roll:
    student_sections = student_map[selected_roll]
    student_name = student_sections[0]["name"]
    
    st.write(f"**Evaluating:** {student_name} ({selected_roll})")
    st.write(f"**Tests taken:** {len(student_sections)}")
    
    # Show all sections for this student
    for section_data in student_sections:
        st.write(f"- **{section_data['section']}**: {len(section_data['responses'])} questions")
    
    # Section selection for evaluation
    section_names = [data["section"] for data in student_sections]
    selected_section = st.selectbox("Select Section to Evaluate", section_names)
    
    # Find the selected section data
    selected_section_data = None
    for data in student_sections:
        if data["section"] == selected_section:
            selected_section_data = data
            break
    
    if selected_section_data:
        st.subheader(f"🔍 Evaluating: {selected_section}")
        
        # Show all responses for this section
        responses = selected_section_data["responses"]
        st.write(f"**Number of questions:** {len(responses)}")
        
        for i, resp in enumerate(responses):
            with st.expander(f"Q{resp.get('QuestionID', i+1)}: {resp.get('Question', 'No question text')[:50]}...", expanded=False):
                st.write(f"**Student's answer:** {resp.get('Response', 'No response')}")
                
                # Simple scoring interface
                score = st.radio(
                    "Score:",
                    [0, 1, 2, 3],
                    horizontal=True,
                    key=f"score_{selected_roll}_{selected_section}_{i}"
                )
        
        # Save evaluation button
        if st.button("💾 Save Evaluation"):
            st.success("Evaluation saved! (Placeholder - add your save logic here)")

st.markdown("---")
st.info("💡 **Tip**: If you're not seeing expected data, check the field names in your Firestore documents match what the code expects (Name, Roll, Section, Responses).")
