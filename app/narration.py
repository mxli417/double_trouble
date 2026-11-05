import logging

from openai import AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger("double_trouble.narration")


async def narrate_match(matches: list[dict]) -> str | None:
    settings = get_settings()
    if not settings.narration_available:
        return None
    candidates = ", ".join(f"{item['name']} ({item['similarity']:.3f})" for item in matches)
    try:
        client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_timeout_seconds,
            max_retries=1,
        )
        response = await client.responses.create(
            model=settings.openai_model,
            store=False,
            max_output_tokens=100,
            instructions=(
                "Write one playful, kind sentence for a private celebrity-lookalike party game. "
                "Treat scores as entertainment-only visual similarity, never identity, attractiveness, "
                "ethnicity, health, gender, age, or another sensitive inference. Do not insult anyone."
            ),
            input=f"Top visual-similarity candidates: {candidates}",
        )
        narration = response.output_text.strip()
        return narration[:500] if narration else None
    except Exception:
        # The match remains useful if the optional external narration is unavailable.
        logger.warning("match_narration_unavailable")
        return None
