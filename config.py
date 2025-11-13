from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    # .env 파일을 읽어옴
    model_config = SettingsConfigDict(env_file=".env", extra='ignore')

    # DB 설정
    DATA_DIR: Path = Path("data")
    DB_NAME: str = "defects.db"
    
    # 로컬 스토리지 설정 (개발용)
    UPLOADS_DIR_NAME: str = "images"
    STATIC_MOUNT_PATH: str = "/data"
    
    @property
    def DB_PATH(self) -> Path:
        return self.DATA_DIR / self.DB_NAME

    @property
    def UPLOADS_DIR(self) -> Path:
        return self.DATA_DIR / self.UPLOADS_DIR_NAME

# 앱 전체에서 공유할 설정 객체
settings = Settings()

# ---------------------------------------------
# ⭐️ 앱 시작 시 폴더 생성 보장
settings.DATA_DIR.mkdir(exist_ok=True)
settings.UPLOADS_DIR.mkdir(exist_ok=True)