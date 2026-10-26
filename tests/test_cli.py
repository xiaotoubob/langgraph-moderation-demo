import json
import subprocess
import sys


def cli(*args, check=True):
    return subprocess.run(
        [sys.executable, "-m", "moderation_demo.cli", *map(str, args)],
        capture_output=True,
        text=True,
        timeout=30,
        check=check,
    )


def test_pause_exit_and_resume_from_another_process(tmp_path):
    db = tmp_path / "demo.sqlite"
    paused = json.loads(
        cli(
            "run",
            "--case",
            "threat-direct",
            "--thread",
            "a",
            "--db",
            db,
            "--pause-before",
            "validate",
        ).stdout
    )
    assert paused["paused"] is True
    assert paused["next"] == ["validate"]
    assert paused["result"] is None
    completed = json.loads(cli("resume", "--thread", "a", "--db", db).stdout)
    assert completed["paused"] is False
    assert completed["result"]["decision"] == "VIOLATION"
    assert completed["model_calls"] == paused["model_calls"] == 4
    assert completed["message_count"] == paused["message_count"]
    history = json.loads(cli("history", "--thread", "a", "--db", db, "--messages").stdout)
    assert history[-1]["status"] == "completed"
    assert any(item["next"] == ["validate"] for item in history)
    assert history[-1]["messages"]
    # A second thread cannot overwrite the first one, even from another process.
    other = json.loads(
        cli(
            "run",
            "--case",
            "privacy-unclear",
            "--thread",
            "b",
            "--db",
            db,
        ).stdout
    )
    assert other["result"]["decision"] == "NEEDS_REVIEW"
    again = json.loads(cli("history", "--thread", "a", "--db", db).stdout)
    assert again[-1]["result"]["decision"] == "VIOLATION"


def test_reusing_thread_or_resuming_terminal_thread_has_clear_error(tmp_path):
    db = tmp_path / "demo.sqlite"
    cli("run", "--thread", "a", "--db", db)
    reused = cli("run", "--thread", "a", "--db", db, check=False)
    assert reused.returncode == 2
    assert "already exists" in reused.stderr
    resumed = cli("resume", "--thread", "a", "--db", db, check=False)
    assert resumed.returncode == 2
    assert "already terminal" in resumed.stderr


def test_checkpoint_lab_is_a_separate_command(tmp_path):
    output = json.loads(cli("lab", "--db", tmp_path / "lab.sqlite", "--thread", "lab").stdout)
    stages = [step for step in output["history"] if step["status"] in ("drafted", "revised")]
    assert [step["result"] for step in stages] == ["draft result", "revised result"]
    assert all(step["message_count"] == 1 for step in stages)


def test_local_backend_needs_actual_model_name(tmp_path, monkeypatch):
    monkeypatch.delenv("MODERATION_MODEL", raising=False)
    output = cli("run", "--backend", "local", "--db", tmp_path / "local.sqlite", check=False)
    assert output.returncode == 2
    assert "MODERATION_MODEL" in output.stderr


def test_custom_input_cannot_silently_use_reference_replay(tmp_path):
    output = cli("run", "--text", "自定义内容", "--db", tmp_path / "demo.sqlite", check=False)
    assert output.returncode == 2
    assert "requires --backend local" in output.stderr
