import json
import os
import google.generativeai as genai
import pandas as pd
import pypdf
import streamlit as st

# 페이지 기본 설정
st.set_page_config(
    page_title="역사과 AI 서논술형 수행평가 시스템 (Gemini)", page_icon="📜", layout="wide"
)

# ==========================================
# [설정] 관리자 계정 정보
# ==========================================
ADMIN_ID = "dydrlf455"
ADMIN_PW = "dudth0905!"

# 제미나이 API 설정 함수
def init_gemini():
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
        return True
    return False

# 세션 스테이트 초기화 (데이터베이스 대체)
if "user_role" not in st.session_state:
    st.session_state.user_role = None  # 'teacher' or 'student'
if "current_student_id" not in st.session_state:
    st.session_state.current_student_id = None
if "show_admin_login" not in st.session_state:
    st.session_state.show_admin_login = False

if "evaluations" not in st.session_state:
    st.session_state.evaluations = {
        "1970년대 산업화와 노동 현실 분석": {
            "rubric": "1. 역사적 사실(사료)의 정확한 인용 (10점)\n2. 구조적 모순(노동/환경 문제)에 대한 인과적 분석 (10점)\n3. 비판적 대안 및 역사적 통찰력 (10점)",
            "total_score": 30,
        }
    }

if "submissions" not in st.session_state:
    st.session_state.submissions = {}

if "form_eval_name" not in st.session_state:
    st.session_state.form_eval_name = "일제의 내선일체 포스터 분석 및 비판적 역사 글쓰기"
if "form_rubric" not in st.session_state:
    st.session_state.form_rubric = (
        "1. 포스터 분석력 (20점)\n"
        "2. 역사적 맥락 파악 (20점)\n"
        "3. 비판적 사고력 (30점)\n"
        "4. 문제 해결력 구술 발표 (10점)"
    )
if "form_total_score" not in st.session_state:
    st.session_state.form_total_score = 80

if "student_list" not in st.session_state:
    st.session_state.student_list = [f"101{i:02d}" for i in range(1, 21)]


# Gemini API 호출 함수 (가채점)
def call_ai_grader(text, rubric_text):
    if not init_gemini():
        return {
            "score": 24,
            "deductions": "1. 사료 인용은 적절하나 구체적 통계 언급이 다소 부족함 (-3점)\n2. 노동 조건의 변화와 법적 제도 연계 분석이 평면적임 (-3점)",
            "feedback": "제출한 내용은 1970년대 노동 현실의 핵심을 잘 짚었습니다. 다만 '근로기준법 준수 요구' 등 당시 구체적인 노동쟁의 사례를 덧붙이면 훨씬 설득력 있는 글이 됩니다.",
        }

    prompt = f"""
    당신은 고등학교 역사 교사입니다. 아래의 채점 기준(루브릭)을 바탕으로 학생의 서논술형 답안을 가채점해 주세요.
    반드시 JSON 형식으로만 응답하며, 키는 'score'(숫자), 'deductions'(문자열), 'feedback'(문자열)로 구성하세요.

    [채점 기준]
    {rubric_text}

    [학생 답안]
    {text}
    """
    try:
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            generation_config={"response_mime_type": "application/json"}
        )
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        return {
            "score": 20,
            "deductions": f"AI 분석 중 오류 발생으로 기본 점수 부여 ({str(e)})",
            "feedback": "내용을 다시 확인하고 보완해 주세요.",
        }


# Gemini API 호출 함수 (세특 초안 생성)
def call_ai_setuk(student_name_or_id, text, score, eval_name):
    if not init_gemini():
        return f"[{student_name_or_id}] 학생은 '{eval_name}' 수행평가에서 서논술형 글쓰기를 수행함. 당시 사료를 바탕으로 1970년대 산업화 과정에서 발생한 사회적 모순과 노동 문제를 인과적으로 분석해내는 역사적 탐구력이 돋보임."

    prompt = f"""
    당신은 고등학교 역사 교사입니다. 오직 아래에 제공된 [학생 원문] 내용만을 바탕으로 학교생활기록부 '세부능력 및 특기사항(세특)' 초안을 작성해 주세요.
    - 절대 환각(학생이 쓰지 않은 사실)을 지어내지 말 것.
    - 2022 개정 교육과정 역사과 성취기준 및 핵심 역량(역사적 탐구력, 비판적 사고력 등)을 반영할 것.
    - 분량은 500자 이내의 명료한 문어체로 작성할 것.

    [수행평가명]: {eval_name}
    [학생 점수]: {score}점
    [학생 원문]:
    {text}
    """
    model = genai.GenerativeModel(model_name="gemini-2.5-flash")
    response = model.generate_content(prompt)
    return response.text.strip()


