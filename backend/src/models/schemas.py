"""Pydantic スキーマ定義"""
from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional


class StoreCreate(BaseModel):
    """店舗作成スキーマ"""
    name: str
    hall_id: str
    url: Optional[str] = None
    region: Optional[str] = None


class DailyResultCreate(BaseModel):
    """日次営業成績作成スキーマ"""
    store_id: int
    machine_id: Optional[int] = None
    date: date
    games_count: Optional[int] = None
    medals_in: Optional[int] = None
    medals_out: Optional[int] = None
    diff: Optional[int] = None


class MachineCreate(BaseModel):
    """機種作成スキーマ"""
    name: str
    type: str  # 'pachislot' or 'pachinko'
    maker: Optional[str] = None


class ScrapedMachine(BaseModel):
    """スクレイプされた機種データ"""
    台番号: str
    貸玉: str
    機種名: str
    BB回数: Optional[str] = None
    RB回数: Optional[str] = None
    ART回数: Optional[str] = None
    初当り回数: Optional[str] = None
    確変回数: Optional[str] = None
    前日最終スタート: Optional[str] = None
    スタート回数: Optional[str] = None


class PredictionCreate(BaseModel):
    """予測結果作成スキーマ"""
    store_id: int
    date: date
    predicted_diff: float
    confidence: float
    model_version: Optional[str] = "v1"
