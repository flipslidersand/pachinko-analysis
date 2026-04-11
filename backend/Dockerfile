FROM python:3.12-slim

WORKDIR /app

# 依存パッケージのインストール
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python 依存関係
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコード
COPY . .

# FastAPI サーバー起動
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