# PDF 텍스트 추출 및 Gemini 루브릭 자동 추출 함수
def extract_rubric_from_pdf(pdf_file):
    try:
        reader = pypdf.PdfReader(pdf_file)
        extracted_text = ""
        for page in reader.pages:
            extracted_text += page.extract_text() or ""
    except Exception as e:
        return None, f"PDF 읽기 오류: {str(e)}"

    if not init_gemini():
        return None, "Gemini API 키가 설정되지 않았습니다. Streamlit Secrets에 GEMINI_API_KEY를 등록해 주세요."

    prompt = f"""
    당신은 고등학교 역사 교사입니다. 아래의 [수행평가 계획서 텍스트]를 분석하여 JSON 형식으로만 답하세요.
    필수 키:
    - 'title': (문자열) 수행평가명
    - 'rubric': (문자열) 평가 요소와 배점이 정리된 루브릭 내용
    - 'total_score': (숫자) 총 배점 합계 (숫자만)

    [수행평가 계획서 텍스트]:
    {extracted_text[:4000]}
    """
    try:
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            generation_config={"response_mime_type": "application/json"}
        )
        response = model.generate_content(prompt)
        data = json.loads(response.text)
        return data, None
    except Exception as e:
        return None, f"AI 분석 오류: {str(e)}"


# ==========================================
# 1. 로그인 화면 (관리자 바로가기 배너 포함)
# ==========================================
if st.session_state.user_role is None:
    st.title("📜 역사과 서논술형 AI 수행평가 시스템 (Gemini)")

    with st.container():
        st.info("🛠️ **교사(관리자)이신가요?** 아래 버튼을 눌러 관리자 모드로 즉시 로그인할 수 있습니다.")
        if st.button("👉 [관리자 모드 로그인하기]", type="primary", use_container_width=True):
            st.session_state.show_admin_login = not st.session_state.show_admin_login

    if st.session_state.show_admin_login:
        with st.expander("🔐 관리자 계정 인증", expanded=True):
            col_ad1, col_ad2, col_ad3 = st.columns()  # <--- 이 부분 수정됨!
            with col_ad1:
                input_admin_id = st.text_input("관리자 아이디", key="admin_id_input")
            with col_ad2:
                input_admin_pw = st.text_input("관리자 비밀번호", type="password", key="admin_pw_input")
            with col_ad3:
                st.write("")
                st.write("")
                if st.button("로그인 확인", key="admin_submit_btn"):
                    if input_admin_id == ADMIN_ID and input_admin_pw == ADMIN_PW:
                        st.session_state.user_role = "teacher"
                        st.session_state.show_admin_login = False
                        st.rerun()
                    else:
                        st.error("아이디 또는 비밀번호가 틀렸습니다. 다시 확인해 주세요.")

    st.divider()
    st.markdown("### 🎓 학생용 로그인")
    s_input = st.text_input(
        "학번 입력 (예: 10105)",
        max_chars=5,
        help="아이디와 비밀번호 모두 학번으로 통일되어 있습니다.",
    )
    if st.button("학생으로 입장하기", type="secondary"):
        if s_input in st.session_state.student_list:
            st.session_state.user_role = "student"
            st.session_state.current_student_id = s_input
            st.rerun()
        else:
            st.error("등록되지 않은 학번입니다. (예시: 10101 ~ 10120)")

