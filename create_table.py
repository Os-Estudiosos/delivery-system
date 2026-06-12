import boto3
import time

athena = boto3.client('athena', region_name='us-east-1')

ddl = """
CREATE EXTERNAL TABLE IF NOT EXISTS dijkfood_analytics.events (
  order_id INT,
  status STRING,
  restaurant_id INT,
  region_id INT,
  timestamp STRING
)
PARTITIONED BY (year STRING, month STRING, day STRING)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
WITH SERDEPROPERTIES (
  'ignore.malformed.json' = 'true'
)
STORED AS TEXTFILE
LOCATION 's3://dijkfood-datalake-beadf2ad/events/'
TBLPROPERTIES (
  'projection.enabled' = 'true',
  'projection.year.type' = 'integer',
  'projection.year.range' = '2023,2030',
  'projection.year.digits' = '4',
  'projection.month.type' = 'integer',
  'projection.month.range' = '01,12',
  'projection.month.digits' = '2',
  'projection.day.type' = 'integer',
  'projection.day.range' = '01,31',
  'projection.day.digits' = '2'
);
"""

res = athena.start_query_execution(
    QueryString=ddl,
    QueryExecutionContext={'Database': 'dijkfood_analytics'},
    ResultConfiguration={'OutputLocation': 's3://dijkfood-datalake-beadf2ad/athena-results/'}
)
qid = res['QueryExecutionId']

while True:
    status = athena.get_query_execution(QueryExecutionId=qid)
    state = status['QueryExecution']['Status']['State']
    if state in ['SUCCEEDED', 'FAILED', 'CANCELLED']:
        print(f"Table Creation: {state}")
        if state == 'FAILED':
            print(status['QueryExecution']['Status']['StateChangeReason'])
        break
    time.sleep(1)

msck_query = "MSCK REPAIR TABLE dijkfood_analytics.events;"
res2 = athena.start_query_execution(
    QueryString=msck_query,
    QueryExecutionContext={'Database': 'dijkfood_analytics'},
    ResultConfiguration={'OutputLocation': 's3://dijkfood-datalake-beadf2ad/athena-results/'}
)
qid2 = res2['QueryExecutionId']
while True:
    status = athena.get_query_execution(QueryExecutionId=qid2)
    state = status['QueryExecution']['Status']['State']
    if state in ['SUCCEEDED', 'FAILED', 'CANCELLED']:
        print(f"MSCK: {state}")
        break
    time.sleep(1)
