#!/usr/bin/env python3
"""
Command Line Interface for aiochainscan configuration management.

This CLI tool helps developers and users manage their blockchain scanner configurations,
API keys, and generate necessary configuration files.
"""

import argparse
import sys
from pathlib import Path

from aiochainscan.config import config_manager

# One of the files ConfigurationManager loads scanners from at startup.
DEFAULT_SCANNER_CONFIG_FILE = 'aiochainscan.json'


def cmd_list_scanners(args: argparse.Namespace) -> None:
    """List all available scanners and their status."""
    print('🔍 Available Blockchain Scanners')
    print('=' * 50)

    configs = config_manager.list_all_configurations()

    for scanner_id, info in configs.items():
        status = '✅ READY' if info['api_key_configured'] else '❌ NO API KEY'
        networks = ', '.join(info['networks'][:3])
        if len(info['networks']) > 3:
            networks += f' (+{len(info["networks"]) - 3} more)'

        print(f'\n📋 {scanner_id.upper()}: {info["name"]}')
        print(f'   Domain: {info["domain"]}')
        print(f'   Currency: {info["currency"]}')
        print(f'   Networks: {networks}')
        print(f'   Status: {status}')

        if not info['api_key_configured'] and info['requires_api_key']:
            print(f'   💡 Set one of: {", ".join(info["api_key_sources"][:2])}')


def cmd_generate_env(args: argparse.Namespace) -> None:
    """Generate .env template file."""
    output_file = Path(args.output) if args.output else Path.cwd() / '.env.example'

    template = config_manager.generate_env_template(output_file)

    print(f'✅ Generated .env template at: {output_file}')
    print('\n📝 Next steps:')
    print(f'1. Copy {output_file.name} to .env')
    print('2. Fill in your API keys')
    print('3. Make sure .env is in your .gitignore')

    if args.show:
        print('\n📄 Template content:')
        print('-' * 40)
        print(template)


def cmd_check_config(args: argparse.Namespace) -> None:
    """Check current configuration status."""
    print('🔧 Configuration Status Check')
    print('=' * 50)

    configs = config_manager.list_all_configurations()

    # Count statistics
    total_scanners = len(configs)
    configured_scanners = sum(1 for c in configs.values() if c['api_key_configured'])

    print(f'\n📊 Summary: {configured_scanners}/{total_scanners} scanners configured')

    # Group by status
    ready_scanners = []
    missing_scanners = []

    for scanner_id, info in configs.items():
        if info['api_key_configured']:
            ready_scanners.append((scanner_id, info))
        elif info['requires_api_key']:
            missing_scanners.append((scanner_id, info))

    if ready_scanners:
        print(f'\n✅ Ready scanners ({len(ready_scanners)}):')
        for scanner_id, info in ready_scanners:
            print(f'   • {scanner_id}: {info["name"]}')

    if missing_scanners:
        print(f'\n❌ Missing API keys ({len(missing_scanners)}):')
        for scanner_id, info in missing_scanners:
            primary_env = (
                info['api_key_sources'][0]
                if info['api_key_sources']
                else f'{scanner_id.upper()}_KEY'
            )
            print(f'   • {scanner_id}: Set {primary_env}')

    # Check for .env files
    env_files = [
        Path.cwd() / '.env',
        Path.cwd() / '.env.local',
        Path.home() / '.aiochainscan' / '.env',
    ]

    existing_env_files = [f for f in env_files if f.exists()]

    if existing_env_files:
        print('\n📁 Found .env files:')
        for env_file in existing_env_files:
            print(f'   • {env_file}')
    else:
        print("\n💡 No .env files found. Use 'aiochainscan generate-env' to create one.")


def cmd_add_scanner(args: argparse.Namespace) -> None:
    """Add a custom scanner configuration."""
    scanner_data = {
        'name': args.name,
        'base_domain': args.domain,
        'currency': args.currency,
        'supported_networks': args.networks.split(',') if args.networks else ['main'],
        'requires_api_key': not args.no_api_key,
        'special_config': {},
    }

    try:
        config_manager.register_scanner(args.id, scanner_data)

        if args.save is not None:
            config_file = Path(args.save)
            config_manager.persist_scanner(args.id, config_file)
            print(f'✅ Successfully added scanner: {args.id}')
            print(f'   Saved to: {config_file}')
        else:
            print(f'✅ Registered scanner for this process only: {args.id}')

        print(f'   Name: {scanner_data["name"]}')
        print(f'   Domain: {scanner_data["base_domain"]}')
        print(f'   Networks: {", ".join(scanner_data["supported_networks"])}')

        if args.save is None:
            print('   💡 Nothing was written to disk. Pass --save to persist it,')
            print(f'      e.g. --save {DEFAULT_SCANNER_CONFIG_FILE}')

        if scanner_data['requires_api_key']:
            suggestions = config_manager._get_api_key_suggestions(args.id)
            print(f'   💡 Set API key with: {suggestions[0]}=your_api_key')

    except (ValueError, OSError) as e:
        print(f'❌ Error adding scanner: {e}')
        sys.exit(1)


