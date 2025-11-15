marks_given = {}
text_total = 0

for _, row in short_df.iterrows():
    qid = str(row["QuestionID"])
    qtext = row["Question"]

    student_ans = "(no answer)"
    for r in responses:
        if str(r["QuestionID"]) == qid:
            student_ans = r["Response"]
            break

    # decide marking scale
    if any(term in qtext.lower() for term in ["3 sentences", "three sentences", "3 points"]):
        scale = [0,1,2,3]
    else:
        scale = [0,1]

    # EXPANDED BY DEFAULT
    with st.expander(f"Q{qid}: {qtext}", expanded=True):

        colA, colB = st.columns([3, 1])

        with colA:
            st.markdown(f"**Student Answer:** {student_ans}")

        with colB:
            mark = st.radio(
                "Marks",
                scale,
                horizontal=True,
                key=f"m_{qid}"
            )

        marks_given[qid] = mark
        text_total += mark
