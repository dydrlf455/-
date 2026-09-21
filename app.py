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
                "structured_rubric": {
                    "element_name": "포스터 분석력",
                    "dimension": "과정·기능",
                    "levels": {
                        "advanced": "포스터의 제작 주체와 시기, 포스터에 나타난 이미지와 핵심 문구를 포스터가 내포하는 선전 내용과 연결하여 서술함.",
                        "basic": "포스터의 제작 주체나 시기를 언급하고 이미지나 문구의 표면적 의미만을 서술함.",
                        "beginner": "포스터에 표면적으로 드러난 내용을 찾아서 나열함."
                    }
                },
                "max_score": 10
            }
        }
    if "student_submissions" not in st.session_state:
        st.session_state.student_submissions = {}
    save_data()

# ==========================================
# [구글 Gemini AI 연동 함수 정의]
# ==========================================
def call_ai_grading(student_text, structured_rubric, api_key=None):
    rubric_text = json.dumps(structured_rubric, ensure_ascii=False, indent=2)
    prompt = f"""
당신은 고등학교 역사 교사입니다. 아래의 [수행평가 구조화 루브릭(JSON)]을 기반으로 학생이 작성한 [학생 제출물]을 공정하게 평가해 주세요.
반드시 아래의 JSON 포맷으로만 응답해 주세요. (다른 설명 없이 순수 JSON만 출력하세요)

[수행평가 구조화 루브릭]
{rubric_text}

[학생 제출물]
{student_text}

응답 JSON 포맷:
{{
  "score": (숫자, 예: 8.5),
  "item_deductions": "(루브릭의 기준(심화/기본/기초)에 비추어 어떤 부분이 충족되었고 어떤 부분에서 감점되었는지 상세히 서술)",
  "comment": "(학생에게 건네는 격려 및 보완 가이드 코멘트)"
}}
"""
    if not GENAI_AVAILABLE or not api_key:
        return {
            "score": 8.0,
            "item_deductions": "분석 기준(기본~심화)에 따른 가채점 결과: 제작 시기 언급은 양호하나 핵심 문구 연결이 다소 부족함.",
            "comment": "전반적인 흐름 이해가 훌륭합니다. 포스터의 구체적 문구를 직접 인용해 보세요!",
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

def call_ai_rubric_parser(raw_text, api_key=None):
    prompt = f"""
다음은 고등학교 역사 과목 수행평가 채점 기준(루브릭) 문서 내용입니다.
이 내용을 분석하여 반드시 아래 JSON 구조로만 출력해 주세요. 마크다운 기호(```json) 없이 순수 JSON 텍스트만 반환하세요.
배점이 높은 순서대로 '심화', '기본', '기초'에 내용을 매핑하세요.

[출력 JSON 포맷]
{{
  "element_name": "평가 요소 이름 (예: 포스터 분석력)",
  "dimension": "과정·기능", 
  "levels": {{
    "advanced": "가장 높은 배점의 채점 기준 내용",
    "basic": "중간 배점의 채점 기준 내용",
    "beginner": "가장 낮은 배점의 채점 기준 내용"
  }}
}}

[루브릭 원문]
{raw_text}
"""
    default_mock = {
        "element_name": "평가요소 파악 실패",
        "dimension": "지식·이해",
        "levels": {
            "advanced": raw_text[:50] + "...",
            "basic": "중간 수준 기준을 직접 입력하세요.",
            "beginner": "기초 수준 기준을 직접 입력하세요."
        }
    }
    
    if not GENAI_AVAILABLE or not api_key:
        return default_mock

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3.6-flash")
        response = model.generate_content(prompt)
        content = response.text.strip()
        
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        parsed_json = json.loads(content)
        return parsed_json
    except:
        return default_mock

def call_ai_seteuk(student_text, score, assessment_name, api_key=None):
    prompt = f"""
당신은 고등학교 역사 교사입니다. 2022 개정 교육과정 역사과 성취기준 및 핵심 역량(역사적 사고력, 역사적 탐구 및 소통력 등)을 바탕으로 아래 학생의 세부능력 및 특기사항(세특) 초안을 작성해 주세요.

[절대 규칙 - 환각 배제]
1. 아래 제공된 [학생 원문 내용]에 명시적으로 드러난 사실, 역사적 개념, 탐구 내용만을 기반으로 작성할 것.
2. 분량은 500바이트 내외(3~5문장)로 서술할 것.

[수행평가명]: {assessment_name}
[획득 점수]: {score}점
[학생 원문 내용]:
{student_text}
"""
    if not GENAI_AVAILABLE or not api_key:
        return f"[모의 세특 생성 결과] ({assessment_name} / {score}점 기반)\n수행평가 과정에서 뛰어난 탐구력을 보여줌."

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3.6-flash")
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"세특 생성 중 오류 발생: {str(e)}"

# ==========================================
# [사이드바 및 기본 UI]
# ==========================================
with st.sidebar:
    st.header("🔑 로그인 및 설정")
    api_key_input = st.text_input("구글 AI 스튜디오 API 키", type="password")
    if api_key_input:
        os.environ["GEMINI_API_KEY"] = api_key_input

    st.divider()

    if not st.session_state.logged_in:
        login_type = st.radio("로그인 유형 선택", ["학생 로그인", "교사 로그인", "👑 관리자 로그인"])
        
        if login_type == "학생 로그인":
            s_id = st.text_input("학번 입력")
            s_pw = st.text_input("비밀번호 입력", type="password")
            if st.button("학생 입장하기"):
                if s_id in st.session_state.student_credentials and st.session_state.student_credentials[s_id] == s_pw:
                    st.session_state.logged_in = True
                    st.session_state.user_role = "student"
                    st.session_state.user_id = s_id
                    st.rerun()
                else:
                    st.error("정보를 확인해 주세요.")
        
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
                    st.error("교사 인증 실패.")

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
                    st.error("관리자 인증 실패.")
    else:
        st.success(f"현재 접속자: **{st.session_state.user_id}** ({st.session_state.user_role})")
        if st.button("로그아웃"):
            st.session_state.logged_in = False
            st.session_state.user_role = None
            st.session_state.user_id = None
            st.rerun()

if not st.session_state.logged_in:
    st.title("📚 역사과 서논술형 AI 수행평가 플랫폼")
    st.info("👈 왼쪽 사이드바에서 로그인을 진행해 주세요.")

# ------------------------------------------
# 1. 관리자(Admin) 모드 (생략 없이 유지)
# ------------------------------------------
elif st.session_state.user_role == "admin":
    st.title("👑 최고 관리자 대시보드")
    tab_accounts, tab_test = st.tabs(["🔐 계정 관리", "🎭 권한 테스트"])
    
    with tab_accounts:
        st.subheader("👨‍🏫 교사 계정 설정")
        new_t_id = st.text_input("교사 아이디", value=st.session_state.teacher_credentials["id"])
        new_t_pw = st.text_input("교사 비밀번호", value=st.session_state.teacher_credentials["pw"])
        if st.button("교사 계정 업데이트"):
            st.session_state.teacher_credentials["id"] = new_t_id
            st.session_state.teacher_credentials["pw"] = new_t_pw
            save_data()
            st.success("변경 완료.")
            
        st.divider()
        st.subheader("🎓 학생 계정 일괄 업로드")
        sample_df = pd.DataFrame({"학번": ["10101"], "비밀번호": ["10101"]})
        sample_csv = sample_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button("📄 엑셀 양식 다운로드", data=sample_csv, file_name="student_template.csv", mime="text/csv")
        
        uploaded_excel = st.file_uploader("학생 명단 파일 업로드 (CSV)", type=["csv"])
        if uploaded_excel is not None:
            df_upload = pd.read_csv(uploaded_excel)
            if "학번" in df_upload.columns and "비밀번호" in df_upload.columns:
                for _, row in df_upload.iterrows():
                    st.session_state.student_credentials[str(row["학번"]).strip()] = str(row["비밀번호"]).strip()
                save_data()
                st.success("일괄 등록 완료!")
                st.rerun()

    with tab_test:
        if st.button("👨‍🏫 교사 모드로 진입"):
            st.session_state.user_role = "teacher"
            st.session_state.user_id = st.session_state.teacher_credentials["id"]
            st.rerun()

# ------------------------------------------
# 2. 학생(Student) 모드
# ------------------------------------------
elif st.session_state.user_role == "student":
    student_id = st.session_state.user_id
    st.title(f"🎓 학생용 수행평가 작성실 (학번: {student_id})")
    
    assess_list = list(st.session_state.assessments.keys())
    if not assess_list:
        st.warning("현재 등록된 수행평가가 없습니다.")
    else:
        selected_assess = st.selectbox("진행할 수행평가 선택", assess_list)
        current_rubric = st.session_state.assessments[selected_assess].get("structured_rubric", {})
        
        with st.expander("📌 [필독] 이번 수행평가 채점 기준", expanded=True):
            if current_rubric:
                st.markdown(f"**평가 요소:** {current_rubric.get('element_name', '')} ({current_rubric.get('dimension', '')})")
                st.markdown(f"- **심화:** {current_rubric['levels'].get('advanced', '')}")
                st.markdown(f"- **기본:** {current_rubric['levels'].get('basic', '')}")
                st.markdown(f"- **기초:** {current_rubric['levels'].get('beginner', '')}")
            else:
                st.markdown("루브릭 정보가 없습니다.")
        
        if student_id not in st.session_state.student_submissions:
            st.session_state.student_submissions[student_id] = {}
        if selected_assess not in st.session_state.student_submissions[student_id]:
            st.session_state.student_submissions[student_id][selected_assess] = {
                "draft": "", "status": "draft", "score": None, "item_deductions": "", "comment": ""
            }
        
        sub_data = st.session_state.student_submissions[student_id][selected_assess]
        
        if sub_data["status"] == "submitted":
            st.warning("🔒 최종 제출 완료")
            st.text_area("원문", value=sub_data["draft"], height=250, disabled=True)
            st.metric("가채점 최종 점수", f"{sub_data['score']} 점")
            st.info(sub_data['comment'])
        else:
            user_input_text = st.text_area("답안 작성:", value=sub_data["draft"], height=300)
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🤖 AI 가채점", use_container_width=True):
                    with st.spinner("분석 중..."):
                        ai_result = call_ai_grading(user_input_text, current_rubric, os.environ.get("GEMINI_API_KEY"))
                        sub_data.update({"draft": user_input_text, "score": ai_result.get("score", 0), "item_deductions": ai_result.get("item_deductions", ""), "comment": ai_result.get("comment", "")})
                        save_data()
                        st.rerun()
            with col2:
                if st.button("🚨 최종 제출", type="primary", use_container_width=True):
                    sub_data["status"] = "submitted"
                    save_data()
                    st.rerun()
                    
            if sub_data["score"] is not None:
                st.divider()
                st.metric("가채점 점수", f"{sub_data['score']}점")
                st.info(f"분석:\n{sub_data.get('item_deductions', '')}")
                st.success(f"코멘트:\n{sub_data['comment']}")

# ------------------------------------------
# 3. 교사(Teacher) 모드 (UI 개편 핵심 적용)
# ------------------------------------------
elif st.session_state.user_role == "teacher":
    st.title("👩‍🏫 교사용 대시보드")
    
    tab_dashboard, tab_management, tab_seteuk = st.tabs([
        "📋 제출 대시보드", 
        "⚙️ 수행평가 등록 (구조화 UI 적용)", 
        "✨ 세특 초안 생성"
    ])

    with tab_management:
        st.subheader("📁 수행평가 및 루브릭 등록")
        
        if "structured_rubric" not in st.session_state:
            st.session_state.structured_rubric = {
                "element_name": "",
                "dimension": "과정·기능",
                "levels": {"advanced": "", "basic": "", "beginner": ""}
            }

        uploaded_pdf = st.file_uploader("채점 기준 PDF 파일 업로드 (자동 채워짐)", type=["pdf"])
        
        if uploaded_pdf is not None:
            if PYPDF_AVAILABLE:
                try:
                    reader = PdfReader(BytesIO(uploaded_pdf.read()))
                    extracted_text = "".join([page.extract_text() or "" for page in reader.pages])
                    
                    if extracted_text.strip():
                        with st.spinner("AI가 PDF를 분석하여 구조화된 UI를 생성 중입니다..."):
                            parsed_json = call_ai_rubric_parser(extracted_text.strip(), os.environ.get("GEMINI_API_KEY"))
                            st.session_state.structured_rubric = parsed_json
                        st.success("PDF 루브릭 추출 완료! 아래 카드 UI에 반영되었습니다.")
                except Exception as e:
                    st.error(f"PDF 읽기 오류: {str(e)}")
            else:
                st.error("pypdf 라이브러리가 없습니다.")

        st.markdown("---")
        
        # [스크린샷 기반 구조화된 UI 렌더링]
        with st.form("new_assessment_form"):
            new_title = st.text_input("수행평가명 (제목)", placeholder="예: 5·18 민주 운동 서술")
            new_max_score = st.number_input("이 과제의 만점 배점", min_value=1, max_value=100, value=10)
            
            st.markdown("#### 📝 루브릭 세부 설정 (PDF 업로드 시 자동 입력)")
            with st.container(border=True):
                c1, c2 = st.columns([2, 1])
                with c1:
                    rubric_elem = st.text_input("평가 요소", value=st.session_state.structured_rubric.get("element_name", ""))
                with c2:
                    dimensions = ["지식·이해", "과정·기능", "가치·태도"]
                    current_dim = st.session_state.structured_rubric.get("dimension", "과정·기능")
                    if current_dim not in dimensions:
                        current_dim = "과정·기능"
                    rubric_dim = st.radio("차원", dimensions, index=dimensions.index(current_dim), horizontal=True)

                st.markdown("---")
                
                c_level1, c_text1 = st.columns([1, 6])
                with c_level1: st.markdown("<br>**심화**", unsafe_allow_html=True)
                with c_text1: rub_adv = st.text_area("심화 기준", value=st.session_state.structured_rubric.get("levels", {}).get("advanced", ""), label_visibility="collapsed")
                
                c_level2, c_text2 = st.columns([1, 6])
                with c_level2: st.markdown("<br>**기본**", unsafe_allow_html=True)
                with c_text2: rub_bas = st.text_area("기본 기준", value=st.session_state.structured_rubric.get("levels", {}).get("basic", ""), label_visibility="collapsed")
                
                c_level3, c_text3 = st.columns([1, 6])
                with c_level3: st.markdown("<br>**기초**", unsafe_allow_html=True)
                with c_text3: rub_beg = st.text_area("기초 기준", value=st.session_state.structured_rubric.get("levels", {}).get("beginner", ""), label_visibility="collapsed")
            
            submitted_new = st.form_submit_button("수행평가 최종 등록", type="primary")
            
            if submitted_new:
                if new_title and rubric_elem:
                    st.session_state.assessments[new_title] = {
                        "structured_rubric": {
                            "element_name": rubric_elem,
                            "dimension": rubric_dim,
                            "levels": {
                                "advanced": rub_adv,
                                "basic": rub_bas,
                                "beginner": rub_beg
                            }
                        },
                        "max_score": new_max_score
                    }
                    save_data()
                    st.success(f"'{new_title}' 수행평가가 구조화된 루브릭과 함께 등록되었습니다!")
                    st.rerun()
                else:
                    st.warning("수행평가명과 평가 요소를 입력해 주세요.")

    with tab_dashboard:
        st.subheader("제출 현황 대시보드")
        assess_names = list(st.session_state.assessments.keys())
        if assess_names:
            selected_assess_t = st.selectbox("조회할 수행평가", assess_names)
            current_students = sorted(list(st.session_state.student_credentials.keys()))
            target_sid = st.selectbox("상세 조회 및 최종 제출 처리할 학생 학번", current_students)
            target_sub = st.session_state.student_submissions.get(target_sid, {}).get(selected_assess_t, None)
            
            if target_sub and target_sub["draft"]:
                with st.container(border=True):
                    c1, c2 = st.columns(2)
                    with c1: st.text_area("원문", target_sub["draft"], height=200, disabled=True)
                    with c2: 
                        st.metric("가채점 점수", f"{target_sub.get('score', 0)}점")
                        st.caption(f"상태: {target_sub['status']}")
                        if target_sub['status'] != 'submitted' and st.button("강제 최종 제출 처리"):
                            target_sub['status'] = 'submitted'
                            save_data()
                            st.rerun()
            else:
                st.info("해당 학생의 작성 내용이 없습니다.")

    with tab_seteuk:
        st.subheader("세특 자동 생성")
        if assess_names:
            selected_assess_s = st.selectbox("수행평가 선택", assess_names, key="s_sel")
            submitted_students = [sid for sid, d in st.session_state.student_submissions.items() if selected_assess_s in d and d[selected_assess_s]["status"] == "submitted"]
            if submitted_students:
                chosen_student = st.selectbox("학생 선택", submitted_students)
                student_work = st.session_state.student_submissions[chosen_student][selected_assess_s]
                
                if st.button("세특 생성"):
                    generated = call_ai_seteuk(student_work["draft"], student_work.get("score", 0), selected_assess_s, os.environ.get("GEMINI_API_KEY"))
                    student_work["se-teuk"] = generated
                    save_data()
                    st.rerun()
                
                edited = st.text_area("세특 초안", value=student_work.get("se-teuk", ""), height=150)
                if st.button("세특 저장"):
                    student_work["se-teuk"] = edited
                    save_data()
                    st.success("저장 완료")
