"""Local version routing, real offline Git handoff; Linux identities are modeled.

No SSH, GitHub, APT, actual users or services are used by these tests.
"""
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
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
ui=module('version_ui',ROOT/'scripts/interactive.py')
beta=module('version_beta',ROOT/'scripts/beta_install.py')


class Versions(unittest.TestCase):
    def test_catalogue_has_reviewed_fixed_versions(self):
        m=ui.metadata()
        self.assertEqual(set(m['versions']),{'1.8.1','1.8.0','1.7.0','1.6.0','1.5.0','1.4.0','1.3.0','1.2.0','1.1.0','1.0.0','beta0.1.0'})
        self.assertEqual(m['default_version'],'1.8.1')
        self.assertEqual(m['versions']['1.8.1']['commit'],'f0ce19000cd3482b51f1093b36586a5d5fa9374f')
        self.assertEqual(m['versions']['1.8.1']['tag'],'v1.8.1')
        self.assertEqual(m['versions']['1.8.0']['commit'],'c1fe5497577049b9fa1b69fa9de7094f62cadd67')
        self.assertEqual(m['versions']['1.8.0']['tag'],'v1.8.0')
        self.assertEqual(m['versions']['1.7.0']['commit'],'f0c5ab044775a7060b563c0e055e484f165b2eb4')
        self.assertEqual(m['versions']['1.7.0']['tag'],'v1.7.0')
        self.assertEqual(m['versions']['1.6.0']['commit'],'9f1bc9329aba6e89b1301a74fcd0d99cf00ef3d0')
        self.assertEqual(m['versions']['1.6.0']['tag'],'v1.6.0')
        self.assertEqual(m['versions']['1.5.0']['commit'],'1fce41f13dd3b556384e58e35ff8efb1e08b0582')
        self.assertEqual(m['versions']['1.5.0']['tag'],'v1.5.0')
        self.assertEqual(m['versions']['1.4.0']['commit'],'a31c680f4e85111a161466941a838409fff9036e')
        self.assertEqual(m['versions']['1.4.0']['tag'],'v1.4.0')
        self.assertEqual(m['versions']['1.3.0']['commit'],'ead5e46cba31d50e0be53738c4d855581c1c674e')
        self.assertEqual(m['versions']['1.3.0']['tag'],'v1.3.0')
        self.assertEqual(m['versions']['1.2.0']['commit'],'cb280d280d35212b23bd823e8f64727f6811d9c6')
        self.assertEqual(m['versions']['1.2.0']['tag'],'v1.2.0')
        self.assertEqual(m['versions']['1.1.0']['commit'],'07f9adf18e133534e02ce9d9500af45dc8afb90b')
        self.assertEqual(m['versions']['1.1.0']['tag'],'v1.1.0')
        self.assertEqual(m['versions']['1.0.0']['commit'],'73e544e32b67bee2ac17cca7f21b7cf5692d0482')
        self.assertEqual(m['versions']['beta0.1.0']['commit'],'5922e1408de91e56771f1ea0bf94a9df1b7028cd')
        self.assertEqual(hashlib.sha256((ROOT/'scripts/private_repo.py').read_bytes()).hexdigest(),m['source_helper_sha256'])

    def test_selection_is_exact_and_invalid_input_does_not_execute(self):
        answers=iter(['latest','1.0','$(id)','../main','beta0.1.0'])
        with contextlib.redirect_stdout(io.StringIO()):
            selected=ui.select_version(ui.metadata(),read=lambda _:next(answers))
        self.assertEqual((selected['engine'],selected['branch']),('legacy-beta','main'))
        with contextlib.redirect_stdout(io.StringIO()):
            for version in ('1.8.1','1.8.0','1.7.0','1.6.0','1.5.0','1.4.0','1.3.0','1.2.0','1.1.0','1.0.0','beta0.1.0'):
                self.assertEqual(ui.select_version(ui.metadata(),version)['version'],version)
            with self.assertRaisesRegex(ValueError,'UNKNOWN_INSTALL_VERSION'):
                ui.select_version(ui.metadata(),'latest')

    def test_empty_or_eof_selects_nothing(self):
        def eof(_):raise EOFError()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(ui.select_version(ui.metadata(),read=lambda _:''))
            self.assertIsNone(ui.select_version(ui.metadata(),read=eof))

    def test_metadata_rejects_branch_engine_path_sha_and_unknown_fields(self):
        for field,value in [('branch','main'),('engine','legacy-beta'),('entrypoint','../../bad.py'),
                            ('commit','a'*39),('entrypoint_sha256','0'*63),('unknown','x')]:
            data=ui.metadata();data['versions']['1.0.0'][field]=value
            with self.subTest(field=field),mock.patch.object(Path,'read_text',return_value=json.dumps(data)):
                with self.assertRaises(ValueError):ui.metadata()

    def live_catalogue(self,raw):
        source=mock.Mock()
        source.locked.return_value=contextlib.nullcontext()
        source.git.return_value=raw
        with contextlib.redirect_stdout(io.StringIO()):result=ui.available_versions(ui.metadata(),source)
        source.verify_local.assert_called_once()
        source.git.assert_called_once_with('ls-remote','--tags',ui.REPO)
        source.clone.assert_not_called()
        return result

    def tag_rows(self):
        return '\n'.join(item['commit']+'\trefs/tags/'+item['tag'] for item in ui.metadata()['versions'].values())

    def test_live_scan_keeps_only_registered_tags_and_never_adopts_an_unknown_version(self):
        result=self.live_catalogue(self.tag_rows()+'\n'+'a'*40+'\trefs/tags/v99.0.0')
        self.assertEqual(result,ui.metadata())
        self.assertNotIn('99.0.0',result['versions'])

    def test_live_scan_checks_annotated_tag_peeled_commit(self):
        current=ui.metadata()['versions']['1.2.0']['commit']
        rows=self.tag_rows().replace(current+'\trefs/tags/v1.2.0','a'*40+'\trefs/tags/v1.2.0')
        result=self.live_catalogue(rows+'\n'+current+'\trefs/tags/v1.2.0^{}')
        self.assertEqual(result['versions']['1.2.0']['commit'],current)

    def test_unpublished_tag_is_not_offered_for_installation(self):
        for missing,default in [('1.8.1','1.8.0'),('1.8.0','1.8.1'),('1.7.0','1.8.1'),('1.6.0','1.8.1'),('1.5.0','1.8.1')]:
            rows='\n'.join(row for row in self.tag_rows().splitlines() if not row.endswith('/v'+missing))
            result=self.live_catalogue(rows)
            self.assertNotIn(missing,result['versions']);self.assertEqual(result['default_version'],default)

    def test_moved_registered_tag_refuses_instead_of_using_latest_head(self):
        current=ui.metadata()['versions']['1.2.0']['commit']
        with self.assertRaisesRegex(ValueError,'PUBLISHED_VERSION_TAG_MISMATCH'):
            self.live_catalogue(self.tag_rows().replace(current,'a'*40))

    def test_invalid_duplicate_oversized_or_orphan_peeled_listing_is_rejected(self):
        current=ui.metadata()['versions']['1.2.0']['commit']
        for raw in ('bad listing',self.tag_rows()+'\n'+self.tag_rows().splitlines()[0],
                    'x'*(2*1024**2+1),current+'\trefs/tags/v1.2.0^{}'):
            with self.subTest(length=len(raw)),self.assertRaises(ValueError):self.live_catalogue(raw)

    def test_empty_or_only_unknown_remote_tags_cannot_start_installation(self):
        for raw in ('','a'*40+'\trefs/tags/v99.0.0'):
            with self.assertRaisesRegex(ValueError,'NO_APPROVED_PUBLISHED_VERSIONS'):self.live_catalogue(raw)

    def route(self,version='1.0.0',wrong_hash=False,mode='local-test',answer=True,domain=False,capability=0):
        temp=tempfile.TemporaryDirectory(prefix='version-route-');self.addCleanup(temp.cleanup)
        root=Path(temp.name);key=root/'deploy_key';key.write_text('fixture marker')
        catalogue=ui.metadata()
        events=[];instances=[]
        class Source:
            def __init__(self,keys,source,repo,branch,commit):
                self.key=key;self.source=Path(source);self.branch=branch;self.commit=commit;instances.append(self)
            @contextlib.contextmanager
            def locked(self):yield
            def verify_local(self):events.append('identity')
            def authorized(self):events.append('authorized')
            def git(self,*args):
                events.append('live-tags')
                return '\n'.join(item['commit']+'\trefs/tags/'+item['tag'] for item in catalogue['versions'].values())
            def check_node(self,path):pass
        def acquire(source):
            events.append(('acquire',source.branch,source.commit))
            checkout=root/source.commit;checkout.mkdir()
            spec=catalogue['versions'][version]
            path=checkout/spec['entrypoint'];path.parent.mkdir(parents=True);path.write_bytes(b'# approved entrypoint')
            if spec['engine']=='isolated':(path.parent/'private_repo.py').write_bytes(b'# approved helper')
            source.source=checkout
            return checkout
        for name,spec in catalogue['versions'].items():
            spec['entrypoint_sha256']=hashlib.sha256(b'# approved entrypoint').hexdigest()
        catalogue['source_helper_sha256']=hashlib.sha256(b'# approved helper').hexdigest()
        if wrong_hash:catalogue['versions'][version]['entrypoint_sha256']='0'*64
        selected=[]
        def read(prompt):
            events.append('version-prompt')
            return version if answer else ''
        args=types.SimpleNamespace(mode=mode,version=None,authorize_install=True,authorize_isolated_egress=True,ack_local_test_trust=True)
        coordinator=mock.Mock()
        coordinator.DOMAIN_SUPPORT=capability
        if domain:args.domain_config=Path('root-only-domain-fixture')
        def load(name,path):selected.append((name,Path(path)));return coordinator
        with mock.patch.object(ui,'KEYS',root/'keys'),mock.patch.object(ui,'SOURCES',root/'sources'), \
             mock.patch.object(ui.tools,'initial'),mock.patch.object(ui.tools.diag,'begin'), \
             mock.patch.object(ui,'latest_catalogue',side_effect=lambda value:(events.append('latest-catalogue') or value)), \
             mock.patch.object(ui.private,'PrivateSource',Source),mock.patch.object(ui,'acquire',side_effect=acquire) as fetch, \
             mock.patch.object(ui,'load',side_effect=load),mock.patch.object(ui,'display_credentials'),contextlib.redirect_stdout(io.StringIO()):
            result=ui.flow(args,catalogue,read)
        return result,events,selected,coordinator,args,fetch

    def test_release_version_routes_to_existing_private_coordinator(self):
        result,events,selected,coordinator,args,_=self.route()
        self.assertTrue(result)
        self.assertEqual(selected[0][0],'approved_private_deployment')
        self.assertEqual(args.version,'1.0.0')
        coordinator.deploy.assert_called_once_with(args,ui.tools)
        self.assertLess(events.index('authorized'),events.index('version-prompt'))
        self.assertLess(events.index('authorized'),events.index('live-tags'))
        self.assertLess(events.index('authorized'),events.index('latest-catalogue'))
        self.assertLess(events.index('latest-catalogue'),events.index('live-tags'))
        self.assertLess(events.index('live-tags'),events.index('version-prompt'))

    def test_domain_handoff_requires_explicit_new_private_capability(self):
        with self.assertRaisesRegex(ValueError,'DOMAIN_CAPABLE_RELEASE_REQUIRED'):self.route(domain=True)
        result,_,_,coordinator,args,_=self.route(domain=True,capability=1)
        self.assertTrue(result);self.assertEqual(args.domain_config,Path('root-only-domain-fixture'))
        coordinator.deploy.assert_called_once_with(args,ui.tools)

    def test_beta_domain_handoff_is_rejected_without_changing_beta(self):
        with self.assertRaisesRegex(ValueError,'DOMAIN_BETA_NOT_SUPPORTED'):self.route('beta0.1.0',domain=True,capability=1)

    def test_1_1_0_routes_to_reviewed_new_commit(self):
        result,events,selected,coordinator,args,_=self.route('1.1.0')
        self.assertTrue(result)
        self.assertEqual(args.version,'1.1.0')
        self.assertIn(('acquire','feature/CC','07f9adf18e133534e02ce9d9500af45dc8afb90b'),events)
        self.assertEqual(selected[0][0],'approved_private_deployment')
        coordinator.deploy.assert_called_once_with(args,ui.tools)

    def test_1_2_0_routes_to_reviewed_source_update_release(self):
        result,events,selected,coordinator,args,_=self.route('1.2.0')
        self.assertTrue(result)
        self.assertEqual(args.version,'1.2.0')
        self.assertIn(('acquire','feature/CC','cb280d280d35212b23bd823e8f64727f6811d9c6'),events)
        self.assertEqual(selected[0][0],'approved_private_deployment')
        coordinator.deploy.assert_called_once_with(args,ui.tools)

    def test_beta_routes_to_adapter_and_main_fixed_commit(self):
        result,events,selected,coordinator,args,_=self.route('beta0.1.0')
        self.assertTrue(result)
        self.assertEqual(selected,[('public_beta_install',ROOT/'scripts/beta_install.py')])
        self.assertIn(('acquire','main','5922e1408de91e56771f1ea0bf94a9df1b7028cd'),events)
        coordinator.deploy.assert_called_once()
        self.assertEqual(args.version,'beta0.1.0')

    def test_beta_cannot_pretend_to_use_formal_cc_signature_pipeline(self):
        with self.assertRaisesRegex(ValueError,'EXPLICIT_LEGACY_MODE'):self.route('beta0.1.0',mode='formal')

    def test_wrong_entrypoint_hash_stops_both_engines(self):
        for version in ('1.3.0','1.2.0','1.1.0','1.0.0','beta0.1.0'):
            with self.subTest(version=version),self.assertRaisesRegex(ValueError,'DIGEST_MISMATCH'):self.route(version,wrong_hash=True)

    def test_cancel_selection_never_loads_or_acquires_source(self):
        result,_,selected,coordinator,_,fetch=self.route(answer=False)
        self.assertFalse(result);self.assertEqual(selected,[]);fetch.assert_not_called();coordinator.deploy.assert_not_called()

    def test_short_entrypoint_keeps_clean_environment_and_explicit_flags(self):
        text=(ROOT/'install.sh').read_text()
        for token in ('exec env -i','PATH=/usr/sbin:/usr/bin:/sbin:/bin','GIT_CONFIG_GLOBAL=/dev/null',
                      '--mode local-test','--ack-local-test-trust','--authorize-install','--authorize-isolated-egress'):
            self.assertIn(token,text)
        self.assertNotIn('curl',text)


