# API_SPEC — 화면과 서버의 약속

PRD.md의 "웹 API 계약 초안"을 Python 구현(`cardnews/server.py`)에 맞춰 확정한 문서다.
지금 구현된 범위는 **주제 입력 → 조사 → 후보 선택 → 질문·답변 → 편집 방향(심층 검증 포함)**까지다(STEP 5, 모의 엔진과 Claude CLI 엔진).
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

### `POST /api/projects/{id}/retry`
`{ "requestId" }`. `failed / interrupted / cancelled`일 때 실패한 작업(`error.retryKind`)을 다시 시작한다. 이미 받은 후보·선택·답변은 그대로 둔다.

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