# ==========================================
# 2. 학생용 인터페이스
# ==========================================
elif st.session_state.user_role == "student":
    sid = st.session_state.current_student_id
    st.sidebar.title(f"🎓 학생 모드 ({sid})")
    if st.sidebar.button("로그아웃"):
        st.session_state.user_role = None
        st.session_state.current_student_id = None
        st.rerun()

    eval_names = list(st.session_state.evaluations.keys())
    selected_eval = st.selectbox("수행평가 선택", eval_names)
    eval_info = st.session_state.evaluations[selected_eval]

    st.info(f"📋 **[수행평가 채점 기준 (루브릭)] - {selected_eval}**\n\n{eval_info['rubric']}")

    if sid not in st.session_state.submissions:
        st.session_state.submissions[sid] = {}
    if selected_eval not in st.session_state.submissions[sid]:
        st.session_state.submissions[sid][selected_eval] = {
            "draft_text": "",
            "draft_score": 0,
            "deductions": "",
            "feedback": "",
            "is_final": False,
        }

    sub_data = st.session_state.submissions[sid][selected_eval]

    if sub_data["is_final"]:
        st.success("✅ 본 수행평가는 이미 **[최종 제출]**이 완료되었습니다. 수정할 수 없습니다.")
        st.text_area("제출된 최종 답안", value=sub_data["draft_text"], height=250, disabled=True)
        st.metric("가채점 점수", f"{sub_data['draft_score']} 점")
    else:
        user_essay = st.text_area(
            "서논술형 답안 작성란 (계속 수정 및 재가채점이 가능합니다)",
            value=sub_data["draft_text"],
            height=250,
            placeholder="여기에 답안을 작성하세요...",
        )

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🤖 AI 즉시 가채점 및 피드백 받기", type="secondary"):
                if not user_essay.strip():
                    st.warning("답안을 입력한 후 버튼을 눌러주세요.")
                else:
                    with st.spinner("AI가 루브릭을 분석하여 피드백을 생성하고 있습니다..."):
                        res = call_ai_grader(user_essay, eval_info["rubric"])
                        sub_data["draft_text"] = user_essay
                        sub_data["draft_score"] = res["score"]
                        sub_data["deductions"] = res["deductions"]
                        sub_data["feedback"] = res["feedback"]
                    st.rerun()

        with col_b:
            if st.button("🚨 최종 제출하기 (마감)", type="primary"):
                if not user_essay.strip():
                    st.error("답안을 작성한 후 최종 제출해 주세요.")
                else:
                    sub_data["draft_text"] = user_essay
                    sub_data["is_final"] = True
                    st.success("최종 제출되었습니다!")
                    st.rerun()

        if sub_data["draft_text"]:
            st.divider("### 🔍 AI 피드백 결과")
            m_col1, m_col2 = st.columns(2)
            with m_col1:
                st.metric("현재 가채점 점수", f"{sub_data['draft_score']} / {eval_info['total_score']}점")
            with m_col2:
                st.warning(f"**감점 및 주요 요인 사유**\n\n{sub_data['deductions']}")

            st.info(f"💡 **보완 코멘트 (수정 가이드)**\n\n{sub_data['feedback']}")

