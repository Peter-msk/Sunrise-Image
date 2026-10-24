"""Capture Python startup failures before loading GUI/native dependencies."""
import os,sys,traceback
from pathlib import Path

def main():
    try:
        from diagnostics import configure_logging
        configure_logging()
        from hwpx_image_extractor import main as start
        start()
    except Exception:
        folder=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'SunriseImage'/'Diagnostics'
        folder.mkdir(parents=True,exist_ok=True);path=folder/'startup_error.log'
        path.write_text(traceback.format_exc(),encoding='utf-8')
        message='프로그램 시작 중 오류가 발생했습니다.\n오류 기록: '+str(path)
        if sys.platform=='win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,message,'Sunrise Image',0x10)
        elif sys.stderr:print(message,file=sys.stderr)
        sys.exit(1)

if __name__=='__main__':main()
