#!/usr/bin/env python3
"""
Quatt Modbus Sniffer with Home Assistant MQTT Integration
=========================================================

A TCP server that captures Modbus RTU communication from Quatt heat pumps
and publishes the data to MQTT for Home Assistant integration.

Features:
- Modbus RTU frame parsing and analysis
- MQTT publishing with Home Assistant autodiscovery
- Real-time sensor data extraction with accurate register mappings
- Request/response matching and timing
- Binary sensor support for status bits and alarms

Register Mappings:
- Updated to match M10tech/Quatt-sniffer v1.1.0 project
- Includes all 40+ sensors with proper scaling and offsets
- Status bit parsing for R2108 and R2119 registers
- Temperature offset handling (-3000 for Quatt temperature readings)
"""

import socket
import threading
import time
import logging
import json
import signal
import sys
import struct
import configparser
import os
import argparse
from datetime import datetime
from typing import Dict, Any, Optional

# Constants
MAX_BUFFER_SIZE = 512
BUFFER_CLEANUP_SIZE = 256
MIN_FRAME_SIZE = 4
MAX_FRAME_SIZE = 256
TEMPERATURE_MIN = -30
TEMPERATURE_MAX = 150
MODBUS_CRC_INIT = 0xFFFF
MODBUS_CRC_POLY = 0xA001
STATS_PUBLISH_INTERVAL = 50

