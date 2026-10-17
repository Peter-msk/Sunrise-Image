"""Windows-only direct EXE builder and packager (no virtual environment required)."""
from __future__ import annotations
import argparse, hashlib, importlib.metadata, importlib.util, json, os, platform, shutil, struct, subprocess, sys, time, traceback, zipfile
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


def command(args, log_name):
    with (AUDIT / log_name).open('w', encoding='utf-8') as log:
        result = subprocess.run(args, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise RuntimeError(f'{log_name}: command failed ({result.returncode})')


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
        print(summary['error'])
    finally:
        (AUDIT / 'WINDOWS_BUILD_RESULT.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if summary['status'] == 'PASS' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--package-only', action='store_true', help='Package an existing EXE after a fresh runtime check, without reinstalling or compiling.')
    sys.exit(main(parser.parse_args().package_only))
