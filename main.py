from PIL import Image
import uvicorn
from fastapi import FastAPI, HTTPException, Body, File, UploadFile, Form
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timezone, timedelta
from pathlib import Path
import uuid
import aiosqlite
from contextlib import asynccontextmanager
import shutil

from config import settings
from models import DefectCreate, DefectOut, DefectPatch
from database import init_db, create_defect_in_db, db_row_to_model
from llava import load_llava_model, run_llava
from airobot import *
import asyncio
from map import *
from s3_utils import upload_to_s3

from dotenv import load_dotenv


load_dotenv()


# ----- 자동화 로직 -----
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("----- 데이터베이스 초기화 중 -----")
    await init_db()
    await delete_old_defects(days=30)
    print(f"✅ 데이터베이스 준비 완료: {settings.DB_PATH.resolve()}")

    # LLaVA 모델 로드
    await asyncio.to_thread(load_llava_model)
    
    # Discord 봇 백그라운드 실행
    asyncio.create_task(client.start(discord_key))

    yield

    print("----- 애플리케이션 종료 -----")
    await client.close()


# ----- FastAPI 앱 -----
app = FastAPI(
    title="Airovision — 건물 외벽 손상 관리 API",
    description=(
        "**드론 촬영 이미지 및 메타데이터를 기반으로 건물 외벽 손상을 분석하는 AI 시스템**\n\n"
        "드론 → 라즈베리파이 + Hailo 엣지 장치 → FastAPI 서버 → LLaVA 분석 → Discord 알림\n\n"
        "---\n\n"
        "📡 드론 + 라즈베리파이 + Hailo 엣지 장치 기반 실시간 손상 탐지\n\n"
        "🧠 FastAPI 서버에서 LLaVA 모델 기반 손상 이미지 분석\n\n"
        "📋 SQLite 기반 손상 기록 저장 및 조회\n\n"
        "🔔 Discord 챗봇 연동 손상 알림 및 상호작용"
    ),
    version="1.0.0",
    lifespan=lifespan
)


# ----- 정적 파일 마운트 (개발용) -----
app.mount(
    settings.STATIC_MOUNT_PATH,
    StaticFiles(directory=settings.DATA_DIR.name),
    name="data"
)


# ----- API 엔드포인트 -----
# [드론용] 새로운 손상 정보 생성 API
@app.post(
    "/defect-info",
    response_model=DefectOut,
    status_code=201, # 201 Created
    summary="[드론용] 새로운 손상 정보 생성",
    description="드론에서 촬영한 이미지와 시간 정보를 받아 새 손상 데이터를 생성합니다."
)

async def create_defect_info(defect: DefectCreate = Body(...)):
    new_id = str(uuid.uuid4())
    
    # 시간 설정
    if defect.detect_time:
        detect_time = defect.detect_time
    else:
        KST = timezone(timedelta(hours=9))
        detect_time = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

    # 주소 설정
    address = get_address_from_coords(defect.latitude, defect.longitude)

    new_defect_data = DefectOut(
        id=new_id,
        latitude=defect.latitude,
        longitude=defect.longitude,
        image=defect.image,
        detect_time=detect_time,
        address=address
    )

    saved_defect = await create_defect_in_db(new_defect_data)
    if not saved_defect:
        raise HTTPException(status_code=500, detail="❌ DB 생성 실패")
    
    final_defect = await run_analysis_and_notify(saved_defect)
    if final_defect is None:
        raise HTTPException(status_code=500, detail="❌ DB 업데이트 실패")
    
    return final_defect

#----- 백그라운드 작업 함수 -----
async def run_analysis_and_notify(defect: DefectOut):
    """
    POST 요청과는 별개로 실행되는 백그라운드 작업입니다.
    """

    try:
        defect_type,  urgency = await asyncio.to_thread(run_llava, defect.image, None, None, None, None)
        
        patch_data = DefectPatch(defect_type=defect_type, urgency=urgency)
        updated_defect = await patch_defect_in_db(defect.id, patch_data)

        if  updated_defect is None:
            raise HTTPException(status_code=404, detail=f"Defect ID '{defect.id}'를 찾을 수 없습니다.")
        
        print(f"✅ DB 업데이트 완료 (ID: {defect.id})")

        # Discord 알림 전송
        llava_summary = "🚨 손상 감지 🚨\n" \
            "새로운 외벽 손상이 탐지되었습니다. 아래의 정보를 확인하세요.\n" \
            f"📍 위치: {defect.address}\n" \
            f"🕒 감지 시각: {defect.detect_time}\n" \
            f"🏷️ 손상 유형: {defect_type}\n" \
            f"⚠️ 위험도(점검 긴급성): {urgency}"
        await send_defect_alert(updated_defect, llava_summary)

        return updated_defect
        
    except Exception as e:
        print(f"❌ 백그라운드 작업 실패 (ID: {defect.id}): {e} : {type(e)}")
        import traceback
        traceback.print_exc()

# [개발용] 로컬 이미지 업로드 API
@app.post(
    "/upload-img-dev",
    summary="[개발용] 로컬 이미지 업로드",
    description="로컬 개발 시 파일 업로드를 위한 헬퍼 API입니다. 배포 시 S3로 대체될 예정입니다."
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

    image_url_path = f"{settings.STATIC_MOUNT_PATH}/{settings.UPLOADS_DIR_NAME}/{file_name}"
    
    return {"url": image_url_path}

# [배포용] S3 이미지 업로드 API
@app.post(
    "/upload-img",
    summary="[배포용] S3 이미지 업로드",
    description="업로드된 이미지를 S3에 저장하고, 접근 가능한 URL을 반환합니다."
)

async def upload_image_s3(file: UploadFile = File(...)):
    """
    이미지를 S3 버킷에 업로드하고 S3 public URL을 반환합니다.
    """

    try:
        s3_url = await upload_to_s3(file)
        return {"url": s3_url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3 업로드 실패: {e}")


# ----- 서버 실행 -----
if __name__ == "__main__":
    print("----- 서버 시작 중 -----")
    print(f"✅ DB 위치: {settings.DB_PATH.resolve()}")
    print(f"✅ 업로드 폴더: {settings.UPLOADS_DIR.resolve()}")
    print(f"✅ 정적 파일 URL: http://34.218.88.107:8000{settings.STATIC_MOUNT_PATH}/")
    uvicorn.run(app, host="0.0.0.0", port=8000)