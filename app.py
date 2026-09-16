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
# [데이터 파일 저장/불러오기 기능 설정]
# ==========================================
DATA_FILE = "school_app_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return None
    return None

def save_data():
    data = {
        "teacher_credentials": st.session_state.teacher_credentials,
        "student_credentials": st.session_state.student_credentials,
        "assessments": st.session_state.assessments,
        "student_submissions": st.session_state.student_submissions
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# ==========================================
# [기본 설정 및 세션 스테이트 초기화]
# ==========================================
st.set_page_config(page_title="역사과 AI 서논술형 수행평가 시스템", layout="wide")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_role = None
    st.session_state.user_id = None
    st.session_state.original_role = None

app_data = load_data()

if app_data:
    if "teacher_credentials" not in st.session_state:
        st.session_state.teacher_credentials = app_data.get("teacher_credentials")
    if "student_credentials" not in st.session_state:
        st.session_state.student_credentials = app_data.get("student_credentials")
    if "assessments" not in st.session_state:
        st.session_state.assessments = app_data.get("assessments")
    if "student_submissions" not in st.session_state:
        st.session_state.student_submissions = app_data.get("student_submissions")
else:
    if "teacher_credentials" not in st.session_state:
        st.session_state.teacher_credentials = {"id": "history_teacher", "pw": "2026"}
    if "student_credentials" not in st.session_state:
        st.session_state.student_credentials = {f"101{str(i).zfill(2)}": f"101{str(i).zfill(2)}" for i in range(1, 21)}
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
    save_data()

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
  "item_deductions": "(루브릭의 각 평가 요소별로 어떤 부분이 충족되었고 어떤 부분에서 감점되었는지 항목별로 상세히 서술)",
  "comment": "(학생에게 건네는 격려 및 보완 가이드 코멘트)"
}}
"""
    if not GENAI_AVAILABLE or not api_key:
        return {
            "score": 8.0,
            "item_deductions": "- 역사적 사실의 정확성 (2.5/3점): 구체적 사실 언급은 있으나 일부 연도 누락\n- 관점의 균형성 (3.0/4점): 노동자 고통 서술이 다소 부족함\n- 결론 도출 (2.5/3점): 사료 연계 분석 양호",
            "comment": "전반적인 흐름 이해가 훌륭합니다. 구체적 사료나 사례를 한 가지만 더 추가해 보세요!",
            "is_mock": True
        }
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3.6-flash")
        response = model.generate_content(prompt)
        content = response.text.strip()
        
        backticks = "`" * 3
        if content.startswith(f"{backticks}json"):
            content = content[7:-3].strip()
        elif content.startswith(backticks):
            content = content[3:-3].strip()
            
        return json.loads(content)
    except Exception as e:
        return {
            "score": 0.0,
            "item_deductions": f"AI 분석 중 오류 발생: {str(e)}",
            "comment": "API 키를 확인하거나 잠시 후 다시 시도해 주세요.",
            "is_mock": True
        }

def call_ai_table_parser(raw_text, api_key=None):
    prompt = f"""
다음은 고등학교 역사 과목 수행평가 루브릭(채점 기준) 내용입니다. 
이 내용을 교사가 보기 쉽도록 '평가 요소', '배점', '세부 기준' 항목으로 나누어 깔끔한 마크다운 표(Markdown Table) 형식으로 정리해 주세요. 다른 서론이나 설명 없이 오직 마크다운 표 형식만 출력하세요.

