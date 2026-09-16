import os
import streamlit as st
import pandas as pd
import json
from io import BytesIO

# PDF 추출을 위한 pypdf 라이브러리 안전 Import
try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

# 구글 제미나이(Gemini) 라이브러리 안전 Import
try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

# ==========================================
# [기본 설정 및 세션 스테이트 초기화]
# ==========================================
st.set_page_config(page_title="역사과 AI 서논술형 수행평가 시스템", layout="wide")

# 권한 및 계정 세션 초기화
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_role = None  # 'admin', 'teacher', or 'student'
    st.session_state.user_id = None
    st.session_state.original_role = None  # 관리자가 다른 권한으로 테스트 진입 시 복귀용

# 계정 데이터 관리 (관리자 모드에서 수정 가능하도록 세션으로 이동)
if "teacher_credentials" not in st.session_state:
    st.session_state.teacher_credentials = {"id": "history_teacher", "pw": "2026"}

if "student_credentials" not in st.session_state:
    # 기본 학생 명단 초기화 (10101 ~ 10120, 초기 비번은 학번과 동일)
    st.session_state.student_credentials = {f"101{str(i).zfill(2)}": f"101{str(i).zfill(2)}" for i in range(1, 21)}

# 과제 및 루브릭 데이터 저장소
if "assessments" not in st.session_state:
    st.session_state.assessments = {
        "1970년대 산업화와 노동 현실 분석": {
            "rubric": """
            [만점: 10점]
            1. 역사적 사실의 정확성 (3점): 1970년대 경제개발과 노동 환경의 구체적 사실 언급 여부
            2. 관점의 균형성 및 비판적 사고 (4점): 경제적 성과와 그 이면에 존재했던 노동자의 고통을 균형 있게 분석했는가?
            3. 문맥적 이해 및 결론 도출 (3점): 제시된 사료와 연계하여 역사적 의미를 도출했는가?
            """,
            "max_score": 10
        }
    }

if "student_submissions" not in st.session_state:
    st.session_state.student_submissions = {}

# ==========================================
# [구글 Gemini AI 연동 함수 정의]
# ==========================================
def call_ai_grading(student_text, rubric_text, api_key=None):
    prompt = f"""
당신은 고등학교 역사 교사입니다. 아래의 [수행평가 루브릭]을 기반으로 학생이 작성한 [학생 제출물]을 공정하게 평가해 주세요.
반드시 아래의 JSON 포맷으로만 응답해 주세요. (다른 설명 없이 순수 JSON만 출력하세요)

[수행평가 루브릭]
{rubric_text}

[학생 제출물]
{student_text}

응답 JSON 포맷:
{{
  "score": (숫자, 예: 8.5),
  "deduction": "(감점 사유 및 부족했던 부분 요약)",
  "comment": "(학생에게 건네는 격려 및 보완 가이드 코멘트)"
}}
"""
    if not GENAI_AVAILABLE or not api_key:
        return {
            "score": 8.0,
            "deduction": "1970년대 구체적인 사건이나 법적 제도적 한계에 대한 언급이 조금 더 구체적이면 좋습니다.",
            "comment": "전반적인 흐름 이해가 훌륭합니다. 구체적 사료나 사례를 한 가지만 더 추가해 보세요!",
            "is_mock": True
        }
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        content = response.text.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("
