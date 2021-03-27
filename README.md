Candy Delivery App
==================

REST API сервис на Python для интернет-магазина, позволяющий нанимать курьеров на работу, принимать заказы и оптимально распределять заказы между курьерами, попутно считая их рейтинг и заработок.

**POST /couriers**  
Загрузка списка курьеров в систему

**PATCH /couriers/$courier_id**  
Изменение информации о курьере

**POST /orders**  
Загрузка списка заказов в систему

**POST /orders/assign**  
Назначение максимального количества заказов курьеру

**POST /orders/complete**  
Пометка заказа как выполненного

**GET /couriers/$courier_id**  
Получение информации о курьере

Установка для Ubuntu
--------------------

```shell
sudo apt install git python3-dateutil python3-flask
git clone https://github.com/ibiruai/candy_delivery_app.git ~/candy_delivery_app
```

Обновление
----------

```shell
git -C ~/candy_delivery_app pull
```

Запуск
------

```shell
cd ~/candy_delivery_app && flask run --host=0.0.0.0 --port=5000
```

Запускать после перезагрузки
----------------------------

```shell
crontab -e
```

Добавить в cron:

```shell
@reboot cd ~/candy_delivery_app && flask run --host=0.0.0.0 --port=5000
```

Тесты
-----

```shell
cd tests
chmod +x *
cat import_couriers_201.sh  # Вывести тест
./import_couriers_201.sh  # Выполнить тест
```
