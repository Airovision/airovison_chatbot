# python 코드로 LLaVA 실행하기
import torch, textwrap, re # 라바 답변 줄바꿈
from transformers import AutoProcessor, LlavaForConditionalGeneration, BitsAndBytesConfig
from PIL import Image
from deep_translator import GoogleTranslator # 번역 라이브러리
from io import BytesIO
import requests

# LLaVA 모델 로드를 매번 하지 않도록 전역 변수로 선언 (한 번만 로드)
_model = None
_processor = None
_device = None

REF_DIR = "./reference_images" # ICL 기법 프롬프트에 들어갈 예시 사진들

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

def load_llava_model():
    global _model, _processor, _device
    if _model is not None and _processor is not None:
        return _model, _processor, _device

    # 모델과 프로세서 준비
    model_id = "llava-hf/llava-1.5-7b-hf"
    revision = "a272c74"
    
    if torch.backends.mps.is_available(): # 맥북 gpu
        _device = "mps"
    elif torch.cuda.is_available(): # 서버 gpu
        _device = "cuda"
    else:
        _device = "cpu"
    
    # Cuda 4-bit 양자화 설정
    if _device == "cuda":
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16
        )
    else:
        quantization_config = None
    
    # 모델 로드
    print("----- LLaVA 모델 불러오는 중 -----")
    _model = LlavaForConditionalGeneration.from_pretrained(
        model_id,
        revision=revision,
        quantization_config=quantization_config,
        torch_dtype=torch.float16,
        device_map="auto"
    )

    try:
        _processor = AutoProcessor.from_pretrained(model_id, revision=revision)
    except Exception as e:
       print(f"❌ 프로세서 로드 실패: {e}")
       raise

    print("✅ LLaVA 모델 로드 완료")
    
    return _model, _processor, _device

def _as_str(m):
    return m.group(1).strip() if isinstance(m, re.Match) else (m.strip() if isinstance(m, str) else "")

def load_image(image_path: str, question: str|None)-> Image.Image:
    # 1) S3 URL인 경우
    if image_path.startswith("http://") or image_path.startswith("https://"):
        resp = requests.get(image_path, timeout=10)
        resp.raise_for_status()
        return Image.open(BytesIO(resp.content)).convert("RGB")

    # 2) 로컬 경로인 경우
    local_path = image_path if question else "." + image_path
    return Image.open(local_path).convert("RGB")

