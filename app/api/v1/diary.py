"""GET/POST /v1/diary — 日记读写端点。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps import get_long_term_tools
from cogcore.tools import LongTermExperienceTools

router = APIRouter(prefix="/v1/diary", tags=["diary"])


class WriteDiaryRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)


class DiaryEntry(BaseModel):
    id: str
    title: str
    content: str
    importance: float
    tags: list[str]


class WriteDiaryResponse(BaseModel):
    diary_id: str


@router.post("", response_model=WriteDiaryResponse)
def write_diary(
    req: WriteDiaryRequest, lt: LongTermExperienceTools = Depends(get_long_term_tools)
) -> WriteDiaryResponse:
    """写一条日记。"""
    diary_id = lt.write_diary(
        title=req.title,
        content=req.content,
        importance=req.importance,
        tags=req.tags,
    )
    return WriteDiaryResponse(diary_id=diary_id)


@router.get("", response_model=list[DiaryEntry])
def read_diary(
    query: str = "",
    k: int = 5,
    lt: LongTermExperienceTools = Depends(get_long_term_tools),
) -> list[DiaryEntry]:
    """读日记。query 为空返回最近 k 条。"""
    if k < 1 or k > 100:
        raise HTTPException(status_code=400, detail="k must be in [1, 100]")
    entries = lt.read_diary(query=query, k=k)
    return [DiaryEntry(**e) for e in entries]
