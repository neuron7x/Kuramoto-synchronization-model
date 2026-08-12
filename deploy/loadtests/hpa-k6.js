import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 50 },
    { duration: '8m', target: 200 },
    { duration: '6m', target: 400 },
    { duration: '5m', target: 50 },
    { duration: '3m', target: 0 },
  ],
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<400'],
  },
};

const BASE_URL =
  __ENV.GEOSYNC_BASE_URL || 'http://geosync-api.geosync.svc.cluster.local';
const LATENCY_SLO_MS = parseFloat(__ENV.GEOSYNC_LATENCY_SLO_MS || '400');

export default function () {
  const res = http.get(`${BASE_URL}/health`);
  check(res, {
    'status is 200': (r) => r.status === 200,
    'latency within SLO': (r) => r.timings.duration <= LATENCY_SLO_MS,
  });
  sleep(0.5);
}
