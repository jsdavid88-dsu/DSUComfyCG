# DSUComfyCG Manager: 아키텍처 및 철학 (Architecture & Philosophy)

## 1. 프로그램 철학 (Philosophy)
본 프로그램은 **"전문적인 3D/AI 그래픽스 환경을, 완전한 초보자(바보)라도 클릭 한 번으로 무설치(Zero-Dependency) 구동할 수 있어야 한다"**는 극단적인 사용자 친화적 철학을 바탕으로 설계되었습니다.

- **Zero-Dependency (완전 무설치):** 사용자의 PC에 Git, Python, CUDA 등 그 어떤 개발 환경도 설치되어 있을 필요가 없습니다. USB에 담아서 포맷 직후의 깡통 PC에 꽂아도 완벽하게 작동해야 합니다.
- **Isolation & Portability (격리 및 호환성):** 시스템 레벨의 환경 변수나 폴더를 오염시키지 않으며 오직 프로젝트 루트 폴더(`DSUComfyCG/`) 내부에서만 동작합니다.
- **Resource Efficiency (자원 효율성):** 코어 프로그램은 완벽히 격리(Multi-Environment)하되, 무거운 AI 모델 파일(Checkpoints, LoRA 등)은 단일 공유 폴더를 통해 모든 환경이 함께 쓰도록 하여 수백 GB의 디스크 낭비를 원천 차단합니다.

---

## 2. 만든 이유 (Why We Built This? / Origin Story)
현재 오픈소스 생태계(특히 ComfyUI와 부가 Custom Node들)는 극도로 파편화되어 있습니다.
1. **의존성 지옥 (Dependency Hell):** 일반 사용자가 ComfyUI를 시작하려면 Python 버전을 맞추고, Git을 설치하여 환경 변수를 잡고, PyTorch와 CUDA 버전을 일치시켜야만 했습니다.
2. **업데이트의 늪:** 시간이 지남에 따라 플러그인(Custom Nodes)들이 서로 충돌하기 시작하며, 기존 ZIP 압축 해제 방식은 `git pull` 업데이트를 지원하지 않아 유지보수가 완전히 불가능했습니다.
3. **환경 분리 불가:** 최신 기술(dev)을 테스트하다가 기존 업무 환경(stable)이 부서지는 일이 잦았습니다. 이를 막기 위해 ComfyUI를 여러 개 깔면, 수십 GB에 달하는 모델 파일들이 중복으로 복사되어 디스크 용량이 폭발합니다.

이러한 고통을 끊어내고자 **레퍼런스(`ComfyUI-Easy-Install`)의 안정성을 계승하면서도, 다중 환경-단일 모델 구조를 지닌 궁극의 매니저 UI**를 개발하게 되었습니다.

---

## 3. 핵심 기능 (Features)

1. **Self-Bootstrapping (자가 복구/설치 메커니즘):**
   - 최초 실행 시 `DSU_Manager.bat`이 시스템의 Git과 Python 유무를 판단.
   - 누락되었다면 백그라운드에서 공식 **MinGit 포터블 버전(2.47)**과 **Python 3.12 Embedded(포터블)**을 자동 표적 다운로드 및 폴더 내 압축 해제합니다.
2. **다중 환경(Multi-Environment) 독립 샌드박스:**
   - 안정화 버전(`stable`), 최신 버전(`latest`), 개발 버전(`dev`) 등 환경별로 독립된 ComfyUI 저장소와 Python 패키징(venv)을 분리합니다.
3. **중앙 집중식 모델 공유 (Shared Models Linker):**
   - 각 독립 환경의 `extra_model_paths.yaml`을 자동 생성/수정하여 부모 폴더의 `models/` 디렉토리를 바라보게 합니다.
4. **선택적 애드온 및 최적화 노드 원클릭 설치 (UI):**
   - SageAttention, FlashAttention, Nunchaku, ONNX Runtime GPU 기반 최적화 모듈을 체크박스 하나로 자동 컴파일 및 설치합니다.
5. **Git 기반 개별 무결성 업데이트:**
   - 임시 ZIP 다운로드를 버리고 100% `git clone` 기반으로 설치하여, 추후 언제든 매니저 UI 버튼으로 개별 노드 및 코어를 `git pull` 로 손상 없이 업데이트합니다.

