import asyncio
import logging
import argparse
import aiohttp
# 不再需要 aiohttp_socks
import sys

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('relayx.test')

# 测试目标网站列表
TEST_SITES = [
    # "https://www.google.com",
    # "https://www.cloudflare.com",
    # "https://httpbin.org/get",
    "https://api.ipify.org",  # 返回你的IP地址
    # "http://example.com"      # 测试普通HTTP
]

async def test_http_connection(url, proxy_host='127.0.0.1', proxy_port=8080, verify_ssl=False):
    """通过HTTP代理连接"""
    try:
        logger.info(f"HTTP代理连接测试: {url} (通过 {proxy_host}:{proxy_port})")
        
        # 配置HTTP代理
        proxy_url = f'http://{proxy_host}:{proxy_port}'
        
        async with aiohttp.ClientSession() as session:
            # 这里的ssl参数控制与目标网站的SSL验证
            ssl_context = None if verify_ssl else False
                
            async with session.get(url, proxy=proxy_url, timeout=20, ssl=ssl_context) as response:
                status = response.status
                content = await response.text()
                logger.info(f"状态码: {status}")
                logger.info(f"内容长度: {len(content)} 字节")
                logger.info(f"内容: {content}")
                return True
    except Exception as e:
        if "Errno 61" in str(e):
            logger.error(f"连接被拒绝，目标服务器可能未运行: {e}")
        elif "[SSL]" in str(e):
            logger.error(f"SSL连接失败: {e}")
            logger.info("尝试禁用SSL验证可能解决此问题（使用 --no-verify-ssl 选项）")
        else:
            logger.error(f"连接失败: {e}")
        return False

async def run_tests(proxy_host='127.0.0.1', proxy_port=8080, verify_ssl=False):
    """运行所有测试"""
    logger.info("====== 开始测试HTTP代理 ======")
    logger.info(f"代理服务器: {proxy_host}:{proxy_port}")
    logger.info(f"SSL验证: {'启用' if verify_ssl else '禁用'}")
    
    # 测试各网站连接
    success_count = 0
    
    for url in TEST_SITES:
        result = await test_http_connection(url, proxy_host, proxy_port, verify_ssl)
        
        if result:
            success_count += 1
        
        logger.info(f"测试 {url}: {'✅ 成功' if result else '❌ 失败'}")
        logger.info("-" * 50)
    
    # 总结
    logger.info("====== 测试结果摘要 ======")
    logger.info(f"代理连接成功率: {success_count}/{len(TEST_SITES)} ({success_count/len(TEST_SITES)*100:.1f}%)")
    
    if success_count == 0:
        logger.error("❌ 测试失败: 所有代理连接都失败了")
    elif success_count < len(TEST_SITES):
        logger.warning(f"⚠️ 测试部分通过: {success_count}/{len(TEST_SITES)} 成功")
    else:
        logger.info("✅ 测试通过: 所有代理连接都成功")

def parse_args():
    parser = argparse.ArgumentParser(description="测试HTTP代理服务器")
    parser.add_argument('-H', '--host', type=str, default='127.0.0.1',
                        help="HTTP代理服务器主机 (默认: 127.0.0.1)")
    parser.add_argument('-p', '--port', type=int, default=8080,
                        help="HTTP代理服务器端口 (默认: 8080)")
    parser.add_argument('--verify-ssl', action='store_true', default=False,
                        help="启用SSL验证 (默认: 禁用)")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    
    try:
        asyncio.run(run_tests(args.host, args.port, args.verify_ssl))
    except KeyboardInterrupt:
        logger.info("测试被用户中断")
        sys.exit(0)
    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}")
        sys.exit(1)
