#!/usr/bin/env python3
"""
Демонстрация Moralis Web3 Data API интеграции.

Этот файл показывает полную интеграцию Moralis API в архитектуру aiochainscan
с тестированием ключевых функций: баланс, транзакции, токены.
"""

import asyncio
import os

from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method


async def test_moralis_balance():
    """Тестирование получения баланса через Moralis API."""

    print('💰 Тестирование баланса кошелька\n')

    # Используем корректное имя переменной
    api_key = os.getenv('MORALIS_KEY')
    if not api_key:
        print('❌ MORALIS_KEY environment variable not set')
        print("   Установите: export MORALIS_KEY='your_moralis_api_key'")
        return False

    # Тестовый адрес с активностью (Vitalik Buterin)
    test_address = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

    try:
        # Создаем клиент для Ethereum
        client = ChainscanClient(
            scanner_name='moralis',
            scanner_version='v1',
            api_kind='moralis',
            network='eth',
            api_key=api_key,
        )

        print(f'✅ Клиент создан: {client}')
        print('🔗 Сеть: Ethereum (chain: 0x1)')
        print(f'📍 Адрес: {test_address}')

        # Запрос баланса
        print('\n🔄 Запрашиваем баланс...')
        balance = await client.call(Method.ACCOUNT_BALANCE, address=test_address)

        print('✅ Успешно получен баланс!')
        print(f'   Raw balance: {balance}')

        # Конвертируем в ETH для удобства
        if isinstance(balance, int | str):
            balance_wei = int(balance)
            balance_eth = balance_wei / 10**18
            print(f'   💰 Баланс: {balance_eth:.6f} ETH')
            print(f'   💰 Баланс: {balance_wei:,} wei')

        await client.close()
        return True

    except Exception as e:
        print(f'❌ Ошибка при запросе баланса: {e}')
        return False


async def test_moralis_transactions():
    """Тестирование получения списка транзакций."""

    print('\n📄 Тестирование списка транзакций\n')

    api_key = os.getenv('MORALIS_KEY')
    if not api_key:
        print('❌ MORALIS_KEY не установлен')
        return False

    # Адрес с большой активностью для тестирования (Vitalik Buterin)
    test_address = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

    try:
        client = ChainscanClient(
            scanner_name='moralis',
            scanner_version='v1',
            api_kind='moralis',
            network='eth',
            api_key=api_key,
        )

        print(f'📍 Адрес: {test_address}')
        print('🔄 Запрашиваем историю транзакций...')

        # Запрос транзакций
        transactions = await client.call(Method.ACCOUNT_TRANSACTIONS, address=test_address)

        print('✅ Успешно получены транзакции!')
        print(f'   Raw response type: {type(transactions)}')

        if isinstance(transactions, list):
            print(f'   📊 Количество транзакций: {len(transactions)}')

            # Показываем первые несколько транзакций
            for i, tx in enumerate(transactions[:3]):
                print(f'\n   📄 Транзакция {i + 1}:')
                if isinstance(tx, dict):
                    print(f'      Hash: {tx.get("hash", "N/A")}')
                    print(f'      From: {tx.get("from", "N/A")}')
                    print(f'      To: {tx.get("to", "N/A")}')
                    print(f'      Value: {tx.get("value", "N/A")}')
                    print(f'      Block: {tx.get("block_number", "N/A")}')
                else:
                    print(f'      {tx}')

        elif isinstance(transactions, dict):
            print(f'   📋 Response keys: {list(transactions.keys())}')
            if 'result' in transactions:
                result = transactions['result']
                if isinstance(result, list):
                    print(f'   📊 Транзакций в result: {len(result)}')

        await client.close()
        return True

    except Exception as e:
        print(f'❌ Ошибка при запросе транзакций: {e}')
        print(f'   Тип ошибки: {type(e).__name__}')
        return False


async def test_moralis_tokens():
    """Тестирование получения токенов кошелька."""

    print('\n🪙 Тестирование токенов кошелька\n')

    api_key = os.getenv('MORALIS_KEY')
    if not api_key:
        print('❌ MORALIS_KEY не установлен')
        return False

    # Адрес с токенами (Vitalik Buterin)
    test_address = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

    try:
        client = ChainscanClient(
            scanner_name='moralis',
            scanner_version='v1',
            api_kind='moralis',
            network='eth',
            api_key=api_key,
        )

        print(f'📍 Адрес: {test_address}')
        print('🔄 Запрашиваем токены...')

        # Запрос токенов
        tokens = await client.call(Method.TOKEN_BALANCE, address=test_address)

        print('✅ Успешно получены токены!')
        print(f'   Raw response type: {type(tokens)}')

        if isinstance(tokens, list):
            print(f'   🪙 Количество токенов: {len(tokens)}')

            # Показываем первые несколько токенов
            for i, token in enumerate(tokens[:5]):
                print(f'\n   🪙 Токен {i + 1}:')
                if isinstance(token, dict):
                    print(f'      Symbol: {token.get("symbol", "N/A")}')
                    print(f'      Name: {token.get("name", "N/A")}')
                    print(f'      Balance: {token.get("balance", "N/A")}')
                    print(f'      Decimals: {token.get("decimals", "N/A")}')
                    print(f'      Contract: {token.get("token_address", "N/A")}')
                else:
                    print(f'      {token}')

        elif isinstance(tokens, dict):
            print(f'   📋 Response keys: {list(tokens.keys())}')

        await client.close()
        return True

    except Exception as e:
        print(f'❌ Ошибка при запросе токенов: {e}')
        return False