# Import required libraries
try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('quatt_modbus_sniffer.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class HomeAssistantMQTT:
    """
    MQTT client for Home Assistant integration with autodiscovery.
    """
    
    def __init__(self, broker_host="localhost", broker_port=1883, 
                 username=None, password=None, device_prefix="quatt", device_config=None):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = username
        self.password = password
        self.device_prefix = device_prefix
        self.device_config = device_config or {}
        self.client = None
        self.connected = False
        
        # Home Assistant discovery topics
        self.discovery_prefix = "homeassistant"
        
        # Track device info for each slave ID
        self.device_infos = {}
        self.discovered_slaves = set()
        
        if MQTT_AVAILABLE:
            self.setup_mqtt()
    
    def setup_mqtt(self):
        """Initialize MQTT client"""
        try:
            # Use the current callback API version (paho-mqtt 2.0+)
            self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
            
            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)
            
            self.client.on_connect = self.on_connect
            self.client.on_disconnect = self.on_disconnect
            self.client.connect(self.broker_host, self.broker_port, 60)
            self.client.loop_start()
            
        except Exception as e:
            logger.error(f"MQTT setup failed: {e}")
            self.client = None
    
    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        """Callback for MQTT connection"""
        if not reason_code.is_failure:
            self.connected = True
            logger.info(f"🏠 Connected to Home Assistant MQTT broker")
        else:
            logger.error(f"MQTT connection failed: {reason_code}")
    
    def on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        """Callback for MQTT disconnection"""
        self.connected = False
        logger.warning("🏠 Disconnected from MQTT broker")
    
    def _sanitize_sensor_name(self, sensor_name: str) -> str:
        """Convert sensor name to topic-safe format"""
        return sensor_name.lower().replace(' ', '_').replace('-', '_').replace('/', '_')
    
    def publish_sensor_discovery(self, sensor_name: str, slave_id: int, unit: str = None, 
                                device_class: str = None, icon: str = None):
        """Publish Home Assistant sensor discovery configuration"""
        if not self.connected:
            return
        
        # Include slave ID in sensor naming
        sensor_id = f"{self.device_prefix}_{slave_id:02x}_{self._sanitize_sensor_name(sensor_name)}"
        config_topic = f"{self.discovery_prefix}/sensor/{sensor_id}/config"
        state_topic = f"{self.device_prefix}/sensor/{slave_id:02x}_{self._sanitize_sensor_name(sensor_name)}/state"
        
        config = {
            "name": sensor_name,
            "unique_id": sensor_id,
            "state_topic": state_topic,
            "device": self.get_device_info(slave_id)
        }
        
        if unit:
            config["unit_of_measurement"] = unit
        if device_class:
            config["device_class"] = device_class
        if icon:
            config["icon"] = icon
        
        self.client.publish(config_topic, json.dumps(config), retain=True)
        logger.debug(f"📡 Published sensor discovery for {sensor_name} on device {slave_id:02X}")
    
    def publish_binary_sensor_discovery(self, sensor_name: str, slave_id: int, icon: str = None):
        """Publish Home Assistant binary sensor discovery configuration"""
        if not self.connected:
            return
        
        # Include slave ID in sensor naming
        sensor_id = f"{self.device_prefix}_{slave_id:02x}_{self._sanitize_sensor_name(sensor_name)}"
        config_topic = f"{self.discovery_prefix}/binary_sensor/{sensor_id}/config"
        state_topic = f"{self.device_prefix}/binary_sensor/{slave_id:02x}_{self._sanitize_sensor_name(sensor_name)}/state"
        
        config = {
            "name": sensor_name,
            "unique_id": sensor_id,
            "state_topic": state_topic,
            "device": self.get_device_info(slave_id),
            "payload_on": "True",
            "payload_off": "False"
        }
        
        if icon:
            config["icon"] = icon
        
        # Set appropriate icon based on sensor type
        sensor_lower = sensor_name.lower()
        if "alarm" in sensor_lower:
            config["icon"] = "mdi:alert"
        elif "fan" in sensor_lower:
            config["icon"] = "mdi:fan"
        elif "heater" in sensor_lower:
            config["icon"] = "mdi:radiator"
        elif "valve" in sensor_lower:
            config["icon"] = "mdi:valve"
        elif "pump" in sensor_lower:
            config["icon"] = "mdi:pump"
        elif "defrost" in sensor_lower:
            config["icon"] = "mdi:snowflake"
        
        self.client.publish(config_topic, json.dumps(config), retain=True)
        logger.debug(f"📡 Published binary sensor discovery for {sensor_name} on device {slave_id:02X}")

    def publish_sensor_data(self, sensor_name: str, slave_id: int, value: Any):
        """Publish sensor data to Home Assistant"""
        if not self.connected:
            return
        
        state_topic = f"{self.device_prefix}/sensor/{slave_id:02x}_{self._sanitize_sensor_name(sensor_name)}/state"
        self.client.publish(state_topic, str(value))
    
    def publish_binary_sensor_data(self, sensor_name: str, slave_id: int, value: bool):
        """Publish binary sensor data to Home Assistant"""
        if not self.connected:
            return
        
        state_topic = f"{self.device_prefix}/binary_sensor/{slave_id:02x}_{self._sanitize_sensor_name(sensor_name)}/state"
        self.client.publish(state_topic, "True" if value else "False")
        
    def get_device_info(self, slave_id: int) -> dict:
        """Get device info for a specific slave ID, creating if needed"""
        if slave_id not in self.device_infos:
            # Get device name from config, with fallback logic
            device_name = self._get_device_name(slave_id)
            
            self.device_infos[slave_id] = {
                "identifiers": [f"{self.device_prefix}_heatpump_{slave_id:02x}"],
                "name": device_name,
                "model": "Quatt Heat Pump",
                "manufacturer": "Quatt",
                "sw_version": "1.0.0",
                "via_device": f"{self.device_prefix}_modbus_bridge"
            }
            logger.info(f"🏠 Created device info for Heat Pump {slave_id:02X}: '{device_name}'")
        return self.device_infos[slave_id]
    
    def _get_device_name(self, slave_id: int) -> str:
        """Get the configured device name for a specific slave ID"""
        # Check for custom name for this specific slave ID
        custom_name_key = f"device_{slave_id:02x}_name"
        if custom_name_key in self.device_config:
            return self.device_config[custom_name_key]
        
        # Use base name pattern
        base_name = self.device_config.get('device_base_name', 'Quatt Heat Pump')
        return f"{base_name} {slave_id:02X}"
    
    def shutdown(self):
        """Shutdown MQTT client cleanly"""
        if hasattr(self, 'client') and self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
                logger.info("🏠 MQTT client shutdown completed")
            except Exception as e:
                logger.warning(f"Error during MQTT shutdown: {e}")

