"""Windows build profiles: BUILD_MIN for development, RELEASE_MIN for signed delivery."""
from __future__ import annotations
import argparse, hashlib, importlib.metadata, importlib.util, json, os, platform, shutil, struct, subprocess, sys, time, traceback, uuid, zipfile
from collections import deque
from pathlib import Path
from product_info import APP_ID, APP_NAME, ENTRY_EXECUTABLE, PACKAGE_KIND

ROOT = Path(__file__).resolve().parent
AUDIT = ROOT / 'Windows_결과'
DIST = ROOT / 'dist' / 'SunriseImage'
DEFAULT_PROFILE = 'RELEASE_MIN'
# Every official Sunrise desktop package extracts below one group folder.
PACKAGE_PREFIX = 'Sunrise Group/Sunrise Image'


def check_source_audit():
    audit = json.loads((ROOT / 'SOURCE_AUDIT.json').read_text(encoding='utf-8'))
    if audit.get('status') != 'PASS':
        raise RuntimeError('Source audit is not PASS')
    if audit.get('schema_version') == 2:
        required = {f.relative_to(ROOT).as_posix() for pattern in ('*.py', '*.ps1', '*.bat', 'requirements*.txt') for f in ROOT.glob(pattern) if f.name != 'render_final_execution_screens.py'}
        required.update(f.relative_to(ROOT).as_posix() for f in (ROOT / 'assets').rglob('*') if f.is_file())
        if required - audit['sha256'].keys():
            raise RuntimeError('Source audit does not cover all build inputs')
    for name, digest in audit['sha256'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Source changed after audit: ' + name)
    # Windows cmd.exe must not parse an LF-only or BOM-corrupted batch script.
    # This is a source gate, not a second full runtime test.
    for script in ROOT.glob('*.bat'):
        contents = script.read_bytes()
        if (contents.startswith((b'\xef\xbb\xbf', b'\xff\xfe', b'\xfe\xff'))
                or b'\x00' in contents or b'\n' not in contents
                or contents.count(b'\r\n') != contents.count(b'\n')
                or contents.count(b'\r\n') != contents.count(b'\r')):
            raise RuntimeError(f'Windows batch encoding/CRLF invalid: {script.name}')
        try:
            contents.decode('utf-8', errors='strict')
        except UnicodeError as exc:
            raise RuntimeError(f'Windows batch UTF-8 invalid: {script.name}') from exc
    return audit


def _log_tail(log_path: Path, lines: int = 65) -> str:
    """Bounded read of the failing subprocess output, including malformed Windows bytes."""
    with log_path.open('r', encoding='utf-8', errors='replace') as stream:
        return ''.join(deque(stream, maxlen=lines)).rstrip()


def _failure_hint(log_name: str, details: str) -> str:
    """A possible fix, never a claim that the root cause was proven."""
    lower = details.lower()
    if log_name in {'00_signing_preflight.log', '04_signing.log'}:
        if ('execution policy' in lower or 'executionpolicy' in lower or 'cannot be loaded' in lower
                or 'not digitally signed' in lower or 'unauthorizedaccess' in lower):
            return ('PowerShell script execution was blocked. The build uses process-only -ExecutionPolicy Bypass '
                    'for its audited signer; MachinePolicy/UserPolicy Group Policy still takes precedence. '
                    'If enterprise policy restricts scripts, contact the policy administrator. '
                    'Do not modify persistent execution policies.')
        if 'certificate' in lower or 'cert:' in lower:
            return 'Windows CurrentUser certificate creation/reuse or signing failed; see 04_signing.log.'
        if 'timestamp' in lower or 'https://' in lower:
            return 'Optional timestamp was configured and failed; check SUNRISE_TIMESTAMP_URL or omit it for Capture-style signing.'
        return 'Inspect signing log; a matching Authenticode signer is required; timestamp is optional for local self-signing.'
    if log_name != '02_pyinstaller.log':
        return '실제 오류는 해당 단계 로그의 마지막 ERROR/Traceback을 확인하세요.'
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


def command(args, log_name, env=None):
    log_path = AUDIT / log_name
    # Do not hide the child process failure behind a generic return-code message.
    with log_path.open('w', encoding='utf-8') as log:
        result = subprocess.run(args, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=False,
                                timeout=1800 if log_name == '02_pyinstaller.log' else 900 if log_name == '01_dependencies.log' else 90,
                                env=env)
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


def check_signing_prerequisites():
    """Capture-style signing: no timestamp URL or pre-installed cert required.

    Windows built-in code signing tools will provision a non-exportable cert only
    if the current user has no usable Sunrise Group code-signing certificate.
    No trust-root, execution policy or other applications are modified.
    """
    test = (
        "$ErrorActionPreference='Stop'; "
        "Get-Command New-SelfSignedCertificate,Set-AuthenticodeSignature,Get-AuthenticodeSignature,Export-Certificate "
        "-ErrorAction Stop | Out-Null; "
        "$null=Get-Item 'Cert:\\CurrentUser\\My' -ErrorAction Stop; "
        "Write-Output 'PASS: Windows Capture-style signing tools ready; certificate may be auto-created.'"
    )
    # PowerShell -Command does not load a .ps1 file; no OS-wide policy edits.
    command(['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive',
             '-Command', test], '00_signing_preflight.log')


def sign_executable(executable: Path):
    """SHA-audited signer, per-process PowerShell only, verified report required."""
    script = ROOT / 'sign_release.ps1'
    audit = json.loads((ROOT / 'SOURCE_AUDIT.json').read_text(encoding='utf-8'))
    pinned = audit.get('sha256', {}).get('sign_release.ps1')
    if not pinned or not script.is_file() or hashlib.sha256(script.read_bytes()).hexdigest() != pinned:
        raise RuntimeError('Signing script missing or SHA256 differs from SOURCE_AUDIT.json; refusing to sign.')
    output = AUDIT / 'WINDOWS_SIGNING_RESULT.json'
    output.unlink(missing_ok=True)
    command(['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive',
             '-ExecutionPolicy', 'Bypass', '-File', str(script),
             '-Executable', str(executable), '-ReportPath', str(output)], '04_signing.log')
    if not output.is_file():
        raise RuntimeError('Signer reported success but did not create WINDOWS_SIGNING_RESULT.json.')
    signed = json.loads(output.read_text(encoding='utf-8-sig'))
    required = ('CAPTURE_STYLE_SELF_SIGNED_AUTHENTICODE', 'CN=Sunrise Group', 'Authenticode')
    if (signed.get('signing_mode') != required[0]
            or signed.get('signer_subject') != required[1]
            or signed.get('signature_type') != required[2]
            or signed.get('windows_signature_status') not in ('Valid','NotTrusted','UnknownError')
            or not signed.get('signer_thumbprint')
            or signed.get('executable_sha256_after_signing') != hashlib.sha256(executable.read_bytes()).hexdigest()):
        raise RuntimeError('Signed executable identity or signature report validation failed.')
    return signed


def _requirements():
    """Only pinned packages are allowed in a reproducible official build."""
    entries = []
    for filename in ('requirements.txt', 'requirements-build.txt'):
        for line in (ROOT / filename).read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            name, separator, expected = line.partition('==')
            if not separator or not name or not expected:
                raise RuntimeError(f'Expected pinned dependency in {filename}: {line}')
            entries.append((name, expected))
    return entries


def _dependencies_ready(search_path=None) -> bool:
    """Check exact versions in system Python, or exclusively inside our private target."""
    if search_path is None:
        for name, expected in _requirements():
            try:
                if importlib.metadata.version(name) != expected:
                    return False
            except importlib.metadata.PackageNotFoundError:
                return False
        return True
    installed = {}
    for dist in importlib.metadata.distributions(path=[str(search_path)]):
        name = (dist.metadata.get('Name') or '').lower().replace('_', '-').replace('.', '-')
        installed[name] = dist.version
    return all(installed.get(name.lower().replace('_', '-').replace('.', '-')) == expected
               for name, expected in _requirements())


def _dependency_fingerprint():
    return hashlib.sha256(b'\0'.join((ROOT / filename).read_bytes()
                                   for filename in ('requirements.txt', 'requirements-build.txt'))).hexdigest()


def prepare_build_dependencies():
    """No .venv and NEVER pip-install into a shared Python environment.

    Use existing exact system requirements when safe. For missing/mismatched requirements
    or an incompatible PySide6 metapackage, install a complete *private* site-packages
    overlay under Windows_결과; no system package is uninstalled or upgraded.
    """
    conflicts = _pyside6_distribution_conflicts()
    if _dependencies_ready() and not conflicts:
        (AUDIT / '01_dependencies.log').write_text(
            'All pinned build dependencies present; system packages unchanged.\n', encoding='utf-8')
        return None, 'PASS (reused exact system dependencies)', []
    if conflicts:
        print('[INFO] System Qt metadata differs: ' + '; '.join(conflicts), flush=True)
        print('[INFO] Using private build packages; system PySide6 is not modified.', flush=True)
    overlay = AUDIT / 'private_build_packages'
    marker = overlay / '_sunrise_dependency_checkpoint.json'
    fingerprint = _dependency_fingerprint()
    if marker.is_file():
        try:
            saved = json.loads(marker.read_text(encoding='utf-8'))
            if saved.get('requirements_sha256') == fingerprint and _dependencies_ready(overlay):
                (AUDIT / '01_dependencies.log').write_text(
                    'Reused pinned private build packages; system packages unchanged.\n', encoding='utf-8')
                return overlay, 'PASS (reused private build packages)', conflicts
        except (OSError, ValueError, KeyError):
            pass
    staged = AUDIT / ('private_packages_staging_' + uuid.uuid4().hex)
    staged.mkdir(parents=True, exist_ok=False)
    try:
        print('1/3: Installing pinned dependencies into private build folder (no venv; no global pip changes)...', flush=True)
        command([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check',
                 '--no-warn-script-location', '--ignore-installed', '--target', str(staged),
                 '-r', 'requirements.txt', '-r', 'requirements-build.txt'], '01_dependencies.log')
        if not _dependencies_ready(staged):
            raise RuntimeError('Private build packages do not match pinned requirements; see 01_dependencies.log')
        (staged / '_sunrise_dependency_checkpoint.json').write_text(
            json.dumps({'requirements_sha256': fingerprint}, indent=2), encoding='utf-8')
        if overlay.exists():
            backup = AUDIT / ('previous_private_packages_' + uuid.uuid4().hex)
            overlay.rename(backup)
            try:
                staged.rename(overlay)
            except Exception:
                backup.rename(overlay)
                raise
            # Old private packages are disposable cache, not end-user data.
            try:
                shutil.rmtree(backup)
            except OSError:
                print('[WARN] Previous private package cache not removed: ' + str(backup), flush=True)
        else:
            staged.rename(overlay)
    finally:
        if staged.exists():
            shutil.rmtree(staged, ignore_errors=True)
    return overlay, 'PASS (created private build packages)', conflicts


def private_python_environment(overlay):
    """Child import path takes priority without changing shared Python packages."""
    env = dict(os.environ)
    env['PYTHONPATH'] = str(overlay)
    env['PYTHONNOUSERSITE'] = '1'
    return env


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
        print(f'[INFO] 이전 빌드 보존: {backup}', flush=True)
    return backup


def restore_promoted_directory(current: Path, staged: Path, backup: Path | None):
    """Restore the old onedir if final archive replacement failed."""
    if staged.exists():
        raise RuntimeError(f'Cannot safely roll back: staged directory already exists: {staged}')
    current.rename(staged)
    if backup is not None:
        try:
            backup.rename(current)
        except Exception:
            # Last resort: put the newly built runnable directory back where it was.
            # Never delete a previous build or leave the installation folder empty.
            if not current.exists() and staged.exists():
                staged.rename(current)
            raise


def _pyside6_distribution_conflicts():
    """Warn about orphaned old metapackages without uninstalling other apps' dependencies."""
    requirement_file = ROOT / 'requirements.txt'
    if requirement_file.is_file():
        expected = next(line.split('==', 1)[1].strip() for line in requirement_file.read_text(encoding='utf-8').splitlines()
                        if line.startswith('PySide6-Essentials=='))
    else:
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


def source_checkpoint(audit):
    return hashlib.sha256(json.dumps(audit['sha256'], sort_keys=True).encode('utf-8')).hexdigest()


def write_executable_info(path):
    # Windows requires fixed numeric resource fields; no product release version is exposed.
    fixed_info = (0, 0, 0, 0)
    properties = {'CompanyName': 'Sunrise Group', 'ProductName': APP_NAME,
                  'FileDescription': 'Sunrise Image document image tools',
                  'InternalName': 'SunriseImage', 'OriginalFilename': ENTRY_EXECUTABLE,
                  'LegalCopyright': 'Copyright © 2026 Sunrise Group. All rights reserved.'}
    strings = ','.join(f'StringStruct({key!r}, {value!r})' for key, value in properties.items())
    path.write_text(f"VSVersionInfo(ffi=FixedFileInfo(filevers={fixed_info!r}, prodvers={fixed_info!r}, mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0,0)), kids=[StringFileInfo([StringTable('040904B0', [{strings}])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])])", encoding='utf-8')


def main(package_only=False, profile=DEFAULT_PROFILE):
    AUDIT.mkdir(exist_ok=True)
    summary = {
        'status': 'FAILED',
        'profile': profile,
        'qualification': 'BUILD_GATE_PENDING',
        'official_release': False,
        'update_notice_integration': 'NOT_APPLICABLE (product has no update or notice feature)',
        'platform': platform.system(),
        'architecture': platform.machine(),
        'mode': 'package_existing_executable' if package_only else 'build_and_package',
        'stages': {},
    }
    stage = 'platform'
    staged_root = None
    overlay = None
    built_dist = DIST
    try:
        if profile not in {'BUILD_MIN', 'RELEASE_MIN'}:
            raise ValueError('Unknown build profile')
        if platform.system() != 'Windows':
            raise RuntimeError('Windows EXE must be built on Windows. No Windows artifact was generated.')
        if sys.version_info[:2] != (3, 12) or struct.calcsize('P') != 8 or platform.machine().lower() not in {'amd64', 'x86_64'}:
            raise RuntimeError('Use the declared 64-bit Python 3.12 build toolchain.')
        stage = 'source_audit'
        source = check_source_audit()
        summary['stages']['source_audit'] = 'REUSED_PASS'
        if profile == 'RELEASE_MIN':
            stage = 'signing_preflight'
            check_signing_prerequisites()
            summary['stages']['signing_preflight'] = 'PASS'
        if package_only:
            if not (DIST / 'SunriseImage.exe').is_file():
                raise RuntimeError('Existing dist/SunriseImage/SunriseImage.exe is missing. Run EXE_빌드.bat first.')
            staged_root = AUDIT / 'package_staging' / uuid.uuid4().hex
            built_dist = staged_root / 'SunriseImage'
            shutil.copytree(DIST, built_dist)
            if profile == 'RELEASE_MIN':
                previous_identity = json.loads((DIST / 'package_info.json').read_text(encoding='utf-8'))
                if (previous_identity.get('source_checkpoint') != source_checkpoint(source)
                        or previous_identity.get('source_binding') != 'built_from_checkpoint'
                        or previous_identity.get('executable_sha256') != hashlib.sha256((DIST / ENTRY_EXECUTABLE).read_bytes()).hexdigest()):
                    raise RuntimeError('Existing EXE source checkpoint does not match; rebuild before official release.')
            summary['stages']['dependencies'] = 'SKIPPED (reuse installed environment)'
            summary['stages']['build'] = 'REUSED existing EXE; no compilation'
            summary['existing_exe_matches_current_app_sources'] = 'NOT VERIFIED (packaging-only mode does not update application code)'
        else:
            stage = 'dependencies'
            overlay, dependency_status, conflicts = prepare_build_dependencies()
            summary['stages']['dependencies'] = dependency_status
            summary['dependency_scope'] = 'private' if overlay is not None else 'system_exact_pins'
            if conflicts:
                summary['dependency_warnings'] = conflicts
            if overlay is not None:
                # collect_licenses reads package metadata in this process. The child
                # PyInstaller process separately gets PYTHONPATH pointing to the overlay.
                sys.path.insert(0, str(overlay))
            # Never COLLECT into the existing release folder: it might be in use,
            # read-only, or hold a partially collected file from a prior failed build.
            staged_root = AUDIT / 'build_staging' / uuid.uuid4().hex
            staged_root.mkdir(parents=True, exist_ok=False)
            built_dist = staged_root / 'SunriseImage'
            version_file = staged_root / 'version_info.txt'
            write_executable_info(version_file)
            args = [
                sys.executable, '-m', 'PyInstaller', '--noconfirm', '--windowed', '--onedir', '--noupx', '--clean',
                '--workpath', str(staged_root / 'work'),
                '--specpath', str(staged_root),
                '--version-file', str(version_file),
                '--distpath', str(staged_root),
                '--name', 'SunriseImage',
                '--icon', str(ROOT / 'assets' / 'sunrise_image.ico'),
                '--add-data', str(ROOT / 'assets') + os.pathsep + 'assets',
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
                '--add-data', str(ROOT / 'THIRD_PARTY_NOTICES.md') + os.pathsep + '.',
                str(ROOT / 'app_entry.py'),
            ]
            stage = 'build'
            print('2/3: Building Windows EXE (dist/SunriseImage/SunriseImage.exe)...', flush=True)
            if overlay is not None:
                # -S prevents system/user site-packages (including stale Qt bindings)
                # from leaking into this private PyInstaller build process.
                isolated_args = [args[0], '-S', *args[1:]]
                isolated_args.extend(['--paths', str(overlay)])
                command(isolated_args, '02_pyinstaller.log', env=private_python_environment(overlay))
            else:
                command(args, '02_pyinstaller.log')
            summary['stages']['build'] = 'PASS'
        exe = built_dist / 'SunriseImage.exe'
        if not exe.is_file():
            raise RuntimeError(f'PyInstaller returned success but EXE is missing: {exe}')
        stage = 'package_identity'
        identity = {'app_id': APP_ID,
                    'package_kind': PACKAGE_KIND, 'entry_executable': ENTRY_EXECUTABLE,
                    'source_checkpoint': source_checkpoint(source),
                    'source_binding': 'unverified_existing_exe' if package_only and profile == 'BUILD_MIN' else 'built_from_checkpoint'}
        (built_dist / 'package_info.json').write_text(json.dumps(identity, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['stages']['package_identity'] = 'PASS'
        executable_hash = hashlib.sha256(exe.read_bytes()).hexdigest()
        stage = 'windows_runtime'
        report = AUDIT / 'WINDOWS_RUNTIME_CHECK.json'
        if report.exists():
            report.unlink()
        print('1/2: Checking existing Windows executable...' if package_only else '3/3: Checking frozen Windows runtime...', flush=True)
        command([str(exe), '--startup-smoke', '--report', str(report)], '03_runtime.log')
        checked = json.loads(report.read_text(encoding='utf-8'))
        if checked.get('status') != 'PASS' or not checked.get('windows_verified') or not checked.get('frozen') or checked.get('program') != APP_NAME or checked.get('app_id') != APP_ID or checked.get('package_kind') != PACKAGE_KIND:
            raise RuntimeError('Frozen Windows runtime did not pass.')
        if hashlib.sha256(exe.read_bytes()).hexdigest() != executable_hash:
            raise RuntimeError('Executable changed during runtime check.')
        summary['stages']['windows_runtime'] = 'PASS'
        if package_only:
            print('2/2: Finalizing licenses and release ZIP...', flush=True)
        stage = 'licenses'
        collect_licenses(built_dist / 'licenses')
        summary['stages']['licenses'] = 'PASS'
        stage = 'signing'
        if profile == 'RELEASE_MIN':
            signing = sign_executable(exe)
            executable_hash = hashlib.sha256(exe.read_bytes()).hexdigest()
            summary['stages']['signing'] = 'PASS (self-signed Authenticode)'
            summary['signing_mode'] = signing['signing_mode']
            summary['signing_thumbprint'] = signing['signer_thumbprint']
            summary['signing_windows_trust'] = signing['windows_signature_status']
            summary['signing_timestamped'] = signing['timestamped']
            identity['signing_mode'] = signing['signing_mode']
            identity['signer_thumbprint'] = signing['signer_thumbprint']
            identity['timestamped'] = signing['timestamped']
            # Like Capture, export only the public .cer; never a private key or PFX.
            public_cert = AUDIT / 'SunriseGroup_SelfSigned_CodeSigning.cer'
            if public_cert.is_file():
                (built_dist / 'signing').mkdir(exist_ok=True)
                shutil.copy2(public_cert, built_dist / 'signing' / public_cert.name)
        else:
            summary['stages']['signing'] = 'PENDING (development build)'
        identity['executable_sha256'] = executable_hash
        (built_dist / 'package_info.json').write_text(json.dumps(identity, ensure_ascii=False, indent=2), encoding='utf-8')
        stage = 'archive'
        release = ROOT / 'release'
        release.mkdir(exist_ok=True)
        archive = release / ('Sunrise_Image.zip' if profile == 'RELEASE_MIN' else 'Sunrise_Image_DEV.zip')
        if archive.exists():
            preserved = release / 'preserved' / (uuid.uuid4().hex + '_' + archive.name)
            preserved.parent.mkdir(exist_ok=True)
            shutil.copy2(archive, preserved)
        temporary = archive.with_suffix('.zip.tmp')
        promoted = False
        previous_dist = None
        try:
            with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as z:
                for file in sorted(built_dist.rglob('*')):
                    if file.is_file():
                        z.write(file, PACKAGE_PREFIX + '/' + file.relative_to(built_dist).as_posix())
            with zipfile.ZipFile(temporary) as verified:
                if verified.testzip() is not None:
                    raise RuntimeError('Release ZIP CRC failed')
                package = json.loads(verified.read(PACKAGE_PREFIX + '/package_info.json'))
                if package != identity or PACKAGE_PREFIX + '/' + ENTRY_EXECUTABLE not in verified.namelist():
                    raise RuntimeError('Release package identity mismatch')
            # Compute the archive checksum before touching any published files.
            archive_digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
            if built_dist != DIST:
                stage = 'promote'
                previous_dist = promote_verified_directory(built_dist, DIST, AUDIT)
                promoted = True
                summary['stages']['promote'] = 'PASS (previous dist replaced after runtime verification)'
            stage = 'archive'
            try:
                temporary.replace(archive)
            except Exception:
                if promoted:
                    try:
                        restore_promoted_directory(DIST, built_dist, previous_dist)
                        summary['stages']['promote'] = 'ROLLED_BACK (archive promotion failed)'
                    except Exception:
                        summary['stages']['promote'] = 'ROLLBACK_FAILED (see traceback)'
                        raise
                raise
        finally:
            temporary.unlink(missing_ok=True)
        summary['stages']['archive'] = 'PASS'
        summary.update(
            status='PASS',
            qualification=('SELF_SIGNED_PACKAGE_VALIDATED_NOT_PUBLICLY_TRUSTED' if profile == 'RELEASE_MIN'
                           else 'DEVELOPMENT_PACKAGE_VALIDATED') if not package_only else 'PACKAGE_VALIDATED_SOURCE_BINDING_LIMITED',
            official_release=False,
            signed_release_candidate=profile == 'RELEASE_MIN',
            certificate_trust='SELF_SIGNED_NOT_PUBLICLY_TRUSTED' if profile == 'RELEASE_MIN' else 'UNSIGNED',
            windows_visual_validation='PENDING',
            update_notice_integration='NOT_APPLICABLE (product has no update or notice feature)',
            release=str(archive),
            release_sha256=archive_digest,
            executable_sha256=executable_hash,
            source_audit=source['validation'],
        )
        print('PASS: ' + str(archive))
    except Exception:
        summary['failed_stage'] = stage
        summary['error'] = traceback.format_exc()
        log_names = {'signing_preflight': '00_signing_preflight.log',
                     'dependencies': '01_dependencies.log', 'build': '02_pyinstaller.log',
                     'windows_runtime': '03_runtime.log', 'signing': '04_signing.log'}
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
        if overlay is not None and str(overlay) in sys.path:
            sys.path.remove(str(overlay))
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
    parser.add_argument('--profile', choices=['BUILD_MIN', 'RELEASE_MIN'], default=DEFAULT_PROFILE)
    args = parser.parse_args()
    sys.exit(main(args.package_only, args.profile))
