import uuid
import boto3
from fastapi import UploadFile
from config import settings
from botocore.exceptions import ClientError

# S3 클라이언트 (IAM Role 기반 자동 인증)
s3_client = boto3.client(
    "s3",
    region_name=settings.AWS_REGION
)

async def upload_to_s3(file: UploadFile) -> str:
    """
    업로드된 파일을 S3 버킷에 저장하고 접근 가능한 URL을 반환합니다.
    IAM Role 기반 인증을 사용하므로 Access Key가 필요 없습니다.
    """

    try:
        # 파일 확장자 추출
        file_extension = file.filename.split(".")[-1]
        
        # S3에 저장될 파일명 생성
        new_filename = f"{uuid.uuid4()}.{file_extension}"

        # S3 Key
        s3_key = f"upload/{new_filename}"

        # 파일 내용을 스트림으로 읽기
        file_bytes = await file.read()

        # S3 업로드
        s3_client.put_object(
            Bucket=settings.AWS_S3_BUCKET,
            Key=s3_key,
            Body=file_bytes,
            ContentType=file.content_type
        )

        # Public URL 생성
        public_url = f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"

        return public_url

    except ClientError as e:
        print(f"❌ S3 업로드 실패: {e}")
        raise RuntimeError(f"S3 업로드 실패: {e}")

    finally:
        await file.close()