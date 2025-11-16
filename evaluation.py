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
    for col in ["Answer", "CorrectAnswer", "Correct", "Ans", "AnswerKey"]:
        if col in row and not pd.isna(row[col]):
            return str(row[col]).strip()
    return None


def likert_to_score(v):
    try:
        v = int(v)
    except Exception:
        return 0
    # 1→0, 2→1, 3→2, 4→3, 5→4
    return max(0, v - 1)


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
doc_cache = {}            # doc_id -> dict

for d in docs:
    data = d.to_dict()
    doc_cache[d.id] = data
    roll = data.get("Roll")
    section = data.get("Section")
    if not roll or not section:
        continue
    student_map.setdefault(roll, []).append((section, d.id))

if not student_map:
    st.error("No student_responses documents found.")
    st.stop()

all_rolls = sorted(student_map.keys())
selected_roll = st.selectbox("Select Student Roll Number", all_rolls)

# ---------------------------------------------------------------
# PRECOMPUTE AUTO TOTALS + SAVED TEXT TOTALS FOR THIS STUDENT
# ---------------------------------------------------------------
total_mcq_all = 0
total_likert_all = 0
per_section = {}          # section -> dict{doc_id, df, responses, saved_text_total, saved_marks}

for section, doc_id in student_map[selected_roll]:
    if section not in ALL_TESTS:
        continue

    data = doc_cache.get(doc_id) or db.collection("student_responses").document(doc_id).get().to_dict()
    doc_cache[doc_id] = data
    responses = data.get("Responses", [])
    df = question_banks[section]

    mcq = calc_mcq(df, responses)
    likert = calc_likert(df, responses)
    total_mcq_all += mcq
    total_likert_all += likert

    eval_data = data.get("Evaluation", {})
    saved_text_total = int(eval_data.get("text_total", 0) or 0)
    saved_marks = eval_data.get("text_marks", {}) or {}

    per_section[section] = {
        "doc_id": doc_id,
        "df": df,
        "responses": responses,
        "mcq": mcq,
        "likert": likert,
        "saved_text_total": saved_text_total,
        "saved_marks": saved_marks,
    }

# ---------------------------------------------------------------
# SELECT TEST FOR MANUAL EVALUATION
# ---------------------------------------------------------------
tests_taken = [sec for sec, _ in student_map[selected_roll] if sec in ALL_TESTS]

if not tests_taken:
    st.success("No tests found for this student.")
    st.stop()

selected_test = st.selectbox("Select Test for Manual Evaluation", tests_taken)

info = per_section[selected_test]
df = info["df"]
responses = info["responses"]
saved_marks = info["saved_marks"]

short_df = df[df["Type"].astype(str).str.lower() == "short"]

# ---------------------------------------------------------------
# MANUAL TEXT EVALUATION UI
# ---------------------------------------------------------------
st.markdown(f"### Manual Evaluation – {selected_test}")

for _, row in short_df.iterrows():
    qid = str(row["QuestionID"])
    qtext = str(row["Question"])

    student_ans = next(
        (r.get("Response", "") for r in responses if str(r.get("QuestionID", "")) == qid),
        "(no answer)"
    )

    # Decide between 0–1 and 0–3 based on wording (very simple rule; adjust if needed)
    qlower = qtext.lower()
    is_three_point = (" 3 " in qlower) or ("three" in qlower) or ("any 3" in qlower)
    scale = [0, 1, 2, 3] if is_three_point else [0, 1]

    saved_mark = int(saved_marks.get(qid, 0) or 0)
    if saved_mark not in scale:
        saved_mark = 0
    default_index = scale.index(saved_mark)

    key = f"{selected_roll}__{selected_test}__{qid}"

    with st.expander(f"{qid}: {qtext}", expanded=True):
        colA, colB = st.columns([3, 1])
        with colA:
            st.markdown(f"**Student Answer:** {student_ans}")
        with colB:
            st.radio(
                "Marks:",
                scale,
                index=default_index,
                horizontal=True,
                key=key
            )

# ---------------------------------------------------------------
# SHOW AUTO TOTALS (always)
# ---------------------------------------------------------------
st.markdown("---")
st.subheader(f"MCQ Score (Auto): {total_mcq_all}")
st.subheader(f"Likert Score (Auto): {total_likert_all}")

# ---------------------------------------------------------------
# SAVE BUTTON – compute & save, THEN show text + grand totals
# ---------------------------------------------------------------
if "last_totals" not in st.session_state:
    st.session_state["last_totals"] = None

if st.button("💾 Save Evaluation for this Test"):
    # 1) Collect current marks for this test from session_state
    text_marks_to_save = {}
    text_total_this_test = 0
    for _, row in short_df.iterrows():
        qid = str(row["QuestionID"])
        key = f"{selected_roll}__{selected_test}__{qid}"
        mark = int(st.session_state.get(key, 0))
        text_marks_to_save[qid] = mark
        text_total_this_test += mark

    # 2) Save ONLY for this test
    doc_id = info["doc_id"]
    with st.spinner("Saving evaluation..."):
        db.collection("student_responses").document(doc_id).set({
            "Evaluation": {
                "text_marks": text_marks_to_save,
                "text_total": text_total_this_test,
            }
        }, merge=True)

    # 3) Compute grand total using:
    #    - auto MCQ + Likert for all tests
    #    - text_total for OTHER tests from saved_text_total
    #    - text_total for THIS test from current marks
    other_text_total = 0
    for sec, sec_info in per_section.items():
        if sec == selected_test:
            continue
        other_text_total += int(sec_info["saved_text_total"] or 0)

    grand_total = total_mcq_all + total_likert_all + other_text_total + text_total_this_test

    st.session_state["last_totals"] = {
        "roll": selected_roll,
        "section": selected_test,
        "text_total": text_total_this_test,
        "grand_total": grand_total,
    }

    st.success("Evaluation saved ✔")

# ---------------------------------------------------------------
# SHOW TEXT MARKS + GRAND TOTAL ONLY AFTER SAVE
# ---------------------------------------------------------------
lt = st.session_state.get("last_totals")
if lt and lt["roll"] == selected_roll and lt["section"] == selected_test:
    st.subheader(f"Text Marks (This Test): {lt['text_total']}")
    st.subheader(f"GRAND TOTAL (All Tests) = {lt['grand_total']}")
else:
    st.info("Click **Save Evaluation for this Test** to see Text Marks and Grand Total.")
