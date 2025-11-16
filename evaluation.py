import streamlit as st
import pandas as pd
import json
import firebase_admin
from firebase_admin import credentials, firestore

# ---------------------------------------------------------------
# FIREBASE INIT
# ---------------------------------------------------------------
@st.cache_resource
def init_firebase():
    """Initialise Firebase only once."""
    if firebase_admin._apps:
        return firestore.client()
    try:
        if "firebase" in st.secrets:
            cfg = dict(st.secrets["firebase"])
            cred = credentials.Certificate(cfg)
            firebase_admin.initialize_app(cred)
        else:
            with open("firebase_key.json", "r") as f:
                cfg = json.load(f)
            cred = credentials.Certificate(cfg)
            firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Firebase initialization failed: {e}")
        return None
    return firestore.client()


db = init_firebase()
if db is None:
    st.stop()

# ---------------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------------
st.set_page_config(page_title="Faculty Evaluation", layout="wide")
st.title("🧑‍🏫 Faculty Evaluation – Text Questions")

# ---------------------------------------------------------------
# LOAD QUESTION BANKS
# ---------------------------------------------------------------
@st.cache_data
def load_questions():
    return {
        "Aptitude Test": pd.read_csv("aptitude.csv"),
        "Adaptability & Learning": pd.read_csv("adaptability_learning.csv"),
        "Communication Skills - Objective": pd.read_csv("communication_skills_objective.csv"),
        "Communication Skills - Descriptive": pd.read_csv("communication_skills_descriptive.csv"),
    }


question_banks = load_questions()

# Only these two have short questions to be manually evaluated
MANUAL_TESTS = ["Aptitude Test", "Communication Skills - Descriptive"]

ALL_TESTS = [
    "Aptitude Test",
    "Adaptability & Learning",
    "Communication Skills - Objective",
    "Communication Skills - Descriptive",
]

# ---------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------
def get_correct_answer(row):
    """Return the correct MCQ answer from any reasonable column name."""
    for col in ["Answer", "CorrectAnswer", "Correct", "Ans", "AnswerKey"]:
        if col in row and not pd.isna(row[col]):
            return str(row[col]).strip()
    return None


def likert_to_score(v):
    """Map 1–5 Likert value to 0–4 score."""
    try:
        v = int(v)
    except Exception:
        return 0
    return max(0, v - 1)  # 1→0, 2→1, 3→2, 4→3, 5→4


def calc_mcq(df, responses):
    total = 0
    for r in responses:
        qid = str(r.get("QuestionID", "")).strip()
        ans = str(r.get("Response", "")).strip()
        row_df = df[df["QuestionID"].astype(str).str.strip() == qid]
        if row_df.empty:
            continue
        row = row_df.iloc[0]
        if str(row["Type"]).strip().lower() != "mcq":
            continue
        correct = get_correct_answer(row)
        if correct and ans == correct:
            total += 1
    return total


def calc_likert(df, responses):
    total = 0
    for r in responses:
        qid = str(r.get("QuestionID", "")).strip()
        ans = r.get("Response", None)
        row_df = df[df["QuestionID"].astype(str).str.strip() == qid]
        if row_df.empty:
            continue
        row = row_df.iloc[0]
        if str(row["Type"]).strip().lower() != "likert":
            continue
        total += likert_to_score(ans)
    return total


# ---------------------------------------------------------------
# BUILD STUDENT MAP
# ---------------------------------------------------------------
docs = db.collection("student_responses").stream()
student_map = {}          # roll -> list of (section, doc_id)

for d in docs:
    data = d.to_dict()
    roll = data.get("Roll")
    section = data.get("Section")
    if not roll or not section:
        continue
    student_map.setdefault(roll, []).append((section, d.id))

if not student_map:
    st.error("No student_responses documents found in Firestore.")
    st.stop()

# ---------------------------------------------------------------
# SELECT STUDENT
# ---------------------------------------------------------------
all_rolls = sorted(student_map.keys())
selected_roll = st.selectbox("Select Student Roll Number", all_rolls)

# ---------------------------------------------------------------
# GATHER PER-SECTION DATA FOR THIS STUDENT
# ---------------------------------------------------------------
sections_info = {}        # section -> info dict
total_mcq_all = 0
total_likert_all = 0

for section, doc_id in student_map[selected_roll]:
    # Skip any section for which we don't have a CSV
    if section not in question_banks:
        continue

    doc_ref = db.collection("student_responses").document(doc_id)
    doc_data = doc_ref.get().to_dict() or {}
    responses = doc_data.get("Responses", [])

    df = question_banks[section].copy()

    # Ensure necessary columns exist
    if "Type" not in df.columns:
        df["Type"] = ""
    if "QuestionID" not in df.columns:
        df["QuestionID"] = [str(i + 1) for i in range(len(df))]

    mcq = calc_mcq(df, responses)
    likert = calc_likert(df, responses)
    total_mcq_all += mcq
    total_likert_all += likert

    eval_data = doc_data.get("Evaluation", {}) or {}
    saved_text_total = int(eval_data.get("text_total", 0) or 0)
    saved_marks = eval_data.get("text_marks", {}) or {}

    sections_info[section] = {
        "doc_id": doc_id,
        "df": df,
        "responses": responses,
        "mcq": mcq,
        "likert": likert,
        "saved_text_total": saved_text_total,
        "saved_marks": saved_marks,
    }