class LatestCatalogue(unittest.TestCase):
    """Real metadata/parser/selection path; HTTPS and SSH transport are modeled."""
    def setUp(self):
        self.baseline=ui.metadata()
        self.new=json.loads(json.dumps(self.baseline))
        item=dict(self.new['versions']['1.8.0'],commit='d'*40,tag='v1.9.0',entrypoint_sha256='e'*64)
        self.new['versions']['1.9.0']=item
        self.new['default_version']='1.9.0'

    def refresh(self,value=None,raw=None,status=200,url=None,error=None):
        response=io.BytesIO(raw if raw is not None else json.dumps(value if value is not None else self.new).encode())
        response.status=status;response.geturl=lambda:url or ui.CATALOGUE_URL
        response.read=mock.Mock(wraps=response.read)
        opener=mock.Mock()
        if error:opener.open.side_effect=error
        else:opener.open.return_value=response
        self.output=io.StringIO()
        with mock.patch.object(ui.urllib.request,'build_opener',return_value=opener) as build,contextlib.redirect_stdout(self.output):
            result=ui.latest_catalogue(self.baseline)
        self.opener=opener;self.build=build;self.reader=response.read
        return result

    def test_latest_registered_version_appears_without_updating_local_metadata(self):
        value=self.refresh()
        self.assertNotIn('1.9.0',self.baseline['versions'])
        source=types.SimpleNamespace(locked=contextlib.nullcontext,verify_local=lambda:None,
            git=lambda *args:'\n'.join(item['commit']+'\trefs/tags/'+item['tag'] for item in value['versions'].values()))
        with contextlib.redirect_stdout(io.StringIO()) as output:
            available=ui.available_versions(value,source)
            selected=ui.select_version(available,read=lambda _:'1.9.0')
        self.assertEqual(selected['commit'],'d'*40)
        self.assertEqual(selected['entrypoint_sha256'],'e'*64)
        self.assertIn('可安装版本：1.9.0, 1.8.1, 1.8.0, 1.7.0, 1.6.0',output.getvalue())
        self.assertNotIn('1.9.0',ui.metadata()['versions'])

    def test_authorized_flow_refreshes_then_reprompts_and_installs_new_fixed_version(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        checkout=Path(temp.name)/('d'*40);events=[]
        entry=b'# approved new-version fixture'
        helper=(ROOT/'scripts/private_repo.py').read_bytes()
        self.new['versions']['1.9.0']['entrypoint_sha256']=hashlib.sha256(entry).hexdigest()
        response=io.BytesIO(json.dumps(self.new).encode());response.status=200;response.geturl=lambda:ui.CATALOGUE_URL
        opener=mock.Mock();opener.open.side_effect=lambda *a,**kw:(events.append('catalogue') or response)
        def tags(*args):
            events.append('tags')
            return '\n'.join(item['commit']+'\trefs/tags/'+item['tag'] for item in self.new['versions'].values())
        source=types.SimpleNamespace(source=checkout,key=Path(temp.name)/'key',check_node=mock.Mock(),
            locked=contextlib.nullcontext,verify_local=lambda:None,git=tags)
        def acquire(value):
            events.append('acquire');self.assertIs(value,source)
            path=checkout/'webdesktop-deploy/scripts';path.mkdir(parents=True)
            (path/'interactive_deploy.py').write_bytes(entry);(path/'private_repo.py').write_bytes(helper)
            return checkout
        answers=iter(['1.99.0','1.9.0'])
        def read(prompt):
            self.assertNotIn('acquire',events)
            answer=next(answers);events.append(answer);return answer
        args=types.SimpleNamespace(mode='local-test',version=None)
        coordinator=mock.Mock()
        with mock.patch.object(ui.tools,'initial'),mock.patch.object(ui.tools.diag,'begin'), \
             mock.patch.object(ui.private,'PrivateSource',return_value=source), \
             mock.patch.object(ui,'authorize_source',side_effect=lambda *a:(events.append('authorized') or True)), \
             mock.patch.object(ui.urllib.request,'build_opener',return_value=opener), \
             mock.patch.object(ui,'acquire',side_effect=acquire),mock.patch.object(ui,'load',return_value=coordinator), \
             mock.patch.object(ui,'post_install_domain'),mock.patch.object(ui,'display_credentials'), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertTrue(ui.flow(args,self.baseline,read))
        self.assertEqual(events,['authorized','catalogue','tags','1.99.0','1.9.0','acquire'])
        self.assertEqual(args.version,'1.9.0');self.assertEqual(args.commit,'d'*40)
        coordinator.deploy.assert_called_once_with(args,ui.tools)
        self.assertIn('该版本不可用',output.getvalue())

    def test_fixed_https_url_timeout_no_proxy_or_credentials_and_bounded_read(self):
        self.refresh()
        args,kwargs=self.opener.open.call_args
        request=args[0]
        self.assertEqual(request.full_url,ui.CATALOGUE_URL)
        self.assertEqual(kwargs,{'timeout':20})
        self.assertEqual(self.build.call_args[0][0].proxies,{})
        self.assertIsInstance(self.build.call_args[0][1],ui.NoCatalogueRedirect)
        self.assertNotIn('Authorization',request.headers)
        self.assertNotIn('Cookie',request.headers)
        self.reader.assert_called_once_with(65537)

    def test_each_run_refreshes_instead_of_using_stale_local_catalogue(self):
        self.assertNotIn('1.9.0',self.refresh(self.baseline)['versions'])
        self.assertIn('1.9.0',self.refresh()['versions'])

    def test_changed_existing_version_entry_is_rejected(self):
        for field,value in [('commit','f'*40),('entrypoint_sha256','f'*64)]:
            changed=json.loads(json.dumps(self.new));changed['versions']['1.6.0'][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'PUBLISHED_VERSION_TAG_MISMATCH'):
                self.refresh(changed)

    def test_changed_authorization_protocol_requires_reviewed_bootstrap_update(self):
        self.new['source_helper_sha256']='f'*64
        with self.assertRaisesRegex(ValueError,'PINNED_SOURCE_MODULE_DIGEST_MISMATCH'):self.refresh()

    def test_publisher_withdrawn_version_is_not_restored_from_local_list(self):
        del self.new['versions']['1.0.0']
        self.assertNotIn('1.0.0',self.refresh()['versions'])

    def test_http_failures_and_redirects_do_not_fall_back_or_leak_error_text(self):
        for options in ({'status':403},{'status':302},{'url':'https://other.invalid/release.json'},
                        {'error':TimeoutError('fixture-sensitive-token')},{'error':OSError('fixture-sensitive-token')}):
            with self.subTest(options=options),self.assertRaisesRegex(ValueError,'^NETWORK$'):self.refresh(**options)
            self.assertNotIn('fixture-sensitive-token',self.output.getvalue())
            self.assertIn('本次停止',self.output.getvalue())

    def test_redirect_handler_refuses_before_following_a_location(self):
        with self.assertRaisesRegex(ValueError,'NETWORK'):
            ui.NoCatalogueRedirect().redirect_request(None,None,None,None,None,None)

    def test_oversize_response_stops_before_json_parsing(self):
        with self.assertRaisesRegex(ValueError,'VERSION_TAG_LIST_TOO_LARGE'):self.refresh(raw=b' '*65537)

    def test_invalid_json_and_duplicate_root_or_nested_keys_are_rejected(self):
        for raw in (b'{',b'\xff',b'{"schema":2,"schema":2}',b'{"versions":{"1.0.0":{},"1.0.0":{}}}'):
            with self.subTest(raw=raw),self.assertRaisesRegex(ValueError,'VERSION_TAG_LIST_INVALID'):self.refresh(raw=raw)

    def test_closed_schema_and_field_types_are_checked(self):
        for key,value in [('schema',True),('schema',3),('versions',[]),('versions',{}),('default_version',[]),
                          ('source_helper_sha256',[]),('extra','unknown')]:
            changed=json.loads(json.dumps(self.new));changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.refresh(changed)
        for raw in (b'[]',b'null',b'false',b'1',b'"string"'):
            with self.subTest(raw=raw),self.assertRaisesRegex(ValueError,'RELEASE_METADATA_FIELDS'):self.refresh(raw=raw)

    def test_repository_branch_path_tag_and_digest_cannot_be_arbitrary(self):
        for field,value in [('branch','main'),('entrypoint','../../code.py'),('commit','d'*39),
                            ('tag','v1.9.1'),('tag',123),('engine','legacy-beta'),('entrypoint_sha256','e'*63)]:
            changed=json.loads(json.dumps(self.new));changed['versions']['1.9.0'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.refresh(changed)
        self.new['repository']='git@github.com:other/private.git'
        with self.assertRaises(ValueError):self.refresh()

    def test_version_count_is_bounded(self):
        for minor in range(200):
            self.new['versions']['2.'+str(minor)+'.0']=dict(self.new['versions']['1.9.0'],tag='v2.'+str(minor)+'.0')
        with self.assertRaisesRegex(ValueError,'APPROVED_METADATA_REQUIRED'):ui.metadata(self.new)

    def test_versions_are_sorted_numerically_with_beta_after_stable(self):
        for version in ('1.10.0','1.11.0'):
            self.new['versions'][version]=dict(self.new['versions']['1.9.0'],tag='v'+version)
        source=types.SimpleNamespace(locked=contextlib.nullcontext,verify_local=lambda:None,
            git=lambda *args:'\n'.join(item['commit']+'\trefs/tags/'+item['tag'] for item in self.new['versions'].values()))
        with contextlib.redirect_stdout(io.StringIO()):value=ui.available_versions(self.new,source)
        names=list(value['versions'])
        self.assertEqual(names[:3],['1.11.0','1.10.0','1.9.0'])
        self.assertEqual(names[-1],'beta0.1.0')

    def test_unavailable_input_reprompts_until_an_exact_listed_version(self):
        answers=iter(['1.99.0','latest','../1.6.0','1.6.0'])
        with contextlib.redirect_stdout(io.StringIO()) as output:
            selected=ui.select_version(self.baseline,read=lambda _:next(answers))
        self.assertEqual(selected['version'],'1.6.0')
        self.assertEqual(output.getvalue().count('该版本不可用'),3)

    def test_no_catalogue_request_before_github_consent_or_when_install_already_complete(self):
        args=types.SimpleNamespace(mode='local-test')
        with mock.patch.object(ui.tools,'initial'),mock.patch.object(ui.tools.diag,'begin'), \
             mock.patch.object(ui.private,'PrivateSource'),mock.patch.object(ui,'authorize_source',return_value=False), \
             mock.patch.object(ui,'latest_catalogue') as refresh,contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(ui.flow(args,self.baseline))
        refresh.assert_not_called()
        with mock.patch.object(ui.private,'require_platform'),mock.patch.object(ui,'verify_checkout',return_value='a'*40), \
             mock.patch.object(ui,'reuse_installation',return_value=True),mock.patch.object(ui,'latest_catalogue') as refresh, \
             contextlib.redirect_stdout(io.StringIO()):
            ui.main(['--mode','local-test','--ack-local-test-trust','--authorize-install','--authorize-isolated-egress'])
        refresh.assert_not_called()


class BetaHandoff(unittest.TestCase):
    def fixture(self,existing=False,fail_installer=False,dirty=False):
        temp=tempfile.TemporaryDirectory(prefix='beta-offline-');self.addCleanup(temp.cleanup)
        root=Path(temp.name);source_root=root/'approved';source_root.mkdir()
        env=dict(os.environ,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_SYSTEM=os.devnull,GIT_TERMINAL_PROMPT='0',GIT_ALLOW_PROTOCOL='file')
        def git(*argv):
            return subprocess.check_output(['git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',*map(str,argv)],env=env,stderr=subprocess.PIPE).decode().strip()
        git('init','--quiet',source_root)
        (source_root/'package.json').write_text('{}\n')
        script=source_root/'webdesktop-deploy/install.sh';script.parent.mkdir();script.write_text('# no actual installer execution\n')
        git('-C',source_root,'add','.')
        git('-C',source_root,'-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture')
        sha=git('-C',source_root,'rev-parse','HEAD')
        home=root/'home';app=home/'webdesktop';state=root/'state'
        if existing:state.mkdir();(state/'state.json').write_text('preserve failure evidence')
        class Source:
            source=source_root;commit=sha;branch='main'
            def existing(self):return dict(dirty=dirty,commit=sha)
            def directory(self,path,**kwargs):pass  # Linux ownership/modes NOT RUN.
            def check_node(self,path,**kwargs):pass  # Linux ownership/modes NOT RUN.
            def write_new(self,path,text):
                with path.open('x',encoding='utf-8') as f:f.write(text)
            def git(self,*args):return git(*args)
        calls=[]
        def run(argv,**kwargs):
            calls.append(list(map(str,argv)))
            if str(argv[0])=='/usr/sbin/useradd':home.mkdir();return ''
            if str(argv[0])=='/usr/bin/git':return git(*argv[1:])
            if str(argv[0])=='/bin/bash':
                if fail_installer:raise ui.tools.diag.Failure('SUBPROCESS_FAILED',exit_code=127,tool='bash')
                return ''  # Original Beta APT/build/service execution is NOT RUN.
            raise AssertionError('Unexpected tool')
        tools=types.SimpleNamespace(require=ui.tools.require,run=run,diag=types.SimpleNamespace(begin=lambda _:None))
        args=types.SimpleNamespace(authorize_install=True,authorize_isolated_egress=True,mode='local-test',
                                   ack_local_test_trust=True,commit=sha,source_dir=source_root,version='beta0.1.0')
        original=Path.lstat
        def lstat(path,*a,**kw):
            value=original(path,*a,**kw)
            if path==home:return types.SimpleNamespace(st_mode=stat.S_IFDIR|0o755,st_uid=1001)
            return value
        with mock.patch.object(beta,'STATE',state),mock.patch.object(beta,'HOME',home),mock.patch.object(beta,'APP',app), \
             mock.patch.object(beta,'unused_identity'),mock.patch.object(beta,'runtime_identity',return_value=types.SimpleNamespace(pw_uid=1001,pw_gid=1001)), \
             mock.patch.object(beta,'own_checkout') as own,mock.patch.object(Path,'lstat',lstat), \
             mock.patch.object(beta.shutil,'disk_usage',return_value=types.SimpleNamespace(free=20*1024**3)), \
             contextlib.redirect_stdout(io.StringIO()):
            if existing or fail_installer or dirty:
                with self.assertRaises((ValueError,ui.tools.diag.Failure)):beta.deploy(args,tools,ui.private,Source())
            else:beta.deploy(args,tools,ui.private,Source())
        return root,state,app,calls,args,own

    def test_real_bundle_clone_has_exact_sha_and_no_ssh_credentials(self):
        root,state,app,calls,args,own=self.fixture()
        summary=json.loads((state/'state.json').read_text())
        self.assertEqual((summary['phase'],summary['version']),('ready','beta0.1.0'))
        config=(app/'.git/config').read_text()
        self.assertIn('https://github.com/isAliceYoung/fa.git',config)
        for forbidden in ('IdentityFile','deploy_key','GIT_SSH_COMMAND'):self.assertNotIn(forbidden,config)
        installer=[c for c in calls if c[0]=='/bin/bash'][0]
        self.assertEqual(installer[-1],'install');self.assertIn(args.commit,installer)
        self.assertEqual(installer[installer.index('--install-dir')+1],str(app))
        own.assert_called_once()

    def test_existing_failure_journal_is_never_overwritten(self):
        root,state,app,calls,_,_=self.fixture(existing=True)
        self.assertEqual((state/'state.json').read_text(),'preserve failure evidence')
        self.assertEqual(calls,[]);self.assertFalse(app.exists())

    def test_installer_failure_retains_journal_checkout_and_bundle(self):
        _,state,app,calls,_,_=self.fixture(fail_installer=True)
        self.assertEqual(json.loads((state/'state.json').read_text())['phase'],'installing')
        self.assertTrue((app/'.git').is_dir());self.assertTrue((state/'source.bundle').is_file())

    def test_dirty_source_never_creates_install_state(self):
        _,state,_,calls,_,_=self.fixture(dirty=True)
        self.assertFalse(state.exists());self.assertEqual(calls,[])

    def test_existing_runtime_account_or_group_is_not_adopted(self):
        fake=types.SimpleNamespace(getpwnam=lambda _:object(),getgrnam=lambda _:object())
        with mock.patch.dict('sys.modules',{'pwd':fake,'grp':fake}):
            with self.assertRaisesRegex(ValueError,'EXISTING_PROJECT_IDENTITY'):beta.unused_identity(ui.tools.require)

    def test_runtime_identity_rejects_wrong_home_and_extra_groups(self):
        account=types.SimpleNamespace(pw_uid=1001,pw_gid=1001,pw_dir=str(beta.HOME),pw_shell='/bin/bash')
        fake=types.SimpleNamespace(getpwnam=lambda _:account,getgrnam=lambda _:types.SimpleNamespace(gr_gid=1001))
        with mock.patch.dict('sys.modules',{'pwd':fake,'grp':fake}),mock.patch.object(os,'getgrouplist',return_value=[1001],create=True):
            self.assertIs(beta.runtime_identity(ui.tools.require),account)
            account.pw_dir='/root'
            with self.assertRaises(ValueError):beta.runtime_identity(ui.tools.require)
            account.pw_dir=str(beta.HOME)
            with mock.patch.object(os,'getgrouplist',return_value=[1001,27]):
                with self.assertRaises(ValueError):beta.runtime_identity(ui.tools.require)

    def test_checkout_scan_rejects_unsafe_objects_before_any_chown(self):
        with tempfile.TemporaryDirectory(prefix='beta-mode-model-') as temp:
            app=Path(temp);child=app/'payload';child.write_text('unchanged')
            account=types.SimpleNamespace(pw_uid=1001,pw_gid=1001)
            original=Path.lstat
            for bad in ('mode','owner','symlink','hardlink','special'):
                def lstat(path,*args,**kw):
                    meta=original(path,*args,**kw)
                    mode=stat.S_IFDIR|0o755 if path==app else stat.S_IFREG|0o644
                    uid=0;nlink=1
                    if path==child:
                        if bad=='mode':mode=stat.S_IFREG|0o666
                        if bad=='owner':uid=1001
                        if bad=='symlink':mode=stat.S_IFLNK|0o777
                        if bad=='hardlink':nlink=2
                        if bad=='special':mode=stat.S_IFIFO|0o600
                    return types.SimpleNamespace(st_mode=mode,st_uid=uid,st_nlink=nlink)
                with self.subTest(bad=bad),mock.patch.object(Path,'lstat',lstat), \
                     mock.patch.object(os,'chown',create=True) as chown:
                    with self.assertRaisesRegex(ValueError,'UNSAFE_BETA_CHECKOUT'):
                        beta.own_checkout(app,account,ui.tools.require)
                    chown.assert_not_called()
            self.assertEqual(child.read_text(),'unchanged')


if __name__=='__main__':unittest.main(verbosity=2)
