curl -i http://127.0.0.1:5000/couriers/20000 \
  --request PATCH \
  --header "Content-Type: application/json" \
  --data '{
      "regions": [1, 12, 22],
      "courier_type": "car",
      "working_hours": ["00:00-23:59"]
    }'
