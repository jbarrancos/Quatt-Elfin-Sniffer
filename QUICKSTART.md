# Quick Start Guide

## 1. Install Dependencies
```bash
pip install -r requirements.txt
```

## 2. Configure Settings
Edit `config.ini`:
```ini
[server]
host = 0.0.0.0
port = 4444

[mqtt]
broker_host = homeassistant.local
username = your_mqtt_user
password = your_mqtt_pass
```

## 3. Run the Sniffer
```bash
# Basic run
python quatt_modbus_sniffer.py

# With config file
python quatt_modbus_sniffer.py --config config.ini

# With debug logging
python quatt_modbus_sniffer.py --config config.ini --debug
```

**Stop the server:** Press `Ctrl+C` for graceful shutdown

## 4. Connect Your Sniffer Device
- Set your sniffer device to send data to `your_computer_ip:4444`
- The sniffer will capture Modbus RTU frames and parse heat pump data
- Data is automatically sent to Home Assistant via MQTT

## What You'll See
- Heat pump devices auto-discovered in Home Assistant
- 40+ sensors per heat pump (temperatures, pressures, power, etc.)
- Real-time monitoring and logging
- Binary sensors for alarms and status

## VS Code Tasks
Use the built-in tasks for easy running:
- `Ctrl+Shift+P` → "Tasks: Run Task"
- Choose from: Config, Config + Debug, Direct, Launcher modes