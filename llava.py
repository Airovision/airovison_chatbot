# python 코드로 LLaVA 실행하기
import torch, textwrap, re # 라바 답변 줄바꿈
from transformers import AutoProcessor, LlavaForConditionalGeneration, BitsAndBytesConfig
from PIL import Image
from googletrans import Translator # 번역 라이브러리
import os

# LLaVA 모델 로드를 매번 하지 않도록 전역 변수로 선언 (한 번만 로드)
_model = None
_processor = None
_device = None

REF_DIR = "./reference_images" # ICL 기법 프롬프트에 들어갈 예시 사진들

# 손상 유형
defect_type_choice = {
    "Concrete Crack" : "콘크리트 균열",
    "Paing Damage" : "도장 손상",
    "Rebar Exposure" : "철근 노출"
}

# 위험도
urgency_choice = {
    "High" : "높음",
    "Medium" : "보통",
    "Low" : "낮음"
}

def load_llava_model():
    global _model, _processor, _device
    if _model is not None and _processor is not None:
        return _model, _processor, _device

    # 1. 모델과 프로세서 준비
    model_id = "llava-hf/llava-1.5-7b-hf"
    revision = "a272c74"

    # # 4-bit 양자화 설정 (메모리 절약을 위해 필수!)-> cuda 전용
    # quantization_config = BitsAndBytesConfig(
    #     load_in_4bit=True,
    #     bnb_4bit_compute_dtype=torch.float16
    # )

    
    if torch.backends.mps.is_available(): # 맥북 gpu
        _device = "mps"
    elif torch.cuda.is_available(): # 서버 gpu
        _device = "cuda"
    else:
        _device = "cpu"
    
    # 모델 로드
    print("--- LLaVA 모델 불러오는 중... ---")
    _model = LlavaForConditionalGeneration.from_pretrained(
        model_id,
        revision=revision,
        torch_dtype=torch.float16,
        device_map="auto"
    ).to(_device)

    # Processor: fast → 실패 시 slow
    try:
        _processor = AutoProcessor.from_pretrained(model_id, revision=revision)
    except Exception as e:
       print("Processor load failed:", e)
       raise
    
    print("✅ LLaVA 모델 로드 완료")
    
    return _model, _processor, _device

def _as_str(m): # re.Match 객체 str로 변환
    return m.group(1).strip() if isinstance(m, re.Match) else (m.strip() if isinstance(m, str) else "")


# 추가 질문에 대한 라바 답변
def run_llava(image_path: str, question: str):
    """
    디스코드 챗봇에서 호출용:
    image_path: 분석할 이미지 파일 경로
    question: 버튼으로 받은 한국어 질문
    """

    model, processor, device = load_llava_model()

    # 2. 이미지와 프롬프트 입력받기
    # ./images/sample.jpg
    
    image_path = image_path if question else "."+image_path
    image = Image.open(image_path)

    # LLaVA 추가 질문 목록
    llava_questions = {
        "이미지에 나타난 손상에 대해 분석 요약해주세요": textwrap.dedent("""You are an AI assistant analyzing a potential building defect from a drone image for a preliminary assessment.
                                                Your analysis is NOT a substitute for a professional engineering inspection.
                                                Provide a concise yet informative summary of the defect’s visible characteristics and overall condition.
                                                Describe the shape, size, and color or texture differences compared to the surrounding area.
                                                Then, include a short analytical summary describing how severe or extensive the defect appears visually, as if giving a quick inspection report."""),
        "이 손상의 위험도를 1~10 단계로 평가해주세요": textwrap.dedent("""You are an AI assistant analyzing a potential building defect from a drone image for a preliminary assessment.
                                                Your analysis is NOT a substitute for a professional engineering inspection.
                                                Evaluate the damage risk level on a scale of 1 to 10. Answer in the following format: \"It is XX points. {Write the reason in less than three sentences.}\"""")
    }

    user_text =  llava_questions.get(question) if question else (prompt_start).strip()
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

    korean_result = translator.translate(english_result, src='en', dest='ko').text
    formatted_korean = re.sub(r'(?<=[가-힣\w][다요함임]\.)+', '\n', korean_result).strip()
    # '다.', '요.' 등으로 끝나고 공백이 이어질 때
    return formatted_korean
    
