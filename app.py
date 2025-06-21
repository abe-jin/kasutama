# app.py (すべての機能をこのファイルに集約)

# === 標準ライブラリ ===
import os
import re
import json
import logging
from functools import wraps
from datetime import datetime
from threading import Lock
import io
import csv
from flask_cors import CORS
# === 外部ライブラリ ===
import firebase_admin
import jaconv
import numpy as np
import openai
from dotenv import load_dotenv
from firebase_admin import credentials, firestore
from google.cloud.firestore import SERVER_TIMESTAMP
from flask import (Flask, Response, abort, flash, jsonify, redirect,
                   render_template, request, send_file, url_for)
from flask_login import (LoginManager, UserMixin, current_user,
                         login_required, login_user, logout_user)
from flask_wtf import CSRFProtect, FlaskForm
from flask import jsonify
from langdetect import detect
from linebot import LineBotApi, WebhookHandler
from linebot.models import (MessageEvent, TextMessage, TextSendMessage)
from numpy.linalg import norm
from wtforms import PasswordField, StringField
from wtforms.validators import DataRequired

# --- 初期設定 ---
load_dotenv()

# --- Flaskアプリケーションの初期化 ---
app = Flask(__name__)
CORS(app)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")
csrf = CSRFProtect(app)

# --- Firestoreクライアントの初期化 ---
try:
    if not firebase_admin._apps:
        cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not cred_path or not os.path.exists(cred_path):
            raise ValueError(f"Google認証情報ファイルが見つかりません: {cred_path}")
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    print(f"!!!!!!!!!! Firestoreの初期化に失敗しました: {e} !!!!!!!!!!")
    db = None

# --- APIクライアント設定 ---
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET', '')
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '')
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
openai.api_key = os.environ.get("OPENAI_API_KEY")
SUPPORT_PHONE = os.environ.get('SUPPORT_PHONE', '0120-123-456')

# --- FAQキャッシュ関連 ---
faq_cache = []
faq_cache_lock = Lock()
FAQ_COLLECTION = "faq"

def load_faq_cache():
    if not db: return
    global faq_cache
    with faq_cache_lock:
        new_faqs = [{"id": doc.id, **doc.to_dict()} for doc in db.collection(FAQ_COLLECTION).stream()]
        faq_cache.clear()
        faq_cache.extend(new_faqs)
        print(f"【INFO】FAQキャッシュを再構築。件数: {len(faq_cache)}")

def start_faq_watch():
    if not db: return
    def on_snapshot(col_snapshot, changes, read_time):
        global faq_cache
        with faq_cache_lock:
            new_faqs = [{"id": doc.id, **doc.to_dict()} for doc in col_snapshot]
            faq_cache.clear()
            faq_cache.extend(new_faqs)
        print(f"【INFO】Firestore変更検知。キャッシュ自動更新。件数: {len(faq_cache)}")
    db.collection(FAQ_COLLECTION).on_snapshot(on_snapshot)

# --- ログイン管理 ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class AdminUser(UserMixin):
    def __init__(self, user_id, role="viewer"):
        self.id = user_id
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    admin_user = os.environ.get("ADMIN_USER", "admin")
    editor_user = os.environ.get("EDITOR_USER", "editor")
    if user_id == admin_user: return AdminUser(user_id, role="admin")
    if user_id == editor_user: return AdminUser(user_id, role="editor")
    return AdminUser(user_id, role="viewer")

def role_required(*roles):
    @wraps(roles)
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated or getattr(current_user, 'role', 'viewer') not in roles:
                abort(403)
            return func(*args, **kwargs)
        return wrapper
    return decorator

# --- ログイン/トップページ関連 ---
class LoginForm(FlaskForm):
    username = StringField('ユーザー名', validators=[DataRequired()])
    password = PasswordField('パスワード', validators=[DataRequired()])

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin_top'))
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        admin_user = os.environ.get("ADMIN_USER", "admin")
        admin_pass = os.environ.get("ADMIN_PASS", "password")
        editor_user = os.environ.get("EDITOR_USER", "editor")
        editor_pass = os.environ.get("EDITOR_PASS", "editor_pass")
        user_to_login = None
        if username == admin_user and password == admin_pass:
            user_to_login = AdminUser(username, role="admin")
        elif username == editor_user and password == editor_pass:
            user_to_login = AdminUser(username, role="editor")
        if user_to_login:
            login_user(user_to_login)
            return redirect(request.args.get('next') or url_for('admin_top'))
        else:
            flash("ユーザー名またはパスワードが正しくありません。", "danger")
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("ログアウトしました。", "info")
    return redirect(url_for('login'))

# --- 管理画面関連のルート ---
@app.route('/admin')
@login_required
def admin_top():
    faqs = db.collection(FAQ_COLLECTION).stream() if db else []
    faq_list = [{"id": doc.id, **doc.to_dict()} for doc in faqs]
    return render_template('admin.html', faqs=faq_list)

@app.route('/admin/faq/save', methods=['POST'])
@login_required
@role_required('admin', 'editor')
def admin_faq_save():
    try:
        faq_id = request.form.get('faq_id') or None
        question = request.form.get('question', '').strip()
        answer = request.form.get('answer', '').strip()
        if not question or not answer:
            raise ValueError("質問と回答は必須です。")
        doc_data = {"question": question, "answer": answer}
        if faq_id:
            db.collection(FAQ_COLLECTION).document(faq_id).set(doc_data)
        else:
            db.collection(FAQ_COLLECTION).add(doc_data)
        flash('FAQを保存しました', 'success')
    except Exception as e:
        flash(f"保存に失敗しました: {e}", 'danger')
    return redirect(url_for('admin_top'))

