from PIL import Image
import uvicorn
from fastapi import FastAPI, HTTPException, Body, File, UploadFile, Form
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timezone
from pathlib import Path
import uuid
import aiosqlite  # 비동기 SQLite 라이브러리
from contextlib import asynccontextmanager
import shutil

# ⭐️ 분리된 파일들에서 import
from config import settings
from models import DefectCreate, DefectOut, DefectPatch
from database import init_db, create_defect_in_db, db_row_to_model
from llava import load_llava_model, run_llava
from airobot import *
import asyncio
from map import *

from dotenv import load_dotenv # ⭐️ .env 로드

# ⭐️ .env 로드 (가장 먼저 실행)
load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("데이터베이스 초기화를 시작합니다...")
    await init_db()
    print(f"데이터베이스 준비 완료: {settings.DB_PATH.resolve()}")
    # 2. ⭐️ LLaVA 모델 로드 (무거우므로 스레드에서)
    await asyncio.to_thread(load_llava_model)
    
    # 3. ⭐️ Discord 봇 백그라운드 실행
    #    client.run() (X) -> client.start() (O)
    asyncio.create_task(client.start(discord_key))

    yield

    print("애플리케이션을 종료합니다.")


# ----- FastAPI 앱 -----
app = FastAPI(
    title="결함 관리 API (Drone/LLaVA)",
    description="드론에서 결함 정보를 받고 LLaVA가 분석한 데이터를 갱신합니다.",
    version="1.0.0",
    lifespan=lifespan # 앱 시작/종료 시 lifespan 함수 실행
)


# ----- 3. 정적 파일 마운트 (로컬 개발용) -----
# 이렇게 하면 "data/images/image.jpg" 파일을
# "http://서버주소/data/images/image.jpg" URL로 접근 가능
# "data" 디렉토리를 "/data" URL 경로에 연결
app.mount(
    settings.STATIC_MOUNT_PATH,
    StaticFiles(directory=settings.DATA_DIR.name), # "data"
    name="data"
)


# ----- API 엔드포인트 -----
@app.post(
    "/defect-info",
    response_model=DefectOut,
    status_code=201, # 201 Created
    summary="새로운 결함 정보 생성 (드론용)",
    description="드론에서 촬영한 이미지와 위치 정보를 받아 새 결함 데이터를 생성합니다."
)
async def create_defect_info(defect: DefectCreate = Body(...)):
    """
    (배포용/개발용 공통)
    1. 드론에서 JSON (좌표 + 이미지 URL)을 받습니다.
    2. DB에 '미완성' 상태로 즉시 저장하고 드론에게 응답합니다.
    3. [백그라운드] LLaVA 분석을 실행합니다.
    4. [백그라운드] LLaVA 결과를 DB에 PATCH(갱신)합니다.
    5. [백그라운드] Discord로 알림을 보냅니다.
    """
    
    # 1. 고유 ID 생성
    new_id = str(uuid.uuid4())
    
    # 2. 감지 시간 설정 (클라이언트가 안 보냈으면 서버가 UTC로 생성)
    if defect.detect_time:
        detect_time = defect.detect_time
    else:
        # ISO 8601 형식 + UTC (Z)
        detect_time = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    address = get_address_from_coords(defect.latitude, defect.longitude)
    # address = get_address_from_coords(37.3595963, 127.1054328)  # 위도, 경도

    # 3. 최종 저장될 DefectOut 모델 객체 생성
    new_defect_data = DefectOut(
        id=new_id,
        latitude=defect.latitude,
        longitude=defect.longitude,
        image=defect.image, # 클라이언트가 제공한 이미지 url
        detect_time=detect_time,
        address=address
    )
    print(f"도로명: {address}\n")

    # 4. db에 해당 객체 데이터 연결(삽입)
    saved_defect = await create_defect_in_db(new_defect_data)
    if not saved_defect:
        raise HTTPException(status_code=500, detail="DB 저장 실패")
    
    # 2. ⭐️ [핵심] LLaVA 분석 + DB 갱신 + Discord 알림을
    #    '백그라운드 작업'으로 분리 (드론이 기다리지 않게 함)
    # asyncio.create_task(
    #     run_analysis_and_notify(saved_defect)
    # )
    final_defect = await run_analysis_and_notify(saved_defect)
    if final_defect is None:
        raise HTTPException(status_code=500, detail="데이터베이스 저장에 실패했습니다.")
    return final_defect

#----- 4. 백그라운드 작업 함수 -----
async def run_analysis_and_notify(defect: DefectOut):
    """
    POST 요청과는 별개로 실행되는 백그라운드 작업
    """
    try:
        defect_type,  urgency = await asyncio.to_thread(run_llava, defect.image, None)
        
        
        # 3. DB 갱신 (PATCH)
        #    (database.py에 patch_defect_in_db 함수가 필요합니다)
        patch_data = DefectPatch(defect_type=defect_type, urgency=urgency)
        updated_defect = await patch_defect_in_db(defect.id, patch_data)

        if  updated_defect is None:
            raise HTTPException(status_code=404, detail=f"Defect ID '{defect.id}'를 찾을 수 없습니다.")
        
        print(f"✅ DB 갱신 완료 (ID: {defect.id})")

        # 4. ⭐️ Discord 알림 전송 (discord_bot.py의 함수 호출)
        llava_summary = "🚨 손상 감지 🚨\n" \
            "새로운 외벽 손상이 탐지되었습니다. 아래의 정보를 확인하세요.\n" \
            f"📍 위치: {defect.address}\n" \
            f"🕒 감지 시각: {defect.detect_time}\n" \
            f"🏷️ 손상 유형: {defect_type}\n" \
            f"⚠️ 위험도(점검 긴급성): {urgency}"
        await send_defect_alert(defect, llava_summary)

        return updated_defect
        
    except Exception as e:
        print(f"❌ 백그라운드 작업 실패 (ID: {defect.id}): {e} : {type(e)}")
        # ⭐️ [중요] 'import'와 'traceback' 두 줄을 추가합니다.
        import traceback
        traceback.print_exc() # ⭐️ 전체 오류 로그 출력
        # (오류 발생 시 Discord로 오류 알림을 보낼 수도 있음)


@app.post(
    "/upload-image-dev",
    summary="[개발용] 로컬 이미지 업로드",
    description="로컬 개발 시 파일 업로드를 위한 헬퍼 API. 배포 시 S3로 대체될 예정."
)
async def upload_image_dev(file: UploadFile = File(...)):
    """
    (개발용)
    이미지 파일을 받아 서버 로컬(/data/images)에 저장하고
    접근 가능한 URL을 반환합니다.
    """
    try:
        file_extension = Path(file.filename).suffix
        file_name = f"{uuid.uuid4()}{file_extension}"
        file_path = settings.UPLOADS_DIR / file_name

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 저장 실패: {e}")
    finally:
        file.file.close()

    # /data/images/파일명.jpg 형식의 URL 반환
    image_url_path = f"{settings.STATIC_MOUNT_PATH}/{settings.UPLOADS_DIR_NAME}/{file_name}"
    
    return {"url": image_url_path}


# ----- 5. 서버 실행 -----
if __name__ == "__main__":
    print("--- ⭐️ 개발용 서버 모드 ⭐️ ---")
    print(f"DB 위치: {settings.DB_PATH.resolve()}")
    print(f"업로드 폴더: {settings.UPLOADS_DIR.resolve()}")
    print(f"정적 파일 URL: http://127.0.0.1:8000{settings.STATIC_MOUNT_PATH}/")
    uvicorn.run(app, host="127.0.0.1", port=8000)