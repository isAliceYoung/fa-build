"""Fast simulated interaction only. No SSH/GitHub/APT/services are contacted."""
import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('public_ui',ROOT/'scripts/interactive.py')
ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(ui)

class Interaction(unittest.TestCase):
    def test_consent_only_y_or_Y(self):
        for value,expected in [('y',True),('Y',True),('n',False),('N',False),('',False),('yes',False),('invalid',False)]:
            with self.subTest(value=value),contextlib.redirect_stdout(io.StringIO()):self.assertEqual(ui.consent(lambda _:value),expected)
        def eof(_):raise EOFError()
        self.assertFalse(ui.consent(eof))

    def fixture(self,answer,error=None,existing=False,broken=False,install_error=False):
        temp=tempfile.TemporaryDirectory(prefix='public-bootstrap-test-');self.addCleanup(temp.cleanup)
        root=Path(temp.name)/'source'
        if existing:(Path(temp.name)/'deploy_key').write_text('nonsecret fixture marker')
        class Source:
            source=root;commit='a'*40;branch='feature/CC';key=Path(temp.name)/'deploy_key'
            def prepare(self):
                if existing:raise AssertionError('Existing key must not be regenerated or repaired')
                return 'ssh-ed25519 TEST_PUBLIC_FIXTURE_ONLY fixture'
            @contextlib.contextmanager
            def locked(self):yield
            def verify_local(self):
                if broken:raise ui.private.Failure('KEY_PAIR','unsafe fixture keypair')
            def authorized(self):
                if error:raise ui.private.Failure(error,'simulated denial')
                return 'b'*40
            def git(self,*args):return 'a'*40+'\trefs/tags/v1.0.0'
            def clone(self):
                root.mkdir()
                for name,data in [('webdesktop-deploy/scripts/interactive_deploy.py',b'# approved fixture'),('webdesktop-deploy/scripts/private_repo.py',b'# helper fixture')]:
                    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
                return dict(dirty=False,commit='a'*40)
            def check_node(self,*args):pass
        m=dict(default_version='1.0.0',versions={'1.0.0':dict(commit='a'*40,tag='v1.0.0',branch='feature/CC',engine='isolated',entrypoint='webdesktop-deploy/scripts/interactive_deploy.py',entrypoint_sha256=hashlib.sha256(b'# approved fixture').hexdigest())},source_helper_sha256=hashlib.sha256(b'# helper fixture').hexdigest())
        a=types.SimpleNamespace(mode='local-test')
        coordinator=mock.Mock()
        if install_error:coordinator.deploy.side_effect=ValueError('FINAL_HEALTH_NOT_READY')
        with mock.patch.object(ui.tools.diag,'append'),mock.patch.object(ui.tools,'initial'),mock.patch.object(ui.private,'PrivateSource',return_value=Source()),mock.patch.object(ui,'load',return_value=coordinator):
            def read(_):
                if '版本' in _:return '1.0.0'
                if existing:raise AssertionError('Valid existing identity must not prompt again')
                return answer
            self.output=io.StringIO()
            with contextlib.redirect_stdout(self.output):result=ui.flow(a,m,read)
            if existing:self.assertNotIn('Public key:',self.output.getvalue())
        return result,coordinator

    def test_n_never_enters_private_deployment(self):
        value,coordinator=self.fixture('n');self.assertFalse(value);coordinator.deploy.assert_not_called()

    def test_y_still_requires_live_authorization(self):
        for error in ('AUTHORIZATION','HOST_KEY','NETWORK','BRANCH','COMMIT'):
            with self.subTest(error=error),self.assertRaises(ui.private.Failure):self.fixture('y',error)

    def test_authorized_y_delegates_once_after_fixed_source_hashes(self):
        value,coordinator=self.fixture('y');self.assertTrue(value);coordinator.deploy.assert_called_once()

    def test_success_prints_password_command_without_reading_passwords(self):
        self.fixture('y')
        self.assertIn('cat /etc/webdesktop-isolated/login.json',self.output.getvalue())
        with mock.patch('builtins.open',side_effect=AssertionError('Credentials must not be read')),contextlib.redirect_stdout(io.StringIO()) as output:
            ui.credential_help()
        self.assertIn('cat /etc/webdesktop-isolated/login.json',output.getvalue())

    def test_failed_health_or_installation_never_prints_password_command(self):
        with self.assertRaisesRegex(ValueError,'FINAL_HEALTH_NOT_READY'):self.fixture('y',install_error=True)
        self.assertNotIn('cat /etc/webdesktop-isolated/login.json',self.output.getvalue())

    def test_existing_valid_key_live_authorized_without_prompt(self):
        value,coordinator=self.fixture('',existing=True);self.assertTrue(value);coordinator.deploy.assert_called_once()

    def test_existing_invalid_or_revoked_identity_never_prompts_or_rekeys(self):
        for error in ('AUTHORIZATION','HOST_KEY','NETWORK','BRANCH','COMMIT'):
            with self.subTest(error=error),self.assertRaises(ui.private.Failure):self.fixture('',error=error,existing=True)
        with self.assertRaisesRegex(ui.private.Failure,'unsafe fixture'):self.fixture('',existing=True,broken=True)

    def test_local_test_cannot_be_silently_enabled(self):
        with mock.patch.object(ui.private,'require_platform'),mock.patch.object(ui,'metadata',return_value={}):
            with self.assertRaisesRegex(ValueError,'LOCAL_TEST_TRUST_ACK'):ui.main(['--mode','local-test'])

    def test_explicit_install_flags_required(self):
        with mock.patch.object(ui.private,'require_platform'),mock.patch.object(ui,'metadata',return_value={}):
            with self.assertRaisesRegex(ValueError,'INSTALL_AND_EGRESS'):ui.main([])

    def test_resources_and_insufficient_disk(self):
        self.assertEqual(ui.tools.capacity(2*1024**3,2,2*1024**3,15*1024**3,'local-test')['free'],15*1024**3)
        ui.tools.capacity(2*1024**3,2,2*1024**3,11*1024**3,'local-test')
        with self.assertRaises(ValueError):ui.tools.capacity(2*1024**3,2,0,11*1024**3,'local-test')
        for memory,cpu,free in [(512*1024**2,2,15*1024**3),(2*1024**3,1,15*1024**3),(2*1024**3,2,7*1024**3)]:
            with self.assertRaises(ValueError):ui.tools.capacity(memory,cpu,0,free,'local-test')

    def test_existing_correct_node_reused_without_download(self):
        with mock.patch.object(ui.tools.os.path,'lexists',return_value=True),mock.patch.object(ui.tools,'existing_node',return_value=Path('/usr/bin/node')) as existing, \
             mock.patch.object(ui.tools.urllib.request,'urlopen') as download:
            self.assertEqual(ui.tools.node(None),Path('/usr/bin/node'));download.assert_not_called();existing.assert_called_once()

    def test_wrong_node_preserved_and_download_not_used_to_overwrite(self):
        with mock.patch.object(ui.tools.os.path,'lexists',return_value=True),mock.patch.object(ui.tools,'existing_node',side_effect=ValueError('NODE_VERSION_MISMATCH')), \
             mock.patch.object(ui.tools.urllib.request,'urlopen') as download:
            with self.assertRaisesRegex(ValueError,'NODE_VERSION_MISMATCH'):ui.tools.node(None)
            download.assert_not_called()

    def test_status_module_has_no_install_side_effect(self):
        text=(ROOT/'scripts/status.py').read_text()
        for forbidden in ('subprocess','apt-get','mkdir','write_text','write_bytes','swapon'):self.assertNotIn(forbidden,text)

    def test_failed_node_download_can_reenter_only_its_owned_empty_root(self):
        with tempfile.TemporaryDirectory(prefix='node-retry-fixture-') as temp:
            root=Path(temp)/'toolchain'
            class Guard:
                def directory(self,path,create=False,private=False):
                    if create:path.mkdir()
                def write_new(self,path,data):
                    with path.open('x') as stream:stream.write(data)
                def check_node(self,*args,**kwargs):pass  # Linux DAC is separately NOT RUN.
            private=types.SimpleNamespace(PrivateSource=lambda *args:Guard())
            with mock.patch.object(ui.tools,'TOOLS',root),mock.patch.object(ui.tools,'existing_node',side_effect=ValueError('NODE_VERSION_MISMATCH')), \
                 mock.patch.object(ui.tools.urllib.request,'urlopen',side_effect=OSError('simulated network unavailable')) as download:
                for _ in range(2):
                    with self.assertRaisesRegex(OSError,'network unavailable'):ui.tools.node(private)
                self.assertEqual(download.call_count,2)
                (root/'unknown').write_text('preserve')
                with self.assertRaisesRegex(ValueError,'UNKNOWN_TOOLCHAIN_ROOT'):ui.tools.node(private)
                self.assertEqual((root/'unknown').read_text(),'preserve')

if __name__=='__main__':unittest.main(verbosity=2)
