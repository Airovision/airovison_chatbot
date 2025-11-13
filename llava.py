# python 코드로 LLaVA 실행하기
import torch, textwrap, re # 라바 답변 줄바꿈
from transformers import AutoProcessor, LlavaForConditionalGeneration, BitsAndBytesConfig
from PIL import Image
from googletrans import Translator # 번역 라이브러리

# LLaVA 모델 로드를 매번 하지 않도록 전역 변수로 선언 (한 번만 로드)
_model = None
_processor = None

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

def _as_str(m): # re.Match 객체 str로 변환
    return m.group(1).strip() if isinstance(m, re.Match) else (m.strip() if isinstance(m, str) else "")


def run_llava(image_path: str, question: str | None):
    """
    디스코드 챗봇에서 호출용:
    image_path: 분석할 이미지 파일 경로
    question: 버튼으로 받은 한국어 질문
    """

    model, processor = load_llava_model()

    # 2. 이미지와 프롬프트 입력받기
    # ./images/sample.jpg
    image_path = "."+image_path
    image = Image.open(image_path)

    # 첫 시작 LLaVA 질문 ver.4
    prompt_start =  textwrap.dedent("""You are an AI assistant analyzing a potential building defect from a drone image for a preliminary assessment.
    Your analysis is NOT a substitute for a professional engineering inspection.
    Analyze the image and provide the following information in a structured format:
    1. Defect Type: Identify the specific type of defect (Only classify the defect type into one of the following four categories: 
    [Concrete Crack, Concrete Spalling, Paint Damage, Rebar Exposure] Do not use any other categories).
    2. Urgency for Inspection: Classify the urgency for a professional inspection as [Low, Medium, High]. (Only say "Low", "Medium" or "High")
    """)

    # 손상 유형
    defect_type_choice = {
        "Concrete Crack" : "콘크리트 균열",
        "Concrete Spalling" : "콘크리트 박리",
        "Paing Damage" : "도장 손상",
        "Rebar Exposure" : "철근 노출"
    }

    # 위험도
    urgency_choice = {
        "High" : "높음",
        "Medium" : "보통",
        "Low" : "낮음"
    }

    # LLaVA 추가 질문 목록
    llava_questions = {
        "이미지에 나타난 손상에 대해 분석 요약해주세요": textwrap.dedent("""You are an AI assistant analyzing a potential building defect from a drone image for a preliminary assessment.
                                                Your analysis is NOT a substitute for a professional engineering inspection.
                                                Provide a concise yet informative summary of the defect’s visible characteristics and overall condition.
                                                Describe the shape, size, and color or texture differences compared to the surrounding area.
                                                Then, include a short analytical summary describing how severe or extensive the defect appears visually, as if giving a quick inspection report."""),
        "건물의 손상 정도를 측정해주세요": textwrap.dedent("""You are an AI assistant analyzing a potential building defect from a drone image for a preliminary assessment.
                                                Your analysis is NOT a substitute for a professional engineering inspection.
                                                Can you measure how much dameged the buiilding in?"""),
        "이 손상의 위험도를 1~10 단계로 평가해주세요": textwrap.dedent("""You are an AI assistant analyzing a potential building defect from a drone image for a preliminary assessment.
                                                Your analysis is NOT a substitute for a professional engineering inspection.
                                                Evaluate the damage risk level on a scale of 1 to 10. Answer in the following format: \"It is XX points. {Write the reason in less than three sentences.}\"""")
    }

    user_text =  llava_questions.get(question, question) if question else (prompt_start).strip()
    messages = [{
        "role": "user",
        "content": [
            {"type": "image"},
            {"type": "text", "text": user_text},
        ],
    }]

    # 모델용 템플릿 문자열 생성
    prompt_for_model = processor.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=False
    )

    # 3. 모델 추론 실행
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    processor.patch_size = model.config.vision_config.patch_size
    processor.vision_feature_select_strategy = model.config.vision_feature_select_strategy
    inputs = processor(images=image, text=prompt_for_model, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}
    model.to(device)

    generate_ids = model.generate(**inputs, max_new_tokens=1000) # max_new_tokens로 답변 길이 조절
    english_result_full = processor.batch_decode(generate_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]

    # 4. 결과 출력
    # 프롬프트를 제외한 순수 답변 부분만 추출
    english_result = english_result_full.split("ASSISTANT:")[-1].strip()

    translator = Translator()


    if question:
        korean_result = translator.translate(english_result, src='en', dest='ko').text
        formatted_korean = re.sub(r'(?<=[가-힣\w][다요함임]\.)+', '\n', korean_result).strip()
        # '다.', '요.' 등으로 끝나고 공백이 이어질 때
        return formatted_korean
    else:
        #각 항목 추출
        m_type = re.search(r"1\.\s*Defect Type:\s*(.+)", english_result)
        m_urg = re.search(r"2\.\s*Urgency for Inspection:\s*(.+)", english_result)

        defect_type = _as_str(m_type)
        urgency = _as_str(m_urg)

        defect_type_kr = defect_type_choice.get(defect_type, "분류 안됨")
        urgency_kr = urgency_choice.get(urgency, "분류 안됨")

    
        return defect_type_kr, urgency_kr

    
    # print("----LLaVA 질문 프롬프트----")
    # print(user_text)
    # print("----LLaVA 답변(eng.ver)----")
    # print(english_result)

    # print("----LLaVA 답변(kor.ver)----")
    # print(formatted_korean)