async def test_multi_chain_balance():
    """Тестирование мульти-чейн функциональности."""

    print('\n🌐 Тестирование мульти-чейн функциональности\n')

    api_key = os.getenv('MORALIS_KEY')
    if not api_key:
        print('❌ MORALIS_KEY не установлен')
        return False

    # Тестируем разные сети
    networks = {'eth': '0x1', 'bsc': '0x38', 'polygon': '0x89', 'base': '0x2105'}

    test_address = '0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3'

    for network, chain_id in networks.items():
        print(f'🔗 Тестируем {network.upper()} (chain: {chain_id})...')

        try:
            client = ChainscanClient(
                scanner_name='moralis',
                scanner_version='v1',
                api_kind='moralis',
                network=network,
                api_key=api_key,
            )

            balance = await client.call(Method.ACCOUNT_BALANCE, address=test_address)

            if isinstance(balance, int | str):
                balance_wei = int(balance)
                balance_native = balance_wei / 10**18
                print(f'   ✅ Баланс: {balance_native:.6f} нативных токенов')
            else:
                print(f'   ✅ Баланс: {balance}')

            await client.close()

        except Exception as e:
            print(f'   ❌ {network}: {e}')


async def compare_with_etherscan():
    """Сравнение результатов Moralis с Etherscan."""

    print('\n⚖️ Сравнение Moralis vs Etherscan\n')

    moralis_key = os.getenv('MORALIS_KEY')
    etherscan_key = os.getenv('ETHERSCAN_KEY')

    if not moralis_key:
        print('❌ MORALIS_KEY не установлен')
        return

    if not etherscan_key:
        print('❌ ETHERSCAN_KEY не установлен, сравнение только с Moralis')
        return

    test_address = '0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3'

    try:
        # Moralis
        print('🔄 Запрашиваем баланс через Moralis...')
        moralis_client = ChainscanClient(
            scanner_name='moralis',
            scanner_version='v1',
            api_kind='moralis',
            network='eth',
            api_key=moralis_key,
        )

        moralis_balance = await moralis_client.call(Method.ACCOUNT_BALANCE, address=test_address)
        await moralis_client.close()

        # Etherscan
        print('🔄 Запрашиваем баланс через Etherscan...')
        etherscan_client = ChainscanClient(
            scanner_name='etherscan',
            scanner_version='v1',
            api_kind='eth',
            network='main',
            api_key=etherscan_key,
        )

        etherscan_balance = await etherscan_client.call(
            Method.ACCOUNT_BALANCE, address=test_address
        )
        await etherscan_client.close()

        # Сравнение
        print('\n📊 Результаты сравнения:')
        print(f'   Moralis:   {moralis_balance}')
        print(f'   Etherscan: {etherscan_balance}')

        if str(moralis_balance) == str(etherscan_balance):
            print('   ✅ Результаты совпадают!')
        else:
            print('   ⚠️ Результаты отличаются (может быть из-за времени запроса)')

    except Exception as e:
        print(f'❌ Ошибка при сравнении: {e}')


async def main():
    """Основная функция демонстрации."""

    print('🚀 Демонстрация Moralis Web3 Data API интеграции')
    print('=' * 60)

    # Проверка наличия API ключа
    api_key = os.getenv('MORALIS_KEY')
    if not api_key:
        print('\n❌ Для запуска демо необходим API ключ Moralis')
        print("   Установите: export MORALIS_KEY='your_moralis_api_key'")
        print('   Получить ключ: https://admin.moralis.io/')
        return

    print(f'✅ API ключ найден: {api_key[:8]}...')

    # Запуск тестов
    results = []

    results.append(await test_moralis_balance())
    results.append(await test_moralis_transactions())
    results.append(await test_moralis_tokens())
    await test_multi_chain_balance()
    await compare_with_etherscan()

    # Итоги
    print('\n' + '=' * 60)
    print('📊 Итоги тестирования:')

    successful_tests = sum(results)
    total_tests = len(results)

    print(f'   ✅ Успешных тестов: {successful_tests}/{total_tests}')

    if successful_tests == total_tests:
        print('   🎉 Все тесты прошли успешно!')
        print('   🔗 Moralis API полностью интегрирован в aiochainscan')
    else:
        print('   ⚠️ Некоторые тесты не прошли')
        print('   🔧 Проверьте API ключ и подключение к интернету')

    print('\n✨ Демонстрация завершена!')


if __name__ == '__main__':
    asyncio.run(main())
