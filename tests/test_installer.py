"""Run installer lifecycle against fake Git/service tools and temporary files only."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from test_regressions import ROOT

FAKE = r'''#!PYTHON
import os,sys,json,shutil,datetime
from pathlib import Path
name=Path(sys.argv[0]).name
args=sys.argv[1:]
base=Path(os.environ['TEST_INSTALL_ROOT'])
mode=os.environ.get('TEST_INSTALL_MODE','ok')
with (base/'calls').open('a') as stream: stream.write(json.dumps([name]+args)+'\n')
if name=='git':
    if args[0]=='clone':
        dest=Path(args[-1]);dest.mkdir(parents=True)
        shutil.copytree(os.environ['TEST_INSTALL_BUNDLE'],dest/'VocalisMeta.bundle')
    elif 'init' in args:
        dest=Path(args[1]);shutil.copytree(os.environ['TEST_INSTALL_BUNDLE'],dest/'VocalisMeta.bundle')
    elif 'describe' in args: print('v0.1.1')
    elif 'rev-parse' in args: print('abc1234')
elif name=='id':
    sys.exit(1 if mode=='missing_user' else 0)
elif name=='chown':
    sys.exit(1 if mode=='permission' else 0)
elif name=='sleep': pass
elif name=='mv':
    source,dest=Path(args[-2]),Path(args[-1])
    if mode=='move_failure' and source.parent.name=='repository': sys.exit(1)
    shutil.move(str(source),str(dest))
elif name=='systemctl':
    if args[0]=='stop' and mode=='stop_failure': sys.exit(1)
    if args[0]=='is-active': sys.exit(1 if mode=='inactive' else 0)
    if args[0]=='start':
        counter=base/'starts'
        count=int(counter.read_text())+1 if counter.exists() else 1
        counter.write_text(str(count))
        if mode=='interrupt' and count==1:
            import signal
            os.kill(os.getppid(),signal.SIGTERM)
            sys.exit(1)
        if mode=='start_failure' and count==1: sys.exit(1)
        if mode=='restore_start_failure':
            if count>1: sys.exit(1)
        log=Path(os.environ['VOCALISMETA_LOG_FILE'])
        log.parent.mkdir(parents=True,exist_ok=True)
        stamp=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if mode in ('fatal','restore_start_failure'):
            log.write_text(stamp+' NameError: broken fixture\n')
        elif mode!='no_registration':
            log.write_text(stamp+' Creating new agent class called VocalisMetaAlbum\n'+stamp+' Started plug-in\n')
'''


class InstallerLifecycle(unittest.TestCase):
    def run_case(self, mode='ok', previous=True, release=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        bin_dir = root / 'bin';bin_dir.mkdir()
        for name in ('git', 'id', 'chown', 'sleep', 'mv', 'systemctl'):
            p = bin_dir / name;p.write_text(FAKE.replace('PYTHON', sys.executable, 1));p.chmod(0o755)
        # Use the production interpreter for both installer-owned compatibility checks.
        (bin_dir / 'python3').symlink_to(sys.executable)
        script = (ROOT / 'scripts/install-on-plex.sh').read_text()
        start = script.index('if (( EUID != 0 )); then')
        end = script.index('\nfi', start) + 3
        # Remove only the root gate from this disposable fixture; production keeps it.
        script = script[:start] + script[end:]
        test_script = root / 'installer.sh';test_script.write_text(script)
        plugins = root / 'plugins';plugins.mkdir()
        old = plugins / 'VocalisMeta.bundle'
        if previous:
            old.mkdir();(old / 'old-marker').write_text('original bundle')
        env = dict(os.environ, PATH=str(bin_dir)+os.pathsep+os.environ['PATH'],
            TEST_INSTALL_ROOT=str(root), TEST_INSTALL_MODE=mode,
            TEST_INSTALL_BUNDLE=str(ROOT / 'VocalisMeta.bundle'),
            VOCALISMETA_PLUGIN_DIRECTORY=str(plugins), VOCALISMETA_LOG_FILE=str(root/'agent.log'),
            PLEX_USER='fixture', PLEX_GROUP='fixture', PLEX_SERVICE_NAME='fixture-only', TMPDIR=str(root))
        result = subprocess.run(['bash', str(test_script)] + (['--release','v0.1.1'] if release else ['--developer']),
            env=env, text=True, capture_output=True, timeout=20)
        calls = [json.loads(line) for line in (root/'calls').read_text().splitlines()]
        return result, root, old, calls

    def test_success_retains_backup(self):
        result, root, old, calls = self.run_case()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((old/'Contents/Info.plist').exists())
        self.assertEqual(len(list((root/'plugins').glob('.vocalismeta-backup.*/old-marker'))), 1)
        self.assertIn('installed successfully', result.stdout)

    def test_release_mode_uses_exact_tag(self):
        result, root, old, calls = self.run_case(release=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any('refs/tags/v0.1.1:refs/tags/v0.1.1' in call for call in calls))

    def test_failures_restore_original_bundle(self):
        for mode in ('fatal', 'no_registration', 'inactive', 'start_failure', 'move_failure', 'interrupt'):
            with self.subTest(mode=mode):
                result, root, old, calls = self.run_case(mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((old/'old-marker').read_text(), 'original bundle')
                self.assertFalse((old/'Contents').exists())
                self.assertGreaterEqual(int((root/'starts').read_text()), 1)

    def test_permission_and_stop_failure_leave_old_install(self):
        for mode in ('permission', 'stop_failure', 'missing_user'):
            with self.subTest(mode=mode):
                result, root, old, calls = self.run_case(mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue((old/'old-marker').exists())
                self.assertFalse((root/'starts').exists())

    def test_failed_first_install_removes_candidate(self):
        result, root, old, calls = self.run_case('fatal', previous=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(old.exists())

    def test_restore_service_failure_is_reported(self):
        result, root, old, calls = self.run_case('restore_start_failure')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((old/'old-marker').exists())
        self.assertIn('could not restart', result.stderr)
