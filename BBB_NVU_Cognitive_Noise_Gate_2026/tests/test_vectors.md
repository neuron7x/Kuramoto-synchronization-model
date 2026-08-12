# Test Vectors

```yaml
TV001:
  name: Stable
  input:
    BSI: 20
    NRI: 15
    VML: 25
    GRS: 75
    CNI: 20
    confidence: 0.90
  expected: GREEN_STABLE

TV002:
  name: Watch by confidence
  input:
    BSI: 20
    NRI: 15
    VML: 25
    GRS: 75
    CNI: 20
    confidence: 0.62
  expected: YELLOW_WATCH

TV003:
  name: Orange by two domains
  input:
    BSI: 65
    NRI: 15
    VML: 61
    GRS: 70
    CNI: 20
    confidence: 0.85
  expected: ORANGE_RISK

TV004:
  name: Red by critical
  input:
    BSI: 82
    NRI: 15
    VML: 25
    GRS: 75
    CNI: 20
    confidence: 0.90
  expected: RED_CRITICAL

TV005:
  name: Invalid
  input:
    critical_data_invalid: true
  expected: BLACK_INVALID

TV006:
  name: Missing domain
  input:
    BSI: 20
    NRI: 20
    VML: 20
    CNI: 20
    confidence: 0.80
  expected_degradation:
    - missing_domain:GRS
```
