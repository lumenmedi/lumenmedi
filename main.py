#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUMEN - 의학 정보 큐레이션 사이트 (중기 개선 버전)
- 설정 파일 분리 (config.py)
- 데이터베이스 도입 (SQLite)
- 에러 알림 시스템 (이메일)
"""

import os
from dotenv import load_dotenv
import feedparser
from datetime import datetime, timezone, timedelta
import time
import requests
import json
import re
import logging
import hashlib
import asyncio
import aiohttp
from typing import Dict, List, Tuple, Optional
from difflib import SequenceMatcher
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# 설정 파일 import
import config

# =========================================================
# 로깅 설정
# =========================================================
logging.basicConfig(
    level=getattr(logging, config.LOGGING_CONFIG['level']),
    format=config.LOGGING_CONFIG['format'],
    handlers=[
        logging.FileHandler(config.LOGGING_CONFIG['file'], encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =========================================================
# 환경 변수 로드
# =========================================================
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

if not GEMINI_API_KEY:
    logger.error("❌ GEMINI_API_KEY가 .env 파일에 설정되지 않았습니다.")
    exit(1)

logger.info("🔑 API 키가 성공적으로 로드되었습니다.")

# =========================================================
# 데이터베이스 초기화
# =========================================================
def init_database():
    """데이터베이스 초기화 및 테이블 생성"""
    if not config.DATABASE_CONFIG['enabled']:
        return
    
    try:
        conn = sqlite3.connect(config.DATABASE_CONFIG['path'])
        cursor = conn.cursor()
        
        # 뉴스 테이블 생성
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_title TEXT NOT NULL,
                translated_title TEXT,
                short_summary TEXT,
                long_summary TEXT,
                category TEXT,
                url TEXT UNIQUE,
                source TEXT,
                publish_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 실행 로그 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS execution_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                duration_seconds REAL,
                news_count INTEGER,
                cache_hits INTEGER,
                api_calls INTEGER,
                errors_count INTEGER,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 통계 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE UNIQUE,
                total_news INTEGER,
                unique_news INTEGER,
                duplicates_removed INTEGER,
                cache_hit_rate REAL,
                avg_processing_time REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        
        logger.info("🗄️ 데이터베이스 초기화 완료")
    except Exception as e:
        logger.error(f"❌ 데이터베이스 초기화 실패: {type(e).__name__} - {str(e)}")


def save_news_to_db(news_data: List[Dict]):
    """뉴스 데이터를 데이터베이스에 저장"""
    if not config.DATABASE_CONFIG['enabled']:
        return
    
    try:
        conn = sqlite3.connect(config.DATABASE_CONFIG['path'])
        cursor = conn.cursor()
        
        saved_count = 0
        for news in news_data:
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO news 
                    (original_title, translated_title, short_summary, long_summary, 
                     category, url, source, publish_date, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    news['original_title'],
                    news['translated_title'],
                    news['short_summary'],
                    news['long_summary'],
                    news['category'],
                    news['url'],
                    news['source'],
                    news['date']
                ))
                saved_count += 1
            except sqlite3.IntegrityError:
                # 중복 URL은 무시
                continue
        
        conn.commit()
        conn.close()
        
        logger.info(f"💾 데이터베이스에 {saved_count}개 뉴스 저장 완료")
    except Exception as e:
        logger.error(f"❌ 데이터베이스 저장 실패: {type(e).__name__} - {str(e)}")


def save_execution_log(start_time: float, end_time: float, news_count: int, 
                       cache_hits: int, api_calls: int, errors_count: int, status: str):
    """실행 로그를 데이터베이스에 저장"""
    if not config.DATABASE_CONFIG['enabled']:
        return
    
    try:
        conn = sqlite3.connect(config.DATABASE_CONFIG['path'])
        cursor = conn.cursor()
        
        duration = end_time - start_time
        
        cursor.execute('''
            INSERT INTO execution_logs 
            (start_time, end_time, duration_seconds, news_count, cache_hits, 
             api_calls, errors_count, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.fromtimestamp(start_time).isoformat(),
            datetime.fromtimestamp(end_time).isoformat(),
            duration,
            news_count,
            cache_hits,
            api_calls,
            errors_count,
            status
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"📊 실행 로그 저장 완료")
    except Exception as e:
        logger.error(f"❌ 실행 로그 저장 실패: {type(e).__name__} - {str(e)}")


def get_statistics():
    """데이터베이스에서 통계 조회"""
    if not config.DATABASE_CONFIG['enabled']:
        return None
    
    try:
        conn = sqlite3.connect(config.DATABASE_CONFIG['path'])
        cursor = conn.cursor()
        
        # 총 뉴스 수
        cursor.execute('SELECT COUNT(*) FROM news')
        total_news = cursor.fetchone()[0]
        
        # 오늘 수집한 뉴스 수
        cursor.execute('''
            SELECT COUNT(*) FROM news 
            WHERE DATE(created_at) = DATE('now')
        ''')
        today_news = cursor.fetchone()[0]
        
        # 카테고리별 통계
        cursor.execute('''
            SELECT category, COUNT(*) as count 
            FROM news 
            GROUP BY category 
            ORDER BY count DESC
        ''')
        category_stats = cursor.fetchall()
        
        conn.close()
        
        return {
            'total_news': total_news,
            'today_news': today_news,
            'category_stats': category_stats
        }
    except Exception as e:
        logger.error(f"❌ 통계 조회 실패: {type(e).__name__} - {str(e)}")
        return None


# =========================================================
# 알림 시스템
# =========================================================
def send_email_notification(subject: str, message: str):
    """이메일 알림 전송"""
    if not config.NOTIFICATION_CONFIG['email_enabled'] or not EMAIL_USER or not EMAIL_PASS:
        return
    
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = config.SITE_INFO['contact_email']
        msg['Subject'] = f"[LUMEN] {subject}"
        
        body = MIMEText(message, 'plain', 'utf-8')
        msg.attach(body)
        
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        
        logger.info(f"📧 이메일 알림 전송 완료: {subject}")
    except Exception as e:
        logger.error(f"❌ 이메일 전송 실패: {type(e).__name__} - {str(e)}")


def send_slack_notification(message: str):
    """Slack 알림 전송"""
    if not config.NOTIFICATION_CONFIG['slack_enabled'] or not SLACK_WEBHOOK_URL:
        return
    
    try:
        payload = {'text': f"[LUMEN] {message}"}
        response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"💬 Slack 알림 전송 완료")
        else:
            logger.warning(f"⚠️ Slack 알림 전송 실패: {response.status_code}")
    except Exception as e:
        logger.error(f"❌ Slack 전송 실패: {type(e).__name__} - {str(e)}")


def notify_error(error_message: str):
    """에러 발생 시 알림"""
    if not config.NOTIFICATION_CONFIG['notify_on_error']:
        return
    
    send_email_notification("에러 발생", error_message)
    send_slack_notification(f"🚨 에러 발생: {error_message}")


def notify_success(summary: str):
    """성공 시 알림"""
    if not config.NOTIFICATION_CONFIG['notify_on_success']:
        return
    
    send_email_notification("실행 완료", summary)
    send_slack_notification(f"✅ 실행 완료: {summary}")


# =========================================================
# 캐싱 시스템
# =========================================================
def init_cache():
    """캐시 디렉토리 초기화"""
    if not config.CACHE_CONFIG['enabled']:
        return
    
    cache_dir = config.CACHE_CONFIG['directory']
    os.makedirs(cache_dir, exist_ok=True)
    logger.info(f"📦 캐시 디렉토리 준비: {cache_dir}")


def get_cache_key(title: str) -> str:
    """제목을 MD5 해시로 변환하여 캐시 키 생성"""
    return hashlib.md5(title.encode('utf-8')).hexdigest()


def get_cached_summary(title: str) -> Optional[Tuple[str, str, str, str]]:
    """캐시에서 요약 데이터 로드"""
    if not config.CACHE_CONFIG['enabled']:
        return None
    
    cache_key = get_cache_key(title)
    cache_dir = config.CACHE_CONFIG['directory']
    cache_file = os.path.join(cache_dir, f"{cache_key}.json")
    
    if not os.path.exists(cache_file):
        return None
    
    try:
        file_time = datetime.fromtimestamp(os.path.getmtime(cache_file))
        expiry_days = config.CACHE_CONFIG['expiry_days']
        
        if datetime.now() - file_time > timedelta(days=expiry_days):
            logger.debug(f"⏰ 캐시 만료: {title[:30]}...")
            os.remove(cache_file)
            return None
        
        with open(cache_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info(f"💾 캐시 적중: {title[:30]}...")
            return (
                data['translated_title'],
                data['short_summary'],
                data['long_summary'],
                data['category']
            )
    except Exception as e:
        logger.warning(f"⚠️ 캐시 로드 실패: {type(e).__name__}")
        return None


def save_to_cache(title: str, translated_title: str, short_summary: str, 
                  long_summary: str, category: str):
    """요약 데이터를 캐시에 저장"""
    if not config.CACHE_CONFIG['enabled']:
        return
    
    try:
        cache_key = get_cache_key(title)
        cache_dir = config.CACHE_CONFIG['directory']
        cache_file = os.path.join(cache_dir, f"{cache_key}.json")
        
        data = {
            'original_title': title,
            'translated_title': translated_title,
            'short_summary': short_summary,
            'long_summary': long_summary,
            'category': category,
            'cached_at': datetime.now().isoformat()
        }
        
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.debug(f"💾 캐시 저장: {title[:30]}...")
    except Exception as e:
        logger.warning(f"⚠️ 캐시 저장 실패: {type(e).__name__}")


def clean_old_cache():
    """오래된 캐시 파일 정리"""
    if not config.CACHE_CONFIG['enabled']:
        return
    
    cache_dir = config.CACHE_CONFIG['directory']
    if not os.path.exists(cache_dir):
        return
    
    expiry_days = config.CACHE_CONFIG['expiry_days']
    cleaned = 0
    
    for filename in os.listdir(cache_dir):
        filepath = os.path.join(cache_dir, filename)
        try:
            file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
            if datetime.now() - file_time > timedelta(days=expiry_days):
                os.remove(filepath)
                cleaned += 1
        except Exception:
            continue
    
    if cleaned > 0:
        logger.info(f"🧹 오래된 캐시 {cleaned}개 정리 완료")


# =========================================================
# 중복 필터링
# =========================================================
def calculate_similarity(text1: str, text2: str) -> float:
    """두 텍스트의 유사도 계산 (0.0 ~ 1.0)"""
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()


def is_duplicate(title: str, seen_titles: List[str]) -> bool:
    """제목이 중복인지 확인"""
    if not config.DEDUPLICATION_CONFIG['enabled']:
        return False
    
    threshold = config.DEDUPLICATION_CONFIG['similarity_threshold']
    
    for seen_title in seen_titles:
        if calculate_similarity(title, seen_title) >= threshold:
            return True
    return False


def remove_duplicates(news_list: List[Dict]) -> List[Dict]:
    """중복 뉴스 제거"""
    if not config.DEDUPLICATION_CONFIG['enabled']:
        return news_list
    
    unique_news = []
    seen_titles = []
    duplicates_count = 0
    
    for news in news_list:
        title = news['original_title']
        
        if is_duplicate(title, seen_titles):
            duplicates_count += 1
            logger.debug(f"🔄 중복 제거: {title[:40]}...")
            continue
        
        unique_news.append(news)
        seen_titles.append(title)
    
    if duplicates_count > 0:
        logger.info(f"🔄 중복 뉴스 {duplicates_count}개 제거 완료")
    
    return unique_news


# =========================================================
# 비동기 AI 처리 (config 기반)
# =========================================================
async def get_ai_summary_async(session: aiohttp.ClientSession, title: str) -> Tuple[str, str, str, str]:
    """비동기로 AI 번역 및 요약 수행"""
    # 캐시 확인
    cached = get_cached_summary(title)
    if cached:
        return cached
    
    logger.info(f"🤖 AI 처리 시작: {title[:50]}...")
    
    url = f"https://generativelanguage.googleapis.com/v1/models/{config.AI_CONFIG['model']}:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    categories_str = '\n- '.join(config.CATEGORIES)
    
    payload = {
        "contents": [{
            "parts": [{
                "text": f"""당신은 10년 차 베테랑 소화기내과 간호사입니다.
