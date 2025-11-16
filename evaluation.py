import json
from typing import Dict, List, Tuple

import pandas as pd
import streamlit as st

import firebase_admin
from firebase_admin import credentials, firestore


# ---------------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------------
st.set_page_config(page_title="Faculty Evaluation Dashboard", layout="wide")
st.title("👩‍🏫 Faculty Evaluation Dashboard")

st.caption("DEBUG MODE: On – temporary logs are shown to avoid blank screen issues.")


# ---------------------------------------------------------------
# FIREBASE INITIALIZATION (SAFE)
# ---------------------------------------------------------------
@st.cache_resource
def init_firebase():
    try:
        if firebase_admin._apps:
            st.write("✅ DEBUG: Firebase already initialized – using existing app.")
            return firestore.client()

        # Prefer Streamlit secrets
        if "firebase" in st.secrets:
            cfg = dict(st.secrets["firebase"])
            cred = credentials.Certificate(cfg)
            firebase_admin.initialize_app(cred)
            st.write("✅ DEBUG: Firebase initialized from st.secrets['firebase'].")
        else:
            # Local fallback
            with open("firebase_key.json", "r", encoding="utf-8") as f:
                cfg = json.load(f)
            cred = credentials.Certificate(cfg)
            firebase_admin.initialize_app(cred)
            st.write("✅ DEBUG: Firebase initialized from local firebase_key.json.")

        return firestore.client()

    except Exception as e:
        st.error(f"❌ Firebase initialization failed: {e}")
        return None


db = init_firebase()
if db is None:
    st.error("Cannot continue without Firestore connection.")
    # We still don't hard-stop; UI will just not show data.
    st.stop()


# ---------------------------------------------------------------
# LOAD QUESTION BANKS
# ---------------------------------------------------------------
@st.cache_data
def load_question_banks() -> Dict[str, pd.DataFrame]:
    files = {
        "Aptitude Test": "aptitude.csv",
        "Adaptability & Learning": "adaptability_learning.csv",
        "Communication Skills - Objective": "communication_skills_objective.csv",
        "Communication Skills - Descriptive": "communication_skills_descriptive.csv",
    }

    banks = {}
    for section, fname in files.items():
        try:
            df = pd.read_csv(fname)
            banks[section] = df
            st.write(f"✅ DEBUG: Loaded CSV for section '{section}' with {len(df)} rows.")
        except Exception as e:
            st.error(f"❌ Could not load CSV '{fname}' for '{section}': {e}")
    return banks


question_banks = load_question_banks()

AUTO_EVAL_TESTS = [
    "Adaptability & Learning",
    "Communication Skills - Objective",
]

MANUAL_EVAL_TESTS = [
    "Aptitude Test",
    "Communication Skills - Descriptive",
]

ALL_KNOWN_TESTS = list(question_banks.keys())


# ---------------------------------------------------------------
# HELPER FUNCTIONS – SCORING
# ---------------------------------------------------------------
def get_correct_answer(row: pd.Series):
    for col in ["Answer", "CorrectAnswer", "Correct", "Ans", "AnswerKey", "RightAnswer"]:
        if col in row and not pd.isna(row[col]):
            return str(row[col]).strip()
    return None


def likert_to_score(v: int) -> int:
    """
    Mapping requested:
        Likert 1,2,3,4,5 -> 0,1,2,3,4
    """
    try:
        v = int(v)
    except Exception:
        return 0
    return max(0, min(4, v - 1))


def calc_mcq(df: pd.DataFrame, responses: List[Dict]) -> int:
    if df is None or responses is None:
        return 0
    score = 0
    # Pre-index by QuestionID for speed
    df_idx = df.set_index(df["QuestionID"].astype(str), drop=False)
    for r in responses:
        qid = str(r.get("QuestionID", "")).strip()
        student_ans = str(r.get("Response", "")).strip()
        if qid == "" or student_ans == "":
            continue
        if qid not in df_idx.index:
            continue
        row = df_idx.loc[qid]
        if str(row.get("Type", "")).strip().lower() != "mcq":
            continue
        correct = get_correct_answer(row)
        if correct and student_ans == correct:
            score += 1
    return score


