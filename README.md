# Sunrise Image

Sunrise Group의 문서 내 이미지 추출·변환·경량화 프로그램입니다.

## 프로그램 목적

HWPX, PDF 및 Office 문서에 포함된 이미지를 선택해 추출·변환하거나 문서에 포함된 이미지를 최적화하여, 원본을 보존하면서 재사용 가능한 이미지와 경량화 문서 사본을 생성합니다.

## 지원 운영체제

- Windows 10 / Windows 11 (64비트, x64)

## 개발언어 및 주요 기술

- **개발언어:** Python 3.12
- **주요 기술:** PySide6(Qt), Pillow, PyMuPDF, defusedxml
- **배포 형태:** Windows 폴더형 실행 패키지(onedir)

## 주요 기능

- HWPX, DOCX, XLSX, PPTX, PDF 문서의 이미지 확인·추출
- 파일·폴더 일괄 등록과 드래그 앤 드롭
- 이미지 형식·용량 필터 및 개별 항목 선택
- JPG, PNG, WebP, TIFF 등 이미지 형식 변환
- 해상도, DPI, 압축 품질, 목표 용량, 회전 및 파일명 설정
- HWPX 본문 이미지 자르기 정보 반영
- 이미지 미리보기, 원본·결과 비교 및 문서 내 이미지 최적화
- 원본 보존형 문서 경량화 사본 생성과 진행상태·취소 지원

---

Copyright © 2026 Sunrise Group. All rights reserved.

## Sunrise Group 공통 폴더

- 공식 Windows 실행형 배포 ZIP을 압축 해제하면 `Sunrise Group/Sunrise Image/SunriseImage.exe`로 구성됩니다. 사용자가 원하는 부모 폴더에 전체 `Sunrise Group` 폴더를 배치할 수 있습니다.
- 프로그램 진단 파일은 `%LOCALAPPDATA%/Sunrise Group/Sunrise Image/Diagnostics/`에 기록됩니다. 기존 `%LOCALAPPDATA%/SunriseImage/Diagnostics/` 기록은 자동 삭제하지 않습니다.
- 기존 실행파일의 저장 위치나 사용자의 문서·프로젝트 파일을 임의 이동하지 않습니다. 업데이트·설치파일을 이 저장소에 포함하지 않습니다.

## EXE 직접 빌드와 PySide6 충돌 처리

Windows x64 / Python 3.12에서 `EXE_빌드.bat`을 직접 실행합니다. `.venv`는 생성하지 않습니다. 기존 Python에 필요한 의존성이 정확히 설치되어 있으면 재사용하고, PySide6/Qt 버전 충돌이나 의존성 누락 시 `Windows_결과/private_build_packages`에 프로젝트 전용 패키지를 설치하여 시스템/user site-packages와 분리한 채 PyInstaller를 실행합니다. 기존 전역 Python 패키지는 설치·삭제·업그레이드하지 않습니다.

실패 단계는 `Windows_결과/WINDOWS_BUILD_RESULT.json`으로 확인합니다. 의존성 문제는 `01_dependencies.log`, PyInstaller는 `02_pyinstaller.log`, 실행 확인은 `03_runtime.log`, 공식 그룹서명은 `04_signing.log`에 구분해 기록합니다. 본 저장소의 검증은 소스 단위검사이며, Windows 실빌드·서명 완료를 의미하지 않습니다.

### Windows 배치파일 호환성

공식 소스의 `*.bat` 6개는 UTF-8(BOM 없음) + Windows CRLF 줄바꿈을 사용하며, 시작 시 코드페이지 65001을 지정합니다. LF 전용 배치파일과 혼용하지 마세요. `EXE_빌드.bat`은 Python 3.12 x64를 확인하고 오류코드를 반환합니다. 배포 ZIP 교체 실패 시 이전 `dist` 폴더를 복원하도록 소스 파이프라인을 보완했습니다. 실제 Windows `cmd.exe`, PyInstaller, 서명 및 GUI 확인은 별도 검증이 필요합니다.

### 서명 정책 차단 대응 (Windows)

공식 `RELEASE_MIN` 빌드는 서명 전 `00_signing_preflight.log`에서 `CN=Sunrise Group` 인증서(개인키 포함) 및 승인된 `SUNRISE_TIMESTAMP_URL` HTTPS 설정을 확인합니다. 서명 스크립트는 `SOURCE_AUDIT.json` SHA256을 재확인한 다음 **서명 단계의 PowerShell 자식 프로세스에만** `-ExecutionPolicy Bypass`를 적용하여 실행합니다. Windows의 `MachinePolicy`/`UserPolicy` 그룹 정책은 우회하지 않고, 시스템 전체 실행 정책을 변경하지 않습니다. 서명/타임스탬프가 없거나 검증에 실패하면 공식 ZIP은 승격하지 않습니다. Windows 사용자 실빌드에서는 PyInstaller와 startup smoke가 PASS했으나, 공식 Authenticode·타임스탬프는 추가 확인이 필요합니다.