---

## 4. 상세 기술 스펙 (Technical Specifications)

### 시스템 스택
- **Language & Runtime:** Python 3.12.10 (Embedded) / Python 3.12.8 (System fallback)
- **Deep Learning Framework:** PyTorch 2.9.1 / TorchVision 0.24.1 / TorchAudio 2.9.1
- **CUDA Toolkit (Built-in via PyTorch):** cu130 (CUDA 13.0)
- **Package Manager:** `uv` (v0.9.7) — 컴파일 캐시 및 링킹을 극대화한 초고속 Rust 기반 패키지 매니저
- **UI Framework:** PySide6 (Qt for Python 6)

### 디렉토리 구조 (Directory Architecture)
```text
DSUComfyCG/
│
├── DSU_Manager.bat         # 1. 진입점: Git/Python 무설치 자체 조달 스크립트
├── Manager/                # 2. 매니저 소스 (UI 및 비즈니스 로직 - PySide6)
│   ├── main.py
│   ├── ui/                 # 다이얼로그 및 창 UI 컴포넌트
│   └── core/               # 패키지 컴파일, Git 체커, 다운로드 모듈
│
├── git_portable/           # (자동생성) 무설치 포터블 Git 엔진
├── python_embeded/         # (자동생성) 무설치 포터블 Python 엔진
│
├── models/                 # 3. [공유 모델 폴더] 모든 Checkpoint, LoRA 중앙 보관
├── workflows/              # 4. [공유 워크플로우 폴더]
│
└── envs/                   # 5. [격리 환경 폴더]
    ├── stable/             # ├─ 안정 환경 (독립된 python312._pth 경로를 가짐)
    │   ├── ComfyUI/
    │   └── python_embeded/ # (선택 시 이 안에 별도 격리 Python 구성)
    ├── latest/             # ├─ 최신 환경
    └── dev/                # └─ 개발 환경
```

---

## 5. 작동 흐름 (How it works under the hood)

### Step 1: Bootstrap (`DSU_Manager.bat`)
일반 사용자가 `DSU_Manager.bat`을 더블 클릭하면:
1. 시스템 메모리에 `curl` 또는 `powershell Invoke-WebRequest`를 사용하여 GitHub에서 `MinGit.zip`을 받아옵니다.
2. `git_portable/` 로 압축을 풉니다.
3. 동일하게 `Python 3.12 Embedded.zip`을 받아 `python_embeded/`로 풀고, `get-pip.py`를 실행해 `pip`를 주입합니다.
4. 해당 포터블 파이썬 환경의 PATH를 임시 오버라이드한 상태에서 `PySide6`를 설치하고 `Manager/main.py`를 뛰웁니다.
5. *(이 모든 과정이 진행바 형태로 유저 모르게 백그라운드 처리되며 "관리자 권한"을 일절 묻지 않습니다.)*

### Step 2: UI Manager & Installation (`checker.py`)
매니저가 열리고 **[Install ComfyUI]** 버튼을 누르면 다음 시퀀스가 실행됩니다.
1. `uv` 고속 패키지 매니저 활성화.
2. `git clone`을 통해 `Comfy-Org/ComfyUI` 소스코드를 지정한 환경(`envs/[이름]/ComfyUI`)에 다운로드합니다.
3. 환경별 전용 파이썬 인터프리터 안에 PyTorch+CUDA130 및 의존성 라이브러리를 설치합니다.
4. 유저가 선택한 Custom Nodes (ComfyUI-Manager, Easy-Use 등) 들을 연속으로 `git clone` 하고 각 폴더의 `requirements.txt`를 `uv`로 순식간에 설치합니다.
5. 유저가 선택한 Addon (Nunchaku 등)의 특정 버전에 맞는 Wheel(`.whl`) 파일을 직접 매핑하여 강제 주입(Monkey-patching)합니다.

### Step 3: Shared Linker & Execution
1. 설치가 마무리되기 직전, `checker.py` 내의 링커가 `envs/[이름]/ComfyUI/extra_model_paths.yaml` 파일을 덮어쓰기 생성합니다.
2. 저장된 경로는 `base_path: ../../../models` (즉, 루트의 `DSUComfyCG/models/`)를 향하게 되어, 유저는 ComfyUI를 어떤 환경으로 열든 동일하게 폴더 밖의 모델들을 가져다 쓸 수 있습니다.
3. 사용자가 UI에서 특정 환경의 **[실행]**을 누르면 매니저는 해당 환경의 파이썬 인터프리터를 정확히 타게팅하여 독립적으로 ComfyUI 프로세스를 띄웁니다.

