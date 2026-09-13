"""CLI tests.

The CLI reports the library's own declarations, so these tests assert the
derivation rather than a hand-written table: a scanner added to the registry
must show up here without touching this file, and a chain the scanner class
does not declare must not.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aiochainscan.chain_registry import (
    BLOCKSCOUT_INSTANCE_HOSTS,
    SCANNER_RECORDS,
    config_id_for_scanner,
    get_chain_name,
    resolve_chain_id,
    resolve_scanner_target,
)
from aiochainscan.cli import (
    _chains,
    _config_id,
    _env_files,
    _scanner_report,
    build_parser,
    cmd_chains,
    cmd_check,
    cmd_generate_env,
    cmd_scanners,
    cmd_test,
    main,
)
from aiochainscan.config import ConfigurationManager
from aiochainscan.domain.method import Method
from aiochainscan.scanners import chains_served_by, get_scanner_class


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


class TestConfigIdQuery:
    """The scanner→config-id rule lives beside the tables that own it."""

    def test_the_registry_answers_for_every_recorded_scanner(self):
        for scanner in SCANNER_RECORDS:
            assert config_id_for_scanner(scanner) == _config_id(scanner)

    def test_known_ids(self):
        assert config_id_for_scanner('etherscan') == 'eth'
        assert config_id_for_scanner('nodereal') == 'nodereal'
        assert config_id_for_scanner('blockscout') == 'blockscout_eth'
        assert config_id_for_scanner('blockscout_v2') == 'blockscout_eth'

    def test_unknown_scanner_raises_key_error(self):
        with pytest.raises(KeyError):
            config_id_for_scanner('no-such-scanner')


class TestChainsServedBy:
    """The two construction gates as one query, pinned against their
    declared sources — not against a hand-copied chain list."""

    def test_etherscan_serves_exactly_the_chains_its_records_declare(self):
        served = chains_served_by('etherscan')
        declared = {
            get_chain_name(resolve_chain_id(key))
            for key in SCANNER_RECORDS['etherscan'].network_aliases
        }
        assert served == sorted(declared)
        # the retired testnets stay out even though their ids remain resolvable
        assert 'goerli' not in served
        assert 'holesky' not in served

    def test_blockscout_serves_exactly_the_chains_with_a_declared_instance(self):
        served = chains_served_by('blockscout')
        with_instance = sorted(
            {get_chain_name(resolve_chain_id(alias)) for alias in BLOCKSCOUT_INSTANCE_HOSTS}
        )
        assert served == with_instance
        # the second gate's whole point: registry resolution alone would
        # resolve chains no BlockScout instance serves
        resolve_scanner_target('blockscout', 'avalanche', api_key='')  # does not raise
        assert 'avalanche' not in served

    def test_both_blockscout_legs_serve_the_same_chains(self):
        assert chains_served_by('blockscout_v2') == chains_served_by('blockscout')

    def test_nodereal_is_bsc_only(self):
        assert chains_served_by('nodereal') == ['bsc', 'bsc-testnet']

    def test_the_cli_helper_delegates(self):
        assert _chains('nodereal') == chains_served_by('nodereal')


class TestEnvFiles:
    """The credential-file listing asks the manager, so it follows the
    manager's (rebindable) config_dir — never a ``Path.cwd()`` guess."""

    def test_listing_follows_the_manager_config_dir_not_cwd(self, tmp_path, monkeypatch):
        home = tmp_path / 'home'
        home.mkdir()
        monkeypatch.setattr(Path, 'home', lambda: home)
        config_dir = tmp_path / 'conf'
        config_dir.mkdir()
        (config_dir / '.env.local').write_text('A=1\n')
        (config_dir / '.env').write_text('B=2\n')
        cwd = tmp_path / 'elsewhere'
        cwd.mkdir()
        (cwd / '.env').write_text('DECOY=1\n')
        monkeypatch.chdir(cwd)

        manager = ConfigurationManager.create_isolated(config_dir=config_dir)

        assert _env_files(manager) == [config_dir / '.env.local', config_dir / '.env']

    def test_home_file_is_listed_last_when_present(self, tmp_path, monkeypatch):
        home = tmp_path / 'home'
        (home / '.aiochainscan').mkdir(parents=True)
        (home / '.aiochainscan' / '.env').write_text('C=3\n')
        monkeypatch.setattr(Path, 'home', lambda: home)
        config_dir = tmp_path / 'conf'
        config_dir.mkdir()
        (config_dir / '.env').write_text('B=2\n')

        manager = ConfigurationManager.create_isolated(config_dir=config_dir)

        assert _env_files(manager) == [
            config_dir / '.env',
            home / '.aiochainscan' / '.env',
        ]

    def test_candidates_are_what_the_loader_reads(self, tmp_path, monkeypatch):
        """The loader iterates ``env_file_candidates`` — one list, no drift."""
        home = tmp_path / 'home'
        home.mkdir()
        monkeypatch.setattr(Path, 'home', lambda: home)
        config_dir = tmp_path / 'conf'
        config_dir.mkdir()
        (config_dir / '.env').write_text('B=2\n')

        manager = ConfigurationManager.create_isolated(config_dir=config_dir)
        read: list[Path] = []
        monkeypatch.setattr(manager, '_load_env_file', read.append)
        manager._load_env_files()

        assert read == [config_dir / '.env']

    def test_check_reports_the_manager_dir(self, tmp_path, monkeypatch, capsys):
        home = tmp_path / 'home'
        home.mkdir()
        monkeypatch.setattr(Path, 'home', lambda: home)
        config_dir = tmp_path / 'conf'
        config_dir.mkdir()
        (config_dir / '.env.local').write_text('ETHERSCAN_KEY=from-local\n')
        cwd = tmp_path / 'elsewhere'
        cwd.mkdir()
        (cwd / '.env').write_text('DECOY=1\n')
        monkeypatch.chdir(cwd)

        manager = ConfigurationManager.create_isolated(config_dir=config_dir)
        with patch('aiochainscan.cli.config_manager', manager):
            cmd_check(_args(json=True))

        payload = json.loads(capsys.readouterr().out)
        assert payload['env_files'] == [str(config_dir / '.env.local')]

    def test_check_text_order_matches_load_order(self, tmp_path, monkeypatch, capsys):
        home = tmp_path / 'home'
        (home / '.aiochainscan').mkdir(parents=True)
        (home / '.aiochainscan' / '.env').write_text('C=3\n')
        monkeypatch.setattr(Path, 'home', lambda: home)
        config_dir = tmp_path / 'conf'
        config_dir.mkdir()
        (config_dir / '.env.local').write_text('A=1\n')
        (config_dir / '.env').write_text('B=2\n')

        manager = ConfigurationManager.create_isolated(config_dir=config_dir)
        with patch('aiochainscan.cli.config_manager', manager):
            cmd_check(_args(json=False))

        out = capsys.readouterr().out
        assert '(earlier entries override later ones)' in out
        local_pos = out.index(str(config_dir / '.env.local'))
        base_pos = out.index(str(config_dir / '.env') + '\n')
        home_pos = out.index(str(home / '.aiochainscan' / '.env'))
        assert local_pos < base_pos < home_pos


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
