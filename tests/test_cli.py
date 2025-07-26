from pathlib import Path
from unittest.mock import MagicMock, patch

from aiochainscan.cli import (
    cmd_add_scanner,
    cmd_check_config,
    cmd_export_config,
    cmd_generate_env,
    cmd_list_scanners,
    cmd_test_scanner,
    main,
)


class TestCmdListScanners:
    """Test scanner listing functionality."""

    @patch('aiochainscan.cli.config_manager')
    @patch('builtins.print')
    def test_list_scanners_with_configured_keys(self, mock_print, mock_config_manager):
        """Test listing scanners with configured API keys."""
        mock_config_manager.list_all_configurations.return_value = {
            'eth': {
                'name': 'Etherscan',
                'domain': 'etherscan.io',
                'currency': 'ETH',
                'networks': ['main', 'goerli', 'sepolia'],
                'api_key_configured': True,
                'requires_api_key': True,
                'api_key_sources': ['ETHERSCAN_KEY', 'ETH_KEY']
            },
            'bsc': {
                'name': 'BscScan',
                'domain': 'bscscan.com',
                'currency': 'BNB',
                'networks': ['main', 'test'],
                'api_key_configured': False,
                'requires_api_key': True,
                'api_key_sources': ['BSCSCAN_KEY', 'BSC_KEY']
            }
        }

        args = MagicMock()
        cmd_list_scanners(args)

        # Verify the function prints scanner information
        mock_print.assert_called()
        print_calls = [call[0][0] for call in mock_print.call_args_list]

        # Check that scanner info is displayed
        assert any('ETH: Etherscan' in call for call in print_calls)
        assert any('BSC: BscScan' in call for call in print_calls)
        assert any('✅ READY' in call for call in print_calls)
        assert any('❌ NO API KEY' in call for call in print_calls)

    @patch('aiochainscan.cli.config_manager')
    @patch('builtins.print')
    def test_list_scanners_empty_config(self, mock_print, mock_config_manager):
        """Test listing scanners with empty configuration."""
        mock_config_manager.list_all_configurations.return_value = {}

        args = MagicMock()
        cmd_list_scanners(args)

        mock_print.assert_called()


class TestCmdGenerateEnv:
    """Test environment file generation."""

    @patch('aiochainscan.cli.config_manager')
    @patch('builtins.print')
    def test_generate_env_default_output(self, mock_print, mock_config_manager):
        """Test generating .env file with default output path."""
        mock_config_manager.generate_env_template.return_value = "# Test template content"

        args = MagicMock()
        args.output = None
        args.show = False

        with patch('pathlib.Path.cwd') as mock_cwd:
            mock_cwd.return_value = Path('/test/dir')
            cmd_generate_env(args)

        # Verify template generation was called
        expected_path = Path('/test/dir') / '.env.example'
        mock_config_manager.generate_env_template.assert_called_once_with(expected_path)

        # Verify success message
        mock_print.assert_called()

    @patch('aiochainscan.cli.config_manager')
    @patch('builtins.print')
    def test_generate_env_custom_output(self, mock_print, mock_config_manager):
        """Test generating .env file with custom output path."""
        mock_config_manager.generate_env_template.return_value = "# Custom template"

        args = MagicMock()
        args.output = '/custom/path/.env.test'
        args.show = False

        cmd_generate_env(args)

        expected_path = Path('/custom/path/.env.test')
        mock_config_manager.generate_env_template.assert_called_once_with(expected_path)

    @patch('aiochainscan.cli.config_manager')
    @patch('builtins.print')
    def test_generate_env_with_show(self, mock_print, mock_config_manager):
        """Test generating .env file with show option."""
        template_content = "# Template content\nETHERSCAN_KEY=your_key_here"
        mock_config_manager.generate_env_template.return_value = template_content

        args = MagicMock()
        args.output = None
        args.show = True

        with patch('pathlib.Path.cwd') as mock_cwd:
            mock_cwd.return_value = Path('/test/dir')
            cmd_generate_env(args)

        # Verify template content is printed
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert any(template_content in call for call in print_calls)


