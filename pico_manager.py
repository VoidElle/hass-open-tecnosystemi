"""Manager for Pico devices using shared transport."""
import logging
from typing import Dict

from open_pico_local_api.pico_client import PicoClient
from open_pico_local_api.shared_transport_manager import SharedTransportManager

_LOGGER = logging.getLogger(__name__)


class PicoClientManager:
    """
    Manager for multiple Pico devices using shared UDP transport.

    This class handles:
    - Shared transport initialization (single UDP socket for all devices)
    - Client creation with unique device IDs
    - Cleanup on shutdown
    """

    def __init__(self, local_port: int = 40069, verbose: bool = False):
        """Initialize the manager."""
        self._local_port = local_port
        self._verbose = verbose
        self._transport_manager = None
        self._clients: Dict[str, PicoClient] = {}
        self._initialized = False

    async def initialize(self):
        """Initialize the shared transport manager."""
        if self._initialized:
            _LOGGER.debug("PicoClientManager already initialized")
            return

        try:
            # Get singleton transport manager
            self._transport_manager = await SharedTransportManager.get_instance()

            # Initialize shared UDP socket
            await self._transport_manager.initialize(
                local_port=self._local_port,
                verbose=self._verbose
            )

            self._initialized = True
            _LOGGER.info("PicoClientManager initialized on port %d", self._local_port)

        except Exception as e:
            _LOGGER.error("Failed to initialize PicoClientManager: %s", e)
            raise

    def create_client(
        self,
        ip: str,
        pin: str,
        device_id: str = None,
        timeout: float = 15,
        retry_attempts: int = 3,
        retry_delay: float = 2.0
    ) -> PicoClient:
        """
        Create a new Pico client that uses the shared transport.

        Args:
            ip: Device IP address
            pin: Device PIN
            device_id: Optional unique device ID (defaults to IP)
            timeout: Request timeout in seconds
            retry_attempts: Number of retry attempts
            retry_delay: Delay between retries

        Returns:
            PicoClient instance configured for shared transport
        """
        if not self._initialized:
            raise RuntimeError("Manager not initialized. Call initialize() first.")

        # Generate device_id if not provided
        if device_id is None:
            device_id = f"pico_{ip.replace('.', '_')}"

        # Check if client already exists
        if device_id in self._clients:
            _LOGGER.warning("Client for device_id '%s' already exists, returning existing client", device_id)
            return self._clients[device_id]

        # Create new client with shared transport
        client = PicoClient(
            ip=ip,
            pin=pin,
            device_id=device_id,
            device_port=40070,
            local_port=self._local_port,
            timeout=timeout,
            retry_attempts=retry_attempts,
            retry_delay=retry_delay,
            verbose=self._verbose,
            use_shared_transport=True  # Key setting!
        )

        # Store client reference
        self._clients[device_id] = client

        _LOGGER.debug("Created PicoClient for device_id '%s' at %s", device_id, ip)

        return client

    async def shutdown(self):
        """Shutdown all clients and the shared transport."""
        _LOGGER.info("Shutting down PicoClientManager...")

        # Disconnect all clients
        for device_id, client in self._clients.items():
            try:
                if client.connected:
                    await client.disconnect()
                    _LOGGER.debug("Disconnected client '%s'", device_id)
            except Exception as e:
                _LOGGER.error("Error disconnecting client '%s': %s", device_id, e)

        # Clear clients
        self._clients.clear()

        # Shutdown shared transport
        if self._transport_manager:
            try:
                await self._transport_manager.shutdown()
                _LOGGER.info("Shared transport shutdown complete")
            except Exception as e:
                _LOGGER.error("Error shutting down shared transport: %s", e)

        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        """Check if manager is initialized."""
        return self._initialized

    @property
    def client_count(self) -> int:
        """Get number of registered clients."""
        return len(self._clients)

    def get_client(self, device_id: str) -> PicoClient | None:
        """Get a client by device_id."""
        return self._clients.get(device_id)