from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Literal, Optional, List
from datetime import datetime, timezone
from pathlib import Path
import json, os, uuid, io, sys


# ----- 설정 -----
DATA_DIR = Path("data") # data라는 폴더가 DATA_DIR
DATA_DIR.mkdir(exist_ok=True) # 폴더 없으면 생성
JSONL_PATH = DATA_DIR / "defects.ndjson" # 폴더 안에 defects.ndjson 파일 생성

DefectType = Literal["Concrete Crack","Concrete Spalling","Paint Damage","Rebar Exposure"]
Urgency = Literal["High","Medium","Low"]


# 생성용(드론 → 서버) : 최소 필수만
class DefectCreate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    image: str
    # 선택: detect_time (없으면 서버가 채움)
    detect_time: Optional[str] = None

# 부분 갱신용(LLaVA → 서버) : 모두 optional
class DefectPatch(BaseModel):
    defect_type: Optional[DefectType] = None
    urgency: Optional[Urgency] = None
    address: Optional[str] = None


# 조회/응답용(최종 병합 상태)
class DefectOut(BaseModel):
    id: str
    latitude: float
    longitude: float
    image: str
    detect_time: str
    # 아래 3개는 처음엔 없을 수 있으니 Optional
    defect_type: Optional[DefectType] = None
    urgency: Optional[Urgency] = None
    address: Optional[str] = None