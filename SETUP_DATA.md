# 데이터 세팅 절차 (제출/재현용)

납품 불량 클레임 대응 시스템의 DB를 처음부터 구성하는 절차입니다.
아래 순서를 그대로 따르면 시연 데이터(외부 160 + 내부 750 = 910건)가 완성됩니다.

## 0. 사전 준비
- MySQL 8.x 설치, 스키마명 `claims_db`
- DB 접속 정보는 `.env` 참고 (DB_USER / DB_PASSWORD / DB_NAME)
- Python 의존성 설치: `pip install -r requirements.txt`
- **중요**: 데이터에 한글이 포함되어 있어, SQL 적재 시 반드시
  `--default-character-set=utf8mb4` 옵션을 붙여야 함 (안 붙이면 인코딩 에러)

## 데이터 파일 (프로젝트 루트에 위치)
| 파일 | 내용 | 식별 |
|------|------|------|
| `sampleDBB.sql`        | 외부 클레임 160건 (고객사 실명) | `CLM-` / report_id 1~200 |
| `add_internal_data.sql`| 내부 품질검수 750건 (자사)      | `QC-`  / report_id 1001~1750 |

## 실행 순서

### 1단계 — DB/스키마 초기화 + 기본 시드
```
python init_db.py
```
- 테이블 생성 + 기본 계정(admin/qa01/qa02, 비번 1234) + 불량유형 4종 + 설비/LOT 시드
- 참고: init_db가 `sampleDBB.sql` 자동 로드를 시도하지만, 내부 파서의 컬럼 정렬이
  이 파일과 달라 **외부 데이터는 자동 적재되지 않음**(로그 경고가 떠도 무시).
  → 외부 데이터는 아래 2단계에서 수동으로 넣는다.

### 2단계 — 외부 클레임 적재
```
mysql -u root -p --default-character-set=utf8mb4 claims_db < sampleDBB.sql
```

### 3단계 — 내부 클레임 적재
```
mysql -u root -p --default-character-set=utf8mb4 claims_db < add_internal_data.sql
```

### 3-1단계 — 외부 클레임에 AI 분류 이력 부여 (선택, 권장)
```
mysql -u root -p --default-character-set=utf8mb4 claims_db < update_ai_classification.sql
```
- 외부 시드 클레임의 약 75%를 'AI 분류 → 담당자 확정' 이력으로 채워, 목록 화면에서
  "수기입력"만 늘어서 보이는 것을 방지(현실감). 나머지 25%는 수기입력으로 남김.
- 실제 AI가 분류한 건(ai_defect_type 보유)은 덮어쓰지 않음.

### 4단계 — 적재 검증 (선택)
```sql
SELECT COUNT(*) FROM defect_reports WHERE document_no LIKE 'CLM-%';  -- 160 (외부)
SELECT COUNT(*) FROM defect_reports WHERE document_no LIKE 'QC-%';   -- 750 (내부)
SELECT COUNT(*) FROM defect_reports;                                 -- 910 (합계)
```

### 5단계 — 서버 실행
```
start.bat        (속성에서 '차단 해제' 후 실행)
```
또는
```
python run.py
```
실행 후 브라우저가 자동으로 열림 (기본 포트 8002).

## 주의사항
- **순서 고정**: 반드시 `init_db.py` → 외부 SQL → 내부 SQL.
  (두 SQL의 `defect_type`이 `defect_types` 테이블을 FK로 참조하므로, init_db가 먼저여야 함)
- **utf8mb4 필수**: 옵션을 빼면 `ERROR 1366 Incorrect string value` (한글 깨짐) 발생.
- **깨끗한 DB에서 적재**: 두 SQL은 report_id를 직접 지정하므로, 이미 같은 id가 있는
  DB에 다시 넣으면 PK 중복 에러. init_db 직후의 빈 상태에서 적재할 것.
- **모델 파일**: `models/defect_detector.pt`가 있으면 실제 AI 분류, 없으면 더미 모드로
  자동 전환(503 경고는 무시 가능).

## 내부/외부 구분 동작 (참고)
- 통계·목록 화면은 문서번호 접두사로 내부/외부를 구분한다.
  - 외부(`CLM-`): 사례 목록·PPM·고객사 랭킹·차트에 표시
  - 내부(`QC-`): 통계 탭 상단 "내부/외부 비율" 카드에만 카운트, 그 외에는 비표시
