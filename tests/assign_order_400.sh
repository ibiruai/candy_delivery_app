curl -i http://127.0.0.1:5000/orders/assign \
  --request POST \
  --header "Content-Type: application/json" \
  --data '{
      "courier_id": 20000
  }'
