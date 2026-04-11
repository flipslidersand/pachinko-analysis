"""出玉パターン分析（K-means クラスタリング・改善版）"""
import logging
from sqlalchemy import text
from sqlalchemy.orm import Session
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import numpy as np
import pandas as pd
from datetime import date, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 定数
CLUSTER_NAMES = {
    "high": "high_variance_positive",
    "mid": "stable_mid",
    "low": "low_performance"
}


def analyze_machine_patterns(
    db: Session,
    store_id: int,
    machine_type: str = "S",
    n_clusters: int = 3,
    lookback_days: int = 30
) -> Optional[Dict]:
    """
    機種の出玉パターンを分析（K-means クラスタリング）

    Args:
        db: DB セッション
        store_id: 店舗ID
        machine_type: 機種タイプ
        n_clusters: クラスタ数
        lookback_days: 分析対象期間

    Returns:
        パターン分析結果
    """
    try:
        logger.info(
            f"🎯 Analyzing patterns for store {store_id}, "
            f"type {machine_type}, clusters {n_clusters}"
        )

        # 過去 lookback_days のデータを取得
        target_date = date.today()
        start_date = target_date - timedelta(days=lookback_days)

        sql = """
        SELECT
            m.id,
            m.name,
            AVG(CAST(dr.diff AS FLOAT)) as avg_diff,
            STDDEV(CAST(dr.diff AS FLOAT)) as stddev_diff,
            MIN(CAST(dr.diff AS FLOAT)) as min_diff,
            MAX(CAST(dr.diff AS FLOAT)) as max_diff,
            COUNT(*) as play_count,
            SUM(CASE WHEN dr.diff > 0 THEN 1 ELSE 0 END) as win_days
        FROM machines m
        LEFT JOIN daily_results dr ON m.id = dr.machine_id
            AND dr.store_id = :store_id
            AND dr.date >= :start_date
            AND dr.date < :target_date
        WHERE m.type = :machine_type
        GROUP BY m.id, m.name
        HAVING COUNT(*) >= 2
        """

        result = db.execute(text(sql), {
            "store_id": store_id,
            "machine_type": machine_type,
            "start_date": start_date,
            "target_date": target_date,
        }).fetchall()

        if not result or len(result) < n_clusters:
            logger.warning(
                f"⚠️ Not enough machines for clustering: {len(result)} < {n_clusters}"
            )
            return {
                "status": "insufficient_data",
                "message": f"Need at least {n_clusters} machines",
                "patterns": []
            }

        # DataFrame に変換
        df = pd.DataFrame(
            result,
            columns=[
                "id", "name", "avg_diff", "stddev_diff",
                "min_diff", "max_diff", "play_count", "win_days"
            ]
        )

        # NaN処理
        df = df.fillna(0)

        # 勝率を計算
        df["win_rate"] = (df["win_days"] / df["play_count"] * 100).round(1)

        # ボラティリティを計算
        df["volatility"] = (df["max_diff"] - df["min_diff"]).abs()

        # 特徴量を準備（標準化）
        feature_cols = ["avg_diff", "stddev_diff", "volatility", "win_rate"]
        X = df[feature_cols].values

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # K-means クラスタリング
        kmeans = KMeans(
            n_clusters=n_clusters,
            random_state=42,
            n_init=10,
            max_iter=300
        )
        clusters = kmeans.fit_predict(X_scaled)
        df["cluster"] = clusters

        # クラスタの特性を分析
        cluster_names = {}
        for cluster_id in range(n_clusters):
            cluster_df = df[df["cluster"] == cluster_id]
            avg_diff_in_cluster = cluster_df["avg_diff"].mean()
            volatility_in_cluster = cluster_df["volatility"].mean()

            # 中立的なラベルを付与
            if avg_diff_in_cluster > 0 and volatility_in_cluster > stddev_diff.mean():
                cluster_names[cluster_id] = "high_variance_positive"
            elif avg_diff_in_cluster >= 0:
                cluster_names[cluster_id] = "stable_mid"
            else:
                cluster_names[cluster_id] = "low_performance"

        # 結果を整理
        patterns = []
        for cluster_id in range(n_clusters):
            cluster_df = df[df["cluster"] == cluster_id]

            pattern_info = {
                "pattern_name": cluster_names[cluster_id],
                "machines_count": len(cluster_df),
                "machines": [
                    {
                        "id": int(row["id"]),
                        "name": row["name"],
                        "avg_diff": float(row["avg_diff"]),
                        "stddev": float(row["stddev_diff"]),
                        "win_rate": float(row["win_rate"]),
                        "volatility": float(row["volatility"]),
                        "play_count": int(row["play_count"]),
                    }
                    for _, row in cluster_df.iterrows()
                ],
                "summary": {
                    "avg_diff_in_pattern": float(cluster_df["avg_diff"].mean()),
                    "stddev_diff_in_pattern": float(cluster_df["stddev_diff"].mean()),
                    "volatility_in_pattern": float(cluster_df["volatility"].mean()),
                    "win_rate_in_pattern": float(cluster_df["win_rate"].mean()),
                    "machines_count": len(cluster_df),
                }
            }
            patterns.append(pattern_info)

        # 平均差枚で降順ソート
        patterns = sorted(
            patterns,
            key=lambda x: x["summary"]["avg_diff_in_pattern"],
            reverse=True
        )

        logger.info(f"✅ Analyzed {len(df)} machines into {n_clusters} patterns")

        return {
            "status": "success",
            "patterns": patterns,
            "total_machines": len(df),
            "feature_columns": feature_cols,
        }

    except Exception as e:
        logger.error(f"❌ Error analyzing patterns: {e}")
        return {
            "status": "error",
            "message": str(e),
            "patterns": []
        }
