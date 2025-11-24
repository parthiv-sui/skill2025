import json
import pandas as pd
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from io import StringIO

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(page_title="Faculty Evaluation Dashboard", layout="wide")
st.title("👩‍🏫 Faculty Evaluation Dashboard")

# ---------------------------------------------------------
# FIREBASE INIT
# ---------------------------------------------------------
if not firebase_admin._apps:
    try:
        if "firebase" in st.secrets:
            cfg = dict(st.secrets["firebase"])
        else:
            with open("firebase_key.json") as f:
                cfg = json.load(f)
        cred = credentials.Certificate(cfg)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Firebase init failed: {e}")
        st.stop()

db = firestore.client()

# ---------------------------------------------------------
# LOAD CSVs
# ---------------------------------------------------------
def load_csv(fname):
    try:
        # Handle encoding issues and BOM
        df = pd.read_csv(fname, encoding='utf-8-sig')
        df.columns = [c.strip() for c in df.columns]
        
        # Ensure QuestionID is string and clean
        if 'QuestionID' in df.columns:
            df['QuestionID'] = df['QuestionID'].astype(str).str.strip()
        
        # Handle Type column
        if 'Type' in df.columns:
            df['Type'] = df['Type'].astype(str).str.lower().str.strip()
        
        st.success(f"✅ Loaded {fname}: {len(df)} questions")
        return df
    except Exception as e:
        st.error(f"❌ Error loading {fname}: {e}")
        return pd.DataFrame()

banks = {
    "Aptitude Test": load_csv("aptitude.csv"),
    "Adaptability & Learning": load_csv("adaptability_learning.csv"),
    "Communication Skills - Objective": load_csv("communication_skills_objective.csv"),
    "Communication Skills - Descriptive": load_csv("communication_skills_descriptive.csv"),
}

# ---------------------------------------------------------
# SCALE MAPPING - FIXED
# ---------------------------------------------------------
FOUR_POINT_QUESTIONS = {12, 13, 14, 16, 17, 18}
THREE_POINT_QUESTIONS = {22, 23, 24, 25, 28, 29, 30, 34}

def parse_qid(q):
    try:
        return int(str(q).replace("Q", "").strip())
    except:
        return -1

def get_scale_options(qid):
    """Return the appropriate scoring scale for a question"""
    q_num = parse_qid(qid)
    if q_num in FOUR_POINT_QUESTIONS:
        return [0, 1, 2, 3]
    elif q_num in THREE_POINT_QUESTIONS:
        return [0, 1, 2]
    else:
        return [0, 1]  # Default binary scale

# ---------------------------------------------------------
# LOAD STUDENT DATA
# ---------------------------------------------------------
@st.cache_data
def load_all_responses():
    roll_map = {}
    try:
        docs = db.collection("student_responses").stream()
        for doc in docs:
            data = doc.to_dict()
            roll = data.get("Roll", "").strip()
            section = data.get("Section", "").strip()
            
            if roll and section:
                if roll not in roll_map:
                    roll_map[roll] = []
                
                roll_map[roll].append({
                    "doc_id": doc.id,
                    "data": data,
                    "section": section,
                    "responses": data.get("Responses", [])
                })
        return roll_map
    except Exception as e:
        st.error(f"Error loading responses: {e}")
        return {}

roll_map = load_all_responses()

if not roll_map:
    st.error("No student responses found.")
    st.stop()

# ---------------------------------------------------------
# STUDENT SELECTION
# ---------------------------------------------------------
selected_roll = st.selectbox("Select Student Roll Number", sorted(roll_map.keys()))
student_data = roll_map[selected_roll]

# Get available tests for this student
available_tests = list(set([item["section"] for item in student_data]))
selected_test = st.selectbox("Select Test to Evaluate", available_tests)

# Find the selected test document
selected_doc = None
for item in student_data:
    if item["section"] == selected_test:
        selected_doc = item
        break

if not selected_doc:
    st.error("Selected test not found.")
    st.stop()

doc_id = selected_doc["doc_id"]
doc_data = selected_doc["data"]
responses = selected_doc["responses"]
df_test = banks[selected_test]

# ---------------------------------------------------------
# SCORING FUNCTIONS
# ---------------------------------------------------------
def get_correct_answer(row):
    """Extract correct answer from dataframe row"""
    answer_cols = ["Answer", "Correct", "CorrectAnswer", "Ans", "AnswerKey"]
    for col in answer_cols:
        if col in row and pd.notna(row[col]):
            answer = str(row[col]).strip().lower()
            # Clean the answer
            answer = answer.replace('"', '').replace("'", "").replace(".", "")
            return answer
    return None

