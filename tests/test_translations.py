"""The integration's translation files have the same keys."""

import json
from pathlib import Path

FOLDER = Path(__file__).parent.parent / "custom_components" / "fmi_open_data" / "translations"


def _keys(table: dict, prefix: str = "") -> set[str]:
    return {
        key
        for name, value in table.items()
        for key in (_keys(value, f"{prefix}{name}.") if isinstance(value, dict) else {f"{prefix}{name}"})
    }


def test_every_language_has_the_same_keys_as_english():
    english = _keys(json.loads((FOLDER / "en.json").read_text(encoding="utf-8")))
    for path in FOLDER.glob("*.json"):
        assert _keys(json.loads(path.read_text(encoding="utf-8"))) == english, path.name
