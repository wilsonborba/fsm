from __future__ import annotations

import hashlib
import hmac
from typing import Dict, List, Tuple
from urllib.parse import quote

SERVICE = "s3"
ALGORITHM = "AWS4-HMAC-SHA256"
UNSIGNED_PAYLOAD = "UNSIGNED-PAYLOAD"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def derive_signing_key(secret_access_key: str, date_stamp: str, region: str) -> bytes:
    key_date = _hmac(f"AWS4{secret_access_key}".encode("utf-8"), date_stamp)
    key_region = _hmac(key_date, region)
    key_service = _hmac(key_region, SERVICE)
    return _hmac(key_service, "aws4_request")


def credential_scope(date_stamp: str, region: str) -> str:
    return f"{date_stamp}/{region}/{SERVICE}/aws4_request"


def uri_encode(value: str) -> str:
    """RFC 3986 percent-encoding, keeping '/' literal (path segment separator)."""
    return quote(value, safe="/-_.~")


def canonical_query_string(params: List[Tuple[str, str]]) -> str:
    encoded = sorted((quote(k, safe="-_.~"), quote(v, safe="-_.~")) for k, v in params)
    return "&".join(f"{k}={v}" for k, v in encoded)


def canonical_headers(headers: Dict[str, str], signed_header_names: List[str]) -> str:
    lines = []
    for name in signed_header_names:
        value = " ".join(headers[name].split())
        lines.append(f"{name}:{value}\n")
    return "".join(lines)


def build_canonical_request(
    method: str,
    canonical_uri: str,
    canonical_qs: str,
    headers: Dict[str, str],
    signed_header_names: List[str],
    hashed_payload: str,
) -> str:
    return "\n".join(
        [
            method.upper(),
            canonical_uri,
            canonical_qs,
            canonical_headers(headers, signed_header_names),
            ";".join(signed_header_names),
            hashed_payload,
        ]
    )


def build_string_to_sign(amz_date: str, scope: str, canonical_request: str) -> str:
    return "\n".join(
        [
            ALGORITHM,
            amz_date,
            scope,
            sha256_hex(canonical_request.encode("utf-8")),
        ]
    )


def sign(secret_access_key: str, date_stamp: str, region: str, string_to_sign: str) -> str:
    signing_key = derive_signing_key(secret_access_key, date_stamp, region)
    return hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()


def parse_credential(credential: str) -> Tuple[str, str, str]:
    """credential = '<access_key_id>/<date>/<region>/s3/aws4_request' -> (access_key_id, date, region)."""
    parts = credential.split("/")
    if len(parts) != 5 or parts[3] != SERVICE or parts[4] != "aws4_request":
        raise ValueError(f"Malformed credential scope: {credential!r}")
    return parts[0], parts[1], parts[2]
