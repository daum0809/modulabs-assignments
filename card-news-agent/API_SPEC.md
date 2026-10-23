# API_SPEC — 화면과 서버의 약속

PRD.md의 "웹 API 계약 초안"을 Python 구현(`cardnews/server.py`)에 맞춰 확정한 문서다.
지금 구현된 범위는 **주제 입력 → 조사 → 후보 선택 → 질문·답변 → 편집 방향(심층 검증 포함) → 스토리보드 승인 → 카드별 그림 → 글자를 올린 카드 PNG·글자만 고치기**까지다(STEP 8). 요청문으로 카드 고치기·최종 승인·내려받기(`/revisions`, `/exports`)는 아직 없다.
스토리보드 승인·수정·내보내기(`/approve`, `/revisions`, `/exports`)는 아직 없다.

## 기본

- 주소: `http://127.0.0.1:8765` (127.0.0.1에만 열림). 요청·응답은 JSON, UTF-8.
- 긴 작업은 HTTP 요청 하나로 끝내지 않는다. 작업을 시작하는 요청은 `runId`를 **바로** 돌려주고, 화면은 `GET /api/projects/{id}`를 1.2초마다 불러 진행을 본다(작업 중일 때만).
- 상태는 `data\cardnews.sqlite3`에 프로젝트별 문서로 저장된다. 서버를 다시 켜도 남는다.

## 오류 응답

모든 오류는 같은 모양이다.

```json
{ "error": { "code": "stale_question", "message": "지난 질문입니다. 화면을 새로 불러와 현재 질문에 답해 주세요." } }
```

| HTTP | code | 뜻 | 화면이 할 일 |
|---|---|---|---|
| 400 | `bad_request` | 입력이 빠졌거나 잘못됨 (requestId 없음, 후보 4개 이상 등) | 메시지를 보여 주고 다시 입력 |
| 404 | `not_found` | 없는 프로젝트·작업·주소 | 처음 화면으로 |
| 409 | `stale_version` | 후보 목록이 바뀐 뒤 옛 목록으로 선택함 | 새로 불러와 다시 고르기 |
| 409 | `selection_locked` | 선택을 확정한 뒤 바꾸려 함 | — |
| 409 | `stale_question` | 지난 질문(다른 id·version)에 답함 | 새로 불러와 현재 질문에 답하기 |
| 409 | `already_answered` | 이미 답한 질문에 다른 requestId로 또 답함 | 새로 불러오기 (작업은 다시 시작하지 않음) |
| 409 | `request_conflict` | 같은 requestId로 다른 내용을 보냄 | 새 requestId로 다시 |
| 409 | `invalid_state` | 지금 단계에서 할 수 없는 요청 | 새로 불러오기 |
| 413 | `too_large` | 요청 본문 1MB 초과 | — |
| 500 | `internal` | 서버 내부 오류 | 메시지 보여 주기 |

작업 자체의 실패는 HTTP 오류가 아니라 프로젝트의 `status: "failed"`와 `error`로 알린다(아래 "작업 실패").

## 중복 요청 막기 (requestId)

상태를 바꾸는 POST(`research`, `selection`, `answers`, `retry`)는 `requestId`가 필수다.

- 같은 프로젝트에서 **같은 requestId + 같은 입력** → 처음 응답을 그대로 돌려준다(`"replayed": true`). 작업을 새로 시작하지 않는다.
- **같은 requestId + 다른 입력** → `409 request_conflict`.
- 작업이 이미 돌고 있을 때 다른 requestId로 조사를 또 요청해도 새 작업을 만들지 않는다(`"alreadyRunning": true`).
- 화면은 버튼을 누를 때마다 새 requestId(`crypto.randomUUID()`)를 만들고, 누른 직후 버튼을 잠근다.

## 프로젝트 상태 (`status`)

```
created → researching → candidates_ready → running → waiting_for_user ⇄ running → editorial_ready
                ↘ failed / cancelled / interrupted (다시 시도 가능)
```

