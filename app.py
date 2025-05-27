import threading 
from dotenv import load_dotenv
load_dotenv()

faq_cache = []
faq_cache_lock = threading.Lock()
from flask import Flask, request, Response, jsonify, render_template, redirect, url_for
import os
import re
import openai
import logging
from linebot import LineBotApi
from linebot.webhook import WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
from functools import wraps
import jaconv
from admin_faq import admin_bp  # admin_faq.py の Blueprint 名に合わせる
from collections import Counter
import firebase_admin
from firebase_admin import firestore
from linebot.models import TextSendMessage, QuickReply, QuickReplyButton, MessageAction

app = Flask(__name__)
db = firestore.client()
app.register_blueprint(admin_bp)

SUPPORT_PHONE = os.getenv('SUPPORT_PHONE', '0120-123-456')

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
file_handler = logging.FileHandler('app.log', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logger.addHandler(file_handler)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
logger.addHandler(console_handler)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY が設定されていません")
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

# 以下に必要な関数・ルート定義を続けてください
# --- Firestore FAQキャッシュ自動更新用 ---
def log_faq_change(user, action, doc_id, data_before, data_after):
    try:
        db.collection('faq_logs').add({
            'user': user,
            'action': action,         # 'add', 'edit', 'delete'
            'faq_id': doc_id,
            'before': data_before,    # 編集前（新規時はNone）
            'after': data_after,      # 編集後（削除時はNone）
            'timestamp': datetime.now()
        })
    except Exception as e:
        logger.error(f"FAQ変更ログ保存失敗: {e}")
def load_faq_cache():
    global faq_cache
    faqs = []
    for doc in db.collection('faq').stream():
        d = doc.to_dict()
        d['id'] = doc.id
        faqs.append(d)
    with faq_cache_lock:
        faq_cache = faqs

    print(f"【INFO】FAQキャッシュ再構築: {len(faq_cache)}件")
def get_prompt_for_store(store_id):
    doc = db.collection("settings").document(store_id).get()
    if doc.exists:
        return doc.to_dict().get("prompt", "あなたはフレンドリーなカスタマーサポートです。")
    else:
        return "あなたはフレンドリーなカスタマーサポートです。"

def faq_snapshot_callback(col_snapshot, changes, read_time):
    print("【INFO】Firestore FAQ変更検知→キャッシュ再読込")
    load_faq_cache()

def setup_faq_realtime_listener():
    """FAQコレクションのリアルタイムリスナーをセット"""
    faq_ref = db.collection('faq')
    faq_ref.on_snapshot(faq_snapshot_callback)
    print("【INFO】FAQリアルタイムリスナーを設定しました")


def generate_ai_response(user_message: str, store_id: str = None) -> str:
    prompt = get_prompt_for_store(store_id) if store_id else "あなたはフレンドリーなカスタマーサポートです。"
    try:
        resp = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user",   "content": user_message}
            ],
            max_tokens=200,
            temperature=0.7,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI API 呼び出しエラー: {e}")
        return ("【自動応答障害】\n"
            "現在AIによる自動回答が利用できません。\n"
            f"お急ぎの場合は {SUPPORT_PHONE} までご連絡ください。")

