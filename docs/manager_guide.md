# 매니저 사용 가이드

DSUComfyCG Manager는 워크플로우의 의존성을 분석하고 자동으로 설치하는 GUI 도구입니다.

---

## 🚀 실행

```powershell
cd DSUComfyCG
Manager\run_manager.bat
```

---

## 🎛️ 메인 화면

Manager는 3개의 탭으로 구성됩니다:

| 탭 | 기능 |
|---|------|
| **워크플로우** | 워크플로우 등록, 의존성 분석, 노드/모델 설치 |
| **상태** | 시스템 상태 확인, 업데이트 관리 |
| **Standard Pack** | DSU 표준 VFX 워크플로우 템플릿 |

---

## 📁 워크플로우 탭

### 워크플로우 등록

1. **"워크플로우 추가"** 버튼 클릭
2. JSON 파일 선택
3. 자동으로 노드/모델 분석 시작

### 의존성 분석 결과

#### 노드 상태
| 상태 | 아이콘 | 의미 | 조치 |
|------|--------|------|------|
| 설치됨 | ✅ | 노드가 이미 설치됨 | 없음 |
| 다운로드 대기 | 🔗 | URL 확보됨, 설치 준비 | "설치" 클릭 |
| Unknown | ❓ | DB에 없는 노드 | URL 수동 입력 |

#### 모델 상태
| 상태 | 아이콘 | 의미 | 조치 |
|------|--------|------|------|
| 설치됨 | ✅ | 모델 파일 존재 | 없음 |
| 다운로드 대기 | 🔗 | URL 확보됨 | "다운로드" 클릭 |
| Unknown | ❓ | URL 모름 | URL 수동 입력 |

### 일괄 설치

모든 의존성을 한 번에 설치:
1. **"모두 설치"** 버튼 클릭
2. 진행률 표시줄에서 상태 확인
3. 완료 후 ComfyUI 재시작

---

## ❓ Unknown 노드 해결

DB에 없는 노드가 있을 경우:

### 방법 1: 우클릭 복사 후 검색
1. 노드 이름 **우클릭** → **"이름 복사"**
2. GitHub에서 검색: `comfyui {노드이름}`
3. 찾은 레포지토리 URL 복사

### 방법 2: URL 입력
1. Unknown 노드의 **"URL 입력"** 버튼 클릭
2. Git URL 붙여넣기
   - 형식: `https://github.com/user/repo`
3. **"확인"** 클릭
4. 자동으로 DB에 저장됨 (다음부터 자동 인식)

### 예시 URL
```
https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite
https://github.com/cubiq/ComfyUI_IPAdapter_plus
https://github.com/Fannovel16/comfyui_controlnet_aux
```

---

## 📊 상태 탭

### 시스템 정보
- ComfyUI 버전
- Python 버전
- PyTorch 버전
- CUDA 버전

### 설치된 노드 목록
- 모든 커스텀 노드 표시
- 업데이트 필요 노드 하이라이트

### 업데이트
| 버튼 | 기능 |
|------|------|
| **체크** | 업데이트 가능 노드 확인 |
| **모두 업데이트** | git pull 일괄 실행 |
| **ComfyUI 업데이트** | ComfyUI 코어 업데이트 |

---

## 📦 Standard Pack 탭

DSU 표준 VFX 워크플로우 템플릿:

| 워크플로우 | 용도 |
|-----------|------|
| AI Inpainting | 객체 제거, 클린 플레이트 생성 |
| AI Outpainting | 배경 확장 / Set Extension |
| 4K/8K Upscale | 고해상도 디테일 복원 |
| Image-to-Video | 정지 이미지에서 모션 생성 |
| Multi-Pass | Depth/Normal/Mask 추출 |

### 설치 방법
1. 원하는 워크플로우 선택
2. **"설치"** 클릭
3. 필요한 노드/모델 자동 설치
4. `workflows/` 폴더에 JSON 복사됨

---

## ⚡ 고급 기능

### 병렬 다운로드
50MB 이상 모델은 자동으로 4-thread 병렬 다운로드:
- Range 헤더 지원 서버 자동 감지
- 실패 시 3회 재시도
- 진행률 실시간 표시

### 의존성 Safety Net
노드 설치 시 자동 보호:
1. 설치 전 pip freeze 스냅샷
2. requirements.txt 분석 → 충돌 경고
3. 설치 후 pip check 검증
4. 문제 발생 시 자동 롤백

### 스마트 모델 파싱
워크플로우 JSON에서 모델 정보 자동 추출:
```json
// URL이 포함된 경우 자동 인식
"ckpt_name": "model.safetensors [https://huggingface.co/...]"
```

---

## 🛠️ 문제해결

### 매니저가 열리지 않음
```
Error: Python not found
```
**해결**: DSUComfyCG-Install.bat 다시 실행

### 노드 설치 실패
```
Error: git clone failed
```
**해결**: 
1. Git 설치 확인: `git --version`
2. 인터넷 연결 확인
3. URL 형식 확인 (https://...)

### 모델 다운로드 멈춤
```
Download stalled at 0%
```
**해결**:
1. HuggingFace 토큰 설정 (gated 모델)
2. 방화벽 확인
3. VPN 연결 시도

### 의존성 충돌 경고
```
Warning: Dependency conflict detected
```
**해결**:
- 경고 메시지 확인
- 문제 패키지 수동 버전 조정
- 또는 무시하고 진행 (자동 롤백 보호됨)

---

## 📋 단축키

| 키 | 기능 |
|----|------|
| `Ctrl+C` | 선택 항목 이름 복사 |
| `F5` | 목록 새로고침 |
| `Delete` | 선택 워크플로우 제거 |

---

## 🔗 관련 문서

- [설치 가이드](installation.md)
- [로드맵](roadmap.md)
- [README](../README.md)

---

*[← README로 돌아가기](../README.md)*
