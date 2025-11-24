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
        df = pd.read_csv(fname, encoding='utf-8-sig')
        df.columns = [c.strip() for c in df.columns]
        if 'QuestionID' in df.columns:
            df['QuestionID'] = df['QuestionID'].astype(str).str.strip()
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
# SCALE MAPPING
# ---------------------------------------------------------
FOUR_POINT_QUESTIONS = {12, 13, 14, 16, 17, 18}
THREE_POINT_QUESTIONS = {22, 23, 24, 25, 28, 29, 30, 34}

def parse_qid(q):
    try:
        return int(str(q).replace("Q", "").strip())
    except:
        return -1

def get_scale_options(qid):
    q_num = parse_qid(qid)
    if q_num in FOUR_POINT_QUESTIONS:
        return [0, 1, 2, 3]
    elif q_num in THREE_POINT_QUESTIONS:
        return [0, 1, 2]
    else:
        return [0, 1]

# ---------------------------------------------------------
# LOAD FRESH DATA (NO CACHE)
# ---------------------------------------------------------
def load_fresh_data():
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

# Load fresh data (no caching)
roll_map = load_fresh_data()

if not roll_map:
    st.error("No student responses found.")
    st.stop()

# ---------------------------------------------------------
# STUDENT SELECTION
# ---------------------------------------------------------
selected_roll = st.selectbox("Select Student Roll Number", sorted(roll_map.keys()))
student_data = roll_map[selected_roll]

available_tests = list(set([item["section"] for item in student_data]))
selected_test = st.selectbox("Select Test to Evaluate", available_tests)

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
    answer_cols = ["Answer", "Correct", "CorrectAnswer", "Ans", "AnswerKey"]
    for col in answer_cols:
        if col in row and pd.notna(row[col]):
            answer = str(row[col]).strip().lower()
            answer = answer.replace('"', '').replace("'", "").replace(".", "")
            return answer
    return None

def calculate_auto_scores(df, responses):
    mcq_score = 0
    likert_score = 0
    
    q_lookup = {}
    for _, row in df.iterrows():
        if 'QuestionID' in row and pd.notna(row['QuestionID']):
            qid_clean = str(row['QuestionID']).strip()
            q_lookup[qid_clean] = row
            if qid_clean.startswith(('A', 'L')) and len(qid_clean) > 1:
                q_lookup[qid_clean[1:]] = row
    
    for response in responses:
        question_id = None
        student_answer = None
        
        if 'QuestionID' in response:
            question_id = str(response['QuestionID']).strip()
        elif 'question_id' in response:
            question_id = str(response['question_id']).strip()
        
        if 'Response' in response:
            student_answer = str(response['Response']).strip().lower()
        elif 'response' in response:
            student_answer = str(response['response']).strip().lower()
        
        if not question_id or not student_answer:
            continue
            
        question_row = None
        possible_keys = [question_id]
        
        if question_id.startswith(('A', 'L', 'Q')):
            possible_keys.append(question_id[1:])
        if question_id.isdigit():
            possible_keys.append(f"A{question_id}")
            possible_keys.append(f"L{question_id}")
        
        for key in possible_keys:
            if key in q_lookup:
                question_row = q_lookup[key]
                break
        
        if question_row is None:
            continue
            
        q_type = str(question_row.get("Type", "")).lower().strip()
        
        if q_type == "mcq":
            correct_ans = get_correct_answer(question_row)
            if correct_ans and student_answer == correct_ans:
                mcq_score += 1
        elif q_type == "likert":
            try:
                resp_val = int(float(student_answer))
                points = max(0, min(4, resp_val - 1))
                likert_score += points
            except (ValueError, TypeError):
                pass
    
    return mcq_score, likert_score

def evaluate_manual_questions(df_test, responses, existing_manual_marks=None):
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
        
        student_answer = "No answer provided"
        for resp in responses:
            resp_qid = None
            if 'QuestionID' in resp:
                resp_qid = str(resp['QuestionID']).strip()
            if resp_qid == qid:
                if 'Response' in resp:
                    student_answer = str(resp['Response'])
                break
        
        st.write(f"**Q{qid}:** {qtext}")
        st.write(f"**Student's Answer:** {student_answer}")
        
        scale_options = get_scale_options(qid)
        default_mark = manual_marks.get(qid, 0)
        if default_mark not in scale_options:
            default_mark = 0
        
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
# CALCULATE REAL-TIME TOTALS
# ---------------------------------------------------------
def calculate_real_time_totals(student_data, current_test_id, current_test_score):
    """Calculate REAL-TIME totals including current edits"""
    grand_total = 0
    all_tests_data = []
    
    for item in student_data:
        if item["doc_id"] == current_test_id:
            # Use the current edited score (not saved yet)
            test_score = current_test_score
            status = "🔄 Editing"
        else:
            # Use saved score
            test_eval = item.get("evaluation", {})
            test_score = test_eval.get("final_total", 0)
            status = "✅ Saved"
        
        grand_total += test_score
        all_tests_data.append({
            "Test": item["section"],
            "Status": status,
            "Score": test_score
        })
    
    return grand_total, all_tests_data

# ---------------------------------------------------------
# MAIN EVALUATION INTERFACE
# ---------------------------------------------------------
st.header(f"📊 Evaluating: {selected_test}")

# FIXED: Get existing evaluation data - check if scores exist (not just if > 0)
existing_auto_mcq = existing_evaluation.get("auto_mcq", None)
existing_auto_likert = existing_evaluation.get("auto_likert", None)
existing_manual_marks = existing_evaluation.get("manual_marks", {})
existing_manual_total = existing_evaluation.get("manual_total", 0)
existing_final_total = existing_evaluation.get("final_total", 0)

