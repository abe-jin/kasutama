# faq_firestore.py

import os
import numpy as np
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore import Transaction, SERVER_TIMESTAMP
from threading import Lock
import openai

# --- グローバル変数と設定 ---
# このファイルでは定義せず、app.pyなどのアプリケーション起動ファイルで設定する
# openai.api_key = os.getenv("OPENAI_API_KEY") 

EMBED_MODEL = "text-embedding-3-small"
FAQ_COLLECTION = "faq"
VERSION_COLLECTION = "faq_versions"

# --- Firestoreクライアントの初期化 ---
# アプリケーション起動時に一度だけ実行されるようにする
try:
    if not firebase_admin._apps:
        cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not cred_path:
            raise ValueError("GOOGLE_APPLICATION_CREDENTIALSが設定されていません。")
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    # 起動時のエラーは明確に知らせる
    print(f"!!!!!!!!!! Firestoreの初期化に失敗しました: {e} !!!!!!!!!!")
    db = None # dbクライアントをNoneにして、以降の処理でエラーが出るようにする

# --- FAQキャッシュ管理 ---
# NOTE: 複数ワーカーで動かす場合、各プロセスでキャッシュが分散するため注意が必要
faq_cache = []
faq_cache_lock = Lock()

def load_faq_cache():
    """FirestoreからFAQを読み込み、メモリ上のキャッシュを更新する"""
    if not db:
        print("DBクライアントが初期化されていないため、キャッシュをロードできません。")
        return

    global faq_cache
    with faq_cache_lock:
        faq_cache = [{"id": doc.id, **doc.to_dict()} for doc in db.collection(FAQ_COLLECTION).stream()]
        print(f"【INFO】FAQキャッシュを再構築しました。件数: {len(faq_cache)}")

def on_faqs_snapshot(col_snapshot, changes, read_time):
    # ...
    with faq_cache_lock:
        new_faqs = [{"id": doc.id, **doc.to_dict()} for doc in col_snapshot]
        faq_cache.clear() # ★ リストを空にする
        faq_cache.extend(new_faqs) # ★ 新しいデータを追加する
    print(f"【INFO】Firestore変更検知。FAQキャッシュを自動更新。件数: {len(faq_cache)}")
def start_faq_watch():
    """Firestoreコレクションの監視を開始する"""
    if not db:
        print("DBクライアントが初期化されていないため、監視を開始できません。")
        return
    db.collection(FAQ_COLLECTION).on_snapshot(on_faqs_snapshot)

# --- OpenAI Embedding ---
def generate_embedding(text: str) -> list[float]:
    """OpenAIのEmbedding APIを呼び出し、ベクトル（floatのリスト）を返す"""
    try:
        # 最新のSDKの書き方に統一
        resp = openai.embeddings.create(model=EMBED_MODEL, input=text)
        return resp.data[0].embedding
    except Exception as e:
        print(f"[ERROR] OpenAI Embeddingの生成に失敗: {e}")
        return []

# --- データバリデーション ---
def _validate_faq_data(question: str, answer: str):
    """FAQデータの必須項目をチェックする内部関数"""
    if not question or not isinstance(question, str):
        raise ValueError("質問（question）は必須の文字列です。")
    if not answer or not isinstance(answer, str):
        raise ValueError("回答（answer）は必須の文字列です。")

# --- FAQデータ操作関数 ---
def load_faqs(lang: str = None) -> list[dict]:
    """FAQの一覧をFirestoreから取得する"""
    if not db: return []
    query = db.collection(FAQ_COLLECTION)
    if lang:
        query = query.where("lang", "==", lang)
    return [{"id": doc.id, **doc.to_dict()} for doc in query.stream()]

