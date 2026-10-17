"""Coordinate the deterministic profile projection through its repository adapter.

The producer passes its existing owner transaction; no additional commit is opened.
"""
from app.student_profile.repositories.learning_projection import POLICY, project_learning_profile

__all__ = ['POLICY', 'project_learning_profile']
