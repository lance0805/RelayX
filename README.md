# RelayX

A flexible HTTP proxy relay service built with Python and asyncio. RelayX starts an HTTP proxy server on a specified port and forwards traffic through SwiftShadow proxies.

## Features

- HTTP proxy server implementation
- Integration with mitmproxy and rnet libraries for handling HTTP requests
- Integration with SwiftShadow proxy rotation library
- Automatic proxy rotation and failure handling
- Proxy list caching for improved performance
- Support for all HTTP methods (GET, POST, PUT, DELETE, etc.)
- Asynchronous architecture for high performance

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/relayx.git
cd relayx

# Install the package
pip install -e .
```

## Quick Start

1. Start the HTTP proxy server:
   ```bash
   python -m main -p 8080
   ```

2. Configure your applications to use the HTTP proxy at `localhost:8080`

3. Test the proxy connection:
   ```bash
   python check.py
   ```

## Usage

```
python -m main [-h] [-p PORT] [-b BIND] [-c CACHE_FOLDER]

Options:
  -h, --help            Show this help message and exit
  -p PORT, --port PORT  Port to run the HTTP proxy server on (default: 8080)
  -b BIND, --bind BIND  Host to run the HTTP proxy server on (default: 0.0.0.0)
  -c CACHE_FOLDER, --cache-folder CACHE_FOLDER
                        Path to the cache folder (default: /tmp/cache)
```

## Test Tool

RelayX provides a test script `check.py` to verify the proxy server functionality:

```
python check.py [-h] [-H HOST] [-p PORT] [--verify-ssl]

Options:
  -h, --help            Show this help message and exit
  -H HOST, --host HOST  HTTP proxy server host (default: 127.0.0.1)
  -p PORT, --port PORT  HTTP proxy server port (default: 8080)
  --verify-ssl          Enable SSL verification (default: disabled)
```

## Docker Deployment

RelayX provides Docker support. Use the following commands to build and run:

```bash
# Build Docker image
docker build -t relayx .

# Run Docker container
docker run -p 8080:8080 relayx
```

## Proxy Implementation

RelayX uses the following technologies:

- **mitmproxy**: As the base HTTP proxy server, supporting TLS interception and HTTP/2
- **rnet**: For sending HTTP requests
- **SwiftShadow**: For managing and rotating proxies

Each time a connection fails, the system automatically rotates to a new proxy, with up to 50 retries, ensuring high availability.

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
