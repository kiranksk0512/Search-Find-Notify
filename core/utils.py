def diff_jobs(current: dict, previous: dict) -> dict:
    return {k: v for k, v in current.items() if k not in previous}
