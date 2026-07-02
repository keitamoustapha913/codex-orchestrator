# Rediscovery

Advanced repair classifications include:

- `OUTSIDE_KNOWN_GRAPH`
- `INVENTORY_CONTRADICTION`
- `MASTER_GOAL_CHANGED`
- `EXCESSIVE_IMPACTED_SCOPE`

Commands:

```bash
cxor rediscover --repo /path/to/target-repo --scope impacted
cxor rediscover --repo /path/to/target-repo --scope full
cxor rebuild-inventory --repo /path/to/target-repo --scope impacted
```

Rediscovery preserves prior failure and repair artifacts while writing durable rediscovery records.
