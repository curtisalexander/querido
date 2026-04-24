import json
from pathlib import Path

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_agent_list_shows_installable_targets() -> None:
    result = runner.invoke(app, ["agent", "list"])
    assert result.exit_code == 0
    assert "skill" in result.output
    assert "continue" in result.output
    assert "installable" in result.output
    assert "reference" in result.output


def test_agent_list_json_marks_installable_targets() -> None:
    result = runner.invoke(app, ["-f", "json", "agent", "list"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    targets = {target["name"]: target for target in payload["data"]["targets"]}
    assert targets["skill"]["kind"] == "installable"
    assert targets["skill"]["installable"] is True
    assert targets["workflow-authoring"]["kind"] == "reference"
    assert targets["workflow-authoring"]["installable"] is False


def test_agent_show_prints_skill_content() -> None:
    result = runner.invoke(app, ["agent", "show", "skill"])
    assert result.exit_code == 0
    assert "Using querido (qdo)" in result.output
    assert "WORKFLOW_AUTHORING.md" in result.output


def test_agent_install_skill_writes_skill_directory(tmp_path: Path) -> None:
    destination = tmp_path / "skills" / "querido"
    result = runner.invoke(app, ["agent", "install", "skill", "--path", str(destination)])
    assert result.exit_code == 0
    assert (destination / "SKILL.md").read_text().startswith("---")
    assert (destination / "WORKFLOW_AUTHORING.md").exists()
    assert (destination / "WORKFLOW_EXAMPLES.md").exists()


def test_agent_install_continue_writes_rule_file(tmp_path: Path) -> None:
    destination = tmp_path / ".continue" / "rules"
    result = runner.invoke(app, ["agent", "install", "continue", "--path", str(destination)])
    assert result.exit_code == 0
    assert "Using querido (qdo)" in (destination / "qdo.md").read_text()


def test_agent_install_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    destination = tmp_path / "skills" / "querido"
    destination.mkdir(parents=True)
    (destination / "SKILL.md").write_text("custom")

    result = runner.invoke(app, ["agent", "install", "skill", "--path", str(destination)])

    assert result.exit_code != 0
    assert (destination / "SKILL.md").read_text() == "custom"


def test_agent_install_force_overwrites(tmp_path: Path) -> None:
    destination = tmp_path / "skills" / "querido"
    destination.mkdir(parents=True)
    (destination / "SKILL.md").write_text("custom")

    result = runner.invoke(
        app, ["agent", "install", "skill", "--path", str(destination), "--force"]
    )

    assert result.exit_code == 0
    assert "Using querido (qdo)" in (destination / "SKILL.md").read_text()
