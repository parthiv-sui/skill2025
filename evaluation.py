import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import json
import traceback

st.set_page_config(layout="wide")
st.title("🔥 FIREBASE FULL VALIDATION DEBUGGER")

st.subheader("1️⃣ Checking Streamlit Secrets")

if "firebase" not in st.secrets:
    st.error("❌ st.secrets['firebase'] NOT FOUND")
    st.stop()

cfg = st.secrets["firebase"]

# Show raw secrets (keys only, not values)
st.write("Found keys in firebase secrets:", list(cfg.keys()))

required_keys = [
    "type", "project_id", "private_key_id", "private_key",
    "client_email", "client_id", "auth_uri", "token_uri",
    "auth_provider_x509_cert_url", "client_x509_cert_url"
]

missing = [k for k in required_keys if k not in cfg]
if missing:
    st.error(f"❌ Missing fields in firebase config: {missing}")
    st.stop()

st.success("✔ All required fields present in firebase secrets.")


# -------------------------------------------------------
st.subheader("2️⃣ Attempting Firebase Initialization")
# -------------------------------------------------------

try:
    if firebase_admin._apps:
        st.info("Firebase already initialized — using existing app.")
        db = firestore.client()
    else:
        cred = credentials.Certificate(dict(cfg))
        firebase_admin.initialize_app(cred)
        st.success("✔ Firebase initialized successfully.")
        db = firestore.client()

except Exception as e:
    st.error("❌ FIREBASE INITIALIZATION FAILED")
    st.code(str(e))
    st.code(traceback.format_exc())
    st.stop()


# -------------------------------------------------------
st.subheader("3️⃣ Checking collection: student_responses")
# -------------------------------------------------------

try:
    docs = list(db.collection("student_responses").stream())
    st.success(f"✔ Found {len(docs)} documents")
except Exception as e:
    st.error("❌ ERROR reading collection")
    st.code(str(e))
    st.code(traceback.format_exc())
    st.stop()


# -------------------------------------------------------
st.subheader("4️⃣ Listing first 5 documents")
# -------------------------------------------------------

if len(docs) == 0:
    st.warning("⚠ Collection is empty.")
else:
    for d in docs[:5]:
        st.write("-----")
        st.write("📄 **Document ID:**", d.id)
        st.json(d.to_dict())
