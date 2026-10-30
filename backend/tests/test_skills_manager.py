"""Tests for skills_manager.py — catalog, SQLite persistence, prompt injection."""

import sys
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skills_manager import (
    SKILLS_CATALOG,
    get_skill,
    get_skills_catalog,
    init_skills_table,
    get_skills_status,
    set_skill_enabled,
    get_active_skill_prompts,
)


# ═══════════════════════════════════════════════════════════════
# Catalog integrity
# ═══════════════════════════════════════════════════════════════

class TestSkillsCatalog:
    """The SKILLS_CATALOG must have all required fields for each skill."""

    def test_catalog_has_expected_skills(self):
        names = {s["name"] for s in SKILLS_CATALOG}
        expected = {"debug", "tdd", "security", "review", "batch", "scheduled_automation", "rtk", "programming"}
        assert names == expected, f"Missing: {expected - names}, Extra: {names - expected}"

    def test_each_skill_has_required_fields(self):
        for skill in SKILLS_CATALOG:
            assert "name" in skill, f"{skill} missing 'name'"
            assert "display_name" in skill, f"{skill} missing 'display_name'"
            assert "description" in skill, f"{skill} missing 'description'"
            assert "triggers" in skill, f"{skill} missing 'triggers'"
            assert isinstance(skill["triggers"], list), f"{skill} triggers not a list"
            assert len(skill["triggers"]) > 0, f"{skill} has empty triggers"

    def test_skill_content_loaded_from_file(self):
        for skill in SKILLS_CATALOG:
            s = get_skill(skill["name"])
            assert s is not None, f"{skill['name']} not found by get_skill()"
            assert "content" in s, f"{skill['name']} missing 'content'"
            content = s["content"]
            assert isinstance(content, str), f"{skill['name']} content not a string"
            assert len(content) > 200, (
                f"{skill['name']} content too short ({len(content)} chars)"
            )

    def test_get_skills_catalog_loads_all_content(self):
        catalog = get_skills_catalog()
        assert len(catalog) == len(SKILLS_CATALOG)
        for s in catalog:
            assert len(s.get("content", "")) > 200

    def test_unknown_skill_returns_none(self):
        assert get_skill("nonexistent_skill") is None


# ═══════════════════════════════════════════════════════════════
# SQLite integration
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def skills_db():
    """Create a temporary SQLite DB with the skills table initialized."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
    try:
        init_skills_table(conn)
        yield conn
    finally:
        conn.close()
        try:
            os.unlink(db_path)
        except OSError:
            pass


class TestSkillsSQLite:
    """Skills table CRUD operations."""

    def test_init_creates_all_rows(self, skills_db):
        status = get_skills_status(skills_db)
        assert len(status) == len(SKILLS_CATALOG)
        names = {s["name"] for s in status}
        assert "debug" in names
        assert "batch" in names
        assert "scheduled_automation" in names

    def test_all_skills_start_disabled(self, skills_db):
        status = get_skills_status(skills_db)
        assert all(not s["enabled"] for s in status)

    def test_enable_skill(self, skills_db):
        set_skill_enabled(skills_db, "batch", True)
        status = get_skills_status(skills_db)
        batch = next(s for s in status if s["name"] == "batch")
        assert batch["enabled"] is True

    def test_disable_skill(self, skills_db):
        set_skill_enabled(skills_db, "tdd", True)
        set_skill_enabled(skills_db, "tdd", False)
        status = get_skills_status(skills_db)
        tdd = next(s for s in status if s["name"] == "tdd")
        assert tdd["enabled"] is False

    def test_toggle_multiple_skills(self, skills_db):
        set_skill_enabled(skills_db, "debug", True)
        set_skill_enabled(skills_db, "review", True)
        set_skill_enabled(skills_db, "batch", True)
        status = get_skills_status(skills_db)
        enabled = [s for s in status if s["enabled"]]
        assert len(enabled) == 3


# ═══════════════════════════════════════════════════════════════
# Prompt injection
# ═══════════════════════════════════════════════════════════════

class TestActiveSkillPrompts:
    """get_active_skill_prompts() returns the full prompt text for enabled skills."""

    def test_no_active_skills_returns_empty(self, skills_db):
        prompts = get_active_skill_prompts(skills_db)
        assert prompts == []

    def test_one_active_skill_returns_its_prompt(self, skills_db):
        set_skill_enabled(skills_db, "debug", True)
        prompts = get_active_skill_prompts(skills_db)
        assert len(prompts) == 1
        assert "SKILL: Debug" in prompts[0]

    def test_multiple_active_skills_return_all_prompts(self, skills_db):
        for name in ["debug", "tdd", "batch"]:
            set_skill_enabled(skills_db, name, True)
        prompts = get_active_skill_prompts(skills_db)
        assert len(prompts) == 3
        assert any("SKILL: Debug" in p for p in prompts)
        assert any("SKILL: TDD" in p for p in prompts)
        assert any("SKILL: Batch" in p for p in prompts)

    def test_inactive_skills_not_included(self, skills_db):
        set_skill_enabled(skills_db, "debug", True)
        set_skill_enabled(skills_db, "security", False)
        prompts = get_active_skill_prompts(skills_db)
        names = []
        for p in prompts:
            import re
            m = re.search(r"SKILL: (.+?) ===", p)
            if m:
                names.append(m.group(1).strip())
        assert "Debug" in names
        assert "Security Review" not in names
