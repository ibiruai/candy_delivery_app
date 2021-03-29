from flask import Flask, abort, jsonify, request
from datetime import datetime
from dateutil import parser
import re
import sqlite3


app = Flask(__name__)
DB_NAME = "delivery.db"
COURIER_TYPES = ("foot", "bike", "car")
COURIER_TYPES_CAPACITY = {"foot": 10, "bike": 15, "car": 50}
COURIER_TYPES_COEFFICIENT = {"foot": 2, "bike": 5, "car": 9}
ORDER_MIN_WEIGHT = 0.01
ORDER_MAX_WEIGHT = 50
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def hours_are_valid(intervals):
    regex = "^([01]?[0-9]|2[0-3]):[0-5][0-9]-([01]?[0-9]|2[0-3]):[0-5][0-9]$"
    return (isinstance(intervals, list) and
            all(isinstance(interval, str) and
                re.search(regex, interval) for interval in intervals))


def regions_are_valid(regions):
    return (isinstance(regions, list) and
            all(isinstance(region, int) and region > 0 for region in regions))


def intervals_intersect(interval_1, interval_2):
    start_1 = int(interval_1[:2]) * 60 + int(interval_1[3:5])
    start_2 = int(interval_2[:2]) * 60 + int(interval_2[3:5])
    end_1 = int(interval_1[6:8]) * 60 + int(interval_1[9:11])
    end_2 = int(interval_2[6:8]) * 60 + int(interval_2[9:11])
    if start_1 > end_1:
        end_1 += 24 * 60
    if start_2 > end_2:
        end_2 += 24 * 60
    if end_1 < start_2:
        start_1 += 24 * 60
        end_1 += 24 * 60
    elif end_2 < start_1:
        start_2 += 24 * 60
        end_2 += 24 * 60
    return start_1 <= start_2 <= end_1 or start_1 <= end_2 <= end_1


def get_courier_dictionary(courier_id):
    courier = {"courier_id": courier_id}
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(f"SELECT type FROM couriers WHERE id = {courier_id}")
    row = c.fetchone()
    if row is None:
        conn.close()
        return False
    courier["courier_type"] = row[0]
    c.execute(f"SELECT region FROM regions WHERE courier_id = {courier_id}")
    courier["regions"] = [row[0] for row in c.fetchall()]
    c.execute(f"""SELECT interval
                  FROM working_hours
                  WHERE courier_id = {courier_id}""")
    courier["working_hours"] = [row[0] for row in c.fetchall()]
    conn.close()
    return courier


@app.route("/couriers", methods=["POST"])
def import_couriers():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id FROM couriers")
    existing_couriers = [row[0] for row in c.fetchall()]
    conn.close()

    valid_couriers = []
    invalid_couriers = []
    fields = ("courier_id", "courier_type", "regions", "working_hours")
    for courier in request.json["data"]:
        if (set(courier.keys()) == set(fields) and
           courier["courier_id"] not in existing_couriers and
           courier["courier_type"] in COURIER_TYPES and
           hours_are_valid(courier["working_hours"]) and
           regions_are_valid(courier["regions"])):
            valid_couriers.append({"id": courier["courier_id"]})
        else:
            invalid_couriers.append({"id": courier["courier_id"]})

    if len(invalid_couriers) != 0:
        return jsonify(
            {"validation_error": {"couriers": invalid_couriers}}), 400

    query_couriers = "INSERT INTO couriers (id, type) VALUES "
    query_regions = "INSERT INTO regions (courier_id, region) VALUES "
    query_hours = "INSERT INTO working_hours (courier_id, interval) VALUES "
    for courier in request.json["data"]:
        query_couriers += (f'({courier["courier_id"]}, '
                           f'"{courier["courier_type"]}"), ')
        for region in courier["regions"]:
            query_regions += f'({courier["courier_id"]}, {region}), '
        for interval in courier["working_hours"]:
            query_hours += f'({courier["courier_id"]}, "{interval}"), '
    query_couriers = query_couriers[:-2] + ";"
    query_regions = query_regions[:-2] + ";"
    query_hours = query_hours[:-2] + ";"

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(query_couriers)
    c.execute(query_regions)
    c.execute(query_hours)
    conn.commit()
    conn.close()

    return ({"couriers": valid_couriers}), 201


