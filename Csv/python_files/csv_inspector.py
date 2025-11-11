# app/utils/csv_inspector.py  (lines 1~end)
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# 헤더 별칭 사전
# - 좌: 입력에서 올 수 있는 다양한 헤더
# - 우: 내부 표준 키
DEFAULT_HEADER_ALIASES: Dict[str, str] = {
    "상품명": "name",
    "name": "name",
    "Name": "name",
    "상품코드": "sku",
    "sku": "sku",
    "SKU": "sku",
    "카테고리": "category_name",
    "category": "category_name",
    "category_name": "category_name",
    "카테고리ID": "category_id",
    "category_id": "category_id",
    "수량": "quantity",
    "재고": "quantity",
    "qty": "quantity",
    "quantity": "quantity",
    "단가": "price",
    "가격": "price",
    "price": "price",
}

# 구분자 후보
CANDIDATE_DELIMITERS = [",", ";", "\t"]

# 인코딩 후보
CANDIDATE_ENCODINGS = ["utf-8-sig", "utf-8", "cp949", "euc-kr"]


@dataclass
class InspectResult:
    encoding: str
    delimiter: str
    headers_original: List[str]
    headers_normalized: List[str]
    header_map: Dict[str, str]          # 원본헤더 -> 표준키
    preview_rows: List[Dict[str, str]]  # 표준키 기반 미리보기 N행


def _try_decode(raw: bytes) -> Tuple[str, str]:
    # 여러 인코딩으로 디코드 시도함
    last_error = None
    for enc in CANDIDATE_ENCODINGS:
        try:
            return raw.decode(enc), enc
        except Exception as e:
            last_error = e
            continue
    raise UnicodeDecodeError("unknown", raw, 0, 1, f"failed to decode with {CANDIDATE_ENCODINGS}: {last_error}")


def _sniff_delimiter(text: str) -> str:
    # csv.Sniffer 우선 시도함. 실패 시 후보군 카운트로 대체함
    try:
        sample = text[:10000]
        dialect = csv.Sniffer().sniff(sample, delimiters="".join(CANDIDATE_DELIMITERS))
        if dialect.delimiter in CANDIDATE_DELIMITERS:
            return dialect.delimiter
    except Exception:
        pass
    counts = {d: text.count(d) for d in CANDIDATE_DELIMITERS}
    return max(counts, key=lambda k: (counts[k], k == ","))  # 동률이면 콤마 우선


def _normalize_header_one(h: str) -> str:
    # 공백 제거 및 BOM 제거함
    base = h.strip().replace("\ufeff", "")
    return base


def _build_header_map(headers: List[str], aliases: Dict[str, str]) -> Dict[str, str]:
    # 헤더를 표준 키로 매핑함
    mapping: Dict[str, str] = {}
    for h in headers:
        normalized = _normalize_header_one(h)
        # 완전 일치 우선
        if normalized in aliases:
            mapping[h] = aliases[normalized]
            continue
        # 소문자 비교
        lower = normalized.lower()
        if lower in aliases:
            mapping[h] = aliases[lower]
            continue
        # 특수문자 제거 후 비교
        squashed = "".join(ch for ch in lower if ch.isalnum() or ch == "_")
        if squashed in aliases:
            mapping[h] = aliases[squashed]
            continue
        # 매핑 실패 시 원본 유지함(후단에서 처리)
        mapping[h] = normalized
    return mapping


def inspect_csv(
    raw_bytes: bytes,
    header_aliases: Optional[Dict[str, str]] = None,
    preview_limit: int = 5,
) -> InspectResult:
    """
    업로드 CSV 바이트 분석 유틸
    - 인코딩 감지 및 디코드
    - 구분자 추론
    - 헤더 정규화 및 별칭 매핑
    - 표준 키 기반 미리보기 N행 생성
    """
    if header_aliases is None:
        header_aliases = DEFAULT_HEADER_ALIASES

    text, encoding = _try_decode(raw_bytes)
    delimiter = _sniff_delimiter(text)

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    original_headers = reader.fieldnames or []

    header_map = _build_header_map(original_headers, header_aliases)
    normalized_headers = [header_map.get(h, h) for h in original_headers]

    preview: List[Dict[str, str]] = []
    for i, row in enumerate(reader):
        if i >= preview_limit:
            break
        normalized_row: Dict[str, str] = {}
        for k, v in (row or {}).items():
            norm_key = header_map.get(k, k)
            normalized_row[norm_key] = (v or "").strip()
        preview.append(normalized_row)

    return InspectResult(
        encoding=encoding,
        delimiter=delimiter,
        headers_original=original_headers,
        headers_normalized=normalized_headers,
        header_map=header_map,
        preview_rows=preview,
    )