@app.route('/admin/faq/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_faq_delete():
    try:
        faq_id = request.form.get('faq_id')
        if not faq_id: raise ValueError("削除対象のIDが指定されていません。")
        db.collection(FAQ_COLLECTION).document(faq_id).delete()
        flash('FAQを削除しました', 'info')
    except Exception as e:
        flash(f"削除に失敗しました: {e}", 'danger')
    return redirect(url_for('admin_top'))
from flask import jsonify

@app.route("/api/faqs", methods=["GET"])
def api_get_faqs():
    """FAQ一覧をJSONで返す（GET）"""
    if not db:
        return jsonify([]), 200
    faqs = db.collection(FAQ_COLLECTION).stream()
    faq_list = [{"id": doc.id, **doc.to_dict()} for doc in faqs]
    return jsonify(faq_list), 200

@app.route("/api/faqs", methods=["POST"])
def api_add_faq():
    """FAQ新規追加（POST）"""
    if not db:
        return jsonify({"error": "DB未接続"}), 500
    data = request.get_json()
    if not data.get("question") or not data.get("answer"):
        return jsonify({"error": "質問と回答は必須です"}), 400
    doc_ref = db.collection(FAQ_COLLECTION).add({
        "question": data["question"],
        "answer": data["answer"],
        "lang": data.get("lang", "ja")
    })
    doc_id = doc_ref[1].id if isinstance(doc_ref, tuple) else doc_ref.id
    new_faq = db.collection(FAQ_COLLECTION).document(doc_id).get()
    return jsonify({"id": doc_id, **new_faq.to_dict()}), 201

@app.route("/api/faqs/<faq_id>", methods=["PUT"])
def api_update_faq(faq_id):
    """FAQ編集（PUT）"""
    if not db:
        return jsonify({"error": "DB未接続"}), 500
    data = request.get_json()
    update_data = {}
    if "question" in data:
        update_data["question"] = data["question"]
    if "answer" in data:
        update_data["answer"] = data["answer"]
    if "lang" in data:
        update_data["lang"] = data["lang"]
    db.collection(FAQ_COLLECTION).document(faq_id).set(update_data, merge=True)
    updated_faq = db.collection(FAQ_COLLECTION).document(faq_id).get()
    return jsonify({"id": faq_id, **updated_faq.to_dict()}), 200

@app.route("/api/faqs/<faq_id>", methods=["DELETE"])
def api_delete_faq(faq_id):
    """FAQ削除（DELETE）"""
    if not db:
        return jsonify({"error": "DB未接続"}), 500
    db.collection(FAQ_COLLECTION).document(faq_id).delete()
    return "", 204
@app.route("/api/conversations", methods=["GET"])
def api_get_conversations():
    """会話履歴一覧をJSONで返す（GET）"""
    if not db:
        return jsonify([]), 200
    docs = db.collection("messages").order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
    conv_list = [{"id": doc.id, **doc.to_dict()} for doc in docs]
    return jsonify(conv_list), 200

# --- LINE Bot用ヘルパー関数群 ---
def normalize_text(text: str) -> str:
    if not text: return ""
    text = jaconv.z2h(text, kana=True, ascii=True, digit=True)
    text = jaconv.kata2hira(text)
    text = text.lower()
    text = re.sub(r'[!-/:-@[-`{-~]', '', text)
    text = re.sub(r'[、。「」？]', '', text)
    text = re.sub(r'\s+', '', text)
    return text.strip()

def save_message_to_firestore(user_message, response, hit_status, user_id):
    try:
        data = {'user_message': user_message, 'response': response, 'hit_status': hit_status, 'user_id': user_id, 'timestamp': SERVER_TIMESTAMP}
        if db: db.collection('messages').add(data)
    except Exception as e:
        app.logger.error(f"Firestoreへのメッセージ保存に失敗: {e}")

# --- LINE Webhookハンドラ ---
@app.route("/callback", methods=['POST'])
@csrf.exempt
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        app.logger.error(f"Webhook Handler Error: {e}")
        abort(500)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """LINEからのメッセージを処理する（完全一致→部分一致→デフォルト）"""
    try:
        user_id = event.source.user_id
        text_in = event.message.text
        app.logger.info(f"Received message from {user_id}: {text_in}")

        norm_text = normalize_text(text_in)

        # --- 完全一致 ---
        found_faq = next((faq for faq in faq_cache
                          if 'question' in faq and normalize_text(faq['question']) == norm_text), None)

        hit_status = ""
        if found_faq:
            reply = found_faq.get('answer', '回答が見つかりませんでした。')
            hit_status = "完全一致"
        else:
            # --- 部分一致 ---
            found_faq_partial = next((faq for faq in faq_cache
                                      if 'question' in faq and norm_text in normalize_text(faq['question'])), None)
            if found_faq_partial:
                reply = found_faq_partial.get('answer', '回答が見つかりませんでした。')
                hit_status = "部分一致"
            else:
                # --- どれも一致しない場合 ---
                reply = "お問い合わせありがとうございます。ご質問いただいた内容については、担当者が確認の上、改めてご案内いたします。"
                hit_status = "未ヒット/要対応"

        save_message_to_firestore(text_in, reply, hit_status, user_id)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    except Exception as e:
        app.logger.error(f"Handle_messageでエラーが発生: {e}")
        try:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="申し訳ありません、システムエラーが発生しました。"))
        except Exception as ex:
            app.logger.error(f"エラー通知の送信にも失敗: {ex}")


# --- アプリケーション起動 ---
if __name__ == '__main__':
    print("--- アプリケーションを起動します ---")
    load_faq_cache()
    start_faq_watch()
    print("------------------------------------")
    app.run(host='0.0.0.0', port=5000, debug=False)