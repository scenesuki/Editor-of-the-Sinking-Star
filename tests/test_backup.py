import importlib.util
from contextlib import nullcontext
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


class BackupTests(unittest.TestCase):
    def test_game_installation_is_not_accepted_as_save_directory(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
            root=Path(tmp);game=root/'Order of the Sinking Star';game.mkdir()
            (game/'sinking_star.exe').write_bytes(b'synthetic executable marker')
            store=self.store(root)
            with self.assertRaises(ValueError):store.backup(game)
            self.assertFalse(store.root.exists())
            self.assertEqual((game/'sinking_star.exe').read_bytes(),b'synthetic executable marker')

    def test_failed_install_of_restore_rolls_back_without_merging(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
            root=Path(tmp);saves=root/'Order of the Sinking Star';saves.mkdir();(saves/'state').write_bytes(b'old')
            store=self.store(root);backup=store.backup(saves);(saves/'state').write_bytes(b'current')
            rename=Path.rename
            def fail_stage(path,target):
                if path.name.startswith('.ootss-restore-'):raise OSError('install failed')
                return rename(path,target)
            with patch.object(Path,'rename',fail_stage):
                with self.assertRaises(OSError):store.restore(backup,saves,confirmed=True)
            self.assertEqual((saves/'state').read_bytes(),b'current')
            self.assertEqual(len(store.list()),2)

    def test_pending_applied_restore_can_finish_without_overwriting_newer_files(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
            root=Path(tmp);saves=root/'Order of the Sinking Star';saves.mkdir();(saves/'state').write_bytes(b'old')
            store=self.store(root);backup=store.backup(saves);(saves/'state').write_bytes(b'current')
            with patch.object(store,'_finish',side_effect=OSError('finish interrupted')):
                with self.assertRaises(OSError):store.restore(backup,saves,confirmed=True)
            self.assertEqual((saves/'state').read_bytes(),b'old')
            (saves/'state').write_bytes(b'new progress')
            result=store.finish_pending()
            self.assertEqual(len(result),1);self.assertEqual((saves/'state').read_bytes(),b'new progress')

    def store(self,root,**kwargs):
        self.assertIsNotNone(importlib.util.find_spec('solution_editor.save_backup'))
        from solution_editor.save_backup import SaveBackupStore
        return SaveBackupStore(root/'backups',events=root/'events',guard=lambda:None,lease_factory=nullcontext,**kwargs)

    def test_full_restore_preserves_pre_restore_version_and_invalidates_owned_session(self):
        from solution_editor.campaign_project import CampaignProject
        from solution_editor.game_builds import UPDATED
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
            root=Path(tmp);saves=root/'Order of the Sinking Star';(saves/'default').mkdir(parents=True)
            (saves/'default/state').write_bytes(b'old');(saves/'User.keymap').write_bytes(b'keys')
            project=CampaignProject.create(root/'project','synthetic',saves,'default',game_sha256=UPDATED.sha256)
            session=project.prepare_session(saves,return_campaign='default')
            store=self.store(root,project_roots=[project.root]);backup=store.backup(saves)
            (saves/'default/state').write_bytes(b'new');(saves/'later').mkdir();(saves/'later/state').write_bytes(b'later')
            result=store.restore(backup,saves,confirmed=True)
            self.assertEqual((saves/'default/state').read_bytes(),b'old');self.assertFalse((saves/'later').exists())
            before=Path(result['before'])/'snapshot'
            self.assertEqual((before/'default/state').read_bytes(),b'new');self.assertTrue((before/'later/state').exists())
            self.assertIsNone(project.pending());self.assertEqual(len(list((project.root/'.session-history').glob('*.json'))),1)

    def test_tampered_backup_and_unconfirmed_restore_never_change_target(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
            root=Path(tmp);saves=root/'Order of the Sinking Star';saves.mkdir();(saves/'state').write_bytes(b'original')
            store=self.store(root);backup=store.backup(saves)
            with self.assertRaises(ValueError):store.restore(backup,saves,confirmed=False)
            (backup/'snapshot/state').write_bytes(b'bad')
            with self.assertRaises(ValueError):store.restore(backup,saves,confirmed=True)
            self.assertEqual((saves/'state').read_bytes(),b'original')

    def test_backup_destination_must_be_disjoint_and_running_guard_blocks(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
            root=Path(tmp);saves=root/'Order of the Sinking Star';saves.mkdir()
            store=self.store(root)
            store.guard=lambda:(_ for _ in ()).throw(ValueError('Game running'))
            with self.assertRaises(ValueError):store.backup(saves)
            self.assertFalse(store.root.exists())
            from solution_editor.save_backup import SaveBackupStore
            store=SaveBackupStore(saves/'nested',events=root/'events',guard=lambda:None,lease_factory=nullcontext)
            with self.assertRaises(ValueError):store.backup(saves)

    def test_copy_failure_keeps_current_save_and_does_not_publish_valid_backup(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
            root=Path(tmp);saves=root/'Order of the Sinking Star';saves.mkdir();(saves/'state').write_bytes(b'keep')
            store=self.store(root)
            with patch('solution_editor.save_backup.shutil.copyfile',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):store.backup(saves)
            self.assertEqual((saves/'state').read_bytes(),b'keep')
            self.assertEqual(list(store.root.glob('backup-*')),[])
