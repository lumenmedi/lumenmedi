#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUMEN - 의학 정보 큐레이션 사이트 (네비게이션 + 면책 배너 포함)
"""

import os
from dotenv import load_dotenv
import feedparser
from datetime import datetime, timezone, timedelta
import time
import requests
import json

# =========================================================
# 설정
# =========================================================
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("⚠️ API 키가 없습니다!")
    exit()

print(f"🔑 API 키 로드 성공: {GEMINI_API_KEY[:5]}...")

# =========================================================
# Gemini 2.0 Flash로 제목 번역 + 짧은/긴 요약 + 카테고리 분류
# =========================================================
def get_ai_summary_and_category(title):
    """
    뉴스 제목을 보고:
    1. 한국어 제목 번역
    2. 짧은 요약 (1-2줄)
    3. 긴 요약 (3-4줄)
    4. 카테고리 자동 분류
    """
    print(f"    🤖 AI 번역 및 요약 중...")
    
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash-lite:generateContent?key={GEMINI_API_KEY}"
    
    headers = {"Content-Type": "application/json"}
    
    payload = {
        "contents": [{
            "parts": [{
                "text": f"""당신은 10년 차 베테랑 소화기내과 간호사입니다.
아래 영어 뉴스 제목을 보고 다음 작업을 수행하세요:

1. 제목을 한국어로 번역 (간결하게, 15자 이내)
2. 짧은 요약 (1-2문장, 핵심만)
3. 긴 요약 (3-4문장, 상세하게)
4. 카테고리 분류

[카테고리 옵션]
- 기술/혁신: AI, 새로운 장비, 기술 발전
- 규제/가이드라인: FDA 승인, 정책, 지침
- 연구/임상: 임상시험, 연구 결과, 통계
- 안전/품질: 감염 관리, 의료사고, 안전
- 교육/훈련: 교육 프로그램, 워크샵

영어 뉴스 제목: {title}

