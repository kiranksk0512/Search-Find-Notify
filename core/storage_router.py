import os
from core.logger import get_company_logger

logger = get_company_logger("storage_router")

if os.environ.get("STORAGE_BACKEND", "local").lower() == "s3":
    try:
        from core.storage_s3 import load_json, save_json
        logger.info("📦 Using S3 storage backend")
    except Exception as e1:
        logger.warning(f"Falling back to local storage for JSON: {e1}")
        from core.storage import load_json, save_json

    try:
        from core.storage_s3 import load_aux_json, save_aux_json  # type: ignore
    except Exception as e2:
        logger.warning(f"Falling back to local storage for AUX JSON: {e2}")
        from core.storage import load_aux_json, save_aux_json  # type: ignore

else:
    from core.storage import load_json, save_json
    from core.storage import load_aux_json, save_aux_json
    logger.info("💾 Using local file storage backend")
