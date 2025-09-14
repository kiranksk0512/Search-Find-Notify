import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List

import boto3
from botocore.exceptions import ClientError

# Keep parity with your config-driven approach
try:
    from config import COMPANY_VERSIONING, BACKUP_RETENTION_DAYS, S3_BUCKET, S3_PREFIX  # type: ignore
except Exception:
    # Fallbacks so it can still run if config is not wired in Lambda init yet
    import os
    COMPANY_VERSIONING = {}
    BACKUP_RETENTION_DAYS = int(os.environ.get("BACKUP_RETENTION_DAYS", "7"))
    S3_BUCKET = os.environ["S3_BUCKET"]
    S3_PREFIX = os.environ.get("S3_PREFIX", "scraper")

s3 = boto3.client("s3")


def _join(*parts: str) -> str:
    return "/".join(p.strip("/") for p in parts if p is not None and p != "")


def _latest_key(company_name: str) -> str:
    return _join(S3_PREFIX, f"{company_name}_jobs.json")


def _version_key(company_name: str, ts: str) -> str:
    # Matches local file naming: {company}_jobs_{YYYYmmdd_HHMMSS}.json
    return _join(S3_PREFIX, f"{company_name}_jobs_{ts}.json")


def load_json(company_name: str) -> Dict[str, Any]:
    """
    Load the latest snapshot for a company.
    Returns {} if not found (same as your local storage).
    """
    key = _latest_key(company_name)
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
        body = obj["Body"].read()
        return json.loads(body)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in ("NoSuchKey", "NoSuchBucket"):
            return {}
        raise
    except Exception:
        # If corrupt JSON or other issue, treat as empty (parity with simple local behavior)
        return {}


def save_json(company_name: str, data: Dict[str, Any], force_version: bool = False) -> None:
    """
    Save the latest snapshot and optionally a versioned backup.
    Mirrors:
      - 'latest' file write (company_jobs.json)
      - versioning if COMPANY_VERSIONING[company] or force_version
      - cleanup of old backups
    """
    body = json.dumps(data, indent=2).encode("utf-8")

    # 1) Save latest snapshot
    latest_key = _latest_key(company_name)
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=latest_key,
        Body=body,
        ContentType="application/json",
    )

    # 2) Versioned backup?
    should_version = bool(COMPANY_VERSIONING.get(company_name, False)) or bool(force_version)
    if should_version:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        ver_key = _version_key(company_name, ts)
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=ver_key,
            Body=body,
            ContentType="application/json",
        )
        # 3) Cleanup old backups
        cleanup_old_backups(company_name)


def cleanup_old_backups(company_name: str) -> None:
    """
    Delete versioned backups older than BACKUP_RETENTION_DAYS.
    Looks for keys like: {S3_PREFIX}/{company}_jobs_YYYYmmdd_HHMMSS.json
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=BACKUP_RETENTION_DAYS)
    prefix_for_versions = _join(S3_PREFIX, f"{company_name}_jobs_")  # list prefix up to timestamp

    # List all matching objects
    keys_to_delete: List[str] = []
    continuation = None
    while True: 
        kwargs = {
            "Bucket": S3_BUCKET,
            "Prefix": prefix_for_versions,
        }
        if continuation:
            kwargs["ContinuationToken"] = continuation
        resp = s3.list_objects_v2(**kwargs)

        contents = resp.get("Contents", [])
        for obj in contents:
            key = obj["Key"]
            # Expect filename like <prefix>/<company>_jobs_YYYYmmdd_HHMMSS.json
            name = key.rsplit("/", 1)[-1]
            # Extract timestamp
            try:
                # Remove company prefix and suffix to isolate the timestamp
                # name example: meta_jobs_20250819_120102.json
                # inside cleanup_old_backups(...)
                ts_str = name.replace(f"{company_name}_jobs_", "").replace(".json", "")
                file_time = datetime.strptime(ts_str, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)  # <-- add tzinfo
                if file_time < cutoff:
                    keys_to_delete.append(key)

            except Exception:
                # Ignore files that don't match the timestamp pattern
                continue

        if resp.get("IsTruncated"):
            continuation = resp.get("NextContinuationToken")
        else:
            break

    # Batch delete in groups of 1000
    for i in range(0, len(keys_to_delete), 1000):
        batch = keys_to_delete[i : i + 1000]
        if not batch:
            continue
        s3.delete_objects(
            Bucket=S3_BUCKET,
            Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True},
        )


# add helpers
def _aux_key(company_name: str, tag: str) -> str:
    # e.g. {S3_PREFIX}/microsoft_miss_counts.json
    return _join(S3_PREFIX, f"{company_name}_{tag}.json")

def load_aux_json(company_name: str, tag: str):
    key = _aux_key(company_name, tag)
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
        body = obj["Body"].read()
        return json.loads(body)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in ("NoSuchKey", "NoSuchBucket"):
            return {}
        raise
    except Exception:
        return {}

def save_aux_json(company_name: str, tag: str, data):
    key = _aux_key(company_name, tag)
    body = json.dumps(data, indent=2).encode("utf-8")
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=body,
        ContentType="application/json",
    )
