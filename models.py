from pydantic import BaseModel, Field
from typing import Literal, Optional


DefectType = Literal["콘크리트 균열","콘크리트 박리","도장 손상","철근 노출"]
Urgency = Literal["높음","보통","낮음"]
Repair_status = Literal["미처리", "진행 중", "완료"]


# ----- 생성용(드론 → 서버) -----
class DefectCreate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    image: str = Field(..., description="이미지가 저장된 최종 URL")
    
    detect_time: Optional[str] = None
    address: Optional[str] = None


# ----- 부분 갱신용(LLaVA → 서버) -----
class DefectPatch(BaseModel):
    defect_type: Optional[DefectType] = None
    urgency: Optional[Urgency] = None


# ----- 조회/응답용 -----
class DefectOut(BaseModel):
    id: str
    latitude: float
    longitude: float
    image: str
    detect_time: str
    
    defect_type: Optional[DefectType] = None
    urgency: Optional[Urgency] = None
    address: Optional[str] = None
    repair_status: Optional[Repair_status] = None