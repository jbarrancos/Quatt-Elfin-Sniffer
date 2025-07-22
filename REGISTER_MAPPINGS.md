# Quatt Heat Pump Register Mappings

## Temperature Sensors
| Register | Name | Unit | Notes |
|----------|------|------|-------|
| 2110 | Outside Temperature | °C | Outdoor ambient |
| 2111 | Evaporator Coil Temperature | °C | Coil sensor |
| 2112 | Gas Discharge Temperature | °C | Compressor output |
| 2113 | Gas Return Temperature | °C | Compressor input |
| 2131 | Condensing Temperature | °C | Calculated |
| 2132 | Evaporating Temperature | °C | Calculated |
| 2133 | Water In Temperature | °C | Inlet water |
| 2134 | Water Out Temperature | °C | Outlet water |
| 2135 | Condenser Coil Temperature | °C | Indoor coil |

## Pressure & Flow
| Register | Name | Unit | Notes |
|----------|------|------|-------|
| 2116 | Evaporator Pressure | bar | Low pressure side |
| 2117 | Condenser Pressure | bar | High pressure side |
| 2138 | Pump Flow | L/h | Water flow rate |

## Power & Control
| Register | Name | Unit | Notes |
|----------|------|------|-------|
| 2100 | Compressor AC Voltage | V | Input voltage |
| 2101 | Compressor AC Current | A | Input current |
| 2102 | Compressor Frequency Demand | Hz | Requested speed |
| 2103 | Compressor Frequency Actual | Hz | Actual speed |
| 2137 | Pump Power | W | Water pump power |

## Status Information
| Register | Name | Type | Notes |
|----------|------|------|-------|
| 2099 | Working Mode Actual | Value | Current operation mode |
| 2104 | Fan Speed Maximum | RPM | Max fan speed |
| 2105 | Fan Speed Actual | RPM | Current fan speed |
| 2107 | Electric Expansion Valve | p | Valve position |
| 2118 | Defrost Mode | Binary | Defrost active |
| 2122 | Firmware Version | Value | Software version |
| 2123 | EEPROM Version | Value | Config version |

## Status Bits (R2108)
- Bit 0: Fan Low Speed Mode
- Bit 2: Bottom Heater
- Bit 3: Crankcase Heater  
- Bit 4: Fan Defrost Speed Mode
- Bit 5: Fan High Speed Mode
- Bit 6: 4-way Valve
- Bit 11: Pump Relay

## Alarm Bits (R2119)
- Bit 0: Main Line Current Alarm
- Bit 3: Compressor Oil Return Info
- Bit 4: High Pressure Switch Alarm
- Bit 6: 1st Start Pre-heat Alarm
- Bit 9: AC High/Low Voltage Alarm
- Bit 12: Low Pressure Switch Alarm
