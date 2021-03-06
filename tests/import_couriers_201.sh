curl -i http://`cat address`/couriers \
  --request POST \
  --header "Content-Type: application/json" \
  --data '{
      "data": [
          {
              "courier_id": 1,
              "courier_type": "foot",
              "regions": [1, 12, 22],
              "working_hours": ["11:35-14:05", "09:00-11:00"]
          },
          {
              "courier_id": 2,
              "courier_type": "bike",
              "regions": [22],
              "working_hours": ["09:00-18:00"]
          },
          {
              "courier_id": 3,
              "courier_type": "car",
              "regions": [12, 22, 23, 33],
              "working_hours": ["01:00-15:00"]
          }
      ]
  }'