# Show overall auto-evaluated totals
st.markdown("### Auto-evaluated totals (all tests)")
st.write(f"**MCQ Score (Auto):** {total_mcq_all}")
st.write(f"**Likert Score (Auto):** {total_likert_all}")

# ---------------------------------------------------------------
# WHICH MANUAL TESTS DOES THIS STUDENT ACTUALLY HAVE?
# ---------------------------------------------------------------
manual_tests_taken = [
    section for section, _ in student_map[selected_roll]
    if section in MANUAL_TESTS and section in sections_info
]

if not manual_tests_taken:
    # No short-answer tests for this student – just compute grand total from saved text totals
    total_text_all = sum(info["saved_text_total"] for info in sections_info.values())
    grand_total = total_mcq_all + total_likert_all + total_text_all
    st.success("No short-answer questions for this student. All evaluation is auto.")
    st.subheader(f"GRAND TOTAL (All Tests) = {grand_total}")
    st.stop()

# ---------------------------------------------------------------
# SELECT TEST FOR MANUAL TEXT EVALUATION
# ---------------------------------------------------------------
selected_test = st.selectbox("Select Test for Manual Evaluation", manual_tests_taken)

info = sections_info[selected_test]
df = info["df"]
responses = info["responses"]
saved_marks = info["saved_marks"]

short_df = df[df["Type"].astype(str).str.lower() == "short"]

st.markdown(f"### Manual text evaluation – {selected_test}")

# ---------------------------------------------------------------
# BUILD UI FOR SHORT QUESTIONS
# ---------------------------------------------------------------
for _, row in short_df.iterrows():
    qid = str(row["QuestionID"])
    qtext = str(row["Question"])

    student_ans = next(
        (r.get("Response", "") for r in responses if str(r.get("QuestionID", "")) == qid),
        "(no answer)"
    )

    # Decide between 0–1 and 0–3 scale based on wording (simple heuristic)
    qlower = qtext.lower()
    is_three_point = (" 3 " in qlower) or ("three" in qlower) or ("any 3" in qlower)
    scale = [0, 1, 2, 3] if is_three_point else [0, 1]

    saved_mark = int(saved_marks.get(qid, 0) or 0)
    if saved_mark not in scale:
        saved_mark = 0
    default_index = scale.index(saved_mark)

    key = f"{selected_roll}__{selected_test}__{qid}"

    with st.expander(f"{qid}: {qtext}", expanded=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"**Student Answer:** {student_ans}")
        with col2:
            st.radio(
                "Marks:",
                scale,
                index=default_index,
                horizontal=True,
                key=key,
            )

st.markdown("---")

# ---------------------------------------------------------------
# SAVE + SHOW TOTALS
# ---------------------------------------------------------------
if "last_totals" not in st.session_state:
    st.session_state["last_totals"] = None

if st.button("💾 Save Evaluation for this Test"):
    # 1) Collect marks for this test
    text_marks = {}
    text_total = 0
    for _, row in short_df.iterrows():
        qid = str(row["QuestionID"])
        key = f"{selected_roll}__{selected_test}__{qid}"
        mark = int(st.session_state.get(key, 0))
        text_marks[qid] = mark
        text_total += mark

    # 2) Save to Firestore
    doc_id = info["doc_id"]
    db.collection("student_responses").document(doc_id).set({
        "Evaluation": {
            "text_marks": text_marks,
            "text_total": text_total,
        }
    }, merge=True)

    # 3) Update in-memory text total for this test
    sections_info[selected_test]["saved_text_total"] = text_total

    # 4) Compute grand total using:
    #    - all MCQ + Likert
    #    - text_total for this test (current)
    #    - text_total for other tests (saved values)
    other_text_total = sum(
        sec_info["saved_text_total"]
        for sec_name, sec_info in sections_info.items()
        if sec_name != selected_test
    )
    grand_total = total_mcq_all + total_likert_all + other_text_total + text_total

    st.session_state["last_totals"] = {
        "roll": selected_roll,
        "section": selected_test,
        "text_total": text_total,
        "grand_total": grand_total,
    }
    st.success("Evaluation saved for this test ✅")

# ---------------------------------------------------------------
# DISPLAY TEXT MARKS + GRAND TOTAL AFTER SAVE
# ---------------------------------------------------------------
lt = st.session_state.get("last_totals")
if lt and lt["roll"] == selected_roll and lt["section"] == selected_test:
    st.subheader(f"Text Marks (This Test): {lt['text_total']}")
    st.subheader(f"GRAND TOTAL (All Tests) = {lt['grand_total']}")
else:
    st.info("After awarding marks, click **Save Evaluation for this Test** to see text marks and the grand total.")
