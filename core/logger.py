import logging
import os
from datetime import datetime
from pathlib import Path
from core.context import current_company

def get_company_logger(company_name: str = None) -> logging.Logger:
    name = company_name or current_company.get()
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        # Always log to console (CloudWatch picks this up in Lambda)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        ))
        logger.addHandler(console_handler)

        # If running locally (not in Lambda), also log to file
        if not os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
            logs_dir = Path("logs")
            logs_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = logs_dir / f"{name}_{timestamp}.log"

            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(logging.Formatter(
                "%(asctime)s - %(levelname)s - %(message)s"
            ))
            logger.addHandler(file_handler)

    return logger
