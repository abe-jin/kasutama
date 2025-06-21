# ベースイメージ
FROM python:3.11-slim

# 作業ディレクトリ
WORKDIR /app

# 依存関係を先にコピーしてインストール（キャッシュ活用）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# 環境変数設定例
ENV PYTHONUNBUFFERED=1

# ポートを公開
EXPOSE 5000

# 起動コマンド
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]