curl -i http://`cat address`/orders \
  --request POST \
  --header "Content-Type: application/json" \
  --data '{
      "data": [
          {
              "order_id": 1,
              "weight": 0.23,
              "region": 12,
              "delivery_hours": ["09:00-18:00"]
          },
          {
              "order_id": 2,
              "weight": 15,
              "region": 1,
              "delivery_hours": ["09:00-18:00"],
              "111111": "11111"
          },
          {
              "order_id": 3,
              "region": 22,
              "delivery_hours": ["09:00-12:00", "16:00-21:30"]
          }
      ]
  }'
