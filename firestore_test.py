import os
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore

# .env の読み込み
load_dotenv()

# サービスアカウント鍵のパス取得
key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
project_id = os.getenv("FIREBASE_PROJECT_ID")

# Firebase Admin 初期化
cred = credentials.Certificate(key_path)
firebase_admin.initialize_app(cred, {"projectId": project_id})

# Firestore クライアント作成
db = firestore.client()

# テスト書き込み
doc_ref = db.collection("test_collection").document("sample_doc")
doc_ref.set({
    "message": "Hello, Firestore!",
    "status": "success"
})

# テスト読み込み
doc = doc_ref.get()
print("Firestoreから取得:", doc.to_dict())
