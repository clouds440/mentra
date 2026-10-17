"""Compatibility facade for the chat assessment persistence adapter."""
from .repositories.chat import ChatAssessmentRepository as ChatAssessments

__all__ = ['ChatAssessments']
