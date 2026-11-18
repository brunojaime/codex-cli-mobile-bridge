import unittest,json,tempfile
from pathlib import Path
from unittest.mock import patch
from services.chatgpt_collaboration.client import environment_defaults
class EnvironmentTest(unittest.TestCase):
 def test_explicit_dev_uses_separate_endpoint_and_token_store(self):
  env,url,state=environment_defaults('dev',environ={'BRIDGE_ENVIRONMENT':'prod'})
  self.assertEqual((env,url,state.name),('dev','http://127.0.0.1:8167','backend-dev'))
 def test_dev_launcher_is_detected(self):
  self.assertEqual(environment_defaults('auto',environ={'BRIDGE_ENVIRONMENT':'dev'})[0],'dev')
 def test_prod_remains_existing_endpoint(self):
  self.assertEqual(environment_defaults('prod',environ={})[1],'http://127.0.0.1:8166')
 def test_stage_path_detected_without_inherited_variable(self):
  with patch('services.chatgpt_collaboration.client.urlopen') as call:
   call.return_value.__enter__.return_value.read.return_value=b'{"environment_identity":{"environment":"dev","worktree_path":"/tmp/stage"}}'
   self.assertEqual(environment_defaults('auto',cwd='/tmp/stage/services',environ={})[0],'dev')
 def test_known_dev_stage_does_not_fall_back_when_dev_is_down(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=root/'.local/share/chatgpt-collaboration/dev-routing.json';p.parent.mkdir(parents=True)
   p.write_text(json.dumps({'workspace_paths':['/tmp/known-dev-stage']}))
   with patch('services.chatgpt_collaboration.client.Path.home',return_value=root),patch('services.chatgpt_collaboration.client.urlopen',side_effect=OSError):
    self.assertEqual(environment_defaults('auto',cwd='/tmp/known-dev-stage/src',environ={})[0],'dev')
if __name__=='__main__':unittest.main()
