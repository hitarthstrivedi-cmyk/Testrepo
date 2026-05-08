import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from analyzer import CategoryAnalysis, analyze_category
from config import TOPIC_CATEGORIES, settings
from instagram import instagram_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory cache for analysis results
_analysis_cache: Dict[str, CategoryAnalysis] = {}
_last_fetch_time: Optional[datetime] = None
_is_fetching: bool = False

CACHE_FILE = Path(__file__).parent / "cache.json"


def _save_cache():
    try:
        data = {}
        for cat, analysis in _analysis_cache.items():
            data[cat] = {
                "category": analysis.category,
                "total_posts_analyzed": analysis.total_posts_analyzed,
                "analysis_timestamp": analysis.analysis_timestamp,
                "error": analysis.error,
                "trending_topics": [
                    {
                        "title": t.title,
                        "summary": t.summary,
                        "key_themes": t.key_themes,
                        "engagement_signals": t.engagement_signals,
                        "example_post_caption": t.example_post_caption,
                        "hashtags_analyzed": t.hashtags_analyzed,
                    }
                    for t in analysis.trending_topics
                ],
            }
        CACHE_FILE.write_text(json.dumps(data, indent=2))
    except Exception as e:
        logger.warning(f"Could not save cache: {e}")


def _load_cache():
    global _analysis_cache, _last_fetch_time
    if not CACHE_FILE.exists():
        return
    try:
        from analyzer import TrendingTopic

        data = json.loads(CACHE_FILE.read_text())
        for cat, raw in data.items():
            topics = [
                TrendingTopic(**t) for t in raw.get("trending_topics", [])
            ]
            _analysis_cache[cat] = CategoryAnalysis(
                category=raw["category"],
                trending_topics=topics,
                total_posts_analyzed=raw.get("total_posts_analyzed", 0),
                analysis_timestamp=raw.get("analysis_timestamp", ""),
                error=raw.get("error"),
            )
        if _analysis_cache:
            timestamps = [
                a.analysis_timestamp
                for a in _analysis_cache.values()
                if a.analysis_timestamp
            ]
            if timestamps:
                _last_fetch_time = datetime.fromisoformat(max(timestamps))
        logger.info(f"Loaded {len(_analysis_cache)} cached categories from disk.")
    except Exception as e:
        logger.warning(f"Could not load cache: {e}")


async def fetch_and_analyze_all():
    global _analysis_cache, _last_fetch_time, _is_fetching

    if _is_fetching:
        logger.info("Fetch already in progress, skipping.")
        return

    _is_fetching = True
    logger.info("Starting Instagram data fetch and analysis...")

    try:
        for category, hashtags in TOPIC_CATEGORIES.items():
            logger.info(f"Fetching posts for category: {category}")
            hashtag_data_list = await instagram_client.fetch_category_posts(hashtags)
            analysis = await analyze_category(category, hashtag_data_list)
            _analysis_cache[category] = analysis
            logger.info(
                f"  → {len(analysis.trending_topics)} trending topics identified"
                f" from {analysis.total_posts_analyzed} posts"
            )

        _last_fetch_time = datetime.utcnow()
        _save_cache()
        logger.info("Fetch and analysis complete.")
    except Exception as e:
        logger.error(f"Error during fetch/analysis: {e}")
    finally:
        _is_fetching = False


scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_cache()

    if settings.instagram_access_token and settings.anthropic_api_key:
        scheduler.add_job(
            fetch_and_analyze_all,
            "interval",
            hours=settings.fetch_interval_hours,
            id="fetch_job",
            next_run_time=datetime.now() if not _analysis_cache else None,
        )
        scheduler.start()
        logger.info(
            f"Scheduler started — fetching every {settings.fetch_interval_hours}h"
        )
    else:
        logger.warning(
            "Instagram or Anthropic credentials missing — running in demo mode."
        )

    yield

    scheduler.shutdown(wait=False)


app = FastAPI(
    title="StratAI Social Media Manager",
    description="Instagram trend analysis for AI & Data Strategy topics",
    version="1.0.0",
    lifespan=lifespan,
)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ── API routes ────────────────────────────────────────────────────────────────


class TrendingTopicResponse(BaseModel):
    title: str
    summary: str
    key_themes: List[str]
    engagement_signals: str
    example_post_caption: str
    hashtags_analyzed: List[str]


class CategoryResponse(BaseModel):
    category: str
    trending_topics: List[TrendingTopicResponse]
    total_posts_analyzed: int
    analysis_timestamp: str
    error: Optional[str] = None


class StatusResponse(BaseModel):
    status: str
    last_fetch_time: Optional[str]
    categories_analyzed: int
    is_fetching: bool
    has_credentials: bool


@app.get("/")
async def serve_dashboard():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({"message": "StratAI Social Media Manager API is running."})


@app.get("/api/status", response_model=StatusResponse)
async def get_status():
    return StatusResponse(
        status="running",
        last_fetch_time=_last_fetch_time.isoformat() if _last_fetch_time else None,
        categories_analyzed=len(_analysis_cache),
        is_fetching=_is_fetching,
        has_credentials=bool(
            settings.instagram_access_token and settings.anthropic_api_key
        ),
    )


@app.get("/api/trends", response_model=List[CategoryResponse])
async def get_all_trends():
    if not _analysis_cache:
        return []
    return [
        CategoryResponse(
            category=a.category,
            trending_topics=[
                TrendingTopicResponse(
                    title=t.title,
                    summary=t.summary,
                    key_themes=t.key_themes,
                    engagement_signals=t.engagement_signals,
                    example_post_caption=t.example_post_caption,
                    hashtags_analyzed=t.hashtags_analyzed,
                )
                for t in a.trending_topics
            ],
            total_posts_analyzed=a.total_posts_analyzed,
            analysis_timestamp=a.analysis_timestamp,
            error=a.error,
        )
        for a in _analysis_cache.values()
    ]


@app.get("/api/trends/{category_name}", response_model=CategoryResponse)
async def get_category_trends(category_name: str):
    # Fuzzy match on category name
    matched = next(
        (
            a
            for cat, a in _analysis_cache.items()
            if cat.lower().replace(" ", "-") == category_name.lower()
            or cat.lower() == category_name.lower()
        ),
        None,
    )
    if not matched:
        raise HTTPException(status_code=404, detail=f"Category '{category_name}' not found.")

    return CategoryResponse(
        category=matched.category,
        trending_topics=[
            TrendingTopicResponse(
                title=t.title,
                summary=t.summary,
                key_themes=t.key_themes,
                engagement_signals=t.engagement_signals,
                example_post_caption=t.example_post_caption,
                hashtags_analyzed=t.hashtags_analyzed,
            )
            for t in matched.trending_topics
        ],
        total_posts_analyzed=matched.total_posts_analyzed,
        analysis_timestamp=matched.analysis_timestamp,
        error=matched.error,
    )


@app.post("/api/refresh")
async def trigger_refresh():
    if _is_fetching:
        return JSONResponse(
            {"message": "Fetch already in progress."}, status_code=202
        )
    if not settings.instagram_access_token or not settings.anthropic_api_key:
        raise HTTPException(
            status_code=503,
            detail="Instagram or Anthropic credentials not configured.",
        )
    asyncio.create_task(fetch_and_analyze_all())
    return JSONResponse({"message": "Refresh triggered successfully."})


@app.get("/api/categories")
async def list_categories():
    return {"categories": list(TOPIC_CATEGORIES.keys())}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=False,
    )
