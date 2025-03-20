import argparse
import asyncio
import logging
from relayx.server import HttpProxy


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def parse_args():
    parser = argparse.ArgumentParser(description="RelayX - A HTTP proxy relay service")
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=8080,
        help="Port to run the HTTP proxy server on (default: 8080)",
    )
    parser.add_argument(
        "-b",
        "--bind",
        type=str,
        default="0.0.0.0",
        help="Host to run the HTTP proxy server on (default: 0.0.0.0)",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    setup_logging()
    logger = logging.getLogger("relayx")

    logger.info(f"Starting RelayX HTTP proxy server on port {args.port}")

    try:
        server = HttpProxy(args.port, args.bind)
        await server.start()
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Error starting server: {e}")
    finally:
        logger.info("Server stopped")


if __name__ == "__main__":
    asyncio.run(main())
