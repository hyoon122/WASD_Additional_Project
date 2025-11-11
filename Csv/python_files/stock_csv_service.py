# app/services/stock_csv_service.py
# 목적: Stocks CSV 임포트/익스포트 핵심 서비스
# 의존: SQLAlchemy Session, app.models.stock_model.Stock, app.models.category_model.Category

from __future__ import annotations

import csv
import io
import base64
from datetime import datetime
from typing import Any, Dict, Iterable, List, Tuple, Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.stock_model import Stock
from app.models.category_model import Category
from app.utils.csv_inspector import inspect_csv

# CSV 헤더 고정
CSV_HEADERS = [
    "id",
    "name",
    "inventory",
    "category_id",
    "price",
    "description",
    "created_at",
    "updated_at",
]

# 검증 규칙
MAX_NAME_LEN = 255
MAX_DESC_LEN = 2000


class StockCsvService:
    """Stocks CSV 임포트/익스포트 서비스"""

    # ------- 익스포트 -------

    def export_stream(
        self,
        db: Session,
        *,
        keyword: Optional[str] = None,
        category_id: Optional[int] = None,
        sort: Optional[str] = None,
    ) -> Iterable[bytes]:
        """
        CSV 스트리밍 제너레이터 반환
        - 필터: keyword(name LIKE), category_id
        - sort: 예) "id:asc", "name:desc"
        """
        query = select(Stock)

        # 키워드 필터
        if keyword:
            like = f"%{keyword}%"
            # ilike 사용 위해 DB가 대소문자 무시 지원해야 함. 미지원 시 lower 비교로 변경 필요.
            query = query.where(Stock.name.ilike(like))

        # 카테고리 필터
        if category_id:
            query = query.where(Stock.category_id == category_id)

        # 정렬
        if sort:
            col, _, direction = sort.partition(":")
            direction = (direction or "asc").lower()
            col_map = {
                "id": Stock.id,
                "name": Stock.name,
                "inventory": Stock.inventory,
                "price": Stock.price,
                "created_at": Stock.created_at,
                "updated_at": Stock.updated_at,
            }
            if col in col_map:
                order_col = col_map[col]
                query = query.order_by(
                    order_col.asc() if direction == "asc" else order_col.desc()
                )

        # 헤더 라인 먼저 출력
        header_io = io.StringIO()
        writer = csv.writer(header_io)
        writer.writerow(CSV_HEADERS)
        yield header_io.getvalue().encode("utf-8")

        # 청크로 스트리밍
        chunk_size = 1000
        offset = 0
        while True:
            rows = db.execute(query.limit(chunk_size).offset(offset)).scalars().all()
            if not rows:
                break
            offset += chunk_size

            buf = io.StringIO()
            writer = csv.writer(buf)
            for s in rows:
                writer.writerow(
                    [
                        s.id,
                        s.name,
                        s.inventory,
                        s.category_id,
                        _to_str(s.price),
                        s.description or "",
                        _iso(s.created_at),
                        _iso(s.updated_at),
                    ]
                )
            yield buf.getvalue().encode("utf-8")

    # ------- 임포트 -------

    def import_csv(
        self,
        db: Session,
        file_bytes: bytes,
        *,
        dry_run: bool = True,
        upsert: bool = True,
        chunk_size: int = 1000,
    ) -> Dict:
        """
        CSV 임포트 수행
        - dry_run=True: 검증만, DB 미반영
        - upsert=True: id 존재 시 업데이트, 없으면 생성
        - chunk_size: 커밋 단위
        - 반환: 리포트 dict (dry_run 시 errors.csv Base64 포함)
        """
        text_io = io.TextIOWrapper(io.BytesIO(file_bytes), encoding="utf-8")
        reader = csv.DictReader(text_io)
        _ensure_header(reader.fieldnames)

        rows = list(reader)
        total_rows = len(rows)
        errors: List[Dict] = []

        # 카테고리 캐시
        existing_category_ids = _load_category_id_set(db)

        # 1차 검증
        parsed: List[Tuple[int, Dict]] = []  # (rownum, clean_dict)
        seen_ids: Dict[int, int] = {}  # id -> 최초 발견 행번호
        for idx, raw in enumerate(rows, start=2):  # 헤더 다음이 2행
            clean, row_errors = _validate_and_clean(raw, idx, existing_category_ids)
            if row_errors:
                errors.extend(row_errors)
                continue

            # 같은 id 중복 검사
            if clean.get("id") is not None:
                cid = clean["id"]
                if cid in seen_ids:
                    errors.append(
                        {"row": idx, "field": "id", "message": f"중복 id (이전에 {seen_ids[cid]}행에서 등장)"}
                    )
                else:
                    seen_ids[cid] = idx

            parsed.append((idx, clean))

        if dry_run:
            # upsert 시뮬레이션 집계
            would_create = 0
            would_update = 0
            if upsert:
                existing_ids = _load_existing_stock_ids(
                    db, [p[1]["id"] for p in parsed if p[1]["id"] is not None]
                )
                for _, d in parsed:
                    if d.get("id") and d["id"] in existing_ids:
                        would_update += 1
                    else:
                        would_create += 1
            else:
                for _, d in parsed:
                    if d.get("id") is None:
                        would_create += 1
                    else:
                        errors.append(
                            {"row": 0, "field": "id", "message": "upsert=false에서는 id 지정 불가"}
                        )

            # errors.csv(Base64) 생성(있을 때만)
            errors_csv_b64 = None
            errors_csv_filename = None
            if errors:
                ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                errors_csv_filename = f"stocks_import_errors_{ts}.csv"
                errors_csv_b64 = _errors_to_csv_b64(errors)

            return {
                "dry_run": True,
                "total_rows": total_rows,
                "valid_rows": len(parsed),
                "invalid_rows": len(errors),
                "errors": errors,
                "would_create": would_create,
                "would_update": would_update,
                "upsert": upsert,
                "errors_csv_b64": errors_csv_b64,
                "errors_csv_filename": errors_csv_filename,
            }

        # 실제 반영 (청크 단위 트랜잭션)
        created = 0
        updated = 0

        existing_ids = _load_existing_stock_ids(
            db, [p[1]["id"] for p in parsed if p[1]["id"] is not None]
        )

        for i in range(0, len(parsed), chunk_size):
            chunk = parsed[i : i + chunk_size]
            try:
                for _, d in chunk:
                    if upsert and d.get("id") and d["id"] in existing_ids:
                        # 업데이트
                        db_obj = db.get(Stock, d["id"])
                        if db_obj is None:
                            # 동시성으로 사라진 경우 생성으로 대체
                            db_obj = Stock()
                            _assign_stock(db_obj, d, is_create=True)
                            db.add(db_obj)
                            created += 1
                        else:
                            _assign_stock(db_obj, d)
                            updated += 1
                    else:
                        # 생성
                        db_obj = Stock()
                        _assign_stock(db_obj, d, is_create=True)
                        db.add(db_obj)
                        created += 1
                db.commit()
            except Exception as e:
                db.rollback()
                errors.append(
                    {"row": 0, "field": "chunk", "message": f"청크 커밋 실패: {e}"}
                )

        return {
            "dry_run": False,
            "total_rows": total_rows,
            "valid_rows": len(parsed),
            "invalid_rows": len(errors),
            "errors": errors,
            "created": created,
            "updated": updated,
            "upsert": upsert,
        }


