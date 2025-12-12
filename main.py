#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUMEN - 의학 정보 큐레이션 사이트 (보안 강화 버전)
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
from typing import Dict, List, Tuple, Optional

# =========================================================
# 로깅 설정
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('lumen.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =========================================================
# 설정
# =========================================================
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    logger.error("❌ GEMINI_API_KEY가 .env 파일에 설정되지 않았습니다.")
    exit(1)

# API 키 검증만 수행 (로깅하지 않음)
logger.info("🔑 API 키가 성공적으로 로드되었습니다.")

# =========================================================
# RSS 피드 설정
# =========================================================
RSS_FEEDS = {
    "Gastroenterology & Endoscopy News": "https://www.gastroendonews.com/rss",
    "Medical Xpress - Gastroenterology": "https://medicalxpress.com/rss-feed/search/?search=gastroenterology",
    "News-Medical - Gastroenterology": "https://www.news-medical.net/tag/feed/Gastroenterology.aspx",
    "Healio - Gastroenterology": "https://www.healio.com/rss/gastroenterology.xml",
    "Medscape - Gastroenterology": "https://www.medscape.com/rss/gastroenterology",
    "American College of Gastroenterology": "https://gi.org/news/feed/"
}

CATEGORY_TAG_CLASS = {
    "기술/혁신": "tag-tech",
    "규제/가이드라인": "tag-regulation",
    "연구/임상": "tag-research",
    "안전/품질": "tag-safety",
    "교육/훈련": "tag-education"
}

# =========================================================
# Gemini API 호출 (보안 강화)
# =========================================================
def get_ai_summary_and_category(title: str, max_retries: int = 2) -> Tuple[str, str, str, str]:
    """
    뉴스 제목을 보고 AI 번역 및 요약 수행
    
    Args:
        title: 영어 뉴스 제목
        max_retries: 최대 재시도 횟수
        
    Returns:
        (번역된 제목, 짧은 요약, 긴 요약, 카테고리)
    """
    logger.info(f"🤖 AI 처리 시작: {title[:50]}...")
    
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash-lite:generateContent?key={GEMINI_API_KEY}"
    
    headers = {"Content-Type": "application/json"}
    
    payload = {
        "contents": [{
            "parts": [{
                "text": f"""당신은 10년 차 베테랑 소화기내과 간호사입니다.
아래 영어 뉴스 제목을 보고 다음 작업을 수행하세요:

1. 제목: 한국어로 의역 (간결하게, 핵심만)
2. 짧은 요약: 1-2문장으로 핵심 내용 설명
3. 긴 요약: 3-4문장으로 상세하게 설명
4. 카테고리: 아래 5개 중 하나만 선택

[카테고리 옵션]
- 기술/혁신
- 규제/가이드라인
- 연구/임상
- 안전/품질
- 교육/훈련

영어 뉴스 제목: {title}

중요: 반드시 아래 형식을 정확히 지켜주세요. 다른 기호나 텍스트를 추가하지 마세요.

제목: [한국어 제목]
카테고리: [위 5개 중 정확히 하나]
짧은요약: [1-2문장]
긴요약: [3-4문장]

예시:
제목: 젊은 층 대장암 급증 원인 규명
카테고리: 연구/임상
짧은요약: 최근 연구에서 젊은 연령층의 대장암 발병률이 급증하고 있는 원인이 밝혀졌습니다.
긴요약: 미국 의학 저널에 발표된 연구에 따르면, 30-40대 대장암 환자가 지난 10년간 2배 증가했습니다. 연구팀은 가공식품 섭취 증가와 운동 부족이 주요 원인으로 분석했습니다. 전문가들은 30대부터 정기 검진을 권장하고 있습니다."""
            }]
        }],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 400
        }
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                
                if 'candidates' in result and len(result['candidates']) > 0:
                    candidate = result['candidates'][0]
                    
                    if 'content' in candidate and 'parts' in candidate['content']:
                        text = candidate['content']['parts'][0].get('text', '')
                        
                        if text:
                            parsed = parse_ai_response(text, title)
                            if parsed:
                                logger.info(f"✅ AI 처리 완료: [{parsed[3]}]")
                                return parsed
                
                logger.warning(f"⚠️ AI 응답 파싱 실패 (시도 {attempt + 1}/{max_retries})")
                
            elif response.status_code == 429:
                wait_time = 2 ** attempt
                logger.warning(f"⚠️ API 속도 제한 (429) - {wait_time}초 대기 후 재시도...")
                time.sleep(wait_time)
                continue
                
            else:
                logger.error(f"❌ API 오류 (상태 코드: {response.status_code})")
                
        except requests.Timeout:
            logger.warning(f"⚠️ API 타임아웃 (시도 {attempt + 1}/{max_retries})")
            time.sleep(1)
            
        except requests.RequestException as e:
            logger.error(f"❌ 네트워크 오류: {type(e).__name__}")
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"❌ 예상치 못한 오류: {type(e).__name__} - {str(e)}")
            break
    
    # 모든 재시도 실패 시 기본값 반환
    logger.warning(f"⚠️ AI 처리 실패 - 기본값 사용: {title[:30]}...")
    return get_fallback_summary(title)