---

## 6. 설계 규칙 (Design Rules)

코드 작성 및 수정 시 반드시 준수해야 하는 불변 규칙입니다.

### Rule 1: Portable-First (포터블 우선 정책)

시스템에 Git/Python이 설치되어 있더라도, **항상 포터블 버전을 우선 사용**합니다.

```
탐색 순서 (Git):
  1. git_portable/cmd/git.exe      ← 최우선
  2. 시스템 PATH의 git              ← 포터블 없을 때만 fallback

탐색 순서 (Python):
  1. envs/[env]/python_embeded/python.exe   ← 환경별 전용 (최우선)
  2. python_embeded/python.exe              ← 루트 포터블
  3. 시스템 PATH의 python                    ← 최후의 fallback (경고 로그 필수)
```

**이유:** 시스템 Python이 3.9일 수도, Git이 구버전일 수도 있습니다. 버전 불일치로 인한 장애를 원천 차단하려면 우리가 제공한 버전을 쓰는 게 확정적(deterministic)입니다.

**위반 금지 사항:**
- `shutil.which("python")`으로 시스템 Python을 찾아서 쓰는 것 → 반드시 포터블 경로 탐색 이후 최후 fallback에서만 허용
- `subprocess.run(["git", ...])` 호출 전 `ensure_git_installed()` 또는 `setup_portable_git()` 미호출 → 모든 git 호출 전 반드시 포터블 git PATH 보장

### Rule 2: Git 버전 단일화

bat과 Python(checker.py)에서 다운로드하는 Git 패키지는 **동일한 버전, 동일한 형식**이어야 합니다.

```
공식 소스: MinGit-{VERSION}-64-bit.zip
설치 위치: git_portable/
```

**위반 금지 사항:**
- bat에서 MinGit 2.47, Python에서 PortableGit 2.44 같은 버전 불일치
- `.7z.exe` 자가 압축 해제 방식 사용 → zip 통일

### Rule 3: 공유 모델 폴더 — 전체 타입 커버리지

`extra_model_paths.yaml`에 링크하는 모델 서브디렉토리는 `models_db.json`의 `folder_mappings`에 정의된 **모든 타입**을 포함해야 합니다.

```yaml
# 필수 링크 대상 (models_db.json folder_mappings 기준)
checkpoints, loras, vae, clip, clip_vision, unet,
controlnet, upscale_models, embeddings,
diffusion_models, text_encoders,
sam2, LLM, audio, rife, yolo, dwpose
```

새로운 모델 타입이 `models_db.json`에 추가되면, yaml 생성 로직도 반드시 동기화해야 합니다. 누락 시 해당 타입의 모델이 환경마다 중복 다운로드됩니다.

**단일 진실 공급원(Single Source of Truth):** `models_db.json`의 `folder_mappings`가 모델 타입의 정의입니다. yaml 생성 코드에 타입을 하드코딩하지 말고, `folder_mappings`에서 동적으로 읽어야 합니다.

### Rule 4: 경로 해석 기준 (Path Resolution)

모든 경로는 **저장 시 상대경로, 사용 시 절대경로로 resolve** 합니다.

```
저장 (envs.json, extra_model_paths.yaml):
  → BASE_DIR 기준 상대경로: "envs/stable/ComfyUI"

사용 (Python 코드 내부):
  → _resolve_path()로 절대경로 변환: os.path.join(BASE_DIR, relative_path)
```

**extra_model_paths.yaml의 경로 해석:**
- `base_path`는 해당 yaml 파일이 위치한 ComfyUI 디렉토리 기준 상대경로
- Python 코드에서 `EXTRA_MODEL_PATHS`로 로딩할 때는 반드시 **ComfyUI 디렉토리를 기준으로 resolve**하여 절대경로로 변환

