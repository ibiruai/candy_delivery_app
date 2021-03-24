curl -i http://127.0.0.1:5000/orders \
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
              "delivery_hours": ["09:00-18:00"]
          },
          {
              "order_id": 3,
              "weight": 0.01,
              "region": 22,
              "delivery_hours": ["09:00-12:00", "16:00-21:30"]
          }
      ]
  }'
