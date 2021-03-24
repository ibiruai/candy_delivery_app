Установка
---------

```shell
sudo apt install git
sudo apt install python3-flask
git clone https://github.com/ibiruai/candy_delivery_app.git ~/candy_delivery_app
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

Добавить:

```shell
@reboot cd ~/candy_delivery_app && flask run --host=0.0.0.0 --port=5000
```

Тесты
-----

```shell
cd tests
chmod +x *
cat import_couriers_201.sh  # Посмотреть тест
./import_couriers_201.sh  # Выполнить тест
```
