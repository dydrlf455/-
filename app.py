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
st.set_page_config(page_title="역사과 AI 서논술형 수행평가 시스템 (PDF 연동)", layout="wide")

# 교사 계정 정보 (하드코딩)
TEACHER_CREDENTIALS = {"id": "history_teacher", "pw": "2026"}

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_role = None  # 'teacher' or 'student'
    st.session_state.user_id = None

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

SAMPLE_CLASS_STUDENTS = [f"101{str(i).zfill(2)}" for i in range(1, 21)]

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
        login_type = st.radio("로그인 유형 선택", ["학생 로그인", "교사 로그인"])
        
        if login_type == "학생 로그인":
            st.caption("아이디와 비밀번호 모두 '학번'으로 입력하세요. (예: 10101)")
            s_id = st.text_input("학번 입력", max_chars=5)
            s_pw = st.text_input("비밀번호 입력", type="password", max_chars=5)
            
            if st.button("학생 입장하기"):
                if s_id and s_id == s_pw and s_id.isdigit():
                    st.session_state.logged_in = True
                    st.session_state.user_role = "student"
                    st.session_state.user_id = s_id
                    st.rerun()
                else:
                    st.error("학번과 비밀번호를 올바르게 일치시켜 입력해 주세요.")
        
        else:
            t_id = st.text_input("교사 아이디")
            t_pw = st.text_input("교사 비밀번호", type="password")
            if st.button("교사 입장하기"):
                if t_id == TEACHER_CREDENTIALS["id"] and t_pw == TEACHER_CREDENTIALS["pw"]:
                    st.session_state.logged_in = True
                    st.session_state.user_role = "teacher"
                    st.session_state.user_id = t_id
                    st.rerun()
                else:
                    st.error("교사 인증 정보가 일치하지 않습니다.")
    else:
        st.success(f"현재 접속자: **{st.session_state.user_id}** ({'교사' if st.session_state.user_role == 'teacher' else '학생'})")
        if st.button("로그아웃"):
            st.session_state.logged_in = False
            st.session_state.user_role = None
            st.session_state.user_id = None
            st.rerun()

# ==========================================
# [메인 화면 분기]
# ==========================================
if not st.session_state.logged_in:
    st.title("📚 역사과 서논술형 AI 수행평가 플랫폼")
    st.info("👈 왼쪽 사이드바에서 **학생 로그인** 또는 **교사 로그인**을 진행해 주세요.")