def extract_questions(text):
    system_prompt = (
        "ユーザー発言から『質問文だけ』を日本語のリストとしてすべて抽出してください。\n"
        "質問でない部分（雑談・あいさつ・説明など）は除外してください。\n"
        "質問が複数含まれる場合は、必ず1つずつ分割して抽出してください。\n"
        "区切りが曖昧な場合でも一文ごとに分割してください。\n"
        "出力はJSON配列のみ。\n"
        "【例1】\n"
        "ユーザー: 『営業時間と定休日を教えてください。ついでに駐車場はありますか？』\n"
        "→ [\"営業時間を教えてください。\", \"定休日を教えてください。\", \"駐車場はありますか？\"]\n"
        "【例2】\n"
        "ユーザー: 『こんにちは。お弁当はテイクアウトできますか？あと現金以外の支払い方法は？』\n"
        "→ [\"お弁当はテイクアウトできますか？\", \"現金以外の支払い方法は何ですか？\"]\n"
    )
    try:
        resp = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            max_tokens=256,
            temperature=0.0,
        )
        import json
        res = resp.choices[0].message.content.strip()
        res = res.replace("```json", "").replace("```", "").strip()
        questions = json.loads(res)
        # ↓★★★ ここを追加 ★★★
        if isinstance(questions, list):
            if len(questions) == 1 and questions[0].strip() == text.strip():
                import re
                tmp = re.split(r'[？?。！!]', text)
                questions = [q.strip() for q in tmp if q.strip()]
            return questions
        else:
            return [text]
    except Exception as e:
        logger.error(f"質問分割APIエラー: {e}")
        return [text]



def is_complaint(text: str) -> bool:
    # クレームや強い困りごとワード
    keywords = ['クレーム', '返品', '壊れて', '遅い', '不良品', '怒って', '苦情', '困って', '腹立つ', '二度と', '対応が悪い', '届かない', '来ない', '間違い']
    norm = normalize_text(text)
    return any(kw in norm for kw in keywords)
def complaint_response():
    return (
        "ご迷惑をおかけし申し訳ありません。\n"
        f"担当者が直接ご案内しますので、下記までご連絡ください。\n"
        f"【お問い合わせ】{SUPPORT_PHONE}"
    )

def save_message_to_firestore(user_message, response, hit_status, user_id):
    try:
        data = {
            'user_message': user_message,
            'response': response,
            'hit_status': hit_status,
            'user_id': user_id,
            'timestamp': datetime.now()
        }
        db.collection('messages').add(data)
    except Exception as e:
        logger.error(f"Firestore保存失敗: {e}")

app = Flask(__name__)
app.config['PROPAGATE_EXCEPTIONS'] = True

@app.before_request
def log_request():
    auth_hdr = request.headers.get('Authorization')
    logger.debug(f"Request: {request.method} {request.path}, Authorization={auth_hdr!r}")

LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET', '').strip()
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', '').strip()
if not LINE_CHANNEL_SECRET or not LINE_CHANNEL_ACCESS_TOKEN:
    logger.error('LINE_CHANNEL_SECRET または ACCESS_TOKEN が設定されていません')
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

cred_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', '').strip()
if not cred_path:
    logger.error('GOOGLE_APPLICATION_CREDENTIALS が設定されていません')
else:
    try:
        cred = credentials.Certificate(cred_path)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        logger.debug('Firebase initialized')
    except Exception:
        logger.exception('Firebase 初期化に失敗しました')

ADMIN_USER = (os.getenv('ADMIN_USER') or '').strip()
ADMIN_PASS = (os.getenv('ADMIN_PASS') or '').strip()
logger.debug(f'Loaded BASIC creds: ADMIN_USER={ADMIN_USER!r}, ADMIN_PASS={ADMIN_PASS!r}')

def check_auth(username, password):
    return username == ADMIN_USER and password == ADMIN_PASS

