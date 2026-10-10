"""Bounded multimodal answer extraction; transcription always requires review."""
import asyncio
import base64
import json
import re
import subprocess
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from pydantic import BaseModel, ConfigDict, Field, model_validator
from langchain_core.messages import HumanMessage
from starlette.concurrency import run_in_threadpool
from app.core.exceptions import AppError
from app.langchain.prompts import PromptSource
from app.core.logging import workflow_logger


class AnswerRegion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode='after')
    def bounds(self):
        if self.x+self.width > 1.001 or self.y+self.height > 1.001:
            raise ValueError('Region exceeds page bounds')
        return self


class ExtractedAnswer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question_id: str
    text: str = Field(max_length=8000)
    confidence: float = Field(ge=0, le=1)
    ambiguous: bool = False
    region: AnswerRegion | None = None


class PageAnswers(BaseModel):
    model_config = ConfigDict(extra='forbid')
    answers: list[ExtractedAnswer] = Field(default_factory=list, max_length=10)
    warnings: list[str] = Field(default_factory=list, max_length=5)


def prepare_pages(data):
    from PIL import Image, ImageOps
    def encode(path):
        with Image.open(path) as original:
            if original.width*original.height > 30_000_000:
                raise AppError('ASSESSMENT_IMAGE_SIZE', 'The answer sheet exceeds the image pixel limit.', 422)
            image = ImageOps.exif_transpose(original).convert('RGB')
            image.thumbnail((1600,1600))
            output = BytesIO()
            image.save(output, format='JPEG', quality=90)
            return base64.b64encode(output.getvalue()).decode('ascii')
    if not data.startswith(b'%PDF'):
        return [encode(BytesIO(data))]
    with TemporaryDirectory(prefix='mentra-answer-vision-') as directory:
        source = Path(directory)/'source.pdf'
        source.write_bytes(data)
        info = subprocess.run(['pdfinfo', str(source)], capture_output=True, text=True, timeout=10, check=True)
        match = re.search(r'^Pages:\s+(\d+)', info.stdout, re.M)
        if not match or not 1 <= int(match.group(1)) <= 6:
            raise AppError('ASSESSMENT_VISION_PAGES', 'Vision extraction supports up to six pages; OCR and manual review remain available.', 422)
        prefix = Path(directory)/'page'
        subprocess.run(['pdftoppm','-r','120','-scale-to','1600','-jpeg',str(source),str(prefix)], capture_output=True, timeout=45, check=True)
        return [encode(path) for path in sorted(Path(directory).glob('page-*.jpg'))]


@workflow_logger.connect_module(default_outcome='success')
class AssessmentAnswerExtractor:
    def __init__(self, llm):
        self.llm = llm

    async def extract(self, data, questions):
        images = await run_in_threadpool(prepare_pages, data)
        mapping = [dict(number=index, question_id=str(question.id), prompt=question.prompt[:500])
                   for index, question in enumerate(questions, 1)]
        allowed = {item['question_id'] for item in mapping}
        semaphore = asyncio.Semaphore(2)
        async def read(page, image):
            async with semaphore:
                result = await self.llm.ainvoke_messages(PromptSource.ASSESSMENT_TRANSCRIPTION,
                    [HumanMessage(content=[dict(type='text', text=json.dumps(dict(page=page, questions=mapping))),
                        dict(type='image_url', image_url=dict(url='data:image/jpeg;base64,'+image, detail='high'))])],
                    output_schema=PageAnswers)
                result = PageAnswers.model_validate(result)
                ids = [answer.question_id for answer in result.answers]
                if len(ids) != len(set(ids)) or not set(ids) <= allowed:
                    raise AppError('ASSESSMENT_INVALID_TRANSCRIPTION', 'The image transcription changed question identity.', 502)
                return page, result
        from app.langchain.workflow_budget import model_budget
        with model_budget():
            pages = await asyncio.wait_for(asyncio.gather(*(read(index, image) for index,image in enumerate(images,1))), 60)
        answers = {identifier:'' for identifier in allowed}
        blocks, warnings, confidence = [], [], []
        for page, result in pages:
            warnings.extend(result.warnings)
            for answer in result.answers:
                combined = '\n'.join(filter(None, [answers[answer.question_id], answer.text]))
                if len(combined) > 8000:
                    raise AppError('ASSESSMENT_ANSWER_SIZE', 'A transcribed answer exceeds 8000 characters. Review it manually.', 422)
                answers[answer.question_id] = combined
                confidence.append(answer.confidence)
                blocks.append(dict(question_id=answer.question_id, page=page, text=answer.text,
                    method='vision', confidence=answer.confidence, ambiguous=answer.ambiguous,
                    region=answer.region.model_dump() if answer.region else None))
                if answer.ambiguous:
                    warnings.append(f'Question {next(item["number"] for item in mapping if item["question_id"]==answer.question_id)} has ambiguous handwriting or numbering on page {page}.')
        missing = [item['number'] for item in mapping if not answers[item['question_id']].strip()]
        if missing:
            warnings.append('No answer was recognized for questions: '+', '.join(map(str, missing))+'.')
        return dict(answers=answers, blocks=blocks, warnings=list(dict.fromkeys(warnings)),
            text='\n\n'.join(answer for answer in answers.values() if answer), reader_revision='assessment-vision-v1',
            extraction_confidence=min(confidence) if confidence else 0, mapping_confidence=None,
            requires_confirmation=True, handwriting_support='vision_requires_review', truncated=False)
