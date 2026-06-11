"""answer_menu_question tool — FR-007, FR-008.

Retrieve-then-synthesize: embed the question, pull top-k menu chunks via
MenuService.search, call the synthesis-tier LLM with a citations-only
constraint.

Returns the no-info fallback when retrieval is empty (FR-007 §fallback).
Never fabricates ingredients, prices, or descriptions not present in the
retrieved citations (Principle IV synthesis-tier discipline).

contracts/internal_tools.md §answer_menu_question — synthesis tier.
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.clients import EmbeddingClient, LLMClient
from app.domain.language import Language
from app.domain.tools import AnswerMenuQuestionIn, AnswerMenuQuestionOut, MenuCitation

logger = logging.getLogger(__name__)

_NO_INFO_EN = "I don't have info on that — let me show you what we do have."
_NO_INFO_AR = "ليس لدي معلومات عن هذا — دعني أريك ما لدينا."

_SYSTEM_EN = """\
You are a menu assistant for a Lebanese restaurant.
Answer the customer's question ONLY using the provided menu citations below.
Do NOT invent, assume, or add any ingredients, prices, portions, or descriptions \
that are not explicitly stated in the citations.
If the citations do not contain enough information to answer, say so briefly.
Keep your answer concise (2–4 sentences).
"""

_SYSTEM_AR = """\
أنت مساعد قائمة لمطعم لبناني.
أجب على سؤال العميل فقط باستخدام اقتباسات القائمة المقدمة أدناه.
لا تخترع أو تفترض أي مكونات أو أسعار أو كميات أو أوصاف غير مذكورة صراحةً في الاقتباسات.
إذا لم تحتوِ الاقتباسات على معلومات كافية، فقل ذلك باختصار.
"""

_USER_TEMPLATE = """\
Customer question: {question}

Menu citations:
{citations_text}
"""


async def answer_menu_question(
    inp: AnswerMenuQuestionIn,
    session: AsyncSession,
    embedder: EmbeddingClient,
    llm: LLMClient,
) -> AnswerMenuQuestionOut:
    """RAG-grounded menu Q&A — synthesis tier.

    contracts/internal_tools.md §answer_menu_question; FR-007, FR-008.
    """
    from app.services import menu_service

    chunks = await menu_service.search(session, inp.question, embedder, k=3)

    if not chunks:
        logger.info("answer_menu_question_no_hits")
        no_info = _NO_INFO_AR if inp.language == Language.AR_LB else _NO_INFO_EN
        return AnswerMenuQuestionOut(answer=no_info, citations=[])

    citations_text = "\n".join(
        f"[{i + 1}] {chunk.menu_item_id}: {chunk.text}"
        for i, chunk in enumerate(chunks)
    )
    system = _SYSTEM_AR if inp.language == Language.AR_LB else _SYSTEM_EN
    user_msg = _USER_TEMPLATE.format(
        question=inp.question,
        citations_text=citations_text,
    )

    answer = await llm.complete_synthesis(system=system, user=user_msg)

    citations = [
        MenuCitation(menu_item_id=chunk.menu_item_id, chunk_id=chunk.id)
        for chunk in chunks
    ]
    logger.info("answer_menu_question_answered", extra={"citations": len(citations)})
    return AnswerMenuQuestionOut(answer=answer, citations=citations)
