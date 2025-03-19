# RelayX

A flexible SOCKS5 proxy relay service built with Python and asyncio. RelayX starts a SOCKS5 server on a specified port and forwards traffic through SwiftShadow proxies.

## Features

- SOCKS5 server implementation
- Integration with SwiftShadow proxy rotation library
- Support for multiple proxy sources:
  - Free public proxies
  - Proxies from a file
  - Custom defined proxies
- Automatic proxy rotation and failure handling
- Configurable via YAML configuration file
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

1. Create a configuration file:
   ```bash
   cp config.yml.example config.yml
   ```

2. Edit the configuration file if needed (default uses free proxies from SwiftShadow)

3. Start the SOCKS5 server:
   ```bash
   python -m relayx.main -p 1080
   ```

4. Configure your applications to use the SOCKS5 proxy at `localhost:1080`

## Usage

```
python -m relayx.main [-h] [-p PORT] [-c CONFIG]

Options:
  -h, --help            Show this help message and exit
  -p PORT, --port PORT  Port to run the SOCKS5 server on (default: 1080)
  -c CONFIG, --config CONFIG
                        Path to configuration file (default: config.yml)
```

## Configuration

RelayX uses a YAML configuration file for SwiftShadow proxy settings. See `config.yml.example` for a complete example.

### Example Configuration

```yaml
# SwiftShadow proxy configuration
swiftshadow:
  source: free  # Use free proxy sources
  name: SwiftShadow Proxy
  auto_rotate: true  # Automatically rotate proxies
  rotate_on_fail: true  # Rotate on connection failures
  max_failures: 3  # Maximum failures before rotating
  timeout: 10  # Connection timeout in seconds
```

## Proxy Sources

### Free Proxies

Use free public proxies automatically sourced by SwiftShadow:

```yaml
swiftshadow:
  source: free  # Use free proxy sources
  auto_rotate: true
  rotate_on_fail: true
```

### File-based Proxies

Load proxies from a text file:

```yaml
swiftshadow:
  source: file
  proxy_file: /path/to/proxies.txt  # Path to file with proxy list
  auto_rotate: true
```

### Custom Proxies

Define your own list of proxies:

```yaml
swiftshadow:
  source: custom
  proxies:
    - protocol: http
      host: proxy1.example.com
      port: 8080
      username: user1  # Optional
      password: pass1  # Optional
    - protocol: socks5
      host: proxy2.example.com
      port: 1080
  auto_rotate: true
```

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
