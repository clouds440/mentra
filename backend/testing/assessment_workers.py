"""Explicitly drain both durable phases in end-to-end domain tests."""
from app.assessments.worker import AssessmentWorker
from app.assessments.evidence_worker import AssessmentEvidenceWorker


async def run_assessment_pipeline(service):
    handled = await AssessmentWorker(service).run_once()
    if handled:
        await AssessmentEvidenceWorker(service).run_once()
    return handled