@app.route('/couriers/<int:courier_id>', methods=['PATCH'])
def update_courier(courier_id):
    courier = get_courier_dictionary(courier_id)
    if not courier:
        abort(404)
    courier_type = courier["courier_type"]
    regions = courier["regions"]
    working_hours = courier["working_hours"]

    fields = ("courier_type", "regions", "working_hours")
    if any(field not in fields for field in request.json.keys()):
        abort(400)
    if "regions" in request.json:
        regions = request.json["regions"]
        if not regions_are_valid(regions):
            abort(400)
    if "courier_type" in request.json:
        courier_type = request.json["courier_type"]
        if courier_type not in COURIER_TYPES:
            abort(400)
    if "working_hours" in request.json:
        working_hours = request.json["working_hours"]
        if not hours_are_valid(working_hours):
            abort(400)

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    if "regions" in request.json:
        c.execute(f"DELETE FROM regions WHERE courier_id = {courier_id}")
        query = "INSERT INTO regions (courier_id, region) VALUES "
        for region in regions:
            query += f"({courier_id}, {region}), "
        query = query[:-2] + ";"
        c.execute(query)
    if "working_hours" in request.json:
        c.execute(f"DELETE FROM working_hours WHERE courier_id = {courier_id}")
        query = "INSERT INTO working_hours (courier_id, interval) VALUES "
        for interval in working_hours:
            query += f'({courier_id}, "{interval}"), '
        query = query[:-2] + ";"
        c.execute(query)
    if "courier_type" in request.json:
        c.execute(f"""UPDATE couriers
                      SET type = "{courier_type}"
                      WHERE id = {courier_id}""")
    conn.commit()

    capacity = COURIER_TYPES_CAPACITY[courier_type]
    orders_to_reassign = []
    c.execute(f"""SELECT
                    orders.id, weight, region, interval
                  FROM orders
                  JOIN delivery_hours
                    ON orders.id = delivery_hours.order_id
                  WHERE courier_id = {courier_id} AND completed_at IS NULL
                  ORDER BY weight""")
    for row in c.fetchall():
        order_id, weight, region, delivery_interval = row
        if region not in regions or capacity < weight:
            orders_to_reassign.append(order_id)
            continue
        for working_interval in working_hours:
            if intervals_intersect(working_interval, delivery_interval):
                capacity -= weight
                break
        else:
            orders_to_reassign.append(order_id)
    c.execute(f"""UPDATE orders
                  SET courier_id = NULL
                  WHERE id IN ({', '.join(map(str, orders_to_reassign))})""")
    conn.commit()
    conn.close()

    courier["courier_type"] = courier_type
    courier["regions"] = regions
    courier["working_hours"] = working_hours
    return jsonify(courier)


@app.route("/orders", methods=["POST"])
def import_orders():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id FROM orders")
    existing_orders = [row[0] for row in c.fetchall()]
    conn.close()

    valid_orders = []
    invalid_orders = []
    fields = ("order_id", "weight", "region", "delivery_hours")
    for order in request.json["data"]:
        if (set(order.keys()) == set(fields) and
           order["order_id"] not in existing_orders and
           isinstance(order["weight"], (int, float)) and
           ORDER_MIN_WEIGHT <= order["weight"] <= ORDER_MAX_WEIGHT and
           hours_are_valid(order["delivery_hours"]) and
           regions_are_valid([order["region"]])):
            valid_orders.append({"id": order["order_id"]})
        else:
            invalid_orders.append({"id": order["order_id"]})

    if len(invalid_orders) != 0:
        return jsonify({"validation_error": {"orders": invalid_orders}}), 400

    query_orders = "INSERT INTO orders (id, weight, region) VALUES "
    query_hours = "INSERT INTO delivery_hours (order_id, interval) VALUES "
    for order in request.json["data"]:
        query_orders += (f'({order["order_id"]}, {order["weight"]}, '
                         f'{order["region"]}), ')
        for interval in order["delivery_hours"]:
            query_hours += f'({order["order_id"]}, "{interval}"), '
    query_orders = query_orders[:-2] + ";"
    query_hours = query_hours[:-2] + ";"

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(query_orders)
    c.execute(query_hours)
    conn.commit()
    conn.close()

    return ({"orders": valid_orders}), 201


