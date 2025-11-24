import json
import pandas as pd
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(page_title="Faculty Evaluation Dashboard", layout="wide")
st.title("👩‍🏫 Faculty Evaluation Dashboard (FAST MODE)")


# ---------------------------------------------------------
# FIREBASE INIT
# ---------------------------------------------------------
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


# ---------------------------------------------------------
# LOAD ALL CSVs FROM DEPLOYMENT FOLDER
# ---------------------------------------------------------
CSV_PATHS = {
    "Aptitude Test": "/mount/src/skill2025/aptitude.csv",
    "Adaptability & Learning": "/mount/src/skill2025/adaptability_learning.csv",
    "Communication Skills - Objective": "/mount/src/skill2025/communication_skills_objective.csv",
    "Communication Skills - Descriptive": "/mount/src/skill2025/communication_skills_descriptive.csv",
}


@st.cache_data
def load_question_banks():
    banks = {}
    for section, path in CSV_PATHS.items():
        try:
            df = pd.read_csv(path)
            df.columns = [c.strip() for c in df.columns]
            df["Type"] = df["Type"].astype(str).str.lower()
            banks[section] = df
        except Exception as e:
            st.error(f"Error loading {path}: {e}")
            banks[section] = pd.DataFrame()
    return banks


question_banks = load_question_banks()


# ---------------------------------------------------------
# FIXED MARKING QID RULES
# ---------------------------------------------------------
FOUR_MARK_QIDS = {12, 13, 14, 16, 17, 18}
THREE_MARK_QIDS = {22, 23, 24, 25, 28, 29, 30, 34}


def parse_qid(q):
    s = str(q).replace("Q", "").strip()
    try:
        return int(s)
    except:
        return -1


def scale_for_qid(qid):
    q = parse_qid(qid)
    if q in FOUR_MARK_QIDS:
        return [0, 1, 2, 3]
    if q in THREE_MARK_QIDS:
        return [0, 1, 2]
    return [0, 1]


# ---------------------------------------------------------
# LOAD STUDENT RESPONSES
# ---------------------------------------------------------
def load_students():
    roll_map = {}
    doc_refs = list(db.collection("student_responses").list_documents())

    for ref in doc_refs:
        snap = ref.get()
        if not snap.exists:
            continue

        data = snap.to_dict()
        roll = data.get("Roll")
        section = data.get("Section")

        if not roll or not section:
            continue

        responses = data.get("Responses")
        if not isinstance(responses, list):
            responses = []

        data["Responses"] = responses

        if roll not in roll_map:
            roll_map[roll] = []

        roll_map[roll].append((ref.id, data))

    return roll_map


roll_to_docs = load_students()
rolls_sorted = sorted(roll_to_docs.keys())
selected_roll = st.selectbox("Select Student Roll Number", rolls_sorted)
docs_for_roll = roll_to_docs[selected_roll]


# ---------------------------------------------------------
# SCORING FUNCTIONS
# ---------------------------------------------------------
def get_correct_answer(row):
    for col in ["Answer", "Correct", "CorrectAnswer", "Ans", "AnswerKey"]:
        if col in row and pd.notna(row[col]):
            return str(row[col]).strip()
    return None


def calc_mcq(df, responses):
    if df is None or df.empty: return 0
    score = 0
    df_idx = df.set_index(df["QuestionID"].astype(str), drop=False)

    for r in responses:
        qid = str(r.get("QuestionID", "")).strip()
        ans = str(r.get("Response", "")).strip()
        if not qid or not ans: continue
        if qid not in df_idx.index: continue

        row = df_idx.loc[qid]
        if row["Type"] != "mcq": continue

        correct = get_correct_answer(row)
        if ans == correct:
            score += 1

    return score


def likert_to_score(v):
    try:
        v = int(v)
        return max(0, min(4, v - 1))
    except:
        return 0


def calc_likert(df, responses):
    if df is None or df.empty: return 0
    total = 0
    df_idx = df.set_index(df["QuestionID"].astype(str), drop=False)

    for r in responses:
        qid = str(r.get("QuestionID", ""))
        raw = r.get("Response", "")

        if qid not in df_idx.index: continue
        row = df_idx.loc[qid]

        if row["Type"] != "likert":
            continue

        total += likert_to_score(raw)

    return total