응답 형식 (반드시 이 형식으로):
제목: [한국어 번역 제목]
카테고리: [위 옵션 중 하나]
짧은요약: [1-2문장]
긴요약: [3-4문장]"""
            }]
        }],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 400
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            
            if 'candidates' in result and len(result['candidates']) > 0:
                candidate = result['candidates'][0]
                
                if 'content' in candidate and 'parts' in candidate['content']:
                    text = candidate['content']['parts'][0].get('text', '')
                    
                    if text:
                        # 기본값
                        translated_title = title[:50]
                        category = "연구/임상"
                        short_summary = text.strip()
                        long_summary = text.strip()
                        
                        lines = text.strip().split('\n')
                        for line in lines:
                            if '제목:' in line or 'Title:' in line:
                                translated_title = line.split(':', 1)[1].strip()
                            elif '카테고리:' in line or 'Category:' in line:
                                category = line.split(':', 1)[1].strip()
                            elif '짧은요약:' in line or 'Short:' in line:
                                short_summary = line.split(':', 1)[1].strip()
                            elif '긴요약:' in line or 'Long:' in line:
                                long_summary = line.split(':', 1)[1].strip()
                        
                        print(f"    ✅ 완료! [{category}]\n")
                        return translated_title, short_summary, long_summary, category
            
            print(f"    ⚠️ 파싱 실패\n")
            return title[:50], f"{title[:60]}...", f"{title[:80]}...", "연구/임상"
            
        else:
            print(f"    ❌ API 오류 ({response.status_code})\n")
            return title[:50], f"{title[:60]}...", f"{title[:80]}...", "연구/임상"
            
    except Exception as e:
        print(f"    ❌ 오류: {str(e)[:50]}\n")
        return title[:50], f"{title[:60]}...", f"{title[:80]}...", "연구/임상"


# ============================================
# 중복 체크 함수
# ============================================
def is_duplicate(title, existing_news, threshold=0.7):
    """
    제목 유사도를 계산해서 중복 판별
    """
    from difflib import SequenceMatcher
    
    title_lower = title.lower()
    
    for news in existing_news:
        existing_title_lower = news['original_title'].lower()
        similarity = SequenceMatcher(None, title_lower, existing_title_lower).ratio()
        
        if similarity > threshold:
            return True
    
    return False


# ============================================
# RSS 피드 수집
# ============================================
def fetch_rss_feeds():
    print("\n📡 여러 RSS 피드에서 최신 기사를 가져오는 중...\n")
    
    rss_urls = [
        {
            "url": "https://news.google.com/rss/search?q=endoscopy+health&hl=en-US&gl=US&ceid=US:en",
            "name": "Google News - Endoscopy",
            "priority": "⭐⭐⭐"
        },
        {
            "url": "https://news.google.com/rss/search?q=gastroenterology+endoscopy&hl=en-US&gl=US&ceid=US:en",
            "name": "Google News - Gastroenterology",
            "priority": "⭐⭐⭐"
        },
        {
            "url": "https://news.google.com/rss/search?q=colonoscopy+screening&hl=en-US&gl=US&ceid=US:en",
            "name": "Google News - Colonoscopy",
            "priority": "⭐⭐⭐"
        },
        {
            "url": "https://rss.sciencedaily.com/health_medicine/digestive_disorders.xml",
            "name": "ScienceDaily - Digestive",
            "priority": "⭐⭐⭐⭐"
        },
        {
            "url": "https://medicalxpress.com/rss-feed/search/?search=endoscopy",
            "name": "Medical Xpress - Endoscopy",
            "priority": "⭐⭐⭐⭐"
        },
        {
            "url": "https://www.news-medical.net/tag/feed/Endoscopy.aspx",
            "name": "News-Medical - Endoscopy",
            "priority": "⭐⭐⭐⭐"
        },
    ]
    
    news_items = []
    total_count = 0
    
    for feed_info in rss_urls:
        url = feed_info["url"]
        source_name = feed_info["name"]
        priority = feed_info["priority"]
        
        print(f"📡 {source_name} ({priority})에서 수집 중...")
        
        try:
            feed = feedparser.parse(url)
            
            if not feed.entries:
                print(f"  ⚠️ 피드가 비어있거나 접근 불가\n")
                continue
            
            num_articles = 5 if "⭐⭐⭐⭐" in priority else 3
            
            for i, entry in enumerate(feed.entries[:num_articles], 1):
                total_count += 1
                print(f"  [{total_count}] 기사 처리 중...")
                
                original_title = entry.get('title', '제목 없음')
                link = entry.get('link', '#')
                published = entry.get('published', '')
                
                # 중복 체크
                if is_duplicate(original_title, news_items):
                    print(f"    ⚠️ 중복 뉴스 건너뜀\n")
                    continue
                
                # 날짜 파싱
                try:
                    date_formats = [
                        '%a, %d %b %Y %H:%M:%S %z',
                        '%a, %d %b %Y %H:%M:%S %Z',
                        '%a, %d %b %Y',
                        '%Y-%m-%d',
                    ]
                    
                    date_obj = None
                    for fmt in date_formats:
                        try:
                            date_obj = datetime.strptime(published[:25], fmt)
                            break
                        except:
                            continue
                    
                    if date_obj:
                        formatted_date = date_obj.strftime('%Y-%m-%d')
                    else:
                        formatted_date = datetime.now().strftime('%Y-%m-%d')
                except:
                    formatted_date = datetime.now().strftime('%Y-%m-%d')

                # AI 번역 + 요약 + 카테고리 분류
                translated_title, short_summary, long_summary, category = get_ai_summary_and_category(original_title)
                
                news_item = {
                    'original_title': original_title,
                    'translated_title': translated_title,
                    'short_summary': short_summary,
                    'long_summary': long_summary,
                    'source': source_name,
                    'priority': priority,
                    'date': formatted_date,
                    'url': link,
                    'category': category
                }
                news_items.append(news_item)
                
                # API Rate Limit 방지
                print(f"    ⏳ 2초 대기...\n")
                time.sleep(2)
        
        except Exception as e:
            print(f"  ❌ {source_name} 피드 오류: {e}\n")
            continue
        
        print(f"  ✅ {source_name} 완료!\n")
    
    print(f"=" * 60)
    print(f"✅ 이 {len(news_items)}개 기사 수집 완료!")
    print(f"=" * 60)
    print()
    return news_items


# ============================================
# HTML 생성 (팝업 모달 포함)
# ============================================
def generate_html(news_list):
    # 한국 시간대 (UTC+9) 설정
    kst = timezone(timedelta(hours=9))
    current_date = datetime.now(kst).strftime("%Y년 %m월 %d일 %H:%M")
    
    # 카테고리별 색상
    category_tag_class = {
        "기술/혁신": "tag-tech",
        "규제/가이드라인": "tag-regulation",
        "연구/임상": "tag-research",
        "안전/품질": "tag-safety",
        "교육/훈련": "tag-education"
    }
    
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="해외 최신 내시경 의학 뉴스를 AI가 매일 한국어로 큐레이션합니다">
    <meta name="keywords" content="내시경,의학,뉴스,소화기내과,gastroenterology,endoscopy">
    <title>LUMEN - 내시경 뉴스</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Malgun Gothic', sans-serif; background: #f0f2f5; color: #333; line-height: 1.6; }}
        
        /* 헤더 */
        header {{ background: linear-gradient(135deg, #003366 0%, #004d99 100%); color: white; padding: 1.2rem 1rem; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        header h1 {{ font-size: 2rem; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); }}
        .update {{ margin-top: 0.5rem; font-size: 0.85rem; opacity: 0.85; }}
        
        /* 네비게이션 */
        nav {{
            background: white;
            padding: 1rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 2rem;
        }}
        nav ul {{
            list-style: none;
            display: flex;
            justify-content: center;
            flex-wrap: wrap;
            gap: 1.5rem;
            max-width: 1200px;
            margin: 0 auto;
        }}
        nav a {{
            color: #003366;
            text-decoration: none;
            font-weight: 500;
            transition: color 0.3s;
        }}
        nav a:hover {{ color: #FFD700; }}
        
        /* 컨테이너 */
        .container {{ max-width: 1200px; margin: 1.5rem auto; padding: 0 1rem; }}
        
        /* 면책 배너 */
        .disclaimer-banner {{
            background: linear-gradient(135deg, #fff3cd 0%, #ffe8a1 100%);
            border-left: 5px solid #ffc107;
            padding: 1rem 1.5rem;
            margin-bottom: 1.5rem;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(255,193,7,0.2);
        }}
        .disclaimer-banner p {{
            color: #856404;
            font-size: 0.9rem;
            margin: 0;
            line-height: 1.6;
        }}
        .disclaimer-banner strong {{
            color: #d9534f;
            font-weight: 600;
        }}
        .disclaimer-banner a {{
            color: #003366;
            text-decoration: underline;
            font-weight: 500;
        }}
        
        /* 간결한 통계 */
        .stats-inline {{ background: white; padding: 0.8rem 1.5rem; border-radius: 8px; box-shadow: 0 2px 6px rgba(0,0,0,0.1); margin-bottom: 1.5rem; display: flex; justify-content: space-around; align-items: center; flex-wrap: wrap; gap: 1rem; }}
        .stat-item {{ display: flex; align-items: center; gap: 0.5rem; }}
        .stat-item .number {{ font-size: 1.5rem; font-weight: bold; color: #003366; }}
        .stat-item .label {{ font-size: 0.85rem; color: #666; }}
        
        /* 뉴스 그리드 */
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1.5rem; margin-bottom: 3rem; }}
        .card {{ background: white; padding: 1.5rem; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border-top: 4px solid #003366; transition: all 0.3s; cursor: pointer; }}
        .card:hover {{ transform: translateY(-5px); box-shadow: 0 8px 15px rgba(0,0,0,0.2); }}
        
        /* 카테고리 태그 */
        .tag {{ display: inline-block; color: white; padding: 0.3rem 0.8rem; border-radius: 20px; font-size: 0.85rem; font-weight: bold; margin-bottom: 0.8rem; }}
        .tag-tech {{ background: #4A90E2; }}
        .tag-regulation {{ background: #E74C3C; }}
        .tag-research {{ background: #2ECC71; }}
        .tag-safety {{ background: #F39C12; }}
        .tag-education {{ background: #9B59B6; }}
        
        /* 출처 뱃지 */
        .source-badge {{ display: inline-block; font-size: 0.75rem; background: #f8f9fa; color: #666; padding: 0.2rem 0.5rem; border-radius: 4px; margin-left: 0.5rem; }}
        
        /* 제목 */
        .title {{ font-size: 1.3rem; font-weight: bold; color: #003366; margin-bottom: 1rem; line-height: 1.4; }}
        
        /* 요약 */
        .summary {{ font-size: 0.95rem; color: #555; line-height: 1.6; margin-bottom: 1rem; }}
        
        /* 메타 */
        .meta {{ display: flex; justify-content: space-between; align-items: center; font-size: 0.85rem; color: #888; flex-wrap: wrap; gap: 0.5rem; }}
        
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
                <span class="label">이 뉴스</span>
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
        tag_class = category_tag_class.get(news['category'], "tag-research")
        
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
        tag_class = category_tag_class.get(news['category'], "tag-research")
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
    print("\n" + "=" * 60)
    print("🚀 LUMEN 시스템 시작 (네비게이션 + 면책 배너 포함)")
    print("=" * 60)
    
    news_data = fetch_rss_feeds()
    
    if not news_data:
        print("⚠️ 뉴스를 가져오지 못했습니다.")
        exit()
    
    print("🔧 HTML 파일 생성 중...\n")
    final_html = generate_html(news_data)
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(final_html)
    
    print("=" * 60)
    print("✅ 완료! index.html 파일을 브라우저로 열어보세요.")
    print("=" * 60)
    print("\n💡 개선사항:")
    print("  ✅ 네비게이션 메뉴 추가")
    print("  ✅ 면책 배너 추가")
    print("  ✅ 짧은 요약 표시")
    print("  ✅ 원문 링크 제공")