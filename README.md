# カスタマーサポートBot（LINE × Flask × Firestore）

## 概要
LINEを通じてFAQ回答・会話ログ管理・クレーム検知を行うカスタマーサポートBotです。

## 主な機能
- LINE Botとの連携（公式SDK）
- FirestoreによるFAQ管理・リアルタイム更新
- 類似度スコアに基づくFAQ検索（F1ベース）
- 管理画面（Flask）でのFAQ編集・会話履歴閲覧
- クレーム検出・OpenAIによるバックアップ応答
- CSV/JSONインポート・エクスポート
- セッションログイン＋CSRF対応
- GitHub ActionsによるCI（pytest自動実行）

## セットアップ手順

### 1. Python環境

```bash
git clone https://github.com/abe-jin/kasutama.git
cd kasutama
python -m venv venv
venv\Scripts\activate  # Mac/Linuxは source venv/bin/activate
pip install -r requirements.txt