def save_faq(question: str, answer: str, aliases_str: str, editor_id: str, lang: str = "ja", faq_id: str = None):
    """
    FAQを1件保存（新規追加または更新）する。
    更新時は、更新前のデータをバージョン履歴に保存する。
    """
    if not db: raise ConnectionError("Firestoreに接続できません。")
    _validate_faq_data(question, answer)

    # Embeddingベクトルを計算
    aliases = [a.strip() for a in aliases_str.split(",") if a.strip()]
    texts_for_embedding = [question] + aliases
    embeddings = [generate_embedding(t) for t in texts_for_embedding if t]
    avg_embedding = list(np.mean(embeddings, axis=0)) if embeddings else []

    new_data = {
        "question": question,
        "answer": answer,
        "aliases": aliases,
        "lang": lang,
        "embedding": avg_embedding,
        "last_updated_by": editor_id,
        "last_updated_at": SERVER_TIMESTAMP
    }

    if faq_id:
        # 更新処理
        doc_ref = db.collection(FAQ_COLLECTION).document(faq_id)
        _save_version_and_update(doc_ref, new_data, editor_id)
        return faq_id
    else:
        # 新規追加処理
        _, doc_ref = db.collection(FAQ_COLLECTION).add(new_data)
        return doc_ref.id

@firestore.transactional
def _save_version_and_update(transaction: Transaction, doc_ref, new_data: dict, editor_id: str):
    """
    【トランザクション処理】
    1. 更新前のドキュメントを取得し、バージョン履歴に保存する。
    2. 新しいデータでドキュメントを更新する。
    """
    # 1. 更新前のドキュメントを取得
    old_doc = doc_ref.get(transaction=transaction)
    if old_doc.exists:
        # 履歴保存用の新しいドキュメント参照を作成
        version_ref = db.collection(VERSION_COLLECTION).document()
        version_data = {
            "faq_id": old_doc.id,
            "data": old_doc.to_dict(),
            "editor": editor_id,
            "timestamp": SERVER_TIMESTAMP
        }
        # トランザクション内で履歴を保存
        transaction.set(version_ref, version_data)

    # 2. 新しいデータでドキュメントを更新
    transaction.set(doc_ref, new_data)


def delete_faq(faq_id: str):
    """FAQを1件削除する"""
    if not db: raise ConnectionError("Firestoreに接続できません。")
    db.collection(FAQ_COLLECTION).document(faq_id).delete()


# --- バージョン管理関連 ---
def get_faq_versions(faq_id: str) -> list[dict]:
    """指定したFAQの更新履歴をタイムスタンプの降順で取得する"""
    if not db: return []
    query = (
        db.collection(VERSION_COLLECTION)
          .where("faq_id", "==", faq_id)
          .order_by("timestamp", direction=firestore.Query.DESCENDING)
    )
    return [{"id": doc.id, **doc.to_dict()} for doc in query.stream()]


def rollback_faq(faq_id: str, version_id: str, editor_id: str):
    """指定したバージョンIDの状態にFAQを復元（ロールバック）する"""
    if not db: raise ConnectionError("Firestoreに接続できません。")
    
    version_doc_ref = db.collection(VERSION_COLLECTION).document(version_id)
    version_doc = version_doc_ref.get()

    if not version_doc.exists:
        raise ValueError(f"指定されたバージョン(ID: {version_id})が見つかりません。")

    version_data = version_doc.to_dict()
    if "data" not in version_data:
         raise ValueError(f"バージョン(ID: {version_id})のデータ形式が不正です。")

    # ロールバック先のデータを準備
    rollback_data = version_data["data"]
    # 誰がいつロールバックしたかの情報を追記
    rollback_data["last_updated_by"] = editor_id
    rollback_data["last_updated_at"] = SERVER_TIMESTAMP

    # 現在のFAQを、取得したバージョンデータで上書き保存
    # この操作自体も履歴に残したい場合は、save_faq関数を呼び出すのが良い
    faq_doc_ref = db.collection(FAQ_COLLECTION).document(faq_id)
    _save_version_and_update(db.transaction(), faq_doc_ref, rollback_data, editor_id)