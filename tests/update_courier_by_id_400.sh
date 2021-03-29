curl -i http://`cat address`/couriers/2 \
  --request PATCH \
  --header "Content-Type: application/json" \
  --data '{
      "city": "Москва"
    }'