| status | 뜻 |
|---|---|
| `created` | 막 만듦 |
| `researching` | 넓은 조사 중 |
| `candidates_ready` | 후보가 나왔고 사용자가 고르는 중 (임시 선택은 저장됨) |
| `running` | 심층 조사·편집 판단 중 |
| `waiting_for_user` | 질문에 대한 답을 기다림. **실패가 아니다.** 답하기 전에는 다음 단계로 가지 않는다 |
| `editorial_ready` | 독자·형식·표지 문장 후보가 정해짐 (STEP 4의 끝) |
| `failed` | 작업 실패. `error.message`에 이유 |
| `cancelled` | 사용자가 취소 |
| `interrupted` | 서버가 다시 켜져서 돌던 작업이 끊김 |

## 엔드포인트

### `GET /api/health`
```json
{ "engine": "mock", "mock": true, "dataDir": "C:\\...\\data" }
```

### `GET /api/projects`
프로젝트 목록(최근 것부터). `{ "projects": [{ "id", "topic", "status", "engine", "createdAt", "updatedAt" }] }`

### `POST /api/projects` → 201
| 입력 | 필수 | 설명 |
|---|---|---|
| `topic` | ✔ | 주제, 1~200자 |
| `sourcePath` | | 내 자료 폴더 경로. 있으면 그 자료를 먼저 읽는다(PRD 1절 추가 규칙) |
| `direction` | | 편집 방향. 독자가 적혀 있으면 독자를 다시 묻지 않는다 |
| `periodDays` | | 7(기본) 또는 30 |

결과: `{ "projectId": "prj_..." }`. 프로젝트마다 엔진 세션 ID(`engineSessionId`)를 따로 만든다.

### `GET /api/projects/{id}`
프로젝트 전체 상태. 화면은 이것만 보고 그린다.

```json
{
  "id": "prj_...", "topic": "...", "sourcePath": null, "direction": null, "periodDays": 7,
  "engine": "mock", "engineSessionId": "mock-...", "status": "waiting_for_user", "error": null,
  "research": {
    "researchedAt": "2026-10-23T13:07:59+09:00", "timezone": "대한민국 표준시",
    "periodStart": "2026-10-16", "periodEnd": "2026-10-23", "periodDays": 7,
    "mock": true, "note": "모의 데이터입니다. 실제 조사 결과가 아닙니다.", "candidatesVersion": 1,
    "candidates": [{ "id": "c1", "title": "...", "summary": "...", "kind": "문제", "date": "미확인",
                     "source": "...", "value": "...", "uncertainty": "..." }]
  },
  "selection": { "candidateIds": ["c1", "c3"], "confirmed": true, "savedAt": "..." },
  "question": {
    "id": "q_...", "version": 1, "key": "audience", "question": "누구를 위한 카드뉴스인가요?",
    "why": "...", "options": [{ "id": "owner-new", "label": "...", "desc": "..." }],
    "recommended": "owner-new", "recommendReason": "...", "multiSelect": false, "allowFree": true, "askedAt": "..."
  },
  "answers": [{ "key": "audience", "questionId": "q_...", "version": 1, "optionId": "owner-new",
                "text": null, "label": "자동화가 처음인 사장님", "answeredAt": "..." }],
  "editorial": null,
  "runs": [{ "id": "run_...", "kind": "research", "status": "done", "startedAt": "...", "finishedAt": "...", "error": null }],
  "currentRunId": "run_...", "activeRun": { "...": "currentRunId의 작업" },
  "events": [{ "at": "...", "message": "작업 시작: research (run_...)" }]
}
```

- `recommended`는 **표시만** 한다. 사용자 답으로 저장하지 않고, 화면도 미리 체크하지 않는다.
- `events`는 화면의 "작업 진행 내역"이다(최근 200개).

### `POST /api/projects/{id}/research`
| 입력 | 필수 | 설명 |
|---|---|---|
| `requestId` | ✔ | |
| `periodDays` | | 7 또는 30. "30일로 넓혀 다시 조사"에 쓴다 |

결과: `{ "runId", "status": "researching" }`. 다시 조사하면 `candidatesVersion`이 1 올라가고 임시 선택이 비워진다.
`created / candidates_ready / failed / interrupted / cancelled`에서만 가능.