def calc_likert(df: pd.DataFrame, responses: List[Dict]) -> int:
    if df is None or responses is None:
        return 0
    total = 0
    df_idx = df.set_index(df["QuestionID"].astype(str), drop=False)
    for r in responses:
        qid = str(r.get("QuestionID", "")).strip()
        ans = r.get("Response", None)
        if qid == "" or ans is None:
            continue
        if qid not in df_idx.index:
            continue
        row = df_idx.loc[qid]
        if str(row.get("Type", "")).strip().lower() != "likert":
            continue
        try:
            total += likert_to_score(int(ans))
        except Exception:
            continue
    return total


def infer_mark_scale(question_text: str):
    """
    Heuristic:
      - If the question mentions '3' or 'three' -> 0/1/2/3
      - Otherwise -> 0/1
    """
    q = question_text.lower()
    if " 3 " in f" {q} " or "three" in q:
        return [0, 1, 2, 3]
    return [0, 1]


# ---------------------------------------------------------------
# LOAD STUDENT RESPONSES SAFELY
# ---------------------------------------------------------------
def load_safe_student_responses():
    """
    Uses list_documents() (fast & safe) instead of stream().
    Returns:
        dict[roll] -> List[(doc_id, data_dict)]
    """
    roll_map: Dict[str, List[Tuple[str, Dict]]] = {}
    try:
        doc_refs = db.collection("student_responses").list_documents()
        refs_list = list(doc_refs)
        st.write(f"✅ DEBUG: Found {len(refs_list)} documents in 'student_responses'.")
    except Exception as e:
        st.error(f"❌ Error listing Firestore documents: {e}")
        return roll_map

    for ref in refs_list:
        try:
            snap = ref.get()
            if not snap.exists:
                continue
            data = snap.to_dict() or {}
            roll = data.get("Roll")
            section = data.get("Section")
            if not roll or not section:
                continue

            # Normalise responses
            responses = data.get("Responses")
            if not isinstance(responses, list):
                responses = []
            data["Responses"] = responses

            if roll not in roll_map:
                roll_map[roll] = []
            roll_map[roll].append((ref.id, data))
        except Exception as e:
            st.write(f"⚠️ DEBUG: Skipping a document due to error: {e}")
            continue

    return roll_map


roll_to_docs = load_safe_student_responses()
if not roll_to_docs:
    st.warning("No student_responses documents found. Nothing to evaluate yet.")
    st.stop()


# ---------------------------------------------------------------
# BUILD STUDENT DROPDOWN WITH EVALUATION STATUS
# ---------------------------------------------------------------
def has_any_text_marks(doc_list: List[Tuple[str, Dict]]) -> bool:
    for _doc_id, data in doc_list:
        eval_data = data.get("Evaluation", {})
        text_total = eval_data.get("text_total", 0)
        if text_total and text_total > 0:
            return True
    return False


# Construct labels showing ✔ if evaluated
roll_labels = []
sorted_rolls = sorted(roll_to_docs.keys())
for r in sorted_rolls:
    mark = "✔" if has_any_text_marks(roll_to_docs[r]) else "✖"
    roll_labels.append(f"{r}  ({mark})")

label_to_roll = {label: roll for label, roll in zip(roll_labels, sorted_rolls)}

selected_label = st.selectbox("Select Student Roll Number", roll_labels)
selected_roll = label_to_roll[selected_label]

st.write(f"✅ DEBUG: Selected roll = {selected_roll}")

docs_for_roll = roll_to_docs.get(selected_roll, [])


