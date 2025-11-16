import streamlit as st
import pandas as pd
import json
import firebase_admin
from firebase_admin import credentials, firestore

# ---------------------------------------------------------------
# PAGE + FIREBASE INIT
# ---------------------------------------------------------------
st.set_page_config(page_title="Faculty Evaluation", layout="wide")
st.title("🧑‍🏫 Faculty Evaluation Dashboard")


@st.cache_resource
def init_firebase():
    """Initialize Firebase only once."""
    if firebase_admin._apps:
        return firestore.client()

    try:
        if "firebase" in st.secrets:
            cfg = dict(st.secrets["firebase"])
        else:
            with open("firebase_key.json", "r", encoding="utf-8") as f:
                cfg = json.load(f)

        cred = credentials.Certificate(cfg)
        firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        st.error(f"Firebase initialization failed: {e}")
        return None


db = init_firebase()
if db is None:
    st.stop()

# ---------------------------------------------------------------
# SAFE LOADER FOR student_responses
# ---------------------------------------------------------------
def load_safe_student_responses(db):
    """
    Load docs from student_responses safely:
    - skip docs without Roll or Section
    - ensure Responses exists and is a list
    - never crash the app
    """
    safe_docs = []
    try:
        docs = db.collection("student_responses").stream()
    except Exception as e:
        st.error(f"Error reading Firestore: {e}")
        return safe_docs

    for d in docs:
        try:
            data = d.to_dict() or {}
            roll = data.get("Roll")
            section = data.get("Section")
            if not roll or not section:
                # malformed doc, ignore
                continue

            responses = data.get("Responses")
            if not isinstance(responses, list):
                responses = []
            data["Responses"] = responses

            safe_docs.append((d.id, data))
        except Exception:
            # skip any weird doc without killing the app
            continue

    return safe_docs


safe_docs = load_safe_student_responses(db)

# Build student_map: roll -> list of {section, doc_id, data}
student_map = {}
for doc_id, data in safe_docs:
    roll = data["Roll"]
    section = data["Section"]
    student_map.setdefault(roll, []).append(
        {"section": section, "doc_id": doc_id, "data": data}
    )

if not student_map:
    st.info("No student responses found in Firestore.")
    st.stop()

# ---------------------------------------------------------------
# LOAD CSV QUESTION BANKS
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

# Manual evaluation is needed for:
MANUAL_EVAL_TESTS = [
    "Aptitude Test",
    "Communication Skills - Descriptive",
]

# ---------------------------------------------------------------
# HELPERS FOR MARKING
# ---------------------------------------------------------------
def get_correct_answer(row):
    for col in ["Answer", "CorrectAnswer", "Correct", "Ans", "AnswerKey", "RightAnswer"]:
        if col in row and not pd.isna(row[col]):
            return str(row[col]).strip()
    return None


def likert_to_score(v):
    v = int(v)
    if v == 1:
        return 0
    if v == 2:
        return 1
    if v == 3:
        return 2
    if v in [4, 5]:
        return 3
    return 0


def calc_mcq(df, responses):
    score = 0
    for r in responses:
        qid = str(r.get("QuestionID", ""))
        student_ans = str(r.get("Response", "")).strip()
        row_df = df[df["QuestionID"].astype(str) == qid]
        if row_df.empty:
            continue
        row = row_df.iloc[0]
        if str(row.get("Type", "")).strip().lower() != "mcq":
            continue
        correct = get_correct_answer(row)
        if correct and student_ans == correct:
            score += 1
    return score


def calc_likert(df, responses):
    total = 0
    for r in responses:
        qid = str(r.get("QuestionID", ""))
        ans = r.get("Response", None)
        row_df = df[df["QuestionID"].astype(str) == qid]
        if row_df.empty:
            continue
        row = row_df.iloc[0]
        if str(row.get("Type", "")).strip().lower() != "likert":
            continue
        try:
            total += likert_to_score(int(ans))
        except Exception:
            continue
    return total


def is_evaluated_local(doc_data):
    ev = doc_data.get("Evaluation", {})
    # treat as evaluated if we at least have any stored totals
    return (
        "mcq_total" in ev
        or "likert_total" in ev
        or "text_total" in ev
        or "final_total" in ev
    )


# ---------------------------------------------------------------
# AUTO-EVALUATE MCQ + LIKERT FOR THE SELECTED STUDENT
# ---------------------------------------------------------------
def auto_evaluate_for_student(roll):
    """Compute mcq_total & likert_total for each section for this student."""
    entries = student_map[roll]
    for entry in entries:
        section = entry["section"]
        data = entry["data"]
        doc_id = entry["doc_id"]

        df = question_banks.get(section)
        if df is None:
            continue

        responses = data.get("Responses", [])
        mcq = calc_mcq(df, responses)
        likert = calc_likert(df, responses)

        ev = data.get("Evaluation", {})
        ev["mcq_total"] = mcq
        ev["likert_total"] = likert
        ev["final_total"] = mcq + likert + ev.get("text_total", 0)

        data["Evaluation"] = ev  # update local cache
        # Persist back to Firestore
        db.collection("student_responses").document(doc_id).set(
            {"Evaluation": ev}, merge=True
        )


