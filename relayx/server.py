import asyncio
import logging
import threading
from pathlib import Path
from typing import Any, Optional, Self

from mitmproxy import http
from mitmproxy.addons import default_addons, script
from mitmproxy.master import Master
from mitmproxy.options import Options
from rnet import Client, Impersonate, ImpersonateOS, Method, Proxy
from swiftshadow.classes import ProxyInterface

logger = logging.getLogger("relayx.server")
proxy_logger = logging.getLogger("mitmproxy.proxy.server")
proxy_logger.setLevel(logging.WARNING)


class RnetAddon:
    """mitmproxy addon for handling requests using rnet"""

    def __init__(self, proxy_interface: ProxyInterface = None):
        self.client = Client(
            verify=False,
            impersonate=Impersonate.Chrome101,
            impersonate_os=ImpersonateOS.MacOS,
        )
        self.proxy_interface = proxy_interface
        self.proxy = None
        self.timeout = 60

    def client_connected(self, client):
        self.proxy = self.proxy_interface.get()

    def client_disconnected(self, client):
        pass

    async def request(self, flow: http.HTTPFlow) -> None:
        """Handle HTTP/HTTPS requests"""
        # Get request information
        method = flow.request.method
        url = flow.request.url
        headers = dict(flow.request.headers)
        body = flow.request.content if flow.request.content else b""
        try:
            proxy_url = f"{self.proxy.protocol}://{self.proxy.ip}:{self.proxy.port}"
            rnet_method = getattr(Method, method.upper())
            resp = await self.client.request(
                rnet_method,
                url,
                headers=headers,
                data=body,
                proxy=Proxy.all(url=proxy_url),
                timeout=self.timeout,
            )

            # Request successful, set response and return
            content = await resp.bytes()
            flow.response = http.Response.make(
                int(str(resp.status_code)), content, dict(resp.headers.items())
            )
            resp.close()
            return

        except Exception as e:
            logger.warning(f"Request to {url} failed: {e}")
        flow.response = http.Response.make(
            502,
            "Gateway Error".encode(),
            {"Content-Type": "text/plain"},
        )


class ThreadedMitmProxy(threading.Thread):
    def __init__(self, user_addon, **options: Any) -> None:
        # Create event loop
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        # Create Master
        self.master = Master(Options(), event_loop=self.loop)

        # Add default plugins, replace ScriptLoader with user-defined addon
        self.master.addons.add(
            *(
                user_addon if isinstance(addon, script.ScriptLoader) else addon
                for addon in default_addons()
            )
        )

        # Set options
        self.master.options.update(**options)
        super().__init__(daemon=True)

    def run(self) -> None:
        self.loop.run_until_complete(self.master.run())

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, *_) -> None:
        self.master.shutdown()
        self.join()


class HttpProxy:
    def __init__(self, port: int, host: str, cache_folder_path: Optional[Path] = None):
        self.port = port
        self.host = host
        self.proxy_thread = None

        self.proxy_interface = ProxyInterface(
            autoRotate=True,
            autoUpdate=False,
            maxProxies=100,
            cachePeriod=2 * 60,
            protocol="socks5",
            cacheFolderPath=cache_folder_path,
        )

        # Create rnet addon
        self.rnet_addon = RnetAddon(proxy_interface=self.proxy_interface)

    async def start(self):
        """Start mitmproxy proxy server"""
        try:
            # Set mitmproxy options
            options = {
                "listen_host": self.host,
                "listen_port": self.port,
                "http2": True,
                "ssl_insecure": True,
            }

            # Create and start threaded mitmproxy
            await self.proxy_interface.async_update()
            self.proxy_thread = ThreadedMitmProxy(self.rnet_addon, **options)

            # Start proxy thread
            self.proxy_thread.__enter__()

            logger.info(
                f"HTTP proxy server started on port {self.port} and bind {self.host}"
            )

            # Keep main thread running until stop signal received
            stop_event = asyncio.Event()
            await stop_event.wait()

        except Exception as e:
            logger.error(f"Failed to start mitmproxy: {e}")
            raise

    def stop(self):
        """Stop proxy server"""
        if self.proxy_thread:
            self.proxy_thread.__exit__(None, None, None)
            logger.info("HTTP proxy server stopped")
