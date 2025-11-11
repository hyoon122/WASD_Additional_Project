# Stocks CSV API 계약서

## 개요
- 목적: 재고 데이터의 **대량 내보내기(Export)**, **대량 가져오기(Import)**, **드라이런 검증(Dry-run)** 제공
- 기본 경로: `/api/stocks`
- 응답 포맷: `text/csv`(export), `application/json`(import)

---

## 1) 내보내기: Export CSV

### HTTP
```
GET /api/stocks/export.csv
```

### Query 파라미터
| 이름 | 타입 | 설명 | 비고 |
|---|---|---|---|
| `keyword` | string | 이름 부분 검색 | 선택 |
| `categoryId` | int | 카테고리 필터 | 선택, 내부는 `category_id`로 매핑 |
| `sort` | string | 정렬 규칙 | 예: `id:asc`, `name:desc` |

### 응답
- 성공: `200 OK`, 헤더 `Content-Disposition: attachment; filename="stocks_YYYYMMDD_HHMMSS.csv"`  
- 본문: `text/csv; charset=utf-8` 스트림

### CSV 컬럼(예시)
```
id,name,inventory,category_id,description,created_at,updated_at
```

### 예시 요청
```bash
curl -G "http://127.0.0.1:8000/api/stocks/export.csv" \
  --data-urlencode "keyword=apple" \
  --data-urlencode "categoryId=0" \
  --data-urlencode "sort=id:desc" \
  -o stocks.csv
```

---

## 2) 가져오기: Import CSV (+ 드라이런)

### HTTP
```
POST /api/stocks/import?dry_run=true&upsert=true
Content-Type: multipart/form-data
```

### Query 파라미터
| 이름 | 타입 | 기본값 | 설명 |
|---|---|---:|---|
| `dry_run` | bool | `true` | 검증만 수행, DB 미반영 |
| `upsert` | bool | `true` | `id`가 존재하면 업데이트, 없으면 생성 |

### Form-Data
| 이름 | 타입 | 설명 |
|---|---|---|
| `file` | 파일 | CSV 파일(UTF-8, 헤더 포함) |

### CSV 요구사항
- **필수 헤더**: `id,name,inventory,category_id`  
- **검증 규칙 요약**
  - `id`: 정수 또는 빈 값(신규)
  - `name`: 비어 있을 수 없음, 최대 길이(서비스 상수 기준)
  - `inventory`: **정수**만 허용
  - `category_id`: 정수 또는 빈 값
- `dry_run=true`일 때는 **오류만 리턴**, DB 변경 없음

### 성공 응답 예시(dry_run=true)
```json
{
  "dry_run": true,
  "total_rows": 3,
  "valid_rows": 2,
  "invalid_rows": 1,
  "errors": [
    {
      "row": 3,
      "field": "inventory",
      "message": "inventory는 정수여야 함: '1.7'"
    }
  ],
  "summary": {
    "to_create": 1,
    "to_update": 1,
    "skipped": 1
  }
}
```

### 성공 응답 예시(dry_run=false)
```json
{
  "dry_run": false,
  "total_rows": 3,
  "created": 1,
  "updated": 1,
  "skipped": 1,
  "errors": []
}
```

### 오류 응답 예시
- 빈 파일 업로드:
```json
{
  "detail": "업로드된 파일이 비어있음"
}
```
- 일반 처리 오류:
```json
{
  "detail": "CSV import 실패: <원인 메시지>"
}
```

### 예시 요청
```bash
# 드라이런
curl -X POST "http://127.0.0.1:8000/api/stocks/import?dry_run=true&upsert=true" \
  -F "file=@stocks_sample.csv"

# 실반영
curl -X POST "http://127.0.0.1:8000/api/stocks/import?dry_run=false&upsert=true" \
  -F "file=@stocks_sample.csv"
```

---

## 3) 샘플 CSV

```
id,name,inventory,category_id,description
,New Apple,50,0,첫 입고
2,Keyboard,120,1,기존 재고 갱신
3,Mouse,1.7,1,잘못된 재고(정수 아님)
```

> 주석 라인은 실제 파일에 넣지 말 것. 마지막 행은 검증 실패 예시를 담기 위한 의도적 오류.

---

## 4) 상태 코드

| 코드 | 의미 | 예시 상황 |
|---:|---|---|
| 200 | 성공 | Export 스트리밍, Import 보고서 |
| 400 | 잘못된 요청 | 정렬 키 오류, 내부 변환 실패 등 일반 처리 예외 |
| 422 | 처리 불가 | 업로드 파일이 비어 있는 경우 등 |

---

## 5) 통합 체크리스트
- [ ] `app/routers/stock_csv_router.py`가 `app/main.py`에 `include_router`로 연결되어 있는가  
- [ ] 서비스에서 `keyword` 검색이 데이터베이스 무관하게 동작(`lower LIKE`)하는가  
- [ ] `inventory`를 정수로만 검증하는가  
- [ ] `categoryId=0`이 필터로 정상 반영되는가  
- [ ] 드라이런에서 오류 개수·행 번호·필드명이 정확히 표기되는가  

---

## 6) 팀 핸드오프 가이드
- 프런트: 위 cURL을 Postman에 그대로 등록하면 된다. `multipart/form-data`로 파일 전송 필수.  
- 백엔드: 운영 전, 드라이런으로 **오류 케이스**를 먼저 수집하고 실제 반영은 최종 승인 후 실행.  
- QA: 샘플 CSV의 오류 행을 케이스 템플릿으로 활용.