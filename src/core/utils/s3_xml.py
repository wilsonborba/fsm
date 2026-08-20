from __future__ import annotations

from typing import List
from xml.sax.saxutils import escape

from src.domain.models.object_models import ObjectItem


def error_xml(code: str, message: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Error>"
        f"<Code>{escape(code)}</Code>"
        f"<Message>{escape(message)}</Message>"
        "</Error>"
    )


def list_bucket_result_xml(bucket: str, prefix: str, items: List[ObjectItem]) -> str:
    contents = "".join(
        "<Contents>"
        f"<Key>{escape(item.key)}</Key>"
        f"<LastModified>{escape(item.updated_at)}</LastModified>"
        f'<ETag>"{item.checksum_sha256}"</ETag>'
        f"<Size>{item.size_bytes}</Size>"
        "<StorageClass>STANDARD</StorageClass>"
        "</Contents>"
        for item in items
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        f"<Name>{escape(bucket)}</Name>"
        f"<Prefix>{escape(prefix)}</Prefix>"
        f"<KeyCount>{len(items)}</KeyCount>"
        "<MaxKeys>1000</MaxKeys>"
        "<IsTruncated>false</IsTruncated>"
        f"{contents}"
        "</ListBucketResult>"
    )


def delete_result_xml(deleted_keys: List[str]) -> str:
    deleted = "".join(f"<Deleted><Key>{escape(key)}</Key></Deleted>" for key in deleted_keys)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<DeleteResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        f"{deleted}"
        "</DeleteResult>"
    )


def copy_object_result_xml(item: ObjectItem) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<CopyObjectResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        f"<LastModified>{escape(item.updated_at)}</LastModified>"
        f'<ETag>"{item.checksum_sha256}"</ETag>'
        "</CopyObjectResult>"
    )
