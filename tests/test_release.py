"""分享版必要检查：仅使用项目内合成数据，不连接游戏。"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def test_markdown_release_has_resolvable_local_document_links(self):
        import re
        from release.manual_content import render
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
            folder=Path(tmp)
            render(folder)
            self.assertTrue((folder/'README.md').is_file())
            self.assertTrue((folder/'README.en.md').is_file())
            self.assertTrue((folder/'docs/使用细则.md').is_file())
            self.assertTrue((folder/'docs/USAGE.en.md').is_file())
            self.assertFalse(list(folder.rglob('*.html')))
            self.assertFalse(list(folder.glob('README*.txt')))
            # License files are installed by the package builder.
            (folder/'licenses').mkdir(exist_ok=True)
            for name in ('LICENSE.md','THIRD_PARTY_NOTICES.md','ootss-cmd-LICENSE.txt'):
                (folder/'licenses'/name).touch()
            for document in folder.rglob('*.md'):
                content=document.read_text(encoding='utf-8')
                targets=re.findall(r'\]\(([^)#]+)(?:#[^)]*)?\)',content)+re.findall(r'src="([^"]+)"',content)
                for target in targets:
                    if '://' not in target:
                        self.assertTrue((document.parent/target).exists(),(document,target))

    def test_manual_button_opens_local_markdown_even_without_file_association(self):
        from solution_editor.release_ui import Launcher
        from solution_editor.paths import Paths
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
            folder=Path(tmp);(folder/'docs').mkdir()
            manual=folder/'docs/USAGE.en.md';manual.write_text('# Usage',encoding='utf-8')
            window=Launcher.__new__(Launcher)
            with patch('solution_editor.release_ui.paths',return_value=Paths(folder,folder,True)),patch('solution_editor.release_ui.language',return_value='en'),patch('solution_editor.release_ui.os.startfile',side_effect=OSError('no association')),patch('solution_editor.release_ui.subprocess.Popen') as launch:
                window.open_manual()
            self.assertEqual(launch.call_args.args[0],['notepad.exe',str(manual)])

    def test_standalone_source_docs_render_without_workspace_or_executables(self):
        import shutil,subprocess,sys,os
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
            folder=Path(tmp)/'source';folder.mkdir()
            shutil.copytree(ROOT/'release',folder/'release')
            shutil.copytree(ROOT/'assets',folder/'assets')
            script="from release.manual_content import render; from pathlib import Path; render(Path('output'),source=True)"
            env=dict(os.environ);env.pop('PYTHONPATH',None)
            result=subprocess.run([sys.executable,'-B','-c',script],cwd=folder,env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            text=(folder/'output/README.en.md').read_text(encoding='utf-8')
            self.assertIn('python -B release/entry.py',text)
            self.assertNotIn('Run `SinkingStarEditor.exe`',text)
            self.assertTrue((folder/'output/docs/BUILD.zh-CN.md').is_file())
            self.assertTrue((folder/'output/docs/assets/order-of-the-sinking-star-store.jpg').is_file())

    def test_nested_development_paths_keep_assets_and_data_separate(self):
        import solution_editor.paths as module
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
            workspace=Path(tmp);dev=workspace/'dev';dev.mkdir()
            (workspace/'AGENTS.md').write_text('workspace')
            with patch.object(module,'__file__',str(dev/'solution_editor/paths.py')),patch.object(module.sys,'frozen',False,create=True),patch.object(module.sys,'_MEIPASS',str(dev),create=True):
                layout=module.paths()
            self.assertEqual(layout.app,dev)
            self.assertEqual(layout.assets,dev/'research')
            self.assertEqual(layout.projects,workspace/'data/projects')
            self.assertEqual(layout.config,workspace/'data/records/config')
            self.assertEqual(layout.logs,workspace/'data/records/runtime')
            self.assertEqual(layout.backups,workspace/'data/save-backups')

    def test_source_key_worker_can_start_outside_source_directory(self):
        import subprocess,os
        from solution_editor.macro_input import key_worker_prefix
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
            env={k:v for k,v in os.environ.items() if not k.upper().startswith('PYTHON')}
            result=subprocess.run(key_worker_prefix()+['--help'],cwd=tmp,env=env,capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('--pid',result.stdout)

    def test_build_paths_keep_delivery_outside_dev_and_reject_escape(self):
        import release.build as build
        from solution_editor.paths import workspace_root
        self.assertEqual(build.WORKSPACE,workspace_root(ROOT))
        self.assertEqual(build.inside(build.WORKSPACE/'deliverables/check'),build.WORKSPACE/'deliverables/check')
        with self.assertRaises(ValueError):build.inside(build.WORKSPACE.parent/'outside')
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
            self.assertEqual(workspace_root(Path(tmp)),Path(tmp))

    def test_frozen_key_worker_stays_beside_executable(self):
        from solution_editor.macro_input import key_worker_prefix
        with patch('sys.frozen',True,create=True),patch('sys.executable',str(ROOT/'synthetic/SinkingStarEditor.exe')):
            self.assertEqual(key_worker_prefix(),[str(ROOT/'synthetic/SSEKeyWorker.exe')])

    def test_backup_window_keeps_restore_buttons_visible_in_both_languages(self):
        from solution_editor.paths import Paths
        from solution_editor.release_ui import BackupWindow
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
            layout=Paths(Path(tmp),ROOT,True);layout.prepare()
            for locale in ('zh-CN','en'):
                with patch('solution_editor.release_ui.paths',return_value=layout),patch('solution_editor.release_ui.language',return_value=locale):
                    window=BackupWindow()
                    try:
                        window.root.geometry('900x700');window.root.update()
                        for button in window.buttons:
                            self.assertGreaterEqual(button.winfo_height(),30,(locale,button['text']))
                    finally:window.close()

    def test_english_preview_models_keep_private_fields_and_have_no_p_action(self):
        import re
        from solution_editor.ingame_panel import PanelState
        p=PanelState();p.preview=True;p.language='en';p.name='私人名称';p.toggle_hint='`'
        for state in ('closed','active','recovery'):
            p.project_state=state
            for settings in (False,True):
                p.settings_open=settings
                for width,height in ((1920,1080),(1280,720),(640,480)):
                    model=p.model(width,height)
                    self.assertEqual(model['locale'],'en')
                    self.assertLessEqual(len(model['items']),128)
                    for item in model['items']:
                        self.assertLessEqual(item['y']+item['h'],height+.01)
                        self.assertGreaterEqual(item['x'],0)
                        self.assertLessEqual(item['x']+item['w'],width+.01)
                        if item['kind']!='field' and item.get('id')!='language':
                            self.assertFalse(re.search('[\u3400-\u9fff]',item.get('text','')),item)
        p.project_state='active';p.inserting=True;p.action_open=True
        buttons={i.get('id') for i in p.model(1920,1080)['items'] if i['kind']=='button'}
        self.assertNotIn('choose_action:P',buttons)

    def test_p_preflight_precedes_reset_speed_or_input(self):
        from types import SimpleNamespace
        from solution_editor.recording_controller import RecordingController
        from solution_editor.timeline import Step
        c=RecordingController.__new__(RecordingController)
        c.projects=SimpleNamespace(session=SimpleNamespace(timeline=SimpleNamespace(steps=[Step('P')])))
        c._available=lambda:True
        c._normal_speed=lambda:(_ for _ in ()).throw(AssertionError('no speed change before P rejection'))
        with patch('solution_editor.release_profile.preview',return_value=True):
            with self.assertRaises(ValueError):c.begin_replay()

    def test_portable_paths_separate_resources_and_user_data(self):
        self.assertIsNotNone(importlib.util.find_spec('solution_editor.paths'))
        from solution_editor.paths import Paths
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
            root=Path(tmp);app=root/'app';resources=root/'runtime';app.mkdir();resources.mkdir()
            paths=Paths(app,resources,portable=True)
            self.assertEqual(paths.projects,app/'data/projects')
            self.assertEqual(paths.assets,resources/'research')
            paths.prepare();self.assertTrue(paths.logs.is_dir())
            self.assertFalse(resources.joinpath('data').exists())
            legacy=Paths(app,resources,portable=False)
            self.assertEqual(legacy.projects,app/'projects')

    def test_pending_sessions_require_local_environment_and_closed_legacy_can_open(self):
        from solution_editor.campaign_project import CampaignProject
        from solution_editor.game_builds import UPDATED
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
            root=Path(tmp);saves=root/'saves';(saves/'default').mkdir(parents=True)
            (saves/'default/state').write_bytes(b'synthetic')
            p=CampaignProject.create(root/'project','test',saves,'default',game_sha256=UPDATED.sha256)
            row=p.prepare_session(saves,return_campaign='default')
            self.assertIn('environment',row)
            pending_path=p.root/'session.json';original=pending_path.read_bytes()
            row['environment']='foreign';pending_path.write_text(json.dumps(row))
            with self.assertRaisesRegex(ValueError,'environment|环境|设备'):p.pending()
            self.assertEqual(json.loads(pending_path.read_text())['environment'],'foreign')
            row.pop('environment');pending_path.write_text(json.dumps(row))
            with self.assertRaises(ValueError):p.pending()
            row['phase']='closed';pending_path.write_text(json.dumps(row));self.assertIsNone(p.pending())

    def test_preview_disables_p_before_any_replay_or_recording(self):
        self.assertIsNotNone(importlib.util.find_spec('solution_editor.release_profile'))
        from solution_editor.release_profile import check_steps
        from solution_editor.timeline import Step
        with self.assertRaises(ValueError):check_steps([Step('U'),Step('P')],preview=True)
        check_steps([Step('U'),Step('_',1000)],preview=True)
        check_steps([Step('P')],preview=False)

    def test_toggle_key_is_persisted_and_conflicts_checked(self):
        self.assertIsNotNone(importlib.util.find_spec('solution_editor.key_settings'))
        from solution_editor.key_settings import parse_toggle,validate_toggle
        from solution_editor.native_bindings import BindingSnapshot
        self.assertEqual(parse_toggle('F10'),0x79);self.assertEqual(parse_toggle('`'),0xc0)
        with self.assertRaises(ValueError):parse_toggle('Ctrl')
        snapshot=BindingSnapshot([dict(name='Gameplay',enabled=True,rows=[dict(action='Forward',key=87,modifiers=0)])],[],'test')
        with self.assertRaises(ValueError):validate_toggle(87,snapshot,dict(correct='E',wait='T'))
        with self.assertRaises(ValueError):validate_toggle(ord('T'),snapshot,dict(correct='E',wait='T'))
        validate_toggle(0x79,snapshot,dict(correct='E',wait='T'))
        extended=BindingSnapshot([dict(name='Gameplay',enabled=True,rows=[dict(action='Custom',key=152,modifiers=0)])],[],'test')
        with self.assertRaises(ValueError):validate_toggle(0x79,extended,dict(correct='E',wait='T'))
        from solution_editor.tool_preferences import ToolPreferences
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
            path=Path(tmp)/'keys.json';preferences=ToolPreferences(path)
            preferences.save(dict(solve='P',correct='E',wait='T'),toggle='F10')
            self.assertEqual(ToolPreferences(path).toggle_vk,0x79)

    def test_unwritable_portable_folder_has_no_silent_fallback(self):
        from solution_editor.paths import Paths
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
            root=Path(tmp);layout=Paths(root,root,True)
            with patch('solution_editor.paths.tempfile.TemporaryFile',side_effect=PermissionError('readonly')):
                with self.assertRaisesRegex(PermissionError,'writable'):layout.prepare()
            self.assertEqual(layout.data,root/'data')

    def test_preview_p_key_is_not_reserved_and_cannot_trigger_completion(self):
        import subprocess
        script=r'''
const assert=require('node:assert/strict');const {PanelRecorder}=require('./research/panel_recorder.js');
const r=new PanelRecorder({steps:[],tool_keys:{solve:'P',correct:'E',wait:'T'},interval_ms:250,extra_wait_ms:1000},
{record:{80:'X'},undo:[90],unsupported:[],errors:[],solve_enabled:false},'new');r.start();
assert.equal(r.blocksPolling(80),false);assert.equal(r.key(80,true),false);
assert.equal(r.mode,'recording');assert.equal(r.document.steps[0].symbol,'X');
'''
        result=subprocess.run(['node','-e',script],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stderr)