# ---------------------------------------------------------
# MANUAL TEST SELECTION
# ---------------------------------------------------------
MANUAL_TESTS = ["Aptitude Test", "Communication Skills - Descriptive"]

manual_tests_available = sorted([
    data.get("Section")
    for _, data in docs_for_roll
    if data.get("Section") in MANUAL_TESTS
])

selected_test = st.selectbox("Select Test for Manual Evaluation", manual_tests_available)

# Fetch document
selected_doc_id = None
selected_doc_data = None
for doc_id, data in docs_for_roll:
    if data.get("Section") == selected_test:
        selected_doc_id = doc_id
        selected_doc_data = data
        break

df_test = question_banks[selected_test]
responses_test = selected_doc_data.get("Responses", [])

saved_eval = selected_doc_data.get("Evaluation", {})
saved_text_marks = saved_eval.get("text_marks", {})


# ---------------------------------------------------------
# BUILD MARK ENTRY (FAST MODE — NO AUTO UPDATE)
# ---------------------------------------------------------
st.markdown("## ✍️ Manual Evaluation")

short_df = df_test[df_test["Type"] == "short"]

marks_given = {}
text_current_total = 0

for _, row in short_df.iterrows():
    qid = str(row["QuestionID"])
    qtext = str(row["Question"])

    stu_ans = "(no answer)"
    for r in responses_test:
        if str(r.get("QuestionID")) == qid:
            stu_ans = str(r.get("Response", "(no answer)"))
            break

    scale = scale_for_qid(qid)
    default = saved_text_marks.get(qid, 0)
    if default not in scale:
        default = 0

    with st.expander(f"Q{qid}: {qtext}", expanded=True):
        st.write(f"**Answer:** {stu_ans}")
        mark = st.radio(
            "Marks",
            scale,
            horizontal=True,
            index=scale.index(default),
            key=f"{selected_roll}_{selected_test}_{qid}"
        )

    marks_given[qid] = mark
    text_current_total += mark


# ---------------------------------------------------------
# CALCULATE BUTTON (NO AUTO UPDATE)
# ---------------------------------------------------------
st.markdown("## 🧮 Calculate Marks (Preview Only)")

if st.button("Calculate Marks"):
    mcq_sel = calc_mcq(df_test, responses_test)
    likert_sel = calc_likert(df_test, responses_test)
    final_sel = mcq_sel + likert_sel + text_current_total

    st.success(f"""
### ✔ Marks Calculated
- MCQ: **{mcq_sel}**
- Likert: **{likert_sel}**
- Text: **{text_current_total}**

### 👉 FINAL SCORE (THIS TEST): **{final_sel}**
""")


# ---------------------------------------------------------
# SAVE BUTTON
# ---------------------------------------------------------
st.markdown("## 💾 Save Final Evaluation")

if st.button("Save Evaluation for This Test"):
    mcq_sel = calc_mcq(df_test, responses_test)
    likert_sel = calc_likert(df_test, responses_test)
    text_sel = text_current_total
    final_sel = mcq_sel + likert_sel + text_sel

    # Update Firestore
    db.collection("student_responses").document(selected_doc_id).set(
        {
            "Evaluation": {
                "text_marks": marks_given,
                "text_total": text_sel,
                "mcq_total": mcq_sel,
                "likert_total": likert_sel,
                "final_total": final_sel,
            }
        },
        merge=True,
    )

    # Compute new grand total
    grand = 0
    for doc_id, data in docs_for_roll:
        ev = data.get("Evaluation", {})
        if doc_id == selected_doc_id:
            grand += final_sel
        elif "final_total" in ev:
            grand += int(ev.get("final_total", 0))
        else:
            df = question_banks[data.get("Section")]
            resp = data.get("Responses", [])
            grand += calc_mcq(df, resp) + calc_likert(df, resp)

    # Save grand total to all docs
    batch = db.batch()
    for doc_id, _ in docs_for_roll:
        ref = db.collection("student_responses").document(doc_id)
        batch.set(ref, {"Evaluation": {"grand_total": grand}}, merge=True)
    batch.commit()

    st.success(f"""
### 🎉 Evaluation Saved Successfully!
Final Score: **{final_sel}**  
Updated GRAND TOTAL: **{grand}**
""")
