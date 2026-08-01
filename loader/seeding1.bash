aws dynamodb batch-write-item --request-items file://./seeding1.json --region us-east-1


aws dynamodb query \
  --table-name y62db-config-rule-catalog \
  --key-condition-expression "pk = :pk" \
  --expression-attribute-values '{":pk":{"S":"RULE#access-keys-rotated"}}' \
  --region us-east-1


  Yes — Query is generally cheaper and faster than Scan in DynamoDB. A Scan reads the whole table or index and then filters results, while a Query reads only items matching the key condition.

Practical rule
Use Query when you know the partition key, and optionally the sort key.

Use Scan only when you truly need to inspect the whole table or index.

Why it costs more
DynamoDB charges based on how much data is read, not just how many items are returned, so a Scan can consume much more read capacity because it examines everything first. Even a filter on Scan does not avoid reading the skipped items.