elif st.session_state.user_role == "student":
    student_id = st.session_state.user_id
    st.title(f"🎓 학생용 수행평가 작성실 (학번: {student_id})")
    
    assess_list = list(st.session_state.assessments.keys())
    selected_assess = st.selectbox("진행할 수행평가 선택", assess_list)
    current_rubric = st.session_state.assessments[selected_assess]["rubric"]
    
    with st.expander("📌 [필독] 이번 수행평가 채점 기준 (루브릭)", expanded=True):
        st.markdown(current_rubric)
    
    if student_id not in st.session_state.student_submissions:
        st.session_state.student_submissions[student_id] = {}
    if selected_assess not in st.session_state.student_submissions[student_id]:
        st.session_state.student_submissions[student_id][selected_assess] = {
            "draft": "",
            "status": "draft",
            "score": None,
            "deduction": "",
            "comment": ""
        }
    
    sub_data = st.session_state.student_submissions[student_id][selected_assess]
    is_submitted = (sub_data["status"] == "submitted")

    if is_submitted:
        st.warning("🔒 이 과제는 이미 **[최종 제출]** 처리가 완료되어 수정할 수 없습니다.")
        st.text_area("제출된 글 원문", value=sub_data["draft"], height=250, disabled=True)
        st.metric("가채점 최종 점수", f"{sub_data['score']} 점 / {st.session_state.assessments[selected_assess]['max_score']}점")
        st.info(f"**AI 피드백 요약:** {sub_data['comment']}")
    else:
        st.subheader("✍️ 서논술형 글쓰기 및 AI 가채점")
        user_input_text = st.text_area(
            "과제 내용을 작성하거나 붙여넣으세요:",
            value=sub_data["draft"],
            height=300,
            placeholder="예시: 1970년대 대한민국은 고도의 경제성장을 이룩하였으나, 저임금과 열악한 노동 환경이라는 어두운 이면이 존재했습니다..."
        )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🤖 AI 가채점 및 피드백 받기 (재업로드 가능)", use_container_width=True):
                if not user_input_text.strip():
                    st.warning("내용을 먼저 작성해 주세요.")
                else:
                    with st.spinner("Gemini AI가 루브릭에 맞춰 분석 중입니다..."):
                        ai_result = call_ai_grading(user_input_text, current_rubric, api_key_input)
                        sub_data["draft"] = user_input_text
                        sub_data["score"] = ai_result.get("score", 0)
                        sub_data["deduction"] = ai_result.get("deduction", "")
                        sub_data["comment"] = ai_result.get("comment", "")
                        st.rerun()

        with col2:
            if st.button("🚨 최종 제출하기 (이후 수정 불가)", type="primary", use_container_width=True):
                if not user_input_text.strip():
                    st.error("내용이 비어있습니다.")
                else:
                    ai_result = call_ai_grading(user_input_text, current_rubric, api_key_input)
                    sub_data["draft"] = user_input_text
                    sub_data["score"] = ai_result.get("score", 0)
                    sub_data["deduction"] = ai_result.get("deduction", "")
                    sub_data["comment"] = ai_result.get("comment", "")
                    sub_data["status"] = "submitted"
                    st.success("성공적으로 최종 제출되었습니다!")
                    st.rerun()

        if sub_data["score"] is not None:
            st.divider()
            st.subheader("📊 AI 가채점 및 피드백 결과")
            c1, c2 = st.columns([1, 2])
            with c1:
                st.metric("가채점 점수", f"{sub_data['score']} / {st.session_state.assessments[selected_assess]['max_score']}점")
            with c2:
                st.info(f"**감점 및 보완 포인트:**\n\n{sub_data['deduction']}")
            st.success(f"**AI 코멘트:**\n\n{sub_data['comment']}")

