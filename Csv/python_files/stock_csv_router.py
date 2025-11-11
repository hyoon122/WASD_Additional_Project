# app/routers/stock_csv_router.py
# 목적: Stocks CSV export / import 전용 라우터
# 참고: 기존 stock_router.py는 그대로 두고, CSV 전용 엔드포인트만 분리 추가함
# 규칙: 서비스 계층(app/services/stock_csv_service.py)만 호출하도록 얇게 유지

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db  # DB 세션 의존성(프로젝트 내 공용 패턴 가정)
from app.services.stock_csv_service import StockCsvService

router = APIRouter(prefix="/api/stocks", tags=["stocks-csv"])

_service = StockCsvService()  # 상태 없음. DI 단순화


@router.get("/export.csv")
def export_stocks_csv(
    keyword: Optional[str] = Query(None, description="이름 부분 검색"),
    categoryId: Optional[int] = Query(None, alias="categoryId", description="카테고리 필터"),
    sort: Optional[str] = Query(None, description='정렬 키: "id:asc", "name:desc" 등'),
    db: Session = Depends(get_db),
):
    """
    재고(Stocks) CSV 익스포트
    - 페이징 파라미터는 무시. 필터(keyword, categoryId), 정렬(sort)만 반영.
    - 결과는 text/csv 스트리밍
    """
    # 파일명: stocks_YYYYMMDD_HHMMSS.csv (서버 로컬 타임 기준)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"stocks_{ts}.csv"

    # 서비스 레이어 스트림 제너레이터
    stream = _service.export_stream(
        db,
        keyword=keyword,
        category_id=categoryId,
        sort=sort,
    )

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }
    return StreamingResponse(stream, media_type="text/csv; charset=utf-8", headers=headers)


@router.post("/import", response_class=JSONResponse)
async def import_stocks_csv(
    file: UploadFile = File(..., description="CSV 파일 (UTF-8, 헤더 포함)"),
    dry_run: bool = Query(True, description="드라이런 여부(기본: True)"),
    upsert: bool = Query(True, description="id 있으면 업데이트, 없으면 생성"),
    db: Session = Depends(get_db),
):
    """
    재고(Stocks) CSV 임포트
    - dry_run=True: 유효성 검사만 하고 DB 미반영. 리포트 JSON 반환.
    - upsert=True: id 존재 시 업데이트, 없으면 생성.
    - 실패 행은 errors에 누적.
    """
    # 파일 읽기
    file_bytes = await file.read()

    # 서비스 호출
    report = _service.import_csv(
        db,
        file_bytes,
        dry_run=dry_run,
        upsert=upsert,
    )
    return JSONResponse(content=report, status_code=200)
