"""Windows-only direct EXE builder and packager (no virtual environment required)."""
from __future__ import annotations
import argparse, hashlib, importlib.metadata, importlib.util, json, os, platform, shutil, struct, subprocess, sys, time, traceback, uuid, zipfile
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
        if 'mpl-data' in lower or 'matplotlib' in lower:
            return ('Matplotlib 리소스 복사 중 접근 거부: 불필요한 Matplotlib 수집을 제외하고 '
                    '격리된 임시 폴더에 빌드하도록 수정했습니다. 기존 dist 파일 점유 여부도 확인하세요.')
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



def promote_verified_directory(staged: Path, destination: Path, audit_dir: Path):
    """Move a fully checked onedir build into place; restore the previous version on failure."""
    if not staged.is_dir() or not (staged / 'SunriseImage.exe').is_file():
        raise RuntimeError(f'Verified staged EXE directory missing: {staged}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if destination.exists():
        backup = audit_dir / ('previous_dist_' + uuid.uuid4().hex)
        try:
            destination.rename(backup)  # Fails safely if a file is locked.
        except PermissionError as exc:
            raise RuntimeError(
                '기존 배포 폴더의 사용 권한 또는 파일 점유 때문에 교체할 수 없습니다. '
                'SunriseImage.exe 및 해당 폴더를 사용하는 창을 닫고 다시 실행하세요. '
                f'기존 결과는 유지됩니다: {destination}'
            ) from exc
    try:
        staged.rename(destination)  # Rename in the same filesystem where possible.
    except Exception:
        if backup is not None and backup.exists() and not destination.exists():
            backup.rename(destination)
        raise
    if backup is not None:
        try:
            shutil.rmtree(backup)
        except OSError as exc:
            print(f'[WARN] 이전 배포본 백업 삭제 실패 (수동 확인 필요): {backup} ({exc})', flush=True)


def _pyside6_distribution_conflicts():
    """Warn about orphaned old metapackages without uninstalling other apps' dependencies."""
    expected = importlib.metadata.version('PySide6-Essentials')
    conflicts = []
    for name in ('PySide6', 'PySide6-Addons'):
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        if actual != expected:
            conflicts.append(f'{name} {actual} (PySide6-Essentials {expected})')
    return conflicts


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
    staged_root = None
    built_dist = DIST
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
            try:
                conflicts = _pyside6_distribution_conflicts()
            except importlib.metadata.PackageNotFoundError:
                conflicts = []
            if conflicts:
                summary['dependency_warnings'] = conflicts
                print('[WARN] 전체 Python 환경에 구버전 PySide6 메타패키지가 남아 있습니다:',
                      '; '.join(conflicts), flush=True)
                print('[WARN] 다른 프로젝트의 패키지를 자동으로 삭제하지 않습니다. '
                      '해당 환경을 확인해 주세요.', flush=True)
            # Never COLLECT into the existing release folder: it might be in use,
            # read-only, or hold a partially collected file from a prior failed build.
            staged_root = AUDIT / 'build_staging' / uuid.uuid4().hex
            staged_root.mkdir(parents=True, exist_ok=False)
            built_dist = staged_root / 'SunriseImage'
            args = [
                sys.executable, '-m', 'PyInstaller', '--noconfirm', '--windowed', '--onedir', '--noupx',
                '--distpath', str(staged_root),
                '--name', 'SunriseImage',
                '--icon', 'assets/sunrise_image.ico',
                '--add-data', 'assets:assets',
                # Sunrise Image uses PySide6 only. Other Qt bindings installed in a
                # shared Python environment must not trigger incompatible hooks.
                '--exclude-module', 'PyQt5',
                '--exclude-module', 'PyQt6',
                '--exclude-module', 'PySide2',
                # PyMuPDF's broad --collect-all pulls optional CLI/tests and their
                # matplotlib, pandas and pytest dependencies into the EXE.
                # Only native extensions are required in addition to imports
                # found by normal module analysis; smoke test verifies PDF use.
                '--collect-binaries', 'pymupdf',
                '--exclude-module', 'matplotlib',
                '--exclude-module', 'pandas',
                '--exclude-module', 'pytest',
                '--copy-metadata', 'PyMuPDF',
                '--copy-metadata', 'defusedxml',
                '--add-data', 'THIRD_PARTY_NOTICES.md:.',
                'app_entry.py',
            ]
            stage = 'build'
            print('2/3: Building Windows EXE (dist/SunriseImage/SunriseImage.exe)...', flush=True)
            command(args, '02_pyinstaller.log')
            summary['stages']['build'] = 'PASS'
        exe = built_dist / 'SunriseImage.exe'
        if not exe.is_file():
            raise RuntimeError(f'PyInstaller returned success but EXE is missing: {exe}')
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
        collect_licenses(built_dist / 'licenses')
        summary['stages']['licenses'] = 'PASS'
        stage = 'documentation'
        for name in ['사용방법.md', 'Windows_배포안내.md', '성능개선.md']:
            shutil.copyfile(ROOT / name, built_dist / name)
        summary['stages']['documentation'] = 'PASS'
        stage = 'archive'
        release = ROOT / 'release'
        release.mkdir(exist_ok=True)
        archive = release / 'Sunrise_Image_WINDOWS_x64.zip'
        temporary = archive.with_suffix('.zip.tmp')
        try:
            with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as z:
                for file in sorted(built_dist.rglob('*')):
                    if file.is_file():
                        z.write(file, str(file.relative_to(built_dist.parent)))
            # The archive is complete. Only now touch the prior distribution.
            if not package_only:
                stage = 'promote'
                promote_verified_directory(built_dist, DIST, AUDIT)
                summary['stages']['promote'] = 'PASS (previous dist replaced after runtime verification)'
            stage = 'archive'
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
        if staged_root is not None and staged_root.is_dir():
            summary['staging_path_if_available'] = str(staged_root)
        if stage == 'promote':
            summary['diagnostic_hint'] = ('기존 dist 배포 폴더의 파일 점유 또는 접근 권한 확인. '
                                          '빌드 및 동결 실행 단계가 PASS라면 전체 재컴파일이 아닌 '
                                          '출력 폴더 교체만 실패한 상태입니다.')
        print(summary['error'])
    finally:
        if staged_root is not None and staged_root.exists() and summary['status'] == 'PASS':
            try:
                shutil.rmtree(staged_root)
            except OSError as exc:
                print(f'[WARN] 임시 빌드 디렉터리 정리 실패: {exc}', flush=True)
        (AUDIT / 'WINDOWS_BUILD_RESULT.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if summary['status'] == 'PASS' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--package-only', action='store_true', help='Package an existing EXE after a fresh runtime check, without reinstalling or compiling.')
    sys.exit(main(parser.parse_args().package_only))
