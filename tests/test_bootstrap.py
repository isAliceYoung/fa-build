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

    def fixture(self,answer,error=None):
        temp=tempfile.TemporaryDirectory(prefix='public-bootstrap-test-');self.addCleanup(temp.cleanup)
        root=Path(temp.name)/'source'
        class Source:
            source=root;commit='a'*40
            def prepare(self):return 'ssh-ed25519 TEST_PUBLIC_FIXTURE_ONLY fixture'
            @contextlib.contextmanager
            def locked(self):yield
            def verify_local(self):pass
            def authorized(self):
                if error:raise ui.private.Failure(error,'simulated denial')
                return 'b'*40
            def clone(self):
                root.mkdir()
                for name,data in [('webdesktop-deploy/scripts/interactive_deploy.py',b'# approved fixture'),('webdesktop-deploy/scripts/private_repo.py',b'# helper fixture')]:
                    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
                return dict(dirty=False,commit='a'*40)
            def check_node(self,*args):pass
        m=dict(commit='a'*40,entrypoint='webdesktop-deploy/scripts/interactive_deploy.py',entrypoint_sha256=hashlib.sha256(b'# approved fixture').hexdigest(),source_helper_sha256=hashlib.sha256(b'# helper fixture').hexdigest())
        a=types.SimpleNamespace(mode='local-test')
        coordinator=mock.Mock()
        with mock.patch.object(ui.tools,'initial'),mock.patch.object(ui.private,'PrivateSource',return_value=Source()),mock.patch.object(ui,'load',return_value=coordinator):
            with contextlib.redirect_stdout(io.StringIO()):result=ui.flow(a,m,lambda _:answer)
        return result,coordinator

    def test_n_never_enters_private_deployment(self):
        value,coordinator=self.fixture('n');self.assertFalse(value);coordinator.deploy.assert_not_called()

    def test_y_still_requires_live_authorization(self):
        for error in ('AUTHORIZATION','HOST_KEY','NETWORK','BRANCH','COMMIT'):
            with self.subTest(error=error),self.assertRaises(ui.private.Failure):self.fixture('y',error)

    def test_authorized_y_delegates_once_after_fixed_source_hashes(self):
        value,coordinator=self.fixture('y');self.assertTrue(value);coordinator.deploy.assert_called_once()

    def test_local_test_cannot_be_silently_enabled(self):
        with mock.patch.object(ui.private,'require_platform'),mock.patch.object(ui,'metadata',return_value={}):
            with self.assertRaisesRegex(ValueError,'LOCAL_TEST_TRUST_ACK'):ui.main(['--mode','local-test'])

    def test_explicit_install_flags_required(self):
        with mock.patch.object(ui.private,'require_platform'),mock.patch.object(ui,'metadata',return_value={}):
            with self.assertRaisesRegex(ValueError,'INSTALL_AND_EGRESS'):ui.main([])

    def test_resources_and_insufficient_disk(self):
        self.assertEqual(ui.tools.capacity(2*1024**3,2,2*1024**3,15*1024**3,'local-test')['free'],15*1024**3)
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

if __name__=='__main__':unittest.main(verbosity=2)