# ---------- 내부 유틸 ----------

def _ensure_header(fields: List[str] | None) -> None:
    if not fields:
        raise ValueError("CSV 헤더 없음")
    missing = [h for h in CSV_HEADERS if h not in fields]
    if missing:
        raise ValueError(f"헤더 불일치: {missing} 누락")


def _iso(dt: datetime | None) -> str:
    return dt.isoformat(timespec="seconds") if dt else ""


def _to_str(v) -> str:
    return "" if v is None else str(v)


def _parse_int(s: str | None) -> Tuple[Optional[int], Optional[str]]:
    if s is None or s == "":
        return None, None
    try:
        return int(s), None
    except Exception:
        return None, "정수만 허용"


def _parse_float(s: str | None) -> Tuple[Optional[float], Optional[str]]:
    if s is None or s == "":
        return None, None
    try:
        return float(s), None
    except Exception:
        return None, "숫자만 허용"


def _parse_dt(s: str | None) -> Tuple[Optional[datetime], Optional[str]]:
    if s is None or s.strip() == "":
        return None, None
    try:
        # ISO 형식 기대
        return datetime.fromisoformat(s), None
    except Exception:
        return None, "ISO-8601 형식 아님 (예: 2025-11-10T10:30:00)"


def _validate_and_clean(
    raw: Dict[str, str],
    rownum: int,
    category_ids: set[int],
) -> Tuple[Dict, List[Dict]]:
    errs: List[Dict] = []
    out: Dict = {}

    # id
    val, err = _parse_int(raw.get("id"))
    if err:
        errs.append({"row": rownum, "field": "id", "message": err})
    out["id"] = val

    # name
    name = (raw.get("name") or "").strip()
    if not name:
        errs.append({"row": rownum, "field": "name", "message": "필수"})
    elif len(name) > MAX_NAME_LEN:
        errs.append({"row": rownum, "field": "name", "message": f"길이 {MAX_NAME_LEN}자 초과"})
    out["name"] = name

    # inventory
    inv, err = _parse_int(raw.get("inventory"))
    if err:
        errs.append({"row": rownum, "field": "inventory", "message": err})
    elif inv is None:
        errs.append({"row": rownum, "field": "inventory", "message": "필수"})
    elif inv < 0:
        errs.append({"row": rownum, "field": "inventory", "message": "0 이상"})
    out["inventory"] = inv

    # category_id
    cat_id, err = _parse_int(raw.get("category_id"))
    if err:
        errs.append({"row": rownum, "field": "category_id", "message": err})
    elif cat_id is not None and cat_id not in category_ids:
        errs.append({"row": rownum, "field": "category_id", "message": "존재하지 않는 카테고리"})
    out["category_id"] = cat_id

    # price
    price, err = _parse_float(raw.get("price"))
    if err:
        errs.append({"row": rownum, "field": "price", "message": err})
    out["price"] = price

    # description
    desc = (raw.get("description") or "").strip()
    if len(desc) > MAX_DESC_LEN:
        errs.append({"row": rownum, "field": "description", "message": f"길이 {MAX_DESC_LEN}자 초과"})
    out["description"] = desc or None

    # created_at / updated_at
    created_at, err = _parse_dt(raw.get("created_at"))
    if err:
        errs.append({"row": rownum, "field": "created_at", "message": err})
    updated_at, err = _parse_dt(raw.get("updated_at"))
    if err:
        errs.append({"row": rownum, "field": "updated_at", "message": err})

    out["created_at"] = created_at
    out["updated_at"] = updated_at

    return out, errs


