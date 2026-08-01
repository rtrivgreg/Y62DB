aws dynamodb batch-write-item --request-items file://./seeding1.json --region us-east-1


aws dynamodb query \
  --table-name y62db-config-rule-catalog \
  --key-condition-expression "pk = :pk" \
  --expression-attribute-values '{":pk":{"S":"RULE#access-keys-rotated"}}' \
  --region us-east-1
