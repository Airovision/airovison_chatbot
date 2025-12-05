import requests
from config import settings
from models import *

def get_address_from_coords(latitude, longitude):
    """
    네이버 Reverse Geocoding API를 호출하여 좌표를 도로명 주소로 변환합니다.
    
    Args:
        latitude (float): 위도
        longitude (float): 경도
        
    Returns:
        str: 변환된 도로명 주소. 실패 시 None.
    """
    
    # 1. API 요청 URL
    api_url = "https://maps.apigw.ntruss.com/map-reversegeocode/v2/gc"
    
    # 2. 요청 파라미터 설정(**coords는 '경도,위도' 순서)
    params = {
        "coords": f"{longitude},{latitude}",
        "orders": "roadaddr",
        "output": "json",
    }
    
    # 3. 요청 헤더 설정
    headers = {
        "x-ncp-apigw-api-key-id": settings.NAVER_CLIENT_ID,
        "x-ncp-apigw-api-key": settings.NAVER_CLIENT_SECRET,
    }
    
    try:
        # 4. API 호출
        response = requests.get(api_url, params=params, headers=headers)
        
        # 5. 응답 확인
        if response.status_code == 200:
            data = response.json()
            
            # 6. 응답 데이터 파싱
            if data['status']['code'] == 0:
                results = data['results'][0]
                
                region = results['region']
                land = results['land']
                
                area1 = region['area1']['name']
                area2 = region['area2']['name']
                
                road_name = land['name']
                building_num = land['number1']

                building_name = ""
                if land.get('addition0') and land['addition0']['type'] == 'building':
                    building_name = land['addition0']['value']
                
                full_address = f"{area1} {area2} {road_name} {building_num} {building_name}".strip()
                
                return full_address
                
            else:
                print(f"❌ 네이버 API 오류: {data['status']['message']}")
                return "인천 미추홀구 인하로 100, 인하대학교"
                
        else:
            print(f"❌ HTTP 오류 발생: {response.status_code}")
            print(f"❌ 응답 내용: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ 요청 처리 실패: {e}")
        return None    