### `POST /api/projects/{id}/selection`
| 입력 | 필수 | 설명 |
|---|---|---|
| `candidateIds` | ✔ | 고른 후보 id 목록, 최대 3개 |
| `version` | ✔ | 화면이 본 `research.candidatesVersion`. 다르면 `409 stale_version` |
| `confirm` | | `false`(기본): 임시 저장만(새로고침해도 남음). `true`: 1~3개로 확정하고 심층 조사 작업 시작 |
| `requestId` | ✔ | |

결과: `{ "selection", "status", "runId" }` (`runId`는 확정했을 때만).

### `POST /api/projects/{id}/answers`
| 입력 | 필수 | 설명 |
|---|---|---|
| `questionId` | ✔ | 화면에 보인 질문의 `id` |
| `version` | ✔ | 화면에 보인 질문의 `version` |
| `answer` | ✔ | `{ "optionId": "..." }` 또는 `{ "text": "직접 입력" }`(질문이 `allowFree`일 때) |
| `requestId` | ✔ | |

- 현재 질문과 id·version이 같을 때만 받는다. 지난 질문이면 `409 stale_question`, 이미 답한 질문이면 `409 already_answered`. 어느 경우도 현재 작업을 덮어쓰지 않는다.
- 받으면 답을 저장하고 `status`를 `running`으로 바꾼 뒤, **같은 엔진 세션**으로 작업을 이어 간다.

결과: `{ "accepted": true, "status": "running", "runId" }`

### `POST /api/projects/{id}/storyboard` (STEP 7)
| 입력 | 필수 | 설명 |
|---|---|---|
| `requestId` | ✔ | |
| `feedback` | | 변경 요청 문장. 있으면 지난 스토리보드에 이 요청만 반영해 다시 만든다 |

`editorial_ready` 또는 승인 전 `storyboard_ready`에서만. 승인한 뒤에는 `409 storyboard_locked`. 결과 `{ runId, status: "running" }` → 끝나면 `status: "storyboard_ready"`.

### `POST /api/projects/{id}/approve`
`{ stage: "storyboard", version, requestId }`. 화면이 본 `storyboard.version`과 다르면 `409 stale_version`. 승인하면 모든 카드의 `image.status`를 `pending`으로 두고 **그림 작업을 시작**한다(`status: running` → 끝나면 `images_ready`). `stage: "final"`은 STEP 9에서 추가.

### `POST /api/projects/{id}/cards/{no}/image`
`{ requestId }`. 카드 하나의 그림만 다시 만든다(새 버전 파일, 이전 파일 보관). 다른 카드와 승인한 스토리보드는 그대로.

### `GET /api/projects/{id}/images/{file}`
그림 파일(`card-NN-vK.svg|png|jpg|jpeg|webp`)을 그대로 준다.

### 스토리보드·그림 데이터 (`GET /api/projects/{id}`의 `storyboard`)
```json
{
  "version": 2, "approved": { "version": 2, "at": "..." }, "format": "이야기형", "reason": "...",
  "style": { "palette": ["#1F3A5F"], "illustration": "...", "mood": "...", "layout": "위쪽 40%를 비워 제목 자리" },
  "cards": [{
    "no": 1, "role": "표지", "title": "...", "keyLine": "...", "body": "...", "imageRole": "...", "imagePlan": "...",
    "sources": ["...README.md"], "note": "...",
    "image": {
      "status": "done", "version": 1, "tool": "agy | claude-cli-svg | mock-svg", "toolLabel": "...",
      "file": "card-01-v1.jpg", "format": "JPEG", "width": 896, "height": 1200, "bytes": 123456,
      "kind": "생성 이미지", "prompt": "그림 요청문", "createdAt": "...",
      "fallbackReason": "agy를 쓰지 않은 이유 (agy로 만들었으면 null)", "attempts": [{ "tool": "agy", "error": "..." }],
      "costUsd": 0.069, "error": null
    }
  }]
}
```
- `image.status`: `pending`(차례 기다림) / `generating` / `done` / `failed`(`error`에 이유). 파일이 실제 이미지인지 검사한 뒤에만 `done`.
- 프로젝트 `storyboardFeedback`: 반영한 변경 요청 목록.
- 새 상태: `storyboard_ready`(승인 기다림), `images_ready`(그림 작업 끝, 실패한 카드가 있을 수 있음).

