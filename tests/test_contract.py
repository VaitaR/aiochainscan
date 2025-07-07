from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from aiochainscan import Client


@pytest_asyncio.fixture
async def contract():
    c = Client('TestApiKey')
    yield c.contract
    await c.close()


@pytest.mark.asyncio
async def test_contract_abi(contract):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await contract.contract_abi('0x012345')
        mock.assert_called_once_with(
            params={'module': 'contract', 'action': 'getabi', 'address': '0x012345'}, headers={}
        )


@pytest.mark.asyncio
async def test_contract_source_code(contract):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await contract.contract_source_code('0x012345')
        mock.assert_called_once_with(
            params={'module': 'contract', 'action': 'getsourcecode', 'address': '0x012345'},
            headers={},
        )


@pytest.mark.asyncio
async def test_contract_creation(contract):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await contract.contract_creation(['0x012345', '0x678901'])
        mock.assert_called_once_with(
            params={
                'module': 'contract',
                'action': 'getcontractcreation',
                'contractaddresses': '0x012345,0x678901',
            },
            headers={},
        )


@pytest.mark.asyncio
async def test_verify_contract_source_code(contract):
    with patch('aiochainscan.network.Network.post', new=AsyncMock()) as mock:
        await contract.verify_contract_source_code(
            contract_address='0x012345',
            source_code='some source code\ntest',
            contract_name='some contract name',
            compiler_version='1.0.0',
            optimization_used=False,
            runs=123,
            constructor_arguements='some args',
        )
        mock.assert_called_once_with(
            data={
                'module': 'contract',
                'action': 'verifysourcecode',
                'contractaddress': '0x012345',
                'sourceCode': 'some source code\ntest',
                'contractname': 'some contract name',
                'compilerversion': '1.0.0',
                'optimizationUsed': 0,
                'runs': 123,
                'constructorArguements': 'some args',
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.post', new=AsyncMock()) as mock:
        await contract.verify_contract_source_code(
            contract_address='0x012345',
            source_code='some source code\ntest',
            contract_name='some contract name',
            compiler_version='1.0.0',
            optimization_used=False,
            runs=123,
            constructor_arguements='some args',
            libraries={'one_name': 'one_addr', 'two_name': 'two_addr'},
        )
        mock.assert_called_once_with(
            data={
                'module': 'contract',
                'action': 'verifysourcecode',
                'contractaddress': '0x012345',
                'sourceCode': 'some source code\ntest',
                'contractname': 'some contract name',
                'compilerversion': '1.0.0',
                'optimizationUsed': 0,
                'runs': 123,
                'constructorArguements': 'some args',
                'libraryname1': 'one_name',
                'libraryaddress1': 'one_addr',
                'libraryname2': 'two_name',
                'libraryaddress2': 'two_addr',
            },
            headers={},
        )


@pytest.mark.asyncio
async def test_check_verification_status(contract):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await contract.check_verification_status('some_guid')
        mock.assert_called_once_with(
            params={'module': 'contract', 'action': 'checkverifystatus', 'guid': 'some_guid'},
            headers={},
        )


async def test_verify_proxy_contract(contract):
    with patch('aiochainscan.network.Network.post', new=AsyncMock()) as mock:
        await contract.verify_proxy_contract(
            address='0x012345',
        )
        mock.assert_called_once_with(
            data={
                'module': 'contract',
                'action': 'verifyproxycontract',
                'address': '0x012345',
                'expectedimplementation': None,
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.post', new=AsyncMock()) as mock:
        await contract.verify_proxy_contract(
            address='0x012345',
            expected_implementation='0x54321',
        )
        mock.assert_called_once_with(
            data={
                'module': 'contract',
                'action': 'verifyproxycontract',
                'address': '0x012345',
                'expectedimplementation': '0x54321',
            },
            headers={},
        )


@pytest.mark.asyncio
async def test_check_proxy_contract_verification(contract):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await contract.check_proxy_contract_verification('some_guid')
        mock.assert_called_once_with(
            params={'module': 'contract', 'action': 'checkproxyverification', 'guid': 'some_guid'},
            headers={},
        )


def test_parse_libraries(contract):
    mydict = {
        'lib1': 'addr1',
        'lib2': 'addr2',
    }
    expected = {
        'libraryname1': 'lib1',
        'libraryaddress1': 'addr1',
        'libraryname2': 'lib2',
        'libraryaddress2': 'addr2',
    }
    assert contract._parse_libraries(mydict) == expected

    mydict = {
        'lib1': 'addr1',
    }
    expected = {
        'libraryname1': 'lib1',
        'libraryaddress1': 'addr1',
    }
    assert contract._parse_libraries(mydict) == expected

    mydict = {}
    expected = {}
    assert contract._parse_libraries(mydict) == expected
