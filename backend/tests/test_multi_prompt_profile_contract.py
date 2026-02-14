import ast
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "dags" / "modules" / "update" / "multi_summary_config.json"
ENUMS_PATH = REPO_ROOT / "backend" / "app" / "core" / "enums.py"


def _load_config():
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _extract_summary_style_values():
    source = ENUMS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    summary_style_values = set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "SummaryStyle":
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and stmt.targets and isinstance(stmt.targets[0], ast.Name):
                    if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                        summary_style_values.add(stmt.value.value)
            break

    return summary_style_values


def test_multi_summary_config_exists():
    assert CONFIG_PATH.exists(), f"missing config: {CONFIG_PATH}"


def test_prompt_profiles_contract():
    cfg = _load_config()
    profiles = cfg.get("prompt_profiles")

    assert isinstance(profiles, list) and profiles, "prompt_profiles must be a non-empty list"

    styles = []
    for p in profiles:
        assert isinstance(p, dict), "each profile must be an object"
        assert p.get("style"), "profile.style is required"
        assert isinstance(p.get("system_prompt"), list) and p.get("system_prompt"), "system_prompt must be non-empty list"
        assert isinstance(p.get("user_prompt_template"), list) and p.get("user_prompt_template"), "user_prompt_template must be non-empty list"

        text = "\n".join(p["user_prompt_template"])
        assert "{title}" in text, f"style={p['style']} missing {{title}} placeholder"
        assert "{abstract}" in text, f"style={p['style']} missing {{abstract}} placeholder"

        output_format = p.get("output_format", "json")
        assert output_format in {"json", "delimited"}, f"style={p['style']} invalid output_format={output_format}"

        if output_format == "delimited":
            assert "###TITLE###" in text, f"style={p['style']} missing ###TITLE### marker"
            assert "###HOOK###" in text, f"style={p['style']} missing ###HOOK### marker"
            assert "###SUMMARY###" in text, f"style={p['style']} missing ###SUMMARY### marker"

        styles.append(p["style"])

    assert len(styles) == len(set(styles)), "profile style values must be unique"


def test_prompt_styles_must_exist_in_backend_summary_enum():
    cfg = _load_config()
    profile_styles = {p["style"] for p in cfg.get("prompt_profiles", []) if p.get("style")}
    enum_styles = _extract_summary_style_values()

    assert enum_styles, "could not parse SummaryStyle enum values"
    missing = sorted(profile_styles - enum_styles)
    assert not missing, (
        "styles in multi_summary_config.json are missing in backend SummaryStyle enum: "
        + ", ".join(missing)
    )
