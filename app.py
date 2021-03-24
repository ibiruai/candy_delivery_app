from flask import Flask, abort, jsonify, request
from datetime import datetime
from dateutil import parser
import re
import sqlite3


app = Flask(__name__)

DB_NAME = "delivery.db"
COURIER_TYPES_CAPACITY = {"foot": 10, "bike": 15, "car": 50}
COURIER_TYPES_COEFFICIENT = {"foot": 2, "bike": 5, "car": 9}
MIN_WEIGHT = 0.01
MAX_WEIGHT = 50
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def courier_type_is_valid(courier_type):
    return courier_type in ("foot", "bike", "car")


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


def get_courier_info(courier_id):
    courier = {"courier_id": courier_id}
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(f"SELECT COURIER_TYPE FROM COURIERS WHERE COURIER_ID = {courier_id}")
    row = cursor.fetchone()
    if row is None:
        conn.close()
        return False
    courier["courier_type"] = row[0]
    cursor.execute(f"SELECT REGION FROM REGIONS WHERE COURIER_ID = {courier_id}")
    courier["regions"] = [row[0] for row in cursor.fetchall()]
    cursor.execute(f"SELECT HOURS FROM WORKING_HOURS WHERE COURIER_ID = {courier_id}")
    courier["working_hours"] = [row[0] for row in cursor.fetchall()]
    conn.close()
    return courier


@app.route("/couriers", methods=["POST"])
def import_couriers():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COURIER_ID FROM COURIERS")
    existing_couriers = [row[0] for row in cursor.fetchall()]
    conn.close()

    valid_couriers = []
    invalid_couriers = []
    fields = ("courier_id", "courier_type", "regions", "working_hours")
    for courier in request.json["data"]:
        if (set(courier.keys()) == set(fields) and
           courier["courier_id"] not in existing_couriers and
           courier_type_is_valid(courier["courier_type"]) and
           hours_are_valid(courier["working_hours"]) and
           regions_are_valid(courier["regions"])):
            valid_couriers.append({"id": courier["courier_id"]})
        else:
            invalid_couriers.append({"id": courier["courier_id"]})

    if len(invalid_couriers) != 0:
        return jsonify(
            {"validation_error": {"couriers": invalid_couriers}}), 400

    query_couriers = "INSERT INTO COURIERS (COURIER_ID, COURIER_TYPE) VALUES "
    query_regions = "INSERT INTO REGIONS (COURIER_ID, REGION) VALUES "
    query_working_hours = "INSERT INTO WORKING_HOURS (COURIER_ID, HOURS) VALUES "
    for courier in request.json["data"]:
        query_couriers += f'({courier["courier_id"]}, "{courier["courier_type"]}"), '
        for region in courier["regions"]:
            query_regions += f'({courier["courier_id"]}, {region}), '
        for interval in courier["working_hours"]:
            query_working_hours += f'({courier["courier_id"]}, "{interval}"), '
    query_couriers = query_couriers[:-2] + ";"
    query_regions = query_regions[:-2] + ";"
    query_working_hours = query_working_hours[:-2] + ";"

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(query_couriers)
    cursor.execute(query_regions)
    cursor.execute(query_working_hours)
    conn.commit()
    conn.close()

    return ({"couriers": valid_couriers}), 201


