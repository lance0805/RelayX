import asyncio
import logging
from pathlib import Path
import threading
from typing import Any, Optional, Self

from rnet import Client, Impersonate
from mitmproxy import http
from mitmproxy.addons import default_addons, script
from mitmproxy.master import Master
from mitmproxy.options import Options

from swiftshadow.classes import ProxyInterface

logger = logging.getLogger("relayx.server")
proxy_logger = logging.getLogger("mitmproxy.proxy.server")
proxy_logger.setLevel(logging.WARNING)


class RnetAddon:
    """mitmproxy addon for handling requests using rnet"""

    def __init__(self, proxy_interface: ProxyInterface = None):
        self.client = Client(impersonate=Impersonate.Chrome133)
        self.proxy_interface = proxy_interface
        self.proxy = None
        self.proxy_updated = False
        
    async def initialize(self):
        if self.proxy_interface and not self.proxy:
            self.proxy = self.proxy_interface.get()
            logger.info(f"Proxy initialized: {self.proxy.protocol}://{self.proxy.ip}:{self.proxy.port}")
            self.proxy_updated = True

    async def _update_proxy(self, force=False):
        if self.proxy_interface and (force or not self.proxy):
            self.proxy = self.proxy_interface.get()
            logger.info(f"Proxy updated: {self.proxy.protocol}://{self.proxy.ip}:{self.proxy.port}")
            self.proxy_updated = True

    async def request(self, flow: http.HTTPFlow) -> None:
        """Handle HTTP/HTTPS requests"""
        # Initialize retry counter
        retry_count = 0
        max_retries = 50
        last_error = None

        # Get request information
        method = flow.request.method
        url = flow.request.url
        headers = dict(flow.request.headers)
        body = flow.request.content if flow.request.content else b""

        while retry_count <= max_retries:
            try:
                
                # Configure proxy (if available)
                proxy_url = f"{self.proxy.protocol}://{self.proxy.ip}:{self.proxy.port}"

                # Send request using rnet
                if method == "GET":
                    resp = await self.client.get(url, headers=headers, proxy=proxy_url)
                elif method == "POST":
                    resp = await self.client.post(
                        url, headers=headers, data=body, proxy=proxy_url
                    )
                elif method == "PUT":
                    resp = await self.client.put(
                        url, headers=headers, data=body, proxy=proxy_url
                    )
                elif method == "DELETE":
                    resp = await self.client.delete(
                        url, headers=headers, proxy=proxy_url
                    )
                elif method == "HEAD":
                    resp = await self.client.head(url, headers=headers, proxy=proxy_url)
                elif method == "OPTIONS":
                    resp = await self.client.options(
                        url, headers=headers, proxy=proxy_url
                    )
                elif method == "PATCH":
                    resp = await self.client.patch(
                        url, headers=headers, data=body, proxy=proxy_url
                    )
                else:
                    # Unsupported method
                    flow.response = http.Response.make(
                        501, b"Method not implemented", {"Content-Type": "text/plain"}
                    )
                    return

                # Request successful, set response and return
                content = await resp.bytes()
                flow.response = http.Response.make(
                    int(str(resp.status_code)), content, dict(resp.headers.items())
                )

                # Successful return, exit retry loop
                return

            except Exception as e:
                # Log error
                last_error = e
                logger.warning(
                    f"Request failed (attempt {retry_count + 1}/{max_retries + 1}): {e}"
                )

                # Update proxy only on failure
                self.proxy_interface.update()
                await self._update_proxy(force=True)

                # Increment retry counter
                retry_count += 1

                # If maximum retries reached, exit loop
                if retry_count > max_retries:
                    break

                # Short delay before retrying
                await asyncio.sleep(0.5)

        # All retries failed, return error response
        logger.error(
            f"All {max_retries + 1} attempts failed for {url}. Last error: {last_error}"
        )
        flow.response = http.Response.make(
            502,
            f"Error after {max_retries + 1} attempts: {str(last_error)}".encode(),
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
            cachePeriod=24 * 60,
            protocol="http",
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
            await self.rnet_addon.initialize()
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