# icl_llava(처음 사진 분석 시 사용)
def run_icl_llava(target_image_path, examples, question, options, mode):
    """
    In-Context Learning을 수행하는 함수
    :param target_image_path: 분석할 대상 이미지 경로
    :param examples: [(이미지경로, 정답라벨), ...] 형태의 튜플 리스트
    :param question: 모델에게 던질 질문
    :param options: 모델이 선택해야 할 답변 목록 (예: ['Low', 'Medium', 'High'])
    :return: 모델의 텍스트 답변
    """
    model, processor, device = load_llava_model()

    # 이미지 리스트 (ference images + target image)
    image_list=[]

    # 프롬프트 텍스트 구성 (chat template 형식)
    # LLaVA는 <image> 토큰 순서대로 이미지를 매핑함
    prompt_text = "You are an AI assistant analyzing a potential building defect from a drone image for a preliminary assessment.Your analysis is NOT a substitute for a professional engineering inspection.Analyze the image carefully and provide the following information in a structured format."

    if mode: prompt_text += "Your task is to classify the final target image based on visual similarity to the provided examples.\n"
    
    for path, label in examples:
        if not os.path.exists(path):
            print(f"경고: 참조 이미지를 찾을 수 없습니다.: {path}")
            continue

        img = Image.open(path).convert("RGB")
        image_list.append(img)
        prompt_text += f"Example: <image>\nAnswer: {label}\n"

    target_img = Image.open(target_image_path).convert("RGB")
    image_list.append(target_img)
    prompt_text += f"Target: <image>\nQuestion: {question}\nChoose one from: {options}\nAnswer:"

    messages = [
        {"role":"user",
         "content":[
            {"type": "text", "text": prompt_text}
        ]}
    ]

    # apply_chat_template은 텍스트 포맷팅을 도와줍니다.
    # 하지만 LLaVA 1.5 HF 구현체는 텍스트 내 <image> 개수와 image_list 길이가 같아야 함.
    text_prompt = processor.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)

    inputs = processor(text=text_prompt, images=image_list, return_tensors="pt").to(device)

    with torch.inference_mode():
        generate_ids = model.generate(**inputs, max_new_tokens=20) # 답변은 짧게
    
    output = processor.batch_decode(generate_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]

    # 답변 추출 ("ASSISTANT:" 이후)
    answer = output.split("ASSISTANT:")[-1].strip()
    print(f"answer: {answer}\n")
    return answer

# 손상 이미지에 대한 첫 손상 알림
def analyze_defect_basic(target_image_filename):
    """
    step 1: 유형분류 -> step 2: 그에 맞는 위험도 판단
    """

    target_path = "."+target_image_filename

    if not os.path.exists(target_path):
        return "이미지 없음", "이미지 없음"
    
    print(f"\n🚀 [분석 시작] {target_image_filename}")

    # ------step 1 : 손상 유형 분류------
    print(">>> step 1. 손상 유형 분류 중...")

    # 유형별 참조할 대표 이미지
    type_examples = [
        (os.path.join(REF_DIR, "균열_대표.jpg"), "Concrete Crack"),
        (os.path.join(REF_DIR, "도장손상_대표.jpg"), "Paint Damage"),
        (os.path.join(REF_DIR, "철근노출_대표.jpg"), "Rebar Exposure")
    ]

    type_result = run_icl_llava(
        target_path,
        type_examples,
        "Select the type that is VISUALLY MOST SIMILAR to the examples.",
        "['Concrete Crack', 'Paint Damage', 'Rebar Exposure', 'None']",
        1
    )

    defect_type = "None"
    if "Crack" in type_result: defect_type = "Concrete Crack"
    elif "Paint" in type_result: defect_type = "Paint Damage"
    elif "Rebar" in type_result: defect_type = "Rebar Exposure"

    print(f"  1차 판정 결과: {defect_type} (Raw: {type_result})")

    # ------step 2. 위험도 판단------
    """
    규칙
    1. 도장손상 -> 하 (w/o llava)
    2. 철근노출 -> 상 (w/o llava)
    3. 박리 -> 중/상 (w/ llava)
    4. 균열 -> 하/중/상 (w/ llava)
    """
    print(">>> step 2: 위험도 측정 중...")

    urgency = "Unknown"
    if defect_type=="None": urgency="None"
    elif defect_type=="Paint Damage": urgency="Low"
    elif defect_type=="Rebar Exposure": urgency="High"
    elif defect_type=="Concrete Crack":
        creck_examples = [
            (os.path.join(REF_DIR, "균열_상.jpg"), "High"),
            (os.path.join(REF_DIR, "균열_하.jpg"), "Low"),
            (os.path.join(REF_DIR, "균열_중.jpg"), "Medium")
        ]

        urgency_result = run_icl_llava(
            target_path,
            creck_examples,
            "Based on the thickness and darkness of the crack compared to examples, what is the urgency?",
            "['Low', 'Medium', 'High']",
            0
        )
        if "High" in urgency_result: urgency = "High"
        elif "Medium" in urgency_result: urgency = "Medium"
        else: urgency = "Low" # 기본값
        print(f"***AI 균열 위험도 판정: {urgency} (Raw: {urgency_result})")

    defect_type_kr = defect_type_choice.get(defect_type, "분류 안됨")

    urgency_kr = urgency_choice.get(urgency, "분류 안됨")

    print("---- LLaVA 답변(eng) ----")
    print(f"Defect type: {defect_type}, Urgency: {urgency}")
    print("---- LLaVA 답변(kor) ----")
    print(f"손상 유형: {defect_type_kr}, 위험도: {urgency_kr}")

    return defect_type_kr, urgency_kr
