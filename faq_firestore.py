import firebase_admin
from firebase_admin import credentials, firestore
import os

if not firebase_admin._apps:
    cred = credentials.Certificate(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
    firebase_admin.initialize_app(cred)
db = firestore.client()
COL = "faqs"

def load_faqs():
    docs = db.collection(COL).stream()
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]

def save_faq(faq_id, question, answer, aliases):
    data = {
        "question": question,
        "answer": answer,
        "aliases": [a.strip() for a in aliases.split(",") if a.strip()]
    }
    if faq_id:
        db.collection(COL).document(faq_id).set(data)
    else:
        db.collection(COL).add(data)

def delete_faq(faq_id):
    db.collection(COL).document(faq_id).delete()

def import_faq_list(faq_list):
    for faq in faq_list:
        db.collection(COL).add(faq)

def export_faq_list():
    faqs = load_faqs()
    return faqs
