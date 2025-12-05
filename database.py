import aiosqlite
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timedelta, timezone

from models import *
from config import settings


# ----- 설정 -----
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "defects.db" # 데이터베이스 파일 경로


# ----- 데이터베이스 초기화 -----
async def init_db():
    """
    앱 시작 시 데이터베이스와 테이블을 생성합니다.
    """

    async with aiosqlite.connect(settings.DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS defects (
            id TEXT PRIMARY KEY,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            image TEXT NOT NULL,
            detect_time TEXT NOT NULL,
            defect_type TEXT,
            urgency TEXT,
            address TEXT
        )
        """)
        await db.commit()


# ----- 헬퍼: DB 응답을 DefectOut 모델로 변환 -----
def db_row_to_model(row: aiosqlite.Row) -> DefectOut:
    """
    SQLite Row 객체를 Pydantic 모델로 변환합니다.
    """

    if row:
        return DefectOut(**dict(row))
    return None


# ----- DB 안에 defect 객체 생성 -----
async def create_defect_in_db(defect: DefectOut) -> Optional[DefectOut]:
    sql = """
          INSERT INTO defects (id, latitude, longitude, image, detect_time, address)
          VALUES (?, ?, ?, ?, ?, ?)
          """
    try:
        async with aiosqlite.connect(settings.DB_PATH) as db:
            await db.execute(sql, (
                defect.id, defect.latitude, defect.longitude,
                defect.image, defect.detect_time, defect.address
            ))
            await db.commit()
        return defect
    except aiosqlite.Error as e:
        return None
    

# ----- 해당 객체에 대한 llava 답변 update -----
async def patch_defect_in_db(defect_id: str, patch_data) -> Optional[DefectOut]:
    updated_defect = None

    try:
        async with aiosqlite.connect(settings.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            # 1. 수정할 현재 데이터를 먼저 조회
            async with db.execute("SELECT * FROM defects WHERE id = ?", (defect_id,)) as cursor:
                current_row = await cursor.fetchone()
            
            if not current_row:
                print(f"Defect ID '{defect_id}'를 찾을 수 없습니다.")
                return None
            
            # 2. Pydantic 모델로 데이터 병합
            current_defect = db_row_to_model(current_row)
            patch_dict = patch_data.model_dump(exclude_unset=True)
            updated_defect = current_defect.model_copy(update=patch_dict)

            # 3. 변경된 내용으로 DB UPDATE
            sql = """
                  UPDATE defects
                  SET defect_type = ?, urgency = ?, address = ?
                  WHERE id = ?
                  """
            await db.execute(sql, (
                updated_defect.defect_type,
                updated_defect.urgency,
                updated_defect.address,
                updated_defect.id
            ))
            await db.commit()

    except aiosqlite.Error as e:
        return None
    
    return updated_defect


# ----- defect 기록 조회 -----
async def get_all_defects_from_db(sort_by_urgency: bool = False) -> List[DefectOut]:
    """
    모든 결함 기록을 DB에서 조회합니다.
    sort_by_urgency=True 시, 'get_records'의 요구사항에 맞게 정렬합니다.
    """
    
    # 1. 기본 쿼리
    sql = "SELECT * FROM defects"

    # 2. 정렬 로직
    #    "높음"(3) -> "중간"(2) -> "낮음"(1) 순서로 정렬
    if sort_by_urgency:
        sql += """
               ORDER BY
                   CASE 
                       WHEN urgency = '높음' THEN 3
                       WHEN urgency = '보통' THEN 2
                       WHEN urgency = '낮음' THEN 1
                       ELSE 0 
                   END DESC,
                   detect_time ASC 
               """
    else:
        sql += " ORDER BY detect_time DESC"

    try:
        async with aiosqlite.connect(settings.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql) as cursor:
                rows = await cursor.fetchall()
                return [db_row_to_model(row) for row in rows]
    except aiosqlite.Error as e:
        print(f"❌ DB 조회 실패: {e}")
        return []


# ----- 오래된 defect 삭제 -----
async def delete_old_defects(days: int = 30):
    """
    현재 시각 기준으로 'detect_time' 이 30일 이상 지난 손상 기록을 삭제합니다.
    """

    threshold = datetime.now(timezone.utc) - timedelta(days=days)
    threshold_iso = threshold.isoformat().replace("+00:00", "Z")

    sql = """
          DELETE FROM defects
           WHERE detect_time < ?
          """

    try:
        async with aiosqlite.connect(settings.DB_PATH) as db:
            await db.execute(sql, (threshold_iso,))
            await db.commit()
        print(f"🗑️ {days}일 이상 지난 손상 기록을 삭제했습니다.")
    except aiosqlite.Error as e:
        print(f"❌ 오래된 데이터 삭제 실패: {e}")