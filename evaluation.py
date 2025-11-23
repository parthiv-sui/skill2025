# ===============================================================
# FACULTY EVALUATION DASHBOARD (FINAL – OPTIMIZED)
# ===============================================================

import json
import pandas as pd
import streamlit as st

import firebase_admin
from firebase_admin import credentials, firestore

# ---------------------------------------------------------------
# PAGE CONFIG (FAST, CLEAN, NO DEBUG LOGS)
# ---------------------------------------------------------------
st.set_page_config(page_title="Faculty Evaluation Dashboard", layout="wide")
st.title("👩‍🏫 Faculty Evaluation Dashboard")

# ---------------------------------------------------------------
# FIREBASE INITIALIZATION (CACHED)
# ---------------------------------------------------------------
@st.cache_resource
def init_firebase():
    try:
        if firebase_admin._apps:
            return firestore.client()

        if "firebase" in st.secrets:
            cfg = dict(st.secrets["firebase"])
        else:
            with open("firebase_key.json", "r") as f:
                cfg = json.load(f)

        cred = credentials.Certificate(cfg)
        firebase_admin.initialize_app(cred)
        return firestore.client()

    except Exception as e:
        st.error(f"Firebase init failed: {e}")
        return None

db = init_firebase()
if db is None:
    st.stop()

# ---------------------------------------------------------------
# LOAD QUESTION BANK CSVs (CACHED)
# ---------------------------------------------------------------
@st.cache_data
def load_question_banks():
    files = {
        "Adaptability & Learning": "/mnt/data/adaptability_learning.csv",
        "Aptitude Test": "/mnt/data/aptitude.csv",
        "Communication Skills - Objective": "/mnt/data/communication_skills_objective.csv",
        "Communication Skills - Descriptive": "/mnt/data/communication_skills_descriptive.csv",
    }

    banks = {}
    for section, path in files.items():
        df = pd.read_csv(path)
        df.columns = [c.strip() for c in df.columns]
        df["Type"] = df["Type"].astype(str).str.lower()
        df["QuestionID"] = df["QuestionID"].astype(str).str.strip()
        banks[section] = df
    return banks

question_banks = load_question_banks()
# ===============================================================
#                   SCORING FUNCTIONS
# ===============================================================

# FIXED SCORING FOR DESCRIPTIVE QUESTIONS
FOUR_MARK = {12, 13, 14, 16, 17, 18}
THREE_MARK = {22, 23, 24, 25, 28, 29, 30, 34}

def qid_to_int(qid):
    try:
        return int(str(qid).replace("Q", "").strip())
    except:
        return -1

def mark_scale(qid):
    q = qid_to_int(qid)
    if q in FOUR_MARK: return [0,1,2,3]
    if q in THREE_MARK: return [0,1,2]
    return [0,1]

def get_correct(row):
    for col in ["Correct", "Answer", "Ans", "AnswerKey"]:
        if col in row and pd.notna(row[col]):
            return str(row[col]).strip()
    return None

def likert_map(value):
    try:
        v = int(value)
        return max(0, min(4, v - 1))
    except:
        return 0

def calc_mcq(df, responses):
    if df is None or responses is None: return 0
    score = 0
    df_idx = df.set_index(df["QuestionID"], drop=False)

    for r in responses:
        qid = str(r.get("QuestionID","")).strip()
        ans = str(r.get("Response","")).strip()

        if not qid or not ans: continue
        if qid not in df_idx.index: continue

        row = df_idx.loc[qid]
        if row["Type"] != "mcq": continue

        if ans == get_correct(row):
            score += 1
    return score

def calc_likert(df, responses):
    if df is None or responses is None: return 0
    total = 0
    df_idx = df.set_index(df["QuestionID"], drop=False)

    for r in responses:
        qid = str(r.get("QuestionID","")).strip()
        val = r.get("Response")

        if qid not in df_idx.index: continue
        if df_idx.loc[qid]["Type"] != "likert": continue

        total += likert_map(val)
    return total
# ===============================================================
#                 LOAD STUDENTS FROM FIRESTORE
# ===============================================================

@st.cache_data
def load_students():
    roll_map = {}
    for ref in db.collection("student_responses").list_documents():
        snap = ref.get()
        if not snap.exists: continue

        data = snap.to_dict()
        roll = data.get("Roll")
        section = data.get("Section")
        if not roll or not section: continue

        responses = data.get("Responses")
        if not isinstance(responses, list):
            responses = []
        data["Responses"] = responses

        if roll not in roll_map:
            roll_map[roll] = []
        roll_map[roll].append((ref.id, data))
    return roll_map

