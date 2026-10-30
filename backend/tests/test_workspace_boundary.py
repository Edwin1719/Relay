"""Frontera del workspace: nada fuera de la raíz es accesible.

Regresión que previene: la comprobación por prefijo de texto aceptaba una
carpeta vecina cuyo nombre empieza igual (``proyecto-evil`` vs ``proyecto``),
porque ``"C:\\...\\proyecto-evil"`` empieza por ``"C:\\...\\proyecto"``.
"""

import os

import pytest

from agent_core import is_within_root
from agent_factory import _read_files_batch


@pytest.fixture
def layout(tmp_path):
    """``proyecto/`` (raíz) y ``proyecto-evil/`` (vecina con un secreto)."""
    root = tmp_path / "proyecto"
    sibling = tmp_path / "proyecto-evil"
    root.mkdir()
    sibling.mkdir()
    (root / "dentro.txt").write_text("contenido", encoding="utf-8")
    (sibling / "secreto.txt").write_text("NO-DEBE-LEERSE", encoding="utf-8")
    return root, sibling


def test_inside_root(layout):
    root, _ = layout
    assert is_within_root(root, root / "dentro.txt")


def test_root_itself(layout):
    root, _ = layout
    assert is_within_root(root, root)


def test_sibling_prefix_rejected(layout):
    root, sibling = layout
    assert not is_within_root(root, sibling / "secreto.txt")


def test_parent_escape_rejected(layout, tmp_path):
    root, _ = layout
    outside = tmp_path / "fuera.txt"
    outside.write_text("NO-DEBE-LEERSE", encoding="utf-8")
    assert not is_within_root(root, outside)
    assert not is_within_root(root, root / ".." / "fuera.txt")


def test_nonexistent_inside_path_is_still_inside(layout):
    """write_file necesita validar rutas que aún no existen."""
    root, _ = layout
    assert is_within_root(root, root / "nuevo" / "archivo.txt")


@pytest.mark.skipif(os.name != "nt", reason="solo Windows normaliza mayúsculas")
def test_case_variation_is_inside(layout):
    root, _ = layout
    assert is_within_root(root, str(root).upper() + os.sep + "DENTRO.TXT")


def test_read_files_batch_rejects_sibling_prefix(layout):
    root, _ = layout
    out = _read_files_batch({"paths": ["../proyecto-evil/secreto.txt"]}, root)
    assert "path escapes workspace boundary" in out
    assert "NO-DEBE-LEERSE" not in out


def test_read_files_batch_reads_inside(layout):
    root, _ = layout
    out = _read_files_batch({"paths": ["dentro.txt"]}, root)
    assert "contenido" in out
