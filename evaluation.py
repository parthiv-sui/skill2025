import json
import pandas as pd
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from io import StringIO
import time
from datetime import datetime

# ---------------------------------------------------------
# CACHE CLEARANCE FUNCTION
# ---------------------------------------------------------
def clear_all_caches():
    """Clear all caches to force data refresh"""
    try:
        # Clear streamlit caches
        st.cache_data.clear()
        st.cache_resource.clear()
        return True
    except Exception as e:
        st.error(f"Cache clearance warning: {e}")
        return False

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(page_title="Faculty Evaluation Dashboard", layout="wide")
st.title("👩‍🏫 Faculty Evaluation Dashboard")

# Add refresh button at the top
col1, col2 = st.columns([4, 1])
with col2:
    if st.button("🔄 Clear Cache & Refresh"):
        clear_all_caches()
        st.rerun()

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
# LOAD FRESH DATA FUNCTION
# ---------------------------------------------------------
@st.cache_data(ttl=30)  # Cache for only 30 seconds
def load_all_student_data():
    """Load all student data from Firebase"""
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

# ---------------------------------------------------------
# INITIAL DATA LOAD
# ---------------------------------------------------------
roll_map = load_all_student_data()

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
# CALCULATE REAL-TIME TOTALS WITH SIMPLIFIED STATUS
# ---------------------------------------------------------
def calculate_real_time_totals(student_data, current_test_id, current_test_score):
    """Calculate REAL-TIME totals including current edits"""
    grand_total = 0
    all_tests_data = []
    
    for item in student_data:
        test_eval = item.get("evaluation", {})
        has_evaluation = bool(test_eval) and test_eval.get("final_total") is not None
        
        if item["doc_id"] == current_test_id:
            saved_final = test_eval.get("final_total", None)
        
            # If current calculated = saved -> it is saved
            if saved_final == current_test_score:
                status = "✅ Saved"
            else:
                status = "✏️ Editing"
        
            test_score = current_test_score
        
        else:
            saved_final = test_eval.get("final_total", None)
        
            if saved_final is None:
                status = "⏳ Pending"
                test_score = 0
            else:
                status = "✅ Saved"
                test_score = saved_final

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

# Get existing evaluation data
existing_auto_mcq = existing_evaluation.get("auto_mcq", None)
existing_auto_likert = existing_evaluation.get("auto_likert", None)
existing_manual_marks = existing_evaluation.get("manual_marks", {})
existing_manual_total = existing_evaluation.get("manual_total", 0)
existing_final_total = existing_evaluation.get("final_total", 0)

# ALWAYS RECALCULATE AUTO SCORES
auto_mcq, auto_likert = calculate_auto_scores(df_test, responses)

# Manual evaluation
manual_total, manual_marks = evaluate_manual_questions(df_test, responses, existing_manual_marks)

# Current test final score
final_score = auto_mcq + auto_likert + manual_total

# Calculate REAL-TIME totals
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

# Show progress with enhanced status indicators
st.subheader("📋 Evaluation Status Overview")

# Display all tests
st.write(f"**Student:** {selected_roll} | **Total Tests:** {len(progress_data)}")

# Create a more visual status table
for test_data in progress_data:
    test_name = test_data["Test"]
    status = test_data["Status"]
    score = test_data["Score"]
    
    col1, col2, col3 = st.columns([3, 2, 1])
    
    with col1:
        st.write(f"**{test_name}**")
    
    with col2:
        if status == "✅ Saved":
            st.success("✅ Saved")
        elif status == "✏️ Editing":
            st.warning("✏️ Editing")
        elif status == "⏳ Pending":
            st.error("⏳ Pending")
        else:
            st.write(status)
    
    with col3:
        st.write(f"**{score}**")

# Status Legend
with st.expander("📖 Status Legend"):
    st.success("✅ Saved - Evaluation completed and saved")
    st.warning("✏️ Editing - Currently being evaluated") 
    st.error("⏳ Pending - Not yet evaluated")

st.write("---")

