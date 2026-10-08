def create_history_management(sessions, llm, profile=None):
    from app.chat.repositories.postgres import ChatRepository
    from app.chat.repositories.history_reader import ChatReadFacade
    from .repositories.postgres import MemoryRepository
    from .memory.validation import MemoryValidator
    from .service import HistoryManagement
    from app.core.config import settings
    return HistoryManagement(MemoryRepository(sessions, settings.memory_active_limit, settings.memory_pending_limit),
        ChatReadFacade(ChatRepository(sessions)), MemoryValidator(llm), profile,
        dict(goal=settings.memory_goal_days, fact=settings.memory_fact_days, preference=settings.memory_preference_days))
