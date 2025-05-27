import json
import os
import difflib
import datetime

FAQ_PATH = os.path.join(os.path.dirname(__file__), '../data/faq_data.json')
LOG_PATH = os.path.join(os.path.dirname(__file__), '../data/logs.json')

SYNONYM_MAP = {
    "OPEN": "営業時間",
    "オープン": "営業時間",
    "支払": "支払い",
    "カード払い": "支払い方法",
    "カードで払える": "支払い方法",
    "カード使える": "支払い方法",
    "クレジットカード": "支払い方法",
    "支払い": "支払い方法",
    # 必要に応じて追加
}

def preprocess_input(user_input):
    for k, v in SYNONYM_MAP.items():
        if k in user_input:
            user_input = user_input.replace(k, v)
    return user_input

def load_faq_data():
    with open(FAQ_PATH, encoding='utf-8') as f:
        return json.load(f)

def save_log(user_input, bot_answer, hit_status):
    log_entry = {
        "datetime": datetime.datetime.now().isoformat(timespec='seconds'),
        "input": user_input,
        "answer": bot_answer,
        "hit_status": hit_status
    }
    try:
        with open(LOG_PATH, encoding='utf-8') as f:
            logs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logs = []
    logs.append(log_entry)
    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

def get_faq_answer(user_input, threshold=0.4):
    user_input = preprocess_input(user_input)
    faq_data = load_faq_data()
    hit_status = "未ヒット"
    answer = "申し訳ありませんが、そのご質問にはお答えできません。"

    # 完全一致
    for faq in faq_data:
        if faq['question'] == user_input:
            hit_status = "完全一致"
            answer = faq['answer']
            break
    else:
        # 部分一致
        for faq in faq_data:
            if faq['question'] in user_input or user_input in faq['question']:
                hit_status = "部分一致"
                answer = faq['answer']
                break
        else:
            # 類似度判定
            max_ratio = 0
            best_answer = None
            for faq in faq_data:
                ratio = difflib.SequenceMatcher(None, faq['question'], user_input).ratio()
                if ratio > max_ratio:
                    max_ratio = ratio
                    best_answer = faq['answer']
            if max_ratio >= threshold:
                hit_status = "類似一致"
                answer = best_answer

    save_log(user_input, answer, hit_status)  # ログ保存

    return answer