# ---------------------------------------------------------
# DEBUG: VERIFY FIREBASE DATA
# ---------------------------------------------------------
with st.expander("🔍 Debug: Verify Current Firebase Data"):
    try:
        doc_ref = db.collection("student_responses").document(doc_id)
        firebase_data = doc_ref.get().to_dict()
        if firebase_data and 'Evaluation' in firebase_data:
            st.write("✅ Current Firebase Evaluation Data:")
            st.json(firebase_data['Evaluation'])
            
            # Show data freshness
            evaluated_at = firebase_data['Evaluation'].get('evaluated_at')
            if evaluated_at:
                st.write(f"**Last Saved:** {evaluated_at}")
        else:
            st.write("❌ No evaluation data in Firebase")
    except Exception as e:
        st.error(f"Debug error: {e}")

# ---------------------------------------------------------
# SAVE EVALUATION - ENHANCED WITH CACHE CLEARANCE
# ---------------------------------------------------------
if st.button("💾 Save Evaluation & Update Grand Total", type="primary"):
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
        
        # Save to Firebase
        db.collection("student_responses").document(doc_id).update({
            "Evaluation": evaluation_data
        })
        
        # Update grand total in ALL documents for consistency
        all_docs = db.collection("student_responses").where("Roll", "==", selected_roll).stream()
        for doc in all_docs:
            doc.reference.update({
                "Evaluation.grand_total": real_time_grand_total
            })
        
        st.success(f"✅ Evaluation saved for {selected_test}!")
        st.success(f"📊 Grand Total Updated: {real_time_grand_total}")
        st.balloons()
        
        # CRITICAL: Clear caches and force complete reload
        if clear_all_caches():
            st.info("🔄 Caches cleared - refreshing data...")
        
        # Add a small delay to ensure Firebase updates
        time.sleep(2)
        
        # Force complete reload
        st.rerun()
        
    except Exception as e:
        st.error(f"❌ Save failed: {e}")
        st.error("Please try again or check Firebase connection")

# ---------------------------------------------------------
# EXPORT TO CSV
# ---------------------------------------------------------
st.header("📥 Export Results")

if st.button("📊 Download Complete Evaluation Report"):
    results_data = []
    
    for item in student_data:
        test_name = item["section"]
        test_responses = item["responses"]
        test_df = banks[test_name]
        
        # Calculate fresh scores
        auto_mcq_val, auto_likert_val = calculate_auto_scores(test_df, test_responses)
        
        if item["doc_id"] == doc_id:
            test_score = final_score
            manual_total_val = manual_total
        else:
            existing_eval = item.get("evaluation", {})
            manual_total_val = existing_eval.get("manual_total", 0)
            test_score = auto_mcq_val + auto_likert_val + manual_total_val
        
        # Determine test types
        has_mcq = len(test_df[test_df["Type"] == "mcq"]) > 0
        has_likert = len(test_df[test_df["Type"] == "likert"]) > 0
        has_manual = len(test_df[test_df["Type"].isin(["short", "descriptive"])]) > 0
        
        # Replace 0 with NA if not applicable
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
    export_grand_total = sum(item["Test_Score"] for item in results_data)
    
    # Add grand total row
    grand_total_row = pd.DataFrame([{
        "Roll_Number": selected_roll, 
        "Test": "GRAND TOTAL", 
        "Auto_MCQ_Score": "",
        "Auto_Likert_Score": "", 
        "Manual_Total": "", 
        "Test_Score": export_grand_total
    }])
    
    final_df = pd.concat([results_df, grand_total_row], ignore_index=True)
    
    # Download
    csv = final_df.to_csv(index=False)
    st.download_button(
        label="⬇️ Download Complete Report (CSV)",
        data=csv,
        file_name=f"complete_evaluation_{selected_roll}.csv",
        mime="text/csv"
    )
    
    # Preview
    st.subheader("📋 Report Preview")
    st.dataframe(final_df)

# ---------------------------------------------------------
# SIDEBAR STATUS
# ---------------------------------------------------------
st.sidebar.write("---")
st.sidebar.subheader("🔄 System Status")
st.sidebar.write(f"Data loaded: {datetime.now().strftime('%H:%M:%S')}")
st.sidebar.write(f"Students loaded: {len(roll_map)}")
st.sidebar.write(f"Tests for {selected_roll}: {len(student_data)}")

if st.sidebar.button("🔄 Refresh Data Only"):
    clear_all_caches()
    st.success("Data refresh triggered!")
    time.sleep(1)
    st.rerun()
