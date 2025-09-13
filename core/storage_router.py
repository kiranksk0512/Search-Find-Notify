import os
from core.logger import get_company_logger

logger = get_company_logger("storage_router")

if os.environ.get("STORAGE_BACKEND", "local").lower() == "s3":
    try:
        from core.storage_s3 import load_json, save_json
        logger.info("📦 Using S3 storage backend")
    except Exception as e:
        logger.warning(f"Falling back to local storage: {e}")
        from core.storage import load_json, save_json
else:
    from core.storage import load_json, save_json
    logger.info("💾 Using local file storage backend")