# ---------------------------------------------------------------
# AUTO-SCORE ACROSS ALL TESTS (IN MEMORY ONLY)
# ---------------------------------------------------------------
def compute_auto_totals_for_roll(doc_list: List[Tuple[str, Dict]]):
    total_mcq = 0
    total_likert = 0
    per_doc_scores = {}  # doc_id -> (mcq, likert)
    for doc_id, data in doc_list:
        section = data.get("Section")
        df = question_banks.get(section)
        responses = data.get("Responses", [])
        mcq = calc_mcq(df, responses)
        likert = calc_likert(df, responses)
        total_mcq += mcq
        total_likert += likert
        per_doc_scores[doc_id] = (mcq, likert)
    return total_mcq, total_likert, per_doc_scores


auto_mcq_total, auto_likert_total, per_doc_auto = compute_auto_totals_for_roll(docs_for_roll)
st.write(f"✅ DEBUG: Auto MCQ total={auto_mcq_total}, Auto Likert total={auto_likert_total}")


# ---------------------------------------------------------------
# MANUAL EVALUATION – SELECT TEST
# ---------------------------------------------------------------
tests_taken_manual = []
for doc_id, data in docs_for_roll:
    section = data.get("Section")
    if section in MANUAL_EVAL_TESTS:
        tests_taken_manual.append(section)

tests_taken_manual = sorted(set(tests_taken_manual))

if not tests_taken_manual:
    st.info("This student has no tests requiring manual evaluation.")
    # Still show the auto scores & overall summary
    st.subheader(f"MCQ Score (Auto): {auto_mcq_total}")
    st.subheader(f"Likert Score (Auto): {auto_likert_total}")
    # Grand total from saved data if any
    saved_grand = 0
    for _doc_id, data in docs_for_roll:
        ev = data.get("Evaluation", {})
        saved_grand += ev.get("final_total", 0)
    st.subheader(f"GRAND TOTAL (All Tests) = {saved_grand}")
    st.stop()

selected_test = st.selectbox("Select Test for Manual Evaluation", tests_taken_manual)
st.write(f"✅ DEBUG: Selected test = {selected_test}")


# Find the Firestore document for this test
selected_doc_id = None
selected_doc_data = None
for doc_id, data in docs_for_roll:
    if data.get("Section") == selected_test:
        selected_doc_id = doc_id
        selected_doc_data = data
        break

if selected_doc_id is None or selected_doc_data is None:
    st.error("Could not find Firestore document for selected test.")
    st.stop()

df_test = question_banks.get(selected_test)
if df_test is None:
    st.error(f"No CSV question bank loaded for test '{selected_test}'.")
    st.stop()

responses = selected_doc_data.get("Responses", [])
eval_existing = selected_doc_data.get("Evaluation", {})
existing_text_marks: Dict[str, int] = eval_existing.get("text_marks", {})
saved_text_total = eval_existing.get("text_total", 0)

st.write(f"✅ DEBUG: Existing text_total (saved) for this test = {saved_text_total}")


# ---------------------------------------------------------------
# BUILD MANUAL MARKING UI
# ---------------------------------------------------------------
# Filter only short/descriptive questions
short_df = df_test[df_test["Type"].astype(str).str.lower() == "short"]

marks_given: Dict[str, int] = {}
text_current_total = 0

if short_df.empty:
    st.info("No 'short' type questions found in CSV for this test – nothing to mark.")
else:
    st.markdown("### Manual Text Evaluation")

    for _, row in short_df.iterrows():
        qid = str(row.get("QuestionID"))
        qtext = str(row.get("Question", ""))
        # find student answer from responses
        stu_ans = "(no answer)"
        for r in responses:
            if str(r.get("QuestionID")) == qid:
                stu_ans = str(r.get("Response", "") or "(no answer)")
                break

        scale = infer_mark_scale(qtext)
        default_mark = int(existing_text_marks.get(qid, 0))
        if default_mark not in scale:
            default_mark = 0

        # Determine index in radio
        try:
            default_index = scale.index(default_mark)
        except ValueError:
            default_index = 0

        with st.expander(f"{qid}: {qtext}", expanded=True):
            colA, colB = st.columns([3, 1])
            with colA:
                st.markdown(f"**Student Answer:** {stu_ans}")
            with colB:
                mark = st.radio(
                    "Marks:",
                    scale,
                    index=default_index,
                    key=f"{selected_roll}_{selected_test}_{qid}",
                    horizontal=True,
                )
        marks_given[qid] = int(mark)
        text_current_total += int(mark)

