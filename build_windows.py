"""Windows-only direct EXE builder and packager (no virtual environment required)."""
from __future__ import annotations
import argparse, hashlib, importlib.metadata, importlib.util, json, os, platform, shutil, struct, subprocess, sys, time, traceback, zipfile
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AUDIT = ROOT / 'Windows_결과'
DIST = ROOT / 'dist' / 'SunriseImage'


def check_source_audit():
    audit = json.loads((ROOT / 'SOURCE_AUDIT.json').read_text(encoding='utf-8'))
    if audit.get('status') != 'PASS':
        raise RuntimeError('Source audit is not PASS')
    for name, digest in audit['sha256'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Source changed after audit: ' + name)
    return audit


def _log_tail(log_path: Path, lines: int = 65) -> str:
    """Bounded read of the failing subprocess output, including malformed Windows bytes."""
    with log_path.open('r', encoding='utf-8', errors='replace') as stream:
        return ''.join(deque(stream, maxlen=lines)).rstrip()


def _failure_hint(log_name: str, details: str) -> str:
    """A possible fix, never a claim that the root cause was proven."""
    if log_name != '02_pyinstaller.log':
        return '실제 오류는 해당 단계 로그의 마지막 ERROR/Traceback을 확인하세요.'
    lower = details.lower()
    if 'multiple qt bindings' in lower or 'more than one qt' in lower:
        return 'Qt 바인딩 중복 수집 오류입니다. PySide6만 패키징하도록 제외 옵션을 적용했습니다.'
    if 'permissionerror' in lower or 'winerror 5' in lower or 'winerror 32' in lower:
        return '파일 사용 중/접근 거부 가능성: 실행 중인 SunriseImage.exe 종료, 백신 격리와 폴더 권한 확인.'
    if 'no module named pyinstaller' in lower:
        return '현재 Python의 PyInstaller 설치 확인: python -m pip show pyinstaller.'
    if 'module not found' in lower or 'modulenotfounderror' in lower or 'importerror' in lower:
        return '모듈 누락 또는 호환성 문제 가능성: 로그의 모듈명과 requirements 버전을 확인.'
    if 'file not found' in lower or 'not found' in lower:
        return '경로 또는 수집 파일을 찾지 못했을 수 있습니다. 로그에 표시된 파일 경로를 확인.'
    return '로그 마지막 부분의 원래 예외 메시지를 확인하세요. Windows_결과/WINDOWS_BUILD_RESULT.json에도 기록됩니다.'


def command(args, log_name):
    log_path = AUDIT / log_name
    # Do not hide the child process failure behind a generic return-code message.
    with log_path.open('w', encoding='utf-8') as log:
        result = subprocess.run(args, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        tail = _log_tail(log_path)
        hint = _failure_hint(log_name, tail)
        print(f'\n[FAILED] {log_name} (exit {result.returncode})', file=sys.stderr, flush=True)
        print(f'[원인 확인] {log_path}', file=sys.stderr, flush=True)
        if tail:
            print('----- 실제 하위 프로세스 오류 (마지막 65줄) -----', file=sys.stderr, flush=True)
            print(tail, file=sys.stderr, flush=True)
            print('----- 오류 출력 끝 -----', file=sys.stderr, flush=True)
        print(f'[진단 안내] {hint}', file=sys.stderr, flush=True)
        raise RuntimeError(f'{log_name}: command failed ({result.returncode}); '
                           f'log={log_path}; hint={hint}')


def _dependencies_ready() -> bool:
    requirements = (ROOT / 'requirements.txt').read_text().splitlines() + (ROOT / 'requirements-build.txt').read_text().splitlines()
    for entry in requirements:
        entry = entry.strip()
        if not entry or entry.startswith('#'):
            continue
        name, expected = entry.split('==', 1)
        try:
            if importlib.metadata.version(name) != expected:
                return False
        except importlib.metadata.PackageNotFoundError:
            return False
    return True



def collect_licenses(destination):
    destination.mkdir(parents=True, exist_ok=True)
    packages = ['Pillow', 'PySide6-Essentials', 'shiboken6', 'PyMuPDF', 'defusedxml']
    for name in packages:
        try:
            dist = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            if name == 'PySide6-Essentials':
                dist = importlib.metadata.distribution('PySide6')
            else:
                raise
        target = destination / name
        target.mkdir(exist_ok=True)
        metadata = dist.read_text('METADATA')
        if metadata is None:
            metadata = dist.read_text('PKG-INFO')
        if metadata is None:
            raise RuntimeError('Installed package metadata is missing: ' + name)
        (target / 'PACKAGE_METADATA.txt').write_text(metadata, encoding='utf-8')
        for file in dist.files or []:
            if any(part.lower() in {'licenses', 'license', 'copying'} or part.lower().startswith(('license.', 'copying.')) for part in file.parts):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    safe = target / Path(str(file).replace('..', '_')).name
                    shutil.copyfile(source, safe)
    shutil.copyfile(ROOT / 'THIRD_PARTY_NOTICES.md', destination / 'THIRD_PARTY_NOTICES.md')


def main(package_only=False):
    AUDIT.mkdir(exist_ok=True)
    summary = {
        'status': 'FAILED',
        'platform': platform.system(),
        'architecture': platform.machine(),
        'mode': 'package_existing_executable' if package_only else 'build_and_package',
        'stages': {},
    }
    stage = 'platform'
    try:
        if platform.system() != 'Windows':
            raise RuntimeError('Windows EXE must be built on Windows. No Windows artifact was generated.')
        if sys.version_info[:2] < (3, 10) or struct.calcsize('P') != 8:
            raise RuntimeError('Use 64-bit Python 3.10+ for the release build.')
        stage = 'source_audit'
        source = check_source_audit()
        summary['stages']['source_audit'] = 'PASS reused (hashes match; full tests are not rerun)'
        if package_only:
            if not (DIST / 'SunriseImage.exe').is_file():
                raise RuntimeError('Existing dist/SunriseImage/SunriseImage.exe is missing. Run EXE_빌드.bat first.')
            summary['stages']['dependencies'] = 'SKIPPED (reuse installed environment)'
            summary['stages']['build'] = 'REUSED existing EXE; no compilation'
            summary['existing_exe_matches_current_app_sources'] = 'NOT VERIFIED (packaging-only mode does not update application code)'
        else:
            stage = 'dependencies'
            if _dependencies_ready():
                print('1/3: Build dependencies already installed in Python environment (versions match; skipping pip install)...', flush=True)
                (AUDIT / '01_dependencies.log').write_text('All required packages already installed in system Python.\n', encoding='utf-8')
                summary['stages']['dependencies'] = 'PASS (reused system Python packages)'
            else:
                print('1/3: Installing missing build dependencies into current Python...', flush=True)
                command([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt', '-r', 'requirements-build.txt'], '01_dependencies.log')
                summary['stages']['dependencies'] = 'PASS'
            args = [
                sys.executable, '-m', 'PyInstaller', '--noconfirm', '--windowed', '--onedir', '--noupx',
                '--name', 'SunriseImage',
                '--icon', 'assets/sunrise_image.ico',
                '--add-data', 'assets:assets',
                # Sunrise Image uses PySide6 only. Other Qt bindings installed in a
                # shared Python environment must not trigger incompatible hooks.
                '--exclude-module', 'PyQt5',
                '--exclude-module', 'PyQt6',
                '--exclude-module', 'PySide2',
                '--collect-all', 'pymupdf',
                '--copy-metadata', 'PyMuPDF',
                '--copy-metadata', 'defusedxml',
                '--add-data', 'THIRD_PARTY_NOTICES.md:.',
                'app_entry.py',
            ]
            stage = 'build'
            print('2/3: Building Windows EXE (dist/SunriseImage/SunriseImage.exe)...', flush=True)
            command(args, '02_pyinstaller.log')
            summary['stages']['build'] = 'PASS'
        exe = DIST / 'SunriseImage.exe'
        executable_hash = hashlib.sha256(exe.read_bytes()).hexdigest()
        stage = 'windows_runtime'
        report = AUDIT / 'WINDOWS_RUNTIME_CHECK.json'
        if report.exists():
            report.unlink()
        print('1/2: Checking existing Windows executable...' if package_only else '3/3: Checking frozen Windows runtime...', flush=True)
        command([str(exe), '--smoke-test', '--report', str(report)], '03_runtime.log')
        checked = json.loads(report.read_text(encoding='utf-8'))
        if checked.get('status') != 'PASS' or not checked.get('windows_verified') or not checked.get('frozen') or checked.get('program') != 'Sunrise Image':
            raise RuntimeError('Frozen Windows runtime did not pass.')
        if hashlib.sha256(exe.read_bytes()).hexdigest() != executable_hash:
            raise RuntimeError('Executable changed during runtime check.')
        summary['stages']['windows_runtime'] = 'PASS'
        if package_only:
            print('2/2: Finalizing licenses and release ZIP...', flush=True)
        stage = 'licenses'
        collect_licenses(DIST / 'licenses')
        summary['stages']['licenses'] = 'PASS'
        stage = 'documentation'
        for name in ['사용방법.md', 'Windows_배포안내.md', '성능개선.md']:
            shutil.copyfile(ROOT / name, DIST / name)
        summary['stages']['documentation'] = 'PASS'
        stage = 'archive'
        release = ROOT / 'release'
        release.mkdir(exist_ok=True)
        archive = release / 'Sunrise_Image_WINDOWS_x64.zip'
        temporary = archive.with_suffix('.zip.tmp')
        try:
            with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as z:
                for file in sorted(DIST.rglob('*')):
                    if file.is_file():
                        z.write(file, str(file.relative_to(DIST.parent)))
            temporary.replace(archive)
        finally:
            temporary.unlink(missing_ok=True)
        summary['stages']['archive'] = 'PASS'
        summary.update(
            status='PASS',
            release=str(archive),
            release_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
            executable_sha256=executable_hash,
            source_audit=source['validation'],
        )
        print('PASS: ' + str(archive))
    except Exception:
        summary['failed_stage'] = stage
        summary['error'] = traceback.format_exc()
        log_names = {'dependencies': '01_dependencies.log', 'build': '02_pyinstaller.log',
                     'windows_runtime': '03_runtime.log'}
        if stage in log_names:
            log_path = AUDIT / log_names[stage]
            if log_path.is_file():
                summary['failed_log'] = str(log_path)
                summary['failed_log_tail'] = _log_tail(log_path)
                summary['diagnostic_hint'] = _failure_hint(log_names[stage], summary['failed_log_tail'])
        print(summary['error'])
    finally:
        (AUDIT / 'WINDOWS_BUILD_RESULT.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if summary['status'] == 'PASS' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--package-only', action='store_true', help='Package an existing EXE after a fresh runtime check, without reinstalling or compiling.')
    sys.exit(main(parser.parse_args().package_only))
