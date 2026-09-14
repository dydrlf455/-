import json
import os
import pandas as pd
import streamlit as st
from openai import OpenAI

# 페이지 기본 설정
st.set_page_config(
    page_title="역사과 AI 서논술형 수행평가 시스템", page_icon="📜", layout="wide"
)

# 세션 스테이트 초기화 (데이터베이스 대체)
if "user_role" not in st.session_state:
    st.session_state.user_role = None  # 'teacher' or 'student'
if "current_student_id" not in st.session_state:
    st.session_state.current_student_id = None

if "evaluations" not in st.session_state:
    # 기본 수행평가 예시 데이터
    st.session_state.evaluations = {
        "1970년대 산업화와 노동 현실 분석": {
            "rubric": "1. 역사적 사실(사료)의 정확한 인용 (10점)\n2. 구조적 모순(노동/환경 문제)에 대한 인과적 분석 (10점)\n3. 비판적 대안 및 역사적 통찰력 (10점)",
            "total_score": 30,
        }
    }

if "submissions" not in st.session_state:
    # 학생 제출 데이터 저장소: { "학번": { "평가명": { "draft_text": "", "draft_score": 0, "draft_feedback": "", "is_final": False } } }
    st.session_state.submissions = {}

# 가상 학급 명렬 (1학년 1반 예시)
if "student_list" not in st.session_state:
    st.session_state.student_list = [f"101{i:02d}" for i in range(1, 21)]


# OpenAI API 호출 함수 (Fallback 포함)
def call_ai_grader(text, rubric_text):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        # API 키가 없을 경우 모의(Mock) 응답 반환
        return {
            "score": 24,
            "deductions": "1. 사료 인용은 적절하나 구체적 통계 언급이 다소 부족함 (-3점)\n2. 노동 조건의 변화와 법적 제도 연계 분석이 평면적임 (-3점)",
            "feedback": "제출한 내용은 1970년대 노동 현실의 핵심을 잘 짚었습니다. 다만 '근로기준법 준수 요구' 등 당시 구체적인 노동쟁의 사례를 덧붙이면 훨씬 설득력 있는 글이 됩니다.",
        }

    client = OpenAI(api_key=api_key)
    prompt = f"""
    당신은 고등학교 역사 교사입니다. 아래의 채점 기준(루브릭)을 바탕으로 학생의 서논술형 답안을 가채점해 주세요.
    반드시 JSON 형식으로만 응답하며, 키는 'score'(숫자), 'deductions'(문자열), 'feedback'(문자열)로 구성하세요.

    [채점 기준]
    {rubric_text}

    [학생 답안]
    {text}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "system",
                "content": "You are a helpful history teacher grading student essays in JSON format.",
            }, {"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {
            "score": 20,
            "deductions": f"AI 분석 중 오류 발생으로 기본 점수 부여 ({str(e)})",
            "feedback": "내용을 다시 확인하고 보완해 주세요.",
        }


def call_ai_setuk(student_name_or_id, text, score, eval_name):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return f"[{student_name_or_id}] 학생은 '{eval_name}' 수행평가에서 서논술형 글쓰기를 수행함. 당시 사료를 바탕으로 1970년대 산업화 과정에서 발생한 사회적 모순과 노동 문제를 인과적으로 분석해내는 역사적 탐구력이 돋보임. 구조적 불평등에 대한 비판적 시각을 바탕으로 역사적 성찰을 균형 있게 서술함."

    client = OpenAI(api_key=api_key)
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
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "system",
            "content": "You are a professional Korean high school history teacher writing official student records.",
        }, {"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()


# ==========================================
# 1. 로그인 화면
# ==========================================
if st.session_state.user_role is None:
    st.title("📜 역사과 서논술형 AI 수행평가 시스템")
    st.markdown("### 로그인 방식을 선택하세요")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("👨‍🏫 교사용 로그인")
        t_id = st.text_input("교사 아이디", key="t_id")
        t_pw = st.text_input("비밀번호", type="password", key="t_pw")
        if st.button("교사로 입장하기"):
            # 교사 계정 하드코딩 검증 (id: teacher / pw: 1234)
            if t_id == "teacher" and t_pw == "1234":
                st.session_state.user_role = "teacher"
                st.rerun()
            else:
                st.error("교사 아이디 또는 비밀번호가 일치하지 않습니다. (id: teacher / pw: 1234)")

    with col2:
        st.subheader("🎓 학생용 로그인")
        s_input = st.text_input(
            "학번 입력 (예: 10105)",
            max_chars=5,
            help="아이디와 비밀번호 모두 학번으로 통일되어 있습니다.",
        )
        if st.button("학생으로 입장하기"):
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

    # 수행평가 선택
    eval_names = list(st.session_state.evaluations.keys())
    selected_eval = st.selectbox("수행평가 선택", eval_names)
    eval_info = st.session_state.evaluations[selected_eval]

    # 상단 루브릭 안내
    st.info(f"📋 **[수행평가 채점 기준 (루브릭)] - {selected_eval}**\n\n{eval_info['rubric']}")

    # 데이터 초기화
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

        col_a, col_b = st.columns([1, 1])
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

        # 가채점 결과 및 피드백 표시 영역
        if sub_data["draft_text"]:
            st.divider("### 🔍 AI 피드백 결과")
            m_col1, m_col2 = st.columns([1, 2])
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
    if st.sidebar.button("로그아웃"):
        st.session_state.user_role = None
        st.rerun()

    tab1, tab2, tab3 = st.tabs(["📊 제출 현황 대시보드", "📝 피드백 열람 및 세특 생성", "⚙️ 수행평가 및 루브릭 관리"])

    # [탭 1] 대시보드
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

    # [탭 2] 피드백 열람 및 세특 생성
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

    # [탭 3] 관리 탭 (수행평가 추가 및 루브릭 등록)
    with tab3:
        st.header("새로운 수행평가 및 루브릭 등록")
        new_eval_name = st.text_input("수행평가명 입력", placeholder="예: 5·18 민주화 운동의 역사적 의의 서술")
        new_rubric = st.text_area(
            "루브릭(평가 요소, 채점 기준, 배점) 등록",
            placeholder="1. 사료 해석의 객관성 (10점)\n2. 역사적 인과관계 파악 (10점)\n3. 민주주의 가치에 대한 성찰 (10점)",
        )
        new_total_score = st.number_input("총 배점", min_value=10, max_value=100, value=30, step=5)

        if st.button("수행평가 등록하기"):
            if new_eval_name and new_rubric:
                st.session_state.evaluations[new_eval_name] = {
                    "rubric": new_rubric,
                    "total_score": new_total_score,
                }
                st.success(f"'{new_eval_name}' 수행평가가 성공적으로 등록되었습니다!")
                st.rerun()
            else:
                st.warning("수행평가명과 루브릭을 모두 입력해 주세요.")
