from __future__ import annotations

import base64
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

from src.core.settings import Settings
from src.core.utils import sigv4
from src.domain.services.s3_errors import S3ApiError


_MAX_CLOCK_SKEW = timedelta(minutes=15)


def _unauthorized(detail: str) -> S3ApiError:
    return S3ApiError(status_code=403, code="AccessDenied", message=detail)


def _lowercase(mapping: Dict[str, str]) -> Dict[str, str]:
    return {key.lower(): value for key, value in mapping.items()}


def _parse_amz_date(amz_date: str) -> datetime:
    try:
        return datetime.strptime(amz_date, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise _unauthorized("Invalid or missing x-amz-date") from exc


class S3AuthService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _credential(self, access_key_id: str):
        credential = self.settings.s3_credentials.get(access_key_id)
        if credential is None:
            raise _unauthorized("Unknown access key id")
        return credential

    def verify_header_auth(
        self,
        method: str,
        path: str,
        query_params: List[Tuple[str, str]],
        headers: Dict[str, str],
    ) -> str:
        headers = _lowercase(headers)
        authorization = headers.get("authorization")
        if not authorization or not authorization.startswith(sigv4.ALGORITHM):
            raise _unauthorized("Missing or malformed Authorization header")

        try:
            _, rest = authorization.split(" ", 1)
            parts = dict(
                item.strip().split("=", 1) for item in rest.split(",") if "=" in item
            )
            credential_value = parts["Credential"] if "Credential" in parts else parts["credential"]
        except (KeyError, ValueError) as exc:
            raise _unauthorized("Malformed Authorization header") from exc

        signed_headers_raw = parts.get("SignedHeaders") or parts.get("signedheaders")
        signature = parts.get("Signature") or parts.get("signature")
        if not signed_headers_raw or not signature:
            raise _unauthorized("Malformed Authorization header")

        access_key_id, date_stamp, region = sigv4.parse_credential(credential_value)
        credential = self._credential(access_key_id)

        amz_date = headers.get("x-amz-date")
        if not amz_date:
            raise _unauthorized("Missing x-amz-date header")
        request_time = _parse_amz_date(amz_date)
        now = datetime.now(timezone.utc)
        if abs(now - request_time) > _MAX_CLOCK_SKEW:
            raise _unauthorized("Request time too skewed")

        signed_header_names = signed_headers_raw.split(";")
        hashed_payload = headers.get("x-amz-content-sha256", sigv4.UNSIGNED_PAYLOAD)

        canonical_request = sigv4.build_canonical_request(
            method=method,
            canonical_uri=sigv4.uri_encode(path),
            canonical_qs=sigv4.canonical_query_string(query_params),
            headers=headers,
            signed_header_names=signed_header_names,
            hashed_payload=hashed_payload,
        )
        scope = sigv4.credential_scope(date_stamp, region)
        string_to_sign = sigv4.build_string_to_sign(amz_date, scope, canonical_request)
        expected_signature = sigv4.sign(credential.secret_access_key, date_stamp, region, string_to_sign)

        if not hmac.compare_digest(expected_signature, signature):
            raise _unauthorized("Signature does not match")

        return credential.app

    def verify_query_auth(
        self,
        method: str,
        path: str,
        query_params: List[Tuple[str, str]],
        headers: Dict[str, str],
    ) -> str:
        headers = _lowercase(headers)
        params = dict(query_params)
        credential_value = params.get("X-Amz-Credential")
        amz_date = params.get("X-Amz-Date")
        expires_raw = params.get("X-Amz-Expires")
        signed_headers_raw = params.get("X-Amz-SignedHeaders")
        signature = params.get("X-Amz-Signature")

        if not all([credential_value, amz_date, expires_raw, signed_headers_raw, signature]):
            raise _unauthorized("Missing required X-Amz-* query parameters")

        access_key_id, date_stamp, region = sigv4.parse_credential(credential_value)
        credential = self._credential(access_key_id)

        request_time = _parse_amz_date(amz_date)
        expires_seconds = int(expires_raw)
        if expires_seconds > self.settings.s3_max_expires_seconds:
            raise _unauthorized("Requested expiration exceeds the maximum allowed")
        now = datetime.now(timezone.utc)
        if now > request_time + timedelta(seconds=expires_seconds):
            raise _unauthorized("Presigned URL has expired")
        if now < request_time - _MAX_CLOCK_SKEW:
            raise _unauthorized("Presigned URL is not yet valid")

        signed_header_names = signed_headers_raw.split(";")
        signing_params = [(k, v) for k, v in query_params if k != "X-Amz-Signature"]

        canonical_request = sigv4.build_canonical_request(
            method=method,
            canonical_uri=sigv4.uri_encode(path),
            canonical_qs=sigv4.canonical_query_string(signing_params),
            headers=headers,
            signed_header_names=signed_header_names,
            hashed_payload=sigv4.UNSIGNED_PAYLOAD,
        )
        scope = sigv4.credential_scope(date_stamp, region)
        string_to_sign = sigv4.build_string_to_sign(amz_date, scope, canonical_request)
        expected_signature = sigv4.sign(credential.secret_access_key, date_stamp, region, string_to_sign)

        if not hmac.compare_digest(expected_signature, signature):
            raise _unauthorized("Signature does not match")

        return credential.app

    def verify_post_policy(self, form_fields: Dict[str, str], file_size: int, bucket: str) -> str:
        fields = _lowercase(form_fields)
        policy_b64 = fields.get("policy")
        signature = fields.get("x-amz-signature")
        credential_value = fields.get("x-amz-credential")
        if not policy_b64 or not signature or not credential_value:
            raise _unauthorized("Missing policy/signature/credential fields")

        access_key_id, date_stamp, region = sigv4.parse_credential(credential_value)
        credential = self._credential(access_key_id)

        expected_signature = sigv4.sign(credential.secret_access_key, date_stamp, region, policy_b64)
        if not hmac.compare_digest(expected_signature, signature):
            raise _unauthorized("Signature does not match")

        try:
            policy = json.loads(base64.b64decode(policy_b64))
        except (ValueError, UnicodeDecodeError) as exc:
            raise _unauthorized("Malformed policy document") from exc

        expiration = policy.get("expiration")
        if expiration:
            expires_at = datetime.strptime(expiration, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires_at:
                raise _unauthorized("Policy document has expired")

        for condition in policy.get("conditions", []):
            self._check_condition(condition, fields, file_size, bucket)

        return credential.app

    def _check_condition(self, condition, fields: Dict[str, str], file_size: int, bucket: str) -> None:
        if isinstance(condition, dict):
            (field_name, expected_value), = condition.items()
            if field_name.lower() == "bucket":
                actual_value = bucket
            else:
                actual_value = fields.get(field_name.lower())
            if actual_value != expected_value:
                raise _unauthorized(f"Policy condition failed for {field_name!r}")
            return

        if isinstance(condition, list) and condition:
            operator = condition[0]
            if operator == "content-length-range":
                _, minimum, maximum = condition
                if not (minimum <= file_size <= maximum):
                    raise _unauthorized("Uploaded file size violates content-length-range")
                return
            if operator in ("starts-with", "eq"):
                _, field_ref, expected_value = condition
                field_name = field_ref.lstrip("$").lower()
                actual_value = fields.get(field_name, "")
                matches = (
                    actual_value.startswith(expected_value)
                    if operator == "starts-with"
                    else actual_value == expected_value
                )
                if not matches:
                    raise _unauthorized(f"Policy condition failed for {field_ref!r}")
                return

        raise _unauthorized("Unsupported policy condition")