**위반 금지 사항:**
- `EXTRA_MODEL_PATHS`에 상대경로 문자열을 그대로 저장한 뒤, 나중에 `BASE_DIR` 기준으로 join → 잘못된 경로
- `os.path.join(BASE_DIR, "../../../models")` → resolve 기준 오류
- `envs.json`에 절대경로 저장 → 폴더 이동 시 깨짐

### Rule 5: 패키지 매니저 사용 기준 (uv vs pip)

```
uv 사용 (기본):
  - ComfyUI requirements.txt 설치
  - Custom Node requirements.txt 설치
  - 일반 PyPI 패키지 설치

pip 직접 사용 (예외):
  - PyTorch 설치 (커스텀 index-url 필요, uv 호환성 불확실)
  - Wheel 직접 주입 (addon .whl 파일)
  - uv 자체 설치 (pip install uv)
```

post-install 노드 추가(`install_node`)에서도 `uv`를 사용해야 합니다. pip fallback은 uv가 설치되지 않은 환경에서만 허용합니다.

### Rule 6: 프로세스 격리 (Subprocess Isolation)

ComfyUI 프로세스를 spawn할 때, 자식 프로세스의 `PATH` 환경 변수에서 **시스템 Python/Git 경로를 제거**하고 포터블 경로만 남겨야 합니다.

```python
# 올바른 방식
env = os.environ.copy()
env["PATH"] = f"{portable_git_path};{portable_python_path};{minimal_system_path}"
subprocess.Popen([python_exe, "main.py", ...], env=env)
```

**이유:** 시스템 PATH에 다른 Python이 있으면, Custom Node의 subprocess 호출이 시스템 Python을 타게팅할 수 있음.

### Rule 7: 네트워크 회복력 (Network Resilience)

모든 다운로드 작업에는 다음이 필수입니다:
- **타임아웃**: 연결 10초, 읽기 30초
- **재시도**: 최소 3회 (지수 백오프)
- **에러 체크**: 다운로드 완료 후 파일 존재 및 크기 검증
- **부분 다운로드 정리**: 실패 시 불완전 파일 삭제

bat 스크립트에서도 동일: `Invoke-WebRequest` 실패 시 재시도 또는 명확한 에러 메시지.

### Rule 8: extra_model_paths 로더 단일화

`EXTRA_MODEL_PATHS`를 로딩하는 함수는 **단 하나**만 존재해야 합니다.

**규칙:** `read_extra_model_paths()` 하나만 존재하며, 모듈 초기화 시와 환경 전환 시 동일한 함수를 호출합니다.

---

## 7. 기술 부채 이력 (Technical Debt History)

아래는 2026-03-28 코드리뷰에서 식별되어 **모두 해소된** 기술 부채 목록입니다.

| ID | 규칙 | 상태 | 해소 내용 |
|----|------|------|-----------|
| TD-01 | Rule 1 | ✅ 해소 | `DSU_Manager.bat` 포터블 우선 탐색으로 순서 역전 |
| TD-02 | Rule 1 | ✅ 해소 | `scan_and_install.py` portable git PATH 설정 + python 경로 수정 |
| TD-03 | Rule 1 | ✅ 해소 | `run_comfy.bat` portable git PATH + multi-env 경로 |
| TD-04 | Rule 1 | ✅ 해소 | `perform_update()` ensure_git_installed() 추가 |
| TD-05 | Rule 1 | ✅ 해소 | `check_comfyui_version()`, `check_custom_nodes_updates()` 동일 |
| TD-06 | Rule 2 | ✅ 해소 | checker.py를 MinGit 2.47 zip으로 통일 |
| TD-07 | Rule 3 | ✅ 해소 | yaml 생성 시 `FOLDER_MAPPINGS`에서 동적 읽기 |
| TD-08 | Rule 4 | ✅ 해소 | `read_extra_model_paths()` ComfyUI 기준 절대경로 resolve |
| TD-09 | Rule 5 | ✅ 해소 | `install_node()` uv 우선, pip fallback |
| TD-10 | Rule 6 | ✅ 해소 | `run_comfyui()` PATH 정리 + env 전달 |
| TD-11 | Rule 7 | ✅ 부분해소 | ensure_git_installed + bat 다운로드 재시도 추가 (일부 urlretrieve에 타임아웃 미적용) |
| TD-12 | Rule 8 | ✅ 해소 | `load_extra_model_paths()` 삭제, `read_extra_model_paths()` 단일화 |
