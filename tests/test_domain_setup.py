"""Pinned public routing/consent and post-Claude order; no network or services."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch, Mock

BASE=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
D=module('public_domain_test',BASE/'scripts/domain_setup.py')
UI=module('domain_order_ui',BASE/'scripts/interactive.py')
APP='a'*40;MAINTENANCE='b'*40
URL='https://'+'c'*24+'.ourgoal.win'


class CurrentMetadata(unittest.TestCase):
    def test_published_domain_metadata_matches_registered_immutable_release(self):
        value=D.metadata(UI.tools)
        catalogue=UI.metadata()
        self.assertEqual(set(value['supported_versions']),{'1.5.0','1.6.0','1.7.0'})
        for version, commit in value['supported_versions'].items():
            self.assertEqual(commit,catalogue['versions'][version]['commit'])
        self.assertEqual(value['commit'],value['supported_versions']['1.7.0'])
        self.assertNotEqual(value['commit'],value['supported_versions']['1.6.0'])
        self.assertNotEqual(value['commit'],value['supported_versions']['1.5.0'])
        self.assertEqual(set(value['files']),D.MODULES)


class PublicDomain(unittest.TestCase):
    def start(self,p):
        result=p.start();self.addCleanup(p.stop);return result

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'sources'/MAINTENANCE
        self.start(patch.object(D,'ROOT',self.root));self.start(patch.object(D,'SOURCES',self.root/'sources'))
        self.start(patch.object(D,'NATIVE',self.root/'state.json'))
        self.state=dict(schema=1,deployment_kind='isolated',authorized_new_vps=True,status='ready',phase='ready',branch='feature/CC',commit=APP,bind_host='127.0.0.1')
        D.NATIVE.write_text(json.dumps(self.state))
        self.bodies={name:b'# reviewed local fixture\n' for name in D.MODULES}
        self.bodies[D.ENTRY]=('def setup(commit,read,authorize_restart):\n'
                             ' if not authorize_restart:raise ValueError("authorization missing")\n'
                             ' return {"phase":"ready","url":'+repr(URL)+'}\n').encode()
        self.value=dict(schema=1,repository=D.REPO,branch='feature/CC',commit=MAINTENANCE,entrypoint=D.ENTRY,
                        files={name:hashlib.sha256(raw).hexdigest() for name,raw in self.bodies.items()},supported_versions={'1.5.0':APP})
        self.save()
        self.checker=types.SimpleNamespace(source=self.source,directory=Mock(),check_node=Mock())
        self.private=types.SimpleNamespace(PrivateSource=Mock(return_value=self.checker))
        self.tools=types.SimpleNamespace(require=UI.tools.require,diag=types.SimpleNamespace(begin=Mock()))
        def acquire(checker):
            self.assertIs(checker,self.checker)
            for name,raw in self.bodies.items():
                path=self.source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            return self.source
        self.acquire=Mock(side_effect=acquire)

    def save(self): (self.root/'domain-maintenance.json').write_text(json.dumps(self.value))

    def offer(self,answer='y',**kwargs):
        self.output=io.StringIO()
        with contextlib.redirect_stdout(self.output):
            return D.offer(self.tools,self.private,self.acquire,read=lambda _:answer,expected_commit=APP,**kwargs)

    def test_only_explicit_y_can_acquire_private_maintenance_code(self):
        for answer in ('n','N','','yes','invalid'):
            with self.subTest(answer=answer):self.assertIsNone(self.offer(answer))
        self.acquire.assert_not_called()
        self.assertEqual(self.offer('Y'),URL)
        self.acquire.assert_called_once()

    def test_eof_does_not_fetch_or_call_private_setup(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(D.consent(Mock(side_effect=EOFError())))

    def test_fixed_branch_sha_and_six_module_hashes_verified_before_import(self):
        self.assertEqual(self.offer(),URL)
        self.private.PrivateSource.assert_called_once_with(D.KEYS,self.source,D.REPO,'feature/CC',MAINTENANCE)
        self.assertEqual(self.checker.check_node.call_count,1+len(D.MODULES))
        self.assertIn('域名绑定成功',self.output.getvalue())

    def test_changed_entrypoint_or_helper_refused(self):
        for name in (D.ENTRY,'webdesktop-deploy/scripts/domain_install.py'):
            self.bodies[name]+=b'# unreviewed change'
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'DIGEST_MISMATCH'):self.offer()
            self.bodies[name]=self.bodies[name][:-len(b'# unreviewed change')]

    def test_metadata_rejects_arbitrary_repository_branch_entry_and_commit(self):
        for key,value in [('repository','git@github.com:other/repo.git'),('branch','main'),('entrypoint','../../evil.py'),('commit','b'*39),('commit','0'*40),('schema',True),('extra','unknown')]:
            original=copy.deepcopy(self.value);self.value[key]=value;self.save()
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'METADATA_INVALID'):self.offer()
            self.value=original
        self.acquire.assert_not_called()

    def test_metadata_requires_all_reviewed_helpers_and_full_hashes(self):
        for change in ('missing','extra','short-hash'):
            original=copy.deepcopy(self.value)
            if change=='missing':self.value['files'].pop(D.ENTRY)
            elif change=='extra':self.value['files']['../../evil.py']='a'*64
            else:self.value['files'][D.ENTRY]='a'*63
            self.save()
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'METADATA_INVALID'):self.offer()
            self.value=original
        self.acquire.assert_not_called()

    def test_wrong_or_incomplete_installation_stops_before_prompt_and_fetch(self):
        for change in ({'status':'failed'},{'commit':'d'*40},{'bind_host':'0.0.0.0'}):
            D.NATIVE.write_text(json.dumps(dict(self.state,**change)))
            with self.subTest(change=change),self.assertRaises(ValueError):self.offer()
        self.acquire.assert_not_called()

    def test_unsupported_old_release_is_skipped_without_changing_it(self):
        D.NATIVE.write_text(json.dumps(dict(self.state,commit='d'*40)))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(D.offer(self.tools,self.private,self.acquire,read=Mock(side_effect=AssertionError('must not prompt'))))
        self.acquire.assert_not_called()

    def test_nonready_or_unexpected_url_never_reported_as_success(self):
        for phase,url in [('pending-review',URL),('ready','https://evil.invalid')]:
            self.bodies[D.ENTRY]=('def setup(*args,**kwargs):return '+repr(dict(phase=phase,url=url))).encode()
            self.value['files'][D.ENTRY]=hashlib.sha256(self.bodies[D.ENTRY]).hexdigest();self.save()
            with self.subTest(phase=phase,url=url),self.assertRaisesRegex(ValueError,'DOMAIN_BIND_FAILED'):self.offer()
            self.assertNotIn('域名绑定成功',self.output.getvalue())


class InstallOrder(unittest.TestCase):
    def flow(self,claude_error=False,domain_error=False,launcher=False,launcher_error=False):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        entry=root/'webdesktop-deploy/scripts/interactive_deploy.py';entry.parent.mkdir(parents=True)
        entry.write_bytes(b'# fixture');(entry.parent/'private_repo.py').write_bytes(b'# helper')
        version=dict(version='1.6.0',engine='isolated',branch='feature/CC',commit=APP,
                     entrypoint='webdesktop-deploy/scripts/interactive_deploy.py',entrypoint_sha256=hashlib.sha256(b'# fixture').hexdigest())
        catalogue=dict(default_version='1.6.0',versions={'1.6.0':version},source_helper_sha256=hashlib.sha256(b'# helper').hexdigest())
        events=[];source=Mock();source.source=root
        coordinator=types.SimpleNamespace(deploy=lambda *args:events.append('desktop'))
        if launcher:
            coordinator.CLAUDE_DESKTOP_SUPPORT=1
            def register(*args):
                events.append('launcher')
                if launcher_error:raise ValueError('CLAUDE_REGISTRATION_CONFLICT')
            coordinator.register_claude=register
        def claude(*args):
            events.append('claude')
            if claude_error:raise ValueError('CLAUDE_PACKAGE_NOT_INSTALLED')
        def domain(*args):
            events.append('domain')
            if domain_error:raise ValueError('DOMAIN_CONNECT_TIMEOUT')
            return URL
        def load(name,path):return coordinator if name=='approved_private_deployment' else types.SimpleNamespace(install=claude)
        args=types.SimpleNamespace(mode='local-test')
        with patch.object(UI.tools,'initial'),patch.object(UI.tools.diag,'append'), \
             patch.object(UI.private,'PrivateSource',return_value=source),patch.object(UI,'authorize_source',return_value=True), \
             patch.object(UI,'latest_catalogue',side_effect=lambda value:value), \
             patch.object(UI,'available_versions',return_value=catalogue),patch.object(UI,'select_version',return_value=version), \
             patch.object(UI,'acquire',return_value=root),patch.object(UI,'load',side_effect=load), \
             patch.object(UI,'post_install_domain',side_effect=domain), \
             patch.object(UI,'display_credentials',side_effect=lambda *args:events.append('credentials')), \
             contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            if claude_error or domain_error or launcher_error:
                with self.assertRaises(ValueError):UI.flow(args,catalogue)
            else:UI.flow(args,catalogue)
        return events

    def test_binding_prompt_follows_successful_desktop_and_claude(self):
        self.assertEqual(self.flow(),['desktop','claude','domain','credentials'])

    def test_claude_failure_does_not_begin_binding(self):
        self.assertEqual(self.flow(claude_error=True),['desktop','claude','credentials'])

    def test_supported_release_registers_launcher_after_package_and_before_binding(self):
        self.assertEqual(self.flow(launcher=True),['desktop','claude','launcher','domain','credentials'])

    def test_launcher_failure_preserves_desktop_and_credentials_without_binding(self):
        self.assertEqual(self.flow(launcher=True,launcher_error=True),['desktop','claude','launcher','credentials'])

    def test_domain_failure_keeps_access_to_initial_credentials(self):
        self.assertEqual(self.flow(domain_error=True),['desktop','claude','domain','credentials'])

    def test_existing_domain_handoff_does_not_trigger_second_prompt(self):
        args=types.SimpleNamespace(domain_url=URL)
        with patch.object(UI,'load') as load:self.assertEqual(UI.post_install_domain(args),URL)
        load.assert_not_called()

    def test_dedicated_retry_action_does_not_run_fresh_install(self):
        with patch.object(UI.private,'require_platform'),patch.object(UI,'verify_checkout',return_value=MAINTENANCE), \
             patch.object(UI,'metadata',return_value={}),patch.object(UI,'reuse_installation',return_value=True), \
             patch.object(UI,'post_install_domain',return_value=URL) as domain,patch.object(UI,'display_credentials') as display, \
             patch.object(UI,'flow') as flow,patch.object(UI.tools,'initial') as initial,contextlib.redirect_stdout(io.StringIO()):
            UI.main(['domain','--mode','local-test','--ack-local-test-trust','--authorize-install','--authorize-isolated-egress'])
        domain.assert_called_once();display.assert_called_once();flow.assert_not_called();initial.assert_not_called()


if __name__=='__main__':unittest.main()