def calculate_auto_scores(df, responses):
    """Calculate automatic scores (MCQ + Likert) with Firestore-compatible parsing"""
    mcq_score = 0
    likert_score = 0
    
    st.write("🔍 Debug: Starting auto-scoring...")
    
    # Create question lookup - handle different ID formats
    q_lookup = {}
    for _, row in df.iterrows():
        if 'QuestionID' in row and pd.notna(row['QuestionID']):
            qid_clean = str(row['QuestionID']).strip()
            q_lookup[qid_clean] = row
            
            # For adaptability questions (A1, L1), also store without prefix
            if qid_clean.startswith(('A', 'L')) and len(qid_clean) > 1:
                q_lookup[qid_clean[1:]] = row  # Store "1" for "A1"
    
    st.write(f"✅ Loaded {len(q_lookup)} questions into lookup")
    
    # Process each response
    for i, response in enumerate(responses):
        st.write(f"--- Processing Response {i+1} ---")
        
        # Extract data based on your Firestore structure
        question_id = None
        student_answer = None
        
        # METHOD 1: Your actual Firestore structure
        if 'QuestionID' in response:
            question_id = str(response['QuestionID']).strip()
        # METHOD 2: Alternative field names
        elif 'question_id' in response:
            question_id = str(response['question_id']).strip()
        elif 'questionId' in response:
            question_id = str(response['questionId']).strip()
        
        if 'Response' in response:
            student_answer = str(response['Response']).strip().lower()
        elif 'response' in response:
            student_answer = str(response['response']).strip().lower()
        elif 'answer' in response:
            student_answer = str(response['answer']).strip().lower()
        
        st.write(f"🔍 Extracted: QID='{question_id}', Answer='{student_answer}'")
        
        if not question_id or not student_answer:
            st.write("❌ Missing QID or answer, skipping")
            continue
            
        # Find matching question
        question_row = None
        possible_keys = [question_id]
        
        # Add variations for matching
        if question_id.startswith(('A', 'L', 'Q')):
            possible_keys.append(question_id[1:])  # Remove prefix
        if question_id.isdigit():
            possible_keys.append(f"A{question_id}")  # Add prefix for adaptability
            possible_keys.append(f"L{question_id}")  # Add prefix for learning
        
        for key in possible_keys:
            if key in q_lookup:
                question_row = q_lookup[key]
                st.write(f"✅ Matched: Firestore Q{question_id} -> CSV Q{question_row['QuestionID']}")
                break
        
        if question_row is None:
            st.write(f"❌ No CSV match for Q{question_id}")
            continue
            
        # Score the question
        q_type = str(question_row.get("Type", "")).lower().strip()
        st.write(f"📝 Question Type: {q_type}")
        
        if q_type == "mcq":
            correct_ans = get_correct_answer(question_row)
            st.write(f"🔍 MCQ Check: Student='{student_answer}', Correct='{correct_ans}'")
            
            if correct_ans and student_answer == correct_ans:
                mcq_score += 1
                st.write("✅ MCQ Correct: +1 point")
            else:
                st.write("❌ MCQ Incorrect: +0 points")
                
        elif q_type == "likert":
            try:
                resp_val = int(float(student_answer))
                # Your scale: 1=0, 2=1, 3=2, 4=3, 5=4
                points = max(0, min(4, resp_val - 1))
                likert_score += points
                st.write(f"✅ Likert: {resp_val} -> {points} points")
            except (ValueError, TypeError):
                st.write(f"❌ Likert Invalid: '{student_answer}'")
    
    st.success(f"🎯 Auto-scoring Complete: MCQ={mcq_score}, Likert={likert_score}")
    return mcq_score, likert_score

