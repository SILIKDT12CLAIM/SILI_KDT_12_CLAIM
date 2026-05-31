-- ============================================================
--  외부(CLM) 시드 클레임에 'AI 분류 → 담당자 확정' 이력 부여
--
--  배경: SQL로 직접 적재한 시드 데이터는 ai_defect_type이 비어 있어
--        목록에서 전부 "수기입력"으로 표시됨. 실제로는 과거 클레임 상당수가
--        AI 분류를 거쳤으므로, 약 75%를 AI 분류 이력으로 채워 현실감을 준다.
--        (나머지 25%는 수기입력으로 남겨 둠 — 기획서의 "AI 대상 외는 수기입력"과 일치)
--
--  안전장치:
--    - 외부(CLM-)만 대상. 내부(QC-)는 목록 비표시이므로 제외.
--    - ai_defect_type IS NULL 조건 → 실제로 AI가 분류한 시연 건은 절대 덮어쓰지 않음.
--    - report_id % 4 <> 0 → 결정적으로 약 75% 선택 (RAND 미사용, 재현 가능).
--
--  사용:
--    mysql -u root -p --default-character-set=utf8mb4 claims_db < update_ai_classification.sql
-- ============================================================

USE claims_db;

UPDATE defect_reports
SET ai_defect_type = defect_type,
    ai_confidence  = ROUND(0.72 + (report_id % 23) / 100, 3)   -- 0.72~0.94 분산
WHERE document_no LIKE 'CLM-%'
  AND ai_defect_type IS NULL
  AND (report_id % 4) <> 0;

-- 검증: 외부 클레임의 AI 분류 / 수기입력 분포
SELECT
  SUM(ai_defect_type IS NOT NULL) AS ai_classified,
  SUM(ai_defect_type IS NULL)     AS manual_input,
  COUNT(*)                        AS total_external
FROM defect_reports
WHERE document_no LIKE 'CLM-%';
