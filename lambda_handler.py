# lambda_handler.py
import os, sys, asyncio

# import the async main() from your CLI module
from main import main as cli_main

def handler(event, context):
    """
    Map EventBridge/Lambda inputs to your existing argparse flags.
    Precedence: event JSON > environment vars > argparse defaults.
    """
    argv = ["main.py"]  # argv[0] is program name

    # --- EventBridge / Invoke payload (preferred) ---
    # Example event: {"company":"meta","force_version":true,"no_email":true}
    company = (event or {}).get("company")
    if not company:
        # allow an env default (e.g., run only one company on this function)
        company = os.environ.get("DEFAULT_COMPANY")
    if company:
        argv += ["--company", company]

    if (event or {}).get("force_version") or os.environ.get("FORCE_VERSION_DEFAULT") == "1":
        argv += ["--force-version"]

    # You named the flag --no-email; keep semantics:
    if (event or {}).get("no_email") or os.environ.get("NO_EMAIL_DEFAULT") == "1":
        argv += ["--no-email"]

    # Make argparse in main.py see these flags
    sys.argv = argv

    # Run your original async entrypoint
    return asyncio.run(cli_main())
