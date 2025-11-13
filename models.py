from pydantic import BaseModel, Field
from typing import Literal, Optional



DefectType = Literal["콘크리트 균열","콘크리트 박리","도장 손상","철근 노출"]
Urgency = Literal["높음","보통","낮음"]


# 생성용(드론 → 서버) : 최소 필수만
class DefectCreate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    image: str = Field(..., description="이미지가 저장된 최종 URL") # image url
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