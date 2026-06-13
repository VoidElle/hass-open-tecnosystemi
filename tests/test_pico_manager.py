"""Tests for PicoClientManager."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from custom_components.open_pico.pico_manager import PicoClientManager


@pytest.fixture
def mock_transport():
    transport = MagicMock()
    transport.initialize = AsyncMock()
    transport.shutdown = AsyncMock()
    return transport


@pytest.fixture
def manager():
    return PicoClientManager(local_port=40069, verbose=False)


class TestInit:
    def test_not_initialized_by_default(self, manager):
        assert not manager.is_initialized

    def test_client_count_zero(self, manager):
        assert manager.client_count == 0


class TestInitialize:
    async def test_initialize_calls_transport(self, manager, mock_transport):
        with patch(
            "custom_components.open_pico.pico_manager.SharedTransportManager"
        ) as MockSTM:
            MockSTM.get_instance = AsyncMock(return_value=mock_transport)
            await manager.initialize()

        assert manager.is_initialized
        mock_transport.initialize.assert_called_once_with(
            local_port=40069, verbose=False
        )

    async def test_double_initialize_is_noop(self, manager, mock_transport):
        with patch(
            "custom_components.open_pico.pico_manager.SharedTransportManager"
        ) as MockSTM:
            MockSTM.get_instance = AsyncMock(return_value=mock_transport)
            await manager.initialize()
            await manager.initialize()

        assert mock_transport.initialize.call_count == 1

    async def test_initialize_failure_propagates(self, manager):
        with patch(
            "custom_components.open_pico.pico_manager.SharedTransportManager"
        ) as MockSTM:
            transport = MagicMock()
            transport.initialize = AsyncMock(side_effect=OSError("port in use"))
            MockSTM.get_instance = AsyncMock(return_value=transport)

            with pytest.raises(OSError, match="port in use"):
                await manager.initialize()

        assert not manager.is_initialized


class TestCreateClient:
    async def _init(self, manager, mock_transport):
        with patch(
            "custom_components.open_pico.pico_manager.SharedTransportManager"
        ) as MockSTM:
            MockSTM.get_instance = AsyncMock(return_value=mock_transport)
            await manager.initialize()

    async def test_create_client_returns_client(self, manager, mock_transport):
        await self._init(manager, mock_transport)
        with patch("custom_components.open_pico.pico_manager.PicoClient") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance
            client = manager.create_client(ip="192.168.1.50", pin="1234", device_id="dev1")

        assert client is mock_instance
        assert manager.client_count == 1

    async def test_duplicate_device_id_returns_existing(self, manager, mock_transport):
        await self._init(manager, mock_transport)
        with patch("custom_components.open_pico.pico_manager.PicoClient") as MockClient:
            MockClient.return_value = MagicMock()
            c1 = manager.create_client(ip="192.168.1.50", pin="1234", device_id="dev1")
            c2 = manager.create_client(ip="192.168.1.51", pin="1234", device_id="dev1")

        assert c1 is c2
        assert manager.client_count == 1

    def test_create_before_init_raises(self, manager):
        with pytest.raises(RuntimeError, match="initialize"):
            manager.create_client(ip="192.168.1.50", pin="1234")

    async def test_auto_device_id_from_ip(self, manager, mock_transport):
        await self._init(manager, mock_transport)
        with patch("custom_components.open_pico.pico_manager.PicoClient") as MockClient:
            MockClient.return_value = MagicMock()
            manager.create_client(ip="10.0.0.1", pin="1234")
            call_kwargs = MockClient.call_args[1]

        assert call_kwargs["device_id"] == "pico_10_0_0_1"


class TestGetClient:
    async def test_get_existing_client(self, manager, mock_transport):
        with patch(
            "custom_components.open_pico.pico_manager.SharedTransportManager"
        ) as MockSTM:
            MockSTM.get_instance = AsyncMock(return_value=mock_transport)
            await manager.initialize()

        with patch("custom_components.open_pico.pico_manager.PicoClient") as MockClient:
            mc = MagicMock()
            MockClient.return_value = mc
            manager.create_client(ip="10.0.0.1", pin="1234", device_id="mydev")

        assert manager.get_client("mydev") is mc

    def test_get_missing_client_returns_none(self, manager):
        assert manager.get_client("nonexistent") is None


class TestShutdown:
    async def test_shutdown_disconnects_connected_clients(self, manager, mock_transport):
        with patch(
            "custom_components.open_pico.pico_manager.SharedTransportManager"
        ) as MockSTM:
            MockSTM.get_instance = AsyncMock(return_value=mock_transport)
            await manager.initialize()

        client = MagicMock()
        client.connected = True
        client.disconnect = AsyncMock()
        manager._clients["dev1"] = client

        await manager.shutdown()

        client.disconnect.assert_called_once()
        assert manager.client_count == 0
        assert not manager.is_initialized

    async def test_shutdown_skips_disconnected_clients(self, manager, mock_transport):
        with patch(
            "custom_components.open_pico.pico_manager.SharedTransportManager"
        ) as MockSTM:
            MockSTM.get_instance = AsyncMock(return_value=mock_transport)
            await manager.initialize()

        client = MagicMock()
        client.connected = False
        client.disconnect = AsyncMock()
        manager._clients["dev1"] = client

        await manager.shutdown()
        client.disconnect.assert_not_called()

    async def test_shutdown_calls_transport_shutdown(self, manager, mock_transport):
        with patch(
            "custom_components.open_pico.pico_manager.SharedTransportManager"
        ) as MockSTM:
            MockSTM.get_instance = AsyncMock(return_value=mock_transport)
            await manager.initialize()

        await manager.shutdown()
        mock_transport.shutdown.assert_called_once()