class TestCmdCheckConfig:
    """Test configuration status checking."""

    @patch('aiochainscan.cli.config_manager')
    @patch('builtins.print')
    def test_check_config_mixed_status(self, mock_print, mock_config_manager):
        """Test checking configuration with mixed scanner statuses."""
        mock_config_manager.list_all_configurations.return_value = {
            'eth': {
                'name': 'Etherscan',
                'api_key_configured': True,
                'requires_api_key': True,
                'api_key_sources': ['ETHERSCAN_KEY']
            },
            'bsc': {
                'name': 'BscScan',
                'api_key_configured': False,
                'requires_api_key': True,
                'api_key_sources': ['BSCSCAN_KEY']
            },
            'flare': {
                'name': 'Flare Explorer',
                'api_key_configured': False,
                'requires_api_key': False,
                'api_key_sources': []
            }
        }

        args = MagicMock()

        with patch('pathlib.Path.exists', return_value=False):
            cmd_check_config(args)

        # Verify summary and status information is printed
        mock_print.assert_called()
        print_calls = [call[0][0] for call in mock_print.call_args_list]

        assert any('1/3 scanners configured' in call for call in print_calls)
        assert any('Ready scanners' in call for call in print_calls)
        assert any('Missing API keys' in call for call in print_calls)

    @patch('aiochainscan.cli.config_manager')
    @patch('builtins.print')
    def test_check_config_with_env_files(self, mock_print, mock_config_manager):
        """Test configuration check when .env files exist."""
        mock_config_manager.list_all_configurations.return_value = {}

        args = MagicMock()

        def mock_exists():
            return True

        with patch('pathlib.Path.exists', side_effect=mock_exists):
            cmd_check_config(args)

        # Verify env file detection
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert any('Found .env files' in call for call in print_calls)


class TestCmdAddScanner:
    """Test adding custom scanners."""

    @patch('aiochainscan.cli.config_manager')
    @patch('builtins.print')
    def test_add_scanner_success(self, mock_print, mock_config_manager):
        """Test successfully adding a custom scanner."""
        mock_config_manager.register_scanner.return_value = None
        mock_config_manager._get_api_key_suggestions.return_value = ['CUSTOM_KEY']

        args = MagicMock()
        args.id = 'custom'
        args.name = 'Custom Chain'
        args.domain = 'customscan.io'
        args.currency = 'CUSTOM'
        args.networks = 'main,test'
        args.no_api_key = False

        cmd_add_scanner(args)

        # Verify scanner registration
        expected_data = {
            'name': 'Custom Chain',
            'base_domain': 'customscan.io',
            'currency': 'CUSTOM',
            'supported_networks': ['main', 'test'],
            'requires_api_key': True,
            'special_config': {}
        }
        mock_config_manager.register_scanner.assert_called_once_with('custom', expected_data)

        # Verify success message
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert any('Successfully added scanner: custom' in call for call in print_calls)

    @patch('aiochainscan.cli.config_manager')
    @patch('builtins.print')
    @patch('sys.exit')
    def test_add_scanner_failure(self, mock_exit, mock_print, mock_config_manager):
        """Test handling scanner addition failure."""
        mock_config_manager.register_scanner.side_effect = ValueError("Scanner already exists")

        args = MagicMock()
        args.id = 'existing'
        args.name = 'Existing Scanner'
        args.domain = 'existing.com'
        args.currency = 'EXT'
        args.networks = None
        args.no_api_key = True

        cmd_add_scanner(args)

        # Verify error handling
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert any('Error adding scanner' in call for call in print_calls)
        mock_exit.assert_called_once_with(1)


class TestCmdExportConfig:
    """Test configuration export."""

    @patch('aiochainscan.cli.config_manager')
    @patch('builtins.print')
    def test_export_config_success(self, mock_print, mock_config_manager):
        """Test successful configuration export."""
        mock_config_manager.export_config.return_value = None

        args = MagicMock()
        args.output = '/path/to/config.json'

        cmd_export_config(args)

        expected_path = Path('/path/to/config.json')
        mock_config_manager.export_config.assert_called_once_with(expected_path)

        # Verify success message
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert any('Configuration exported to' in call for call in print_calls)

    @patch('aiochainscan.cli.config_manager')
    @patch('builtins.print')
    @patch('sys.exit')
    def test_export_config_failure(self, mock_exit, mock_print, mock_config_manager):
        """Test export configuration failure."""
        mock_config_manager.export_config.side_effect = Exception("Write error")

        args = MagicMock()
        args.output = '/invalid/path/config.json'

        cmd_export_config(args)

        # Verify error handling
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert any('Export failed' in call for call in print_calls)
        mock_exit.assert_called_once_with(1)


class TestCmdTestScanner:
    """Test scanner testing functionality."""

    @patch('builtins.print')
    @patch('asyncio.run')
    def test_test_scanner_success(self, mock_run, mock_print):
        """Test successful scanner testing."""
        mock_run.return_value = None

        args = MagicMock()
        args.scanner = 'eth'
        args.network = 'main'

        cmd_test_scanner(args)

        # Verify asyncio.run was called
        mock_run.assert_called_once()

    @patch('builtins.print')
    @patch('sys.exit')
    @patch('asyncio.run')
    def test_test_scanner_basic(self, mock_run, mock_exit, mock_print):
        """Test basic scanner test functionality."""
        mock_run.return_value = None

        args = MagicMock()
        args.scanner = 'eth'
        args.network = 'main'

        cmd_test_scanner(args)

        # Verify asyncio.run was called
        mock_run.assert_called_once()


