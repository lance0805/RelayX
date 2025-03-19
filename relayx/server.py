import asyncio
import logging
import threading
from typing import Dict, Any, Self

from rnet import Client, Impersonate, Proxy
from mitmproxy import http
from mitmproxy.addons import default_addons, script
from mitmproxy.master import Master
from mitmproxy.options import Options

from swiftshadow.classes import ProxyInterface

logger = logging.getLogger("relayx.server")


class RnetAddon:
    """mitmproxy插件，用于使用rnet处理请求"""

    def __init__(self, proxy_interface: ProxyInterface = None):
        self.client = Client(impersonate=Impersonate.Firefox136)
        self.proxy_interface = proxy_interface
        self.proxy = None
        self.proxy_updated = False

    async def _update_proxy(self):
        """更新代理设置"""
        if self.proxy_interface:
            self.proxy = self.proxy_interface.get()
            logger.info(
                f"Proxy updated: {self.proxy.protocol}://{self.proxy.ip}:{self.proxy.port}"
            )

    async def request(self, flow: http.HTTPFlow) -> None:
        """处理HTTP/HTTPS请求"""
        # 初始化重试计数器
        retry_count = 0
        max_retries = 50
        last_error = None

        # 获取请求信息
        method = flow.request.method
        url = flow.request.url
        headers = dict(flow.request.headers)
        body = flow.request.content if flow.request.content else b""

        while retry_count <= max_retries:
            try:
                # 每次尝试前更新代理
                await self._update_proxy()

                # 记录当前尝试信息
                if retry_count > 0:
                    logger.info(f"Retry #{retry_count} for {method} request to {url}")
                else:
                    logger.info(f"RnetAddon: {method} request to {url}")

                # 配置代理(如果有)
                proxy_url = f"{self.proxy.protocol}://{self.proxy.ip}:{self.proxy.port}"
                logger.info(f"Using proxy {proxy_url}")

                # 使用rnet发送请求
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
                    # 不支持的方法
                    flow.response = http.Response.make(
                        501, b"Method not implemented", {"Content-Type": "text/plain"}
                    )
                    return

                # 请求成功，设置响应并返回
                content = await resp.bytes()
                flow.response = http.Response.make(
                    int(str(resp.status_code)), content, dict(resp.headers.items())
                )

                # 成功返回，退出重试循环
                return

            except Exception as e:
                # 记录错误
                last_error = e
                logger.warning(
                    f"Request failed (attempt {retry_count + 1}/{max_retries + 1}): {e}"
                )

                # 强制更新代理
                self.proxy_interface.update()

                # 增加重试计数
                retry_count += 1

                # 如果达到最大重试次数，跳出循环
                if retry_count > max_retries:
                    break

                # 短暂延迟后重试
                await asyncio.sleep(0.5)

        # 所有重试都失败，返回错误响应
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
        # 创建事件循环
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        # 创建Master
        self.master = Master(Options(), event_loop=self.loop)

        # 添加默认插件，替换ScriptLoader为用户自定义addon
        self.master.addons.add(
            *(
                user_addon if isinstance(addon, script.ScriptLoader) else addon
                for addon in default_addons()
            )
        )

        # 设置选项
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
    def __init__(self, port: int, config: Dict[str, Any]):
        self.port = port
        self.config = config
        self.proxy_thread = None
        self.proxy_interface = ProxyInterface(
            autoRotate=True,
            autoUpdate=False,
            maxProxies=100,
            cachePeriod=24 * 60,
            protocol="socks5",
        )

        # 创建rnet addon
        self.rnet_addon = RnetAddon(proxy_interface=self.proxy_interface)

    async def start(self):
        """启动mitmproxy代理服务器"""
        try:
            # 设置mitmproxy选项
            options = {
                "listen_host": "0.0.0.0",
                "listen_port": self.port,
                "http2": True,
                "ssl_insecure": True,
            }

            # 创建并启动线程化的mitmproxy
            await self.proxy_interface.async_update()
            self.proxy_thread = ThreadedMitmProxy(self.rnet_addon, **options)

            # 启动代理线程
            self.proxy_thread.__enter__()

            logger.info(f"HTTP proxy server started on port {self.port}")

            # 保持主线程运行直到收到停止信号
            stop_event = asyncio.Event()
            await stop_event.wait()

        except Exception as e:
            logger.error(f"Failed to start mitmproxy: {e}")
            raise

    def stop(self):
        """停止代理服务器"""
        if self.proxy_thread:
            self.proxy_thread.__exit__(None, None, None)
            logger.info("HTTP proxy server stopped")
