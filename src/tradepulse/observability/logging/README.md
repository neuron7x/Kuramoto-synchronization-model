# TradePulse Log Shipping

This directory contains configuration required to forward structured TradePulse
logs into the Elastic Stack when running via `docker-compose`.

## Components

* **Filebeat** autodiscovers containers labelled with
  `co.elastic.logs/enabled=true` and streams their JSON logs to Logstash.
* **Logstash** normalises the payload, moves TradePulse metadata to stable
  fields, and writes the events to Elasticsearch.
* **Elasticsearch** stores the log indices (`tradepulse-logs-*`).
* **Kibana** exposes the data for analysis and dashboarding.

## Usage

```bash
docker compose up tradepulse prometheus elasticsearch logstash kibana filebeat
```

The default pipeline expects the application to emit JSON logs to stdout (the
existing `core.utils.logging` module already provides that). Kibana will be
available on <http://localhost:5601> with an index pattern of
`tradepulse-logs-*`.

### Kubernetes deployment

The `deploy/kustomize` overlays embed a Filebeat DaemonSet and Logstash
deployment so that every backend pod annotated with
`co.elastic.logs/enabled=true` ships its logs to Elasticsearch.

```bash
kustomize build deploy/kustomize/overlays/staging | kubectl apply -f -
```

By default Filebeat forwards to the in-cluster Logstash service, which in turn
uses the Elasticsearch host specified via the `ELASTICSEARCH_HOSTS`
environment variable (defaulting to `http://elasticsearch:9200`). To point to a
managed Elastic cluster set the following variables on the Logstash Deployment
prior to apply:

```bash
kubectl -n tradepulse-staging set env deploy/logstash \
  ELASTICSEARCH_HOSTS=https://elastic.example.com:9200 \
  ELASTICSEARCH_USERNAME=tradepulse \
  ELASTICSEARCH_PASSWORD='••••••••'
```

If your Elasticsearch instance uses API keys, set `ELASTICSEARCH_API_KEY` and
omit the username/password pair instead. The Filebeat DaemonSet can be tuned via
the `tradepulse-filebeat-config` ConfigMap generated from
`observability/logging/filebeat.kubernetes.yml`.

## Customisation

* Adjust `service.name` and `environment` fields in `filebeat.docker.yml` to
  align with your deployment naming. Override `FILEBEAT_ENVIRONMENT` when
  running Filebeat as a container to tag logs with the correct environment name.
* Extend `logstash.conf` to enrich the payload or route to additional
  destinations (e.g. S3, Kafka). Use the `LOG_INDEX_PREFIX`,
  `ELASTICSEARCH_HOSTS`, and related environment variables to control the
  Elasticsearch sink without editing the pipeline. Enable TLS forwarding by
  setting `LOGSTASH_SSL_ENABLED=true` and adjusting
  `LOGSTASH_SSL_VERIFICATION` as needed when running Filebeat against a secured
  Logstash endpoint.

