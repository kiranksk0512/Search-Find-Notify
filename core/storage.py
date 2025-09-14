import json
from pathlib import Path
from datetime import datetime, timedelta
from config import BASE_DATA_PATH, COMPANY_VERSIONING, BACKUP_RETENTION_DAYS

def load_json(company_name):
    path = Path(BASE_DATA_PATH) / f"{company_name}_jobs.json"
    if not path.exists():
        return {}
    with open(path, "r") as f:
        return json.load(f)

def save_json(company_name, data, force_version=False):
    Path(BASE_DATA_PATH).mkdir(parents=True, exist_ok=True)

    # Save latest snapshot
    main_path = Path(BASE_DATA_PATH) / f"{company_name}_jobs.json"
    with open(main_path, "w") as f:
        json.dump(data, f, indent=2)

    # Use either config or override
    should_version = COMPANY_VERSIONING.get(company_name, False) or force_version
    if should_version:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        version_path = Path(BASE_DATA_PATH) / f"{company_name}_jobs_{timestamp}.json"
        with open(version_path, "w") as vf:
            json.dump(data, vf, indent=2)

        # Optional cleanup of old backups
        cleanup_old_backups(company_name)

def cleanup_old_backups(company_name):
    cutoff = datetime.now() - timedelta(days=BACKUP_RETENTION_DAYS)
    prefix = f"{company_name}_jobs_"
    for file in Path(BASE_DATA_PATH).glob(f"{prefix}*.json"):
        try:
            ts_str = file.stem.replace(prefix, "")
            file_time = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
            if file_time < cutoff:
                file.unlink()
        except Exception:
            continue


# add at bottom
def load_aux_json(company_name: str, tag: str):
    """
    Load a sidecar JSON for a company, e.g. miss counts.
    Stored as {BASE_DATA_PATH}/{company}_{tag}.json
    """
    path = Path(BASE_DATA_PATH) / f"{company_name}_{tag}.json"
    if not path.exists():
        return {}
    with open(path, "r") as f:
        return json.load(f)

def save_aux_json(company_name: str, tag: str, data):
    """
    Save a sidecar JSON for a company, e.g. miss counts.
    """
    Path(BASE_DATA_PATH).mkdir(parents=True, exist_ok=True)
    path = Path(BASE_DATA_PATH) / f"{company_name}_{tag}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
