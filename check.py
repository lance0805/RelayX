import asyncio
import logging
import argparse
import aiohttp
# No longer need aiohttp_socks
import sys

# Setting up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('relayx.test')

# List of test target websites
TEST_SITES = [
    # "https://www.google.com",
    # "https://www.cloudflare.com",
    # "https://httpbin.org/get",
    "https://api.ipify.org",  # Returns your IP address
    # "http://example.com"      # Test regular HTTP
]

async def test_http_connection(url, proxy_host='127.0.0.1', proxy_port=8080, verify_ssl=False):
    """Test HTTP proxy connection"""
    try:
        logger.info(f"HTTP proxy connection test: {url} (via {proxy_host}:{proxy_port})")
        
        # Configure HTTP proxy
        proxy_url = f'http://{proxy_host}:{proxy_port}'
        
        async with aiohttp.ClientSession() as session:
            # The ssl parameter controls SSL verification with the target website
            ssl_context = None if verify_ssl else False
                
            async with session.get(url, proxy=proxy_url, timeout=20, ssl=ssl_context) as response:
                status = response.status
                content = await response.text()
                logger.info(f"Status code: {status}")
                logger.info(f"Content length: {len(content)} bytes")
                logger.info(f"Content: {content}")
                return True
    except Exception as e:
        if "Errno 61" in str(e):
            logger.error(f"Connection refused, target server may not be running: {e}")
        elif "[SSL]" in str(e):
            logger.error(f"SSL connection failed: {e}")
            logger.info("Try disabling SSL verification to solve this issue (use --no-verify-ssl option)")
        else:
            logger.error(f"Connection failed: {e}")
        return False

async def run_tests(proxy_host='127.0.0.1', proxy_port=8080, verify_ssl=False):
    """Run all tests"""
    logger.info("====== Starting HTTP proxy tests ======")
    logger.info(f"Proxy server: {proxy_host}:{proxy_port}")
    logger.info(f"SSL verification: {'enabled' if verify_ssl else 'disabled'}")
    
    # Test connections to various websites
    success_count = 0
    
    for url in TEST_SITES:
        result = await test_http_connection(url, proxy_host, proxy_port, verify_ssl)
        
        if result:
            success_count += 1
        
        logger.info(f"Test {url}: {'✅ Success' if result else '❌ Failed'}")
        logger.info("-" * 50)
    
    # Summary
    logger.info("====== Test Results Summary ======")
    logger.info(f"Proxy connection success rate: {success_count}/{len(TEST_SITES)} ({success_count/len(TEST_SITES)*100:.1f}%)")
    
    if success_count == 0:
        logger.error("❌ Test failed: All proxy connections failed")
    elif success_count < len(TEST_SITES):
        logger.warning(f"⚠️ Test partially passed: {success_count}/{len(TEST_SITES)} successful")
    else:
        logger.info("✅ Test passed: All proxy connections successful")

def parse_args():
    parser = argparse.ArgumentParser(description="Test HTTP proxy server")
    parser.add_argument('-H', '--host', type=str, default='127.0.0.1',
                        help="HTTP proxy server host (default: 127.0.0.1)")
    parser.add_argument('-p', '--port', type=int, default=8080,
                        help="HTTP proxy server port (default: 8080)")
    parser.add_argument('--verify-ssl', action='store_true', default=False,
                        help="Enable SSL verification (default: disabled)")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    
    try:
        asyncio.run(run_tests(args.host, args.port, args.verify_ssl))
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error occurred during testing: {e}")
        sys.exit(1)
