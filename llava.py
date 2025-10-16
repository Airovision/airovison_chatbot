# python 코드로 LLaVA 실행하기
import torch
from transformers import AutoProcessor, LlavaForConditionalGeneration, BitsAndBytesConfig
import requests
from PIL import Image
from googletrans import Translator # 번역 라이브러리

# LLaVA 모델 로드를 매번 하지 않도록 전역 변수로 선언 (한 번만 로드)
_model = None
_processor = None
_translator = Translator()

def load_llava_model():
    global _model, _processor
    if _model is not None and _processor is not None:
        return _model, _processor

    # 1. 모델과 프로세서 준비
    model_id = "llava-hf/llava-1.5-7b-hf"

    # # 4-bit 양자화 설정 (메모리 절약을 위해 필수!)-> cuda 전용
    # quantization_config = BitsAndBytesConfig(
    #     load_in_4bit=True,
    #     bnb_4bit_compute_dtype=torch.float16
    # )

    # 맥북 gpu용
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    # 모델 로드
    print("--- LLaVA 모델 불러오는 중... ---")
    _model = LlavaForConditionalGeneration.from_pretrained(
        model_id,
        torch_dtype=torch.float16,
    ).to(device)

    # Processor: fast → 실패 시 slow
    try:
        _processor = AutoProcessor.from_pretrained(model_id, use_fast=True)
    except Exception:
        _processor = AutoProcessor.from_pretrained(model_id, use_fast=False)
    
    print("✅ LLaVA 모델 로드 완료")
    
    return _model, _processor




def run_llava(image_path: str, question: str):
    """
    디스코드 챗봇에서 호출용:
    image_path: 분석할 이미지 파일 경로
    question: 버튼으로 받은 한국어 질문
    """

    model, processor = load_llava_model()

    # 2. 이미지와 프롬프트 입력받기
    # ./images/sample.jpg
    image = Image.open(image_path)

    # 질문 목록 정리
    # questions = {
    #     "1": "이미지에 나타난 손상의 종류는 무엇인가요?",
    #     "2": "건물의 손상 정도를 측정할 수 있나요?",
    #     "3": "이 손상은 얼마나 위험한가요? (1~10 단계로 평가)"
    # }

    llava_questions = {
        "이미지에 나타난 손상의 종류는 무엇인가요?": "what kind of building damage in the image?",
        "건물의 손상 정도를 측정할 수 있나요?": "Can you measure how much dameged the buiilding in?",
        "이 손상은 얼마나 위험한가요? (1~10 단계로 평가)": "Is it danger? if so, how much? Tell me on a scale of 1 (safe) to 10 (Can collapse at any time), tell me simply with the reason"

    }


    # llava 입력 포맷
    prompt_en = llava_questions.get(question, question)
    prompt = f"USER: <image>\n{prompt_en} ASSISTANT:"


    # 3. 모델 추론 실행
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    inputs = processor(text=prompt, images=image, return_tensors="pt").to(device)

    generate_ids = model.generate(**inputs, max_new_tokens=100) # max_new_tokens로 답변 길이 조절
    english_result_full = processor.batch_decode(generate_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]

    # 4. 결과 출력
    # 프롬프트를 제외한 순수 답변 부분만 추출
    english_result = english_result_full.split("ASSISTANT:")[-1].strip()
    translator = Translator()

    # 한국어로 번역
    korean_result = translator.translate(english_result, src='en', dest='ko').text
    # result = processor.batch_decode(generate_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
    print("----LLaVA 질문 프롬프트----")
    print(prompt_en)
    print("----LLaVA 답변(eng.ver)----")
    print(english_result)

    print("----LLaVA 답변(kor.ver)----")
    print(korean_result)

    return korean_result