class QuattDataParser:
    """
    Parser for extracting meaningful data from Quatt heat pump registers.
    """
    
    def __init__(self):
        # Quatt register mappings - Updated from M10tech/Quatt-sniffer v1.1.0
        self.register_mappings = {
            # Control registers (write commands from CiC to Quatt)
            1999: {"name": "Compressor Level set by CiC", "unit": "", "scale": 1, "offset": 0, "device_class": None},
            2010: {"name": "Pump Mode set by CiC", "unit": "", "scale": 1, "offset": 0, "device_class": None},
            2015: {"name": "Pump Level set by CiC", "unit": "%", "scale": 0.01, "offset": 0, "device_class": None},
            3999: {"name": "Working Mode set by CiC", "unit": "", "scale": 1, "offset": 0, "device_class": None},
            
            # Status and measurement registers (read responses from Quatt)
            2099: {"name": "Working Mode Actual", "unit": "", "scale": 1, "offset": 0, "device_class": None},
            2100: {"name": "Compressor AC Voltage", "unit": "V", "scale": 1, "offset": 0, "device_class": "voltage"},
            2101: {"name": "Compressor AC Current", "unit": "A", "scale": 0.1, "offset": 0, "device_class": "current"},
            2102: {"name": "Compressor Frequency Demand", "unit": "Hz", "scale": 1, "offset": 0, "device_class": "frequency"},
            2103: {"name": "Compressor Frequency Actual", "unit": "Hz", "scale": 1, "offset": 0, "device_class": "frequency"},
            2104: {"name": "Fan Speed Maximum", "unit": "RPM", "scale": 1, "offset": 0, "device_class": "speed"},
            2105: {"name": "Fan Speed Actual", "unit": "RPM", "scale": 1, "offset": 0, "device_class": "speed"},
            2107: {"name": "Electric Expansion Valve", "unit": "p", "scale": 1, "offset": 0, "device_class": None},
            2108: {"name": "Status Bits R2108", "unit": "", "scale": 1, "offset": 0, "device_class": None},  # Will handle bits separately
            2109: {"name": "EV1 Steps", "unit": "p", "scale": 1, "offset": 0, "device_class": None},  # Internal use
            2110: {"name": "Outside Temperature", "unit": "°C", "scale": 0.01, "offset": -3000, "device_class": "temperature"},
            2111: {"name": "Evaporator Coil Temperature", "unit": "°C", "scale": 0.01, "offset": -3000, "device_class": "temperature"},
            2112: {"name": "Gas Discharge Temperature", "unit": "°C", "scale": 0.01, "offset": -3000, "device_class": "temperature"},
            2113: {"name": "Gas Return Temperature", "unit": "°C", "scale": 0.01, "offset": -3000, "device_class": "temperature"},
            2116: {"name": "Evaporator Pressure", "unit": "bar", "scale": 0.1, "offset": 0, "device_class": "pressure"},
            2117: {"name": "Condenser Pressure", "unit": "bar", "scale": 0.1, "offset": 0, "device_class": "pressure"},
            2118: {"name": "Defrost Mode", "unit": "", "scale": 1, "offset": 0, "device_class": None},
            2119: {"name": "Status Bits R2119", "unit": "", "scale": 1, "offset": 0, "device_class": None},  # Will handle bits separately
            2120: {"name": "Status Bits R2120", "unit": "", "scale": 1, "offset": 0, "device_class": None},
            2121: {"name": "Status Bits R2121", "unit": "", "scale": 1, "offset": 0, "device_class": None},
            2122: {"name": "Firmware Version", "unit": "", "scale": 1, "offset": 0, "device_class": None},
            2123: {"name": "EEPROM Version", "unit": "", "scale": 1, "offset": 0, "device_class": None},
            2131: {"name": "Condensing Temperature", "unit": "°C", "scale": 0.01, "offset": -3000, "device_class": "temperature"},
            2132: {"name": "Evaporating Temperature", "unit": "°C", "scale": 0.01, "offset": -3000, "device_class": "temperature"},
            2133: {"name": "Water In Temperature", "unit": "°C", "scale": 0.01, "offset": -3000, "device_class": "temperature"},
            2134: {"name": "Water Out Temperature", "unit": "°C", "scale": 0.01, "offset": -3000, "device_class": "temperature"},
            2135: {"name": "Condenser Coil Temperature", "unit": "°C", "scale": 0.01, "offset": -3000, "device_class": "temperature"},
            2137: {"name": "Pump Power", "unit": "W", "scale": 0.1, "offset": 0, "device_class": "power"},
            2138: {"name": "Pump Flow", "unit": "L/h", "scale": 0.618, "offset": 0, "device_class": "volume_flow_rate"},
        }
        
        # R2108 Status Bits (binary sensors)
        self.r2108_bits = {
            0: {"name": "Fan Low Speed Mode", "bitmask": 0x1},
            2: {"name": "Bottom Heater", "bitmask": 0x4},
            3: {"name": "Crankcase Heater", "bitmask": 0x8},
            4: {"name": "Fan Defrost Speed Mode", "bitmask": 0x10},
            5: {"name": "Fan High Speed Mode", "bitmask": 0x20},
            6: {"name": "4way Valve", "bitmask": 0x40},
            11: {"name": "Pump Relay", "bitmask": 0x800},
        }
        
        # R2119 Status Bits (binary sensors - alarm and info bits)
        self.r2119_bits = {
            0: {"name": "Alarm - Main Line Current", "bitmask": 0x1},
            3: {"name": "Info - Compressor Oil Return", "bitmask": 0x8},
            4: {"name": "Alarm - High Pressure Switch", "bitmask": 0x10},
            6: {"name": "Alarm - 1st Start Pre-heat", "bitmask": 0x40},
            9: {"name": "Alarm - AC High/Low Voltage", "bitmask": 0x200},
            12: {"name": "Alarm - Low Pressure Switch", "bitmask": 0x1000},
        }
    
    def parse_read_response(self, start_register: int, values: list) -> Dict[str, Any]:
        """Parse read response and extract known sensor values with proper scaling and bit handling"""
        parsed_data = {}
        
        for i, value in enumerate(values):
            register_addr = start_register + i
            
            if register_addr not in self.register_mappings:
                continue
                
            mapping = self.register_mappings[register_addr]
            
            # Handle signed values for temperature readings
            if mapping["device_class"] == "temperature" and value > 32767:
                value = value - 65536  # Convert to signed 16-bit
            
            # Apply offset first, then scaling
            offset_value = value + mapping.get("offset", 0)
            scaled_value = offset_value * mapping["scale"]
            
            # Clamp temperature values to reasonable ranges
            if mapping["device_class"] == "temperature":
                scaled_value = max(TEMPERATURE_MIN, min(scaled_value, TEMPERATURE_MAX))
            
            parsed_data[mapping["name"]] = {
                "value": scaled_value,
                "unit": mapping["unit"],
                "device_class": mapping["device_class"],
                "register": register_addr,
                "raw_value": value
            }
            
            # Handle special bit registers
            if register_addr == 2108:
                self._parse_status_bits(parsed_data, value, register_addr, self.r2108_bits, "R2108")
            elif register_addr == 2118:
                # R2118 defrost mode (bit 0)
                defrost_active = bool(value & 0x1)
                parsed_data["Defrost Mode Active"] = {
                    "value": defrost_active,
                    "unit": "",
                    "device_class": "binary_sensor", 
                    "register": "2118b0",
                    "raw_value": value
                }
            elif register_addr == 2119:
                self._parse_status_bits(parsed_data, value, register_addr, self.r2119_bits, "R2119")
        
        return parsed_data

    def _parse_status_bits(self, parsed_data: dict, value: int, register_addr: int, 
                          bit_mappings: dict, prefix: str):
        """Helper method to parse status bits"""
        for bit_num, bit_info in bit_mappings.items():
            bit_value = bool(value & bit_info["bitmask"])
            parsed_data[f"{prefix} {bit_info['name']}"] = {
                "value": bit_value,
                "unit": "",
                "device_class": "binary_sensor",
                "register": f"{register_addr}b{bit_num}",
                "raw_value": value
            }

