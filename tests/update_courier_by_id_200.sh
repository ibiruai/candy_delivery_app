curl -i http://`cat address`/couriers/2 \
  --request PATCH \
  --header "Content-Type: application/json" \
  --data '{
      "regions": [1, 12, 22],
      "courier_type": "car",
      "working_hours": ["00:00-23:59"]
    }'
