# Admin Module

## Overview

The `admin` module provides administrative tools and utilities for managing TradePulse deployments.

## Purpose

- **System Administration**: Manage system configuration and state
- **User Management**: User accounts and permissions
- **Maintenance**: System maintenance and cleanup tasks
- **Auditing**: Audit logs and compliance reporting

## Key Features

- 👤 **User Management**: Create, update, and manage users
- 🔐 **Access Control**: Role-based permissions
- 📝 **Audit Logging**: Track all administrative actions
- 🧹 **Maintenance**: Cleanup and optimization tasks

## Usage Examples

### User Management

```python
from admin import UserManager

user_mgr = UserManager()

# Create user
user = await user_mgr.create_user(
    username="trader1",
    email="trader1@example.com",
    role="trader"
)

# Update permissions
await user_mgr.grant_permission(user.id, "execute_trades")
```

### System Maintenance

```python
from admin import MaintenanceTasks

tasks = MaintenanceTasks()

# Run cleanup
await tasks.cleanup_old_logs(days=30)
await tasks.optimize_database()
await tasks.clear_cache()
```

## Configuration

```yaml
# config/admin.yaml
admin:
  audit_logging: true
  max_log_age_days: 90
  
  maintenance:
    auto_cleanup: true
    cleanup_schedule: "0 2 * * *"  # Daily at 2 AM
```

## License

See [LICENSE](../LICENSE) for licensing information.
