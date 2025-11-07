# MisanthropicAgent V2.1 Quick Start

## Training

```bash
python -m cli.train_agent --config configs/train.yaml --log-dir logs
```

## Evaluation

```bash
python -m cli.eval_agent --config configs/train.yaml --checkpoint logs/checkpoint.pt
```

## Metrics

Scrape Prometheus metrics:

```bash
curl localhost:9200/metrics
```
