curl -i http://`cat address`/orders/complete \
  --request POST \
  --header "Content-Type: application/json" \
  --data '{
      "courier_id": 200000,
      "order_id": 100000,
      "complete_time": "'`date +"%Y-%m-%dT%H:%M:%SZ"`'"
  }'