def run_llava(image_path: str, question: str|None, defect_id: str|None, defect_type: str|None, urgency:str|None):
    """
    디스코드 챗봇에서 호출용:
        image_path: 분석할 이미지 파일 경로
        uestion: 버튼으로 받은 한국어 질문
    """
    
    model, processor, device = load_llava_model()

    # 이미지와 프롬프트 입력받기
    image = load_image(image_path, question)

    # llava 질문(+배경지식 제공)
    prompt_start = textwrap.dedent(
    """
    You are an AI assistant analyzing a potential building defect from a drone image for a preliminary assessment.
    Your analysis is NOT a substitute for a professional engineering inspection.
    Analyze the image carefully and provide the following information in a structured format.
    ===========================
    ETAILED DEFECT GUIDELINES
    ==========================

    Classify the defect into exactly ONE of the following categories:
    [Concrete Crack, Concrete Spalling, Paint Damage, Rebar Exposure, None]
    Use the following definitions and visual criteria strictly:

    1. Concrete Crack:
    - Appears as one or multiple linear cracks (thin or thick lines).
    - Cracks may run vertically, horizontally, or diagonally.
    - Severity increases when cracks are thicker, longer, or branching.
    - Minor cracks usually appear as slightly darker lines compared to the surrounding concrete, with low color contrast.
    - Severe or deep cracks appear significantly darker, often nearly black, because the interior receives little to no light.
    - IMPORTANT: Even if the crack is thin, if it appears consistently dark or black along a long segment, treat it as a deeper or more severe crack. In such cases, assign Medium or High urgency rather than Low.
    - IMPORTANT: Only the surface is split; no thick concrete chunk is missing.

    2. Rebar Exposure:
    - Reinforcing steel bars are visible due to severe concrete loss.
    - Rebar may appear rusty, orange-brown, or metallic.
    - The surrounding concrete is deeply missing.
    - Urgency is Classified as High.
    - IMPORTANT: If any rebar is visible, classify as Rebar Exposure (not Crack or Spalling).

    3. Concrete Spalling:
    - Thick concrete pieces have detached, creating a deep, rough, irregular cavity.
    - Much deeper and thicker than paint peeling.
    - Severity increases with depth, width, and size of the missing concrete.
    - Urgency is classified as High or Medium (depends on depth, width, and size)
    - IMPORTANT: If rebar is visible, classify as Rebar Exposure instead.

    4. Paint Damage:
    - Only the outer paint layer is peeling or flaking.
     The underlying concrete remains intact.
    - The removed layer is thin, shallow, and mostly cosmetic.
    - Urgency is Classified as Low.

    5. None:
    - If the image does not match ANY of the above defect characteristics, classify as “None”.
    - Examples of NON-defects: window frames, door frames, panel seams, tile joints, shadows, reflections, dirt, stains.
    - Straight lines from structural elements must NOT be considered cracks.
    - If the category is "None", urgency also returns "None"

    ===========================
    INSTRUCTIONS FOR OUTPUT
    ===========================
    Return your answer ONLY in the following format:

    1. Defect Type: <one of the five categories>
    2. Urgency for Inspection: <Low, Medium, or High>

    Do not include any additional explanation.""")


    llava_questions = {
        "이미지에 나타난 손상에 대해 분석 요약해주세요": textwrap.dedent(f"""You are an AI assistant analyzing a potential building defect from a drone image for a preliminary assessment.
                                                                Your analysis is NOT a substitute for a professional engineering inspection.
                                                                For context, this damage has been previously classified as:
                                                                - Defect type: {defect_type}
                                                                - Preliminary urgency level: {urgency}
                                                                You may use this information as a soft hint, but base your description primarily on what you can see in the image itself.

                                                                Provide a concise but informative description in 3–4 sentences, in a natural conversational tone.
                                                                Follow this pattern as closely as possible:

                                                                "The damage in the image appears as [brief visual description of the damage: shape, size, location, and visible texture/color differences]. Based on this appearance, it could cause [potential issues or risks], and the urgency of repair appears to be [how urgent the repair seems, e.g., not very urgent / advisable in the near future / quite urgent]."

                                                                Replace the bracketed parts with your assessment based on the image.
                                                                Do not add any extra sentences, lists, or sections outside this pattern.
                                                            """),
        "어떤 조치가 필요할지 조언해주세요": textwrap.dedent(f"""Based only on the visible appearance of the damage in the image, and the following prior assessment:
                                                        - Defect type: {defect_type}
                                                        - Preliminary urgency level: {urgency}
                                                        what kind of follow-up actions would you tentatively recommend?
                                                        For example, you may mention things like closer professional inspection, monitoring over time, or simple surface repair.
                                                        Answer cautiously in 3-4 sentences, and clearly state that a professional on-site inspection is required before any real repair decision is made.
                                                    """)
    }

    user_text = llava_questions.get(question, question) if question else (prompt_start).strip()
    if device=="mps":
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
    elif device=="cuda":
        prompt_for_model = (
            "USER: <image>\n"
            f"{user_text}\n"
            "ASSISTANT:"
        )

    # 모델 추론 실행
    processor.patch_size = model.config.vision_config.patch_size
    processor.vision_feature_select_strategy = model.config.vision_feature_select_strategy

    inputs = processor(
        text=prompt_for_model,
        images=image,
        return_tensors="pt",
    )

    generate_ids = model.generate(**inputs, max_new_tokens=1500) # max_new_tokens로 답변 길이 조절
    english_result_full = processor.batch_decode(generate_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]

    # 결과 출력(프롬프트를 제외한 순수 답변 부분만 추출)
    english_result = english_result_full.split("ASSISTANT:")[-1].strip()

    if question:
        korean_result = GoogleTranslator(source='en', target='ko').translate(english_result)
        formatted_korean = re.sub(r'(?<=[가-힣\w][다요함임]\.)+', '\n', korean_result).strip()
        print("--- LLaVA 답변(eng) ---")
        print(english_result)
        print("--- LLaVA 답변(kor) ---")
        print(formatted_korean)
        return formatted_korean
    else:
        m_type = re.search(r"Defect Type:\s*(.+)", english_result)
        m_urg = re.search(r"Urgency for Inspection:\s*(.+)", english_result)

        defect_type = _as_str(m_type)
        urgency = _as_str(m_urg)

        defect_type_kr = defect_type_choice.get(defect_type, "분류 안됨")

        urgency_kr = urgency_choice.get(urgency, "분류 안됨")

        print("--- LLaVA 답변(eng) ---")
        print(f"Defect type: {defect_type}, Urgency: {urgency}")
        print("--- LLaVA 답변(kor) ---")
        print(f"손상 유형: {defect_type_kr}, 위험도: {urgency_kr}")
        return defect_type_kr, urgency_kr