### `POST /api/projects/{id}/render` (STEP 8)
`{ requestId }`. 그림이 있고, 아직 안 그렸거나 그림·글자·글자 모양이 바뀐 카드만 PNG로 다시 그린다. 그릴 게 없으면 `{ nothingToDo: true }`. 끝나면 `status: "cards_ready"`.

### `POST /api/projects/{id}/cards/{no}/text`
`{ requestId, title?, keyLine?, body?, layout? }`. **글자만** 고치고 그 카드만 다시 그린다(그림은 그대로).
- `layout`: `{ titleSize 40~100, keySize 26~64, bodySize 26~52, color: "dark"|"light", box: bool }`. `null`이면 자동 맞춤으로 되돌림. 범위를 벗어나면 400.
- 글자 길이 제한: 제목 80자, 핵심 문장 200자, 본문 600자.

### `GET /api/projects/{id}/cards/{file}`
완성 카드 PNG(`card-NN-rK.png`).

### 카드 데이터 (각 카드)
- `text`: 사용자가 고친 글자(없으면 스토리보드 원고 사용), `layout`: 사용자가 정한 글자 모양(없으면 자동 맞춤)
- `render`: `{ status, version, file, format, width, height, imageFile(쓴 그림), text, layout, usedLayout(실제 쓴 모양), checks, at }`
- `checks`: `{ limit, textBottom, overflow, wideWord, phoneBodyPx, smallOnPhone, contrast, overlapPct, lowContrast, autoFit(1 기본·2 제목 줄임·3 상자) }`

### 카드 렌더러 (`cardnews/render.py`)
카드 HTML(그림은 data URI) → Chrome `--headless=new --dump-dom`으로 검사 결과를 읽고 → `--screenshot`으로 1080×1350 PNG. 별도 프로필 폴더(`data\engine-work\<프로젝트>\render\chrome-profile`)를 써서 사용자가 쓰는 Chrome과 섞이지 않음. 그림은 `object-fit: cover`로 4:5에 맞춤. 오른쪽 아래에 그림 출처 표시("AI 생성 그림 (Antigravity)" / "AI 도형 그림 (Claude CLI)").

### STEP 9: 고치기·최종 승인·내보내기

| 요청 | 입력 | 결과·규칙 |
|---|---|---|
| `POST /api/projects/{id}/revisions` | `cardIds[]`, `instruction`(500자 이내), `scope: text\|image`, `requestId` | 고른 카드만. text: 엔진이 글만 고치고 그림 그대로 다시 그림. image: 수정 요청을 붙여 그림만 새 버전 → 다시 그림. 카드마다 `revision.history` 기록 |
| `POST /api/projects/{id}/cards/{no}/text` | (STEP 8 입력) + `sources[]` | 출처 목록도 고칠 수 있음 |
| `POST /api/projects/{id}/cards/{no}/remove` | `requestId` | 카드 빼기, 번호 다시 매김, 그림 유지, 모든 카드 다시 그려야 함 |
| `POST /api/projects/{id}/approve` | `stage: "final"`, `signature`, `requestId` | 화면이 본 카드 묶음 서명(`final.signature`)과 같아야 함(아니면 409 stale_version). 카드가 최신이 아니면 409 not_ready |
| `POST /api/projects/{id}/exports` | `requestId` | 최종 승인된 묶음만(아니면 409 not_approved). ZIP: `cards/01.png…`, `출처.md`, `이미지기록.md`, `image-log.json`, `README.md`. PC 경로는 자료 폴더 기준 상대 경로로 |
| `GET /api/projects/{id}/exports` | — | `{ finalOk, exports: [{file, bytes, at, signature, cards, current, verify}] }` |
| `GET /api/projects/{id}/exports/{file}` | — | ZIP 내려받기(첨부). 지금 승인된 묶음과 다르면 409 |
| `POST /api/projects/{id}/exports/{file}/verify` | — | ZIP을 직접 열어 검사. `rows: [{item, result: 통과\|실패\|확인 못 함, detail}]`, `counts` |