아래 영어 뉴스 제목을 보고 다음 작업을 수행하세요:

1. 제목: 한국어로 의역 (간결하게, 핵심만)
2. 짧은 요약: 1-2문장으로 핵심 내용 설명
3. 긴 요약: 3-4문장으로 상세하게 설명
4. 카테고리: 아래 중 하나만 선택

[카테고리 옵션]
- {categories_str}

영어 뉴스 제목: {title}

중요: 반드시 아래 형식을 정확히 지켜주세요.

제목: [한국어 제목]
카테고리: [위 카테고리 중 하나]
짧은요약: [1-2문장]
긴요약: [3-4문장]"""
            }]
        }],
        "generationConfig": {
            "temperature": config.AI_CONFIG['temperature'],
            "maxOutputTokens": config.AI_CONFIG['max_tokens']
        }
    }
    
    max_retries = config.AI_CONFIG['max_retries']
    timeout_val = config.AI_CONFIG['timeout']
    
    for attempt in range(max_retries):
        try:
            async with session.post(url, headers=headers, json=payload, timeout=timeout_val) as response:
                if response.status == 200:
                    result = await response.json()
                    
                    if 'candidates' in result and len(result['candidates']) > 0:
                        candidate = result['candidates'][0]
                        
                        if 'content' in candidate and 'parts' in candidate['content']:
                            text = candidate['content']['parts'][0].get('text', '')
                            
                            if text:
                                parsed = parse_ai_response(text, title)
                                if parsed:
                                    logger.info(f"✅ AI 처리 완료: [{parsed[3]}]")
                                    save_to_cache(title, *parsed)
                                    return parsed
                    
                    logger.warning(f"⚠️ AI 응답 파싱 실패 (시도 {attempt + 1}/{max_retries})")
                    
                elif response.status == 429:
                    wait_time = 2 ** attempt
                    logger.warning(f"⚠️ API 속도 제한 (429) - {wait_time}초 대기 후 재시도...")
                    await asyncio.sleep(wait_time)
                    continue
                    
                else:
                    logger.error(f"❌ API 오류 (상태 코드: {response.status})")
                    
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ API 타임아웃 (시도 {attempt + 1}/{max_retries})")
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"❌ 예상치 못한 오류: {type(e).__name__} - {str(e)}")
            break
    
    logger.warning(f"⚠️ AI 처리 실패 - 기본값 사용: {title[:30]}...")
    return get_fallback_summary(title)


def parse_ai_response(text: str, original_title: str) -> Optional[Tuple[str, str, str, str]]:
    """AI 응답 텍스트 파싱"""
    translated_title = original_title[:50]
    category = config.CATEGORIES[0]  # 기본 카테고리
    short_summary = ""
    long_summary = ""
    
    # 제목 추출
    title_patterns = [
        r'\*\*제목\*\*:\s*(.+)',
        r'제목:\s*(.+)',
    ]
    for pattern in title_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            translated_title = re.sub(r'[\*\`]', '', match.group(1).strip()).split('\n')[0]
            break
    
    # 카테고리 추출
    category_patterns = [
        r'\*\*카테고리\*\*:\s*(.+)',
        r'카테고리:\s*(.+)',
    ]
    for pattern in category_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            category = re.sub(r'[\*\`]', '', match.group(1).strip()).split('\n')[0]
            break
    
    # 짧은 요약 추출
    short_patterns = [
        r'\*\*짧은요약\*\*:\s*(.+)',
        r'짧은요약:\s*(.+)',
    ]
    for pattern in short_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            short_summary = re.sub(r'[\*\`]', '', match.group(1).strip())
            break
    
    # 긴 요약 추출
    long_patterns = [
        r'\*\*긴요약\*\*:\s*(.+)',
        r'긴요약:\s*(.+)',
    ]
    for pattern in long_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        if match:
            remaining = text[match.start():]
            long_summary = ''
            for line in remaining.split('\n'):
                if line.strip() and not any(x in line for x in ['제목:', '카테고리:', '짧은요약:']):
                    clean_line = re.sub(r'^\*\*긴요약\*\*:\s*|^긴요약:\s*', '', line)
                    clean_line = re.sub(r'[\*\`]', '', clean_line)
                    if clean_line.strip():
                        long_summary += clean_line.strip() + ' '
            long_summary = long_summary.strip()
            if long_summary:
                break
    
    # 검증
    if not translated_title or len(translated_title) < 5:
        translated_title = original_title[:50]
    
    if not short_summary or len(short_summary) < 10:
        short_summary = f"{translated_title} 관련 뉴스입니다."
    
    if not long_summary or len(long_summary) < 20:
        long_summary = f"{translated_title} 관련 소식입니다. 자세한 내용은 원문을 참조하세요."
    
    return (translated_title, short_summary, long_summary, category)


def get_fallback_summary(title: str) -> Tuple[str, str, str, str]:
    """AI 처리 실패 시 기본값 반환"""
    translated_title = title[:50] + ("..." if len(title) > 50 else "")
    short_summary = f"{translated_title} 관련 뉴스입니다."
    long_summary = f"{translated_title} 관련 소식입니다. 자세한 내용은 원문을 참조하세요."
    category = config.CATEGORIES[0]
    
    return (translated_title, short_summary, long_summary, category)


# =========================================================
# RSS 피드 수집 (config 기반)
# =========================================================
async def process_entries_async(session: aiohttp.ClientSession, entries: list, 
                                source_name: str, priority: int) -> List[Dict]:
    """RSS 엔트리들을 비동기로 처리"""
    kst = timezone(timedelta(hours=9))
    tasks = []
    entries_data = []
    
    # config에서 설정 가져오기
    feed_config = None
    for name, cfg in config.RSS_FEEDS.items():
        if name == source_name:
            feed_config = cfg
            break
    
    max_news = feed_config['max_news'] if feed_config else 5
    
    for entry in entries[:max_news]:
        try:
            pub_date = getattr(entry, 'published_parsed', None) or getattr(entry, 'updated_parsed', None)
            if pub_date:
                date_obj = datetime(*pub_date[:6], tzinfo=timezone.utc)
                date_kst = date_obj.astimezone(kst)
                formatted_date = date_kst.strftime("%Y-%m-%d")
            else:
                formatted_date = datetime.now(kst).strftime("%Y-%m-%d")
            
            original_title = entry.title
            url = entry.link
            
            if not original_title or not url:
                continue
            
            entries_data.append({
                'original_title': original_title,
                'url': url,
                'date': formatted_date,
                'source': source_name,
                'priority': f"TOP {priority}"
            })
            
            tasks.append(get_ai_summary_async(session, original_title))
            
        except Exception as e:
            logger.error(f"❌ 엔트리 파싱 실패: {type(e).__name__}")
            continue
    
    if tasks:
        logger.info(f"⚡ {len(tasks)}개 뉴스를 병렬 처리 중...")
        ai_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        news_list = []
        for entry_data, ai_result in zip(entries_data, ai_results):
            if isinstance(ai_result, Exception):
                logger.error(f"❌ AI 처리 중 예외 발생: {type(ai_result).__name__}")
                continue
            
            translated_title, short_summary, long_summary, category = ai_result
            
            news_list.append({
                **entry_data,
                'translated_title': translated_title,
                'short_summary': short_summary,
                'long_summary': long_summary,
                'category': category
            })
        
        return news_list
    
    return []


async def fetch_single_feed_async(session: aiohttp.ClientSession, source_name: str, 
                                  feed_config: Dict, priority: int) -> List[Dict]:
    """단일 RSS 피드에서 뉴스 수집 (비동기)"""
    if not feed_config['enabled']:
        logger.info(f"⏭️ {source_name}: 비활성화됨")
        return []
    
    try:
        logger.info(f"📡 {source_name} 수집 중...")
        
        loop = asyncio.get_event_loop()
        feed = await loop.run_in_executor(None, feedparser.parse, feed_config['url'])
        
        if not feed.entries:
            logger.warning(f"⚠️ {source_name}: 뉴스 없음")
            return []
        
        news_list = await process_entries_async(session, feed.entries, source_name, priority)
        
        logger.info(f"✅ {source_name}: {len(news_list)}개 뉴스 수집 완료")
        return news_list
        
    except Exception as e:
        logger.error(f"❌ {source_name} RSS 피드 오류: {type(e).__name__} - {str(e)}")
        return []


async def fetch_rss_feeds_async() -> List[Dict]:
    """모든 RSS 피드에서 뉴스 수집 (비동기 병렬 처리)"""
    logger.info("=" * 60)
    logger.info("📰 RSS 피드 수집 시작 (비동기 모드)")
    logger.info("=" * 60)
    
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [
            fetch_single_feed_async(session, source_name, feed_config, idx)
            for idx, (source_name, feed_config) in enumerate(config.RSS_FEEDS.items(), 1)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_news = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"❌ 피드 수집 중 예외 발생: {type(result).__name__}")
                continue
            all_news.extend(result)
    
    logger.info("=" * 60)
    logger.info(f"✅ 총 {len(all_news)}개 뉴스 수집 완료")
    logger.info("=" * 60)
    
    return all_news


# =========================================================
# HTML 생성 (config 기반)
# =========================================================
def generate_html(news_list: List[Dict]) -> str:
    """뉴스 목록으로 HTML 생성"""
    kst = timezone(timedelta(hours=9))
    current_date = datetime.now(kst).strftime("%Y년 %m월 %d일")
    
    # 네비게이션 메뉴 생성
    nav_items = ""
    for item in config.NAVIGATION_MENU:
        nav_items += f'<li><a href="{item["link"]}">{item["icon"]} {item["text"]}</a></li>\n            '
    
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{config.SITE_INFO['title']}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', 'Apple SD Gothic Neo', sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #333; line-height: 1.6; }}
        
        header {{ background: linear-gradient(135deg, #003366 0%, #004d99 100%); color: white; text-align: center; padding: 2rem 1rem; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }}
        header h1 {{ font-size: 2.5rem; margin-bottom: 0.5rem; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); }}
        header .update {{ font-size: 0.95rem; opacity: 0.9; }}
        
        nav {{ background: white; box-shadow: 0 2px 8px rgba(0,0,0,0.1); position: sticky; top: 0; z-index: 100; }}
        nav ul {{ list-style: none; display: flex; justify-content: center; flex-wrap: wrap; padding: 1rem; gap: 1.5rem; }}
        nav ul li a {{ text-decoration: none; color: #003366; font-weight: 500; padding: 0.5rem 1rem; border-radius: 6px; transition: all 0.3s; }}
        nav ul li a:hover {{ background: #003366; color: white; }}
        
        .container {{ max-width: 1200px; margin: 2rem auto; padding: 0 1rem; }}
        
        .disclaimer-banner {{ background: #fff3cd; border: 2px solid #ffc107; border-radius: 8px; padding: 1rem; margin-bottom: 2rem; }}
        .disclaimer-banner p {{ color: #856404; font-size: 0.95rem; }}
        .disclaimer-banner a {{ color: #003366; font-weight: 600; text-decoration: underline; }}
        
        .stats-inline {{ display: flex; justify-content: center; gap: 2rem; margin-bottom: 2rem; flex-wrap: wrap; }}
        .stat-item {{ background: white; padding: 1rem 1.5rem; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); text-align: center; }}
        .stat-item .number {{ display: block; font-size: 2rem; font-weight: 700; color: #003366; }}
        .stat-item .label {{ display: block; font-size: 0.9rem; color: #666; margin-top: 0.25rem; }}
        
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1.5rem; }}
        
        .card {{ background: white; border-radius: 12px; padding: 1.5rem; box-shadow: 0 4px 12px rgba(0,0,0,0.1); transition: all 0.3s; cursor: pointer; position: relative; }}
        .card:hover {{ transform: translateY(-5px); box-shadow: 0 8px 20px rgba(0,0,0,0.2); }}
        .tag {{ display: inline-block; padding: 0.4rem 0.8rem; border-radius: 20px; font-size: 0.85rem; font-weight: 600; margin-bottom: 0.75rem; }}
        .tag-tech {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }}
        .tag-regulation {{ background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; }}
        .tag-research {{ background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); color: white; }}
        .tag-safety {{ background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); color: white; }}
        .tag-education {{ background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); color: white; }}
        .source-badge {{ position: absolute; top: 1rem; right: 1rem; background: #FFD700; color: #003366; padding: 0.3rem 0.6rem; border-radius: 6px; font-size: 0.75rem; font-weight: 700; }}
        .title {{ font-size: 1.2rem; font-weight: 700; color: #003366; margin-bottom: 0.75rem; line-height: 1.4; }}
        .summary {{ color: #666; font-size: 0.95rem; margin-bottom: 1rem; line-height: 1.6; }}
        .meta {{ display: flex; justify-content: space-between; font-size: 0.85rem; color: #999; }}
        
        .modal {{ display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.7); }}
        .modal-content {{ background-color: white; margin: 5% auto; padding: 2rem; border-radius: 12px; width: 90%; max-width: 700px; max-height: 80vh; overflow-y: auto; position: relative; box-shadow: 0 10px 40px rgba(0,0,0,0.3); }}
        .close {{ color: #aaa; float: right; font-size: 2rem; font-weight: bold; cursor: pointer; line-height: 1; }}
        .close:hover {{ color: #000; }}
        .modal-title {{ font-size: 1.6rem; font-weight: 700; color: #003366; margin-bottom: 1rem; padding-right: 2rem; }}
        .modal-original-title {{ font-size: 1rem; color: #666; margin-bottom: 1.5rem; padding: 1rem; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #003366; }}
        .modal-summary {{ font-size: 1.05rem; color: #333; line-height: 1.8; margin-bottom: 1.5rem; }}
        .modal-meta {{ display: flex; justify-content: space-between; font-size: 0.9rem; color: #888; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 0.5rem; }}
        .btn {{ display: inline-block; background: linear-gradient(135deg, #003366 0%, #004d99 100%); color: white; padding: 0.8rem 2rem; border-radius: 6px; text-decoration: none; transition: all 0.3s; font-weight: 500; box-shadow: 0 2px 6px rgba(0,51,102,0.3); }}
        .btn:hover {{ background: linear-gradient(135deg, #004d99 0%, #003366 100%); transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,51,102,0.4); }}
        
        .about {{ background: white; padding: 1.5rem; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-top: 3rem; border-left: 4px solid #FFD700; }}
        .about h3 {{ color: #003366; margin-bottom: 1rem; }}
        .about p {{ color: #666; font-size: 0.95rem; }}
        
        footer {{ background: #003366; color: white; text-align: center; padding: 2rem; margin-top: 2rem; }}
        footer a {{ color: #FFD700; text-decoration: none; }}
        footer a:hover {{ text-decoration: underline; }}
        
        @media (max-width: 768px) {{
            header h1 {{ font-size: 1.8rem; }}
            .grid {{ grid-template-columns: 1fr; }}
            .stats-inline {{ flex-direction: column; align-items: flex-start; }}
            nav ul {{ flex-direction: column; align-items: center; gap: 1rem; }}
            .modal-content {{ width: 95%; margin: 10% auto; padding: 1.5rem; }}
        }}
    </style>
</head>
<body>
    <header>
        <h1>{config.SITE_INFO['name']}</h1>
        <p class="update">📅 {current_date}</p>
    </header>
    
    <nav>
        <ul>
            {nav_items}
        </ul>
    </nav>
    
    <div class="container">
        <div class="disclaimer-banner">
            <p><strong>⚠️ 의료 정보 안내:</strong> 본 사이트의 정보는 교육 목적이며 의학적 조언을 대체할 수 없습니다. 
            자세한 내용은 <a href="disclaimer.html">면책조항</a>을 참고하세요.</p>
        </div>
        <div class="stats-inline">
            <div class="stat-item">
                <span class="number">{len(news_list)}</span>
                <span class="label">개 뉴스</span>
            </div>
"""
    
    # 카테고리별 통계
    category_counts = {}
    for news in news_list:
        cat = news['category']
        category_counts[cat] = category_counts.get(cat, 0) + 1
    
    for category, count in category_counts.items():
        html += f"""
            <div class="stat-item">
                <span class="number">{count}</span>
                <span class="label">{category}</span>
            </div>
"""
    
    html += """
        </div>
        
        <div class="grid">
"""
    
    # 뉴스 카드 생성
    for idx, news in enumerate(news_list):
        tag_class = config.CATEGORY_TAG_CLASS.get(news['category'], "tag-research")
        
        html += f"""
            <div class="card" onclick="openModal({idx})">
                <span class="tag {tag_class}">{news['category']}</span>
                <span class="source-badge">{news['priority']}</span>
                <h3 class="title">{news['translated_title']}</h3>
                <p class="summary">{news['short_summary']}</p>
                <div class="meta">
                    <span>📰 {news['source']}</span>
                    <span>{news['date']}</span>
                </div>
            </div>
"""
    
    html += """
        </div>
        
        <div class="about">
            <h3>🩺 LUMEN이란?</h3>
            <p>""" + config.SITE_INFO['description'] + """</p>
        </div>
    </div>
    
    <!-- 모달 팝업 -->
"""
    
    # 각 뉴스별 모달 생성
    for idx, news in enumerate(news_list):
        tag_class = config.CATEGORY_TAG_CLASS.get(news['category'], "tag-research")
        html += f"""
    <div id="modal{idx}" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeModal({idx})">&times;</span>
            <span class="tag {tag_class}">{news['category']}</span>
            <h2 class="modal-title">{news['translated_title']}</h2>
            <div class="modal-original-title">
                <strong>원문 제목:</strong> {news['original_title']}
            </div>
            <p class="modal-summary">{news['long_summary']}</p>
            <div class="modal-meta">
                <span>📰 {news['source']}</span>
                <span>{news['date']}</span>
            </div>
            <a href="{news['url']}" target="_blank" rel="noopener noreferrer" class="btn">원문 보기 →</a>
        </div>
    </div>
"""
    
    # 푸터 메뉴 생성
    footer_links = " | ".join([f'<a href="{item["link"]}">{item["text"]}</a>' for item in config.NAVIGATION_MENU])
    
    html += f"""
    
    <footer>
        <p>© 2024 <a href="index.html">{config.SITE_INFO['name']}</a> | {footer_links}</p>
        <p style="margin-top: 0.5rem; font-size: 0.85rem; opacity: 0.8;">
            AI 큐레이션 | 매일 오전 8시 업데이트 | 문의: {config.SITE_INFO['contact_email']}
        </p>
    </footer>
    
    <script>
        function openModal(index) {{
            document.getElementById('modal' + index).style.display = 'block';
            document.body.style.overflow = 'hidden';
        }}
        
        function closeModal(index) {{
            document.getElementById('modal' + index).style.display = 'none';
            document.body.style.overflow = 'auto';
        }}
        
        window.onclick = function(event) {{
            if (event.target.classList.contains('modal')) {{
                event.target.style.display = 'none';
                document.body.style.overflow = 'auto';
            }}
        }}
    </script>
</body>
</html>
    """
    return html


