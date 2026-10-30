"""La raíz del workspace es siempre la carpeta seleccionada.

Regresión que previene: ``WorkspaceContext.build()`` derivaba la raíz de
``git rev-parse --show-toplevel``. Si un ancestro tenía ``.git`` (por ejemplo
el home del usuario), la raíz pasaba a ser ese ancestro: el sandbox se
ampliaba y las sesiones y ``KODAMA_MEMORY.md`` se escribían fuera del proyecto.
"""

import shutil
import subprocess

import pytest

from agent_core import WorkspaceContext
from agent_factory import create_agent


@pytest.fixture
def nested_project(tmp_path):
    """``repo/`` con un ``.git`` y, dentro, ``repo/proyecto/``."""
    if shutil.which("git") is None:
        pytest.skip("git no está disponible")
    repo = tmp_path / "repo"
    project = repo / "proyecto"
    project.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "-q", str(repo)],
        check=True,
        capture_output=True,
    )
    return repo, project


def test_root_is_the_selected_folder_not_the_git_toplevel(nested_project):
    repo, project = nested_project
    workspace = WorkspaceContext.build(str(project))

    assert workspace.cwd == str(project.resolve())
    assert workspace.repo_root == str(project.resolve())


def test_git_metadata_still_comes_from_the_enclosing_repo(nested_project):
    repo, project = nested_project
    workspace = WorkspaceContext.build(str(project))

    # Repo recién inicializado y carpeta vacía: sin cambios ni commits.
    assert workspace.status == "clean"
    assert workspace.recent_commits == []


def test_agent_stores_sessions_and_memory_inside_the_project(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    project = tmp_path / "proyecto"
    project.mkdir()

    agent = create_agent(cwd=str(project))

    assert agent.root == project.resolve()
    assert str(agent.session_path).startswith(str(project.resolve()))
    assert (project / "KODAMA_MEMORY.md").exists()
