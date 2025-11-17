---
owner: execution@tradepulse
review_cadence: monthly
artifacts:
  - path: artifacts/configs/binance_prod_template.yaml
    checksum: sha256:89d2497eb56653accfaf725e180cf4c24dd5334bfbfc3ec63fada58eb83f0371
    size_bytes: 828
  - path: artifacts/configs/coinbase_prod_template.yaml
    checksum: sha256:8f82952d53039ed6c4e9221452f5f200d99c9af1296c4ff91a8fdd441dd28980
    size_bytes: 832
---

# Exchange Configuration Artifacts

## Overview

This dataset contract defines validated exchange execution configuration templates for production deployment. These YAML configuration overlays specify connection parameters, credentials management, rate limits, risk controls, and WebSocket settings for major cryptocurrency exchanges.

## Security Notice

⚠️ **CRITICAL**: These are **template** configurations only. They contain placeholder values and must be properly configured with real credentials before use in any environment. Never commit actual API keys, secrets, or passphrases to version control.

## Artifacts

### artifacts/configs/binance_prod_template.yaml

**Format**: YAML (YAML Ain't Markup Language)

**Description**: Production-ready configuration template for Binance exchange integration. Includes venue-specific settings for spot trading, rate limiting, risk management, and WebSocket connectivity.

**Schema**:

```yaml
execution:
  venues:
    binance:
      enabled: boolean               # Enable/disable Binance venue
      sandbox: boolean               # Use sandbox/testnet (true) or production (false)
      symbols: [string]              # List of trading pairs (e.g., BTCUSDT)
      credentials:
        env_prefix: string           # Environment variable prefix (e.g., BINANCE)
        required: [string]           # Required credential fields
        optional: [string]           # Optional credential fields
        secret_backend:
          adapter: string            # Secret management backend (vault, kms, env)
          path_env: string          # Environment variable for secret path
          field_mapping:            # Map credentials to backend fields
            KEY: string
      rate_limits:
        max_orders_per_second: int  # Order rate limit (per second)
        max_orders_per_minute: int  # Order rate limit (per minute)
      risk:
        max_notional_usd: float     # Maximum order size in USD
        max_position_usd: float     # Maximum position size in USD
      websocket:
        heartbeat_interval_sec: int # WebSocket heartbeat interval
        reconnect_jitter_sec: float # Reconnection jitter for backoff
```

**Characteristics**:
- **Sandbox Mode**: Enabled by default for safety
- **Conservative Rate Limits**: 10 orders/second, 600/minute
- **Risk Controls**: $25k max order, $50k max position
- **Vault Integration**: Configured for HashiCorp Vault secret management
- **WebSocket Health**: 30-second heartbeat, 0.5s reconnect jitter

**Configuration Details**:

**Credentials Management**:
- **Environment Prefix**: `BINANCE` (looks for `BINANCE_API_KEY`, etc.)
- **Required Fields**: `API_KEY`, `API_SECRET`
- **Optional Fields**: `RECV_WINDOW` (request validity window)
- **Secret Backend**: HashiCorp Vault with path from `BINANCE_VAULT_PATH`

**Supported Symbols**:
- BTCUSDT (Bitcoin/Tether)
- ETHUSDT (Ethereum/Tether)
- Additional pairs can be added to the `symbols` list

**Rate Limiting**:
- Protects against exchange API rate limit violations
- Conservative defaults suitable for most use cases
- Can be increased if exchange permits higher limits

**Risk Parameters**:
- **Max Notional**: $25,000 per order (prevents fat-finger errors)
- **Max Position**: $50,000 total exposure per symbol
- Adjust based on account size and risk tolerance

**Use Cases**:
- Production deployment configuration
- Staging environment setup
- Local development with testnet
- CI/CD pipeline configuration
- Configuration documentation and examples

### artifacts/configs/coinbase_prod_template.yaml

**Format**: YAML

**Description**: Production-ready configuration template for Coinbase Advanced Trade API integration. Includes settings for portfolio management, authentication, rate limits, and risk controls specific to Coinbase's API structure.

**Schema**: Similar to Binance configuration with Coinbase-specific adaptations:

```yaml
execution:
  venues:
    coinbase:
      enabled: boolean
      sandbox: boolean
      symbols: [string]              # Coinbase format (BTC-USD, ETH-USD)
      credentials:
        env_prefix: string           # COINBASE
        required: [string]           # API_KEY, API_SECRET, PASSPHRASE
        secret_backend:
          adapter: string            # kms (Google Cloud KMS)
          path: string              # KMS key path
          field_mapping: {...}
      rate_limits:
        max_orders_per_second: int  # 5 orders/second
        max_orders_per_minute: int  # 150 orders/minute
      risk:
        max_notional_usd: float     # $15,000 max order
        max_position_usd: float     # $30,000 max position
      websocket:
        heartbeat_interval_sec: int # 20 seconds
        reconnect_jitter_sec: float # 0.5 seconds
```

**Characteristics**:
- **Sandbox Mode**: Enabled by default
- **Conservative Rate Limits**: 5 orders/second, 150/minute (Coinbase is more restrictive)
- **Risk Controls**: $15k max order, $30k max position
- **KMS Integration**: Configured for Google Cloud KMS
- **WebSocket Health**: 20-second heartbeat

**Configuration Details**:

**Credentials Management**:
- **Environment Prefix**: `COINBASE`
- **Required Fields**: `API_KEY`, `API_SECRET`, `PASSPHRASE` (Coinbase-specific)
- **Secret Backend**: Google Cloud KMS with full key path
- Passphrase is unique to Coinbase and must be securely stored

**Supported Symbols**:
- BTC-USD (Bitcoin/US Dollar)
- ETH-USD (Ethereum/US Dollar)
- Note: Coinbase uses dash notation (BTC-USD) vs Binance (BTCUSDT)

**Rate Limiting**:
- More conservative than Binance (Coinbase has stricter limits)
- 5 orders/second prevents API throttling
- 150 orders/minute daily limit compliance

**Risk Parameters**:
- **Max Notional**: $15,000 per order
- **Max Position**: $30,000 total exposure
- Lower limits reflect typical Coinbase retail/institutional split

**Use Cases**:
- Coinbase Advanced Trade integration
- Multi-exchange portfolio management
- Arbitrage strategy configuration
- Institutional trading setup
- Regulatory-compliant configuration

## Deployment Guide

### Step 1: Copy Template

```bash
# Copy to your deployment location
cp artifacts/configs/binance_prod_template.yaml config/exchanges/binance.yaml
```

### Step 2: Configure for Environment

Edit the copied file:

```yaml
execution:
  venues:
    binance:
      sandbox: false  # Set to false for production!
      symbols:
        - BTCUSDT
        - ETHUSDT
        # Add your trading pairs
```

### Step 3: Set Up Secret Management

#### Using HashiCorp Vault (Binance example)

```bash
# Store credentials in Vault
vault kv put secret/tradepulse/binance \
  api_key="your_api_key_here" \
  api_secret="your_api_secret_here" \
  recv_window="5000"

# Set environment variable
export BINANCE_VAULT_PATH="secret/tradepulse/binance"
```

#### Using Google Cloud KMS (Coinbase example)

```bash
# Create KMS keyring (one-time setup)
gcloud kms keyrings create tradepulse \
  --location=global

# Store encrypted credentials
gcloud kms keys create coinbase \
  --keyring=tradepulse \
  --location=global \
  --purpose=encryption

# Encrypt and store credentials
echo -n "your_api_key" | gcloud kms encrypt \
  --key=coinbase \
  --keyring=tradepulse \
  --location=global \
  --plaintext-file=- \
  --ciphertext-file=coinbase_api_key.enc
```

#### Using Environment Variables (Development only)

```bash
# .env file (NEVER commit this!)
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here

COINBASE_API_KEY=your_api_key_here
COINBASE_API_SECRET=your_api_secret_here
COINBASE_PASSPHRASE=your_passphrase_here
```

### Step 4: Adjust Risk Parameters

Customize risk limits based on your account:

```yaml
risk:
  max_notional_usd: 50000  # Increase if needed
  max_position_usd: 100000  # Adjust for account size
```

### Step 5: Enable Production Mode

**CRITICAL**: Only after thorough testing:

```yaml
sandbox: false  # Enable production mode
```

### Step 6: Test Configuration

```bash
# Validate configuration
python -m tradepulse config validate config/exchanges/binance.yaml

# Test connection (dry run)
python -m tradepulse exchange test --venue binance --dry-run

# Test with small order
python -m tradepulse exchange test --venue binance --test-order
```

## Security Best Practices

### Credential Management

1. **Never Hardcode**: Don't put credentials in config files
2. **Use Secret Backends**: Vault, KMS, AWS Secrets Manager
3. **Rotate Keys**: Regular rotation schedule (e.g., quarterly)
4. **Limit Permissions**: API keys with minimum required permissions
5. **Monitor Usage**: Log and alert on credential usage patterns

### Access Control

1. **Separate Credentials**: Different keys for prod/staging/dev
2. **IP Whitelisting**: Restrict API access to known IPs
3. **2FA Enforcement**: Enable on exchange accounts
4. **Audit Logs**: Maintain comprehensive access logs
5. **Key Expiration**: Set expiration dates on API keys

### Configuration Security

1. **Encrypt at Rest**: Encrypt configuration files containing sensitive settings
2. **Restrict File Permissions**: `chmod 600` for config files
3. **Version Control**: Never commit real credentials
4. **Audit Changes**: Review all configuration changes
5. **Backup Securely**: Encrypted backups of configurations

## Validation

To validate these configuration templates:

```bash
python scripts/validate_sample_data.py --repo-root . --format text
```

Expected output shows checksums matching for both templates.

## Maintenance

**Review Schedule**: Monthly
- Verify rate limits match current exchange specifications
- Update risk parameters based on portfolio growth
- Review and rotate credentials
- Test WebSocket connectivity
- Validate secret backend access

**Update Triggers**:
- Exchange API changes
- New trading pairs added
- Risk tolerance adjustments
- Security policy updates
- Compliance requirements changes

## Integration Examples

### Loading Configuration

```python
import yaml
from pathlib import Path

def load_exchange_config(exchange: str) -> dict:
    """Load exchange configuration from template."""
    config_path = Path(f"artifacts/configs/{exchange}_prod_template.yaml")
    with config_path.open() as f:
        return yaml.safe_load(f)

binance_config = load_exchange_config("binance")
print(f"Sandbox mode: {binance_config['execution']['venues']['binance']['sandbox']}")
```

### Applying Configuration

```python
from application.settings import Settings

# Load settings with exchange overlay
settings = Settings()
settings.load_overlay("artifacts/configs/binance_prod_template.yaml")

# Verify configuration
assert settings.execution.venues.binance.enabled
assert len(settings.execution.venues.binance.symbols) > 0
```

### Multi-Exchange Setup

```python
# Load both exchange configs
binance = load_exchange_config("binance")
coinbase = load_exchange_config("coinbase")

# Merge into unified config
unified_config = {
    "execution": {
        "venues": {
            **binance["execution"]["venues"],
            **coinbase["execution"]["venues"]
        }
    }
}

# Use in trading system
from execution.engine import ExecutionEngine
engine = ExecutionEngine(unified_config)
```

## Troubleshooting

### Authentication Failures

**Error**: `401 Unauthorized` or `Invalid API key`

**Solutions**:
1. Verify credentials in secret backend
2. Check API key permissions on exchange
3. Ensure correct environment prefix
4. Validate secret path environment variable

### Rate Limit Exceeded

**Error**: `429 Too Many Requests`

**Solutions**:
1. Reduce `max_orders_per_second` in config
2. Implement exponential backoff
3. Check for rate limit headers in responses
4. Distribute orders across time

### Connection Issues

**Error**: WebSocket disconnections or timeouts

**Solutions**:
1. Increase `heartbeat_interval_sec`
2. Adjust `reconnect_jitter_sec` for better backoff
3. Check network connectivity
4. Verify firewall rules allow WebSocket traffic

## Related Documentation

- [Execution System Documentation](../../execution/)
- [Application Settings](../../application/settings.py)
- [Exchange Integration Guide](../../docs/integrations/)
- [Security Framework](../../SECURITY_FRAMEWORK_SUMMARY.md)

## Changelog

### 2025-11-17
- Initial dataset contract creation
- Documented Binance and Coinbase production templates
- Added comprehensive deployment and security guides
- Included validation examples and troubleshooting
- Defined schema specifications and best practices