def compute_totals_for_student(roll, override_section=None, override_text_total=None):
    """
    Compute:
      mcq_sum_all, likert_sum_all, text_sum_all, grand_total
    If override_section + override_text_total given,
    that section uses the override value instead of stored text_total.
    """
    mcq_sum = 0
    likert_sum = 0
    text_sum = 0

    for entry in student_map[roll]:
        section = entry["section"]
        data = entry["data"]
        ev = data.get("Evaluation", {})

        mcq_sum += ev.get("mcq_total", 0)
        likert_sum += ev.get("likert_total", 0)

        t = ev.get("text_total", 0)
        if override_section is not None and section == override_section:
            if override_text_total is not None:
                t = override_text_total
        text_sum += t

    grand_total = mcq_sum + likert_sum + text_sum
    return mcq_sum, likert_sum, text_sum, grand_total


# ---------------------------------------------------------------
# UI – SELECT STUDENT
# ---------------------------------------------------------------
def student_label(roll):
    docs = student_map[roll]
    done = sum(1 for e in docs if is_evaluated_local(e["data"]))
    total = len(docs)
    return f"{roll} ({done}/{total} evaluated)"


all_students = sorted(student_map.keys())
selected_roll = st.selectbox(
    "Select Student Roll Number", all_students, format_func=student_label
)

# Run auto-eval for this student
auto_evaluate_for_student(selected_roll)

# ---------------------------------------------------------------
# UI – SELECT TEST FOR MANUAL EVALUATION
# ---------------------------------------------------------------
# Intersection of student's sections with manual-eval tests
student_sections = [e["section"] for e in student_map[selected_roll]]
tests_taken = [s for s in student_sections if s in MANUAL_EVAL_TESTS]

if not tests_taken:
    st.success("No manual evaluation needed for this student (all auto).")
    # Still show their auto totals:
    mcq_total, likert_total, text_total_all, grand_total = compute_totals_for_student(
        selected_roll
    )
    st.write(f"**MCQ Score (Auto): {mcq_total}**")
    st.write(f"**Likert Score (Auto): {likert_total}**")
    st.write(f"**Text Marks (All Tests): {text_total_all}**")
    st.subheader(f"GRAND TOTAL (All Tests) = {grand_total}")
    st.stop()


def section_label(section):
    entry = next(e for e in student_map[selected_roll] if e["section"] == section)
    return f"{section} ({'✔' if is_evaluated_local(entry['data']) else '✖'})"


selected_test = st.selectbox(
    "Select Test for Manual Evaluation",
    tests_taken,
    format_func=section_label,
)

# ---------------------------------------------------------------
# LOAD CURRENT TEST DATA
# ---------------------------------------------------------------
current_entry = next(
    e for e in student_map[selected_roll] if e["section"] == selected_test
)
current_doc_id = current_entry["doc_id"]
current_data = current_entry["data"]
current_ev = current_data.get("Evaluation", {})

df = question_banks[selected_test]
responses = current_data.get("Responses", [])

short_df = df[df["Type"].astype(str).str.lower() == "short"]

st.subheader(f"Manual Evaluation – {selected_test}")

marks_given = {}
text_total_display = 0

prev_marks = current_ev.get("text_marks", {})

# ---------------------------------------------------------------
# QUESTION-BY-QUESTION MARKING
# 0/1 vs 0/1/2/3 logic preserved exactly
# ---------------------------------------------------------------
for _, row in short_df.iterrows():
    qid = str(row["QuestionID"])
    qtext = str(row["Question"])

    # Find student's answer for this QuestionID
    student_ans = next(
        (r.get("Response", "(no answer)") for r in responses
         if str(r.get("QuestionID", "")) == qid),
        "(no answer)",
    )

    # Your original rule: if question text contains "3" -> 0/1/2/3 else 0/1
    if "3" in qtext.lower():
        scale = [0, 1, 2, 3]
    else:
        scale = [0, 1]

    previous_mark = prev_marks.get(qid, 0)
    try:
        default_index = scale.index(previous_mark)
    except ValueError:
        default_index = 0

    with st.expander(f"{qid}: {qtext}", expanded=True):
        st.markdown(f"**Student Answer:** {student_ans}")
        mark = st.radio(
            "Marks:",
            scale,
            horizontal=True,
            index=default_index,
            key=f"{selected_roll}_{selected_test}_{qid}",
        )

    marks_given[qid] = mark
    text_total_display += mark

# ---------------------------------------------------------------
# SHOW AUTO TOTALS + TEXT MARKS + GRAND TOTAL (PREVIEW)
# ---------------------------------------------------------------
st.markdown("---")

mcq_total, likert_total, text_total_all, grand_total = compute_totals_for_student(
    selected_roll,
    override_section=selected_test,
    override_text_total=text_total_display,
)

st.write(f"**MCQ Score (Auto): {mcq_total}**")
st.write(f"**Likert Score (Auto): {likert_total}**")
st.write(f"**Text Marks (This Test): {text_total_display}**")
st.write(f"**Text Marks (All Tests, including this one): {text_total_all - current_ev.get('text_total', 0) + text_total_display}**")
st.subheader(f"GRAND TOTAL (All Tests) = {grand_total}")

# ---------------------------------------------------------------
# SAVE TO FIRESTORE
# ---------------------------------------------------------------
if st.button("💾 Save Evaluation for this Test"):
    new_ev = current_data.get("Evaluation", {})
    new_ev["text_marks"] = marks_given
    new_ev["text_total"] = text_total_display
    new_ev["final_total"] = (
        new_ev.get("mcq_total", 0)
        + new_ev.get("likert_total", 0)
        + new_ev.get("text_total", 0)
    )

    # Update local cache
    current_data["Evaluation"] = new_ev
    current_entry["data"] = current_data

    db.collection("student_responses").document(current_doc_id).set(
        {"Evaluation": new_ev}, merge=True
    )

    st.success("Evaluation saved successfully ✅")
