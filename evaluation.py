import json
import pandas as pd
import streamlit as st

import firebase_admin
from firebase_admin import credentials, firestore


# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(page_title="Faculty Evaluation Dashboard", layout="wide")
st.title("👩‍🏫 Faculty Evaluation Dashboard – SAFE MODE")


# ---------------------------------------------------------
# FIREBASE INIT (NO CACHE)
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
# LOAD ALL CSVs (FAST)
# ---------------------------------------------------------
def load_csv(fname):
    try:
        df = pd.read_csv(fname)
        df.columns = [c.strip() for c in df.columns]
        df["Type"] = df["Type"].astype(str).str.lower()
        return df
    except:
        return pd.DataFrame()


banks = {
    "Aptitude Test": load_csv("aptitude.csv"),
    "Adaptability & Learning": load_csv("adaptability_learning.csv"),
    "Communication Skills - Objective": load_csv("communication_skills_objective.csv"),
    "Communication Skills - Descriptive": load_csv("communication_skills_descriptive.csv"),
}

AUTO_LIKERT = {"Adaptability & Learning", "Communication Skills - Objective"}
AUTO_MCQ = {"Aptitude Test", "Communication Skills - Objective"}
MANUAL = {"Aptitude Test", "Communication Skills - Descriptive"}


# ---------------------------------------------------------
# FIXED SCALES
# ---------------------------------------------------------
FOUR = {12, 13, 14, 16, 17, 18}
THREE = {22, 23, 24, 25, 28, 29, 30, 34}

def parse_qid(q):
    try:
        return int(str(q).replace("Q", ""))
    except:
        return -1

def scale_for(q):
    x = parse_qid(q)
    if x in FOUR: return [0, 1, 2, 3]
    if x in THREE: return [0, 1, 2]
    return [0, 1]


# ---------------------------------------------------------
# LOAD STUDENT RESPONSES
# (NO CACHE, NO STREAM – FASTEST)
# ---------------------------------------------------------
roll_map = {}
docs = list(db.collection("student_responses").list_documents())

for ref in docs:
    snap = ref.get()
    if not snap.exists:
        continue
    data = snap.to_dict()
    roll = data.get("Roll")
    sec = data.get("Section")
    if not roll or not sec:
        continue
    if roll not in roll_map:
        roll_map[roll] = []
    if "Responses" not in data or not isinstance(data["Responses"], list):
        data["Responses"] = []
    roll_map[roll].append((ref.id, data))


if not roll_map:
    st.error("No student responses found.")
    st.stop()


# ---------------------------------------------------------
# UI – SELECT ROLL
# ---------------------------------------------------------
selected_roll = st.selectbox("Select Student Roll Number", sorted(roll_map.keys()))
docs_for_roll = roll_map[selected_roll]


# ---------------------------------------------------------
# SELECT TEST FOR MANUAL EVALUATION
# ---------------------------------------------------------
tests = sorted([d["Section"] for _, d in docs_for_roll if d["Section"] in MANUAL])

if not tests:
    st.info("This student has no manual tests.")
    st.stop()

selected_test = st.selectbox("Select Test", tests)

# find matching doc
doc_id = None
doc_data = None
for did, d in docs_for_roll:
    if d["Section"] == selected_test:
        doc_id = did
        doc_data = d
        break

df_test = banks[selected_test]
responses = doc_data["Responses"]
saved_eval = doc_data.get("Evaluation", {})
saved_marks = saved_eval.get("text_marks", {})


# ---------------------------------------------------------
# SCORING FUNCTIONS
# ---------------------------------------------------------
def get_correct(row):
    for c in ["Answer", "Correct", "CorrectAnswer", "Ans", "AnswerKey"]:
        if c in row and pd.notna(row[c]):
            return str(row[c]).strip()
    return None

def calc_mcq(df, resp):
    score = 0
    df_idx = df.set_index(df["QuestionID"].astype(str), drop=False)
    for r in resp:
        qid = str(r["QuestionID"])
        if qid in df_idx.index:
            row = df_idx.loc[qid]
            if row["Type"] == "mcq":
                if str(r["Response"]).strip() == get_correct(row):
                    score += 1
    return score

def likert_map(v):
    try:
        return max(0, min(4, int(v)-1))
    except:
        return 0

def calc_likert(df, resp):
    score = 0
    df_idx = df.set_index(df["QuestionID"].astype(str), drop=False)
    for r in resp:
        qid = str(r["QuestionID"])
        if qid in df_idx.index:
            row = df_idx.loc[qid]
            if row["Type"] == "likert":
                score += likert_map(r["Response"])
    return score


# ---------------------------------------------------------
# MANUAL TEXT MARKING (NO EXPANDERS)
# ---------------------------------------------------------
st.subheader("Text Questions")
marks_given = {}
text_sum = 0

short_df = df_test[df_test["Type"] == "short"]

for _, row in short_df.iterrows():
    qid = str(row["QuestionID"])
    qtext = row["Question"]

    # student answer
    ans = "(no answer)"
    for r in responses:
        if str(r["QuestionID"]) == qid:
            ans = str(r["Response"])

    st.write(f"**Q{qid}: {qtext}**")
    st.write(f"Answer: {ans}")

    scale = scale_for(qid)
    default = saved_marks.get(qid, 0)
    if default not in scale:
        default = 0

    mark = st.radio(
        f"Marks for Q{qid}",
        scale,
        index=scale.index(default),
        horizontal=True,
        key=f"{selected_roll}_{qid}"
    )

    marks_given[qid] = mark
    text_sum += mark

st.write("---")


# ---------------------------------------------------------
# CALCULATE BUTTON (NO FREEZE)
# ---------------------------------------------------------
if st.button("Calculate Marks"):

    mcq_score = calc_mcq(df_test, responses)
    likert_score = calc_likert(df_test, responses)
    final = mcq_score + likert_score + text_sum

    st.success(
        f"""
### PREVIEW
MCQ: {mcq_score}  
Likert: {likert_score}  
Text: {text_sum}  

👉 **Final This Test = {final}**
"""
    )


# ---------------------------------------------------------
# SAVE BUTTON
# ---------------------------------------------------------
if st.button("Save Evaluation"):

    mcq_score = calc_mcq(df_test, responses)
    likert_score = calc_likert(df_test, responses)
    final = mcq_score + likert_score + text_sum

    # save this test
    db.collection("student_responses").document(doc_id).set(
        {
            "Evaluation": {
                "text_marks": marks_given,
                "text_total": text_sum,
                "mcq_total": mcq_score,
                "likert_total": likert_score,
                "final_total": final
            }
        },
        merge=True
    )

    # compute grand total
    grand = 0
    for did, d in docs_for_roll:
        if did == doc_id:
            grand += final
        else:
            ev = d.get("Evaluation", {})
            grand += ev.get("final_total", 0)

    # save grand total in all docs
    for did, _ in docs_for_roll:
        db.collection("student_responses").document(did).set(
            {"Evaluation": {"grand_total": grand}},
            merge=True
        )

    st.success(f"Saved. GRAND TOTAL = {grand}")
