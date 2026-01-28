# DSUComfyCG

<div align="center">

![Version](https://img.shields.io/badge/version-0.8.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey)

**"One-Click, All-Ready"**

동서대학교 VFX/Animation 파이프라인을 위한 ComfyUI 통합 설치 & 워크플로우 배포 시스템

[설치하기](#-설치) • [매니저 사용법](#-매니저-사용법) • [Maya Bridge](docs/maya_bridge_guide.md) • [로드맵](docs/roadmap.md) • [문제해결](#-문제해결)

</div>

---

## 🎯 개요

DSUComfyCG는 복잡한 ComfyUI 환경을 **원클릭**으로 설치하고, VFX 워크플로우에 필요한 **노드와 모델을 자동으로 관리**하는 시스템입니다.

### 핵심 특징

| 기능 | 설명 |
|------|------|
| 🔧 **원클릭 설치** | Python, PyTorch, ComfyUI를 자동 설치 |
| 📦 **의존성 자동 해결** | 워크플로우에 필요한 노드/모델 자동 감지 |
| 🛡️ **Safety Net** | 의존성 충돌 감지 및 자동 롤백 |
| ⚡ **병렬 다운로드** | 대용량 모델 4-thread 병렬 다운로드 |
| 🎨 **Deep Space UI** | VFX 아티스트를 위한 다크 테마 |
| 🧳 **포터블** | USB로 통째로 이동 가능 |

---

## 🚀 설치

### 요구사항

- **OS**: Windows 10/11 (64-bit)
- **GPU**: NVIDIA GPU (CUDA 12.x 지원)
- **RAM**: 16GB 이상 권장
- **저장공간**: 최소 50GB (모델 포함 시 100GB+)
- **인터넷**: 첫 설치 시 필요

### 설치 방법

#### 1. 레포지토리 다운로드

```powershell
git clone https://github.com/jsdavid88-dsu/DSUComfyCG.git
cd DSUComfyCG
```

또는 [Releases](https://github.com/jsdavid88-dsu/DSUComfyCG/releases)에서 ZIP 다운로드

#### 2. 설치 스크립트 실행

```powershell
DSUComfyCG-Install.bat
```

설치되는 항목:
- ✅ Portable Python 3.12
- ✅ PyTorch 2.5.1 + CUDA 12.8
- ✅ ComfyUI Core
- ✅ ComfyUI-Manager
- ✅ VideoHelperSuite, IPAdapter, ControlNet 등 핵심 노드

#### 3. ComfyUI 실행

```powershell
Helper\run_comfy.bat
```

브라우저에서 `http://localhost:8188` 접속

---

## 🎛️ 매니저 사용법

DSUComfyCG Manager는 워크플로우의 의존성을 분석하고 자동으로 설치하는 GUI 도구입니다.

### 매니저 실행

```powershell
Manager\run_manager.bat
```

### 주요 기능

#### 1. 워크플로우 등록 및 검증

```
[워크플로우 탭]
1. "워크플로우 추가" 버튼 클릭
2. JSON 파일 선택
3. 자동으로 필요한 노드/모델 분석
4. "모두 설치" 클릭
```

<details>
<summary>📷 스크린샷 보기</summary>

![Workflow Validator](docs/images/workflow_validator.png)
*워크플로우를 로드하면 필요한 노드와 모델이 자동 분석됩니다*

</details>

#### 2. 노드 설치 현황

| 상태 | 의미 |
|------|------|
| ✅ 설치됨 | 해당 노드가 이미 설치됨 |
| 🔗 다운로드 대기 | URL이 확보되어 설치 준비됨 |
| ❓ Unknown | 노드 URL을 수동 입력 필요 |

#### 3. 모델 관리

```
[모델 탭]
- 워크플로우에 필요한 모델 자동 감지
- HuggingFace/CivitAI URL 자동 검색
- 병렬 다운로드 (4-thread)
```

#### 4. 시스템 상태 리포트

```
[상태 탭]
- ComfyUI 버전 확인
- 설치된 노드 목록
- 업데이트 필요 노드 표시
- "모두 업데이트" 원클릭
```

### Unknown 노드 해결

워크플로우에 DB에 없는 노드가 있을 경우:

1. 노드 이름 우클릭 → "이름 복사"
2. GitHub에서 해당 노드 검색
3. URL 입력 다이얼로그에 Git URL 붙여넣기
4. 자동으로 DB에 저장 (다음부터 자동 인식)

---

## 📁 폴더 구조

```
DSUComfyCG/
├── DSUComfyCG-Install.bat     # 설치 스크립트
├── Helper/
│   ├── run_comfy.bat          # ComfyUI 실행
│   └── scan_and_install.py    # 자동 의존성 스캐너
├── Manager/
│   ├── run_manager.bat        # 매니저 GUI 실행
│   ├── core/
│   │   └── checker.py         # 의존성 검사 엔진
│   ├── data/
│   │   ├── extension-node-map.json  # 노드 DB
│   │   └── model-list.json          # 모델 DB
│   └── ui/
│       ├── manager_window.py  # 메인 UI
│       └── workflow_validator.py
├── workflows/                  # 워크플로우 JSON
└── docs/
    └── roadmap.md             # 프로젝트 로드맵
```

---

## ⚡ 주요 기능 상세

### 1. 의존성 Safety Net

노드 설치 시 패키지 충돌을 사전에 감지하고 자동 롤백:

```
1. 설치 전 pip freeze 스냅샷
2. requirements.txt 분석 → 충돌 경고
3. 설치 후 pip check 검증
4. 문제 발생 시 자동 복구
```

### 2. 병렬 다운로드

대용량 모델 다운로드 속도 향상:

```
- 50MB 이상 파일: 4-thread 병렬 다운로드
- Range 헤더 지원 서버 자동 감지
- 실패 시 3회 재시도
- 전체 진행률 실시간 표시
```

### 3. 스마트 모델 파싱

워크플로우 JSON에서 모델 정보 자동 추출:

```json
// 워크플로우에 URL이 포함된 경우
"ckpt_name": "model.safetensors [https://huggingface.co/...]"
```

### 4. Standard VFX Pack (예정)

VFX 작업에 필수적인 워크플로우 템플릿:

| 워크플로우 | 용도 |
|-----------|------|
| AI Inpainting | 객체 제거, 클린 플레이트 |
| AI Outpainting | 배경 확장 |
| 4K/8K Upscale | 고해상도 디테일 복원 |
| Image-to-Video | 정지 이미지에서 영상 생성 |
| Multi-Pass | Depth/Normal/Mask 추출 |

### 🔒 Gated 모델 안내

일부 모델은 HuggingFace에서 **라이선스 동의 후에만** 다운로드 가능합니다:

| 모델 | 워크플로우 | 해결 방법 |
|------|-----------|----------|
| **FLUX.1** | 고품질 이미지 생성 | HuggingFace 가입 → 라이선스 동의 → 토큰 발급 |
| **LTX-Video** | Image-to-Video | HuggingFace 가입 → 라이선스 동의 → 직접 다운로드 |
| **Stable Diffusion 3** | SD3 워크플로우 | Stability AI 약관 동의 필요 |

**해결 방법 (택1):**

1. **HuggingFace 토큰 사용**
   ```powershell
   # 환경변수 설정
   $env:HF_TOKEN = "hf_your_token_here"
   ```

2. **직접 다운로드**
   - [HuggingFace](https://huggingface.co)에서 해당 모델 페이지 방문
   - 라이선스 동의 후 수동 다운로드
   - `ComfyUI/models/checkpoints/` 폴더에 배치

> 💡 **대부분의 모델 (SDXL, ControlNet, LoRA 등)은 토큰 없이 자동 다운로드됩니다.**

---

## 🛠️ 문제해결

### 설치 오류

| 문제 | 해결 |
|------|------|
| Python 다운로드 실패 | 인터넷 연결 확인, 방화벽 해제 |
| CUDA 오류 | NVIDIA 드라이버 최신 버전 설치 |
| Git 없음 | `winget install Git.Git` 실행 |

### 실행 오류

| 문제 | 해결 |
|------|------|
| 포트 8188 사용 중 | 기존 ComfyUI 프로세스 종료 |
| 모듈 찾을 수 없음 | `pip install -r requirements.txt` |
| 노드 로딩 실패 | Manager에서 해당 노드 재설치 |

### 매니저 오류

| 문제 | 해결 |
|------|------|
| UI가 안 열림 | Python 경로 확인 (`python_embeded`) |
| 노드 설치 실패 | Git 설치 확인, URL 형식 확인 |
| 모델 다운로드 멈춤 | 네트워크 확인, HF 토큰 설정 |

---

## 📋 로드맵

자세한 개발 로드맵은 [docs/roadmap.md](docs/roadmap.md)를 참조하세요.

### 현재 진행 상황

```
Phase 1 ████████████████████ 100%  ✅ Foundation
Phase 2 ██████████░░░░░░░░░░  50%  🔄 Content & Tools
Phase 3 ░░░░░░░░░░░░░░░░░░░░   0%  ⏳ DCC Integration
```

### 예정 기능

- 🎬 **Cinematic Prompt Builder**: 시각적 카메라/조명 선택기
- 🧊 **3D Reconstruction**: Apple SHARP, Gaussian Splatting
- 🌉 **Maya Bridge**: 양방향 DCC 연동

---

## 📚 문서

- **[Installation Guide](docs/installation.md)**: 상세 설치 가이드
- **[Manager Guide](docs/manager_guide.md)**: 매니저 기능 및 사용법
- **[Maya Bridge Guide](docs/maya_bridge_guide.md)**: Maya 연동 및 3D 워크플로우
- **[Roadmap](docs/roadmap.md)**: 전체 개발 계획

---

## 🤝 기여

버그 리포트, 기능 제안, PR 환영합니다!

1. Fork 후 feature branch 생성
2. 변경사항 커밋
3. Pull Request 제출

---

## 📄 License

MIT License - 동서대학교 CG 교육용

Copyright (c) 2026 동서대학교 글로컬대학30 가상융합기술연구원 & 빨간고양이단주식회사

---

<div align="center">

**공동연구:** 동서대학교 글로컬대학30 가상융합기술연구원 & 빨간고양이단주식회사 ([redcatgangs.com](https://redcatgangs.com))

Made with ❤️ for VFX Artists

[⬆ 맨 위로](#dsucomfycg)

</div>