def authenticate():
    return Response('Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

def normalize_text(text):
    text = jaconv.z2h(text, kana=True, digit=True, ascii=True)
    text = jaconv.kata2hira(text)
    text = text.lower().strip()
    text = re.sub(r'[！？!?.。、「」\s]', '', text)
    return text

def get_keywords(text):
    text = normalize_text(text)
    return re.findall(r'[ぁ-んァ-ン一-龥a-zA-Z0-9]+', text)

def load_faq_data_from_firestore():
    faqs = []
    for doc in db.collection('faq').stream():
        d = doc.to_dict()
        faqs.append({
            'question': d['question'],
            'aliases': d.get('aliases', []),
            'answer': d['answer']
        })
    return faqs

def advanced_faq_answer_real(user_message: str, threshold: float = 0.8):
    with faq_cache_lock:
        faq_data = faq_cache  # ←ここが重要
    input_norm = normalize_text(user_message)
    input_kw = set(get_keywords(input_norm))
    candidates = []
    for faq in faq_data:
        all_aliases = [faq['question']] + faq.get('aliases', [])
        best_score = 0.0
        for alias in all_aliases:
            alias_norm = normalize_text(alias)
            alias_kw = set(get_keywords(alias_norm))
            inter = input_kw & alias_kw
            if not alias_kw or not input_kw:
                score = 0.0
            else:
                precision = len(inter) / len(alias_kw)
                recall = len(inter) / len(input_kw)
                score = (2 * precision * recall) / (precision + recall) if (precision + recall) else 0.0
            if input_norm == alias_norm or input_norm in alias_norm or alias_norm in input_norm:
                score = 1.0
            best_score = max(best_score, score)
        if best_score >= threshold:
            candidates.append((best_score, faq))
    candidates.sort(reverse=True, key=lambda x: x[0])
    if candidates:
        score, best = candidates[0]
        others = [c[1]['question'] for c in candidates[1:3]]
        return best, score, others
    return None, 0.0, []



@app.route('/callback', methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    logger.debug(f"[DEBUG][callback] signature={signature}")
    logger.debug(f"[DEBUG][callback] body={body}")
    try:
        handler.handle(body, signature)
    except Exception as e:
        logger.error(f"[ERROR][callback] handler.handle 例外: {e}")
    return 'OK', 200
def log_audit(user, action, target, details):
    db.collection('audit_logs').add({
        "user": user,
        "action": action,
        "target": target,
        "details": details,
        "timestamp": datetime.now()
    })

def get_prompt_for_store(store_id):
    doc = db.collection("settings").document(store_id).get()
    if doc.exists:
        return doc.to_dict().get("prompt", "あなたはフレンドリーなカスタマーサポートです。")
    else:
        return "あなたはフレンドリーなカスタマーサポートです。"

def generate_ai_response(user_message: str, store_id: str = None) -> str:
    prompt = get_prompt_for_store(store_id) if store_id else "あなたはフレンドリーなカスタマーサポートです。"
    try:
        resp = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user",   "content": user_message}
            ],
            max_tokens=200,
            temperature=0.7,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI API 呼び出しエラー: {e}")
        return ("【自動応答障害】\n"
            "現在AIによる自動回答が利用できません。\n"
            f"お急ぎの場合は {SUPPORT_PHONE} までご連絡ください。")

def load_faq_data_from_firestore(lang=None, category=None):
    faqs = []
    q = db.collection('faq')
    if lang:
        q = q.where('lang', '==', lang)
    if category:
        q = q.where('category', '==', category)
    for doc in q.stream():
        d = doc.to_dict()
        d['id'] = doc.id
        faqs.append(d)
    return faqs

@app.route('/api/faq', methods=['GET'])
@requires_auth
def api_get_faqs():
    lang = request.args.get('lang')
    category = request.args.get('category')
    faqs = load_faq_data_from_firestore(lang=lang, category=category)
    return jsonify(faqs)

@app.route('/api/faq', methods=['POST'])
@requires_auth
def api_add_faq():
    data = request.json
    if not data or 'question' not in data or 'answer' not in data or 'lang' not in data:
        return jsonify({'error': 'question, answer, langは必須です'}), 400
    new_doc = db.collection('faq').document()
    new_doc.set({
        'question': data['question'],
        'aliases': data.get('aliases', []),
        'answer': data['answer'],
        'lang': data['lang'],
        'category': data.get('category', '')
    })
    log_audit(request.authorization.username, "add", new_doc.id, data)
    return jsonify({'result': 'ok', 'id': new_doc.id})

@app.route('/api/faq/<doc_id>', methods=['PUT'])
@requires_auth
def api_update_faq(doc_id):
    data = request.json
    doc_ref = db.collection('faq').document(doc_id)
    if not doc_ref.get().exists:
        return jsonify({'error': '指定IDのFAQが存在しません'}), 404
    doc_ref.update({
        'question': data.get('question'),
        'aliases': data.get('aliases', []),
        'answer': data.get('answer'),
        'lang': data.get('lang', 'ja'),
        'category': data.get('category', '')
    })
    log_audit(request.authorization.username, "edit", doc_id, data)
    return jsonify({'result': 'ok'})

@app.route('/api/faq/<doc_id>', methods=['DELETE'])
@requires_auth
def api_delete_faq(doc_id):
    doc_ref = db.collection('faq').document(doc_id)
    if not doc_ref.get().exists:
        return jsonify({'error': '指定IDのFAQが存在しません'}), 404
    old_data = doc_ref.get().to_dict()
    doc_ref.delete()
    log_audit(request.authorization.username, "delete", doc_id, old_data)
    log_faq_change(request.authorization.username, 'delete', doc_id, old_data, None)


    return jsonify({'result': 'ok'})

def reply_with_carousel(event, faq_list):
    columns = []
    for faq in faq_list[:10]:  # LINEカルーセルは最大10件まで
        columns.append(
            CarouselColumn(
                title=faq.get("category", "FAQ")[:40],  # 40字以内
                text=faq.get("summary", faq["question"])[:60],  # 60字以内
                actions=[
                    MessageAction(label="詳細を見る", text=faq["question"])
                ]
            )
        )
    carousel = TemplateSendMessage(
        alt_text="FAQ候補一覧",
        template=CarouselTemplate(columns=columns)
    )
    line_bot_api.reply_message(event.reply_token, carousel)

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    try:
        user_id = event.source.user_id
        text_in = event.message.text

        # クレーム検知
        norm = normalize_text(text_in)
        if is_complaint(norm):
            reply_text = complaint_response()
            save_message_to_firestore(text_in, reply_text, 'クレーム', user_id)
            return line_bot_api.reply_message(
                event.reply_token, TextSendMessage(text=reply_text)
            )

        # 質問分割
        questions = extract_questions(text_in)

        all_replies = []
        for q in questions:
            norm = normalize_text(q)
            # 完全一致
            for faq in faq_cache:
                if norm == normalize_text(faq['question']):
                    all_replies.append(f"Q: {faq['question']}\nA: {faq['answer']}")
                    break
            else:
                # 類似度判定
                best, score, others = advanced_faq_answer_real(q)
                THRESHOLD = 0.6
                if best and score >= THRESHOLD:
                    rep = f"Q: {best['question']}\nA: {best['answer']}"
                    uniq_others = []
                    for o in others:
                        if o and o != best['question'] and o not in uniq_others:
                            uniq_others.append(o)
                    # --- ここでカルーセルに切り替え ---
                    if uniq_others and len(uniq_others) > 1:
                        other_faqs = [f for f in faq_cache if f['question'] in uniq_others]
                        reply_with_carousel(event, other_faqs)
                        return
                    # --- ここまで ---
                    all_replies.append(rep)
                else:
                    reply = f"Q: {q}\nA: {complaint_response()}"
                    all_replies.append(reply)
                    save_message_to_firestore(q, reply, '未ヒット', user_id)


        if all_replies:
            reply_text = "\n\n".join(all_replies[:3])
            save_message_to_firestore(text_in, reply_text, '複数質問', user_id)
            line_bot_api.reply_message(
                event.reply_token, TextSendMessage(text=reply_text)
            )

    except Exception as e:
        logger.exception(f"Reply failed: {e}")
        try:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=f"【障害案内】\n現在システムが混み合っています。お急ぎの場合は {SUPPORT_PHONE} へご連絡ください。"
                )
            )
        except Exception as ex:
            logger.error(f"障害案内の返信も失敗: {ex}")


