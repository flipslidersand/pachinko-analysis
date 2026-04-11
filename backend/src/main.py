"""FastAPI メインアプリケーション"""
import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from src.database.connection import init_db
from src.routers import scraper
from src.scheduler.jobs import init_scheduler

# ログ設定
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = FastAPI(
    title="パチスロ分析API",
    description="パチスロ営業データ分析・予測システム",
    version="0.1.0"
)

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ルーター登録
app.include_router(scraper.router, prefix="/api/scraper", tags=["scraper"])

from src.routers import analysis
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])

# 静的ファイルの提供
dashboard_path = Path(__file__).parent.parent / "dashboard.html"
if dashboard_path.exists():
    from fastapi.responses import FileResponse

    @app.get("/dashboard")
    async def serve_dashboard():
        return FileResponse(str(dashboard_path))

# グローバルスケジューラー
scheduler = None


@app.on_event("startup")
async def startup_event():
    """起動時のイベント"""
    global scheduler
    try:
        logger.info("🚀 Initializing database...")
        init_db()
        logger.info("✅ Database initialized")

        # スケジューラーを起動
        logger.info("🚀 Starting scheduler...")
        scheduler = init_scheduler()
        scheduler.start()
        logger.info("✅ Scheduler started")

    except Exception as e:
        logger.error(f"❌ Initialization failed: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """シャットダウン時のイベント"""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown()
        logger.info("✅ Scheduler shutdown")


@app.get("/api/health")
async def health_check():
    """ヘルスチェック"""
    return {
        "status": "healthy",
        "service": "pachinko-analysis-api"
    }


@app.get("/")
async def root():
    """ルートエンドポイント"""
    return {
        "message": "パチスロ分析API へようこそ",
        "version": "0.1.0"
    }
