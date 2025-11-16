import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import json

st.set_page_config(layout="wide")

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
            with open("firebase_key.json") as f:
                cfg = json.load(f)
            cred = credentials.Certificate(cfg)
            firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error("Firebase init failed")
        st.code(str(e))
        return None
    return firestore.client()

db = init_firebase()
if not db:
    st.stop()

st.header("DEBUG: List student_responses documents")

try:
    docs = list(db.collection("student_responses").stream())
    st.write(f"Total documents: {len(docs)}")

    for d in docs:
        st.subheader(f"Doc ID: {d.id}")
        st.json(d.to_dict())

except Exception as e:
    st.error("FIRESTORE READ ERROR")
    st.code(str(e))
