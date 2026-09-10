"""CLI tests.

The CLI reports the library's own declarations, so these tests assert the
derivation rather than a hand-written table: a scanner added to the registry
must show up here without touching this file, and a chain the scanner class
does not declare must not.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aiochainscan.chain_registry import SCANNER_RECORDS, resolve_scanner_target
from aiochainscan.cli import (
    _chains,
    _config_id,
    _scanner_report,
    build_parser,
    cmd_chains,
    cmd_check,
    cmd_generate_env,
    cmd_scanners,
    cmd_test,
    main,
)
from aiochainscan.domain.method import Method
from aiochainscan.scanners import get_scanner_class


def _args(**kwargs):
    namespace = MagicMock()
    namespace.__dict__.update(kwargs)
    for key, value in kwargs.items():
        setattr(namespace, key, value)
    return namespace


class TestDerivation:
    def test_every_registered_scanner_is_reported(self):
        reported = {report['scanner'] for report in map(_scanner_report, SCANNER_RECORDS)}
        assert reported == set(SCANNER_RECORDS)

    @pytest.mark.parametrize('scanner', sorted(SCANNER_RECORDS))
    def test_method_count_matches_the_scanner_class(self, scanner):
        report = _scanner_report(scanner)
        target = resolve_scanner_target(
            scanner, sorted(report['chains'])[0] if report['chains'] else 'ethereum', api_key=''
        )
        scanner_class = get_scanner_class(target.scanner_name, target.scanner_version)
        assert report['methods_declared'] == len(scanner_class.SPECS)
        assert report['methods_total'] == len(Method)

    @pytest.mark.parametrize('scanner', sorted(SCANNER_RECORDS))
    def test_reported_chains_are_constructible(self, scanner):
        """Every chain the CLI names must pass both construction gates."""
        for chain in _chains(scanner):
            target = resolve_scanner_target(scanner, chain, api_key='')
            scanner_class = get_scanner_class(target.scanner_name, target.scanner_version)
            assert target.scanner_network in scanner_class.supported_networks

    def test_registry_resolution_alone_is_not_enough(self):
        """Avalanche resolves in the registry but no BlockScout instance serves it."""
        resolve_scanner_target('blockscout', 'avalanche', api_key='')  # does not raise
        assert 'avalanche' not in _chains('blockscout')
        assert 'avalanche' not in _chains('blockscout_v2')

    def test_blockscout_is_keyless_and_etherscan_is_not(self):
        assert _scanner_report('blockscout')['keyless'] is True
        assert _scanner_report('blockscout_v2')['keyless'] is True
        assert _scanner_report('etherscan')['keyless'] is False
        assert _scanner_report('nodereal')['keyless'] is False

    def test_config_id_per_scanner(self):
        assert _config_id('etherscan') == 'eth'
        assert _config_id('nodereal') == 'nodereal'
        assert _config_id('blockscout').startswith('blockscout')


class TestScannersCommand:
    def test_json_output_lists_every_scanner(self, capsys):
        cmd_scanners(_args(json=True))
        payload = json.loads(capsys.readouterr().out)
        assert {row['scanner'] for row in payload} == set(SCANNER_RECORDS)
        assert all(row['methods_declared'] > 0 for row in payload)

    def test_text_output_names_the_public_factory(self, capsys):
        cmd_scanners(_args(json=False))
        out = capsys.readouterr().out
        assert 'ChainscanClient.from_config' in out
        for scanner in SCANNER_RECORDS:
            assert scanner in out

    def test_no_legacy_per_chain_scanners(self, capsys):
        """The pre-1.0 registry (BscScan, PolygonScan, one key per chain) is gone."""
        cmd_scanners(_args(json=False))
        out = capsys.readouterr().out
        for legacy in ('BscScan', 'PolygonScan', 'BSCSCAN_KEY', 'POLYGONSCAN_KEY', 'mumbai'):
            assert legacy not in out


class TestCheckCommand:
    def test_json_shape(self, capsys):
        cmd_check(_args(json=True))
        payload = json.loads(capsys.readouterr().out)
        assert set(payload) == {'keyless', 'configured', 'missing', 'env_files'}
        assert 'blockscout' in payload['keyless']

    def test_missing_key_names_the_env_var(self, capsys):
        config = MagicMock(requires_api_key=True)
        config.name = 'Etherscan'  # MagicMock(name=...) names the mock, not the field
        with patch('aiochainscan.cli.config_manager') as manager:
            manager.get_scanner_config.return_value = config
            manager.get_api_key.return_value = ''
            cmd_check(_args(json=False))
        out = capsys.readouterr().out
        assert 'Key missing' in out
        assert 'ETHERSCAN_KEY' in out


class TestChainsCommand:
    def test_filter_narrows_the_listing(self, capsys):
        cmd_chains(_args(filter='ethereum', json=True))
        payload = json.loads(capsys.readouterr().out)
        assert payload
        assert all('ethereum' in row['name'] or 'ethereum' in row['aliases'] for row in payload)

    def test_unknown_filter_says_so(self, capsys):
        cmd_chains(_args(filter='no-such-chain', json=False))
        assert 'No chain matches' in capsys.readouterr().out

    def test_rows_carry_the_serving_scanners(self, capsys):
        cmd_chains(_args(filter='1', json=True))
        payload = json.loads(capsys.readouterr().out)
        ethereum = next(row for row in payload if row['chain_id'] == 1)
        assert 'etherscan' in ethereum['scanners']
        assert 'blockscout' in ethereum['scanners']


class TestGenerateEnv:
    def test_template_covers_only_keys_in_use(self, capsys):
        cmd_generate_env(_args(output=None))
        out = capsys.readouterr().out
        assert 'ETHERSCAN_KEY=' in out
        assert 'NODEREAL_KEY=' in out
        assert 'BSCSCAN_KEY' not in out
        assert 'BLOCKSCOUT' not in out

    def test_writes_to_file(self, tmp_path, capsys):
        target = tmp_path / '.env.template'
        cmd_generate_env(_args(output=str(target)))
        capsys.readouterr()
        assert 'ETHERSCAN_KEY=' in target.read_text()


class TestTestCommand:
    def test_success_reports_the_value_and_closes_the_client(self, capsys):
        client = MagicMock()
        client.get_balance = AsyncMock(return_value='123')
        client.close = AsyncMock()
        with patch('aiochainscan.ChainscanClient.from_config', return_value=client):
            cmd_test(_args(scanner='blockscout_v2', network='ethereum', address=None))
        out = capsys.readouterr().out
        assert '123' in out
        client.close.assert_awaited_once()

    def test_failure_exits_non_zero_and_closes_the_client(self, capsys):
        client = MagicMock()
        client.get_balance = AsyncMock(side_effect=RuntimeError('boom'))
        client.close = AsyncMock()
        with (
            patch('aiochainscan.ChainscanClient.from_config', return_value=client),
            pytest.raises(SystemExit) as exit_info,
        ):
            cmd_test(_args(scanner='etherscan', network='ethereum', address=None))
        assert exit_info.value.code == 1
        assert 'boom' in capsys.readouterr().err
        client.close.assert_awaited_once()

    def test_unconstructible_target_exits_non_zero(self, capsys):
        with pytest.raises(SystemExit) as exit_info:
            cmd_test(_args(scanner='nodereal', network='ethereum', address=None))
        assert exit_info.value.code == 1
        assert 'not supported by NodeReal' in capsys.readouterr().err


class TestParser:
    def test_scanners_has_the_legacy_list_alias(self):
        parser = build_parser()
        assert parser.parse_args(['list']).func is parser.parse_args(['scanners']).func

    def test_test_network_defaults_to_ethereum(self):
        args = build_parser().parse_args(['test', 'blockscout_v2'])
        assert args.network == 'ethereum'
        assert args.address is None

    @pytest.mark.parametrize('command', ['add-scanner', 'export'])
    def test_legacy_commands_are_gone(self, command):
        with pytest.raises(SystemExit):
            build_parser().parse_args([command, 'x'])

    def test_no_command_prints_help_and_exits(self, capsys):
        with patch('sys.argv', ['aiochainscan']), pytest.raises(SystemExit) as exit_info:
            main()
        assert exit_info.value.code == 1
        assert 'usage' in capsys.readouterr().out

    def test_dispatches_to_the_selected_command(self):
        with (
            patch('sys.argv', ['aiochainscan', 'check', '--json']),
            patch('aiochainscan.cli.cmd_check') as command,
        ):
            main()
        command.assert_called_once()

    def test_keyboard_interrupt_is_not_a_traceback(self, capsys):
        with (
            patch('sys.argv', ['aiochainscan', 'check']),
            patch('aiochainscan.cli.cmd_check', side_effect=KeyboardInterrupt),
            pytest.raises(SystemExit) as exit_info,
        ):
            main()
        assert exit_info.value.code == 130
        assert 'Interrupted' in capsys.readouterr().err
