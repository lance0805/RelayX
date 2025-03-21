import asyncio
import logging
from pathlib import Path
import threading
from typing import Any, Optional, Self
import time
import os

import aiohttp
from mitmproxy import http
from mitmproxy.addons import default_addons, script
from mitmproxy.master import Master
from mitmproxy.options import Options

from aiohttp_socks import ProxyConnector
from swiftshadow.classes import ProxyInterface

logger = logging.getLogger("relayx.server")
proxy_logger = logging.getLogger("mitmproxy.proxy.server")
proxy_logger.setLevel(logging.WARNING)


class AioHttpAddon:
    """mitmproxy addon for handling requests using aiohttp"""

    def __init__(self, proxy_interface: ProxyInterface = None):
        self.proxy_interface = proxy_interface
        self.proxy = None
        self.proxy_updated = False
        self.timeout = 120
        self.active_connections = {}  # 跟踪活动连接
        self.connector = None  # Store the connector as an instance variable

    async def initialize(self):
        if self.proxy_interface and not self.proxy:
            self.proxy = self.proxy_interface.get()
            logger.info(
                f"Proxy initialized: {self.proxy.protocol}://{self.proxy.ip}:{self.proxy.port}"
            )
            self.proxy_updated = True

    async def _update_proxy(self, force=False):
        if self.proxy_interface and (force or not self.proxy):
            self.proxy = self.proxy_interface.get()
            logger.info(
                f"Proxy updated: {self.proxy.protocol}://{self.proxy.ip}:{self.proxy.port}"
            )
            self.proxy_updated = True

    def client_connected(self, client):
        """当客户端建立连接时调用"""
        conn_id = id(client)
        self.active_connections[conn_id] = True

    def client_disconnected(self, client):
        """当客户端断开连接时调用"""
        conn_id = id(client)
        if conn_id in self.active_connections:
            del self.active_connections[conn_id]

    async def request(self, flow: http.HTTPFlow) -> None:
        """Handle HTTP/HTTPS requests using aiohttp"""
        # Initialize retry counter
        retry_count = 0
        max_retries = 50
        last_error = None
        conn_id = id(flow.client_conn)

        # Get request information
        method = flow.request.method
        url = flow.request.url
        headers = dict(flow.request.headers)
        body = flow.request.content if flow.request.content else None

        # 设置一个总体超时时间
        start_time = time.time()
        max_total_time = 240

        while retry_count <= max_retries:
            # 检查连接是否已断开
            if (
                conn_id in self.active_connections
                and not self.active_connections[conn_id]
            ):
                logger.warning(
                    f"Client connection {conn_id} closed, aborting request to {url}"
                )
                flow.response = http.Response.make(
                    499, b"Client closed request", {"Content-Type": "text/plain"}
                )
                return

            try:
                # 在重试循环中检查超时
                if time.time() - start_time > max_total_time:
                    logger.warning(
                        f"Request to {url} exceeded maximum total time of {max_total_time}s, aborting"
                    )
                    flow.response = http.Response.make(
                        504, b"Request timeout", {"Content-Type": "text/plain"}
                    )
                    return

                # Create a connector if needed or if proxy has been updated
                if self.connector is None or self.proxy_updated:
                    # Close previous connector if it exists
                    if self.connector is not None:
                        await self.connector.close()

                    # Create new connector
                    self.connector = ProxyConnector.from_url(
                        f"{self.proxy.protocol}://{self.proxy.ip}:{self.proxy.port}"
                    )
                    self.proxy_updated = False

                # Use the stored connector
                async with aiohttp.request(
                    method=method,
                    url=url,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    headers=headers,
                    data=body,
                    allow_redirects=False,  # Let the client handle redirects
                    connector=self.connector,
                ) as resp:
                    # 读取响应内容
                    content = await resp.read()

                    # 构建响应头
                    resp_headers = dict(resp.headers)

                    # 设置响应
                    flow.response = http.Response.make(
                        resp.status, content, resp_headers
                    )
                    return

            except Exception as e:
                # 再次检查连接是否已断开
                if (
                    conn_id in self.active_connections
                    and not self.active_connections[conn_id]
                ):
                    logger.warning(
                        f"Client connection {conn_id} closed during retry, aborting request to {url}"
                    )
                    flow.response = http.Response.make(
                        499, b"Client closed request", {"Content-Type": "text/plain"}
                    )
                    return

                # Log error
                last_error = e
                logger.warning(
                    f"Request failed (attempt {retry_count + 1}/{max_retries + 1}): {e}"
                )

                self.proxy_interface.update()
                await self._update_proxy(force=True)

                # Increment retry counter
                retry_count += 1

                # If maximum retries reached, exit loop
                if retry_count > max_retries:
                    break

                # Use exponential backoff strategy
                delay = min(10, 0.5 * (2**retry_count))  # Maximum delay 10 seconds
                await asyncio.sleep(delay)

        # All retries failed, return error response
        logger.error(
            f"All {max_retries + 1} attempts failed for {url}. Last error: {last_error}"
        )
        flow.response = http.Response.make(
            502,
            f"Error after {max_retries + 1} attempts: {str(last_error)}".encode(),
            {"Content-Type": "text/plain"},
        )

    # Add a cleanup method to close the connector
    async def shutdown(self):
        if self.connector:
            await self.connector.close()
            self.connector = None


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

        # Create aiohttp addon
        self.http_addon = AioHttpAddon(proxy_interface=self.proxy_interface)

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
            await self.http_addon.initialize()
            self.proxy_thread = ThreadedMitmProxy(self.http_addon, **options)

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
