"""Fast simulated interaction only. No SSH/GitHub/APT/services are contacted."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import types
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('public_ui',ROOT/'scripts/interactive.py')
ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(ui)

class Interaction(unittest.TestCase):
    def test_domain_diagnostics_preserve_claude_beta_and_version_errors(self):
        diag=ui.tools.diag
        for code,stage in [('CLAUDE_SIGNING_FINGERPRINT_MISMATCH','claude-package'),
                           ('PUBLISHED_VERSION_TAG_MISMATCH','authorization'),('UNSAFE_BETA_CHECKOUT','authorization'),
                           ('DOMAIN_AUTH_BOUNDARY_FAILED','domain-binding')]:
            with self.subTest(code=code):
                value=diag.fields(diag.safe(ValueError(code),stage=stage))
                self.assertEqual(value['code'],code);self.assertEqual(value['stage'],stage)
                self.assertTrue(value['reason'])

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
            def validate_identity(self):return 'ssh-ed25519 TEST_PUBLIC_FIXTURE_ONLY fixture'
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
        with mock.patch.object(ui.tools.diag,'append'),mock.patch.object(ui.tools,'initial'),mock.patch.object(ui.private,'PrivateSource',return_value=Source()),mock.patch.object(ui,'load',return_value=coordinator),mock.patch.object(ui,'display_credentials',return_value=True) as display:
            self.display=display
            def read(_):
                if '版本' in _:return '1.0.0'
                if existing and error!='AUTHORIZATION':raise AssertionError('Valid existing identity must not prompt again')
                return answer
            self.output=io.StringIO()
            with contextlib.redirect_stdout(self.output):result=ui.flow(a,m,read)
            if existing and error!='AUTHORIZATION':self.assertNotIn('Public key:',self.output.getvalue())
        return result,coordinator

    def test_n_never_enters_private_deployment(self):
        value,coordinator=self.fixture('n');self.assertFalse(value);coordinator.deploy.assert_not_called()

    def test_y_still_requires_live_authorization(self):
        for error in ('AUTHORIZATION','HOST_KEY','NETWORK','BRANCH','COMMIT'):
            with self.subTest(error=error),self.assertRaises(ui.private.Failure):self.fixture('y',error)

    def test_authorized_y_delegates_once_after_fixed_source_hashes(self):
        value,coordinator=self.fixture('y');self.assertTrue(value);coordinator.deploy.assert_called_once()

    def test_success_automatically_displays_credentials_after_deployment(self):
        self.fixture('y')
        self.display.assert_called_once()

    def test_failed_health_or_installation_never_displays_credentials(self):
        with self.assertRaisesRegex(ValueError,'FINAL_HEALTH_NOT_READY'):self.fixture('y',install_error=True)
        self.display.assert_not_called()

    def test_existing_valid_key_live_authorized_without_prompt(self):
        value,coordinator=self.fixture('',existing=True);self.assertTrue(value);coordinator.deploy.assert_called_once()

    def test_existing_invalid_identity_and_network_errors_never_prompt_or_rekey(self):
        for error in ('HOST_KEY','NETWORK','BRANCH','COMMIT'):
            with self.subTest(error=error),self.assertRaises(ui.private.Failure):self.fixture('',error=error,existing=True)
        with self.assertRaisesRegex(ui.private.Failure,'unsafe fixture'):self.fixture('',existing=True,broken=True)

    def test_existing_unauthorized_key_still_denied_after_y(self):
        with self.assertRaises(ui.private.Failure):self.fixture('y',error='AUTHORIZATION',existing=True)

    def test_existing_unauthorized_key_n_or_empty_never_installs(self):
        for answer in ('n',''):
            value,coordinator=self.fixture(answer,error='AUTHORIZATION',existing=True)
            self.assertFalse(value);coordinator.deploy.assert_not_called()

    def test_interrupted_key_authorization_reuses_the_same_key_after_y(self):
        with tempfile.TemporaryDirectory() as directory:
            key=Path(directory)/'deploy_key';key.write_bytes(b'nonsecret simulated identity')
            class Source:
                attempts=0
                def locked(self):return contextlib.nullcontext()
                def verify_local(self):pass
                def validate_identity(self):return 'ssh-ed25519 TEST_PUBLIC_FIXTURE_ONLY existing'
                def prepare(self):raise AssertionError('Do not regenerate the key')
                def authorized(self):
                    self.attempts+=1
                    if self.attempts==1:raise ui.private.Failure('AUTHORIZATION','simulated first denial')
            source=Source();source.key=key
            output=io.StringIO()
            with contextlib.redirect_stdout(output):self.assertTrue(ui.authorize_source(source,lambda _:'y'))
            self.assertEqual(source.attempts,2);self.assertEqual(key.read_bytes(),b'nonsecret simulated identity')
            self.assertIn('existing key retained',output.getvalue());self.assertIn('TEST_PUBLIC_FIXTURE_ONLY existing',output.getvalue())

    def test_key_identity_cannot_change_while_waiting_for_consent(self):
        with tempfile.TemporaryDirectory() as directory:
            source=mock.Mock();source.key=Path(directory)/'deploy_key';source.key.write_bytes(b'fixture')
            source.locked.side_effect=lambda:contextlib.nullcontext()
            source.authorized.side_effect=ui.private.Failure('AUTHORIZATION','simulated denial')
            source.validate_identity.side_effect=['ssh-ed25519 ORIGINAL fixture','ssh-ed25519 CHANGED fixture']
            with contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(ValueError,'KEY_PAIR'):
                ui.authorize_source(source,lambda _:'y')
            source.authorized.assert_called_once();source.prepare.assert_not_called()

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

class CredentialDisplay(unittest.TestCase):
    def test_domain_user_handoff_is_only_written_to_administrator_tty(self):
        class Terminal(io.StringIO):
            def close(self):pass
        terminal=Terminal();out=io.StringIO();err=io.StringIO();source=mock.Mock()
        raw=b'{"DESKTOP_PASSWORD":"desktop-fixture-password"}'
        meta=types.SimpleNamespace(st_dev=1,st_ino=2,st_mode=ui.stat.S_IFREG|0o600,st_uid=0,st_nlink=1)
        class Secret(io.BytesIO):
            def fileno(self):return 92
        def fdopen(fd,*args,**kwargs):return terminal if fd==91 else Secret(raw)
        def cat(*args,**kwargs):kwargs['stdout'].write('administrator-only-fixture');return types.SimpleNamespace(returncode=0)
        with contextlib.ExitStack() as stack:
            for name in ('O_NOCTTY','O_CLOEXEC','O_NOFOLLOW'):
                stack.enter_context(mock.patch.object(ui.os,name,getattr(ui.os,name,0),create=True))
            stack.enter_context(mock.patch.object(ui.os,'geteuid',return_value=0,create=True))
            stack.enter_context(mock.patch.object(ui.os,'open',side_effect=[91,92]))
            stack.enter_context(mock.patch.object(ui.os,'isatty',return_value=True))
            stack.enter_context(mock.patch.object(ui.os,'fdopen',side_effect=fdopen))
            stack.enter_context(mock.patch.object(ui.os,'fstat',return_value=meta))
            stack.enter_context(mock.patch.object(Path,'lstat',return_value=meta))
            stack.enter_context(mock.patch.object(ui.subprocess,'run',side_effect=cat))
            logs=stack.enter_context(mock.patch.object(ui.tools.diag,'append'))
            stack.enter_context(contextlib.redirect_stdout(out));stack.enter_context(contextlib.redirect_stderr(err))
            self.assertTrue(ui.display_credentials(source,'https://'+'a'*24+'.ourgoal.win'))
        visible=terminal.getvalue()
        self.assertIn('交给用户的信息',visible);self.assertIn('desktop-fixture-password',visible)
        self.assertLess(visible.index('desktop-fixture-password'),visible.index('以下管理信息仅由管理员保留'))
        self.assertIn('administrator-only-fixture',visible)
        self.assertNotIn('fixture',out.getvalue()+err.getvalue());logs.assert_not_called()

    def display(self,unsafe=False,no_terminal=False,child_failure=False,timeout=False,root=True):
        source=mock.Mock()
        if unsafe:source.check_node.side_effect=ui.private.Failure('PERMISSIONS','fixture protected file rejected')
        class Terminal(io.StringIO):
            def close(self):pass  # Preserve the simulated terminal for assertions.
        terminal=Terminal();out=io.StringIO();err=io.StringIO()
        def cat(*args,**kwargs):
            if timeout:raise ui.subprocess.TimeoutExpired(args[0],10)
            if not child_failure:kwargs['stdout'].write('{"DESKTOP_PASSWORD":"initial-test-password"}\n')
            return types.SimpleNamespace(returncode=1 if child_failure else 0,stderr='unreviewed child output')
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(ui.os,'geteuid',return_value=0 if root else 1000,create=True))
            for name in ('O_NOCTTY','O_CLOEXEC','O_NOFOLLOW'):
                stack.enter_context(mock.patch.object(ui.os,name,getattr(ui.os,name,0),create=True))
            opened=stack.enter_context(mock.patch.object(ui.os,'open',return_value=91,side_effect=OSError('no terminal') if no_terminal else None))
            stack.enter_context(mock.patch.object(ui.os,'isatty',return_value=True))
            stack.enter_context(mock.patch.object(ui.os,'fdopen',return_value=terminal))
            run=stack.enter_context(mock.patch.object(ui.subprocess,'run',side_effect=cat))
            logged=stack.enter_context(mock.patch.object(ui.tools.diag,'append'))
            stack.enter_context(contextlib.redirect_stdout(out));stack.enter_context(contextlib.redirect_stderr(err))
            result=ui.display_credentials(source)
        self.assertNotIn('initial-test-password',out.getvalue()+err.getvalue())
        self.assertNotIn('unreviewed child output',out.getvalue()+err.getvalue())
        logged.assert_not_called()
        return result,source,terminal,out.getvalue(),run,opened

    def test_cat_executes_directly_to_terminal_after_protected_path_checks(self):
        result,source,terminal,out,run,opened=self.display()
        self.assertTrue(result);self.assertIn('initial-test-password',terminal.getvalue())
        source.directory.assert_called_once_with(ui.CREDENTIALS.parent,private=True)
        source.check_node.assert_called_once_with(ui.CREDENTIALS,private=True)
        self.assertEqual(run.call_args[0][0],['/usr/bin/cat','--','/etc/webdesktop-isolated/login.json'])
        self.assertIs(run.call_args[1]['stdout'],terminal)
        self.assertEqual(run.call_args[1]['stderr'],ui.subprocess.DEVNULL)
        self.assertEqual(run.call_args[1]['env'],{'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
        self.assertNotIn('cat /etc/webdesktop-isolated/login.json',out)

    def test_no_terminal_never_sends_passwords_to_redirected_stdout(self):
        result,_,terminal,out,run,_=self.display(no_terminal=True)
        self.assertFalse(result);run.assert_not_called();self.assertEqual(terminal.getvalue(),'')
        self.assertIn('cat /etc/webdesktop-isolated/login.json',out)

    def test_unsafe_credential_path_is_not_read(self):
        result,_,terminal,_,run,opened=self.display(unsafe=True)
        self.assertFalse(result);run.assert_not_called();opened.assert_not_called()
        self.assertEqual(terminal.getvalue(),'')

    def test_cat_error_or_timeout_keeps_successful_installation_and_hides_raw_output(self):
        for options in ({'child_failure':True},{'timeout':True}):
            result,_,terminal,out,run,_=self.display(**options)
            self.assertFalse(result);run.assert_called_once()
            self.assertIn('安装已成功',out);self.assertNotIn('initial-test-password',terminal.getvalue())

    def test_nonroot_cannot_display_initial_credentials(self):
        with self.assertRaisesRegex(ValueError,'ROOT_REQUIRED'):self.display(root=False)


class CheckoutReuse(unittest.TestCase):
    def fixture(self,issue=None):
        temp=tempfile.TemporaryDirectory(prefix='bootstrap-reentry-');self.addCleanup(temp.cleanup)
        root=Path(temp.name)/'checkout';root.mkdir()
        def git(*args):
            return subprocess.check_output(['git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false','-C',str(root),*args],stderr=subprocess.STDOUT).decode().strip()
        git('init','-q');git('config','core.autocrlf','false');git('config','user.name','local-fixture');git('config','user.email','fixture@example.invalid')
        for name in ('install.sh','bootstrap.sh','scripts/interactive.py','release.json'):
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('nonsecret test data\n')
        git('add','.');git('commit','-qm','local fixture');git('remote','add','origin','https://github.com/isAliceYoung/fa-build.git')
        if issue=='origin':git('remote','set-url','origin','https://github.com/example/other.git')
        if issue=='dirty':(root/'install.sh').write_text('modified')
        if issue=='untracked':(root/'untracked.txt').write_text('keep')
        before={p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file() and '.git' not in p.relative_to(root).parts}
        calls=[]
        def runner(argv,**kwargs):
            calls.append(list(map(str,argv)))
            self.assertFalse(any(x in argv for x in ('fetch','pull','clone','checkout','reset')))
            return subprocess.run([shutil.which('git'),*argv[1:]],**kwargs)
        checker=ui.private.PrivateSource(Path(temp.name)/'keys',Path(temp.name)/'private','git@github.com:isAliceYoung/fa.git','feature/CC','a'*40,runner=runner)
        original=Path.lstat
        def metadata(path,*args,**kwargs):
            value=original(path,*args,**kwargs);kind=stat.S_IFMT(value.st_mode)
            mode=0o755 if stat.S_ISDIR(value.st_mode) else 0o644;uid=0;links=value.st_nlink
            if path==root/'install.sh':
                if issue=='owner':uid=1001
                if issue=='mode':mode=0o664
                if issue=='symlink':kind=stat.S_IFLNK
                if issue=='hardlink':links=2
            return types.SimpleNamespace(st_mode=kind|mode,st_uid=uid,st_nlink=links)
        with mock.patch.object(ui.private,'PrivateSource',return_value=checker),mock.patch.object(Path,'lstat',metadata):
            if issue:
                with self.assertRaises((ValueError,ui.private.Failure)):ui.verify_checkout(root)
            else:
                for _ in range(2):self.assertEqual(ui.verify_checkout(root),git('rev-parse','HEAD'))
        after={p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file() and '.git' not in p.relative_to(root).parts}
        self.assertEqual(before,after);return calls

    def test_real_git_checkout_can_be_reused_without_fetch_or_modification(self):
        self.assertTrue(self.fixture())

    def test_unknown_modified_or_unsafe_checkout_preserved_and_refused(self):
        for issue in ('origin','dirty','untracked','owner','mode','symlink','hardlink'):
            with self.subTest(issue=issue):self.fixture(issue)

    def installed(self,phase='ready',native_commit='b'*40,bootstrap_commit='a'*40,fresh_commit='a'*40):
        temp=tempfile.TemporaryDirectory(prefix='install-skip-');self.addCleanup(temp.cleanup)
        paths=tuple(Path(temp.name)/(n+'.json') for n in ('native','bootstrap','fresh'))
        values=[dict(schema=1,status=phase,phase=phase,deployment_kind='isolated',authorized_new_vps=True,branch='feature/CC',commit=native_commit),
                dict(schema=1,phase=phase,commit=bootstrap_commit),dict(schema=1,phase=phase,result=phase,inputs=dict(commit=fresh_commit))]
        for path,value in zip(paths,values):path.write_text(json.dumps(value))
        before=[p.read_bytes() for p in paths]
        original=Path.lstat
        def meta(path,*args,**kwargs):
            value=original(path,*args,**kwargs)
            return types.SimpleNamespace(st_mode=stat.S_IFMT(value.st_mode)|(0o755 if stat.S_ISDIR(value.st_mode) else 0o600),st_uid=0,st_nlink=1,st_size=value.st_size)
        with mock.patch.object(ui,'INSTALL_RECORDS',paths),mock.patch.object(Path,'lstat',meta),contextlib.redirect_stdout(io.StringIO()) as out:
            result=ui.reuse_installation()
        self.assertEqual([p.read_bytes() for p in paths],before)
        return result,out.getvalue()

    def test_completed_installation_is_skipped_without_health_success_claim(self):
        result,out=self.installed();self.assertTrue(result);self.assertIn('ALREADY_INSTALLED',out);self.assertNotIn('PASS',out)

    def test_interrupted_or_failed_installation_cannot_be_skipped_as_success(self):
        for phase in ('installing','building','failed'):
            with self.subTest(phase=phase):self.assertFalse(self.installed(phase)[0])

    def test_inconsistent_completed_records_are_rejected(self):
        with self.assertRaises(ValueError):self.installed(fresh_commit='c'*40)

    def test_main_skips_completed_installation_before_apt_authorization_or_deploy(self):
        with mock.patch.object(ui.private,'require_platform'),mock.patch.object(ui,'verify_checkout',return_value='a'*40),mock.patch.object(ui,'metadata',return_value={}),mock.patch.object(ui,'reuse_installation',return_value=True),mock.patch.object(ui,'flow') as flow,mock.patch.object(ui.tools,'initial') as initial,contextlib.redirect_stdout(io.StringIO()):
            ui.main(['--mode','local-test','--ack-local-test-trust','--authorize-install','--authorize-isolated-egress'])
        flow.assert_not_called();initial.assert_not_called()


if __name__=='__main__':unittest.main(verbosity=2)