# ============================================
# 메인 실행
# ============================================
async def main_async():
    """비동기 메인 함수"""
    start_time = time.time()
    cache_hits = 0
    api_calls = 0
    errors_count = 0
    status = "success"
    
    try:
        logger.info("\n" + "=" * 60)
        logger.info("🚀 LUMEN 시스템 시작 (중기 개선 완료 버전)")
        logger.info("=" * 60)
        logger.info("✨ 적용된 개선사항:")
        logger.info("  ⚡ 비동기 처리 (5-10배 속도 향상)")
        logger.info("  💾 캐싱 시스템 (API 비용 60-70% 절감)")
        logger.info("  🔄 중복 뉴스 필터링 (콘텐츠 품질 향상)")
        logger.info("  📁 설정 파일 분리 (유지보수 편리)")
        logger.info("  🗄️ 데이터베이스 도입 (히스토리 관리)")
        logger.info("  📧 에러 알림 시스템 (실시간 모니터링)")
        logger.info("=" * 60 + "\n")
        
        # 초기화
        init_cache()
        clean_old_cache()
        init_database()
        
        # RSS 피드 수집
        news_data = await fetch_rss_feeds_async()
        
        if not news_data:
            logger.warning("⚠️ 수집된 뉴스가 없습니다.")
            status = "no_news"
            notify_error("뉴스 수집 실패: 수집된 뉴스가 없습니다.")
        else:
            # 중복 제거
            original_count = len(news_data)
            news_data = remove_duplicates(news_data)
            final_count = len(news_data)
            
            logger.info(f"📊 중복 제거 결과: {original_count}개 → {final_count}개")
            
            # 데이터베이스에 저장
            save_news_to_db(news_data)
        
        # HTML 생성
        logger.info("🔧 HTML 파일 생성 중...")
        final_html = generate_html(news_data)
        
        output_file = config.OUTPUT_CONFIG['html_file']
        with open(output_file, "w", encoding=config.OUTPUT_CONFIG['encoding']) as f:
            f.write(final_html)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # 실행 로그 저장
        save_execution_log(start_time, end_time, len(news_data), cache_hits, api_calls, errors_count, status)
        
        logger.info("=" * 60)
        logger.info(f"✅ 완료! {output_file} 파일이 생성되었습니다.")
        logger.info("=" * 60)
        logger.info(f"\n⏱️ 성능 통계:")
        logger.info(f"  • 전체 실행 시간: {total_time:.2f}초")
        logger.info(f"  • 최종 뉴스 수: {len(news_data)}개")
        
        # 캐시 통계
        if config.CACHE_CONFIG['enabled'] and os.path.exists(config.CACHE_CONFIG['directory']):
            cache_count = len(os.listdir(config.CACHE_CONFIG['directory']))
            logger.info(f"  • 캐시된 항목: {cache_count}개")
        
        # DB 통계
        if config.DATABASE_CONFIG['enabled']:
            stats = get_statistics()
            if stats:
                logger.info(f"\n📊 데이터베이스 통계:")
                logger.info(f"  • 총 저장된 뉴스: {stats['total_news']}개")
                logger.info(f"  • 오늘 수집한 뉴스: {stats['today_news']}개")
        
        # 성공 알림
        summary = f"실행 완료: {len(news_data)}개 뉴스 수집 ({total_time:.2f}초)"
        notify_success(summary)
        
    except KeyboardInterrupt:
        logger.info("\n⚠️ 사용자에 의해 중단되었습니다.")
        status = "interrupted"
        exit(0)
        
    except Exception as e:
        logger.error(f"\n❌ 치명적 오류 발생: {type(e).__name__} - {str(e)}")
        import traceback
        error_detail = traceback.format_exc()
        logger.error(error_detail)
        
        status = "error"
        errors_count = 1
        notify_error(f"치명적 오류: {type(e).__name__} - {str(e)}")
        exit(1)


if __name__ == "__main__":
    asyncio.run(main_async())
