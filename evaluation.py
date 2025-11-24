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
        df = pd.read_csv(fname)
        df.columns = [c.strip() for c in df.columns]
        if "Type" in df.columns:
            df["Type"] = df["Type"].astype(str).str.lower().str.strip()
        return df
    except Exception as e:
        st.error(f"Error loading {fname}: {e}")
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
            return str(row[col]).strip().lower()
    return None

def calculate_auto_scores(df, responses):
    """Calculate automatic scores (MCQ + Likert)"""
    mcq_score = 0
    likert_score = 0
    
    # Create question lookup
    q_lookup = {}
    for _, row in df.iterrows():
        if 'QuestionID' in row and pd.notna(row['QuestionID']):
            qid = str(row['QuestionID']).strip()
            q_lookup[qid] = row
    
    # Calculate scores
    for response in responses:
        qid = str(response.get("QuestionID", "")).strip()
        student_answer = str(response.get("Response", "")).strip().lower()
        
        if qid in q_lookup:
            row = q_lookup[qid]
            q_type = row.get("Type", "").lower()
            
            if q_type == "mcq":
                correct_ans = get_correct_answer(row)
                if correct_ans and student_answer == correct_ans:
                    mcq_score += 1
            elif q_type == "likert":
                try:
                    resp_val = int(student_answer)
                    likert_score += max(0, min(4, resp_val - 1))
                except:
                    pass
    
    return mcq_score, likert_score

# ---------------------------------------------------------
# MANUAL EVALUATION INTERFACE
# ---------------------------------------------------------
st.header(f"Manual Evaluation: {selected_test}")

# Get saved evaluation or initialize new
saved_eval = doc_data.get("Evaluation", {})
saved_manual_marks = saved_eval.get("manual_marks", {})

# Calculate auto scores first
auto_mcq, auto_likert = calculate_auto_scores(df_test, responses)

# Manual evaluation section
st.subheader("📝 Manual Scoring")
manual_questions = df_test[df_test["Type"].isin(["short", "descriptive"])]

if manual_questions.empty:
    st.info("No manual evaluation questions in this test.")
    manual_total = 0
    manual_marks = {}
else:
    manual_total = 0
    manual_marks = {}
    
    for _, row in manual_questions.iterrows():
        qid = str(row["QuestionID"])
        qtext = row["Question"]
        
        # Find student's answer
        student_answer = "No answer provided"
        for resp in responses:
            if str(resp.get("QuestionID", "")).strip() == qid:
                student_answer = str(resp.get("Response", "No answer provided"))
                break
        
        st.write(f"**Q{qid}:** {qtext}")
        st.write(f"**Student's Answer:** {student_answer}")
        
        # Get scoring scale
        scale_options = get_scale_options(qid)
        default_mark = saved_manual_marks.get(qid, 0)
        
        # Ensure default is valid
        if default_mark not in scale_options:
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

# ---------------------------------------------------------
# FINAL CALCULATION & DISPLAY
# ---------------------------------------------------------
final_score = auto_mcq + auto_likert + manual_total

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
st.header("📊 Export Results")

if st.button("📥 Download Evaluation as CSV"):
    # Create results dataframe
    results_data = {
        "Roll Number": [selected_roll],
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
        label="⬇️ Download CSV",
        data=csv,
        file_name=f"evaluation_{selected_roll}_{selected_test}.csv",
        mime="text/csv"
    )
    
    # Show preview
    st.subheader("CSV Preview")
    st.dataframe(results_df)

# ---------------------------------------------------------
# DEBUG INFO (Optional - can be removed)
# ---------------------------------------------------------
with st.expander("🔍 Debug Info"):
    st.write("Test Dataframe Shape:", df_test.shape)
    st.write("Test Columns:", df_test.columns.tolist())
    st.write("Number of Responses:", len(responses))
    st.write("Manual Questions Count:", len(manual_questions))
    st.write("Auto MCQ Score:", auto_mcq)
    st.write("Auto Likert Score:", auto_likert)