class QuattModbusSniffer:
    """
    Enhanced Quatt Modbus sniffer with Home Assistant integration.
    """
    
    def __init__(self, host='localhost', port=4444, 
                 mqtt_broker="localhost", mqtt_port=1883, mqtt_username=None, mqtt_password=None, 
                 device_prefix="quatt", device_config=None):
        self.host = host
        self.port = port
        self.running = False
        
        # Initialize MQTT integration
        self.mqtt = HomeAssistantMQTT(
            broker_host=mqtt_broker,
            broker_port=mqtt_port,
            username=mqtt_username,
            password=mqtt_password,
            device_prefix=device_prefix,
            device_config=device_config
        ) if MQTT_AVAILABLE else None
        
        # Initialize data parser
        self.data_parser = QuattDataParser()
        
        # Statistics and tracking
        self.stats = {
            'total_frames': 0,
            'valid_frames': 0,
            'requests': 0,
            'responses': 0,
            'errors': 0,
            'mqtt_publishes': 0
        }
        
        # Per-slave statistics
        self.slave_stats = {}
        
        # Track discovered slaves for HA setup
        self.discovered_slaves = set()
        
        self.pending_requests = {}
        
        # Sensors will be auto-discovered when each heat pump is first seen
    
    def setup_ha_sensors_for_slave(self, slave_id: int):
        """Setup Home Assistant sensor discovery for a specific slave"""
        if not self.mqtt or slave_id in self.discovered_slaves:
            return
        
        logger.info(f"🏠 Setting up Home Assistant sensors for Heat Pump {slave_id:02X}...")
        
        # Mark slave as discovered
        self.discovered_slaves.add(slave_id)
        
        # Setup sensors for known registers
        for mapping in self.data_parser.register_mappings.values():
            if mapping.get("device_class") != "binary_sensor":
                self.mqtt.publish_sensor_discovery(
                    mapping["name"],
                    slave_id,
                    mapping["unit"],
                    mapping["device_class"],
                    self.get_sensor_icon(mapping["device_class"])
                )
        
        # Setup binary sensors for status bits
        for bit_info in self.data_parser.r2108_bits.values():
            self.mqtt.publish_binary_sensor_discovery(f"R2108 {bit_info['name']}", slave_id)
        
        # Setup defrost mode binary sensor
        self.mqtt.publish_binary_sensor_discovery("Defrost Mode Active", slave_id)
        
        # Setup binary sensors for R2119 alarm/info bits  
        for bit_info in self.data_parser.r2119_bits.values():
            self.mqtt.publish_binary_sensor_discovery(f"R2119 {bit_info['name']}", slave_id)
        
        # General stats sensors (per heat pump)
        self.mqtt.publish_sensor_discovery("Communication Quality", slave_id, "%", None, "mdi:signal")
        self.mqtt.publish_sensor_discovery("Total Frames", slave_id, "", None, "mdi:counter")
        self.mqtt.publish_sensor_discovery("Response Time", slave_id, "ms", None, "mdi:timer")
        
        logger.info(f"✅ Home Assistant setup complete for Heat Pump {slave_id:02X}")
    
    def get_sensor_icon(self, device_class: str) -> str:
        """Get appropriate icon for sensor type"""
        icons = {
            "temperature": "mdi:thermometer",
            "power": "mdi:lightning-bolt",
            "pressure": "mdi:gauge",
            "energy": "mdi:flash",
            "voltage": "mdi:lightning-bolt",
            "current": "mdi:current-ac",
            "frequency": "mdi:sine-wave",
            "speed": "mdi:speedometer",
            "volume_flow_rate": "mdi:pipe"
        }
        return icons.get(device_class, "mdi:information")
    
    def start_server(self):
        """Start the TCP server with MQTT integration"""
        # Set up signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            logger.info("🛑 Received interrupt signal, shutting down gracefully...")
            self.stop_server()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Set a timeout so we can check for shutdown periodically
            self.server_socket.settimeout(1.0)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)
            self.running = True
            
            logger.info("=" * 70)
            logger.info("🏠 QUATT MODBUS SNIFFER WITH HOME ASSISTANT INTEGRATION")
            logger.info("=" * 70)
            logger.info(f"📡 Listening on: {self.host}:{self.port}")
            logger.info(f"🏠 MQTT: {'Connected' if self.mqtt and self.mqtt.connected else 'Disabled'}")
            logger.info("🔍 Ready to capture and analyze heat pump data")
            logger.info("=" * 70)
            
            # HA sensors will be auto-discovered per heat pump
            logger.info("🔍 Waiting for heat pump communication to auto-discover devices...")
            
            while self.running:
                try:
                    client_socket, client_address = self.server_socket.accept()
                    logger.info(f"📡 Sniffing device connected: {client_address}")
                    
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, client_address)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                    
                except socket.timeout:
                    # Check if we should still be running
                    continue
                except socket.error as e:
                    if self.running:
                        logger.error(f"Socket error: {e}")
                        break
                        
        except Exception as e:
            logger.error(f"Server error: {e}")
        finally:
            self.stop_server()
    
    def handle_client(self, client_socket, client_address):
        """Handle data from connected client with MQTT publishing"""
        buffer = b''
        
        try:
            while self.running:
                data = client_socket.recv(1024)
                if not data:
                    break
                    
                buffer += data
                buffer = self.extract_frames(buffer)
                
        except Exception as e:
            logger.error(f"Error handling client {client_address}: {e}")
        finally:
            client_socket.close()
            logger.info(f"📡 Client disconnected: {client_address}")
    
    def extract_frames(self, buffer):
        """Extract Modbus frames with CRC validation using optimized sliding window"""
        while len(buffer) >= MIN_FRAME_SIZE:
            frame_found = False
            
            # Use sliding window to find valid frames
            for start_pos in range(len(buffer) - 3):  # Ensure at least 4 bytes remain
                remaining = buffer[start_pos:]
                
                # Try different frame lengths
                for frame_len in range(MIN_FRAME_SIZE, min(len(remaining) + 1, MAX_FRAME_SIZE)):
                    potential_frame = remaining[:frame_len]
                    
                    if self.verify_crc(potential_frame):
                        self.process_frame(potential_frame)
                        # Remove processed frame and continue with remaining buffer
                        buffer = buffer[start_pos + frame_len:]
                        frame_found = True
                        break
                
                if frame_found:
                    break
            
            if not frame_found:
                # No valid frame found, discard old data if buffer is too large
                if len(buffer) > MAX_BUFFER_SIZE:
                    buffer = buffer[BUFFER_CLEANUP_SIZE:]  # Keep only recent data
                else:
                    break  # Wait for more data
                
        return buffer
    
    def verify_crc(self, frame):
        """Verify Modbus CRC"""
        if len(frame) < MIN_FRAME_SIZE:
            return False
        data = frame[:-2]
        received_crc = frame[-2:]
        calculated_crc = self.calculate_crc(data)
        return received_crc == calculated_crc
    
    def calculate_crc(self, data):
        """Calculate Modbus CRC16"""
        crc = MODBUS_CRC_INIT
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ MODBUS_CRC_POLY
                else:
                    crc >>= 1
        return struct.pack('<H', crc)
    
    def process_frame(self, frame_data):
        """Process frame and publish to MQTT"""
        try:
            self.stats['total_frames'] += 1
            
            if len(frame_data) < MIN_FRAME_SIZE:
                return
            
            device_id = frame_data[0]
            function_code = frame_data[1]
            current_time = time.time()
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            
            is_request = self.is_modbus_request(function_code, frame_data)
            
            if is_request:
                self.stats['requests'] += 1
                self.update_slave_stats(device_id, 'requests')
                self.pending_requests[device_id] = {
                    'frame': frame_data,
                    'time': current_time,
                    'function_code': function_code
                }
                
                request_info = self.parse_request(frame_data)
                logger.info(f"[{timestamp}] 📤 REQUEST  | Device: {device_id:02X} | {request_info}")
                
            else:
                self.stats['responses'] += 1
                self.update_slave_stats(device_id, 'responses')
                response_time_ms = 0
                
                if device_id in self.pending_requests:
                    request_time = self.pending_requests[device_id]['time']
                    response_time_ms = (current_time - request_time) * 1000
                    request_frame = self.pending_requests[device_id]['frame']
                    del self.pending_requests[device_id]
                else:
                    request_frame = None
                
                response_info = self.parse_response(frame_data, request_frame)
                logger.info(f"[{timestamp}] 📥 RESPONSE | Device: {device_id:02X} | {response_info} | ⏱️ {response_time_ms:.1f}ms")
                
                # Parse and publish sensor data for read responses
                self.handle_sensor_data(frame_data, request_frame, device_id, response_time_ms)
            
            self.stats['valid_frames'] += 1
            self.update_slave_stats(device_id, 'valid_frames')
            
            # Publish stats periodically
            if self.stats['total_frames'] % STATS_PUBLISH_INTERVAL == 0:
                self.publish_stats()
                
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"❌ Error processing frame: {e}")
    
    def handle_sensor_data(self, response_frame, request_frame, device_id, response_time):
        """Extract and publish sensor data to Home Assistant"""
        if not self.mqtt or not request_frame or response_frame[1] not in [0x03, 0x04]:
            return
        
        try:
            # Extract start register from request
            start_register = struct.unpack('>H', request_frame[2:4])[0]
            
            # Extract values from response
            byte_count = response_frame[2]
            values = []
            
            # Process values in pairs (16-bit registers)
            for i in range(0, byte_count, 2):
                if 3 + i + 1 < len(response_frame) - 2:  # Ensure we don't read past frame
                    val = struct.unpack('>H', response_frame[3 + i:5 + i])[0]
                    values.append(val)
            
            # Setup HA sensors for this slave if not already done
            self.setup_ha_sensors_for_slave(device_id)
            
            # Parse known sensors
            parsed_data = self.data_parser.parse_read_response(start_register, values)
            
            # Publish to Home Assistant with slave ID
            for sensor_name, sensor_data in parsed_data.items():
                if sensor_data.get("device_class") == "binary_sensor":
                    self.mqtt.publish_binary_sensor_data(sensor_name, device_id, sensor_data["value"])
                else:
                    self.mqtt.publish_sensor_data(sensor_name, device_id, sensor_data["value"])
                
                self.stats['mqtt_publishes'] += 1
                self.update_slave_stats(device_id, 'mqtt_publishes')
                
                logger.debug(f"🏠 Published {sensor_name}: {sensor_data['value']} {sensor_data.get('unit', '')} (device {device_id:02X})")
            
            # Publish response time for this specific heat pump
            self.mqtt.publish_sensor_data("Response Time", device_id, round(response_time, 1))
            
        except Exception as e:
            logger.error(f"Error publishing sensor data for device {device_id:02X}: {e}")
    
    def publish_stats(self):
        """Publish communication statistics per heat pump"""
        if not self.mqtt:
            return
        
        # Calculate overall communication quality
        quality = (self.stats['valid_frames'] / max(self.stats['total_frames'], 1)) * 100
        
        # Publish per-slave statistics
        for slave_id, slave_stats in self.slave_stats.items():
            if slave_id in self.discovered_slaves:
                slave_quality = (slave_stats['valid_frames'] / max(slave_stats['valid_frames'] + slave_stats.get('errors', 0), 1)) * 100
                self.mqtt.publish_sensor_data("Communication Quality", slave_id, round(slave_quality, 1))
                self.mqtt.publish_sensor_data("Total Frames", slave_id, slave_stats['valid_frames'])
        
        logger.info(f"📊 OVERALL STATS | Total: {self.stats['total_frames']} | "
                   f"Valid: {self.stats['valid_frames']} | "
                   f"MQTT: {self.stats['mqtt_publishes']} | "
                   f"Quality: {quality:.1f}%")
        
        # Log per-slave stats
        for slave_id, slave_stats in self.slave_stats.items():
            logger.info(f"📊 HP{slave_id:02X} | Frames: {slave_stats['valid_frames']} | "
                       f"Reqs: {slave_stats['requests']} | Resp: {slave_stats['responses']} | "
                       f"MQTT: {slave_stats['mqtt_publishes']}")
    
    # Parsing methods
    
    def update_slave_stats(self, slave_id: int, stat_type: str):
        """Update statistics for a specific slave"""
        if slave_id not in self.slave_stats:
            self.slave_stats[slave_id] = {
                'total_frames': 0,
                'valid_frames': 0,
                'requests': 0,
                'responses': 0,
                'errors': 0,
                'mqtt_publishes': 0
            }
        
        self.slave_stats[slave_id][stat_type] += 1
    
    def is_modbus_request(self, function_code, frame_data):
        """Determine if frame is a request or response"""
        # Error responses have function code with high bit set
        if function_code & 0x80:
            return False
            
        # Read functions: requests are typically 8 bytes
        if function_code in [0x01, 0x02, 0x03, 0x04]:
            return len(frame_data) <= 8
            
        # Write functions
        if function_code == 0x06:  # Write single register
            return len(frame_data) == 8
        elif function_code == 0x10:  # Write multiple registers
            return len(frame_data) > 9
            
        return True  # Default to request for unknown functions
    
    def parse_request(self, frame_data):
        """Parse request details"""
        function_code = frame_data[1]
        try:
            if function_code == 0x03:
                start_addr = struct.unpack('>H', frame_data[2:4])[0]
                count = struct.unpack('>H', frame_data[4:6])[0]
                return f"📖 Read Holding Registers | Start: {start_addr} (0x{start_addr:04X}) | Count: {count}"
            elif function_code == 0x04:
                start_addr = struct.unpack('>H', frame_data[2:4])[0]
                count = struct.unpack('>H', frame_data[4:6])[0]
                return f"📊 Read Input Registers | Start: {start_addr} (0x{start_addr:04X}) | Count: {count}"
            elif function_code == 0x06:
                addr = struct.unpack('>H', frame_data[2:4])[0]
                value = struct.unpack('>H', frame_data[4:6])[0]
                return f"✏️ Write Single Register | Addr: {addr} (0x{addr:04X}) | Value: {value}"
            else:
                return f"🔧 Function 0x{function_code:02X}"
        except Exception:
            return f"🔧 Function 0x{function_code:02X} (parse error)"
    
    def parse_response(self, frame_data, request_frame):
        """Parse response details"""
        function_code = frame_data[1]
        try:
            if function_code & 0x80:
                error_code = frame_data[2]
                return f"❌ ERROR Response | Function: 0x{function_code & 0x7F:02X} | Code: {error_code:02X}"
            elif function_code in [0x03, 0x04]:
                byte_count = frame_data[2]
                values = []
                for i in range(0, byte_count, 2):
                    if 3 + i + 1 < len(frame_data) - 2:
                        val = struct.unpack('>H', frame_data[3 + i:5 + i])[0]
                        values.append(str(val))
                return f"📖 Read Response | Bytes: {byte_count} | Values: [{', '.join(values[:8])}{'...' if len(values) > 8 else ''}]"
            else:
                return f"🔧 Function 0x{function_code:02X} Response"
        except Exception:
            return f"🔧 Function 0x{function_code:02X} Response (parse error)"
    
    def stop_server(self):
        """Stop the server gracefully"""
        logger.info("🔄 Stopping Quatt Modbus Sniffer...")
        self.running = False
        
        # Close server socket
        if hasattr(self, 'server_socket'):
            try:
                self.server_socket.close()
                logger.info("📡 Server socket closed")
            except Exception as e:
                logger.warning(f"⚠️ Error closing server socket: {e}")
        
        # Disconnect MQTT
        if self.mqtt and self.mqtt.client:
            try:
                self.mqtt.client.loop_stop()
                self.mqtt.client.disconnect()
                logger.info("🏠 MQTT client disconnected")
            except Exception as e:
                logger.warning(f"⚠️ Error disconnecting MQTT: {e}")
        
        logger.info("🔴 Quatt Modbus Sniffer Server stopped")

