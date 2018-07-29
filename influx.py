import influxdb
from datetime import datetime
from datetime import datetime
import math
import time

import onzo.device

INFLUX_USERNAME = ""
INFLUX_PASSWORD = ""

def make_json(measurement, value, timestamp):

    return [
        {
            "measurement": measurement,
            "time":  timestamp,
            "fields": {
                "value": value
            }
        }
    ]

db = influxdb.InfluxDBClient(host="172.16.0.254", port=8086, username=INFLUX_USERNAME,
                             password=INFLUX_PASSWORD)
db.create_database("onzo")

conn = onzo.device.Connection()
try:
    conn.connect()
    disp = onzo.device.Display(conn)
    clamp = onzo.device.Clamp(conn)
    p_reactive = None
    counter = 0

    while True:
        timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        p_real = clamp.get_power()
        db.write_points(make_json("power_real", p_real, timestamp), database="onzo")

        # reactive power only updates onces every 15s, so there is no use
        # querying more often, this just wastes clamp battery
        if counter % 15 == 0:
            p_reactive = clamp.get_powervars()
            db.write_points(make_json("power_reactive", p_reactive, timestamp), database="onzo")

        # Only update battery once every 10mins
        if counter % (60 * 10) == 0:
            battery = clamp.get_batteryvolts()
            db.write_points(make_json("battery_clamp", battery, timestamp), database="onzo")

        p_apparent = int(math.sqrt(p_real**2 + p_reactive**2))
        db.write_points(make_json("power_apparent", p_apparent, timestamp), database="onzo")


        ear = clamp.get_cumulative_kwh()
        db.write_points(make_json("kWh", ear, timestamp), database="onzo")

        print(timestamp, p_real, p_reactive, p_apparent, ear, battery)

        counter += 1
        time.sleep(1)
finally:
    conn.disconnect()
