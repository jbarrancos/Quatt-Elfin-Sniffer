# Home Assistant Setup Guide

## Quick Setup

### 1. Install MQTT Broker
- In Home Assistant: Settings → Add-ons → Add-on Store
- Search for "Mosquitto broker" and install it
- Start the broker and enable "Start on boot"

### 2. Configure the Sniffer
Edit `config.ini`:
```ini
[mqtt]
broker_host = homeassistant.local  # Your Home Assistant IP
broker_port = 1883
username = your_mqtt_user          # Optional
password = your_mqtt_pass          # Optional
device_prefix = quatt

[devices]
device_base_name = Quatt Heat Pump
```

### 3. Run the Sniffer
```bash
python quatt_modbus_sniffer.py --config config.ini
```

### 4. Check Home Assistant
- Go to Settings → Devices & Services → MQTT
- Your heat pumps should appear automatically as new devices
- Each heat pump gets 40+ sensors for temperature, pressure, power, etc.

## Multiple Heat Pumps

If you have multiple heat pumps, each will appear as a separate device:
- "Quatt Heat Pump 01" 
- "Quatt Heat Pump 02"
- etc.

You can customize the names in `config.ini`:
```ini

[devices]
device_base_name = Quatt Heat Pump
device_01_name = Quatt Left
device_02_name = Quatt Right
```

## Troubleshooting

**No devices appearing?**
- Check MQTT broker is running
- Verify config.ini settings
- Check sniffer logs for errors

**Wrong sensor values?**
- Heat pump communication may be offline
- Check Modbus connection to heat pump
