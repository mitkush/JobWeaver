from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Keep-warm ping target (ADR-0008). Never touches the database."""
    return {"status": "ok"}
