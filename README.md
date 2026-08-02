# 법령검토

키워드 또는 문장을 입력하면 법제처 국가법령정보센터(Open API)에서 관련 **법률 · 시행령 · 시행규칙** 조문을 찾아 3단으로 비교해 보여주는 웹 앱입니다.

데이터 출처: [국가법령정보센터](https://www.law.go.kr) / [법제처](https://www.moleg.go.kr) / [Open API](https://open.law.go.kr)

## 로컬 실행 (Windows)

`run.bat`을 더블클릭하세요.

또는:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

브라우저: http://127.0.0.1:8000

## 환경 변수

`.env` 예시(`.env.example` 참고):

```env
LAW_API_OC=test
COPILOT_API_KEY=sk-ant-...
```

- `LAW_API_OC`: [open.law.go.kr](https://open.law.go.kr) 가입 후 발급 (테스트는 `test`)
- `COPILOT_API_KEY`: Claude(Anthropic) 질문 기능용 ([발급](https://console.anthropic.com/settings/keys))
- `COPILOT_MODEL`: 선택, 기본 `claude-sonnet-4-5`

`.env`는 GitHub에 올리지 마세요.

## GitHub + Render 클라우드 배포 (무료)

### 1. 코드는 GitHub에 저장
이 저장소를 GitHub에 push 합니다. (이미 연결되어 있으면 pull만 하면 됩니다.)

### 2. Render에서 실행
1. [https://render.com](https://render.com) 가입 (GitHub 계정 연동)
2. **New +** → **Blueprint**
3. 이 GitHub 저장소 선택 (`render.yaml` 자동 인식)
4. 환경변수 입력:
   - `LAW_API_OC`
   - `COPILOT_API_KEY` (선택, 질문 기능용)
5. **Apply** 후 배포 완료되면 `https://xxxx.onrender.com` 주소로 접속

수동 배포를 원하면 **Web Service**로 만들고 다음을 입력하세요.

- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

무료 플랜은 잠시 사용하지 않으면 잠들 수 있고, 첫 접속이 느릴 수 있습니다.

## 주요 기능

1. 키워드로 관련 법령 목록 조회 후 선택
2. 새 탭에서 법률·시행령·시행규칙 3단 조문 검색
3. `전체 조문`으로 키워드 없이 전체 조문 3단 보기
4. 현행/시행예정 표시, 수식·표 이미지 표시
5. Claude 패널에서 조문 관련 질의응답
