#!/usr/bin/env python3
"""Command line interface for aiochainscan.

Answers the questions a user has before writing code: which providers this
installation can reach, which of them need a credential and whether it is
present, which chains resolve, and whether a chosen provider actually answers.

Every fact printed here is derived from the same declarations the library uses
at runtime — :data:`aiochainscan.chain_registry.SCANNER_RECORDS`, the scanner
classes' ``SPECS``, and the configuration manager's credential resolution — so
the CLI cannot describe a provider surface the client does not have.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from aiochainscan.chain_registry import (
    BLOCKSCOUT_CONFIG_IDS,
    CUSTOM_BASE_URL_SCANNERS,
    SCANNER_CONFIG_IDS,
    SCANNER_RECORDS,
    ScannerTarget,
    get_chain_aliases,
    get_chain_name,
    list_supported_chains,
    resolve_scanner_target,
)
from aiochainscan.config import config_manager, credential_env_names
from aiochainscan.domain.method import Method
from aiochainscan.scanners import get_scanner_class

#: Address used by ``test`` when the caller names none (vitalik.eth).
PROBE_ADDRESS = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

#: Files ``ConfigurationManager`` reads credentials from, in load order.
ENV_FILE_CANDIDATES = ('.env.local', '.env')


def _env_files() -> list[Path]:
    """The credential files present right now, in the order they are read."""
    paths = [Path.home() / '.aiochainscan' / '.env']
    paths += [Path.cwd() / name for name in ENV_FILE_CANDIDATES]
    return [path for path in paths if path.exists()]


def _identity(scanner: str) -> ScannerTarget:
    """Resolve a public scanner name to its construction target.

    ``api_key=''`` keeps credential lookup out of it: this asks what the
    scanner *is*, not whether it is configured. The candidate networks come
    from the scanner's own record, so a chain-restricted provider (NodeReal is
    BSC-only) resolves on a network it actually serves.
    """
    record = SCANNER_RECORDS[scanner]
    candidates = sorted(record.supported_networks or ()) or ['ethereum']
    errors: list[str] = []
    for network in candidates:
        try:
            return resolve_scanner_target(scanner, network, api_key='')
        except ValueError as exc:  # noqa: PERF203 - candidate list is 1-2 long
            errors.append(f'{network}: {exc}')
    raise ValueError(f'Cannot resolve scanner {scanner!r}: {"; ".join(errors)}')


def _config_id(scanner: str) -> str:
    """Configuration-manager id whose credential this scanner uses."""
    explicit = SCANNER_CONFIG_IDS.get(scanner)
    if explicit is not None:
        return explicit
    if SCANNER_RECORDS[scanner].kind == 'blockscout':
        return BLOCKSCOUT_CONFIG_IDS.get('ethereum', scanner)
    return scanner


def _credential_state(scanner: str) -> dict[str, Any]:
    """Whether *scanner* needs a credential, and whether one is resolvable."""
    config_id = _config_id(scanner)
    try:
        config = config_manager.get_scanner_config(config_id)
    except (ValueError, KeyError):
        return {'requires_api_key': True, 'configured': False, 'env_vars': []}

    try:
        configured = bool(config_manager.get_api_key(config_id))
    except Exception:  # noqa: BLE001 - a missing key is an answer, not a failure
        configured = False

    return {
        'requires_api_key': config.requires_api_key,
        'configured': configured,
        'env_vars': list(credential_env_names(config_id, config.name)),
    }


def _chains(scanner: str) -> list[str]:
    """Canonical chain names this scanner serves, asked one chain at a time.

    Two gates, because construction has two: the registry must resolve the
    chain for this scanner, and the scanner class must declare the resulting
    scanner-dialect network. Registry resolution alone passes chains the
    BlockScout legs have no instance for.
    """
    served: list[str] = []
    for chain_id in list_supported_chains():
        try:
            target = resolve_scanner_target(scanner, chain_id, api_key='')
        except ValueError:
            continue
        scanner_class = get_scanner_class(target.scanner_name, target.scanner_version)
        if target.scanner_network not in scanner_class.supported_networks:
            continue
        served.append(get_chain_name(chain_id))
    return sorted(served)


def _scanner_report(scanner: str) -> dict[str, Any]:
    """Everything the CLI knows about one public scanner name."""
    target = _identity(scanner)
    scanner_class = get_scanner_class(target.scanner_name, target.scanner_version)
    credentials = _credential_state(scanner)
    return {
        'scanner': scanner,
        'version': target.scanner_version,
        'keyless': not credentials['requires_api_key'],
        'api_key_configured': credentials['configured'],
        'api_key_env_vars': credentials['env_vars'],
        'methods_declared': len(scanner_class.SPECS),
        'methods_total': len(Method),
        'chains': _chains(scanner),
        'custom_base_url': scanner in CUSTOM_BASE_URL_SCANNERS,
        'result_window': scanner_class.result_window,
        'max_page_size': scanner_class.max_page_size,
    }


def _all_reports() -> list[dict[str, Any]]:
    return [_scanner_report(name) for name in sorted(SCANNER_RECORDS)]


def _credential_line(report: dict[str, Any]) -> str:
    if report['keyless']:
        return 'no API key required'
    primary = report['api_key_env_vars'][0] if report['api_key_env_vars'] else 'API key'
    state = 'configured' if report['api_key_configured'] else 'MISSING'
    return f'{primary} ({state})'


def cmd_scanners(args: argparse.Namespace) -> None:
    """List the providers this installation can construct."""
    reports = _all_reports()
    if args.json:
        json.dump(reports, sys.stdout, indent=2)
        sys.stdout.write('\n')
        return

    print('Providers available to ChainscanClient.from_config()')
    print('=' * 62)
    for report in reports:
        chains = report['chains']
        shown = ', '.join(chains[:6])
        if len(chains) > 6:
            shown += f' (+{len(chains) - 6} more)'
        print(f'\n{report["scanner"]}  ({report["version"]})')
        print(f'  credentials : {_credential_line(report)}')
        print(f'  methods     : {report["methods_declared"]}/{report["methods_total"]} declared')
        print(f'  chains      : {len(chains) or "-"}{"  " + shown if chains else ""}')
        window = report['result_window']
        page = report['max_page_size']
        print(
            '  pagination  : '
            + (f'result window {window}' if window else 'cursor-paginated, no result window')
            + (f', {page} items per page' if page else '')
        )
        if report['custom_base_url']:
            print('  custom URL  : accepts a self-hosted instance / proxy base URL')

    print('\nUsage: ChainscanClient.from_config(<scanner>, <chain>)')
    print('Chains: aiochainscan chains        Credentials: aiochainscan check')


def cmd_check(args: argparse.Namespace) -> None:
    """Report credential state, and where credentials were read from."""
    reports = _all_reports()
    keyless = [r for r in reports if r['keyless']]
    ready = [r for r in reports if not r['keyless'] and r['api_key_configured']]
    missing = [r for r in reports if not r['keyless'] and not r['api_key_configured']]
    env_files = _env_files()

    if args.json:
        json.dump(
            {
                'keyless': [r['scanner'] for r in keyless],
                'configured': [r['scanner'] for r in ready],
                'missing': {r['scanner']: r['api_key_env_vars'] for r in missing},
                'env_files': [str(path) for path in env_files],
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write('\n')
        return

    print('Credential status')
    print('=' * 62)
    print(f'\nUsable without a key ({len(keyless)}):')
    for report in keyless:
        print(f'  {report["scanner"]} ({report["version"]})')
    if ready:
        print(f'\nKey configured ({len(ready)}):')
        for report in ready:
            print(f'  {report["scanner"]}: {report["api_key_env_vars"][0]}')
    if missing:
        print(f'\nKey missing ({len(missing)}):')
        for report in missing:
            names = ', '.join(report['api_key_env_vars'][:2])
            print(f'  {report["scanner"]}: set one of {names}')

    if env_files:
        print('\nCredential files read (later entries override earlier ones):')
        for path in env_files:
            print(f'  {path}')
    else:
        print('\nNo credential files found. Environment variables still apply;')
        print("'aiochainscan generate-env' writes a template.")

    if not missing:
        print('\nEvery provider this installation knows is usable.')


def cmd_chains(args: argparse.Namespace) -> None:
    """List the chains the registry resolves, with the providers serving them."""
    coverage = {report['scanner']: set(report['chains']) for report in _all_reports()}
    rows: list[dict[str, Any]] = []
    for chain_id in sorted(list_supported_chains()):
        name = get_chain_name(chain_id)
        aliases = [alias for alias in get_chain_aliases(chain_id) if alias != name]
        providers = sorted(scanner for scanner, served in coverage.items() if name in served)
        row: dict[str, Any] = {
            'chain_id': chain_id,
            'name': name,
            'aliases': aliases,
            'scanners': providers,
        }
        if args.filter:
            needle = args.filter.lower()
            haystack = ' '.join([name, *aliases, str(chain_id)]).lower()
            if needle not in haystack:
                continue
        rows.append(row)

    if args.json:
        json.dump(rows, sys.stdout, indent=2)
        sys.stdout.write('\n')
        return

    if not rows:
        print(f'No chain matches {args.filter!r}.')
        return

    print(f'{"chain id":>9}  {"name":<14}  scanners')
    print('-' * 62)
    for row in rows:
        scanners = ', '.join(row['scanners']) or '(no built-in provider)'
        print(f'{row["chain_id"]:>9}  {row["name"]:<14}  {scanners}')
        if row['aliases']:
            print(f'{"":>9}  aliases: {", ".join(row["aliases"])}')


def cmd_generate_env(args: argparse.Namespace) -> None:
    """Write a credential template covering only the keys that are used."""
    lines = [
        '# aiochainscan credentials',
        '# Only the providers that need a key appear here; the BlockScout',
        '# scanners work without one.',
        '',
    ]
    for report in _all_reports():
        if report['keyless'] or not report['api_key_env_vars']:
            continue
        chains = report['chains']
        served = ', '.join(chains[:8]) + (' …' if len(chains) > 8 else '')
        lines += [
            f'# {report["scanner"]} ({report["version"]}) — chains: {served}',
            f'{report["api_key_env_vars"][0]}=',
            '',
        ]
    template = '\n'.join(lines)

    if args.output:
        output = Path(args.output)
        output.write_text(template)
        print(f'Wrote {output}', file=sys.stderr)
    else:
        sys.stdout.write(template)


def cmd_test(args: argparse.Namespace) -> None:
    """Perform one real request with the resolved configuration."""
    from aiochainscan import ChainscanClient

    address = args.address or PROBE_ADDRESS

    async def run() -> None:
        client = ChainscanClient.from_config(args.scanner, args.network)
        try:
            balance = await client.get_balance(address)
        finally:
            await client.close()
        print(f'{args.scanner}/{args.network}: get_balance({address}) -> {balance}')

    try:
        asyncio.run(run())
    except Exception as exc:
        print(
            f'{args.scanner}/{args.network} failed: {type(exc).__name__}: {exc}', file=sys.stderr
        )
        sys.exit(1)


def cmd_mcp(args: argparse.Namespace) -> None:
    """Run the MCP stdio server.

    Nothing may be written to stdout here: it is the transport.
    """
    from aiochainscan.mcp_server import MCP_AVAILABLE, create_mcp_server

    if not MCP_AVAILABLE:
        print('MCP not installed. Run: pip install "aiochainscan[mcp]"', file=sys.stderr)
        sys.exit(1)

    create_mcp_server().run()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='aiochainscan',
        description='Inspect what this aiochainscan installation can reach.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s scanners                       # providers, credentials, coverage
  %(prog)s check                          # credential status
  %(prog)s chains --filter base           # chains the registry resolves
  %(prog)s generate-env > .env            # template for the keys in use
  %(prog)s test blockscout_v2 ethereum    # one real request
        """,
    )
    subparsers = parser.add_subparsers(dest='command')

    scanners = subparsers.add_parser(
        'scanners', aliases=['list'], help='List available providers and their coverage'
    )
    scanners.add_argument('--json', action='store_true', help='Machine-readable output')
    scanners.set_defaults(func=cmd_scanners)

    check = subparsers.add_parser('check', help='Check credential status')
    check.add_argument('--json', action='store_true', help='Machine-readable output')
    check.set_defaults(func=cmd_check)

    chains = subparsers.add_parser('chains', help='List chains the registry resolves')
    chains.add_argument('--filter', help='Substring match on name, alias or chain id')
    chains.add_argument('--json', action='store_true', help='Machine-readable output')
    chains.set_defaults(func=cmd_chains)

    env = subparsers.add_parser('generate-env', help='Print a credential template')
    env.add_argument('--output', '-o', help='Write to this file instead of stdout')
    env.set_defaults(func=cmd_generate_env)

    test = subparsers.add_parser('test', help='Perform one real request with the current config')
    test.add_argument('scanner', help="Scanner name (e.g. 'etherscan', 'blockscout_v2')")
    test.add_argument(
        'network', nargs='?', default='ethereum', help="Chain name or id (default: 'ethereum')"
    )
    test.add_argument('--address', help=f'Address to query (default: {PROBE_ADDRESS})')
    test.set_defaults(func=cmd_test)

    mcp = subparsers.add_parser('mcp', help='Run the MCP stdio server')
    mcp.set_defaults(func=cmd_mcp)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not getattr(args, 'func', None):
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except KeyboardInterrupt:
        print('Interrupted', file=sys.stderr)
        sys.exit(130)


if __name__ == '__main__':
    main()
