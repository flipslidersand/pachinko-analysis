"""営業成績予測モデル（Random Forest）"""
import logging
from sqlalchemy import text
from sqlalchemy.orm import Session
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
import numpy as np
import pandas as pd
from datetime import date, timedelta
import pickle

logger = logging.getLogger(__name__)


def predict_daily_performance(db: Session, store_id: int, machine_type: str = "S"):
    """本日の営業成績を予測

    Args:
        db: DB セッション
        store_id: 店舗 ID
        machine_type: 機種タイプ

    Returns:
        予測結果
    """
    try:
        # 過去14日間のデータを取得
        sql = """
        SELECT
            dr.date,
            EXTRACT(DOW FROM dr.date) as day_of_week,
            m.id as machine_id,
            m.name as machine_name,
            COALESCE(CAST(dr.diff AS FLOAT), 0) as diff
        FROM daily_results dr
        JOIN machines m ON dr.machine_id = m.id
        WHERE dr.store_id = :store_id
            AND dr.date >= :start_date
            AND m.type = :machine_type
        ORDER BY dr.date, m.id
        """

        start_date = date.today() - timedelta(days=14)

        result = db.execute(text(sql), {
            "store_id": store_id,
            "start_date": start_date,
            "machine_type": machine_type
        }).fetchall()

        if not result or len(result) < 10:
            logger.warning("Not enough data for prediction")
            return {
                "status": "insufficient_data",
                "message": f"Need at least 10 data points, got {len(result)}"
            }

        # データフレーム作成
        df = pd.DataFrame(result, columns=["date", "day_of_week", "machine_id", "machine_name", "diff"])

        # 特徴量エンジニアリング
        X = df[["day_of_week", "machine_id"]].values
        y = df["diff"].values

        # モデル学習
        model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
        model.fit(X, y)

        # 本日の予測（全機種）
        today = date.today()
        day_of_week = today.weekday()

        predictions = []
        unique_machines = df["machine_id"].unique()

        for machine_id in unique_machines:
            X_pred = np.array([[day_of_week, machine_id]])
            pred_diff = model.predict(X_pred)[0]

            machine_name = df[df["machine_id"] == machine_id]["machine_name"].iloc[0]

            predictions.append({
                "machine_id": int(machine_id),
                "machine_name": machine_name,
                "predicted_diff": float(pred_diff),
                "confidence": 0.75  # ダミー信頼度
            })

        logger.info(f"✅ Predicted performance for {len(predictions)} machines")

        return {
            "status": "success",
            "date": str(today),
            "day_of_week": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][day_of_week],
            "predictions": predictions,
            "model_accuracy": float(model.score(X, y))
        }

    except Exception as e:
        logger.error(f"❌ Error predicting performance: {e}")
        return {
            "status": "error",
            "message": str(e)
        }
