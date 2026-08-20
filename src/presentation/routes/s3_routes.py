from __future__ import annotations

from urllib.parse import unquote
from xml.etree import ElementTree

from fastapi import APIRouter, Request, Response

from src.core.utils import s3_xml
from src.domain.services.s3_errors import S3ApiError


router = APIRouter()


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _authenticate(request: Request, auth_service) -> str:
    query_params = list(request.query_params.multi_items())
    headers = dict(request.headers.items())
    if "X-Amz-Signature" in request.query_params:
        return auth_service.verify_query_auth(request.method, request.url.path, query_params, headers)
    return auth_service.verify_header_auth(request.method, request.url.path, query_params, headers)


@router.post("/{bucket}")
async def post_bucket(bucket: str, request: Request) -> Response:
    auth_service = request.app.state.s3_auth_service
    s3_service = request.app.state.s3_service

    if "delete" in request.query_params:
        headers = dict(request.headers.items())
        query_params = list(request.query_params.multi_items())
        app_slug = auth_service.verify_header_auth(request.method, request.url.path, query_params, headers)
        app_slug = s3_service.require_bucket_matches_app(bucket, app_slug)

        body = await request.body()
        root = ElementTree.fromstring(body)
        keys = [
            element.text
            for element in root.iter()
            if _local_tag(element.tag) == "Key" and element.text
        ]
        deleted = s3_service.delete_objects(app_slug, keys)
        return Response(content=s3_xml.delete_result_xml(deleted), media_type="application/xml")

    form = await request.form()
    fields = {}
    upload_file = None
    for field_name, value in form.multi_items():
        if field_name.lower() == "file":
            upload_file = value
        else:
            fields[field_name] = value

    if upload_file is None:
        raise S3ApiError(400, "InvalidRequest", "Missing file field in multipart upload")

    data = await upload_file.read()
    app_slug = auth_service.verify_post_policy(fields, len(data), bucket)
    app_slug = s3_service.require_bucket_matches_app(bucket, app_slug)

    key = fields.get("key") or fields.get("Key")
    if not key:
        raise S3ApiError(400, "InvalidRequest", "Missing key field in multipart upload")

    content_type = fields.get("Content-Type") or fields.get("content-type") or upload_file.content_type
    s3_service.put_object(app_slug, key, content_type, data)
    return Response(status_code=204)


@router.get("/{bucket}")
async def list_bucket(bucket: str, request: Request) -> Response:
    if request.query_params.get("list-type") != "2":
        raise S3ApiError(400, "InvalidRequest", "Only list-type=2 (ListObjectsV2) is supported")

    auth_service = request.app.state.s3_auth_service
    s3_service = request.app.state.s3_service
    app_slug = _authenticate(request, auth_service)
    app_slug = s3_service.require_bucket_matches_app(bucket, app_slug)

    prefix = request.query_params.get("prefix", "")
    items = s3_service.list_objects(app_slug, prefix)
    return Response(content=s3_xml.list_bucket_result_xml(bucket, prefix, items), media_type="application/xml")


@router.head("/{bucket}/{key:path}")
async def head_object(bucket: str, key: str, request: Request) -> Response:
    auth_service = request.app.state.s3_auth_service
    s3_service = request.app.state.s3_service
    headers = dict(request.headers.items())
    query_params = list(request.query_params.multi_items())
    app_slug = auth_service.verify_header_auth(request.method, request.url.path, query_params, headers)
    app_slug = s3_service.require_bucket_matches_app(bucket, app_slug)

    item = s3_service.head_object(app_slug, key)
    return Response(
        status_code=200,
        media_type=item.content_type,
        headers={
            "Content-Length": str(item.size_bytes),
            "ETag": f'"{item.checksum_sha256}"',
            "Last-Modified": item.updated_at,
        },
    )


@router.get("/{bucket}/{key:path}")
async def get_object(bucket: str, key: str, request: Request) -> Response:
    auth_service = request.app.state.s3_auth_service
    s3_service = request.app.state.s3_service
    app_slug = _authenticate(request, auth_service)
    app_slug = s3_service.require_bucket_matches_app(bucket, app_slug)

    item = s3_service.get_object(app_slug, key)
    absolute_path = request.app.state.object_storage_adapter.absolute_path_for_item(item)
    data = absolute_path.read_bytes()
    return Response(
        content=data,
        media_type=item.content_type,
        headers={
            "ETag": f'"{item.checksum_sha256}"',
            "Last-Modified": item.updated_at,
        },
    )


@router.delete("/{bucket}/{key:path}")
async def delete_object(bucket: str, key: str, request: Request) -> Response:
    auth_service = request.app.state.s3_auth_service
    s3_service = request.app.state.s3_service
    headers = dict(request.headers.items())
    query_params = list(request.query_params.multi_items())
    app_slug = auth_service.verify_header_auth(request.method, request.url.path, query_params, headers)
    app_slug = s3_service.require_bucket_matches_app(bucket, app_slug)

    s3_service.delete_objects(app_slug, [key])
    return Response(status_code=204)


@router.put("/{bucket}/{key:path}")
async def put_object(bucket: str, key: str, request: Request) -> Response:
    auth_service = request.app.state.s3_auth_service
    s3_service = request.app.state.s3_service
    headers = dict(request.headers.items())
    query_params = list(request.query_params.multi_items())
    app_slug = auth_service.verify_header_auth(request.method, request.url.path, query_params, headers)
    app_slug = s3_service.require_bucket_matches_app(bucket, app_slug)

    copy_source = request.headers.get("x-amz-copy-source")
    if copy_source:
        source_path = unquote(copy_source).lstrip("/")
        _, _, source_key = source_path.partition("/")
        item = s3_service.copy_object(app_slug, source_key, key)
        return Response(content=s3_xml.copy_object_result_xml(item), media_type="application/xml")

    body = await request.body()
    content_type = request.headers.get("content-type", "application/octet-stream")
    item = s3_service.put_object(app_slug, key, content_type, body)
    return Response(status_code=200, headers={"ETag": f'"{item.checksum_sha256}"'})
