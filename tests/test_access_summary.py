"""Labeled initial access details, protected file reads and terminal-only secrets. No real credentials/services."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import types
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('access_summary_ui',ROOT/'scripts/interactive.py')
UI=importlib.util.module_from_spec(spec);spec.loader.exec_module(UI)
CREDS={'DESKTOP_PASSWORD':'desktop-fixture-password','ADMIN_USER':'admin','ADMIN_PASSWORD':'admin-fixture-password',
       'ADMIN_PATH':'ops-fixture','DATABASE_URL':'never-show-extra-secret'}
DESKTOP='https://desktop.example.com';CLAUDE='https://desktop-claude.example.com'
ENTRY={'port':3001,'url':CLAUDE}


class AccessSummary(unittest.TestCase):
    def test_bound_origins_and_both_ssh_passwords_are_labeled_and_admin_is_separate(self):
        text=UI.credential_summary(CREDS,DESKTOP,ENTRY)
        user,admin=text.split('以下管理信息仅由管理员保留，请勿发给用户：')
        self.assertIn('WebDesktop 网址：'+DESKTOP,user);self.assertIn('ClaudeWeb 网址：'+CLAUDE,user)
        self.assertIn('WebDesktop 网址：http://127.0.0.1:3000',user)
        self.assertIn('ClaudeWeb 网址：http://127.0.0.1:3001',user)
        self.assertEqual(user.count('WebDesktop 密码：'+CREDS['DESKTOP_PASSWORD']),2)
        self.assertEqual(user.count('ClaudeWeb 密码：'+CREDS['DESKTOP_PASSWORD']),2)
        self.assertNotIn(CREDS['ADMIN_PASSWORD'],user);self.assertNotIn('ops-fixture',user)
        self.assertIn('管理员域名网址：'+DESKTOP+'/ops-fixture',admin)
        self.assertIn('管理员 SSH 隧道网址：http://127.0.0.1:3000/ops-fixture',admin)
        self.assertIn('管理员账号：admin',admin);self.assertIn('管理员密码：'+CREDS['ADMIN_PASSWORD'],admin)
        self.assertNotIn('never-show-extra-secret',text)
        self.assertIn('-L 3000:127.0.0.1:3000 -L 3001:127.0.0.1:3001',user)

    def test_skipped_domain_still_prints_both_ssh_entries_and_never_invents_domain_urls(self):
        text=UI.credential_summary(CREDS,None,dict(port=3001,url=None))
        self.assertNotIn('https://',text);self.assertIn('install.sh domain',text)
        self.assertIn('install.sh cloudcli-domain',text)
        self.assertIn('ClaudeWeb 网址：http://127.0.0.1:3001',text)
        self.assertIn('共用同一份网页访问密码',text)
        self.assertIn('SSH 登录使用服务器自己的 SSH 凭据',text)

    def test_skipped_claude_hostname_is_explicit_even_when_desktop_is_bound(self):
        text=UI.credential_summary(CREDS,DESKTOP,dict(port=3001,url=None))
        self.assertIn(DESKTOP,text);self.assertNotIn(CLAUDE,text)
        self.assertIn('独立域名尚未添加',text);self.assertIn('install.sh cloudcli-domain',text)

    def test_failed_cloudcli_is_not_advertised_as_a_working_local_or_named_entry(self):
        text=UI.credential_summary(CREDS,DESKTOP,None)
        self.assertIn('未安装成功或入口配置不可用',text)
        self.assertIn('install.sh cloudcli',text)
        self.assertNotIn('3001',text);self.assertNotIn('ClaudeWeb 密码：',text)
        self.assertIn('WebDesktop 密码：',text)

    def test_nondefault_configured_port_is_used_consistently(self):
        text=UI.credential_summary(CREDS,None,dict(port=3101,url=None))
        self.assertIn('-L 3101:127.0.0.1:3101',text)
        self.assertIn('ClaudeWeb 网址：http://127.0.0.1:3101',text)

    def test_untrusted_control_characters_urls_and_admin_paths_are_never_formatted(self):
        for key,value in [('ADMIN_USER','admin\nattack'),('ADMIN_PATH','/ops/../../evil'),('ADMIN_PASSWORD','secret\x1b[2J')]:
            with self.subTest(key=key),self.assertRaises(ValueError):UI.credential_summary(dict(CREDS,**{key:value}),DESKTOP,ENTRY)
        for url in ('http://example.com','https://example.com/path','https://user@example.com','https://bad.example\n'):
            with self.subTest(url=url),self.assertRaises(ValueError):UI.credential_summary(CREDS,url,ENTRY)

    def test_cloudcli_configuration_must_have_safe_complete_origins_and_a_loopback_port(self):
        source=Mock()
        values=[{'schema':1,'port':3001,'origins':['http://127.0.0.1:3001',CLAUDE]},
                {'schema':1,'port':True,'origins':['http://127.0.0.1:1']},
                {'schema':1,'port':3001,'origins':[CLAUDE]},
                {'schema':1,'port':3001,'origins':['http://127.0.0.1:3001','https://bad.example/path']}]
        with patch.object(UI.os.path,'lexists',return_value=True):
            for value in values:
                with self.subTest(value=value),patch.object(UI,'read_display_json',return_value=value):
                    self.assertEqual(UI.cloudcli_access(source),ENTRY if value is values[0] else None)
            with patch.object(UI,'read_display_json',side_effect=UI.private.Failure('PERMISSIONS','unsafe')):
                self.assertIsNone(UI.cloudcli_access(source))

    def display(self,unsafe=False,no_terminal=False,read_error=False,root=True):
        class Terminal(io.StringIO):
            def close(self):pass
        source=Mock();terminal=Terminal();out=io.StringIO();err=io.StringIO()
        if unsafe:source.check_node.side_effect=UI.private.Failure('PERMISSIONS','unsafe')
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(UI.os,'geteuid',return_value=0 if root else 1000,create=True))
            for name in ('O_NOCTTY','O_CLOEXEC','O_NOFOLLOW'):stack.enter_context(patch.object(UI.os,name,getattr(UI.os,name,0),create=True))
            opened=stack.enter_context(patch.object(UI.os,'open',side_effect=OSError('no terminal') if no_terminal else None,return_value=91))
            stack.enter_context(patch.object(UI.os,'isatty',return_value=True))
            stack.enter_context(patch.object(UI.os,'fdopen',return_value=terminal))
            reader=stack.enter_context(patch.object(UI,'read_display_json',side_effect=ValueError('fixture') if read_error else None,return_value=CREDS))
            stack.enter_context(patch.object(UI,'cloudcli_access',return_value=ENTRY))
            logs=stack.enter_context(patch.object(UI.tools.diag,'append'))
            stack.enter_context(contextlib.redirect_stdout(out));stack.enter_context(contextlib.redirect_stderr(err))
            result=UI.display_credentials(source,DESKTOP)
        for secret in (CREDS['DESKTOP_PASSWORD'],CREDS['ADMIN_PASSWORD']):self.assertNotIn(secret,out.getvalue()+err.getvalue())
        logs.assert_not_called()
        return result,terminal.getvalue(),out.getvalue(),opened,reader

    def test_initial_secrets_go_only_to_the_controlling_terminal(self):
        result,terminal,out,opened,reader=self.display()
        self.assertTrue(result);self.assertIn(CREDS['DESKTOP_PASSWORD'],terminal);self.assertIn(CREDS['ADMIN_PASSWORD'],terminal)
        self.assertEqual(opened.call_args.args[0],'/dev/tty');reader.assert_called_once();self.assertEqual(out,'')

    def test_no_terminal_and_unsafe_paths_do_not_read_or_print_secrets(self):
        for options in ({'no_terminal':True},{'unsafe':True}):
            with self.subTest(options=options):
                result,terminal,out,_,reader=self.display(**options)
                self.assertFalse(result);self.assertEqual(terminal,'');reader.assert_not_called()
                self.assertIn('cat /etc/webdesktop-isolated/login.json',out)

    def test_failed_read_keeps_installation_result_and_returns_a_static_recovery_instruction(self):
        result,terminal,out,_,_=self.display(read_error=True)
        self.assertFalse(result);self.assertEqual(terminal,'');self.assertIn('安装已成功',out)

    def test_nonroot_cannot_display_initial_credentials(self):
        with self.assertRaisesRegex(ValueError,'ROOT_REQUIRED'):self.display(root=False)

    def test_protected_json_read_checks_fd_identity_ownership_permissions_and_size(self):
        class Secret(io.BytesIO):
            def fileno(self):return 92
        source=Mock();path=Path('/etc/webdesktop-isolated/login.json')
        valid=dict(st_dev=1,st_ino=2,st_mode=stat.S_IFREG|0o600,st_uid=0,st_nlink=1)
        variants=[{},dict(st_uid=1000),dict(st_nlink=2),dict(st_mode=stat.S_IFREG|0o644),dict(st_ino=3)]
        for change in variants:
            with self.subTest(change=change),contextlib.ExitStack() as stack:
                for name in ('O_CLOEXEC','O_NOFOLLOW'):stack.enter_context(patch.object(UI.os,name,getattr(UI.os,name,0),create=True))
                stack.enter_context(patch.object(UI.os,'open',return_value=92))
                stack.enter_context(patch.object(UI.os,'fdopen',return_value=Secret(json.dumps(CREDS).encode())))
                stack.enter_context(patch.object(UI.os,'fstat',return_value=types.SimpleNamespace(**dict(valid,**change))))
                stack.enter_context(patch.object(Path,'lstat',return_value=types.SimpleNamespace(**valid)))
                if change:
                    with self.assertRaisesRegex(ValueError,'DISPLAY_INPUT_CHANGED'):UI.read_display_json(source,path)
                else:self.assertEqual(UI.read_display_json(source,path),CREDS)


if __name__=='__main__':unittest.main()
