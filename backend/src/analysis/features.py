"""時系列特徴量生成（共通モジュール）"""
import logging
from datetime import date, timedelta
from typing import Optional

import pandas as pd
import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# 定数
HIT_THRESHOLD = 1000  # 当たり判定：差枚 > HIT_THRESHOLD なら hit_label=1


def generate_features_for_training(
    db: Session,
    store_id: int,
    machine_type: str,
    prediction_date: date,
    lookback_days: int = 60,
    machine_id: Optional[int] = None
) -> pd.DataFrame:
    """
    学習用特徴量を生成

    Args:
        db: DB セッション
        store_id: 店舗ID
        machine_type: 機種タイプ ('S' or 'P')
        prediction_date: 予測対象日（この日より前のデータのみ使用）
        lookback_days: 過去何日分を対象にするか
        machine_id: 特定機種を指定（None = 全機種）

    Returns:
        特徴量 DataFrame
    """
    try:
        logger.info(
            f"🔄 Generating features for store {store_id}, "
            f"type {machine_type}, prediction_date {prediction_date}"
        )

        # 過去データを取得（prediction_date より前）
        start_date = prediction_date - timedelta(days=lookback_days)

        sql = """
        SELECT
            dms.machine_id,
            dms.target_date,
            dms.diff,
            dms.games_count,
            m.name as machine_name
        FROM daily_machine_stats dms
        JOIN machines m ON dms.machine_id = m.id
        WHERE dms.store_id = :store_id
            AND dms.machine_type = :machine_type
            AND dms.target_date < :prediction_date
            AND dms.target_date >= :start_date
        ORDER BY dms.machine_id, dms.target_date
        """

        params = {
            "store_id": store_id,
            "machine_type": machine_type,
            "prediction_date": prediction_date,
            "start_date": start_date,
        }

        if machine_id:
            sql += " AND dms.machine_id = :machine_id"
            params["machine_id"] = machine_id

        result = db.execute(text(sql), params).fetchall()

        if not result:
            logger.warning(f"⚠️ No data found for feature generation")
            return pd.DataFrame()

        # DataFrame に変換
        df = pd.DataFrame(
            result,
            columns=["machine_id", "target_date", "diff", "games_count", "machine_name"]
        )

        # ===== 店舗レベル統計を事前計算（キャッシュ） =====
        store_stats_7 = {}
        store_stats_30 = {}

        for target_date_val in df["target_date"].unique():
            date_df = df[df["target_date"] < target_date_val]

            # 7日統計
            df_7d = date_df[date_df["target_date"] >= (target_date_val - timedelta(days=7))]
            if len(df_7d) > 0:
                store_stats_7[target_date_val] = {
                    "avg_diff": float(df_7d["diff"].mean()),
                    "total_games": int(df_7d["games_count"].sum()),
                    "win_rate": float(np.sum(df_7d["diff"] > 0) / len(df_7d) * 100) if len(df_7d) > 0 else 0.0,
                }
            else:
                store_stats_7[target_date_val] = {"avg_diff": 0.0, "total_games": 0, "win_rate": 0.0}

            # 30日統計
            df_30d = date_df[date_df["target_date"] >= (target_date_val - timedelta(days=30))]
            if len(df_30d) > 0:
                store_stats_30[target_date_val] = {
                    "avg_diff": float(df_30d["diff"].mean()),
                }
            else:
                store_stats_30[target_date_val] = {"avg_diff": 0.0}

        # 機種ごとにグループ化して特徴量を生成
        features_list = []

        for machine_id_val in df["machine_id"].unique():
            machine_df = df[df["machine_id"] == machine_id_val].sort_values("target_date").reset_index(drop=True)

            if len(machine_df) < 2:
                continue  # 最低2日分のデータが必要

            machine_name = machine_df["machine_name"].iloc[0]

            # 最後の日を基準として特徴量を生成
            for idx in range(1, len(machine_df)):
                row = machine_df.iloc[idx]
                feature_date = row["target_date"]

                # 前日データ
                prev_1d_diff = machine_df.iloc[idx - 1]["diff"] if idx >= 1 else None
                prev_2d_diff = machine_df.iloc[idx - 2]["diff"] if idx >= 2 else None
                prev_3d_diff = machine_df.iloc[idx - 3]["diff"] if idx >= 3 else None

                # 3日、7日、30日の移動平均と標準偏差
                window_3d = machine_df.iloc[max(0, idx - 3):idx]["diff"].values
                window_7d = machine_df.iloc[max(0, idx - 7):idx]["diff"].values
                window_30d = machine_df.iloc[max(0, idx - 30):idx]["diff"].values

                avg_3d = float(np.mean(window_3d)) if len(window_3d) > 0 else None
                avg_7d = float(np.mean(window_7d)) if len(window_7d) > 0 else None
                avg_30d = float(np.mean(window_30d)) if len(window_30d) > 0 else None

                stddev_3d = float(np.std(window_3d)) if len(window_3d) > 1 else 0.0
                stddev_7d = float(np.std(window_7d)) if len(window_7d) > 1 else 0.0
                stddev_30d = float(np.std(window_30d)) if len(window_30d) > 1 else 0.0

                # トレンド（過去7日）
                window_trend = machine_df.iloc[max(0, idx - 7):idx]["diff"].values
                trend_up = int(np.sum(window_trend > 0))
                trend_down = int(np.sum(window_trend < 0))
                positive_ratio = float(trend_up / len(window_trend) * 100) if len(window_trend) > 0 else 0.0

                # ボラティリティ（過去30日）
                max_diff_30d = int(np.max(window_30d)) if len(window_30d) > 0 else None
                min_diff_30d = int(np.min(window_30d)) if len(window_30d) > 0 else None
                volatility = float(np.std(window_30d)) if len(window_30d) > 1 else 0.0

                # ゲーム数
                total_games_1d = int(row["games_count"]) if row["games_count"] else None

                # 曜日
                day_of_week = int(feature_date.weekday())

                # ラベル（スロット用）
                hit_label = 1 if row["diff"] > HIT_THRESHOLD else 0

                # ===== 店舗レベル特徴量 =====
                store_stat_7 = store_stats_7.get(feature_date, {})
                store_stat_30 = store_stats_30.get(feature_date, {})

                store_avg_diff_7 = int(store_stat_7.get("avg_diff", 0))
                store_avg_diff_30 = int(store_stat_30.get("avg_diff", 0))
                store_diff_momentum = store_avg_diff_7 - store_avg_diff_30
                store_total_games_7 = store_stat_7.get("total_games", 0)
                store_win_rate_7 = store_stat_7.get("win_rate", 0.0)

                # 台の稼働関連
                window_games_7 = machine_df.iloc[max(0, idx - 7):idx]["games_count"].values
                games_avg_7 = int(np.mean(window_games_7)) if len(window_games_7) > 0 else 0

                # 店舗平均稼働
                store_games_7d = df[
                    (df["target_date"] >= (feature_date - timedelta(days=7))) &
                    (df["target_date"] < feature_date)
                ]
                store_avg_games_7 = int(store_games_7d["games_count"].mean()) if len(store_games_7d) > 0 else 1
                games_per_machine_ratio = round(games_avg_7 / store_avg_games_7, 2) if store_avg_games_7 > 0 else 0.0

                # 稼働トレンド（直近7日 vs 直近14日）
                window_games_7 = machine_df.iloc[max(0, idx - 7):idx]["games_count"].values
                window_games_14 = machine_df.iloc[max(0, idx - 14):idx - 7]["games_count"].values

                avg_games_7 = float(np.mean(window_games_7)) if len(window_games_7) > 0 else 0.0
                avg_games_14 = float(np.mean(window_games_14)) if len(window_games_14) > 0 else 0.0

                if avg_games_7 > avg_games_14 * 1.1:  # 10%以上増加
                    games_trend_7 = 1
                elif avg_games_7 < avg_games_14 * 0.9:  # 10%以上減少
                    games_trend_7 = -1
                else:
                    games_trend_7 = 0

                features_list.append({
                    "machine_id": int(machine_id_val),
                    "machine_name": machine_name,
                    "feature_date": feature_date,
                    "prev_1d_diff": prev_1d_diff,
                    "prev_2d_diff": prev_2d_diff,
                    "prev_3d_diff": prev_3d_diff,
                    "avg_3d_diff": avg_3d,
                    "avg_7d_diff": avg_7d,
                    "avg_30d_diff": avg_30d,
                    "stddev_3d": stddev_3d,
                    "stddev_7d": stddev_7d,
                    "stddev_30d": stddev_30d,
                    "trend_up_days_7d": trend_up,
                    "trend_down_days_7d": trend_down,
                    "positive_ratio_7d": positive_ratio,
                    "max_diff_30d": max_diff_30d,
                    "min_diff_30d": min_diff_30d,
                    "volatility_30d": volatility,
                    "total_games_1d": total_games_1d,
                    "day_of_week": day_of_week,
                    "hit_label": hit_label,
                    # ===== 新規: 店舗レベル特徴量 =====
                    "store_avg_diff_7": store_avg_diff_7,
                    "store_avg_diff_30": store_avg_diff_30,
                    "store_diff_momentum": store_diff_momentum,
                    "games_avg_7": games_avg_7,
                    "games_per_machine_ratio": games_per_machine_ratio,
                    "store_total_games_7": store_total_games_7,
                    "games_trend_7": games_trend_7,
                    "store_win_rate_7": store_win_rate_7,
                })

        features_df = pd.DataFrame(features_list)

        logger.info(f"✅ Generated {len(features_df)} feature rows")
        return features_df

    except Exception as e:
        logger.error(f"❌ Error generating features: {e}")
        raise


