# 외부 라이브러리 안내

본 패키지는 사용자의 문서 이미지 추출 및 문서 내 이미지 최적화를 위한 파이썬 소스입니다. 배포용 빌드 시 의존 패키지의 라이선스와 고지 파일을 `licenses` 폴더에 포함합니다. (구형 한글 `.hwp`는 지원 대상에서 제외되며 개방형 한글 `.hwpx`, `.pdf`, `.docx`, `.xlsx`, `.pptx`를 지원합니다.)

| 패키지 | 라이선스 / 공식 안내 |
|---|---|
| Pillow | HPND / https://github.com/python-pillow/Pillow/blob/main/LICENSE |
| PySide6 / Qt | LGPLv3·GPLv3·상용 옵션 / https://doc.qt.io/qtforpython-6/licenses.html |
| PyMuPDF / MuPDF | AGPLv3·상용 옵션 / https://pymupdf.readthedocs.io/en/latest/about.html |
| defusedxml | Python Software Foundation / https://github.com/tiran/defusedxml |
| PyInstaller (빌드 도구) | GPL + bootloader 예외 / https://pyinstaller.org/en/stable/license.html |

라이브러리의 상세 권리와 배포 조건은 각 공식 라이선스 및 빌드에 포함되는 원문 고지를 따릅니다. 본 프로그램 소스는 함께 제공되며 Windows EXE 배포 시에도 소스와 빌드 구성을 함께 전달하세요.
