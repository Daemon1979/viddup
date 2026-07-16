from pathlib import Path

import pytest

from viddup.config import ConfigError, load_config, resolve_defaults
from viddup.cli import build_parser, _explicit_repeated_values


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_config_precedence_user_then_local_then_explicit(tmp_path, monkeypatch):
    user = tmp_path / "user"
    work = tmp_path / "work"
    explicit = tmp_path / "custom.conf"
    work.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(user))
    monkeypatch.chdir(work)
    write(user / "viddup" / "viddup.conf", '[common]\ndb = "user.db"\nnice = 8\n')
    write(work / "viddup.conf", '[common]\ndb = "local.db"\n')
    write(explicit, '[common]\nnice = 2\n')

    config, loaded = load_config(str(explicit))

    assert config["common"] == {"db": "local.db", "nice": 2}
    assert loaded == [user / "viddup" / "viddup.conf", work / "viddup.conf", explicit]


def test_import_and_search_excludes_are_independent():
    config = {
        "import": {"exclude_dirs": ["Games"]},
        "search": {"exclude_dirs": ["Credits"], "profile": "precise"},
    }

    import_defaults, _ = resolve_defaults(config, None, import_mode=True, search_mode=False)
    search_defaults, profile = resolve_defaults(config, None, import_mode=False, search_mode=True)

    assert import_defaults["exclude_dir"] == ["Games"]
    assert "search_exclude_dir" not in import_defaults
    assert search_defaults["search_exclude_dir"] == ["Credits"]
    assert "exclude_dir" not in search_defaults
    assert search_defaults["verify_brightness"] is True
    assert profile == "precise"


def test_inactive_section_is_not_validated():
    config = {"import": {"future_import_option": True}, "search": {"profile": "balanced"}}

    defaults, _ = resolve_defaults(config, None, import_mode=False, search_mode=True)

    assert defaults["indexlength"] == 12


def test_unknown_key_in_active_section_is_rejected():
    with pytest.raises(ConfigError, match="unknown keys in search"):
        resolve_defaults({"search": {"typo": 1}}, None, import_mode=False, search_mode=True)


def test_custom_profile_overrides_builtin_profile():
    config = {"profiles": {"precise": {"brightness_correlation": 0.82}}}

    defaults, _ = resolve_defaults(config, "precise", import_mode=False, search_mode=True)

    assert defaults["indexlength"] == 12
    assert defaults["verify_brightness"] is True
    assert defaults["brightness_correlation"] == 0.82


def test_config_database_satisfies_required_cli_option():
    parser = build_parser({"db": "configured.db"})

    args = parser.parse_args(["--list-db-files"])

    assert args.db == "configured.db"


def test_cli_can_disable_brightness_from_precise_profile():
    defaults, _ = resolve_defaults({}, "precise", import_mode=False, search_mode=True)
    parser = build_parser(defaults)

    args = parser.parse_args(["--db", "videos.db", "--search", "--no-verify-brightness"])

    assert args.verify_brightness is False


def test_explicit_repeated_cli_values_replace_config_list():
    argv = ["--exclude-dir", "One", "--exclude-dir=Two"]

    assert _explicit_repeated_values(argv, "--exclude-dir") == ["One", "Two"]
