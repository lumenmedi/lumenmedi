#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gemini API에서 사용 가능한 모델 목록 확인
"""

import os
from dotenv import load_dotenv
import requests

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("❌ API 키가 없습니다!")
    exit()

print(f"🔑 API 키: {GEMINI_API_KEY[:10]}...\n")

# v1 API로 모델 목록 가져오기
url = f"https://generativelanguage.googleapis.com/v1/models?key={GEMINI_API_KEY}"

try:
    response = requests.get(url, timeout=10)
    
    if response.status_code == 200:
        data = response.json()
        
        print("=" * 60)
        print("✅ 사용 가능한 Gemini 모델 목록:")
        print("=" * 60)
        
        if 'models' in data:
            for model in data['models']:
                model_name = model.get('name', 'Unknown')
                display_name = model.get('displayName', 'Unknown')
                
                # generateContent를 지원하는 모델만 표시
                supported_methods = model.get('supportedGenerationMethods', [])
                if 'generateContent' in supported_methods:
                    print(f"\n📌 {model_name}")
                    print(f"   이름: {display_name}")
                    print(f"   지원: {', '.join(supported_methods)}")
        else:
            print("⚠️ 모델 목록을 찾을 수 없습니다.")
            print(f"\n전체 응답:\n{data}")
    
    elif response.status_code == 400:
        print("❌ API 키가 잘못되었습니다.")
        print("   https://aistudio.google.com/app/apikey 에서 새 키를 발급받으세요.")
    
    elif response.status_code == 403:
        print("❌ API 키 권한이 없습니다.")
        print("   Gemini API가 활성화되지 않았을 수 있습니다.")
        print("   https://aistudio.google.com 에서 API를 활성화하세요.")
    
    else:
        print(f"❌ API 오류 ({response.status_code})")
        print(f"응답: {response.text}")

except Exception as e:
    print(f"❌ 오류: {e}")

print("\n" + "=" * 60)
print("💡 위에 표시된 모델 이름을 코드에 사용하세요!")
print("=" * 60)