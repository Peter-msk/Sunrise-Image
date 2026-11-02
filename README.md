# Sunrise Image

Sunrise Image는 한글 HWPX, PDF, Word, Excel, PowerPoint 문서에 포함된 이미지를 확인·선별·추출하고, 품질과 크기를 조정해 문서 경량화 사본을 만드는 Sunrise Group의 Windows 업무 도구입니다.

## 주요 기능

- 파일·폴더 추가와 드래그 앤 드롭을 통한 문서 일괄 등록
- 이미지 형식·용량 필터와 개별 체크 선택
- 원본 형식 추출 및 JPG·PNG·WebP·TIFF 등 이미지 변환
- 해상도·DPI·품질·목표 용량·회전·파일명 설정
- HWPX 본문 자르기 영역을 반영한 추출
- 이미지 목록·확대/축소·원본과 결과 비교 미리보기
- 선택한 이미지의 문서 내 변환과 경량화 사본 생성
- 진행률·중지·결과 폴더 확인 및 라이트/다크 테마

## 지원 형식

| 문서 | 이미지 추출 | 문서 경량화 |
|---|---|---|
| HWPX | 지원, 본문 자르기 선택 가능 | 지원 |
| Word DOCX | 지원 | 지원 |
| Excel XLSX | 지원 | 지원 |
| PowerPoint PPTX | 지원 | 지원 |
| PDF | 내장·인라인 이미지 추출 | XObject 이미지 교체 지원, 인라인 이미지 교체 제외 |

구형 바이너리 HWP·DOC·XLS·PPT는 지원하지 않습니다. 해당 문서 작성 프로그램에서 지원되는 최신 형식으로 저장한 뒤 사용하세요. 이 제품은 자동 업데이트와 공지사항 조회 기능을 제공하지 않습니다.

## 실행 조건

| 항목 | 조건 |
|---|---|
| 운영체제 | Windows 10/11 x64 |
| 소스 실행·빌드 | Python 3.12 x64 |
| 주요 라이브러리 | PySide6-Essentials, shiboken6, Pillow, PyMuPDF, defusedxml |
| HWPX 추출 | 한컴 자동화 없이 처리 |
| 배포 형태 | SunriseImage.exe와 종속 파일을 포함하는 폴더형 실행 패키지 |

라이브러리 설치 버전은 `requirements.txt`와 `requirements-build.txt`에 고정되어 있습니다.

## 실행과 사용

완성된 실행 패키지를 받았다면 폴더 전체를 압축 해제하고 `SunriseImage.exe`를 실행합니다. 소스에서 실행하려면 저장소 폴더에서 다음을 실행하세요.

```powershell
python -m pip install -r requirements.txt
python app_entry.py
```

1. **문서 추가** 또는 **폴더 추가**로 문서를 등록합니다.
2. 목록과 미리보기에서 필요한 이미지를 선택합니다.
3. 출력 폴더·저장 형식·해상도·품질·용량 설정을 확인합니다.
4. **선택 이미지 변환 추출** 또는 **선택 이미지 문서 내 변환**을 실행합니다.
5. 결과 폴더의 이미지·경량화 사본과 처리 결과를 확인합니다.

원본문서는 보존하고 결과를 별도 사본으로 생성합니다. 업무에 사용할 사본은 원래 문서 작성 프로그램에서 열어 레이아웃과 인쇄 품질을 확인하세요.

## Windows 실행파일 빌드

Windows x64의 Python 3.12 환경에서 `EXE_빌드.bat`을 실행합니다. 생성 위치는 다음과 같습니다.

`.venv`는 만들지 않습니다. PySide6 등의 버전이 일치하면 시스템 Python 패키지를 재사용하고, 충돌하거나 필수 의존성이 부족하면 `Windows_결과/private_build_packages`에 전용 패키지를 준비하여 `python -S -m PyInstaller`로 시스템 Qt를 제외하고 빌드합니다. 공용 패키지는 변경하지 않습니다. 의존성 설치 실패는 `Windows_결과/01_dependencies.log`, PyInstaller 실패는 `02_pyinstaller.log`에서 확인합니다.

- 실행파일: `dist/SunriseImage/SunriseImage.exe`
- 배포 압축본: `release/Sunrise_Image.zip`

Windows 배치파일 6종은 UTF-8(BOM 없음), CRLF 줄바꿈으로 배포합니다. `EXE_빌드.bat` 실행 시 기존의 `LF`-only 배치 파일을 섞지 마십시오. 빌드 전 소스 감사에서 BOM/CRLF 위반을 차단합니다.

현재 저장소는 최종 소스와 필수 빌드 파일을 제공합니다. 실제 Windows 배포 검증 여부는 빌드 결과로 확인해야 합니다.

## 외부 라이브러리

외부 구성요소의 고지는 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)를 확인하세요. 프로젝트 자체의 별도 사용 허락이 명시되지 않은 상태에서 공개 소스만으로 재배포 권한이 자동 부여되지는 않습니다.

---
Copyright © 2026 Sunrise Group. All rights reserved.

## 코드서명 자동 생성·재사용 — Sunrise Capture 호환 정책

기본 `EXE_빌드.bat`은 RELEASE_MIN으로 빌드합니다. `SUNRISE_TIMESTAMP_URL` 환경변수나 사전 생성된 인증서가 없어도 진행합니다. Windows 빌드 PC의 CurrentUser\My에서 기존 `CN=Sunrise Group` 코드서명 인증서와 개인키를 재사용하고, 없을 때만 RSA 3072/SHA256, Code Signing EKU, 비내보내기 개인키를 사용해 자체서명 인증서를 생성합니다. 새로 만든 인증서는 이후 빌드에서 재사용합니다.

`capture_signing.py`는 체크포인트 SHA256 확인 후 Windows 기본 certreq/certutil 및 Windows SDK signtool로 실행합니다. PowerShell 서명 cmdlet은 사용하지 않습니다. 개인키/PFX를 최종 ZIP에 넣거나 사용자 PC의 Trusted Root 인증서 저장소를 변경하지 않습니다. 공개 `.cer`만 `Windows_결과`와 배포 폴더 내 `signing/`에 제공합니다. `WINDOWS_SIGNING_RESULT.json`에 서명자, 지문, PE Authenticode 인증서 테이블 확인 결과, 타임스탬프 사용 여부를 기록하고 서명 후 EXE SHA256을 최종 패키지에 반영합니다.

**자체서명 Authenticode는 Windows의 공인 발행자 신뢰나 SmartScreen 평판을 자동 확보하지 않습니다.** 표준 Capture형 내부 서명 배포 후보로 분류하고, 최종 운영 승인/실제 사용자 문서 처리는 별도로 확인합니다. 공인 신뢰가 필요한 외부 배포는 적절한 공인 코드서명 인증서를 사용해야 합니다.

기존 Windows PC에서 PyInstaller 및 frozen startup 검사는 PASS했으나, 이 소스의 신규 인증서 생성/서명/최종 ZIP은 Windows 실제 환경에서 다시 확인해야 합니다.
