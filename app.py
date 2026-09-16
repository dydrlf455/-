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
        
        # ⚠️ 이 부분이 오류가 났던 곳입니다 (한 줄로 깔끔하게 처리)
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        return json.loads(content)
    except Exception as e:
        return {
            "score": 0.0,
            "deduction": f"AI 분석 중 오류 발생: {str(e)}",
            "comment": "API 키를 확인하거나 잠시 후 다시 시도해 주세요.",
            "is_mock": True
        }

def call_ai_seteuk(student_text, score, assessment_name, api_key=None):
    prompt = f"""
당신은 고등학교 역사 교사입니다. 2022 개정 교육과정 역사과 성취기준 및 핵심 역량(역사적 사고력, 역사적 탐구 및 소통력 등)을 바탕으로 아래 학생의 세부능력 및 특기사항(세특) 초안을 작성해 주세요.

[절대 규칙 - 환각 배제]
1. 아래 제공된 [학생 원문 내용]에 명시적으로 드러난 사실, 역사적 개념, 탐구 내용만을 기반으로 작성할 것.
2. 학생 원문에 없는 내용은 절대 지어내지 말 것.
3. 분량은 학교생활기록부 기재 요령에 맞게 500바이트 내외(3~5문장)로 간결하게 서술할 것.

[수행평가명]: {assessment_name}
[획득 점수]: {score}점
[학생 원문 내용]:
{student_text}
"""
    if not GENAI_AVAILABLE or not api_key:
        return f"[모의 세특 생성 결과] ({assessment_name} / {score}점 기반)\n수행평가 과정에서 해당 역사적 주제에 대한 뛰어난 탐구력과 균형 잡힌 시각을 보여줌. 역사적 사실을 정확하게 이해하고 논리적으로 서술하는 역량이 우수함."

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"세특 생성 중 오류 발생: {str(e)}"

# ==========================================
# [사이드바: 로그인 및 환경설정]
# ==========================================
with st.sidebar:
    st.header("🔑 로그인 및 설정")
    api_key_input = st.text_input("구글 AI 스튜디오 API 키 (Gemini API Key, 선택입력)", type="password", help="입력하지 않으면 기본 모의 AI 엔진이 작동합니다.")
    if api_key_input:
        os.environ["GEMINI_API_KEY"] = api_key_input

    st.divider()

    if not st.session_state.logged_in:
        login_type = st.radio("로그인 유형 선택", ["학생 로그인", "교사 로그인", "👑 관리자 로그인"])
        
        if login_type == "학생 로그인":
            st.caption("아이디와 비밀번호 모두 '학번'으로 입력하세요. (예: 10101)")
            s_id = st.text_input("학번 입력")
            s_pw = st.text_input("비밀번호 입력", type="password")
            
            if st.button("학생 입장하기"):
                if s_id in st.session_state.student_credentials and st.session_state.student_credentials[s_id] == s_pw:
                    st.session_state.logged_in = True
                    st.session_state.user_role = "student"
                    st.session_state.user_id = s_id
                    st.rerun()
                else:
                    st.error("학번과 비밀번호를 확인해 주세요. (미등록 학생일 수 있습니다)")
        
        elif login_type == "교사 로그인":
            t_id = st.text_input("교사 아이디")
            t_pw = st.text_input("교사 비밀번호", type="password")
            if st.button("교사 입장하기"):
                if t_id == st.session_state.teacher_credentials["id"] and t_pw == st.session_state.teacher_credentials["pw"]:
                    st.session_state.logged_in = True
                    st.session_state.user_role = "teacher"
                    st.session_state.user_id = t_id
                    st.rerun()
                else:
                    st.error("교사 인증 정보가 일치하지 않습니다.")

        elif login_type == "👑 관리자 로그인":
            a_id = st.text_input("관리자 아이디")
            a_pw = st.text_input("관리자 비밀번호", type="password")
            if st.button("관리자 입장하기"):
                if a_id == "dydrlf455" and a_pw == "dudth0905!":
                    st.session_state.logged_in = True
                    st.session_state.user_role = "admin"
                    st.session_state.user_id = "SuperAdmin"
                    st.rerun()
                else:
