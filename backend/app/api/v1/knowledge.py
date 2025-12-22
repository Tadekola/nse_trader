"""
Knowledge Base API endpoints for NSE Trader.
"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.knowledge.base import KnowledgeBase, ContentCategory
from app.knowledge.lessons import LessonManager, LessonLevel

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base"])

# Initialize services
knowledge_base = KnowledgeBase()
lesson_manager = LessonManager()


class ArticleResponse(BaseModel):
    """Article response."""
    success: bool
    data: dict


class ArticleListResponse(BaseModel):
    """Article list response."""
    success: bool
    count: int
    data: List[dict]


class LessonResponse(BaseModel):
    """Lesson response."""
    success: bool
    data: dict


class LearningPathResponse(BaseModel):
    """Learning path response."""
    success: bool
    data: dict


# Knowledge Base Endpoints

@router.get("/articles")
async def get_articles(
    category: Optional[str] = Query(None, description="Filter by category: indicator, concept, nigerian_market, risk_warning")
):
    """
    Get all knowledge base articles, optionally filtered by category.
    """
    if category:
        try:
            cat_enum = ContentCategory(category)
            articles = knowledge_base.get_articles_by_category(cat_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid category: {category}")
    else:
        articles = knowledge_base.get_all_articles()
    
    return {
        "success": True,
        "count": len(articles),
        "data": [
            {
                "id": a.id,
                "title": a.title,
                "category": a.category.value,
                "summary": a.summary,
                "difficulty": a.difficulty,
                "read_time_minutes": a.read_time_minutes
            }
            for a in articles
        ]
    }


@router.get("/articles/search")
async def search_articles(
    q: str = Query(..., min_length=2, description="Search query")
):
    """
    Search knowledge base articles.
    """
    results = knowledge_base.search(q)
    return {
        "success": True,
        "query": q,
        "count": len(results),
        "data": [
            {
                "id": a.id,
                "title": a.title,
                "category": a.category.value,
                "summary": a.summary
            }
            for a in results
        ]
    }


@router.get("/articles/{article_id}", response_model=ArticleResponse)
async def get_article(article_id: str):
    """
    Get a specific knowledge base article.
    """
    article = knowledge_base.get_article(article_id)
    
    if not article:
        raise HTTPException(status_code=404, detail=f"Article not found: {article_id}")
    
    return ArticleResponse(
        success=True,
        data={
            "id": article.id,
            "title": article.title,
            "category": article.category.value,
            "summary": article.summary,
            "content": article.content,
            "nigerian_context": article.nigerian_context,
            "related_articles": article.related_articles,
            "difficulty": article.difficulty,
            "read_time_minutes": article.read_time_minutes
        }
    )


@router.get("/indicators/{indicator}")
async def get_indicator_explanation(indicator: str):
    """
    Get explanation for a specific technical indicator.
    """
    explanation = knowledge_base.get_indicator_explanation(indicator)
    
    if not explanation:
        raise HTTPException(
            status_code=404,
            detail=f"No explanation found for indicator: {indicator}"
        )
    
    return {
        "success": True,
        "indicator": indicator,
        "data": explanation
    }


@router.get("/nigerian-context/{topic}")
async def get_nigerian_context(topic: str):
    """
    Get Nigerian market-specific context for a topic.
    """
    context = knowledge_base.get_nigerian_context(topic)
    
    if not context:
        return {
            "success": True,
            "topic": topic,
            "context": None,
            "message": "No specific Nigerian context available for this topic."
        }
    
    return {
        "success": True,
        "topic": topic,
        "context": context
    }


# Learning Path Endpoints

@router.get("/lessons")
async def get_lessons(
    level: Optional[str] = Query(None, description="Filter by level: beginner, intermediate, advanced")
):
    """
    Get all lessons, optionally filtered by difficulty level.
    """
    if level:
        try:
            level_enum = LessonLevel(level)
            lessons = lesson_manager.get_lessons_by_level(level_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid level: {level}")
    else:
        lessons = lesson_manager.get_all_lessons()
    
    return {
        "success": True,
        "count": len(lessons),
        "data": [
            {
                "id": l.id,
                "title": l.title,
                "level": l.level.value,
                "description": l.description,
                "estimated_minutes": l.estimated_minutes,
                "prerequisites": l.prerequisites,
                "has_quiz": len(l.quiz_questions) > 0
            }
            for l in lessons
        ]
    }


@router.get("/lessons/{lesson_id}", response_model=LessonResponse)
async def get_lesson(lesson_id: str):
    """
    Get a specific lesson with full content.
    """
    lesson = lesson_manager.get_lesson(lesson_id)
    
    if not lesson:
        raise HTTPException(status_code=404, detail=f"Lesson not found: {lesson_id}")
    
    return LessonResponse(
        success=True,
        data={
            "id": lesson.id,
            "title": lesson.title,
            "level": lesson.level.value,
            "description": lesson.description,
            "content": lesson.content,
            "quiz_questions": lesson.quiz_questions,
            "estimated_minutes": lesson.estimated_minutes,
            "prerequisites": lesson.prerequisites
        }
    )


@router.get("/paths")
async def get_learning_paths():
    """
    Get all available learning paths.
    """
    paths = lesson_manager.get_all_paths()
    
    return {
        "success": True,
        "count": len(paths),
        "data": [
            {
                "id": p.id,
                "title": p.title,
                "description": p.description,
                "target_audience": p.target_audience,
                "lesson_count": len(p.lessons),
                "estimated_hours": p.estimated_hours
            }
            for p in paths
        ]
    }


@router.get("/paths/{path_id}", response_model=LearningPathResponse)
async def get_learning_path(path_id: str):
    """
    Get a specific learning path with its lessons.
    """
    path = lesson_manager.get_learning_path(path_id)
    
    if not path:
        raise HTTPException(status_code=404, detail=f"Learning path not found: {path_id}")
    
    lessons = lesson_manager.get_path_lessons(path_id)
    
    return LearningPathResponse(
        success=True,
        data={
            "id": path.id,
            "title": path.title,
            "description": path.description,
            "target_audience": path.target_audience,
            "estimated_hours": path.estimated_hours,
            "lessons": [
                {
                    "id": l.id,
                    "title": l.title,
                    "level": l.level.value,
                    "estimated_minutes": l.estimated_minutes
                }
                for l in lessons
            ]
        }
    )


@router.post("/paths/{path_id}/progress")
async def get_path_progress(
    path_id: str,
    completed_lessons: List[str] = []
):
    """
    Calculate progress in a learning path.
    
    Send list of completed lesson IDs to get progress.
    """
    progress = lesson_manager.calculate_progress(path_id, completed_lessons)
    
    if 'error' in progress:
        raise HTTPException(status_code=404, detail=progress['error'])
    
    # Format next_lesson if present
    if progress.get('next_lesson'):
        next_lesson = progress['next_lesson']
        progress['next_lesson'] = {
            "id": next_lesson.id,
            "title": next_lesson.title
        }
    
    return {
        "success": True,
        "data": progress
    }


@router.get("/lessons/{lesson_id}/prerequisites")
async def check_lesson_prerequisites(
    lesson_id: str,
    completed: str = Query("", description="Comma-separated list of completed lesson IDs")
):
    """
    Check if prerequisites are met for a lesson.
    """
    completed_list = [c.strip() for c in completed.split(",") if c.strip()]
    
    met, missing = lesson_manager.check_prerequisites(lesson_id, completed_list)
    
    return {
        "success": True,
        "lesson_id": lesson_id,
        "prerequisites_met": met,
        "missing_prerequisites": missing
    }
