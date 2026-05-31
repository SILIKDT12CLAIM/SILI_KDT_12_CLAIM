import io
import logging
from pathlib import Path
from PIL import Image

from backend.core.defects import MODEL_NAME_TO_CODE, DEFECT_CODES_BY_PART

logger = logging.getLogger(__name__)

# 모델은 6종(커넥터 포함)으로 학습됐으나, 시스템은 프레임 4종만 사용.
# 추론 단계에서 커넥터 클래스(gap_defect / fastening_defect)는 무시한다.
_ALLOWED_CODES = set(DEFECT_CODES_BY_PART["FRAME"])

MODEL_DIR  = Path(__file__).parent.parent.parent / "models"
MODEL_PATH = MODEL_DIR / "defect_detector.pt"   # YOLOv8 detection 모델


def load_model():
    """
    YOLOv8 detection 모델 로드.
    모델 파일 없으면 None 반환 → ai.py에서 더미 모드로 자동 전환.
    """
    if not MODEL_PATH.exists():
        logger.warning(f"모델 파일 없음({MODEL_PATH}) — 더미 모드로 동작")
        return None
    try:
        from ultralytics import YOLO
        model = YOLO(str(MODEL_PATH))
        logger.info(f"YOLOv8 detection 모델 로드 완료: {MODEL_PATH}")
        return model
    except Exception as e:
        logger.error(f"모델 로드 실패: {e}")
        return None


def predict(model, image_data: bytes) -> tuple[str | None, float]:
    """
    YOLOv8 detection 기반 불량 분류.

    모델은 6종(커넥터 포함)으로 학습됐으나, 커넥터 클래스는 무시하고
    프레임 4종(OUTER_DAMAGE / SEALING / HEMMING / HOLE_DEFORM)만 반환한다.

    반환: (defect_code, confidence)
      defect_code : OUTER_DAMAGE / SEALING / HEMMING / HOLE_DEFORM
                    (프레임 4종 미검출 시 None)
      confidence  : 0.0 ~ 1.0
    """
    img = Image.open(io.BytesIO(image_data)).convert("RGB")
    results = model(img, verbose=False)

    boxes = results[0].boxes
    if boxes is None or len(boxes) == 0:
        logger.info("미검출: 감지된 불량 없음")
        return None, 0.0

    names = results[0].names

    # 프레임 4종에 해당하는 박스만 후보로 선택 (커넥터 클래스는 무시).
    # 신뢰도 내림차순으로 보며 첫 번째 허용 코드를 채택한다.
    best_code = None
    best_conf = 0.0
    for i in range(len(boxes)):
        class_name = names[int(boxes.cls[i])]
        code = MODEL_NAME_TO_CODE.get(class_name)
        if code is None or code not in _ALLOWED_CODES:
            continue
        conf = float(boxes.conf[i])
        if conf > best_conf:
            best_conf = conf
            best_code = code

    if best_code is None:
        logger.info("미검출: 프레임 4종 불량 없음 (커넥터 클래스만 감지됨)")
        return None, 0.0

    return best_code, best_conf