@app.route('/admin', methods=['GET'])
@requires_auth
def admin():
    faqs = faq_cache
    messages = []
    for doc in db.collection('messages').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(100).stream():
        d = doc.to_dict()
        messages.append(d)
    unresolved = [m for m in messages if m.get('hit_status') in ('未ヒット', 'クレーム')]

    # --- 未解決TOP10集計 ---
    unresolved_only = [m for m in messages if m.get('hit_status') == '未ヒット']
    counter = Counter(m['user_message'] for m in unresolved_only)
    top_unresolved = counter.most_common(10)

    return render_template('admin.html',
                           faqs=faqs,
                           messages=messages,
                           unresolved=unresolved,
                           top_unresolved=top_unresolved) 
@app.route('/admin/faq_save', methods=['POST'])
@requires_auth
def admin_faq_save():
    faq_id = request.form.get('faq_id')
    question = request.form.get('question')
    aliases = [s.strip() for s in request.form.get('aliases', '').split(',') if s.strip()]
    answer = request.form.get('answer')

    if faq_id:  # 編集
        doc_ref = db.collection('faq').document(faq_id)
        doc_ref.update({'question': question, 'aliases': aliases, 'answer': answer})
    else:       # 追加
        db.collection('faq').add({'question': question, 'aliases': aliases, 'answer': answer})

    global faq_cache
    faq_cache = load_faq_data_from_firestore()
    return redirect(url_for('admin'))