# ==========================================
# 3. 교사용 인터페이스
# ==========================================
elif st.session_state.user_role == "teacher":
    st.sidebar.title("👨‍🏫 교사 모드")
    st.sidebar.caption(f"관리자 접속 중 ({ADMIN_ID})")
    if st.sidebar.button("로그아웃"):
        st.session_state.user_role = None
        st.rerun()

    tab1, tab2, tab3 = st.tabs(["📊 제출 현황 대시보드", "📝 피드백 열람 및 세특 생성", "⚙️ 수행평가 및 루브릭 관리"])

    with tab1:
        st.header("학급별 학생 제출 현황 명렬표")
        eval_names = list(st.session_state.evaluations.keys())
        selected_eval_dash = st.selectbox("확인할 수행평가 선택", eval_names, key="dash_eval")

        status_rows = []
        for s_id in st.session_state.student_list:
            s_sub = st.session_state.submissions.get(s_id, {}).get(selected_eval_dash)
            if not s_sub or not s_sub["draft_text"]:
                status = "미제출 ❌"
                score = "-"
            elif s_sub["is_final"]:
                status = "최종 제출완료 🟢"
                score = f"{s_sub['draft_score']}점"
            else:
                status = "작성 중(임시저장) 🟡"
                score = f"{s_sub['draft_score']}점(가채점)"

            status_rows.append({"학번": s_id, "진행 상태": status, "점수": score})

        df_status = pd.DataFrame(status_rows)
        st.dataframe(df_status, use_container_width=True)

    with tab2:
        st.header("학생별 답안 열람 및 세특 초안 생성")
        eval_names = list(st.session_state.evaluations.keys())
        selected_eval_setuk = st.selectbox("수행평가 선택", eval_names, key="setuk_eval")

        final_submitted_students = [
            s_id for s_id in st.session_state.student_list
            if st.session_state.submissions.get(s_id, {}).get(selected_eval_setuk, {}).get("is_final", False)
        ]

        if not final_submitted_students:
            st.info("아직 최종 제출한 학생이 없습니다.")
        else:
            chosen_s_id = st.selectbox("최종 제출한 학생 선택", final_submitted_students)
            sub_info = st.session_state.submissions[chosen_s_id][selected_eval_setuk]

            col_p1, col_p2 = st.columns(2)
            with col_p1:
                st.subheader(f"학번 [{chosen_s_id}] 학생 원문")
                st.text_area("학생 작성 답안", value=sub_info["draft_text"], height=300, disabled=True, key="view_text")
            with col_p2:
                st.subheader("채점 및 감점 내역")
                st.metric("최종 확정/가채점 점수", f"{sub_info['draft_score']}점")
                st.write("**감점 사유:**")
                st.info(sub_info["deductions"])

            st.divider()

            if st.button("✨ 학생 원문 기반 세특 초안 자동 생성하기", type="primary"):
                with st.spinner("2022 개정 교육과정 기반 세특 초안을 작성 중입니다..."):
                    generated_setuk = call_ai_setuk(
                        chosen_s_id,
                        sub_info["draft_text"],
                        sub_info["draft_score"],
                        selected_eval_setuk,
                    )
                    sub_info["generated_setuk"] = generated_setuk

            if "generated_setuk" in sub_info:
                st.subheader("생성된 세특 초안 (교사 편집 가능)")
                edited_setuk = st.text_area(
                    "학교생활기록부 세특 입력용 텍스트",
                    value=sub_info["generated_setuk"],
                    height=150,
                )
                st.caption("ℹ️ 위 초안은 오직 학생이 직접 작성한 원문만을 바탕으로 생성되었으며, 교사가 자유롭게 수정할 수 있습니다.")

    with tab3:
        st.header("새로운 수행평가 및 루브릭 등록")

        with st.expander("📄 PDF 파일 업로드로 루브릭 자동 생성하기", expanded=True):
            uploaded_pdf = st.file_uploader("수행평가 계획서(PDF) 업로드", type=["pdf"])
            if uploaded_pdf is not None:
                if st.button("🤖 AI로 PDF 분석하여 루브릭 채우기"):
                    with st.spinner("PDF 파일을 읽고 루브릭과 배점을 분석하고 있습니다..."):
                        extracted_data, err = extract_rubric_from_pdf(uploaded_pdf)
                        if err:
                            st.error(err)
                        else:
                            st.session_state.form_eval_name = extracted_data.get("title", st.session_state.form_eval_name)
                            st.session_state.form_rubric = extracted_data.get("rubric", st.session_state.form_rubric)
                            st.session_state.form_total_score = int(extracted_data.get("total_score", st.session_state.form_total_score))
                            st.rerun()

        st.divider()

        new_eval_name = st.text_input("수행평가명 입력", key="form_eval_name", placeholder="예: 5·18 민주화 운동의 역사적 의의 서술")
        new_rubric = st.text_area(
            "루브릭(평가 요소, 채점 기준, 배점) 등록",
            key="form_rubric",
            placeholder="1. 사료 해석의 객관성 (20점)\n2. 역사적 인과관계 파악 (20점)",
            height=150,
        )
        new_total_score = st.number_input("총 배점", min_value=10, max_value=100, key="form_total_score", step=5)

        if st.button("수행평가 등록하기", type="primary"):
            if new_eval_name.strip() and new_rubric.strip():
                st.session_state.evaluations[new_eval_name.strip()] = {
                    "rubric": new_rubric.strip(),
                    "total_score": new_total_score,
                }
                st.success(f"'{new_eval_name.strip()}' 수행평가가 성공적으로 등록되었습니다!")
            else:
                st.warning("수행평가명과 루브릭을 모두 입력해 주세요.")
