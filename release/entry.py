"""共同入口：GUI 启动器／备份窗口／带标准输出的独立按键进程。"""
from pathlib import Path
import sys
import json

if not getattr(sys,'frozen',False):
    source=Path(__file__).resolve().parents[1]
    sys.path[:0]=[str(source),str(source/'.deps')]


def main():
    name=Path(sys.executable).stem.casefold()
    if name=='ssekeyworker' or '--key-worker' in sys.argv:
        if '--key-worker' in sys.argv:sys.argv.remove('--key-worker')
        from solution_editor.windows_keys import main as worker
        try:worker();return 0
        except Exception as error:print(json.dumps(dict(error=str(error))),flush=True);return 1
    import argparse
    parser=argparse.ArgumentParser(description='Sinking Star Editor')
    parser.add_argument('--panel',action='store_true');parser.add_argument('--backup',action='store_true')
    parser.add_argument('--startup-status',type=Path);parser.add_argument('--diagnostics',type=Path)
    args=parser.parse_args()
    from solution_editor.paths import paths
    from solution_editor.release_profile import VERSION,preview
    from solution_editor.localization import language,tr
    layout=paths();layout.prepare()
    if args.diagnostics:
        import frida,platform
        from solution_editor.game_builds import LEGACY,UPDATED
        row=dict(version=VERSION,platform=platform.platform(),pointer_bits=__import__('struct').calcsize('P')*8,
                 frozen=bool(getattr(sys,'frozen',False)),preview=preview(),portable=layout.portable,language=language(),
                 frida=frida.__version__,resources={p.name:p.exists() for p in [layout.assets/'ingame_overlay.js',layout.assets/'game_speed.js',layout.resources/'locales/en.json']},
                 key_worker=(layout.app/'SSEKeyWorker.exe').exists(),data=str(layout.data),supported_builds=[LEGACY.sha256,UPDATED.sha256])
        args.diagnostics.parent.mkdir(parents=True,exist_ok=True);args.diagnostics.write_text(json.dumps(row,indent=2),encoding='utf-8');return 0
    if args.panel:
        from solution_editor.ingame_panel import main as panel
        sys.argv=[sys.argv[0],'--log',str(layout.logs/'ingame-window.log')]
        if args.startup_status:sys.argv+=['--startup-status',str(args.startup_status)]
        try:panel();return 0
        except Exception as error:
            import traceback
            (layout.logs/'launcher-error.log').write_text(traceback.format_exc(),encoding='utf-8')
            from solution_editor.startup_status import report,friendly_error
            report(args.startup_status,'failed',tr(friendly_error(error)));return 1
    from solution_editor.release_ui import run
    run(backup=args.backup or name=='savebackup');return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        import ctypes,traceback
        try:
            from solution_editor.paths import paths
            log=paths().logs;log.mkdir(parents=True,exist_ok=True);(log/'launcher-error.log').write_text(traceback.format_exc(),encoding='utf-8')
        except Exception:pass
        ctypes.windll.user32.MessageBoxW(None,str(error),'Sinking Star Editor',0x10)
        raise SystemExit(1)
