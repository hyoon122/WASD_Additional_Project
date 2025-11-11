# Stocks CSV 모듈 개요

## 1. 구조
```
app/
 ├─ utils/
 │   └─ csv_inspector.py      # CSV 파일 형식 분석 (인코딩, 헤더, 샘플행)
 ├─ services/
 │   └─ stock_csv_service.py  # 핵심 로직: 검증, import/export, dry-run
 └─ routers/
     └─ stock_csv_router.py   # API 라우터: HTTP 엔드포인트 등록
```

---

## 2. 동작 흐름
1. 사용자가 `/api/stocks/export.csv` 호출  
   → `stock_csv_router.py` → `StockCsvService.export_stream()`  
   → CSV 생성 스트리밍 응답 반환  
2. 사용자가 `/api/stocks/import` 업로드  
   → `StockCsvService.import_csv()`  
   → 내부에서 `_validate_and_clean()` 수행  
   → 검증 후 DB 반영 또는 dry-run 보고서 반환  
3. CSV 검사 기능  
   → `csv_inspector.py` 의 `inspect_csv()` 가 인코딩, 헤더, 데이터 길이 추출

---

## 3. 주요 함수 요약

| 파일 | 함수 | 설명 |
|------|------|------|
| `csv_inspector.py` | `inspect_csv(file_bytes, filename, delimiter, encoding)` | CSV 구조 자동 탐지 및 헤더 샘플 반환 |
| `stock_csv_service.py` | `inspect()` | CSV 검사(미반영) |
| 〃 | `dry_run()` | 데이터 전체 검증(DB 미반영) |
| 〃 | `import_csv()` | 검증 후 실제 반영 |
| 〃 | `export_stream()` | 조건 필터 기반 CSV 생성 |
| `stock_csv_router.py` | `GET /api/stocks/export.csv` | 내보내기 |
| 〃 | `POST /api/stocks/import` | 가져오기 및 드라이런 |

---

## 4. 유효성 검증 규칙
- `id`: 정수, 없으면 신규
- `name`: 필수, 최대 길이 제한
- `inventory`: 정수만 허용 (`float` 불가)
- `category_id`: 정수 또는 공백
- `description`: 선택, 최대 길이 제한

---

## 5. 사용 예시

### Export
```bash
curl -G "http://<EC2_IP>:8000/api/stocks/export.csv" \
  --data-urlencode "keyword=apple" -o stocks.csv
```

### Import (Dry-run)
```bash
curl -X POST "http://<EC2_IP>:8000/api/stocks/import?dry_run=true&upsert=true" \
  -F "file=@samples/stocks_sample.csv"
```

---

## 6. 에러 처리 예시
| 상황 | 응답 코드 | 설명 |
|------|-----------|------|
| 빈 파일 업로드 | 422 | `업로드된 파일이 비어있음` |
| 잘못된 정렬 키 | 400 | `CSV export 실패: ...` |
| 데이터 오류 | 200 | `errors` 필드에 상세 행·필드·메시지 반환 |

---

## 7. 향후 개선 계획
- `import_csv()` 와 `dry_run()`의 검증 공통화  
- `errors_csv_b64` 필드 추가 (프런트에서 오류 다운로드 지원)  
- 대용량 처리 시 ID 커서 기반 페이징으로 전환

