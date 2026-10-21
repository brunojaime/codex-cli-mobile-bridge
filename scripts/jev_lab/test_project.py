import os
import unittest
from unittest.mock import patch

import project


class ProjectSecretsTests(unittest.TestCase):
    def test_mobile_panel_name_is_mapped_in_memory(self):
        with patch.dict(os.environ,{},clear=True),patch('project.dotenv_values',return_value={'OPEN_ROUTER_API_KEY':'fake-panel-key','UNRELATED_SECRET':'fake-other'}),patch('project.lab.main',return_value=0):
            self.assertEqual(project.main(),0)
            self.assertEqual(os.environ['OPENROUTER_API_KEY'],'fake-panel-key')
            self.assertNotIn('UNRELATED_SECRET',os.environ)

    def test_rotated_panel_key_overrides_stale_process_value(self):
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'fake-old'},clear=True),patch('project.dotenv_values',return_value={'OPEN_ROUTER_API_KEY':'fake-current'}),patch('project.lab.main',return_value=0):
            project.main()
            self.assertEqual(os.environ['OPENROUTER_API_KEY'],'fake-current')

    def test_standard_spelling_is_supported(self):
        with patch.dict(os.environ,{},clear=True),patch('project.dotenv_values',return_value={'OPENROUTER_API_KEY':'fake-standard'}),patch('project.lab.main',return_value=0):
            project.main()
            self.assertEqual(os.environ['OPENROUTER_API_KEY'],'fake-standard')


if __name__=='__main__':unittest.main()
