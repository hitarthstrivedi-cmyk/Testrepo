from pydantic_settings import BaseSettings
from typing import Dict, List


class Settings(BaseSettings):
    instagram_access_token: str = ""
    instagram_business_account_id: str = ""
    anthropic_api_key: str = ""
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    fetch_interval_hours: int = 6

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

# Topic categories with their associated hashtags
TOPIC_CATEGORIES: Dict[str, List[str]] = {
    "AI Strategy": [
        "aistrategy",
        "artificialintelligencestrategy",
        "aiinbusiness",
        "aidriveninsights",
        "aiforleaders",
    ],
    "AI Automation (No Code)": [
        "nocode",
        "nocodetools",
        "aiautomation",
        "nocodemovement",
        "automationtools",
        "nocodeai",
    ],
    "Agentic AI": [
        "agenticai",
        "agentai",
        "agenticworkflows",
        "autonomousai",
        "agenticframework",
    ],
    "AI Agents": [
        "aiagents",
        "llmagents",
        "intelligentsystems",
        "aiassistants",
        "multiagentsystems",
    ],
    "Data Governance": [
        "datagovernance",
        "datamanagement",
        "dataprivacy",
        "datastewardship",
        "dataqualitymanagement",
    ],
    "Data Strategy": [
        "datastrategy",
        "datadriven",
        "dataanalytics",
        "dataleadership",
        "dataintelligence",
    ],
}

# Instagram Graph API base URL
INSTAGRAM_API_BASE = "https://graph.facebook.com/v21.0"

# Number of posts to fetch per hashtag
POSTS_PER_HASHTAG = 10
