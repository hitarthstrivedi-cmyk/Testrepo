import anthropic
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from config import settings, TOPIC_CATEGORIES
from instagram import HashtagData, InstagramPost

logger = logging.getLogger(__name__)


@dataclass
class TrendingTopic:
    title: str
    summary: str
    key_themes: List[str]
    engagement_signals: str
    example_post_caption: str
    hashtags_analyzed: List[str]


@dataclass
class CategoryAnalysis:
    category: str
    trending_topics: List[TrendingTopic] = field(default_factory=list)
    total_posts_analyzed: int = 0
    analysis_timestamp: str = ""
    error: Optional[str] = None


def _posts_to_text(hashtag_data_list: List[HashtagData]) -> str:
    lines = []
    for hd in hashtag_data_list:
        if hd.error:
            lines.append(f"[#{hd.hashtag}: fetch error — {hd.error}]")
            continue
        for post in hd.posts:
            caption = (post.caption or "").strip()
            if not caption:
                continue
            caption_preview = caption[:400].replace("\n", " ")
            lines.append(
                f"#{hd.hashtag} | likes:{post.like_count} comments:{post.comments_count} | "
                f"{caption_preview}"
            )
    return "\n".join(lines) if lines else "No posts available."


def _build_system_prompt() -> str:
    return """You are StratAI's expert Social Media Intelligence Analyst.
Your role is to analyze Instagram posts and surface the most valuable,
actionable trending topics for AI and data strategy professionals.

Focus on:
- Emerging conversations gaining traction
- Practical insights practitioners are sharing
- Tools, frameworks, or approaches generating buzz
- Pain points or opportunities being discussed

Avoid generic observations. Be specific, insightful, and business-relevant.
Always respond with valid JSON only — no markdown fences, no extra text."""


async def analyze_category(
    category: str, hashtag_data_list: List[HashtagData]
) -> CategoryAnalysis:
    total_posts = sum(len(hd.posts) for hd in hashtag_data_list)
    hashtags_used = [hd.hashtag for hd in hashtag_data_list if not hd.error]

    if total_posts == 0:
        return CategoryAnalysis(
            category=category,
            total_posts_analyzed=0,
            analysis_timestamp=datetime.utcnow().isoformat(),
            error="No posts retrieved for this category.",
        )

    posts_text = _posts_to_text(hashtag_data_list)

    prompt = f"""Analyze these Instagram posts from the "{category}" space and identify the top 3 trending topics.

POSTS DATA:
{posts_text}

Return ONLY a JSON object with this exact structure:
{{
  "trending_topics": [
    {{
      "title": "Short descriptive title (5-8 words)",
      "summary": "2-3 sentence summary of what's trending and why it matters",
      "key_themes": ["theme1", "theme2", "theme3"],
      "engagement_signals": "Brief note on what engagement indicators suggest",
      "example_post_caption": "Most representative caption excerpt (max 100 chars)",
      "hashtags_analyzed": {json.dumps(hashtags_used)}
    }}
  ]
}}

Identify exactly 3 trending topics. Focus on what's genuinely gaining traction."""

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    try:
        async with client.messages.stream(
            model="claude-opus-4-7",
            max_tokens=4096,
            thinking={"type": "adaptive"},
            cache_control={"type": "ephemeral"},
            system=_build_system_prompt(),
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            response = await stream.get_final_message()

        raw_text = next(
            (b.text for b in response.content if b.type == "text"), ""
        ).strip()

        data = json.loads(raw_text)
        topics = []
        for t in data.get("trending_topics", []):
            topics.append(
                TrendingTopic(
                    title=t.get("title", ""),
                    summary=t.get("summary", ""),
                    key_themes=t.get("key_themes", []),
                    engagement_signals=t.get("engagement_signals", ""),
                    example_post_caption=t.get("example_post_caption", ""),
                    hashtags_analyzed=t.get("hashtags_analyzed", hashtags_used),
                )
            )

        return CategoryAnalysis(
            category=category,
            trending_topics=topics,
            total_posts_analyzed=total_posts,
            analysis_timestamp=datetime.utcnow().isoformat(),
        )

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error for category '{category}': {e}")
        return CategoryAnalysis(
            category=category,
            total_posts_analyzed=total_posts,
            analysis_timestamp=datetime.utcnow().isoformat(),
            error=f"Analysis parse error: {e}",
        )
    except anthropic.APIError as e:
        logger.error(f"Claude API error for category '{category}': {e}")
        return CategoryAnalysis(
            category=category,
            total_posts_analyzed=total_posts,
            analysis_timestamp=datetime.utcnow().isoformat(),
            error=f"AI analysis error: {e}",
        )
