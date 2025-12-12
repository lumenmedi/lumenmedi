"""
LUMEN 설정 파일
모든 설정을 이 파일에서 관리합니다.
"""

# =========================================================
# RSS 피드 설정
# =========================================================
RSS_FEEDS = {
    "Gastroenterology & Endoscopy News": {
        "url": "https://www.gastroendonews.com/rss",
        "priority": 1,
        "enabled": True,
        "max_news": 5
    },
    "Medical Xpress - Gastroenterology": {
        "url": "https://medicalxpress.com/rss-feed/search/?search=gastroenterology",
        "priority": 2,
        "enabled": True,
        "max_news": 5
    },
    "News-Medical - Gastroenterology": {
        "url": "https://www.news-medical.net/tag/feed/Gastroenterology.aspx",
        "priority": 3,
        "enabled": True,
        "max_news": 5
    },
    "Healio - Gastroenterology": {
        "url": "https://www.healio.com/rss/gastroenterology.xml",
        "priority": 4,
        "enabled": True,
        "max_news": 5
    },
    "Medscape - Gastroenterology": {
        "url": "https://www.medscape.com/rss/gastroenterology",
        "priority": 5,
        "enabled": True,
        "max_news": 5
    },
    "American College of Gastroenterology": {
        "url": "https://gi.org/news/feed/",
        "priority": 6,
        "enabled": True,
        "max_news": 5
    }
}

# =========================================================
# 카테고리 설정
# =========================================================
CATEGORIES = [
    "기술/혁신",
    "규제/가이드라인",
    "연구/임상",
    "안전/품질",
    "교육/훈련"
]

CATEGORY_TAG_CLASS = {
    "기술/혁신": "tag-tech",
    "규제/가이드라인": "tag-regulation",
    "연구/임상": "tag-research",
    "안전/품질": "tag-safety",
    "교육/훈련": "tag-education"
}

# =========================================================
# AI 설정 (Google Gemini)
# =========================================================
AI_CONFIG = {
    "model": "gemini-2.0-flash-lite",
    "temperature": 0.7,
    "max_tokens": 400,
    "max_retries": 2,
    "timeout": 30
}

# =========================================================
# 캐시 설정
# =========================================================
CACHE_CONFIG = {
    "enabled": True,
    "directory": "cache",
    "expiry_days": 7,  # 7일 후 만료
    "max_size_mb": 100  # 최대 캐시 크기 (MB)
}

# =========================================================
# 중복 필터링 설정
# =========================================================
DEDUPLICATION_CONFIG = {
    "enabled": True,
    "similarity_threshold": 0.8  # 80% 이상 유사하면 중복
}

# =========================================================
# 로깅 설정
# =========================================================
LOGGING_CONFIG = {
    "level": "INFO",  # DEBUG, INFO, WARNING, ERROR
    "file": "lumen.log",
    "format": "%(asctime)s - %(levelname)s - %(message)s",
    "max_file_size_mb": 10,  # 로그 파일 최대 크기
    "backup_count": 5  # 백업 파일 개수
}

# =========================================================
# 출력 파일 설정
# =========================================================
OUTPUT_CONFIG = {
    "html_file": "index.html",
    "encoding": "utf-8"
}

# =========================================================
# 사이트 정보
# =========================================================
SITE_INFO = {
    "name": "LUMEN",
    "title": "✨ LUMEN - AI 의학 뉴스 큐레이션",
    "description": "바쁜 의료 현장을 위해 해외 최신 내시경 뉴스를 AI가 매일 한국어로 브리핑합니다.",
    "contact_email": "lumenmedi@gmail.com",
    "timezone": "Asia/Seoul"
}

# =========================================================
# 네비게이션 메뉴
# =========================================================
NAVIGATION_MENU = [
    {"icon": "🏠", "text": "홈", "link": "index.html"},
    {"icon": "📖", "text": "소개", "link": "about.html"},
    {"icon": "🔒", "text": "개인정보처리방침", "link": "privacy.html"},
    {"icon": "📋", "text": "이용약관", "link": "terms.html"},
    {"icon": "⚖️", "text": "면책조항", "link": "disclaimer.html"},
    {"icon": "📧", "text": "연락처", "link": "contact.html"}
]

# =========================================================
# 성능 설정
# =========================================================
PERFORMANCE_CONFIG = {
    "async_enabled": True,  # 비동기 처리 사용 (Windows는 False 권장)
    "max_concurrent_requests": 10,  # 최대 동시 요청 수
    "request_delay": 0.5  # API 요청 간 대기 시간 (초)
}

# =========================================================
# 데이터베이스 설정 (SQLite)
# =========================================================
DATABASE_CONFIG = {
    "enabled": True,  # 구현됨
    "path": "lumen.db",
    "backup_enabled": True,
    "backup_interval_days": 7
}

# =========================================================
# 알림 설정
# =========================================================
NOTIFICATION_CONFIG = {
    "email_enabled": True,  # 구현됨
    "slack_enabled": False,  # 아직 구현 안 됨
    "notify_on_error": True,
    "notify_on_success": False
}
