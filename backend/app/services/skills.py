"""Compatibility exports; the shared vocabulary lives in the pure tailoring package."""

from app.tailoring.skills import UserSkills, canonical_skill, skill_gaps, user_skills

__all__ = ["UserSkills", "canonical_skill", "skill_gaps", "user_skills"]