st.markdown("---")


# ---------------------------------------------------------------
# SUMMARY NUMBERS (BEFORE SAVE)
# ---------------------------------------------------------------
st.subheader(f"MCQ Score (Auto): {auto_mcq_total}")
st.subheader(f"Likert Score (Auto): {auto_likert_total}")
st.subheader(f"Text Marks (This Test): {text_current_total}")

# Saved grand total from Evaluation.final_total if present
saved_grand_total = 0
for _doc_id, data in docs_for_roll:
    ev = data.get("Evaluation", {})
    saved_grand_total += ev.get("final_total", 0)

st.subheader(f"GRAND TOTAL (All Tests) = {saved_grand_total}")
st.write("*(Grand total updates after you click **Save Evaluation for this Test**.)*")


# ---------------------------------------------------------------
# SAVE HANDLER
# ---------------------------------------------------------------
def recompute_final_for_doc(section: str, df: pd.DataFrame, responses: List[Dict], text_total: int):
    """
    Recalculate mcq_total, likert_total & final_total for a single test.
    """
    mcq = calc_mcq(df, responses)
    likert = calc_likert(df, responses)
    final_total = mcq + likert + text_total
    return mcq, likert, final_total


def recompute_grand_total_for_roll(
    roll: str,
    all_docs: List[Tuple[str, Dict]],
    selected_doc_id: str,
    new_final_for_selected: int,
):
    """
    Grand total = sum of final_total across all docs.
    If a doc has no final_total, compute mcq+likert as fallback.
    """
    grand = 0
    for doc_id, data in all_docs:
        if doc_id == selected_doc_id:
            grand += new_final_for_selected
            continue

        ev = data.get("Evaluation", {})
        if "final_total" in ev:
            grand += int(ev.get("final_total", 0))
            continue

        # Fallback compute
        section = data.get("Section")
        df = question_banks.get(section)
        responses = data.get("Responses", [])
        mcq = calc_mcq(df, responses)
        likert = calc_likert(df, responses)
        grand += mcq + likert
    return grand


if st.button("💾 Save Evaluation for this Test"):
    try:
        mcq_sel, likert_sel, final_sel = recompute_final_for_doc(
            selected_test, df_test, responses, text_current_total
        )

        st.write(
            f"✅ DEBUG: For this test -> mcq={mcq_sel}, likert={likert_sel}, text={text_current_total}, final={final_sel}"
        )

        # Update selected document Evaluation
        db.collection("student_responses").document(selected_doc_id).set(
            {
                "Evaluation": {
                    "text_marks": marks_given,
                    "text_total": text_current_total,
                    "mcq_total": mcq_sel,
                    "likert_total": likert_sel,
                    "final_total": final_sel,
                }
            },
            merge=True,
        )

        # Recompute grand total for this roll
        new_grand_total = recompute_grand_total_for_roll(
            selected_roll, docs_for_roll, selected_doc_id, final_sel
        )

        # Save grand_total into all docs for this roll (optional but useful)
        batch = db.batch()
        for doc_id, _ in docs_for_roll:
            ref = db.collection("student_responses").document(doc_id)
            batch.set(ref, {"Evaluation": {"grand_total": new_grand_total}}, merge=True)
        batch.commit()

        st.success(
            f"Evaluation saved. New GRAND TOTAL (All Tests) for {selected_roll} = {new_grand_total}."
        )
        st.info("Please rerun the app (or change selection) to see updated totals.")
    except Exception as e:
        st.error(f"❌ Error while saving evaluation: {e}")