def compute_auto_scores_for_roll(docs_for_roll):
    """
    Computes TOTAL MCQ and TOTAL Likert for ALL tests of the student.
    Returns:
        doc_scores: {doc_id: {mcq:int, likert:int}}
        mcq_sum: int
        likert_sum: int
    """
    doc_scores = {}
    mcq_sum = 0
    likert_sum = 0

    for section, doc_id in docs_for_roll:
        df = question_banks.get(section)

        try:
            snap = db.collection("student_responses").document(doc_id).get()
            data = snap.to_dict() or {}
        except:
            data = {}

        responses = data.get("Responses") or []

        # Evaluate MCQ & Likert
        mcq = calc_mcq(df, responses)
        likert = calc_likert(df, responses)

        doc_scores[doc_id] = {"mcq": mcq, "likert": likert}
        mcq_sum += mcq
        likert_sum += likert

    return doc_scores, mcq_sum, likert_sum


roll_to_docs = load_students()
if not roll_to_docs:
    st.warning("No student responses available.")
    st.stop()

selected_roll = st.selectbox("Select Student Roll Number", sorted(roll_to_docs.keys()))
docs_for_roll = roll_to_docs[selected_roll]

manual_tests = ["Aptitude Test", "Communication Skills - Descriptive"]
tests_available = sorted([data["Section"] for _,data in docs_for_roll if data["Section"] in manual_tests])

selected_test = st.selectbox("Select Test", tests_available)

doc_id = None
doc_data = None
for did, data in docs_for_roll:
    if data["Section"] == selected_test:
        doc_id, doc_data = did, data
        break

df_test = question_banks[selected_test]
responses = doc_data["Responses"]
existing = doc_data.get("Evaluation", {})
saved_marks = existing.get("text_marks", {})
# ===============================================================
#                 MANUAL TEXT MARKING UI
# ===============================================================

short_df = df_test[df_test["Type"] == "short"]

marks_given = {}
text_total = 0

st.markdown("### ✍️ Manual Descriptive Evaluation")

for _, row in short_df.iterrows():
    qid = str(row["QuestionID"])
    qtext = row["Question"]

    ans = "(no answer)"
    for r in responses:
        if str(r.get("QuestionID")) == qid:
            ans = str(r.get("Response","(no answer)"))
            break

    scale = mark_scale(qid)
    default = saved_marks.get(qid, 0)
    if default not in scale: default = 0

    with st.expander(f"Q{qid}: {qtext}", expanded=True):
        st.markdown(f"**Student Answer:** {ans}")
        mark = st.radio("Marks:", scale, index=scale.index(default),
                        horizontal=True, key=f"{selected_roll}_{qid}")

    marks_given[qid] = mark
    text_total += mark

# ===============================================================
#           CALCULATE BUTTON (PREVIEW ONLY)
# ===============================================================

if st.button("📌 Calculate Marks"):
    mcq = calc_mcq(df_test, responses)
    likert = calc_likert(df_test, responses)
    final_score = mcq + likert + text_total

    st.success(f"""
### Preview Marks
**MCQ:** {mcq}  
**Likert:** {likert}  
**Text:** {text_total}  

### **Final Score: {final_score}**
(Not saved yet)
""")

# ===============================================================
#           SAVE BUTTON (FINAL + GRAND TOTAL)
# ===============================================================

if st.button("💾 Save Evaluation"):
    mcq = calc_mcq(df_test, responses)
    likert = calc_likert(df_test, responses)
    final_score = mcq + likert + text_total

    # Save this test
    db.collection("student_responses").document(doc_id).set(
        {"Evaluation": {
            "text_marks": marks_given,
            "text_total": text_total,
            "mcq_total": mcq,
            "likert_total": likert,
            "final_total": final_score
        }},
        merge=True
    )

    # Compute grand total across ALL tests
    grand = 0
    for did, data in docs_for_roll:
        ev = data.get("Evaluation", {})
        if did == doc_id:
            grand += final_score
        else:
            if "final_total" in ev:
                grand += int(ev["final_total"])
            else:
                df = question_banks[data["Section"]]
                resp = data["Responses"]
                auto = calc_mcq(df, resp) + calc_likert(df, resp) + int(ev.get("text_total",0))
                grand += auto

    # Save grand_total in all docs
    batch = db.batch()
    for did,_ in docs_for_roll:
        ref = db.collection("student_responses").document(did)
        batch.set(ref, {"Evaluation": {"grand_total": grand}}, merge=True)
    batch.commit()

    st.success(f"Saved! Grand Total = {grand}")