def save_features_to_db(
    db: Session,
    store_id: int,
    features_df: pd.DataFrame
) -> int:
    """
    特徴量を DB に保存

    Args:
        db: DB セッション
        store_id: 店舗ID
        features_df: 特徴量 DataFrame

    Returns:
        保存件数
    """
    if features_df.empty:
        logger.warning("⚠️ No features to save")
        return 0

    try:
        saved_count = 0

        for _, row in features_df.iterrows():
            sql = """
            INSERT INTO ml_features (
                store_id, machine_id, machine_type, feature_date,
                prev_1d_diff, prev_2d_diff, prev_3d_diff,
                avg_3d_diff, avg_7d_diff, avg_30d_diff,
                stddev_3d, stddev_7d, stddev_30d,
                trend_up_days_7d, trend_down_days_7d, positive_ratio_7d,
                max_diff_30d, min_diff_30d, volatility_30d,
                total_games_1d, day_of_week, hit_label,
                store_avg_diff_7, store_avg_diff_30, store_diff_momentum,
                games_avg_7, games_per_machine_ratio, store_total_games_7,
                games_trend_7, store_win_rate_7
            ) VALUES (
                :store_id, :machine_id, :machine_type, :feature_date,
                :prev_1d_diff, :prev_2d_diff, :prev_3d_diff,
                :avg_3d_diff, :avg_7d_diff, :avg_30d_diff,
                :stddev_3d, :stddev_7d, :stddev_30d,
                :trend_up_days_7d, :trend_down_days_7d, :positive_ratio_7d,
                :max_diff_30d, :min_diff_30d, :volatility_30d,
                :total_games_1d, :day_of_week, :hit_label,
                :store_avg_diff_7, :store_avg_diff_30, :store_diff_momentum,
                :games_avg_7, :games_per_machine_ratio, :store_total_games_7,
                :games_trend_7, :store_win_rate_7
            ) ON CONFLICT (store_id, machine_id, feature_date) DO UPDATE SET
                avg_3d_diff = :avg_3d_diff,
                avg_7d_diff = :avg_7d_diff,
                avg_30d_diff = :avg_30d_diff,
                hit_label = :hit_label,
                store_avg_diff_7 = :store_avg_diff_7,
                store_avg_diff_30 = :store_avg_diff_30,
                store_diff_momentum = :store_diff_momentum,
                games_avg_7 = :games_avg_7,
                games_per_machine_ratio = :games_per_machine_ratio,
                store_total_games_7 = :store_total_games_7,
                games_trend_7 = :games_trend_7,
                store_win_rate_7 = :store_win_rate_7
            """

            params = {
                "store_id": store_id,
                "machine_id": int(row["machine_id"]),
                "machine_type": "S",  # 後で動的にする
                "feature_date": row["feature_date"],
                "prev_1d_diff": row["prev_1d_diff"],
                "prev_2d_diff": row["prev_2d_diff"],
                "prev_3d_diff": row["prev_3d_diff"],
                "avg_3d_diff": row["avg_3d_diff"],
                "avg_7d_diff": row["avg_7d_diff"],
                "avg_30d_diff": row["avg_30d_diff"],
                "stddev_3d": row["stddev_3d"],
                "stddev_7d": row["stddev_7d"],
                "stddev_30d": row["stddev_30d"],
                "trend_up_days_7d": row["trend_up_days_7d"],
                "trend_down_days_7d": row["trend_down_days_7d"],
                "positive_ratio_7d": row["positive_ratio_7d"],
                "max_diff_30d": row["max_diff_30d"],
                "min_diff_30d": row["min_diff_30d"],
                "volatility_30d": row["volatility_30d"],
                "total_games_1d": row["total_games_1d"],
                "day_of_week": row["day_of_week"],
                "hit_label": row["hit_label"],
                # ===== 新規: 店舗レベル特徴量 =====
                "store_avg_diff_7": row.get("store_avg_diff_7", 0),
                "store_avg_diff_30": row.get("store_avg_diff_30", 0),
                "store_diff_momentum": row.get("store_diff_momentum", 0),
                "games_avg_7": row.get("games_avg_7", 0),
                "games_per_machine_ratio": row.get("games_per_machine_ratio", 0.0),
                "store_total_games_7": row.get("store_total_games_7", 0),
                "games_trend_7": row.get("games_trend_7", 0),
                "store_win_rate_7": row.get("store_win_rate_7", 0.0),
            }

            db.execute(text(sql), params)
            saved_count += 1

        db.commit()
        logger.info(f"✅ Saved {saved_count} features to DB")
        return saved_count

    except Exception as e:
        logger.error(f"❌ Error saving features: {e}")
        db.rollback()
        raise
