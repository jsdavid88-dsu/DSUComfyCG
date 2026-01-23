# 설치 가이드

이 문서는 DSUComfyCG의 상세 설치 과정을 설명합니다.

---

## 📋 사전 요구사항

### 하드웨어
| 항목 | 최소 사양 | 권장 사양 |
|------|----------|----------|
| **GPU** | GTX 1060 6GB | RTX 3060 12GB+ |
| **RAM** | 16GB | 32GB |
| **저장공간** | 50GB | 100GB+ |
| **CPU** | Intel i5 / AMD Ryzen 5 | Intel i7 / AMD Ryzen 7 |

### 소프트웨어
- **OS**: Windows 10/11 (64-bit)
- **NVIDIA Driver**: 535.xx 이상 (CUDA 12.x 지원)
- **Git**: 자동 설치됨 (없을 경우)

---

## 🚀 설치 단계

### Step 1: 레포지토리 다운로드

#### 방법 A: Git Clone (권장)
```powershell
cd C:\Users\YourName\Documents
git clone https://github.com/jsdavid88-dsu/DSUComfyCG.git
cd DSUComfyCG
```

#### 방법 B: ZIP 다운로드
1. GitHub에서 **Code** → **Download ZIP**
2. 원하는 폴더에 압축 해제

> ⚠️ **주의**: 경로에 한글이나 공백이 없는 것을 권장

### Step 2: 설치 스크립트 실행

```powershell
DSUComfyCG-Install.bat
```

설치 과정:
```
1. Git 설치 확인 (없으면 winget으로 자동 설치)
2. Portable Python 3.12 다운로드 (~25MB)
3. pip 업그레이드
4. PyTorch 2.5.1 + CUDA 12.8 설치 (~2.5GB)
5. ComfyUI 클론 (~100MB)
6. ComfyUI-Manager 설치
7. 핵심 노드 설치 (VideoHelperSuite, IPAdapter 등)
```

⏱️ **예상 소요 시간**: 10-30분 (네트워크 속도에 따라)

### Step 3: 설치 확인

```powershell
Helper\run_comfy.bat
```

성공 시 출력:
```
Starting ComfyUI...
To see the GUI go to: http://127.0.0.1:8188
```

브라우저에서 `http://localhost:8188` 접속

---

## 📦 자동 설치되는 구성요소

### Python 환경
- **Portable Python 3.12.3**: 시스템 Python과 격리
- **pip**: 최신 버전
- **venv**: 가상환경 (선택)

### PyTorch
- **PyTorch 2.5.1**: CUDA 12.8 빌드
- **torchvision, torchaudio**: 호환 버전

### ComfyUI 패키지
| 패키지 | 버전 | 용도 |
|--------|------|------|
| ComfyUI | latest | 코어 |
| ComfyUI-Manager | latest | 노드 관리 |
| VideoHelperSuite | latest | 비디오 처리 |
| ComfyUI-IPAdapter-plus | latest | IP Adapter |
| ComfyUI-ControlNet-Aux | latest | ControlNet |
| ComfyUI-LTXVideo | latest | LTX Video |
| ComfyUI-WanVideoWrapper | latest | Wan Video |

---

## 🔧 수동 설치 (고급)

자동 설치가 실패할 경우 수동으로 진행:

### 1. Python 다운로드
```powershell
Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.12.3/python-3.12.3-embed-amd64.zip" -OutFile python.zip
Expand-Archive python.zip -DestinationPath python_embeded
```

### 2. pip 설치
```powershell
Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile get-pip.py
.\python_embeded\python.exe get-pip.py
```

### 3. PyTorch 설치
```powershell
.\python_embeded\Scripts\pip.exe install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

### 4. ComfyUI 클론
```powershell
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI
..\python_embeded\Scripts\pip.exe install -r requirements.txt
```

---

## ❓ 문제해결

### Python 다운로드 실패
```
Error: Unable to download Python
```
**해결**: 
1. 방화벽/백신 일시 해제
2. VPN 연결 확인
3. 수동 다운로드 후 `python_embeded` 폴더에 압축 해제

### CUDA 오류
```
CUDA out of memory / CUDA not available
```
**해결**:
1. NVIDIA 드라이버 업데이트: https://nvidia.com/drivers
2. 다른 GPU 프로그램 종료
3. `--lowvram` 옵션으로 실행

### Git 설치 실패
```
'git' is not recognized
```
**해결**:
```powershell
winget install Git.Git
# 또는
# https://git-scm.com/download/win 에서 수동 설치
```

### 포트 충돌
```
Port 8188 already in use
```
**해결**:
1. 기존 ComfyUI 프로세스 종료
2. 또는 다른 포트로 실행:
```powershell
python main.py --port 8189
```

---

## 🔄 업데이트

### ComfyUI 업데이트
```powershell
cd ComfyUI
git pull origin master
```

### 노드 일괄 업데이트
Manager GUI에서 **상태 탭** → **모두 업데이트** 클릭

---

## 🗑️ 완전 삭제

DSUComfyCG 폴더 전체를 삭제하면 됩니다.
시스템에 설치된 것이 없으므로 레지스트리 정리 불필요.

```powershell
# 선택: Git만 시스템에 설치됨
winget uninstall Git.Git
```

---

*[← README로 돌아가기](../README.md)*