def parse_ai_response(text: str, original_title: str) -> Optional[Tuple[str, str, str, str]]:
    """
    AI 응답 텍스트를 파싱하여 구조화된 데이터 반환
    
    Args:
        text: AI 응답 텍스트
        original_title: 원본 제목 (폴백용)
        
    Returns:
        (제목, 짧은요약, 긴요약, 카테고리) 또는 None
    """
    # 기본값
    translated_title = original_title[:50]
    category = "연구/임상"
    short_summary = ""
    long_summary = ""
    
    # 제목 추출
    title_patterns = [
        r'\*\*제목\*\*:\s*(.+)',
        r'제목:\s*(.+)',
        r'Title:\s*(.+)',
        r'\*\*Title\*\*:\s*(.+)',
    ]
    for pattern in title_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            translated_title = match.group(1).strip()
            translated_title = re.sub(r'[\*\`]', '', translated_title)
            translated_title = translated_title.split('\n')[0]
            break
    
    # 카테고리 추출
    category_patterns = [
        r'\*\*카테고리\*\*:\s*(.+)',
        r'카테고리:\s*(.+)',
        r'Category:\s*(.+)',
    ]
    for pattern in category_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            category = match.group(1).strip()
            category = re.sub(r'[\*\`]', '', category)
            category = category.split('\n')[0]
            break
    
    # 짧은 요약 추출
    short_patterns = [
        r'\*\*짧은요약\*\*:\s*(.+)',
        r'짧은요약:\s*(.+)',
        r'Short:\s*(.+)',
        r'\*\*Short\*\*:\s*(.+)',
    ]
    for pattern in short_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            short_summary = match.group(1).strip()
            short_summary = re.sub(r'[\*\`]', '', short_summary)
            lines_after = text[match.end():].split('\n')
            if lines_after and lines_after[0].strip():
                short_summary += ' ' + lines_after[0].strip()
            break
    
    # 긴 요약 추출
    long_patterns = [
        r'\*\*긴요약\*\*:\s*(.+)',
        r'긴요약:\s*(.+)',
        r'Long:\s*(.+)',
        r'\*\*Long\*\*:\s*(.+)',
    ]
    for pattern in long_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        if match:
            remaining = text[match.start():]
            long_summary = ''
            for line in remaining.split('\n'):
                if line.strip() and not any(x in line for x in ['제목:', 'Title:', '카테고리:', 'Category:', '짧은요약:', 'Short:']):
                    clean_line = re.sub(r'^\*\*긴요약\*\*:\s*', '', line)
                    clean_line = re.sub(r'^긴요약:\s*', '', clean_line)
                    clean_line = re.sub(r'^Long:\s*', '', clean_line)
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
    """
    AI 처리 실패 시 기본값 반환
    
    Args:
        title: 원본 제목
        
    Returns:
        (제목, 짧은요약, 긴요약, 카테고리)
    """
    translated_title = title[:50] + ("..." if len(title) > 50 else "")
    short_summary = f"{translated_title} 관련 뉴스입니다."
    long_summary = f"{translated_title} 관련 소식입니다. 자세한 내용은 원문을 참조하세요."
    category = "연구/임상"
    
    return (translated_title, short_summary, long_summary, category)