class TestMainFunction:
    """Test main CLI entry point."""

    @patch('sys.argv', ['aiochainscan', 'list'])
    @patch('aiochainscan.cli.cmd_list_scanners')
    def test_main_list_command(self, mock_cmd_list):
        """Test main function with list command."""
        main()
        mock_cmd_list.assert_called_once()

    @patch('sys.argv', ['aiochainscan', 'check'])
    @patch('aiochainscan.cli.cmd_check_config')
    def test_main_check_command(self, mock_cmd_check):
        """Test main function with check command."""
        main()
        mock_cmd_check.assert_called_once()

    @patch('sys.argv', ['aiochainscan', 'generate-env', '--output', '.env.test'])
    @patch('aiochainscan.cli.cmd_generate_env')
    def test_main_generate_env_command(self, mock_cmd_generate):
        """Test main function with generate-env command."""
        main()
        mock_cmd_generate.assert_called_once()

    @patch('sys.argv', ['aiochainscan'])
    @patch('builtins.print')
    @patch('sys.exit')
    def test_main_no_command(self, mock_exit, mock_print):
        """Test main function with no command provided."""
        with patch('argparse.ArgumentParser.print_help') as mock_help:
            main()
            mock_help.assert_called_once()
            # Check that exit was called at least once with 1
            mock_exit.assert_called_with(1)

    @patch('sys.argv', ['aiochainscan', 'list'])
    @patch('aiochainscan.cli.cmd_list_scanners')
    @patch('builtins.print')
    @patch('sys.exit')
    def test_main_keyboard_interrupt(self, mock_exit, mock_print, mock_cmd_list):
        """Test main function handling keyboard interrupt."""
        mock_cmd_list.side_effect = KeyboardInterrupt()

        main()

        mock_exit.assert_called_once_with(1)
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert any('Operation cancelled' in call for call in print_calls)

    @patch('sys.argv', ['aiochainscan', 'list'])
    @patch('aiochainscan.cli.cmd_list_scanners')
    @patch('builtins.print')
    @patch('sys.exit')
    def test_main_unexpected_error(self, mock_exit, mock_print, mock_cmd_list):
        """Test main function handling unexpected errors."""
        mock_cmd_list.side_effect = Exception("Unexpected error")

        main()

        mock_exit.assert_called_once_with(1)
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert any('Unexpected error' in call for call in print_calls)

    @patch('sys.argv', ['aiochainscan', 'add-scanner', 'test', '--name', 'Test Scanner', '--domain', 'test.com', '--currency', 'TEST'])
    @patch('aiochainscan.cli.cmd_add_scanner')
    def test_main_add_scanner_command(self, mock_cmd_add):
        """Test main function with add-scanner command."""
        main()
        mock_cmd_add.assert_called_once()

    @patch('sys.argv', ['aiochainscan', 'export', 'config.json'])
    @patch('aiochainscan.cli.cmd_export_config')
    def test_main_export_command(self, mock_cmd_export):
        """Test main function with export command."""
        main()
        mock_cmd_export.assert_called_once()

    @patch('sys.argv', ['aiochainscan', 'test', 'eth', '--network', 'goerli'])
    @patch('aiochainscan.cli.cmd_test_scanner')
    def test_main_test_command(self, mock_cmd_test):
        """Test main function with test command."""
        main()
        mock_cmd_test.assert_called_once()


class TestCLIArgumentParsing:
    """Test command-line argument parsing."""

    def test_list_command_args(self):
        """Test list command argument parsing."""
        from aiochainscan.cli import main

        with patch('sys.argv', ['aiochainscan', 'list']), \
             patch('aiochainscan.cli.cmd_list_scanners') as mock_cmd:
            main()
            mock_cmd.assert_called_once()

    def test_generate_env_args(self):
        """Test generate-env command with various arguments."""
        test_cases = [
            ['aiochainscan', 'generate-env'],
            ['aiochainscan', 'generate-env', '--output', 'custom.env'],
            ['aiochainscan', 'generate-env', '--show'],
            ['aiochainscan', 'generate-env', '-o', 'test.env', '-s'],
        ]

        for argv in test_cases:
            with patch('sys.argv', argv), \
                 patch('aiochainscan.cli.cmd_generate_env') as mock_cmd:
                main()
                mock_cmd.assert_called_once()

    def test_add_scanner_args(self):
        """Test add-scanner command argument parsing."""
        with patch('sys.argv', [
            'aiochainscan', 'add-scanner', 'test_chain',
            '--name', 'Test Chain',
            '--domain', 'testchain.com',
            '--currency', 'TEST',
            '--networks', 'main,test',
            '--no-api-key'
        ]), patch('aiochainscan.cli.cmd_add_scanner') as mock_cmd:
            main()
            mock_cmd.assert_called_once()
            args = mock_cmd.call_args[0][0]
            assert args.id == 'test_chain'
            assert args.name == 'Test Chain'
            assert args.domain == 'testchain.com'
            assert args.currency == 'TEST'
            assert args.networks == 'main,test'
            assert args.no_api_key is True
