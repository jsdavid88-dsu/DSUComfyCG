# Maya Bridge Guide

**DSUComfyCG** 시스템의 핵심 확장 기능인 `MayaAI_Toolkit`은 Autodesk Maya와 ComfyUI를 실시간으로 연동하여 아티스트가 친숙한 3D 환경에서 AI 기능을 활용할 수 있도록 지원합니다.

## 🌟 개요

Maya의 뷰포트와 로컬 ComfyUI 서버를 연동하여, 3D 씬을 AI 이미지로 실시간 변환하고, 텍스처를 프로젝션하며, 애니메이션을 렌더링하는 통합 워크플로우를 제공합니다.

## ✨ 핵심 기능

### 1. Basic Generation (기초 생성)
- **Viewport Live Link**: Maya 뷰포트를 실시간으로 캡처하여 ComfyUI의 입력으로 전송합니다.
- **ControlNet Auto-Setup**: Depth, Normal, Canny 등 필요한 제어 맵을 Maya Scene 정보에서 자동으로 추출하여 전송합니다.
- **Texture Projection**: 생성된 이미지를 카메라 매핑(Camera Projection)을 통해 다시 3D 모델에 텍스처로 입힙니다.

### 2. Advanced Features (고급 기능)
- **Multi-view Synthesis**: 여러 카메라 각도에서 생성한 이미지를 블렌딩하여 360도 일관성 있는 텍스처를 생성합니다.
- **Timeline Animation**: Maya 타임라인을 순차적으로 처리하여 비디오 스타일 변환(Video Style Transfer)을 수행합니다.
- **Layer Compositor**: 캐릭터와 배경 레이어를 분리하여 생성 후 자동 합성, 아티팩트를 최소화합니다.
- **Dynamic UI**: ComfyUI 워크플로우의 노드 파라미터(예: Denoise 강도)를 Maya UI에서 직접 조절할 수 있습니다 (노드명에 `@parameter` 태그 사용).

## 🚀 설치 및 연결

### 사전 요구사항
- **Autodesk Maya**: 2022 이상 (Windows)
- **DSUComfyCG**: 로컬 서버 실행 (Port 8188)
- **Python 의존성**: `requests` (Maya Script Editor에서 설치 필요)

### 설치 방법
1. `MayaAI_Toolkit` 폴더를 Maya 스크립트 경로에 배치합니다.
   - 경로: `Documents/maya/scripts/MayaAI_Toolkit`
2. Maya Script Editor (Python)에서 실행:
   ```python
   import MayaAI_Toolkit.main_ui as mui
   mui.run_maya_ai()
   ```

## 📋 워크플로우 예시

1. **Scene Setup**: Maya에서 씬 구성 (모델링, 카메라 배치).
2. **Connect**: MayaAI Toolkit 실행 및 ComfyUI 연결 확인.
3. **Control Maps**: Depth/Normal Pass 활성화.
4. **Prompting**: ComfyUI 또는 Maya UI에서 프롬프트 입력.
5. **Generate**: 'Generate' 버튼 클릭으로 이미지 생성 및 뷰포트 오버레이 확인.

---
**Note**: 이 기능은 DSUComfyCG의 Phase 3 계획에 포함된 기능으로, 별도의 Toolkit 설치가 필요할 수 있습니다.