def evaluate_manual_questions(df_test, responses):
    """Handle manual evaluation for short answer questions"""
    manual_questions = df_test[df_test["Type"].isin(["short", "descriptive"])]
    manual_total = 0
    manual_marks = {}
    
    if manual_questions.empty:
        st.info("No manual evaluation questions in this test.")
        return manual_total, manual_marks
    
    st.subheader("📝 Manual Evaluation - Text Questions")
    
    for _, row in manual_questions.iterrows():
        qid = str(row["QuestionID"])
        qtext = row["Question"]
        
        # Find student's answer from responses
        student_answer = "No answer provided"
        for resp in responses:
            resp_qid = None
            if 'QuestionID' in resp:
                resp_qid = str(resp['QuestionID']).strip()
            
            if resp_qid == qid:
                if 'Response' in resp:
                    student_answer = str(resp['Response'])
                elif 'Answer' in resp:
                    student_answer = str(resp['Answer'])
                break
        
        st.write(f"**Q{qid}:** {qtext}")
        st.write(f"**Student's Answer:** {student_answer}")
        
        # Get scoring scale
        scale_options = get_scale_options(qid)
        default_mark = 0
        
        # Scoring interface
        mark = st.radio(
            f"Score for Q{qid} (0-{max(scale_options)})",
            options=scale_options,
            index=scale_options.index(default_mark),
            horizontal=True,
            key=f"manual_{selected_roll}_{qid}"
        )
        
        manual_marks[qid] = mark
        manual_total += mark
        st.write("---")
    
    return manual_total, manual_marks

# ---------------------------------------------------------
# MAIN EVALUATION INTERFACE
# ---------------------------------------------------------
st.header(f"📊 Evaluating: {selected_test}")

# Calculate auto scores first (with detailed debugging)
with st.expander("🔍 Auto-Scoring Debug", expanded=True):
    auto_mcq, auto_likert = calculate_auto_scores(df_test, responses)

# Manual evaluation
manual_total, manual_marks = evaluate_manual_questions(df_test, responses)

# Final calculation
final_score = auto_mcq + auto_likert + manual_total

# Display results
st.subheader("🎯 Final Scores")
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Auto MCQ Score", auto_mcq)
with col2:
    st.metric("Auto Likert Score", auto_likert)
with col3:
    st.metric("Manual Evaluation", manual_total)
with col4:
    st.metric("Final Score", final_score)

# ---------------------------------------------------------
# SAVE EVALUATION
# ---------------------------------------------------------
if st.button("💾 Save Evaluation"):
    try:
        evaluation_data = {
            "auto_mcq": auto_mcq,
            "auto_likert": auto_likert,
            "manual_marks": manual_marks,
            "manual_total": manual_total,
            "final_total": final_score,
            "evaluated_at": firestore.SERVER_TIMESTAMP
        }
        
        # Save to Firestore
        db.collection("student_responses").document(doc_id).set({
            "Evaluation": evaluation_data
        }, merge=True)
        
        st.success("✅ Evaluation saved successfully!")
        
    except Exception as e:
        st.error(f"❌ Failed to save evaluation: {e}")

# ---------------------------------------------------------
# EXPORT TO CSV
# ---------------------------------------------------------
st.header("📥 Export Results")

if st.button("📊 Download Evaluation as CSV"):
    # Create results dataframe
    results_data = {
        "Roll_Number": [selected_roll],
        "Test": [selected_test],
        "Auto_MCQ_Score": [auto_mcq],
        "Auto_Likert_Score": [auto_likert],
        "Manual_Total": [manual_total],
        "Final_Score": [final_score]
    }
    
    # Add individual manual question scores
    for qid, score in manual_marks.items():
        results_data[f"Q{qid}_Score"] = [score]
    
    results_df = pd.DataFrame(results_data)
    
    # Convert to CSV
    csv = results_df.to_csv(index=False)
    
    # Download button
    st.download_button(
        label="⬇️ Download CSV File",
        data=csv,
        file_name=f"evaluation_{selected_roll}_{selected_test}.csv",
        mime="text/csv"
    )
    
    # Show preview
    st.subheader("CSV Preview")
    st.dataframe(results_df)

# ---------------------------------------------------------
# DEBUG INFO (Optional - can be removed later)
# ---------------------------------------------------------
with st.expander("🔍 Detailed Debug Info"):
    st.write("### CSV File Info")
    st.write(f"Test: {selected_test}")
    st.write(f"CSV Shape: {df_test.shape}")
    st.write(f"CSV Columns: {df_test.columns.tolist()}")
    
    st.write("### Sample from CSV:")
    if not df_test.empty:
        st.dataframe(df_test.head(3)[['QuestionID', 'Type', 'Question']])
    
    st.write("### Student Responses:")
    st.write(f"Total responses: {len(responses)}")
    for i, resp in enumerate(responses[:5]):
        st.write(f"Response {i+1}: {resp}")
    
    st.write("### Question Type Breakdown in CSV:")
    if 'Type' in df_test.columns:
        type_counts = df_test['Type'].value_counts()
        st.write(type_counts)