`GET /api/projects/{id}`에 `final: { ready, reason, signature, ok, approval }`가 붙는다. 최종 승인은 서명(카드 번호·PNG 파일·글)에 묶여 있어서 카드가 하나라도 바뀌면 `ok: false`가 된다.

### STEP 13: 사장님 도입 체크리스트

- `POST /api/projects`에 `workflow: "cardnews"(기본) | "checklist"`. checklist는 `sourcePath` 필수. 스토리보드·그림·카드 단계는 409.
- 조사(`research`)는 같은 API. 후보가 '반복 업무'로 바뀐다. 고르기(`selection`)도 같다.
- 편집 작업 결과: `editorial.checklist = { title, target, prepare[], steps[], cautions[] (각 {item, basis, basisFound}), missing[], note }`. `basisFound`는 앱이 조사·작성 때 **실제로 읽은 파일·원문**과 근거를 대조한 결과.
- 자료 부족 질문(`question.key = "material"`): `answer.text`에 **추가 자료 폴더 전체 경로**를 보내면 `extraSources`에 더해 다음 호출에 `--add-dir`로 함께 넘긴다(없는 경로는 400). `optionId: "as_is"`면 부족한 대로 만들고 빈칸은 `missing`에. `optionId: "more"`만 보내면 400("경로를 직접 입력에").
- `GET /api/projects/{id}/checklist.md`: 체크리스트 Markdown 내려받기(PC 경로는 상대 경로로).

### `POST /api/projects/{id}/retry`
`{ "requestId" }`. `failed / interrupted / cancelled`일 때 실패한 작업(`error.retryKind`)을 다시 시작한다. 이미 받은 후보·선택·답변은 그대로 둔다. 그림 작업이면 `done`이 아닌 카드만 다시 만든다.

### 그림 작업자 (`cardnews/images.py`)
1. 작업마다 `agy models`로 agy 설치·로그인 확인.
2. 가능하면 `agy -p "<내장 generate_image로 … 저장해 줘>" --output-format json`(작업 폴더 `data\engine-work\<프로젝트>\agy`). 응답의 대화 ID로 `~/.gemini/antigravity-cli/brain/<대화 ID>/`와 작업 폴더에서 **시작 뒤 새로 생기거나 바뀐** 그림을 찾아 복사. 응답 문장·종료 코드만으로 성공 처리하지 않음.
3. agy가 없거나 로그인·한도(429)·권한 문제면 남은 카드는 agy를 건너뛰고, 실패하면 그 카드만 claude cli 도형 그림으로 대신. 도형 그림은 프로젝트 대화와 따로(`--no-session-persistence`, 도구 없음) SVG 코드만 받아 script·text·외부 링크를 지우고 1080×1350으로 맞춤.
4. 저장: `data\projects\<프로젝트>\images\card-NN-vK.<형식>` (이전 버전 보관). PNG·JPEG·WEBP·SVG 머리 부분으로 형식과 크기를 검사.

### `POST /api/runs/{runId}/cancel`
본문 없음. 실행 중인 작업을 취소한다 → 프로젝트 `status: "cancelled"`. 취소 뒤 늦게 도착한 엔진 결과는 버린다.

## 작업 실패와 서버 재시작

| 상황 | 프로젝트에 남는 것 |
|---|---|
| 엔진이 오류를 돌려줌 | `status: "failed"`, `error: { code, message, retryKind }` (예: `search_failed`) |
| 엔진 출력이 약속한 형식이 아님 | `failed`, `code: "invalid_output"` — **완료로 처리하지 않는다** |
| 서버를 껐다 켬 | 돌던 작업은 `interrupted`, 이유와 다시 시도 버튼. `waiting_for_user` 질문은 그대로 남는다 |

## 엔진 연결 방식 (`cardnews/engines/`)

웹 서버는 엔진을 직접 기다리지 않는다. `jobs.Runner`가 별도 스레드에서 엔진을 부르고 결과를 저장한다.

| 엔진 함수 | 하는 일 | 돌려주는 것 |
|---|---|---|
| `research(ctx, emit, cancel)` | 넓은 조사 | `{"type": "result", "research": {...}}` 또는 `error` |
| `editorial(ctx, emit, cancel)` | 심층 조사·편집 판단 | `{"type": "need_input", "question": {...}}` 또는 `result`(`editorial`) 또는 `error` |

