# Quatt Modbus Sniffer

A Python TCP server that captures Modbus RTU communication from Quatt heat pumps and integrates with Home Assistant via MQTT.

Based of M10Tech and Copilot: https://github.com/M10tech/Quatt-sniffer

HomeAssistant integration is optional. Just leave the MQTT info blank

## What It Does
- Captures Modbus RTU frames from heat pump communication
- HA: Automatically discovers multiple heat pumps
- HA: Sends data to Home Assistant via MQTT autodiscovery 
- Provides real-time monitoring and logging

## Quick Setup
1. Install dependencies: `pip install -r requirements.txt`
2. Configure `config.ini` with your MQTT settings
3. Run: `python quatt_modbus_sniffer.py --config config.ini`
4. Check Home Assistant for auto-discovered devices

## Documentation
- [Quick Start Guide](QUICKSTART.md) - Get running in minutes
- [Home Assistant Setup](HOME_ASSISTANT_SETUP.md) - MQTT integration guide
- [Register Mappings](REGISTER_MAPPINGS.md) - Heat pump sensor details
- [File Structure](FILE_STRUCTURE.md) - Project organization

## Requirements
- Python 3.7+
- paho-mqtt library (≥2.0.0)
- Home Assistant with MQTT broker
- Modbus RTU sniffer device connected to heat pump communication

## License
Open source project for Quatt heat pump monitoring.