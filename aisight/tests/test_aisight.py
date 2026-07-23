"""aisight is the command you run when you are leaving. Everything here
pins a way it could take something it should not."""

import json

import pytest

from aisight import TOOLS
from aisight.cli import main
from aisight.clean import Plan, is_checkout, make_plan, run


def make_checkout(root):
    """A convincing AISight working copy."""
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": "aisight", "plugins": []}), encoding="utf-8")
    for t in TOOLS:
        (root / t).mkdir()
        (root / t / "pyproject.toml").write_text("[project]\n",
                                                 encoding="utf-8")
    return root


def test_a_checkout_is_recognised(tmp_path):
    assert is_checkout(make_checkout(tmp_path / "AISight"))


def test_a_home_directory_is_not_a_checkout(tmp_path):
    """--repo ~ would be a very bad afternoon."""
    assert not is_checkout(tmp_path)
    # a directory with the right name and nothing else must NOT pass
    (tmp_path / "AISight").mkdir()
    assert not is_checkout(tmp_path / "AISight")
    # nor another project's marketplace that happens to sit there
    other = tmp_path / "other"
    (other / ".claude-plugin").mkdir(parents=True)
    (other / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": "somebody-else", "plugins": []}), encoding="utf-8")
    assert not is_checkout(other)
    # and neither does ours with a tool folder missing
    half = make_checkout(tmp_path / "half")
    (half / "pcbsight" / "pyproject.toml").unlink()
    assert not is_checkout(half)


def test_uninstall_refuses_a_path_that_is_not_a_checkout(tmp_path, capsys):
    code = main(["uninstall", "--repo", str(tmp_path), "-y"])
    assert code == 2
    assert "refusing to delete it" in capsys.readouterr().err
    assert tmp_path.exists()


def test_dry_run_touches_nothing(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    (home / ".claude" / "skills" / "solidsight").mkdir(parents=True)
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    code = main(["uninstall", "--dry-run"])
    assert code == 0
    assert "dry run" in capsys.readouterr().out
    assert (home / ".claude" / "skills" / "solidsight").is_dir()


def test_only_one_tool_leaves_the_others_and_the_plugin(tmp_path, monkeypatch):
    home = tmp_path / "home"
    skills = home / ".claude" / "skills"
    for t in TOOLS:
        (skills / t).mkdir(parents=True)
    mk = home / ".claude" / "plugins" / "marketplaces" / "aisight"
    mk.mkdir(parents=True)
    monkeypatch.setattr("pathlib.Path.home", lambda: home)

    assert main(["uninstall", "--only", "solidsight", "--keep-packages",
                 "-y"]) == 0
    assert not (skills / "solidsight").exists()
    for t in TOOLS[1:]:
        assert (skills / t).is_dir(), f"{t} was not asked for"
    assert mk.is_dir(), "the marketplace belongs to the family, not one tool"


def test_unregistering_leaves_other_marketplaces_alone(tmp_path, monkeypatch):
    home = tmp_path / "home"
    plugins = home / ".claude" / "plugins"
    (plugins / "marketplaces" / "aisight").mkdir(parents=True)
    reg = plugins / "known_marketplaces.json"
    reg.write_text(json.dumps({"aisight": {"a": 1},
                               "claude-plugins-official": {"b": 2}}),
                   encoding="utf-8")
    monkeypatch.setattr("pathlib.Path.home", lambda: home)

    run(make_plan(packages=False), say=lambda *_: None)
    left = json.loads(reg.read_text(encoding="utf-8"))
    assert "aisight" not in left
    assert "claude-plugins-official" in left, "we only remove our own"


def test_pip_is_never_run_behind_your_back(tmp_path, monkeypatch):
    """--keep-packages means keep them: no pip subprocess at all."""
    calls = []
    monkeypatch.setattr("subprocess.call", lambda *a, **k: calls.append(a))
    plan = Plan(skills=[], packages=["solidsight"])
    run(plan, say=lambda *_: None, pip=False)
    assert calls == []


def test_an_unknown_tool_is_rejected(capsys):
    assert main(["uninstall", "--only", "blendersight", "-y"]) == 2
    assert "not an AISight tool" in capsys.readouterr().err


def test_status_runs_without_anything_installed(tmp_path, monkeypatch,
                                                capsys):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert main(["status"]) == 0
    assert "solidsight" in capsys.readouterr().out


def test_nothing_installed_is_not_an_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert main(["uninstall", "--keep-packages", "-y"]) == 0
    assert "nothing to remove" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [[], ["--help"]])
def test_bare_invocation_prints_help(argv, capsys):
    try:
        main(argv)
    except SystemExit:
        pass
    assert "uninstall" in capsys.readouterr().out


def test_installing_aisight_installs_the_family():
    """`pip install aisight` has to bring the five tools with it, or
    `aisight uninstall` would be a command for removing nothing.
    User: 'pip install aisight deberia hacer pip install (individuales)'."""
    import pathlib
    import re
    txt = (pathlib.Path(__file__).parents[1] / "pyproject.toml") \
        .read_text(encoding="utf-8")
    deps = re.search(r"dependencies = \[(.*?)\]", txt, re.S).group(1)
    for t in TOOLS:
        assert re.search(rf'"{t}>=', deps), f"{t} is not a dependency"