def load_config_file(config_path: str = "config.ini") -> dict:
    """Load configuration from INI file"""
    config = configparser.ConfigParser()
    defaults = {
        'server': {
            'host': 'localhost',
            'port': '4444'
        },
        'mqtt': {
            'broker_host': 'localhost',
            'broker_port': '1883',
            'username': '',
            'password': '',
            'device_prefix': 'quatt'
        },
        'devices': {
            'device_base_name': 'Quatt Heat Pump'
        }
    }
    
    if os.path.exists(config_path):
        config.read(config_path)
        logger.info(f"📋 Loaded configuration from {config_path}")
    else:
        logger.warning(f"⚠️ Config file {config_path} not found, using defaults")
        return defaults
    
    # Merge with defaults
    result = {}
    for section_name, section_defaults in defaults.items():
        result[section_name] = section_defaults.copy()
        if config.has_section(section_name):
            for key, value in config[section_name].items():
                result[section_name][key] = value
    
    # Handle any additional sections not in defaults (like custom device names)
    for section_name in config.sections():
        if section_name not in result:
            result[section_name] = {}
            for key, value in config[section_name].items():
                result[section_name][key] = value
    
    return result

def main():
    """Main entry point with MQTT configuration"""
    parser = argparse.ArgumentParser(description='Quatt Modbus Sniffer with Home Assistant Integration')
    parser.add_argument('--config', default='config.ini', help='Configuration file path')
    parser.add_argument('--mqtt-broker', help='MQTT broker host (overrides config)')
    parser.add_argument('--mqtt-username', help='MQTT username (overrides config)')
    parser.add_argument('--mqtt-password', help='MQTT password (overrides config)')
    parser.add_argument('--host', help='Server host (overrides config)')
    parser.add_argument('--port', type=int, help='Server port (overrides config)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    # Load configuration file
    config = load_config_file(args.config)
    
    # Set debug logging if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("🐛 Debug logging enabled")
    
    # Override config with command line arguments
    mqtt_broker = args.mqtt_broker or config['mqtt']['broker_host']
    mqtt_port = int(config['mqtt']['broker_port'])
    mqtt_username = args.mqtt_username or config['mqtt']['username'] or None
    mqtt_password = args.mqtt_password or config['mqtt']['password'] or None
    device_prefix = config['mqtt']['device_prefix']
    server_host = args.host or config['server']['host']
    server_port = args.port or int(config['server']['port'])
    
    # Clean up password (strip quotes if present)
    if mqtt_password:
        mqtt_password = mqtt_password.strip("'\"")  # Remove both single and double quotes
    
    logger.info(f"🏠 MQTT Broker: {mqtt_broker}:{mqtt_port}")
    logger.info(f"🏷️ Device Prefix: {device_prefix}")
    logger.info(f"👤 MQTT User: {mqtt_username or 'None'}")
    logger.info(f"📡 Server: {server_host}:{server_port}")
    
    if not MQTT_AVAILABLE:
        logger.warning("⚠️ paho-mqtt not available. Install with: pip install paho-mqtt")
    
    sniffer = QuattModbusSniffer(
        host=server_host,
        port=server_port,
        mqtt_broker=mqtt_broker,
        mqtt_port=mqtt_port,
        mqtt_username=mqtt_username,
        mqtt_password=mqtt_password,
        device_prefix=device_prefix,
        device_config=config.get('devices', {})
    )
    
    sniffer.start_server()

if __name__ == "__main__":
    main()
