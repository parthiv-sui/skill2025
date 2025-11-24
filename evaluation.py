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
# LOAD STUDENT DATA WITH EVALUATIONS
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
                
                # Get existing evaluation if available
                evaluation = data.get("Evaluation", {})
                
                roll_map[roll].append({
                    "doc_id": doc.id,
                    "data": data,
                    "section": section,
                    "responses": data.get("Responses", []),
                    "evaluation": evaluation
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
existing_evaluation = selected_doc["evaluation"]
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
    
    # Create question lookup - handle different ID formats
    q_lookup = {}
    for _, row in df.iterrows():
        if 'QuestionID' in row and pd.notna(row['QuestionID']):
            qid_clean = str(row['QuestionID']).strip()
            q_lookup[qid_clean] = row
            
            # For adaptability questions (A1, L1), also store without prefix
            if qid_clean.startswith(('A', 'L')) and len(qid_clean) > 1:
                q_lookup[qid_clean[1:]] = row  # Store "1" for "A1"
    
    # Process each response
    for i, response in enumerate(responses):
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
        
        if not question_id or not student_answer:
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
                break
        
        if question_row is None:
            continue
            
        # Score the question
        q_type = str(question_row.get("Type", "")).lower().strip()
        
        if q_type == "mcq":
            correct_ans = get_correct_answer(question_row)
            if correct_ans and student_answer == correct_ans:
                mcq_score += 1
                
        elif q_type == "likert":
            try:
                resp_val = int(float(student_answer))
                # Your scale: 1=0, 2=1, 3=2, 4=3, 5=4
                points = max(0, min(4, resp_val - 1))
                likert_score += points
            except (ValueError, TypeError):
                pass
    
    return mcq_score, likert_score

def evaluate_manual_questions(df_test, responses, existing_manual_marks=None):
    """Handle manual evaluation for short answer questions"""
    manual_questions = df_test[df_test["Type"].isin(["short", "descriptive"])]
    manual_total = 0
    manual_marks = existing_manual_marks or {}
    
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
        
        # Use existing mark if available, otherwise default to 0
        default_mark = manual_marks.get(qid, 0)
        if default_mark not in scale_options:
            default_mark = 0
        
        # Scoring interface
        mark = st.radio(
            f"Score for Q{qid} (0-{max(scale_options)})",
            options=scale_options,
            index=scale_options.index(default_mark),
            horizontal=True,
            key=f"manual_{selected_roll}_{selected_test}_{qid}"
        )
        
        manual_marks[qid] = mark
        manual_total += mark
        st.write("---")
    
    return manual_total, manual_marks

# ---------------------------------------------------------
# CALCULATE GRAND TOTAL
# ---------------------------------------------------------
def calculate_grand_total(student_data, current_test_data=None):
    """Calculate grand total across all tests"""
    grand_total = 0
    
    for item in student_data:
        test_eval = item.get("evaluation", {})
        test_final = test_eval.get("final_total", 0)
        grand_total += test_final
    
    return grand_total

# ---------------------------------------------------------
# MAIN EVALUATION INTERFACE
# ---------------------------------------------------------
st.header(f"📊 Evaluating: {selected_test}")

# Get existing evaluation data for this test
existing_auto_mcq = existing_evaluation.get("auto_mcq", 0)
existing_auto_likert = existing_evaluation.get("auto_likert", 0)
existing_manual_marks = existing_evaluation.get("manual_marks", {})
existing_manual_total = existing_evaluation.get("manual_total", 0)
existing_final_total = existing_evaluation.get("final_total", 0)

# Calculate auto scores (use existing if available, otherwise calculate)
if existing_auto_mcq > 0 or existing_auto_likert > 0:
    # Use existing scores
    auto_mcq = existing_auto_mcq
    auto_likert = existing_auto_likert
    st.info(f"Using previously calculated auto-scores: MCQ={auto_mcq}, Likert={auto_likert}")
else:
    # Calculate fresh scores
    auto_mcq, auto_likert = calculate_auto_scores(df_test, responses)
    st.success(f"Fresh auto-scores calculated: MCQ={auto_mcq}, Likert={auto_likert}")

# Manual evaluation (always show interface, but use existing marks as defaults)
manual_total, manual_marks = evaluate_manual_questions(df_test, responses, existing_manual_marks)

# Final calculation for current test
final_score = auto_mcq + auto_likert + manual_total

# Calculate current grand total
current_grand_total = calculate_grand_total(student_data)

# ---------------------------------------------------------
# DISPLAY OVERALL PROGRESS & TOTALS
# ---------------------------------------------------------
st.header("🎯 Evaluation Progress & Totals")

# Display current test scores
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("Auto MCQ Score", auto_mcq)
with col2:
    st.metric("Auto Likert Score", auto_likert)
with col3:
    st.metric("Manual Evaluation", manual_total)
with col4:
    st.metric("Current Test Score", final_score)
with col5:
    st.metric("Grand Total (All Tests)", current_grand_total)

# Show progress table
st.subheader("📋 Evaluation Status Across All Tests")
all_tests_data = []
for item in student_data:
    test_eval = item.get("evaluation", {})
    test_final = test_eval.get("final_total", 0)
    all_tests_data.append({
        "Test": item["section"],
        "Status": "✅ Evaluated" if test_final > 0 else "⏳ Pending",
        "Score": test_final
    })

progress_df = pd.DataFrame(all_tests_data)
st.dataframe(progress_df, use_container_width=True)


# ---------------------------------------------------------
# DEBUG SECTION - ADD THIS BEFORE SAVE BUTTON
# ---------------------------------------------------------
with st.expander("🔍 DEBUG: Current Calculations"):
    st.write("### Current Test Scores Breakdown:")
    st.write(f"- Auto MCQ: {auto_mcq}")
    st.write(f"- Auto Likert: {auto_likert}")
    st.write(f"- Manual Total: {manual_total}")
    st.write(f"- **Current Test Final: {final_score}**")
    
    st.write("### All Tests Breakdown (Before Save):")
    total_calculated = 0
    for item in student_data:
        test_name = item["section"]
        if item["doc_id"] == doc_id:
            # This is the current test we're editing
            test_score = final_score
            status = "🔄 CURRENTLY EDITING"
        else:
            test_eval = item.get("evaluation", {})
            test_score = test_eval.get("final_total", 0)
            status = "✅ SAVED"
        
        total_calculated += test_score
        st.write(f"- {test_name}: {test_score} ({status})")
    
    st.write(f"### **Calculated Grand Total: {total_calculated}**")
    st.write(f"### **Displayed Grand Total: {current_grand_total}**")
    
    if total_calculated != current_grand_total:
        st.error("❌ MISMATCH: Calculated vs Displayed Grand Total don't match!")
    else:
        st.success("✅ Grand Total calculation is correct")

# ---------------------------------------------------------
# SAVE EVALUATION (WITH GRAND TOTAL UPDATE)
# ---------------------------------------------------------
if st.button("💾 Save Current Test Evaluation"):
    try:
        # First, save the current test evaluation
        evaluation_data = {
            "auto_mcq": auto_mcq,
            "auto_likert": auto_likert,
            "manual_marks": manual_marks,
            "manual_total": manual_total,
            "final_total": final_score,
            "evaluated_at": firestore.SERVER_TIMESTAMP
        }
        
        # Save current test evaluation
        db.collection("student_responses").document(doc_id).set({
            "Evaluation": evaluation_data
        }, merge=True)
        
        # Recalculate and update grand total for ALL documents of this student
        updated_grand_total = 0
        for item in student_data:
            test_doc_id = item["doc_id"]
            test_section = item["section"]
            
            if test_doc_id == doc_id:
                # This is the current test we just saved
                test_final = final_score
            else:
                # Get the existing final total from other tests
                test_eval = item.get("evaluation", {})
                test_final = test_eval.get("final_total", 0)
            
            updated_grand_total += test_final
            
            # Update grand total in each document
            db.collection("student_responses").document(test_doc_id).set({
                "Evaluation": {"grand_total": updated_grand_total}
            }, merge=True)
        
        st.success(f"✅ Evaluation saved successfully! Grand Total updated to: {updated_grand_total}")
        st.rerun()  # Refresh to show updated scores
        
    except Exception as e:
        st.error(f"❌ Failed to save evaluation: {e}")

# ---------------------------------------------------------
# EXPORT TO CSV
# ---------------------------------------------------------
st.header("📥 Export Results")

if st.button("📊 Download Complete Evaluation Report"):
    # Create comprehensive results dataframe
    results_data = []
    
    for item in student_data:
        test_eval = item.get("evaluation", {})
        results_data.append({
            "Roll_Number": selected_roll,
            "Test": item["section"],
            "Auto_MCQ_Score": test_eval.get("auto_mcq", 0),
            "Auto_Likert_Score": test_eval.get("auto_likert", 0),
            "Manual_Total": test_eval.get("manual_total", 0),
            "Test_Score": test_eval.get("final_total", 0)
        })
    
    results_df = pd.DataFrame(results_data)
    
    # Add grand total row
    grand_total_row = pd.DataFrame([{
        "Roll_Number": selected_roll,
        "Test": "GRAND TOTAL",
        "Auto_MCQ_Score": "",
        "Auto_Likert_Score": "",
        "Manual_Total": "",
        "Test_Score": current_grand_total
    }])
    
    final_df = pd.concat([results_df, grand_total_row], ignore_index=True)
    
    # Convert to CSV
    csv = final_df.to_csv(index=False)
    
    # Download button
    st.download_button(
        label="⬇️ Download Complete Report (CSV)",
        data=csv,
        file_name=f"complete_evaluation_{selected_roll}.csv",
        mime="text/csv"
    )
    
    # Show preview
    st.subheader("Report Preview")
    st.dataframe(final_df)
