# Windows EXE 배포 마무리

현재 패키지에는 수정 소스와 Windows 빌드·실행확인 구성이 있습니다. Linux에서 만든 파일을 Windows EXE로 표시하지 않습니다. 완성된 EXE와 Windows 실행 결과는 Windows PC에서 아래 과정을 수행해야 생성됩니다.

## EXE 생성·실행은 PASS이고 마지막 배포 준비에서 실패한 경우

`WINDOWS_BUILD_RESULT.json`에서 build와 windows_runtime이 PASS이고 라이선스 수집의 `HeaderParseError`로 FAILED가 된 경우, 기존 EXE를 다시 컴파일할 필요가 없습니다. 이 수정은 패키지의 METADATA 원문을 읽어 복사하며 이메일 헤더 형식으로 재직렬화하지 않습니다.

1. 기존 `dist`가 있는 **Sunrise_Image 폴더에 수정 소스 파일을 덮어씁니다.** 압축 안의 Sunrise_Image 폴더가 기존 폴더 안에 한 번 더 중첩되지 않게 하세요.
2. 해당 폴더의 **배포_마무리.bat**을 실행합니다.
3. 기존 EXE의 짧은 실행 확인 후 라이선스·설명서를 넣고 `release/Sunrise_Image_WINDOWS_x64.zip`을 생성합니다.
4. `Windows_결과/WINDOWS_BUILD_RESULT.json`의 최종 status와 licenses·documentation·archive가 PASS인지 확인합니다.

이 경로는 설치와 PyInstaller 컴파일을 생략합니다. 소스의 전체 기능 테스트도 반복하지 않습니다. 기존 배포 폴더의 EXE와 `_internal` 파일을 그대로 포함합니다. 이전 JSON에는 검사한 EXE의 해시가 남지 않았으므로 오래된 PASS를 그대로 확정하지 않고 현재 EXE만 짧게 확인합니다. 새 결과에는 EXE·ZIP 해시를 기록합니다.

배포 마무리는 **기존 EXE를 포장하는 기능**입니다. 새 UI나 이미지 처리 소스 변경을 기존 EXE에 반영하려면 아래의 EXE_빌드.bat으로 빌드해야 합니다. 마무리 모드의 결과 JSON에도 현재 소스와 기존 EXE의 일치 여부는 미검증으로 표시합니다.

실패 단계는 failed_stage에 기록합니다. 라이선스·설명서·압축 단계도 개별 상태로 기록하며, ZIP은 임시 파일을 완성한 뒤 최종 이름으로 교체합니다.

## 한 번 실행하는 과정

1. 64비트 Python 3.12를 설치합니다. 소스 ZIP을 사용자에게 쓰기 권한이 있는 폴더에 풉니다.
2. 가상환경(`.venv`) 생성 과정 없이 바로 **`EXE_빌드.bat`**을 실행합니다. (시스템 Python에 필요한 패키지가 이미 설치되어 있으면 `pip install`도 자동으로 건너뛰고 즉시 `SunriseImage.exe`를 빌드합니다.)
4. 빌드가 PASS이면 `release/Sunrise_Image_WINDOWS_x64.zip`이 생성됩니다.
5. ZIP을 다른 폴더에 풀고 `SunriseImage.exe`를 실행해 실제 문서 선택과 추출을 확인합니다. 배포할 때 폴더 전체를 전달하세요. 실행하는 PC에는 Python·한글·Office 설치가 필요하지 않습니다.

빌드는 PyInstaller onedir 방식입니다. 작업 도중 인터넷 연결이 필요할 수 있지만 배포된 프로그램의 문서 처리는 오프라인입니다. 이번 배포는 서명 없는 휴대용 폴더이며 설치형 Setup.exe는 생성하지 않습니다.

## PASS 재사용

`SOURCE_AUDIT.json`에 기록한 소스 해시가 일치하면 기존 기능 검증 PASS를 재사용하고 전체 단위·통합 테스트를 반복하지 않습니다. 빌드에서는 필요한 라이브러리 설치, EXE 생성, **Windows에서만 확인할 수 있는 동결 런타임 실행**을 수행합니다. 해당 실행이 PASS여야 휴대용 배포 ZIP을 생성합니다.

## 결과 파일

| 파일 | 의미 |
|---|---|
| Windows_결과/WINDOWS_BUILD_RESULT.json | 빌드 단계·결과·배포 ZIP 및 EXE SHA256 |
| Windows_결과/WINDOWS_RUNTIME_CHECK.json | Windows 여부, frozen 여부, Qt·코덱·선택 자르기·PDF 실행 결과 |
| Windows_결과/WINDOWS_RUNTIME_CHECK.png | 테스트 이미지가 표시된 실제 프로그램 화면 |
| Windows_결과/01_dependencies.log | 의존성 설치 로그 |
| Windows_결과/02_pyinstaller.log | EXE 빌드 로그 |
| Windows_결과/03_runtime.log | EXE 실행확인 로그 |

**Windows 실기 마무리 검토에 필요한 파일은 두 JSON입니다.** 실패 시 관련 단계 로그도 함께 확인해야 합니다. 화면 배율이나 실제 문서에서 문제가 보이면 해당 프로그램 화면을 함께 제공하면 위치를 확인할 수 있습니다.

`Windows_실행확인.bat`은 이미 빌드한 EXE를 다시 실행 확인하고 프로그램을 엽니다. 빌드를 반복하지 않으며 평소에는 EXE를 직접 실행하면 됩니다.

## 시작 실패 기록

파이썬/모듈 초기화 오류는 `%LOCALAPPDATA%/SunriseImage/Diagnostics/startup_error.log`에 남기고 오류 창에 경로를 표시합니다. 운영체제 수준에서 로딩이 중단되는 경우에는 빌드·런타임 로그를 함께 확인합니다.

## 의존 패키지 고지

배포 폴더에는 사용설명과 외부 라이브러리의 메타데이터·라이선스 파일을 포함합니다. 상세 안내는 `THIRD_PARTY_NOTICES.md`를 참고하세요. 소스 및 빌드 구성도 배포물과 함께 제공하세요.