# =========================================================
# RSS 피드 수집 (개선된 에러 처리)
# =========================================================
def fetch_single_feed(source_name: str, feed_url: str, priority: int) -> List[Dict]:
    """
    단일 RSS 피드에서 뉴스 수집
    
    Args:
        source_name: 소스 이름
        feed_url: RSS URL
        priority: 우선순위
        
    Returns:
        뉴스 목록
    """
    try:
        logger.info(f"📡 {source_name} 수집 중...")
        feed = feedparser.parse(feed_url)
        
        if not feed.entries:
            logger.warning(f"⚠️ {source_name}: 뉴스 없음")
            return []
        
        news_list = []
        kst = timezone(timedelta(hours=9))
        
        for entry in feed.entries[:5]:
            try:
                # 날짜 파싱
                pub_date = getattr(entry, 'published_parsed', None) or getattr(entry, 'updated_parsed', None)
                if pub_date:
                    date_obj = datetime(*pub_date[:6], tzinfo=timezone.utc)
                    date_kst = date_obj.astimezone(kst)
                    formatted_date = date_kst.strftime("%Y-%m-%d")
                else:
                    formatted_date = datetime.now(kst).strftime("%Y-%m-%d")
                
                # 제목 및 URL 추출
                original_title = entry.title
                url = entry.link
                
                if not original_title or not url:
                    logger.warning(f"⚠️ 제목 또는 URL 없음 - 건너뜀")
                    continue
                
                # AI 번역 및 요약
                time.sleep(0.5)  # API 속도 제한 방지
                translated_title, short_summary, long_summary, category = get_ai_summary_and_category(original_title)
                
                news_list.append({
                    "original_title": original_title,
                    "translated_title": translated_title,
                    "short_summary": short_summary,
                    "long_summary": long_summary,
                    "category": category,
                    "url": url,
                    "date": formatted_date,
                    "source": source_name,
                    "priority": f"TOP {priority}"
                })
                
            except Exception as e:
                logger.error(f"❌ 개별 뉴스 처리 실패: {type(e).__name__}")
                continue
        
        logger.info(f"✅ {source_name}: {len(news_list)}개 뉴스 수집 완료")
        return news_list
        
    except Exception as e:
        logger.error(f"❌ {source_name} RSS 피드 오류: {type(e).__name__} - {str(e)}")
        return []


def fetch_rss_feeds() -> List[Dict]:
    """
    모든 RSS 피드에서 뉴스 수집 (에러 발생 시에도 계속 진행)
    
    Returns:
        전체 뉴스 목록
    """
    logger.info("=" * 60)
    logger.info("📰 RSS 피드 수집 시작")
    logger.info("=" * 60)
    
    all_news = []
    
    for idx, (source_name, feed_url) in enumerate(RSS_FEEDS.items(), 1):
        try:
            news = fetch_single_feed(source_name, feed_url, idx)
            all_news.extend(news)
        except Exception as e:
            logger.error(f"❌ {source_name} 전체 실패: {type(e).__name__}")
            continue  # 다음 소스로 진행
    
    logger.info("=" * 60)
    logger.info(f"✅ 총 {len(all_news)}개 뉴스 수집 완료")
    logger.info("=" * 60)
    
    return all_news


