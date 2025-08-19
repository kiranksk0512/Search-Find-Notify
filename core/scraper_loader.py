import importlib
import pkgutil
import inspect
from scrapers import __path__ as scrapers_path

def discover_scrapers():
    scraper_map = {}
    for _, module_name, _ in pkgutil.iter_modules(scrapers_path):
        module = importlib.import_module(f"scrapers.{module_name}")
        get_jobs = getattr(module, "get_jobs", None)
        if get_jobs and inspect.iscoroutinefunction(get_jobs):
            scraper_map[module_name] = get_jobs
    return scraper_map
