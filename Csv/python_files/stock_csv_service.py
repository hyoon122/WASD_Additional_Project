# app/services/stock_csv_service.py
# 목적: Stocks CSV 임포트/익스포트 핵심 서비스
# 의존: SQLAlchemy Session, app.models.stock_model.Stock, app.models.category_model.Category

from __future__ import annotations

import csv
import io
import base64
from datetime import datetime
from typing import Any, Dict, Iterable, List, Tuple, Optional, Literal

from sqlalchemy.orm import Session
from sqlalchemy import select, func

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
            # 모든 DB에서 동작하도록 lower 비교로 통일
            query = query.where(func.lower(Stock.name).like(func.lower(like)))

        # 카테고리 필터
        if category_id is not None:
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
        else:
            query = query.order_by(Stock.id.asc())        

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
        db,                   # Session 타입이어도 되고, 여기선 사용 안 함
        file_bytes: bytes,
        *,
        dry_run: bool = True,  # 현재는 드라이런만 지원
        upsert: bool = True,   # 자리만 잡아둠(미사용)
        chunk_size: int = 1000 # 자리만 잡아둠(미사용)
    ) -> Dict[str, Any]:
        """
        안정화 버전 CSV 임포트
        - DB 미반영 드라이런만 지원
        - 인코딩/구분자 자동감지 + 헤더 표준화 + 기본 검증
        - 외부 헬퍼 의존성 전부 제거
        """
        # 1) 파일 형식 분석
        ins = inspect_csv(file_bytes)  # encoding, delimiter, header_map, preview_rows 확보
        text_io = io.TextIOWrapper(io.BytesIO(file_bytes), encoding=ins.encoding, newline="")
        reader = csv.DictReader(text_io, delimiter=ins.delimiter)

        original_headers = reader.fieldnames or []
        header_map = ins.header_map
        normalized_headers = [header_map.get(h, h) for h in original_headers]

        # 2) 필수 헤더 최소셋 검사
        required_min = ["name", "inventory"]
        missing = [h for h in required_min if h not in normalized_headers]
        if missing:
            return {
                "dry_run": True,
                "total_rows": 0,
                "valid_rows": 0,
                "invalid_rows": 1,
                "errors": [{"row": 0, "field": ",".join(missing), "message": f"필수 헤더 누락: {missing}"}],
                "encoding": ins.encoding,
                "delimiter": ins.delimiter,
                "headers_original": original_headers,
                "headers_normalized": normalized_headers,
            }

        # 3) 행 단위 표준화 + 기본 검증
        total = 0
        valid = 0
        errors: List[Dict[str, Any]] = []
        parsed: List[Dict[str, Any]] = []

        for idx, raw in enumerate(reader, start=2):  # 헤더가 1행
            total += 1
            # 원본키 → 표준키
            row: Dict[str, str] = {}
            for k, v in (raw or {}).items():
                nk = header_map.get(k, k)
                row[nk] = (v or "").strip()

            # 필수값 검사
            missing_vals = [f for f in required_min if not row.get(f)]
            if missing_vals:
                errors.append({
                    "row": idx,
                    "field": ",".join(missing_vals),
                    "message": f"필수 값 비어 있음: {missing_vals}",
                })
                continue

            # 타입 검사: inventory → 정수
            inv = row.get("inventory", "")
            try:
                # 정수만 허용
                int(inv)
            except Exception:
                errors.append({
                    "row": idx,
                    "field": "inventory",
                    "message": f"inventory는 정수여야 함: '{inv}'",
                })
                continue

            parsed.append(row)
            valid += 1

        # 4) 드라이런 리포트 반환 (DB 미반영)
        return {
            "dry_run": True if dry_run else False,
            "total_rows": total,
            "valid_rows": valid,
            "invalid_rows": len(errors),
            "errors": errors,
            "encoding": ins.encoding,
            "delimiter": ins.delimiter,
            "headers_original": original_headers,
            "headers_normalized": normalized_headers,
            "preview": ins.preview_rows,  # 표준키 기반 앞 5행
    }
    
    def dry_run(
        self,
        file_bytes: bytes,
        *,
        mode: Literal["insert", "upsert", "update-only"] = "upsert",
        conflict: Literal["skip", "overwrite"] = "skip",
        key_fields: Optional[List[str]] = None,
        preview_limit: int = 5,
        error_limit: int = 200,
    ) -> Dict[str, Any]:
        """
        CSV 드라이런 실행
        - DB 변경 없음
        - 파일 형식/헤더/타입 검증 및 요약 리포트 반환
        """

        # 로컬 기준 필수/키 정의. 클래스 상단에 이미 동일 상수가 있으면 그거 사용 권장
        required_fields = ["name", "inventory"]      # 필수 필드
        default_key_fields = ["id"]                # 기본 키 필드
        key_fields = key_fields or default_key_fields

        # 1) 파일 형식 분석: 인코딩/구분자/헤더 맵/미리보기 확보
        inspected = inspect_csv(
            file_bytes,
            header_aliases=getattr(self, "header_aliases", None),
            preview_limit=preview_limit,
        )

        # 2) 전체 행 검사 위해 다시 열기
        text = file_bytes.decode(inspected.encoding, errors="replace")
        reader = csv.DictReader(io.StringIO(text), delimiter=inspected.delimiter)
        original_headers = reader.fieldnames or []
        header_map = inspected.header_map

        # 3) 헤더 검증
        normalized_headers = [header_map.get(h, h) for h in original_headers]
        errors: List[Dict[str, Any]] = []

        for req in required_fields:
            if req not in normalized_headers:
                errors.append({
                    "row": 0,
                    "field": req,
                    "code": "MISSING_REQUIRED_HEADER",
                    "message": f"필수 헤더 없음: {req}",
                })

        for k in key_fields:
            if k not in normalized_headers:
                errors.append({
                    "row": 0,
                    "field": k,
                    "code": "MISSING_KEY_HEADER",
                    "message": f"키 헤더 없음: {k}",
                })

        # 4) 행 단위 정적 검증
        total_rows = 0
        key_seen = set()

        def build_row_key(row_norm: Dict[str, Any]):
            try:
                return tuple((row_norm.get(k) or "").strip() for k in key_fields)
            except Exception:
                return None

        for idx, row in enumerate(reader, start=2):  # 헤더 1행 기준, 데이터는 2행부터
            total_rows += 1
            if len(errors) >= error_limit:
                break

            # 표준키로 맵핑
            row_norm: Dict[str, str] = {}
            for k, v in (row or {}).items():
                nk = header_map.get(k, k)
                row_norm[nk] = (v or "").strip()

            # 필수값 확인
            for req in required_fields:
                if not row_norm.get(req):
                    errors.append({
                        "row": idx,
                        "field": req,
                        "code": "REQUIRED_VALUE_EMPTY",
                        "message": f"필수 값 비어 있음: {req}",
                    })
                    if len(errors) >= error_limit:
                        break
            if len(errors) >= error_limit:
                break

            # 타입 확인: inventory 숫자 여부
            qv = row_norm.get("inventory", "")
            if qv:
                try:
                    float(qv)
                except Exception:
                    errors.append({
                        "row": idx,
                        "field": "inventory",
                        "code": "TYPE_NUMBER_INVALID",
                        "message": f"숫자여야 함: '{qv}'",
                    })

            # 파일 내부 키 중복 체크
            row_key = build_row_key(row_norm)
            if row_key is None or any(v == "" for v in row_key):
                errors.append({
                    "row": idx,
                    "field": ",".join(key_fields),
                    "code": "KEY_INCOMPLETE",
                    "message": f"키 필드({key_fields}) 중 빈 값 존재",
                })
            else:
                if row_key in key_seen:
                    errors.append({
                        "row": idx,
                        "field": ",".join(key_fields),
                        "code": "KEY_DUPLICATED_IN_FILE",
                        "message": f"파일 내부 키 중복: {row_key}",
                    })
                else:
                    key_seen.add(row_key)

            if len(errors) >= error_limit:
                break

        # 5) 요약(예측치는 DB 미조회라 None 처리)
        summary: Dict[str, Any] = {
            "mode": mode,
            "conflict": conflict,
            "encoding": inspected.encoding,
            "delimiter": inspected.delimiter,
            "headers_original": original_headers,
            "headers_normalized": normalized_headers,
            "required_fields": required_fields,
            "key_fields": key_fields,
            "total_rows": total_rows,
            "predicted_inserts": None,
            "predicted_updates": None,
            "predicted_skips": None,
        }

        # 6) 리포트 반환
        return {
            "summary": summary,
            "preview": inspected.preview_rows,    # 표준키 기반 N행
            "errors": errors,
            "error_count": len(errors),
            "error_limit_reached": len(errors) >= error_limit,
        }

# ---------- 내부 유틸 ----------

def _ensure_header(fields: List[str] | None) -> None:
    if not fields:
        raise ValueError("CSV 헤더 없음")
    required_min = ["name", "inventory"]
    missing = [h for h in required_min if h not in fields]
    if missing:
        raise ValueError(f"필수 헤더 누락: {missing}")


def _iso(dt: datetime | None) -> str:
    return dt.isoformat(timespec="seconds") if dt else ""


def _to_str(v) -> str:
    return "" if v is None else str(v)


def _parse_int(s: str | None) -> Tuple[Optional[int], Optional[str]]:
    # 정수 전용 파서: 공백·콤마 제거 후 int 변환
    if s is None or s.strip() == "":
        return None, None
    val = s.strip().replace(",", "")
    try:
        return int(val), None
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
    # updated_at은 항상 최신화
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

