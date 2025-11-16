import aiohttp
import requests
import os
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
    
    # 2. 요청 파라미터 설정
    # (**중요: coords는 '경도,위도' 순서)
    params = {
        "coords": f"{longitude},{latitude}",
        "orders": "roadaddr",  # 도로명 주소 요청
        "output": "json",
    }
    
    # 3. 요청 헤더 설정 (인증)
    headers = {
        "x-ncp-apigw-api-key-id": settings.NAVER_CLIENT_ID,
        "x-ncp-apigw-api-key": settings.NAVER_CLIENT_SECRET,
    }
    
    try:
        # 4. API 호출 (GET 요청)
        response = requests.get(api_url, params=params, headers=headers)
        
        # 5. 응답 확인 (HTTP 상태 코드 200 = 성공)
        if response.status_code == 200:
            data = response.json()
            
            # 6. 응답 데이터 파싱
            # API 호출이 성공했는지 JSON 내부의 'status code' 확인
            if data['status']['code'] == 0:
                # 'results' 리스트에서 도로명 주소 정보 추출
                # (orders=roadaddr 하나만 요청했으므로 보통 results[0]에 있음)
                results = data['results'][0]
                
                # 주소의 각 요소를 조합
                region = results['region']  # 지역 (시/도, 시/군/구)
                land = results['land']      # 도로명 정보
                
                # (예: "인천광역시 미추홀구 용현동")
                area1 = region['area1']['name']
                area2 = region['area2']['name']
                
                # (예: "인하로")
                road_name = land['name']
                # (예: "100")
                building_num = land['number1']
                
                # (예: "인하대학교 60주년기념관", 건물 이름은 없을 수도 있음)
                building_name = ""
                if land.get('addition0') and land['addition0']['type'] == 'building':
                    building_name = land['addition0']['value']
                
                # 조합: "인천광역시 미추홀구 인하로 100 (인하대학교 60주년기념관)"
                full_address = f"{area1} {area2} {road_name} {building_num} {building_name}".strip()
                
                return full_address
                
            else:
                print(f"API Error: {data['status']['message']}")
                return None
                
        else:
            print(f"HTTP Error: {response.status_code}")
            print(f"Error Response Body: {response.text}")
            return None
            
    except Exception as e:
        print(f"Request Error: {e}")
        return None


# ----- 네이버 지도 Reverse Geocoding -----
# async def get_address_from_coords(lat: float, lon: float) -> Optional[str]:
#     """
#     네이버 Reverse Geocoding API를 사용해 좌표 -> 도로명주소 변환
#     """
#     url = "https://naveropenapi.apigw.ntruss.com/map-reversegeocode/v2/gc"
#     headers = {
#         "X-NCP-APIGW-API-KEY-ID": settings.NAVER_CLIENT_ID,
#         "X-NCP-APIGW-API-KEY": settings.NAVER_CLIENT_SECRET,
#     }
#     params = {
#         "coords": f"{lon},{lat}",  # (경도, 위도)
#         "orders": "roadaddr,addr",
#         "output": "json",
#     }

#     try:
#         async with aiohttp.ClientSession() as session:
#             async with session.get(url, headers=headers, params=params) as resp:
#                 if resp.status != 200:
#                     print(f"[ReverseGeocode] API 요청 실패: {resp.status}")
#                     return None

#                 data = await resp.json()
#                 results = data.get("results")
#                 if not results:
#                     return None

#                 # 도로명주소 우선, 없으면 지번주소
#                 for result in results:
#                     region = result.get("region", {})
#                     land = result.get("land", {})
#                     area1 = region.get("area1", {}).get("name", "")
#                     area2 = region.get("area2", {}).get("name", "")
#                     area3 = region.get("area3", {}).get("name", "")
#                     area4 = region.get("area4", {}).get("name", "")
#                     name = land.get("name", "")
#                     number1 = land.get("number1", "")
#                     number2 = land.get("number2", "")

#                     address = f"{area1} {area2} {area3} {area4} {name} {number1}"
#                     if number2:
#                         address += f"-{number2}"
#                     return address.strip()

#                 return None
#     except Exception as e:
#         print(f"[ReverseGeocode] 예외 발생: {e}")
#         return None
    

    