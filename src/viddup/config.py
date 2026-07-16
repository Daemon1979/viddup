from __future__ import annotations

import os
import tomllib
from pathlib import Path


BUILTIN_PROFILES = {
    "balanced": {
        "indexlength": 12,
        "radius": 3.0,
        "verify_brightness": False,
        "brightness_correlation": 0.70,
    },
    "precise": {
        "indexlength": 12,
        "radius": 3.0,
        "verify_brightness": True,
        "brightness_correlation": 0.70,
    },
    "sensitive": {
        "indexlength": 10,
        "radius": 3.0,
        "verify_brightness": False,
        "brightness_correlation": 0.70,
    },
}

COMMON_KEYS = {"db", "nice", "knnlib"}
IMPORT_KEYS = {"numjobs", "exclude_dirs", "vidext"}
SEARCH_KEYS = {
    "profile",
    "exclude_dirs",
    "ignore_start",
    "ignore_end",
    "indexlength",
    "scenelength",
    "radius",
    "verify_brightness",
    "brightness_correlation",
    "step",
    "fixspeed",
    "knnlib",
}
PROFILE_KEYS = {
    "indexlength",
    "scenelength",
    "radius",
    "verify_brightness",
    "brightness_correlation",
    "step",
    "fixspeed",
    "knnlib",
}


class ConfigError(ValueError):
    pass


def default_config_paths() -> list[Path]:
    user_config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "viddup" / "viddup.conf"
    return [user_config, Path.cwd() / "viddup.conf"]


def load_config(explicit_path: str | None = None) -> tuple[dict, list[Path]]:
    merged: dict = {}
    loaded = []
    paths = default_config_paths()
    if explicit_path:
        paths.append(Path(explicit_path).expanduser())

    for path in paths:
        if not path.is_file():
            if explicit_path and path == paths[-1]:
                raise ConfigError(f"config file not found: {path}")
            continue
        try:
            with path.open("rb") as handle:
                data = tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"invalid TOML in {path}: {exc}") from exc
        _merge(merged, data)
        loaded.append(path)
    return merged, loaded


def resolve_defaults(config: dict, profile_name: str | None, import_mode: bool, search_mode: bool) -> tuple[dict, str]:
    _validate_table(config, "common", COMMON_KEYS)
    defaults = dict(config.get("common", {}))

    if import_mode:
        _validate_table(config, "import", IMPORT_KEYS)
        import_values = dict(config.get("import", {}))
        if "exclude_dirs" in import_values:
            import_values["exclude_dir"] = _string_list(import_values.pop("exclude_dirs"), "import.exclude_dirs")
        defaults.update(import_values)

    search_values = dict(config.get("search", {})) if search_mode else {}
    selected_profile = profile_name or search_values.pop("profile", None) or "balanced"
    if search_mode:
        _validate_table(config, "search", SEARCH_KEYS)
        profiles = {name: dict(values) for name, values in BUILTIN_PROFILES.items()}
        configured_profiles = config.get("profiles", {})
        if not isinstance(configured_profiles, dict):
            raise ConfigError("profiles must be a TOML table")
        for name, values in configured_profiles.items():
            if not isinstance(values, dict):
                raise ConfigError(f"profiles.{name} must be a TOML table")
            unknown = set(values) - PROFILE_KEYS
            if unknown:
                raise ConfigError(f"unknown keys in profiles.{name}: {', '.join(sorted(unknown))}")
            profiles.setdefault(name, {}).update(values)
        if selected_profile not in profiles:
            raise ConfigError(f"unknown search profile: {selected_profile}")
        defaults.update(profiles[selected_profile])
        if "exclude_dirs" in search_values:
            search_values["search_exclude_dir"] = _string_list(
                search_values.pop("exclude_dirs"), "search.exclude_dirs"
            )
        defaults.update(search_values)

    return defaults, selected_profile


def _validate_table(config: dict, name: str, allowed: set[str]) -> None:
    values = config.get(name, {})
    if not isinstance(values, dict):
        raise ConfigError(f"{name} must be a TOML table")
    unknown = set(values) - allowed
    if unknown:
        raise ConfigError(f"unknown keys in {name}: {', '.join(sorted(unknown))}")


def _string_list(value, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{name} must be an array of strings")
    return value


def _merge(target: dict, source: dict) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = value