# =========================================================
# HTML 생성
# =========================================================
def generate_html(news_list: List[Dict]) -> str:
    """
    뉴스 목록으로 HTML 생성
    
    Args:
        news_list: 뉴스 데이터 리스트
        
    Returns:
        완성된 HTML 문자열
    """
    kst = timezone(timedelta(hours=9))
    current_date = datetime.now(kst).strftime("%Y년 %m월 %d일")
    
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>✨ LUMEN - AI 의학 뉴스 큐레이션</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', 'Apple SD Gothic Neo', sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #333; line-height: 1.6; }}
        
        /* 헤더 */
        header {{ background: linear-gradient(135deg, #003366 0%, #004d99 100%); color: white; text-align: center; padding: 2rem 1rem; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }}
        header h1 {{ font-size: 2.5rem; margin-bottom: 0.5rem; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); }}
        header .update {{ font-size: 0.95rem; opacity: 0.9; }}
        
        /* 네비게이션 */
        nav {{ background: white; box-shadow: 0 2px 8px rgba(0,0,0,0.1); position: sticky; top: 0; z-index: 100; }}
        nav ul {{ list-style: none; display: flex; justify-content: center; flex-wrap: wrap; padding: 1rem; gap: 1.5rem; }}
        nav ul li a {{ text-decoration: none; color: #003366; font-weight: 500; padding: 0.5rem 1rem; border-radius: 6px; transition: all 0.3s; }}
        nav ul li a:hover {{ background: #003366; color: white; }}
        
        /* 컨테이너 */
        .container {{ max-width: 1200px; margin: 2rem auto; padding: 0 1rem; }}
        
        /* 면책 배너 */
        .disclaimer-banner {{ background: #fff3cd; border: 2px solid #ffc107; border-radius: 8px; padding: 1rem; margin-bottom: 2rem; }}
        .disclaimer-banner p {{ color: #856404; font-size: 0.95rem; }}
        .disclaimer-banner a {{ color: #003366; font-weight: 600; text-decoration: underline; }}
        
        /* 통계 (한 줄) */
        .stats-inline {{ display: flex; justify-content: center; gap: 2rem; margin-bottom: 2rem; flex-wrap: wrap; }}
        .stat-item {{ background: white; padding: 1rem 1.5rem; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); text-align: center; }}
        .stat-item .number {{ display: block; font-size: 2rem; font-weight: 700; color: #003366; }}
        .stat-item .label {{ display: block; font-size: 0.9rem; color: #666; margin-top: 0.25rem; }}
        
        /* 그리드 */
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1.5rem; }}
        
        /* 카드 */
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
        
        /* 모달 (팝업) */
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
        
        /* 소개 섹션 */
        .about {{ background: white; padding: 1.5rem; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-top: 3rem; border-left: 4px solid #FFD700; }}
        .about h3 {{ color: #003366; margin-bottom: 1rem; }}
        .about p {{ color: #666; font-size: 0.95rem; }}
        
        /* 푸터 */
        footer {{ background: #003366; color: white; text-align: center; padding: 2rem; margin-top: 2rem; }}
        footer a {{ color: #FFD700; text-decoration: none; }}
        footer a:hover {{ text-decoration: underline; }}
        
        /* 반응형 */
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
        <h1>✨ LUMEN</h1>
        <p class="update">📅 {current_date}</p>
    </header>
    
    <nav>
        <ul>
            <li><a href="index.html">🏠 홈</a></li>
            <li><a href="about.html">📖 소개</a></li>
            <li><a href="privacy.html">🔒 개인정보처리방침</a></li>
            <li><a href="terms.html">📋 이용약관</a></li>
            <li><a href="disclaimer.html">⚖️ 면책조항</a></li>
            <li><a href="contact.html">📧 연락처</a></li>
        </ul>
    </nav>
    
    <div class="container">
        <!-- 면책 문구 -->
        <div class="disclaimer-banner">
            <p><strong>⚠️ 의료 정보 안내:</strong> 본 사이트의 정보는 교육 목적이며 의학적 조언을 대체할 수 없습니다. 
            자세한 내용은 <a href="disclaimer.html">면책조항</a>을 참고하세요.</p>
        </div>
        <!-- 간결한 통계 (한 줄) -->
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
    
    # 뉴스 카드 생성 (클릭 시 모달 열기)
    for idx, news in enumerate(news_list):
        tag_class = CATEGORY_TAG_CLASS.get(news['category'], "tag-research")
        
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
            <p>바쁜 의료 현장을 위해 <strong>Gastroenterology & Endoscopy News, Medical Xpress, News-Medical</strong> 등 
            해외 최신 내시경 뉴스를 AI(Google Gemini)가 매일 한국어로 브리핑합니다.</p>
        </div>
    </div>
    
    <!-- 모달 팝업 -->
"""
    
    # 각 뉴스별 모달 생성
    for idx, news in enumerate(news_list):
        tag_class = CATEGORY_TAG_CLASS.get(news['category'], "tag-research")
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
    
    html += """
    
    <footer>
        <p>© 2024 <a href="index.html">LUMEN</a> | 
        <a href="about.html">소개</a> | 
        <a href="privacy.html">개인정보처리방침</a> | 
        <a href="terms.html">이용약관</a> | 
        <a href="disclaimer.html">면책조항</a> | 
        <a href="contact.html">연락처</a></p>
        <p style="margin-top: 0.5rem; font-size: 0.85rem; opacity: 0.8;">
            AI 큐레이션 | 매일 오전 8시 업데이트 | 문의: lumenmedi@gmail.com
        </p>
    </footer>
    
    <script>
        function openModal(index) {
            document.getElementById('modal' + index).style.display = 'block';
            document.body.style.overflow = 'hidden';
        }
        
        function closeModal(index) {
            document.getElementById('modal' + index).style.display = 'none';
            document.body.style.overflow = 'auto';
        }
        
        window.onclick = function(event) {
            if (event.target.classList.contains('modal')) {
                event.target.style.display = 'none';
                document.body.style.overflow = 'auto';
            }
        }
    </script>
</body>
</html>
    """
    return html


# ============================================
# 메인 실행
# ============================================
if __name__ == "__main__":
    try:
        logger.info("\n" + "=" * 60)
        logger.info("🚀 LUMEN 시스템 시작 (보안 강화 버전)")
        logger.info("=" * 60)
        
        news_data = fetch_rss_feeds()
        
        if not news_data:
            logger.warning("⚠️ 수집된 뉴스가 없습니다. 일부 RSS 피드에 문제가 있을 수 있습니다.")
            logger.info("💡 수집된 뉴스가 없어도 빈 HTML 파일을 생성합니다.")
        
        logger.info("🔧 HTML 파일 생성 중...")
        final_html = generate_html(news_data)
        
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(final_html)
        
        logger.info("=" * 60)
        logger.info("✅ 완료! index.html 파일이 생성되었습니다.")
        logger.info("=" * 60)
        logger.info("\n💡 적용된 개선사항:")
        logger.info("  ✅ API 키 로깅 제거 (보안 강화)")
        logger.info("  ✅ 구조화된 로깅 시스템 적용")
        logger.info("  ✅ 개별 RSS 피드 실패 시에도 계속 진행")
        logger.info("  ✅ API 재시도 로직 추가 (429 에러 처리)")
        logger.info("  ✅ 타입 힌트 추가 (코드 가독성 향상)")
        logger.info("  ✅ 상세한 에러 로깅")
        
    except KeyboardInterrupt:
        logger.info("\n⚠️ 사용자에 의해 중단되었습니다.")
        exit(0)
        
    except Exception as e:
        logger.error(f"\n❌ 치명적 오류 발생: {type(e).__name__} - {str(e)}")
        exit(1)
