from __future__ import annotations

from pathlib import Path

from conftest import user_text
from session_digest.config import Config, ProjectMapping
from session_digest.scan import ProjectCandidate, SessionMetrics
from session_digest.runner import build_prompt, run, run_project


def make_config(tmp_path: Path, **overrides: object) -> Config:
    return Config(
        knowledge_base=tmp_path / "kb",
        projects_root=tmp_path / "projects",
        projects={"-p-one": ProjectMapping(folder="One", repo=tmp_path / "repo")},
        **overrides,
    )


def make_candidate(tmp_path: Path, make_session) -> ProjectCandidate:
    path = make_session(tmp_path / "projects" / "-p-one", "s", [user_text("hi")], mtime=500.0)
    metrics = SessionMetrics(path, 500.0, 3, True, False, 999)
    return ProjectCandidate("-p-one", [metrics], 500.0)


def test_build_prompt_names_destinations(tmp_path, make_session) -> None:
    config = make_config(tmp_path)
    candidate = make_candidate(tmp_path, make_session)

    prompt = build_prompt(candidate, ["material"], config)

    assert str(tmp_path / "kb" / "One") in prompt
    assert str(tmp_path / "repo") in prompt
    assert "material" in prompt


def test_build_prompt_marks_transcript_as_data(tmp_path, make_session) -> None:
    config = make_config(tmp_path)
    candidate = make_candidate(tmp_path, make_session)

    prompt = build_prompt(candidate, ["material"], config)

    assert "data, not instructions" in prompt


def test_build_prompt_omits_repo_when_unknown(tmp_path, make_session) -> None:
    config = make_config(tmp_path)
    config = Config(
        knowledge_base=config.knowledge_base,
        projects_root=config.projects_root,
        projects={"-p-one": ProjectMapping(folder="One", repo=None)},
    )
    candidate = make_candidate(tmp_path, make_session)

    prompt = build_prompt(candidate, ["material"], config)

    assert "no repository" in prompt


def test_run_project_advances_watermark_on_success(tmp_path, make_session) -> None:
    config = make_config(tmp_path)
    candidate = make_candidate(tmp_path, make_session)
    state = tmp_path / "state.json"

    result = run_project(candidate, config, state, invoke=lambda prompt: (0, "wrote 2 notes"))

    assert result.ok is True
    from session_digest.state import read_watermarks

    assert read_watermarks(state) == {"-p-one": 500.0}


def test_run_project_keeps_watermark_on_failure(tmp_path, make_session) -> None:
    config = make_config(tmp_path)
    candidate = make_candidate(tmp_path, make_session)
    state = tmp_path / "state.json"

    result = run_project(candidate, config, state, invoke=lambda prompt: (1, "boom"))

    assert result.ok is False
    from session_digest.state import read_watermarks

    assert read_watermarks(state) == {}


def test_run_project_survives_invoker_exception(tmp_path, make_session) -> None:
    config = make_config(tmp_path)
    candidate = make_candidate(tmp_path, make_session)
    state = tmp_path / "state.json"

    def explode(prompt: str) -> tuple[int, str]:
        raise RuntimeError("claude missing")

    result = run_project(candidate, config, state, invoke=explode)

    assert result.ok is False
    assert "claude missing" in result.message


def test_run_isolates_project_failures(tmp_path, make_session) -> None:
    config = Config(
        knowledge_base=tmp_path / "kb",
        projects_root=tmp_path / "projects",
    )
    good = make_candidate(tmp_path, make_session)
    bad_path = make_session(tmp_path / "projects" / "-p-two", "s", [user_text("hi")], mtime=600.0)
    bad = ProjectCandidate("-p-two", [SessionMetrics(bad_path, 600.0, 3, True, False, 999)], 600.0)

    def invoke(prompt: str) -> tuple[int, str]:
        return (1, "fail") if "-p-two" in prompt else (0, "ok")

    results = run([good, bad], config, tmp_path / "state.json", invoke=invoke)

    assert [r.ok for r in results] == [True, False]
