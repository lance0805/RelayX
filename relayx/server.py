import asyncio
import logging
import threading
from pathlib import Path
from typing import Any, Optional, Self

from mitmproxy import http
from mitmproxy.addons import default_addons, script
from mitmproxy.master import Master
from mitmproxy.options import Options
from rnet import Client, Method, Proxy
from swiftshadow.classes import ProxyInterface

logger = logging.getLogger("relayx.server")
proxy_logger = logging.getLogger("mitmproxy.proxy.server")
proxy_logger.setLevel(logging.WARNING)


class RnetAddon:
    """mitmproxy addon for handling requests using rnet"""

    def __init__(self, proxy_interface: ProxyInterface = None):
        self.client = Client(
            verify=False,
        )
        self.proxy_interface = proxy_interface
        self.proxies = {}
        self.timeout = 60
        self.session_header = "X-Browser-Session-ID"
        self.proxy_lock = asyncio.Lock()

    async def request(self, flow: http.HTTPFlow) -> None:
        """Handle HTTP/HTTPS requests"""
        # Get request information
        method = flow.request.method
        url = flow.request.url
        headers = dict(flow.request.headers)
        body = flow.request.content if flow.request.content else b""

        # Extract session ID from User-Agent
        ua_key = "User-Agent"
        user_agent = headers.get(ua_key, "")
        if not user_agent:
            ua_key = "user-agent"
            user_agent = headers.get(ua_key, "")
        session_id = None

        # Look for "SessionID/" pattern in User-Agent
        if "SessionID/" in user_agent:
            try:
                # Split by "SessionID/" to get parts before and after
                ua_parts = user_agent.split("SessionID/")
                base_ua = ua_parts[0].strip()
                session_id = ua_parts[1].strip()

                # Clean the User-Agent by removing the SessionID part
                headers[ua_key] = base_ua.rstrip()
            except (IndexError, AttributeError):
                session_id = None

        if not session_id:
            logger.warning(f"Request missing SessionID in User-Agent: {url}")
            flow.response = http.Response.make(
                502,
                "Missing SessionID in User-Agent".encode(),
                {"Content-Type": "text/plain"},
            )
            return

        # Use lock for thread-safe proxy assignment
        async with self.proxy_lock:
            if session_id not in self.proxies and self.proxy_interface:
                logger.info(f"Assigning new proxy for session {session_id}")
                self.proxies[session_id] = self.proxy_interface.get()

        current_proxy = self.proxies.get(session_id)
        if not current_proxy:
            # Fallback if we somehow don't have a proxy
            flow.response = http.Response.make(
                502,
                "No proxy available".encode(),
                {"Content-Type": "text/plain"},
            )
            return

        try:
            proxy_url = (
                f"{current_proxy.protocol}://{current_proxy.ip}:{current_proxy.port}"
            )
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

    # Optional: Clean up method to remove unused sessions
    def cleanup_sessions(self, max_age=3600):  # 1 hour by default
        """Remove sessions that haven't been used for a while"""
        # Implementation would depend on if you want to track session activity times


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
