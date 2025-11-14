# 📄 CSV 기능 통합 가이드

**(FastWMS 프로젝트용 통합 안내서)**

본 문서는 `stock_csv_router.py`, `stock_csv_service.py`,
`csv_inspector.py`,\
그리고 데모 화면(`stock_csv_demo.html/css/js`)을\
기존 FastWMS 프로젝트 구조에 통합하기 위한 절차를 설명합니다.

------------------------------------------------------------------------

# 1. 파일 구조 반영

## 1.1 최종 통합 후 구조

    app
    ├── core
    │   ├── config.py
    │   └── database.py
    ├── crud
    │   └── stock_crud.py
    ├── main.py
    ├── models
    │   └── stock_model.py
    ├── routers
    │   ├── stock_router.py
    │   └── stock_csv_router.py     ← 새로 추가
    ├── schemas
    │   └── stock_schema.py
    ├── services
    │   ├── stock_service.py
    │   └── stock_csv_service.py    ← 새로 추가
    ├── static
    │   ├── css
    │   │   └── stock_csv.css
    │   ├── js
    │   │   └── stock_csv.js
    │   └── images
    ├── templates
    │   └── stock.html
    └── utils
        └── csv_inspector.py

------------------------------------------------------------------------

# 2. 백엔드 통합 절차

## 2.1 csv_inspector.py 추가

    app/utils/csv_inspector.py

## 2.2 stock_csv_service.py 추가

    app/services/stock_csv_service.py

## 2.3 stock_csv_router.py 추가

    app/routers/stock_csv_router.py

``` python
from fastapi import APIRouter, UploadFile, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.stock_csv_service import StockCsvService
from app.utils.csv_inspector import CsvInspector

router = APIRouter(
    prefix="/api/stocks/csv",
    tags=["stocks-csv"]
)

@router.post("/import")
async def import_stocks_csv(
    file: UploadFile,
    db: Session = Depends(get_db)
):
    inspector = CsvInspector()
    service = StockCsvService(db=db, inspector=inspector)
    return await service.import_csv(file)


@router.get("/export")
async def export_stocks_csv(
    db: Session = Depends(get_db)
):
    inspector = CsvInspector()
    service = StockCsvService(db=db, inspector=inspector)
    return await service.export_csv()
```

------------------------------------------------------------------------

# 2.4 main.py 라우터 등록

``` python
from fastapi import FastAPI
from app.routers import stock_csv_router

app = FastAPI()

app.include_router(stock_csv_router.router)
```

------------------------------------------------------------------------

# 3. 프론트엔드 통합 절차

## 3.1 CSS 이동

    app/static/css/stock_csv.css

``` html
<link rel="stylesheet" href="{{ url_for('static', path='css/stock_csv.css') }}">
```

## 3.2 JS 이동

    app/static/js/stock_csv.js

``` html
<script src="{{ url_for('static', path='js/stock_csv.js') }}"></script>
```

## 3.3 stock.html 수정

``` html
<div class="csv-tools">
    <input type="file" id="csvFileInput" accept=".csv" />
    <button id="csvUploadButton">CSV 업로드</button>
    <button id="csvDownloadButton">CSV 다운로드</button>
</div>
```

------------------------------------------------------------------------

# 4. API 엔드포인트

  기능         메서드   경로
  ------------ -------- --------------------------
  CSV Import   POST     `/api/stocks/csv/import`
  CSV Export   GET      `/api/stocks/csv/export`

------------------------------------------------------------------------

# 5. 체크리스트

-   [ ] CSV Import 정상동작\
-   [ ] CSV Export 파일 다운로드\
-   [ ] HTML 버튼 연동 확인\
-   [ ] 컬럼 검사 정상 작동

------------------------------------------------------------------------

# 6. 요약

**라우터·서비스·유틸 구조로 분리하여 추가하고\
`main.py`에 라우터 한 줄만 등록하면 기능이 완전히 통합됩니다.**