def cmd_export_config(args: argparse.Namespace) -> None:
    """Export current configuration to JSON."""
    output_file = Path(args.output)

    try:
        config_manager.export_config(output_file)
        print(f'✅ Configuration exported to: {output_file}')
    except Exception as e:
        print(f'❌ Export failed: {e}')
        sys.exit(1)


def cmd_test_scanner(args: argparse.Namespace) -> None:
    """Test a scanner configuration."""
    import asyncio

    from aiochainscan import ChainscanClient, Method

    async def test_scanner() -> None:
        print(f'🧪 Testing {args.scanner} scanner...')
        client = None

        try:
            client = ChainscanClient.from_config(args.scanner, args.network)
            print('✅ Client created successfully')

            # Test a simple API call using a universally supported method
            # Use ACCOUNT_BALANCE as it's supported by all scanners
            # Use a well-known address (Vitalik's) for consistent testing
            result = await client.call(
                Method.ACCOUNT_BALANCE,
                address='0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',
            )
            print(f'✅ API test successful - got response: {type(result)}')
            print(f'✅ Scanner {args.scanner} is working correctly')

        except Exception as e:
            print(f'❌ API test failed: {e}')
            print(f'❌ Scanner test failed: {e}')
            sys.exit(1)
        finally:
            if client is not None:
                await client.close()

    asyncio.run(test_scanner())


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='aiochainscan configuration management CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list                              # List all scanners
  %(prog)s check                             # Check configuration status
  %(prog)s generate-env                      # Generate .env template
  %(prog)s generate-env --output .env.dev    # Generate custom .env file
  %(prog)s test etherscan                    # Test Ethereum scanner
  %(prog)s add-scanner custom_chain --name "Custom Chain" --domain "customscan.io"
        """,
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # List scanners command
    list_parser = subparsers.add_parser('list', help='List all available scanners')
    list_parser.set_defaults(func=cmd_list_scanners)

    # Check configuration command
    check_parser = subparsers.add_parser('check', help='Check configuration status')
    check_parser.set_defaults(func=cmd_check_config)

    # Generate .env template command
    env_parser = subparsers.add_parser('generate-env', help='Generate .env template')
    env_parser.add_argument('--output', '-o', help='Output file path (default: .env.example)')
    env_parser.add_argument('--show', '-s', action='store_true', help='Show template content')
    env_parser.set_defaults(func=cmd_generate_env)

    # Add custom scanner command
    add_parser = subparsers.add_parser('add-scanner', help='Add custom scanner')
    add_parser.add_argument('id', help='Scanner ID (e.g., "custom_chain")')
    add_parser.add_argument('--name', required=True, help='Scanner display name')
    add_parser.add_argument('--domain', required=True, help='Base domain')
    add_parser.add_argument('--currency', required=True, help='Currency symbol')
    add_parser.add_argument('--networks', help='Comma-separated networks (default: main)')
    add_parser.add_argument(
        '--no-api-key', action='store_true', help='Scanner does not require API key'
    )
    add_parser.add_argument(
        '--save',
        nargs='?',
        const=DEFAULT_SCANNER_CONFIG_FILE,
        default=None,
        metavar='PATH',
        help=(
            'Persist the scanner into a JSON config file '
            f'(default: {DEFAULT_SCANNER_CONFIG_FILE}); without it the registration '
            'lives only for this process'
        ),
    )
    add_parser.set_defaults(func=cmd_add_scanner)

    # Export configuration command
    export_parser = subparsers.add_parser('export', help='Export configuration to JSON')
    export_parser.add_argument('output', help='Output JSON file path')
    export_parser.set_defaults(func=cmd_export_config)

    # Test scanner command
    test_parser = subparsers.add_parser('test', help='Test scanner configuration')
    test_parser.add_argument('scanner', help='Scanner ID to test')
    test_parser.add_argument('--network', default='main', help='Network to test (default: main)')
    test_parser.set_defaults(func=cmd_test_scanner)

    # Parse arguments
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Execute command
    try:
        args.func(args)
    except KeyboardInterrupt:
        print('\n🛑 Operation cancelled')
        sys.exit(1)
    except Exception as e:
        print(f'❌ Unexpected error: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
