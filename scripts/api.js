import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 100 },   // sobe pra 100 usuários
    { duration: '1m',  target: 1000 },  // sobe pra 1000
    { duration: '30s', target: 0 },     // desce
  ],
};

export default function () {
  const res = http.get('http://host.docker.internal:30040/health');
  check(res, { 'status 200': (r) => r.status === 200 });
  sleep(1);
}