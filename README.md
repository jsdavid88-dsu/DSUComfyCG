# DSUComfyCG

> 동서대학교 CG 전공을 위한 ComfyUI 원클릭 설치 & 워크플로우 배포 시스템

## 🚀 빠른 시작

1. `DSUComfyCG-Install.bat` 더블클릭
2. 설치 완료 후 `run_comfy.bat` 실행
3. 브라우저에서 `http://localhost:8188` 접속

## 📦 자동 설치되는 것들

- **Portable Python 3.12** (시스템 설치 불필요)
- **PyTorch + CUDA 12.8**
- **ComfyUI + ComfyUI-Manager**
- **핵심 노드**: VideoHelperSuite, IPAdapter, ControlNet, LTXVideo, WanVideo

## ✨ 주요 기능

### 워크플로우 기반 자동 설치
`workflows/` 폴더에 JSON 파일을 넣고 `run_comfy.bat` 실행하면:
- 필요한 노드 자동 감지 & 설치
- requirements.txt, install.py 자동 실행

### 포터블 환경
- 폴더 전체를 USB로 옮겨도 동작
- 시스템에 흔적 없음 (Git 제외)

## 📁 구조

```
DSUComfyCG/
├── DSUComfyCG-Install.bat   ← 설치 스크립트
├── Helper/
│   ├── run_comfy.bat        ← 실행 스크립트
│   └── scan_and_install.py  ← 자동 의존성 스캐너
└── workflows/               ← 워크플로우 JSON 폴더
```

## 📋 요구사항

- Windows 10/11
- NVIDIA GPU (CUDA 지원)
- 인터넷 연결 (첫 설치 시)

## 📄 License

MIT License - 동서대학교 CG 교육용