@app.route('/orders/assign', methods=['POST'])
def assign_orders():
    courier_id = request.json["courier_id"]
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(f"""SELECT type, orders_assigned_at
                  FROM couriers
                  WHERE id = {courier_id}""")
    row = c.fetchone()
    if row is None:
        conn.close()
        abort(400)
    courier_type, assign_time = row
    assigned_orders = []
    capacity = COURIER_TYPES_CAPACITY[courier_type]

    c.execute(f"""SELECT id, weight
                  FROM orders
                  WHERE courier_id = {courier_id}""")
    for row in c.fetchall():
        order_id, weight = row
        assigned_orders.append({"id": order_id})
        capacity -= weight

    new_orders_ids = []
    c.execute(f"""SELECT interval
                  FROM working_hours
                  WHERE courier_id = {courier_id}""")
    working_hours = [row[0] for row in c.fetchall()]
    c.execute(f"""SELECT
                    orders.id, weight, delivery_hours.interval
                  FROM orders, couriers
                  JOIN regions
                    ON couriers.id = regions.courier_id
                    AND orders.region = regions.region
                  JOIN delivery_hours
                    ON orders.id = delivery_hours.order_id
                  WHERE
                    couriers.id = {courier_id} AND orders.courier_id IS NULL
                  ORDER BY weight, orders.id""")
    for row in c.fetchall():
        order_id, weight, delivery_interval = row
        if {"id": order_id} in assigned_orders:
            continue
        if weight > capacity:
            break
        for working_interval in working_hours:
            if intervals_intersect(working_interval, delivery_interval):
                capacity -= weight
                assigned_orders.append({"id": order_id})
                new_orders_ids.append(order_id)
                break
    if new_orders_ids != []:
        assign_time = datetime.utcnow().strftime(TIME_FORMAT)
        c.execute(f"""UPDATE couriers
                      SET orders_assigned_at = "{assign_time}"
                      WHERE id = {courier_id}""")
        c.execute(f"""UPDATE orders
                      SET courier_id = {courier_id}
                      WHERE id IN ({str(new_orders_ids)[1:-1]})""")
        conn.commit()

    if assigned_orders == []:
        return jsonify({"orders": []})
    return jsonify({"orders": assigned_orders, "assign_time": assign_time})
    conn.close()


@app.route('/orders/complete', methods=['POST'])
def mark_order_as_completed():
    courier_id = request.json["courier_id"]
    order_id = request.json["order_id"]
    complete_time = request.json["complete_time"]
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(f"""SELECT id
                  FROM orders
                  WHERE id = {order_id} AND courier_id = {courier_id}""")
    if c.fetchone() is None:
        abort(400)
    c.execute(f"""SELECT type, orders_assigned_at, last_order_completed_at
                  FROM couriers
                  WHERE id = {courier_id}""")
    courier_type, assign_time, last_order_completed_at = c.fetchone()
    if last_order_completed_at is None:
        last_order_completed_at = assign_time
    time_spent = int(parser.parse(request.json["complete_time"]).timestamp() -
                     max(parser.parse(assign_time).timestamp(),
                         parser.parse(last_order_completed_at).timestamp()))
    coefficient = COURIER_TYPES_COEFFICIENT[courier_type]
    c.execute(f"""UPDATE orders
                  SET
                    completed_at = "{complete_time}",
                    time_spent = {time_spent},
                    coefficient =  {coefficient}
                  WHERE id = {order_id}""")
    c.execute(f"""UPDATE couriers
                  SET last_order_completed_at = "{complete_time}"
                  WHERE id = {courier_id}""")
    conn.commit()
    conn.close()

    return jsonify({"order_id": order_id})


@app.route('/couriers/<int:courier_id>', methods=['GET'])
def get_courier_info(courier_id):
    courier = get_courier_dictionary(courier_id)
    if not courier:
        abort(404)
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(f"""SELECT time_spent, region, coefficient
                  FROM orders
                  WHERE courier_id = {courier_id} AND completed_at NOT NULL""")
    results = c.fetchall()
    if len(results) > 0:
        courier["earnings"] = 0
        spent_per_region = {}
        for row in results:
            time_spent, region, coefficient = row
            courier["earnings"] += 500 * coefficient
            if region not in spent_per_region:
                spent_per_region[region] = []
            spent_per_region[region].append(time_spent)
        t = min(sum(x) / len(x) for x in spent_per_region.values())
        rating = (60 * 60 - min(t, 60 * 60)) / (60 * 60) * 5
        courier["rating"] = round(rating, 2)
    conn.close()
    return jsonify(courier)


def check_database():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    try:
        c.execute("SELECT id FROM couriers")
        conn.close()
        return
    except sqlite3.OperationalError:
        pass

    c.execute("""CREATE TABLE couriers (
                   id INT PRIMARY KEY NOT NULL,
                   type CHAR(4) NOT NULL,
                   orders_assigned_at DATETIME,
                   last_order_completed_at DATETIME
                 )""")
    c.execute("""CREATE TABLE regions (
                   courier_id INT NOT NULL,
                   region INT NOT NULL
                 )""")
    c.execute("""CREATE TABLE working_hours (
                   courier_id INT NOT NULL,
                   interval CHAR(11) NOT NULL
                 )""")
    c.execute("""CREATE TABLE orders (
                   id INT PRIMARY KEY NOT NULL,
                   weight FLOAT(2) NOT NULL,
                   region INT NOT NULL,
                   courier_id INT,
                   completed_at DATETIME,
                   time_spent INT,
                   coefficient INT
                 )""")
    c.execute("""CREATE TABLE delivery_hours (
                   order_id INT NOT NULL,
                   interval CHAR(11) NOT NULL
                 )""")
    c.execute("PRAGMA journal_mode=WAL")
    conn.close()


check_database()