# FIXED: Calculate scores - USE SAVED SCORES IF THEY EXIST
if existing_auto_mcq is not None and existing_auto_likert is not None:
    # Use existing saved scores (even if they are 0)
    auto_mcq = existing_auto_mcq
    auto_likert = existing_auto_likert
    st.info(f"📁 Using saved auto-scores: MCQ={auto_mcq}, Likert={auto_likert}")
else:
    # Calculate fresh scores only if no saved data exists
    auto_mcq, auto_likert = calculate_auto_scores(df_test, responses)
    st.success(f"🔄 Fresh auto-scores calculated: MCQ={auto_mcq}, Likert={auto_likert}")

# Manual evaluation (always show interface, but use existing marks as defaults)
manual_total, manual_marks = evaluate_manual_questions(df_test, responses, existing_manual_marks)

# Current test final score
final_score = auto_mcq + auto_likert + manual_total

# Calculate REAL-TIME totals (including current edits)
real_time_grand_total, progress_data = calculate_real_time_totals(student_data, doc_id, final_score)

# ---------------------------------------------------------
# DISPLAY REAL-TIME TOTALS
# ---------------------------------------------------------
st.header("🎯 Real-Time Evaluation Progress")

# Display current scores
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
    st.metric("Real-Time Grand Total", real_time_grand_total)

# Show progress
st.subheader("📋 Test Status")
progress_df = pd.DataFrame(progress_data)
st.dataframe(progress_df, use_container_width=True)

# Debug information to verify score sources
with st.expander("🔍 Debug: Score Sources"):
    st.write(f"Existing Auto MCQ: {existing_auto_mcq}")
    st.write(f"Existing Auto Likert: {existing_auto_likert}")
    st.write(f"Using saved scores: {existing_auto_mcq is not None}")

# ---------------------------------------------------------
# SAVE EVALUATION (WITH IMMEDIATE STATUS UPDATE)
# ---------------------------------------------------------
if st.button("💾 Save Evaluation & Update Grand Total"):
    try:
        # Save current test evaluation
        evaluation_data = {
            "auto_mcq": auto_mcq,
            "auto_likert": auto_likert,
            "manual_marks": manual_marks,
            "manual_total": manual_total,
            "final_total": final_score,
            "evaluated_at": firestore.SERVER_TIMESTAMP,
            "grand_total": real_time_grand_total
        }
        
        db.collection("student_responses").document(doc_id).update({
            "Evaluation": evaluation_data
        })
        
        # Update grand total in ALL documents for consistency
        all_docs = db.collection("student_responses").where("Roll", "==", selected_roll).stream()
        for doc in all_docs:
            doc.reference.update({
                "Evaluation.grand_total": real_time_grand_total
            })
        
        st.success(f"✅ Evaluation saved! Grand Total: {real_time_grand_total}")
        st.balloons()
        
        # FORCE COMPLETE REFRESH - Clear all caches and reload
        st.cache_data.clear()
        st.rerun()
        
    except Exception as e:
        st.error(f"❌ Save failed: {e}")

# ---------------------------------------------------------
# EXPORT TO CSV (WITH NA INSTEAD OF 0)
# ---------------------------------------------------------
st.header("📥 Export Results")

if st.button("📊 Download Complete Evaluation Report"):
    results_data = []
    
    for item in student_data:
        test_eval = item.get("evaluation", {})
        test_name = item["section"]
        
        # Use current test score if it's the one being edited
        if item["doc_id"] == doc_id:
            test_score = final_score
            auto_mcq_val = auto_mcq
            auto_likert_val = auto_likert
            manual_total_val = manual_total
        else:
            test_score = test_eval.get("final_total", 0)
            auto_mcq_val = test_eval.get("auto_mcq", 0)
            auto_likert_val = test_eval.get("auto_likert", 0)
            manual_total_val = test_eval.get("manual_total", 0)
        
        # Determine which test types are applicable
        df_test_for_export = banks[test_name]
        
        # Check if test has MCQ questions
        has_mcq = len(df_test_for_export[df_test_for_export["Type"] == "mcq"]) > 0
        # Check if test has Likert questions  
        has_likert = len(df_test_for_export[df_test_for_export["Type"] == "likert"]) > 0
        # Check if test has manual questions
        has_manual = len(df_test_for_export[df_test_for_export["Type"].isin(["short", "descriptive"])]) > 0
        
        # Replace 0 with NA if the test type doesn't exist
        auto_mcq_display = auto_mcq_val if has_mcq else "NA"
        auto_likert_display = auto_likert_val if has_likert else "NA" 
        manual_total_display = manual_total_val if has_manual else "NA"
        
        results_data.append({
            "Roll_Number": selected_roll,
            "Test": test_name,
            "Auto_MCQ_Score": auto_mcq_display,
            "Auto_Likert_Score": auto_likert_display,
            "Manual_Total": manual_total_display,
            "Test_Score": test_score
        })
    
    results_df = pd.DataFrame(results_data)
    
    # Add grand total row
    grand_total_row = pd.DataFrame([{
        "Roll_Number": selected_roll, 
        "Test": "GRAND TOTAL", 
        "Auto_MCQ_Score": "",
        "Auto_Likert_Score": "", 
        "Manual_Total": "", 
        "Test_Score": real_time_grand_total
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
    st.subheader("📋 Report Preview (with NA for non-applicable tests)")
    st.dataframe(final_df)
    
    # Also show explanation
    st.info("""
    **📝 Legend:**
    - **NA**: This test type is not applicable for the assessment
    - **0**: The student scored 0 in this test type
    - **Number**: The actual score achieved by the student
    """)
