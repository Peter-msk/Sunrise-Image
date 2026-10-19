import hashlib,json,tempfile,unittest,zipfile,subprocess
from email.errors import HeaderParseError
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import build_windows

class BuildTests(unittest.TestCase):
    def test_raw_multiline_metadata_is_copied_without_email_serialization(self):
        raw='Metadata-Version: 2.4\nName: Pillow\nDescription: <p>\n# README\nSource: example\n'
        class Distribution:
            files=[]
            @property
            def metadata(self):raise HeaderParseError('embedded header')
            def read_text(self,name):return raw if name=='METADATA' else None
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'THIRD_PARTY_NOTICES.md').write_text('notices')
            with patch.object(build_windows,'ROOT',root),patch.object(build_windows.importlib.metadata,'distribution',return_value=Distribution()):
                build_windows.collect_licenses(root/'licenses')
            self.assertEqual((root/'licenses/Pillow/PACKAGE_METADATA.txt').read_text(),raw)
            self.assertTrue((root/'licenses/THIRD_PARTY_NOTICES.md').is_file())

    def test_pkg_info_fallback_and_missing_metadata_failure(self):
        class Distribution:
            files=[]
            def read_text(self,name):return 'Name: test\n' if name=='PKG-INFO' else None
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'THIRD_PARTY_NOTICES.md').write_text('notices');dist=Distribution()
            with patch.object(build_windows,'ROOT',root),patch.object(build_windows.importlib.metadata,'distribution',return_value=dist):
                build_windows.collect_licenses(root/'licenses')
                with patch.object(dist,'read_text',return_value=None):
                    with self.assertRaisesRegex(RuntimeError,'metadata is missing'):build_windows.collect_licenses(root/'missing')

    def _existing_exe(self,root):
        audit=root/'audit';audit.mkdir();dist=root/'dist/SunriseImage';dist.mkdir(parents=True)
        (dist/'SunriseImage.exe').write_bytes(b'existing-exe');(dist/'_internal').mkdir();(dist/'_internal/library.bin').write_bytes(b'library')
        for name in ['사용방법.md','Windows_배포안내.md','성능개선.md']:(root/name).write_text('help',encoding='utf-8')
        (root/'SOURCE_AUDIT.json').write_text(json.dumps({'status':'PASS','sha256':{},'validation':{}}))
        (audit/'WINDOWS_RUNTIME_CHECK.json').write_text(json.dumps({'status':'PASS','windows_verified':True,'frozen':True,'program':'Sunrise Image'}))
        return audit,dist

    def test_package_existing_exe_skips_install_and_build_and_keeps_internal_files(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);audit,dist=self._existing_exe(root);calls=[]
            def command(args,log):
                calls.append(args);self.assertFalse((audit/'WINDOWS_RUNTIME_CHECK.json').exists())
                (audit/'WINDOWS_RUNTIME_CHECK.json').write_text(json.dumps({'status':'PASS','windows_verified':True,'frozen':True,'program':'Sunrise Image'}))
            def licenses(dest):dest.mkdir();(dest/'LICENSE.txt').write_text('license')
            with patch.object(build_windows,'ROOT',root),patch.object(build_windows,'AUDIT',audit),patch.object(build_windows,'DIST',dist),patch.object(build_windows.platform,'system',return_value='Windows'),patch.object(build_windows.sys,'version_info',(3,12,0)),patch.object(build_windows,'command',command),patch.object(build_windows,'collect_licenses',licenses),patch('builtins.print'):
                self.assertEqual(build_windows.main(package_only=True),0)
            self.assertEqual(len(calls),1);self.assertIn('--smoke-test',calls[0]);self.assertEqual((dist/'SunriseImage.exe').read_bytes(),b'existing-exe')
            result=json.loads((audit/'WINDOWS_BUILD_RESULT.json').read_text());self.assertEqual(result['stages']['licenses'],'PASS');self.assertEqual(result['stages']['archive'],'PASS')
            with zipfile.ZipFile(result['release']) as z:
                self.assertEqual(z.read('SunriseImage/_internal/library.bin'),b'library')
                self.assertIn('SunriseImage/licenses/LICENSE.txt',z.namelist())

    def test_existing_runtime_failure_never_reuses_old_pass_or_creates_new_archive(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);audit,dist=self._existing_exe(root)
            def command(args,log):raise RuntimeError('runtime failed')
            with patch.object(build_windows,'ROOT',root),patch.object(build_windows,'AUDIT',audit),patch.object(build_windows,'DIST',dist),patch.object(build_windows.platform,'system',return_value='Windows'),patch.object(build_windows.sys,'version_info',(3,12,0)),patch.object(build_windows,'command',command),patch('builtins.print'):
                self.assertEqual(build_windows.main(package_only=True),1)
            result=json.loads((audit/'WINDOWS_BUILD_RESULT.json').read_text());self.assertEqual(result['failed_stage'],'windows_runtime')
            self.assertFalse((root/'release').exists());self.assertFalse((audit/'WINDOWS_RUNTIME_CHECK.json').exists())

    def test_source_audit_reuse_and_change_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'sample.py').write_text('original')
            (root/'SOURCE_AUDIT.json').write_text(json.dumps({'status':'PASS','validation':{},'sha256':{'sample.py':hashlib.sha256(b'original').hexdigest()}}))
            with patch.object(build_windows,'ROOT',root):
                self.assertEqual(build_windows.check_source_audit()['status'],'PASS')
                (root/'sample.py').write_text('changed')
                with self.assertRaisesRegex(RuntimeError,'changed'):build_windows.check_source_audit()

    def test_direct_build_without_venv_skips_pip_when_dependencies_ready(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);audit,dist=self._existing_exe(root);calls=[]
            def command(args,log):
                calls.append((args,log))
                if log=='02_pyinstaller.log':
                    built=Path(args[args.index('--distpath')+1])/'SunriseImage'
                    built.mkdir(parents=True)
                    (built/'SunriseImage.exe').write_bytes(b'new-exe')
                    (built/'_internal').mkdir()
                    (built/'_internal/library.bin').write_bytes(b'fresh-lib')
                if log=='03_runtime.log':
                    self.assertEqual(Path(args[0]).read_bytes(),b'new-exe')
                    (audit/'WINDOWS_RUNTIME_CHECK.json').write_text(json.dumps({'status':'PASS','windows_verified':True,'frozen':True,'program':'Sunrise Image'}))
            def licenses(dest):dest.mkdir(exist_ok=True);(dest/'LICENSE.txt').write_text('license')
            with patch.object(build_windows,'ROOT',root),patch.object(build_windows,'AUDIT',audit),patch.object(build_windows,'DIST',dist),patch.object(build_windows.platform,'system',return_value='Windows'),patch.object(build_windows.sys,'version_info',(3,12,0)),patch.object(build_windows,'_dependencies_ready',return_value=True),patch.object(build_windows,'command',command),patch.object(build_windows,'collect_licenses',licenses),patch('builtins.print'):
                self.assertEqual(build_windows.main(package_only=False),0)
            # Verify pip install was skipped and PyInstaller was invoked directly
            logs=[log for _,log in calls]
            self.assertNotIn('01_dependencies.log',logs)
            self.assertIn('02_pyinstaller.log',logs)
            self.assertIn('03_runtime.log',logs)
            build_args=next(args for args,log in calls if log=='02_pyinstaller.log')
            self.assertNotIn('--collect-all',build_args)
            self.assertIn('--collect-binaries',build_args)
            self.assertIn('pymupdf',build_args)
            self.assertIn('--distpath',build_args)
            for excluded in ('matplotlib','pandas','pytest'):
                self.assertIn(excluded,build_args)
            for qt in ('PyQt5','PyQt6','PySide2'):
                self.assertIn(qt,build_args)
            self.assertNotIn('--clean',build_args)  # No duplicate clean rebuild by default.
            self.assertEqual((dist/'SunriseImage.exe').read_bytes(),b'new-exe')
            self.assertEqual((dist/'_internal/library.bin').read_bytes(),b'fresh-lib')
            with zipfile.ZipFile(root/'release/Sunrise_Image_WINDOWS_x64.zip') as z:
                self.assertEqual(z.read('SunriseImage/SunriseImage.exe'),b'new-exe')

    def test_subprocess_error_is_visible_and_retained_in_log(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);audit=root/'Windows_결과';audit.mkdir()
            def failed(*args, **kwargs):
                kwargs['stdout'].write('INFO: analyzing hooks\nERROR: Aborting build process due to multiple Qt bindings\n')
                return subprocess.CompletedProcess(args[0], 1)
            with patch.object(build_windows,'ROOT',root),patch.object(build_windows,'AUDIT',audit),patch.object(build_windows.subprocess,'run',side_effect=failed),patch('builtins.print') as printer:
                with self.assertRaisesRegex(RuntimeError, '02_pyinstaller.log: command failed'):
                    build_windows.command(['dummy-pyinstaller'], '02_pyinstaller.log')
            log_text=(audit/'02_pyinstaller.log').read_text(encoding='utf-8')
            self.assertIn('multiple Qt bindings',log_text)
            output='\n'.join(str(c) for c in printer.call_args_list)
            self.assertIn('multiple Qt bindings',output)
            self.assertIn('PySide6',output)

    def test_pyinstaller_hint_and_malformed_log_bytes(self):
        with tempfile.TemporaryDirectory() as t:
            log=Path(t)/'02_pyinstaller.log';log.write_bytes(b'first\n' + b'bad\xffbytes\n' + b'last error\n')
            self.assertIn('last error',build_windows._log_tail(log))
            self.assertIn('\ufffd',build_windows._log_tail(log))
        self.assertIn('파일 사용 중',build_windows._failure_hint('02_pyinstaller.log','PermissionError: [WinError 32]'))
        self.assertIn('모듈 누락',build_windows._failure_hint('02_pyinstaller.log',"ModuleNotFoundError: No module named 'foo'"))

    def test_promotion_denied_keeps_previous_distribution(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);existing=root/'dist/SunriseImage';existing.mkdir(parents=True)
            (existing/'SunriseImage.exe').write_bytes(b'old-exe')
            stage=root/'stage/SunriseImage';stage.mkdir(parents=True)
            (stage/'SunriseImage.exe').write_bytes(b'new-exe')
            with patch.object(build_windows.Path,'rename',autospec=True) as rename:
                def deny_old_move(path,target):
                    if path == existing:
                        raise PermissionError('locked old file')
                    return path.rename(target)
                rename.side_effect=deny_old_move
                with self.assertRaisesRegex(RuntimeError,'교체할 수 없습니다'):
                    build_windows.promote_verified_directory(stage,existing,root)
            self.assertEqual((existing/'SunriseImage.exe').read_bytes(),b'old-exe')
            self.assertEqual((stage/'SunriseImage.exe').read_bytes(),b'new-exe')

    def test_promotion_reverts_previous_exe_on_staged_rename_failure(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);existing=root/'dist/SunriseImage';existing.mkdir(parents=True)
            (existing/'SunriseImage.exe').write_bytes(b'old-exe')
            stage=root/'stage/SunriseImage';stage.mkdir(parents=True)
            (stage/'SunriseImage.exe').write_bytes(b'new-exe')
            original_rename=Path.rename
            def fail_new_move(path,target):
                if path == stage:
                    raise OSError('simulated rename failure')
                return original_rename(path,target)
            with patch.object(build_windows.Path,'rename',autospec=True,side_effect=fail_new_move):
                with self.assertRaisesRegex(OSError,'simulated rename failure'):
                    build_windows.promote_verified_directory(stage,existing,root)
            self.assertEqual((existing/'SunriseImage.exe').read_bytes(),b'old-exe')
            self.assertEqual((stage/'SunriseImage.exe').read_bytes(),b'new-exe')

    def test_pyinstaller_matplotlib_error_gets_actionable_hint(self):
        hint=build_windows._failure_hint('02_pyinstaller.log',
            "PermissionError: denied 'dist\\SunriseImage\\_internal\\matplotlib\\mpl-data\\images\\back.pdf'")
        self.assertIn('Matplotlib',hint)
        self.assertIn('임시 폴더',hint)

    def test_legacy_qt_packages_warn_without_uninstall(self):
        from importlib import metadata
        def fake_version(name):
            return {'PySide6-Essentials':'6.12.0','PySide6':'6.9.3','PySide6-Addons':'6.9.3'}[name]
        with patch.object(build_windows.importlib.metadata,'version',side_effect=fake_version):
            warnings=build_windows._pyside6_distribution_conflicts()
        self.assertEqual(len(warnings),2)
        self.assertTrue(all('6.9.3' in x for x in warnings))

    def test_non_windows_does_not_create_release(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);audit=root/'audit'
            with patch.object(build_windows,'ROOT',root),patch.object(build_windows,'AUDIT',audit),patch.object(build_windows.platform,'system',return_value='Linux'),patch('builtins.print'):
                self.assertEqual(build_windows.main(),1)
            result=json.loads((audit/'WINDOWS_BUILD_RESULT.json').read_text())
            self.assertEqual(result['status'],'FAILED');self.assertFalse((root/'release').exists())

    def test_repository_source_audit_matches_actual_files(self):
        audit=build_windows.check_source_audit()
        self.assertEqual(audit['status'],'PASS')
        self.assertGreaterEqual(len(audit['sha256']),50)

if __name__=='__main__':unittest.main(verbosity=2)
