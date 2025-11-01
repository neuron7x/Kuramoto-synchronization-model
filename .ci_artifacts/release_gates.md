# Release Gates

- **latency**: {'passed': True, 'reason': None, 'metrics': {'median_ms': 50.3, 'p95_ms': 53.76, 'max_ms': 54.0, 'count': 7.0}}
- **coverage**: {'passed': True, 'observed': 0.937, 'required': 0.92}
- **performance**: {'passed': True, 'budgets': [{'component': 'order_router', 'observed_ms': 92.0, 'budget_ms': 110.0, 'passed': True}, {'component': 'link_activator', 'observed_ms': 68.0, 'budget_ms': 85.0, 'passed': True}, {'component': 'thermo_validator', 'observed_ms': 41.0, 'budget_ms': 60.0, 'passed': True}]}
- **energy**: {'passed': True, 'free_energy': 1.263632, 'entropy': 0.41023}
- **negative_tests**: {'degraded_high_latency': {'passed': False, 'free_energy': 2.096551}, 'degraded_packet_loss': {'passed': False, 'free_energy': 1.72422}}
- **passed**: True