def _load_category_id_set(db: Session) -> set[int]:
    ids = db.execute(select(Category.id)).scalars().all()
    return set(ids)


def _load_existing_stock_ids(db: Session, ids: List[int]) -> set[int]:
    if not ids:
        return set()
    q = select(Stock.id).where(Stock.id.in_(ids))
    return set(db.execute(q).scalars().all())


def _assign_stock(obj: Stock, d: Dict, *, is_create: bool = False) -> None:
    # 필수/기본 필드 매핑
    obj.name = d["name"]
    obj.inventory = d["inventory"]
    obj.category_id = d.get("category_id")
    obj.price = d.get("price")
    obj.description = d.get("description")

    # 타임스탬프 채우기
    now = datetime.utcnow()
    if is_create:
        obj.created_at = d.get("created_at") or now
    else:
        if d.get("created_at"):
            obj.created_at = d["created_at"]
    obj.updated_at = d.get("updated_at") or now


def _errors_to_csv_b64(errors: List[Dict]) -> str:
    """
    검증 오류 리스트를 CSV로 직렬화하여 Base64 문자열로 반환
    헤더: row,field,message
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["row", "field", "message"])
    for e in errors:
        writer.writerow([e.get("row", ""), e.get("field", ""), e.get("message", "")])
    raw = buf.getvalue().encode("utf-8")
    return base64.b64encode(raw).decode("ascii")
