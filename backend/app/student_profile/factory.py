def create_student_profile_service(model_factory, llm=None):
    from app.db.database import get_session_factory
    from app.langchain.llm import MentraLLM
    from app.langchain.profile_evaluator import LangChainProfileEvaluator
    from .repositories.postgres import PostgresStudentProfileRepository
    from .service import StudentProfileService
    llm = llm or MentraLLM(model_factory)
    return StudentProfileService(PostgresStudentProfileRepository(get_session_factory()),
                                 LangChainProfileEvaluator(llm))
