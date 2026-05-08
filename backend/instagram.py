import httpx
import asyncio
import logging
from typing import List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from config import settings, INSTAGRAM_API_BASE, POSTS_PER_HASHTAG

logger = logging.getLogger(__name__)


@dataclass
class InstagramPost:
    id: str
    caption: str
    media_type: str
    timestamp: str
    like_count: int = 0
    comments_count: int = 0
    hashtag: str = ""
    permalink: str = ""


@dataclass
class HashtagData:
    hashtag: str
    posts: List[InstagramPost] = field(default_factory=list)
    error: Optional[str] = None


class InstagramClient:
    def __init__(self):
        self.access_token = settings.instagram_access_token
        self.business_account_id = settings.instagram_business_account_id
        self.base_url = INSTAGRAM_API_BASE
        self._hashtag_id_cache: dict[str, str] = {}

    async def _get(self, client: httpx.AsyncClient, endpoint: str, params: dict) -> dict:
        params["access_token"] = self.access_token
        response = await client.get(f"{self.base_url}/{endpoint}", params=params)
        response.raise_for_status()
        return response.json()

    async def get_hashtag_id(self, client: httpx.AsyncClient, hashtag: str) -> Optional[str]:
        if hashtag in self._hashtag_id_cache:
            return self._hashtag_id_cache[hashtag]

        try:
            data = await self._get(client, "ig_hashtag_search", {
                "user_id": self.business_account_id,
                "q": hashtag,
            })
            hashtag_id = data.get("data", [{}])[0].get("id")
            if hashtag_id:
                self._hashtag_id_cache[hashtag] = hashtag_id
            return hashtag_id
        except Exception as e:
            logger.warning(f"Could not resolve hashtag #{hashtag}: {e}")
            return None

    async def fetch_hashtag_posts(
        self, client: httpx.AsyncClient, hashtag: str, media_type: str = "top"
    ) -> HashtagData:
        hashtag_id = await self.get_hashtag_id(client, hashtag)
        if not hashtag_id:
            return HashtagData(hashtag=hashtag, error="Could not resolve hashtag ID")

        endpoint = f"{hashtag_id}/top_media" if media_type == "top" else f"{hashtag_id}/recent_media"
        fields = "id,caption,media_type,timestamp,like_count,comments_count,permalink"

        try:
            data = await self._get(client, endpoint, {
                "user_id": self.business_account_id,
                "fields": fields,
                "limit": POSTS_PER_HASHTAG,
            })

            posts = []
            for item in data.get("data", []):
                posts.append(InstagramPost(
                    id=item.get("id", ""),
                    caption=item.get("caption", ""),
                    media_type=item.get("media_type", ""),
                    timestamp=item.get("timestamp", ""),
                    like_count=item.get("like_count", 0),
                    comments_count=item.get("comments_count", 0),
                    hashtag=hashtag,
                    permalink=item.get("permalink", ""),
                ))
            return HashtagData(hashtag=hashtag, posts=posts)

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}"
            try:
                body = e.response.json()
                error_msg = body.get("error", {}).get("message", error_msg)
            except Exception:
                pass
            logger.warning(f"Failed to fetch posts for #{hashtag}: {error_msg}")
            return HashtagData(hashtag=hashtag, error=error_msg)

        except Exception as e:
            logger.warning(f"Failed to fetch posts for #{hashtag}: {e}")
            return HashtagData(hashtag=hashtag, error=str(e))

    async def fetch_category_posts(self, hashtags: List[str]) -> List[HashtagData]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            tasks = [self.fetch_hashtag_posts(client, tag) for tag in hashtags]
            results = await asyncio.gather(*tasks, return_exceptions=False)
        return list(results)


instagram_client = InstagramClient()