elif st.session_state.user_role == "teacher":
    st.title("👩‍🏫 교사용 대시보드 및 관리자 모드")
    
    tab_dashboard, tab_management, tab_seteuk = st.tabs([
        "📋 학급별 제출 대시보드", 
        "⚙️ 수행평가 및 루브릭 관리 (PDF 업로드 지원)", 
        "✨ 세특 초안 생성 및 열람"
    ])

    with tab_dashboard:
        st.subheader("학생 제출 현황 명렬표")
        assess_names = list(st.session_state.assessments.keys())
        selected_assess_t = st.selectbox("조회할 수행평가 선택", assess_names, key="dash_select")

        table_rows = []
        for sid in SAMPLE_CLASS_STUDENTS:
            sub_info = st.session_state.student_submissions.get(sid, {}).get(selected_assess_t, None)
            if not sub_info:
                status_icon = "❌ 미제출"
                score_str = "-"
            elif sub_info["status"] == "draft":
                status_icon = "📝 작성중"
                score_str = f"{sub_info.get('score', 0)}점 (가채점)"
            else:
                status_icon = "✅ 최종제출"
                score_str = f"{sub_info.get('score', 0)}점"
            
            table_rows.append({
                "학번": sid,
                "진행 상태": status_icon,
                "점수": score_str,
                "글자수": len(sub_info["draft"]) if sub_info else 0
            })
        
        df_status = pd.DataFrame(table_rows)
        st.dataframe(df_status, use_container_width=True, hide_index=True)

    with tab_management:
        st.subheader("📁 수행평가 및 루브릭 등록 (PDF 업로드 기능 포함)")
        
        # 세션에 임시로 저장할 PDF 추출 텍스트 관리
        if "extracted_pdf_text" not in st.session_state:
            st.session_state.extracted_pdf_text = ""

        # PDF 파일 업로더 추가
        uploaded_pdf = st.file_uploader("채점 기준(루브릭)이 담긴 PDF 파일을 업로드하세요.", type=["pdf"])
        
        if uploaded_pdf is not None:
            if PYPDF_AVAILABLE:
                try:
                    reader = PdfReader(BytesIO(uploaded_pdf.read()))
                    extracted_text = ""
                    for page in reader.pages:
                        text = page.extract_text()
                        if text:
                            extracted_text += text + "\n"
                    
                    if extracted_text.strip():
                        st.session_state.extracted_pdf_text = extracted_text.strip()
                        st.success("PDF 파일에서 채점 기준 텍스트를 성공적으로 추출했습니다! 아래 입력창에 자동으로 반영되었습니다.")
                    else:
                        st.warning("PDF에서 텍스트를 추출하지 못했습니다. (이미지 형태의 PDF일 수 있습니다.)")
                except Exception as e:
                    st.error(f"PDF 파일 읽기 오류: {str(e)}")
            else:
                st.error("pypdf 라이브러리가 설치되지 않았습니다.")

        # 등록 폼
        with st.form("new_assessment_form"):
            new_title = st.text_input("수행평가명", placeholder="예: 5·18 민주 운동의 역사적 의의 서술")
            new_max_score = st.number_input("만점 점수", min_value=1, max_value=100, value=10)
            
            # 텍스트 에어리어의 기본값을 PDF에서 추출한 텍스트로 설정
            default_rubric_content = st.session_state.extracted_pdf_text if st.session_state.extracted_pdf_text else "평가 요소별 배점 및 세부 기준을 직접 입력하거나 위에서 PDF를 업로드하세요."
            new_rubric = st.text_area("루브릭 채점 기준 (PDF 업로드 시 자동 입력됨)", value=default_rubric_content, height=200)
            
            submitted_new = st.form_submit_button("수행평가 최종 등록")
            
            if submitted_new:
                if new_title and new_rubric:
                    st.session_state.assessments[new_title] = {
                        "rubric": new_rubric,
                        "max_score": new_max_score
                    }
                    # 등록 후 임시 추출 텍스트 초기화
                    st.session_state.extracted_pdf_text = ""
                    st.success(f"'{new_title}' 수행평가가 성공적으로 등록되었습니다!")
                    st.rerun()
                else:
                    st.warning("수행평가명과 루브릭 내용을 모두 입력해 주세요.")
        
        st.divider()
        st.markdown("### 📋 현재 등록된 수행평가 목록")
        for title, info in st.session_state.assessments.items():
            with st.expander(f"📁 {title} (만점: {info['max_score']}점)"):
                st.markdown(info["rubric"])

    with tab_seteuk:
        st.subheader("최종 제출 학생 원문 확인 및 세특 자동 생성")
        assess_names = list(st.session_state.assessments.keys())
        selected_assess_s = st.selectbox("수행평가 선택", assess_names, key="seteuk_select")

        submitted_students = [
            sid for sid, data in st.session_state.student_submissions.items()
            if selected_assess_s in data and data[selected_assess_s]["status"] == "submitted"
        ]

        if not submitted_students:
            st.info("아직 최종 제출을 완료한 학생이 없습니다.")
        else:
            chosen_student = st.selectbox("최종 제출한 학생 선택 (학번)", submitted_students)
            student_work = st.session_state.student_submissions[chosen_student][selected_assess_s]

            col_w1, col_w2 = st.columns(2)
            with col_w1:
                st.markdown(f"**[학번: {chosen_student}] 학생 원문**")
                st.text_area("원문 내용", value=student_work["draft"], height=300, disabled=True, key="student_original_text")
                st.metric("획득 점수", f"{student_work.get('score', 0)}점")

            with col_w2:
                st.markdown("**[2022 개정 교육과정 기반 세특 초안 생성]**")
                if st.button("✨ 학생 원문 기반 세특 초안 자동 생성", type="primary", use_container_width=True):
                    with st.spinner("Gemini가 세특 초안을 생성 중입니다..."):
                        generated_text = call_ai_seteuk(
                            student_work["draft"],
                            student_work.get("score", 0),
                            selected_assess_s,
                            api_key_input
                        )
                        student_work["se-teuk"] = generated_text
                        st.rerun()

                edited_seteuk = st.text_area(
                    "생성된 세특 초안 편집기 (교사 수정 가능):",
                    value=student_work.get("se-teuk", ""),
                    height=250
                )

                if st.button("💾 세특 수정사항 저장"):
                    student_work["se-teuk"] = edited_seteuk
                    st.success("세특 내용이 저장되었습니다!")