@app.route('/couriers/<int:courier_id>', methods=['PATCH'])
def update_courier(courier_id):
    courier = get_courier_info(courier_id)
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
        if not courier_type_is_valid(courier_type):
            abort(400)
    if "working_hours" in request.json:
        working_hours = request.json["working_hours"]
        if not hours_are_valid(working_hours):
            abort(400)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if "regions" in request.json:
        cursor.execute(f"DELETE FROM REGIONS WHERE COURIER_ID = {courier_id}")
        query = "INSERT INTO REGIONS (COURIER_ID, REGION) VALUES "
        for region in regions:
            query += f"({courier_id}, {region}), "
        query = query[:-2] + ";"
        cursor.execute(query)
    if "working_hours" in request.json:
        cursor.execute(f"DELETE FROM WORKING_HOURS WHERE COURIER_ID = {courier_id}")
        query = "INSERT INTO WORKING_HOURS (COURIER_ID, HOURS) VALUES "
        for interval in working_hours:
            query += f'({courier_id}, "{interval}"), '
        query = query[:-2] + ";"
        cursor.execute(query)
    if "courier_type" in request.json:
        cursor.execute(f"""
            UPDATE COURIERS
            SET COURIER_TYPE = "{courier_type}"
            WHERE COURIER_ID = {courier_id}""")
    conn.commit()

    capacity = COURIER_TYPES_CAPACITY[courier_type]
    orders_to_reassign = []
    cursor.execute(f"""
        SELECT ORDERS.ORDER_ID, WEIGHT, REGION, HOURS
        FROM ORDERS
        INNER JOIN DELIVERY_HOURS ON ORDERS.ORDER_ID = DELIVERY_HOURS.ORDER_ID
        WHERE COURIER_ID = {courier_id}
        AND COMPLETE_TIME IS NULL
        ORDER BY WEIGHT""")
    for row in cursor.fetchall():
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
    cursor.execute(f"""
        UPDATE ORDERS
        SET COURIER_ID = NULL
        WHERE ORDER_ID IN ({', '.join(map(str, orders_to_reassign))})""")
    conn.commit()
    conn.close()

    return jsonify(courier)


@app.route("/orders", methods=["POST"])
def import_orders():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT ORDER_ID FROM ORDERS")
    existing_orders = [row[0] for row in cursor.fetchall()]
    conn.close()

    valid_orders = []
    invalid_orders = []
    fields = ("order_id", "weight", "region", "delivery_hours")
    for order in request.json["data"]:
        if (set(order.keys()) == set(fields) and
           order["order_id"] not in existing_orders and
           isinstance(order["weight"], (int, float)) and
           MIN_WEIGHT <= order["weight"] <= MAX_WEIGHT and
           isinstance(order["region"], int) and order["region"] > 0 and
           hours_are_valid(order["delivery_hours"])):
            valid_orders.append({"id": order["order_id"]})
        else:
            invalid_orders.append({"id": order["order_id"]})

    if len(invalid_orders) != 0:
        return jsonify({"validation_error": {"orders": invalid_orders}}), 400

    query_orders = "INSERT INTO ORDERS (ORDER_ID, WEIGHT, REGION) VALUES "
    query_delivery_hours = "INSERT INTO DELIVERY_HOURS (ORDER_ID, HOURS) VALUES "
    for order in request.json["data"]:
        query_orders += f'({order["order_id"]}, {order["weight"]}, {order["region"]}), '
        for interval in order["delivery_hours"]:
            query_delivery_hours += f'({order["order_id"]}, "{interval}"), '
    query_orders = query_orders[:-2] + ";"
    query_delivery_hours = query_delivery_hours[:-2] + ";"

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(query_orders)
    cursor.execute(query_delivery_hours)
    conn.commit()
    conn.close()

    return ({"orders": valid_orders}), 201


