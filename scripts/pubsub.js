import { AWSConfig, SQSClient } from 'https://jslib.k6.io/aws/0.11.0/sqs.js';

const awsConfig = new AWSConfig({
  region: 'us-east-1',
  accessKeyId: 'test123456789abcdefg',
  secretAccessKey: 'test123456789abcdefg',
  endpoint: 'http://host.docker.internal:4566',
});

const sqs = new SQSClient(awsConfig);

export const options = {
  scenarios: {
    couriers: {
      executor: 'constant-vus',
      vus: 1000,        // simula 1000 entregadores
      duration: '1m',
    },
  },
};

export default async function () {
  await sqs.sendMessage(
    'http://host.docker.internal:4566/000000000000/courier-locations',
    JSON.stringify({
      courier_id: __VU,   // cada VU é um entregador diferente
      lat: -23.5505 + Math.random() * 0.01,
      lng: -46.6333 + Math.random() * 0.01,
      timestamp: Date.now(),
    })
  );
}