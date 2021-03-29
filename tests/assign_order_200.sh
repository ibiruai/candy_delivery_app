curl -i http://`cat address`/orders/assign \
  --request POST \
  --header "Content-Type: application/json" \
  --data '{
      "courier_id": 2
  }'