[루브릭 원문]
{raw_text}
"""
    if not GENAI_AVAILABLE or not api_key:
        return "| 평가 요소 | 배점 | 세부 기준 |\n|---|---|---|\n| 역사적 사실의 정확성 | 3점 | 1970년대 경제개발과 노동 환경 구체적 사실 |\n| 관점의 균형성 | 4점 | 경제 성과와 노동자 고통 균형 분석 |\n| 문맥적 이해 | 3점 | 사료 연계 역사적 의미 도출 |"

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3.6-flash")
        response = model.generate_content(prompt)
        return response.text.strip()
    except:
        return raw_text

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
        model = genai.GenerativeModel("gemini-3.6-flash")
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
                    st.error("관리자 인증 정보가 일치하지 않습니다.")

    else:
        st.success(f"현재 접속자: **{st.session_state.user_id}** ({st.session_state.user_role})")
        
        if st.session_state.original_role == "admin":
            if st.button("👑 관리자 모드로 복귀", type="primary"):
                st.session_state.user_role = "admin"
                st.session_state.user_id = "SuperAdmin"
                st.session_state.original_role = None
                st.rerun()

        if st.button("로그아웃"):
            st.session_state.logged_in = False
            st.session_state.user_role = None
            st.session_state.user_id = None
            st.session_state.original_role = None
            st.rerun()

# ==========================================
# [메인 화면 분기]
# ==========================================
if not st.session_state.logged_in:
    st.title("📚 역사과 서논술형 AI 수행평가 플랫폼")
    st.info("👈 왼쪽 사이드바에서 로그인을 진행해 주세요.")

# ------------------------------------------
# 1. 관리자(Admin) 모드
# ------------------------------------------
elif st.session_state.user_role == "admin":
    st.title("👑 최고 관리자 대시보드")
    st.info("이곳에서 교사 및 학생 계정을 관리하고, 각 권한별 화면을 테스트해 볼 수 있습니다.")

    tab_accounts, tab_test = st.tabs(["🔐 계정 관리 (엑셀 일괄 등록 및 양식 다운로드)", "🎭 권한 테스트 (Impersonation)"])

    with tab_accounts:
        st.subheader("👨‍🏫 교사 계정 설정")
        new_t_id = st.text_input("교사 아이디", value=st.session_state.teacher_credentials["id"])
        new_t_pw = st.text_input("교사 비밀번호", value=st.session_state.teacher_credentials["pw"])
        if st.button("교사 계정 업데이트"):
            st.session_state.teacher_credentials["id"] = new_t_id
            st.session_state.teacher_credentials["pw"] = new_t_pw
            save_data()
            st.success("교사 계정 정보가 성공적으로 변경되었습니다.")
        
        st.divider()

        st.subheader("🎓 학생 계정 관리 (양식 다운로드 및 일괄 업로드)")
        
        st.markdown("#### 📥 학생 등록용 엑셀(CSV) 양식 다운로드")
        st.caption("아래 버튼을 눌러 예시 양식을 다운로드한 후, 학생들의 학번과 비밀번호를 입력해 주세요.")
        
        sample_df = pd.DataFrame({
            "학번": ["10101", "10102", "10103"],
            "비밀번호": ["10101", "10102", "10103"]
        })
        sample_csv = sample_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        
        st.download_button(
            label="📄 학생 일괄 등록 엑셀(CSV) 양식 다운로드",
            data=sample_csv,
            file_name="student_template.csv",
            mime="text/csv",
            use_container_width=True
        )

        st.markdown("---")
        st.markdown("#### 📁 작성한 엑셀(CSV) 파일 일괄 업로드")
        uploaded_excel = st.file_uploader("학생 명단 파일 업로드 (CSV)", type=["csv"])
        
        if uploaded_excel is not None:
            try:
                df_upload = pd.read_csv(uploaded_excel)
                if "학번" in df_upload.columns and "비밀번호" in df_upload.columns:
                    count_added = 0
                    for _, row in df_upload.iterrows():
                        s_id = str(row["학번"]).strip()
                        s_pw = str(row["비밀번호"]).strip()
                        if s_id and s_pw:
                            st.session_state.student_credentials[s_id] = s_pw
                            count_added += 1
                    save_data()
                    st.success(f"총 {count_added}명의 학생 계정이 성공적으로 일괄 등록되었습니다!")
                    st.rerun()
                else:
                    st.error("업로드한 파일에 '학번' 또는 '비밀번호' 컬럼이 존재하지 않습니다. 제공된 양식 파일을 사용해 주세요.")
            except Exception as e:
                st.error(f"파일 읽기 오류: {str(e)}")

        st.markdown("---")
        st.markdown("#### ✍️ 개별 학생 계정 추가 및 수정")
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            m_s_id = st.text_input("학생 학번 (예: 10121)")
        with col_s2:
            m_s_pw = st.text_input("비밀번호 (기본 설정 시 학번과 동일하게 입력)")
        
        if st.button("개별 학생 계정 저장/추가"):
            if m_s_id and m_s_pw:
                st.session_state.student_credentials[m_s_id] = m_s_pw
                save_data()
                st.success(f"학번 '{m_s_id}' 학생 계정이 저장되었습니다.")
            else:
                st.warning("학번과 비밀번호를 모두 입력해 주세요.")
        
        with st.expander("현재 등록된 전체 학생 명단 확인"):
            df_students = pd.DataFrame(
                list(st.session_state.student_credentials.items()), 
                columns=["학번", "비밀번호"]
            ).sort_values("학번").reset_index(drop=True)
            st.dataframe(df_students, use_container_width=True)

    with tab_test:
        st.subheader("화면 권한 테스트")
        st.markdown("현재 관리자 로그인 상태를 유지하면서 교사나 특정 학생의 화면으로 진입합니다.")
        
        col_test1, col_test2 = st.columns(2)
        with col_test1:
            st.markdown("#### 교사용 화면 들어가기")
            if st.button("👨‍🏫 교사 모드로 진입", use_container_width=True):
                st.session_state.original_role = "admin"
                st.session_state.user_role = "teacher"
                st.session_state.user_id = st.session_state.teacher_credentials["id"]
                st.rerun()

        with col_test2:
            st.markdown("#### 학생용 화면 들어가기")
            test_target_student = st.selectbox("테스트할 학생 학번 선택", sorted(list(st.session_state.student_credentials.keys())))
            if st.button("🎓 선택한 학생 모드로 진입", use_container_width=True):
                st.session_state.original_role = "admin"
                st.session_state.user_role = "student"
                st.session_state.user_id = test_target_student
                st.rerun()

# ------------------------------------------
# 2. 학생(Student) 모드
# ------------------------------------------
elif st.session_state.user_role == "student":
    student_id = st.session_state.user_id
    st.title(f"🎓 학생용 수행평가 작성실 (학번: {student_id})")
    
    assess_list = list(st.session_state.assessments.keys())
    
    if not assess_list:
        st.warning("현재 등록된 수행평가가 없습니다. 교사에게 문의하세요.")
    else:
        selected_assess = st.selectbox("진행할 수행평가 선택", assess_list)
        current_rubric_table = st.session_state.assessments[selected_assess].get("rubric_table", st.session_state.assessments[selected_assess]["rubric"])
        
        with st.expander("📌 [필독] 이번 수행평가 채점 기준 (루브릭 표)", expanded=True):
            st.markdown(current_rubric_table)
        
        if student_id not in st.session_state.student_submissions:
            st.session_state.student_submissions[student_id] = {}
        if selected_assess not in st.session_state.student_submissions[student_id]:
            st.session_state.student_submissions[student_id][selected_assess] = {
                "draft": "",
                "status": "draft",
                "score": None,
                "item_deductions": "",
                "comment": ""
            }
        
        sub_data = st.session_state.student_submissions[student_id][selected_assess]
        is_submitted = (sub_data["status"] == "submitted")

        if is_submitted:
            st.warning("🔒 이 과제는 이미 **[최종 제출]** 처리가 완료되어 수정할 수 없습니다.")
            st.text_area("제출된 글 원문", value=sub_data["draft"], height=250, disabled=True)
            st.metric("가채점 최종 점수", f"{sub_data['score']} 점 / {st.session_state.assessments[selected_assess]['max_score']}점")
            st.info(f"**항목별 감점 및 보완 포인트:**\n\n{sub_data.get('item_deductions', '')}")
            st.success(f"**AI 코멘트:**\n\n{sub_data['comment']}")
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
                        with st.spinner("Gemini AI가 루브릭 기준 항목별로 분석 중입니다..."):
                            ai_result = call_ai_grading(user_input_text, current_rubric_table, os.environ.get("GEMINI_API_KEY"))
                            sub_data["draft"] = user_input_text
                            sub_data["score"] = ai_result.get("score", 0)
                            sub_data["item_deductions"] = ai_result.get("item_deductions", "")
                            sub_data["comment"] = ai_result.get("comment", "")
                            save_data()
                            st.rerun()

            with col2:
                if st.button("🚨 최종 제출하기 (이후 수정 불가)", type="primary", use_container_width=True):
                    if not user_input_text.strip():
                        st.error("내용이 비어있습니다.")
                    else:
                        ai_result = call_ai_grading(user_input_text, current_rubric_table, os.environ.get("GEMINI_API_KEY"))
                        sub_data["draft"] = user_input_text
                        sub_data["score"] = ai_result.get("score", 0)
                        sub_data["item_deductions"] = ai_result.get("item_deductions", "")
                        sub_data["comment"] = ai_result.get("comment", "")
                        sub_data["status"] = "submitted"
                        save_data()
                        st.success("성공적으로 최종 제출되었습니다!")
                        st.rerun()

            if sub_data["score"] is not None:
                st.divider()
                st.subheader("📊 AI 가채점 및 피드백 결과")
                c1, c2 = st.columns([1, 2])
                with c1:
                    st.metric("가채점 점수", f"{sub_data['score']} / {st.session_state.assessments[selected_assess]['max_score']}점")
                with c2:
                    st.info(f"**항목별 감점 및 보완 포인트:**\n\n{sub_data.get('item_deductions', '')}")
                st.success(f"**AI 코멘트:**\n\n{sub_data['comment']}")

# ------------------------------------------
# 3. 교사(Teacher) 모드
# ------------------------------------------
elif st.session_state.user_role == "teacher":
    st.title("👩‍🏫 교사용 대시보드 및 관리자 모드")
    
    tab_dashboard, tab_management, tab_seteuk = st.tabs([
        "📋 학급별 제출 대시보드 (상세 팝업 및 강제 제출 지원)", 
        "⚙️ 수행평가 및 루브릭 관리 (자동 표 변환)", 
        "✨ 세특 초안 생성 및 열람"
    ])

    with tab_dashboard:
        st.subheader("학생 제출 현황 및 가채점/최종 점수 확인")
        st.info("💡 **팁:** 아래에서 학번을 선택하면 학생의 원문, 항목별 감점 사유 확인과 함께 **교사 권한으로 최종 제출 처리**를 진행할 수 있습니다.")
        
        assess_names = list(st.session_state.assessments.keys())
        if not assess_names:
            st.info("등록된 수행평가가 없습니다. 탭을 이동해 새 수행평가를 등록해 주세요.")
        else:
            selected_assess_t = st.selectbox("조회할 수행평가 선택", assess_names, key="dash_select")

            table_rows = []
            current_students = sorted(list(st.session_state.student_credentials.keys()))
            for sid in current_students:
                sub_info = st.session_state.student_submissions.get(sid, {}).get(selected_assess_t, None)
                if not sub_info:
                    status_icon = "❌ 미제출"
                    score_str = "-"
                elif sub_info["status"] == "draft":
                    status_icon = "📝 작성중"
                    score_str = f"{sub_info.get('score', 0)}점 (가채점 상태)"
                else:
                    status_icon = "✅ 최종제출"
                    score_str = f"{sub_info.get('score', 0)}점 (최종)"
                
                table_rows.append({
                    "학번": sid,
                    "진행 상태": status_icon,
                    "점수": score_str,
                    "글자수": len(sub_info["draft"]) if sub_info else 0
                })
            
            df_status = pd.DataFrame(table_rows)
            st.dataframe(df_status, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("🔍 학생별 제출물 상세 조회 및 최종 제출 처리")
            target_sid = st.selectbox("상세 내용을 확인할 학생 학번 선택", current_students, key="popup_sid")
            target_sub = st.session_state.student_submissions.get(target_sid, {}).get(selected_assess_t, None)

            if not target_sub or not target_sub["draft"]:
                st.warning(f"학번 {target_sid} 학생은 아직 해당 과제를 작성하지 않았습니다.")
            else:
                with st.container(border=True):
                    st.markdown(f"### 📋 [학번: {target_sid}] 학생 상세 제출 및 피드백 리포트")
                    col_p1, col_p2 = st.columns(2)
                    with col_p1:
                        st.markdown("**✍️ 학생 작성 원문**")
                        st.text_area("원문", value=target_sub["draft"], height=250, disabled=True, key=f"popup_draft_{target_sid}")
                    with col_p2:
                        st.markdown("**🤖 AI 평가 및 감점 리포트**")
                        current_status_label = "✅ 최종 제출 완료" if target_sub['status']=='submitted' else "📝 작성/가채점 중 (미제출)"
                        st.metric("현재 상태 및 점수", f"{target_sub.get('score', 0)}점 / {st.session_state.assessments[selected_assess_t]['max_score']}점 ({current_status_label})")
                        st.info(f"**항목별 감점 분석:**\n\n{target_sub.get('item_deductions', '내용 없음')}")
                        st.success(f"**학생용 코멘트:**\n\n{target_sub.get('comment', '내용 없음')}")

                    st.divider()
                    # 교사 권한 최종 제출 처리 버튼 영역
                    col_btn1, col_btn2 = st.columns([2, 1])
                    with col_btn1:
                        if target_sub['status'] == 'submitted':
                            st.success("현재 이 학생의 과제는 **최종 제출** 상태입니다.")
                        else:
                            st.warning("현재 학생이 과제를 작성했으나 아직 최종 제출을 누르지 않은 상태입니다.")
                    with col_btn2:
                        if target_sub['status'] != 'submitted':
                            if st.button("🚨 교사 권한으로 최종 제출 처리", type="primary", use_container_width=True):
                                target_sub['status'] = 'submitted'
                                save_data()
                                st.success(f"학번 {target_sid} 학생 과제가 최종 제출 처리되었습니다!")
                                st.rerun()
                        else:
                            if st.button("↩️ 최종 제출 취소 (작성중으로 변경)", use_container_width=True):
                                target_sub['status'] = 'draft'
                                save_data()
                                st.info(f"학번 {target_sid} 학생 과제가 작성 중 상태로 변경되었습니다.")
                                st.rerun()

    with tab_management:
        st.subheader("📁 수행평가 및 루브릭 등록 (줄글 ➡️ 표 자동 변환)")
        
        if "extracted_pdf_text" not in st.session_state:
            st.session_state.extracted_pdf_text = ""

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
                        with st.spinner("AI가 PDF 루브릭을 깔끔한 표 형식으로 자동 변환 중입니다..."):
                            table_formatted = call_ai_table_parser(extracted_text.strip(), os.environ.get("GEMINI_API_KEY"))
                        st.session_state.extracted_pdf_text = table_formatted
                        st.success("PDF 루브릭 추출 및 표 형식 변환 완료! 아래 입력창에 적용되었습니다.")
                    else:
                        st.warning("PDF에서 텍스트를 추출하지 못했습니다.")
                except Exception as e:
                    st.error(f"PDF 파일 읽기 오류: {str(e)}")
            else:
                st.error("pypdf 라이브러리가 설치되지 않았습니다.")

        with st.form("new_assessment_form"):
            new_title = st.text_input("수행평가명", placeholder="예: 5·18 민주 운동의 역사적 의의 서술")
            new_max_score = st.number_input("만점 점수", min_value=1, max_value=100, value=10)
            
            default_rubric_content = st.session_state.extracted_pdf_text if st.session_state.extracted_pdf_text else "| 평가 요소 | 배점 | 세부 기준 |\n|---|---|---|\n| 항목명 | 배점 | 기준 내용을 적어주세요 |"
            new_rubric = st.text_area("루브릭 채점 기준 (표 형식으로 자동 변환됨)", value=default_rubric_content, height=220)
            
            submitted_new = st.form_submit_button("수행평가 최종 등록")
            
            if submitted_new:
                if new_title and new_rubric:
                    st.session_state.assessments[new_title] = {
                        "rubric": new_rubric,
                        "rubric_table": new_rubric,
                        "max_score": new_max_score
                    }
                    st.session_state.extracted_pdf_text = ""
                    save_data()
                    st.success(f"'{new_title}' 수행평가가 성공적으로 등록되었습니다!")
                    st.rerun()
                else:
                    st.warning("수행평가명과 루브릭 내용을 모두 입력해 주세요.")
        
        st.divider()
        st.markdown("### 📋 현재 등록된 수행평가 목록 (표 루브릭 확인)")
        for title, info in st.session_state.assessments.items():
            with st.expander(f"📁 {title} (만점: {info['max_score']}점)"):
                st.markdown(info.get("rubric_table", info["rubric"]))

    with tab_seteuk:
        st.subheader("최종 제출 학생 원문 확인 및 세특 자동 생성")
        assess_names = list(st.session_state.assessments.keys())
        if not assess_names:
            st.info("등록된 수행평가가 없습니다.")
        else:
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
                                os.environ.get("GEMINI_API_KEY")
                            )
                            student_work["se-teuk"] = generated_text
                            save_data()
                            st.rerun()

                    edited_seteuk = st.text_area(
                        "생성된 세특 초안 편집기 (교사 수정 가능):",
                        value=student_work.get("se-teuk", ""),
                        height=250
                    )

                    if st.button("💾 세특 수정사항 저장"):
                        student_work["se-teuk"] = edited_seteuk
                        save_data()
                        st.success("세특 내용이 저장되었습니다!")