- `ctx`: 프로젝트 id, **엔진 세션 ID**, 주제, 자료 위치, 편집 방향, 기간, 고른 후보, 지금까지의 답변.
- `emit(message)`: 진행 상황 → `events`.
- `need_input`을 돌려주면 엔진 호출은 끝난다. 사용자가 답하면 앱이 같은 세션 ID와 답변을 담아 `editorial`을 다시 부른다. (같은 OS 프로세스가 계속 살아 있다는 뜻은 아니다.)
- 결과 형식은 `jobs._invalid()`가 검사한다.
- 엔진은 `--engine claude-cli`(기본) 또는 `--engine mock`.
- 결과에 `sessionId`가 있으면 앱이 프로젝트의 `engineSessionId`로 저장하고 `engineSessionStarted: true`로 표시한다. 첫 호출이 실패하면 새 세션 ID로 바꾼다.

### Claude CLI 엔진 (`engines/claude_cli.py`)

| 항목 | 방식 |
|---|---|
| 실행 파일 | npm의 `claude.cmd`가 아니라 그 안의 `bin\claude.exe`를 직접 실행 (`.cmd`는 cmd.exe가 인자를 다시 해석해 위험) |
| 프롬프트 | 명령줄이 아니라 **stdin**으로 전달 (주제·자료 내용이 명령으로 해석되지 않게) |
| 명령 | `claude.exe -p --output-format stream-json --verbose --model sonnet --effort medium --strict-mcp-config --allowedTools WebSearch WebFetch Read Glob Grep --disallowedTools Bash Edit Write NotebookEdit Task [--add-dir <자료 폴더>] (--session-id <ID> \| --resume <ID>)` |
| 세션 | 프로젝트별 ID. 첫 호출 `--session-id`, 이후 `--resume`. `--continue`(최근 세션)는 쓰지 않음 |
| 작업 폴더 | `data\engine-work\<프로젝트 ID>\` |
| 환경 | 데스크톱 앱 안에서 켠 셸이 물려준 `CLAUDECODE`, `CLAUDE_CODE_*` 등 호스트 세션 변수는 넘기지 않음 |
| 진행 상황 | stream-json의 `tool_use`(WebSearch 검색어, WebFetch URL, Read 파일)를 `events`와 `trace`에 기록 |
| 결과 해석 | 마지막 `result` 줄의 `is_error`·`subtype`을 먼저 보고, 성공이면 답변 안의 ```json 블록을 읽는다. 앱이 정한 `status: result / need_input / error` 형식이 아니면 `invalid_output` |
| 시간 제한·취소 | 한 번 호출 최대 15분. 취소·시간 초과·서버 종료 시 `taskkill /T /F`로 하위 프로세스까지 정리 |

엔진 오류 코드 (`error.code`):

| code | 뜻 |
|---|---|
| `auth_required` | Claude CLI 로그인 필요/만료 |
| `usage_limit` | 사용 한도·요청 제한 |
| `search_failed` | 웹 조사인데 검색이 한 번도 실행되지 않았거나, 엔진이 검색 실패를 알림 |
| `invalid_output` | 약속한 JSON 형식이 아님, 또는 이미 답한 질문을 다시 물음 |
| `engine_error` | CLI 비정상 종료 등 |
| `engine_unavailable` | claude를 실행하지 못함 |
| `timeout` | 15분 초과 |

실제 엔진 결과에 추가되는 필드:
- `research.trace`: `{ searches: [검색어], fetched: [원문 URL], files: [읽은 파일] }`, `research.costUsd`
- 후보: `eventDate`(실제 발표·변경일), `sourceRead`(그 후보의 출처를 실제로 읽었는지)
- `editorial`: `audience`, `audienceReason`, `purpose`, `formatCompare[{format, pros, cons}]`, `format`, `formatReason`, `hooks[{text, basis}]`, `verification{facts, claims, unknown: [{text, source}]}`, `conflicts`, `trace`, `costUsd`
- `GET /api/health`: `engineReady`, `engineNote` (서버를 켤 때 `claude auth status`로 확인한 로그인 여부)
