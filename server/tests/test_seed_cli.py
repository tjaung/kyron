import os
import unittest
from unittest.mock import patch

import seed_data


class SeedCliTests(unittest.TestCase):
    def test_seed_only_initializes_supporting_fixtures(self):
        for args in (['seed_data.py'], ['seed_data.py', '--fixtures-only']):
            with self.subTest(args=args), patch.dict(os.environ, {'DATABASE_URL': 'configured'}), patch('sys.argv', args), patch('server.core.seed.initialize_database') as initialize, patch('builtins.print') as output:
                seed_data.main()
                initialize.assert_called_once_with()
                self.assertIn('Run a simulation to create conversations', output.call_args.args[0])