@app.route('/admin/faq_delete', methods=['POST'])
@requires_auth
def admin_faq_delete():
    faq_id = request.form.get('faq_id')
    if faq_id:
        db.collection('faq').document(faq_id).delete()
    global faq_cache
    faq_cache = load_faq_data_from_firestore()
    return redirect(url_for('admin'))
import csv
import io
import json
from flask import send_file, make_response

@app.route('/admin/faq_export', methods=['GET'])
@requires_auth
def admin_faq_export():
    format = request.args.get('format', 'csv')  # ?format=json でJSON出力
    faqs = load_faq_data_from_firestore()

    if format == 'json':
        # JSONエクスポート
        response = make_response(json.dumps(faqs, ensure_ascii=False, indent=2))
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        response.headers['Content-Disposition'] = 'attachment; filename=faq_export.json'
        return response
    else:
        # CSVエクスポート（question,aliases,answer）
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['question', 'aliases', 'answer'])
        for faq in faqs:
            aliases = ','.join(faq.get('aliases', []))
            writer.writerow([faq['question'], aliases, faq['answer']])
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        response.headers['Content-Disposition'] = 'attachment; filename=faq_export.csv'
        return response
@app.route('/admin/faq_import', methods=['POST'])
@requires_auth
def admin_faq_import():
    file = request.files.get('faq_file')
    if not file:
        return "ファイル未選択", 400

    ext = file.filename.rsplit('.', 1)[-1].lower()
    imported = 0

    if ext == 'json':
        data = json.load(file)
        for faq in data:
            db.collection('faq').add({
                'question': faq.get('question', ''),
                'aliases': faq.get('aliases', []),
                'answer': faq.get('answer', '')
            })
            imported += 1
    elif ext == 'csv':
        # CSVは1行目: question,aliases,answer
        file.stream.seek(0)
        decoded = io.StringIO(file.stream.read().decode('utf-8'))
        reader = csv.DictReader(decoded)
        for row in reader:
            aliases = [a.strip() for a in row.get('aliases', '').split(',') if a.strip()]
            db.collection('faq').add({
                'question': row.get('question', ''),
                'aliases': aliases,
                'answer': row.get('answer', '')
            })
            imported += 1
    else:
        return "csv/jsonのみ対応", 400

    # FAQキャッシュ更新
    global faq_cache
    faq_cache = load_faq_data_from_firestore()
    return redirect(url_for('admin'))


if __name__ == '__main__':
    load_faq_cache()                # FAQキャッシュ初期化
    setup_faq_realtime_listener()   # FAQリアルタイム監視開始
    app.run(host='127.0.0.1', port=5000, debug=False)