@app.route('/orders/assign', methods=['POST'])
def assign_orders():
    courier_id = request.json["courier_id"]
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(f"""SELECT COURIER_TYPE, ASSIGN_TIME
                       FROM COURIERS WHERE COURIER_ID = {courier_id}""")
    row = cursor.fetchone()
    if row is None:
        conn.close()
        abort(400)
    courier_type, assign_time = row
    assigned_orders = []
    capacity = COURIER_TYPES_CAPACITY[courier_type]

    cursor.execute(f"""
        SELECT ORDER_ID, WEIGHT
        FROM ORDERS
        WHERE COURIER_ID = {courier_id}""")
    for row in cursor.fetchall():
        order_id, weight = row
        assigned_orders.append({"id": order_id})
        capacity -= weight

    new_orders_ids = []
    cursor.execute(f"SELECT HOURS FROM WORKING_HOURS WHERE COURIER_ID = {courier_id}")
    working_hours = [row[0] for row in cursor.fetchall()]
    cursor.execute(f"""
        SELECT
            ORDERS.ORDER_ID, WEIGHT, DELIVERY_HOURS.HOURS
        FROM
            ORDERS, COURIERS
            INNER JOIN REGIONS ON COURIERS.COURIER_ID = REGIONS.COURIER_ID AND
                                ORDERS.REGION = REGIONS.REGION
            INNER JOIN DELIVERY_HOURS ON ORDERS.ORDER_ID = DELIVERY_HOURS.ORDER_ID
        WHERE
            COURIERS.COURIER_ID = {courier_id} AND ORDERS.COURIER_ID IS NULL
        ORDER BY
            WEIGHT, ORDERS.ORDER_ID""")
    for row in cursor.fetchall():
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
        cursor.execute(f"""
            UPDATE COURIERS
            SET ASSIGN_TIME = "{assign_time}"
            WHERE COURIER_ID = {courier_id}""")
        cursor.execute(f"""
            UPDATE ORDERS
            SET COURIER_ID = {courier_id}
            WHERE ORDER_ID IN ({str(new_orders_ids)[1:-1]})""")
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
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT *
        FROM ORDERS
        WHERE
            ORDER_ID = {order_id}
            AND COURIER_ID = {courier_id}""")
    if cursor.fetchone() is None:
        abort(400)
    cursor.execute(f"""
        SELECT COURIER_TYPE, ASSIGN_TIME, LAST_COMPLETE_TIME
        FROM COURIERS
        WHERE COURIER_ID = {courier_id}""")
    courier_type, assign_time, last_complete_time = cursor.fetchone()
    if last_complete_time is None:
        last_complete_time = assign_time
    time_spent = int(parser.parse(request.json["complete_time"]).timestamp() -
                     max(parser.parse(assign_time).timestamp(),
                         parser.parse(last_complete_time).timestamp()))
    coefficient = COURIER_TYPES_COEFFICIENT[courier_type]
    cursor.execute(f"""
        UPDATE
            ORDERS
        SET
            COMPLETE_TIME = "{complete_time}",
            TIME_SPENT = {time_spent},
            COEFFICIENT =  {coefficient}
        WHERE
            ORDER_ID = {order_id}""")
    cursor.execute(f"""
        UPDATE COURIERS
        SET LAST_COMPLETE_TIME = "{complete_time}"
        WHERE COURIER_ID = {courier_id}""")
    conn.commit()
    conn.close()

    return jsonify({"order_id": order_id})


@app.route('/couriers/<int:courier_id>', methods=['GET'])
def get_courier(courier_id):
    courier = get_courier_info(courier_id)
    if not courier:
        abort(404)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT TIME_SPENT, REGION, COEFFICIENT
        FROM ORDERS
        WHERE COURIER_ID = {courier_id} AND COMPLETE_TIME NOT NULL
                   """)
    results = cursor.fetchall()
    if len(results) > 0:
        courier["earnings"] = 0
        time_spent_per_region = {}
        for row in results:
            time_spent, region, coefficient = row
            courier["earnings"] += 500 * coefficient
            if region not in time_spent_per_region:
                time_spent_per_region[region] = []
            time_spent_per_region[region].append(time_spent)
        t = min(sum(value) / len(value) for value in time_spent_per_region.values())
        courier["rating"] = (60 * 60 - min(t, 60 * 60)) / (60 * 60) * 5
    conn.close()
    return jsonify(courier)


def check_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT COURIER_ID FROM COURIERS")
        conn.close()
        return
    except sqlite3.OperationalError:
        pass

    cursor.execute('''CREATE TABLE COURIERS (
                        COURIER_ID INT PRIMARY KEY NOT NULL,
                        COURIER_TYPE CHAR(4) NOT NULL,
                        ASSIGN_TIME DATETIME,
                        LAST_COMPLETE_TIME DATETIME
                    );''')
    cursor.execute('''CREATE TABLE REGIONS (
                        COURIER_ID INT NOT NULL,
                        REGION INT NOT NULL
                    );''')
    cursor.execute('''CREATE TABLE WORKING_HOURS (
                        COURIER_ID INT NOT NULL,
                        HOURS CHAR(11) NOT NULL
                    );''')
    cursor.execute('''CREATE TABLE ORDERS (
                        ORDER_ID INT PRIMARY KEY NOT NULL,
                        WEIGHT FLOAT(2) NOT NULL,
                        REGION INT NOT NULL,
                        COURIER_ID INT,
                        COMPLETE_TIME DATETIME,
                        TIME_SPENT INT,
                        COEFFICIENT INT
                    );''')
    cursor.execute('''CREATE TABLE DELIVERY_HOURS (
                        ORDER_ID INT NOT NULL,
                        HOURS CHAR(11) NOT NULL
                    );''')
    conn.close()


check_database()
