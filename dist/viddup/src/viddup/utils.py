import time


def format_duration(seconds: float) -> str:
    return time.strftime("%H:%M:%S", time.gmtime(seconds))


def parse_extensions(value: str) -> set[str]:
    return {item.strip().lower().lstrip(".") for item in value.split(",") if item.strip()}
