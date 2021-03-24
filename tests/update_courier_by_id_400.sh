curl -i http://127.0.0.1:5000/couriers/2 \
  --request PATCH \
  --header "Content-Type: application/json" \
  --data '{
      "city": "Москва"
    }'
