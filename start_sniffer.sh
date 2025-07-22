#!/bin/bash

# Quatt Modbus Sniffer - Background Daemon Script
# This script starts the Quatt Modbus Sniffer in the background
# allowing you to start it via SSH and safely disconnect.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/quatt_modbus_sniffer.py"
CONFIG_FILE="$SCRIPT_DIR/config.ini"
PID_FILE="$SCRIPT_DIR/quatt_sniffer.pid"
LOG_FILE="$SCRIPT_DIR/quatt_modbus_sniffer.log"

# Function to check if the process is running
is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            return 0
        else
            # PID file exists but process is not running, clean up
            rm -f "$PID_FILE"
            return 1
        fi
    else
        return 1
    fi
}

# Function to start the sniffer
start_sniffer() {
    if is_running; then
        PID=$(cat "$PID_FILE")
        echo "🟡 Quatt Modbus Sniffer is already running (PID: $PID)"
        return 1
    fi
    
    echo "🚀 Starting Quatt Modbus Sniffer in background..."
    
    # Check if Python script exists
    if [ ! -f "$PYTHON_SCRIPT" ]; then
        echo "❌ Error: Python script not found at $PYTHON_SCRIPT"
        return 1
    fi
    
    # Check if config file exists
    if [ ! -f "$CONFIG_FILE" ]; then
        echo "❌ Error: Configuration file not found at $CONFIG_FILE"
        return 1
    fi
    
    # Start the process in background with nohup
    nohup python3 "$PYTHON_SCRIPT" --config "$CONFIG_FILE" > "$LOG_FILE" 2>&1 &
    
    # Get the PID and save it
    PID=$!
    echo $PID > "$PID_FILE"
    
    # Wait a moment to check if it started successfully
    sleep 2
    
    if is_running; then
        echo "✅ Quatt Modbus Sniffer started successfully!"
        echo "📋 PID: $PID"
        echo "📄 Log file: $LOG_FILE"
        echo "🔧 PID file: $PID_FILE"
        echo ""
        echo "💡 Use './start_sniffer.sh status' to check status"
        echo "💡 Use './start_sniffer.sh stop' to stop the service"
        echo "💡 Use './start_sniffer.sh logs' to view recent logs"
        return 0
    else
        echo "❌ Failed to start Quatt Modbus Sniffer"
        rm -f "$PID_FILE"
        return 1
    fi
}

# Function to stop the sniffer
stop_sniffer() {
    if ! is_running; then
        echo "🟡 Quatt Modbus Sniffer is not running"
        return 1
    fi
    
    PID=$(cat "$PID_FILE")
    echo "🛑 Stopping Quatt Modbus Sniffer (PID: $PID)..."
    
    # Try graceful shutdown first
    kill -TERM "$PID" 2>/dev/null
    
    # Wait up to 10 seconds for graceful shutdown
    for i in {1..10}; do
        if ! ps -p "$PID" > /dev/null 2>&1; then
            echo "✅ Quatt Modbus Sniffer stopped gracefully"
            rm -f "$PID_FILE"
            return 0
        fi
        sleep 1
    done
    
    # Force kill if still running
    echo "⚠️  Forcing shutdown..."
    kill -KILL "$PID" 2>/dev/null
    
    # Wait a bit more
    sleep 2
    
    if ! ps -p "$PID" > /dev/null 2>&1; then
        echo "✅ Quatt Modbus Sniffer stopped (forced)"
        rm -f "$PID_FILE"
        return 0
    else
        echo "❌ Failed to stop Quatt Modbus Sniffer"
        return 1
    fi
}

# Function to restart the sniffer
restart_sniffer() {
    echo "🔄 Restarting Quatt Modbus Sniffer..."
    stop_sniffer
    sleep 2
    start_sniffer
}

# Function to show status
show_status() {
    if is_running; then
        PID=$(cat "$PID_FILE")
        echo "✅ Quatt Modbus Sniffer is running"
        echo "📋 PID: $PID"
        echo "📄 Log file: $LOG_FILE"
        echo "🔧 PID file: $PID_FILE"
        
        # Show memory and CPU usage if ps supports it
        if ps -p "$PID" -o pid,ppid,pcpu,pmem,etime,cmd > /dev/null 2>&1; then
            echo ""
            echo "📊 Process Info:"
            ps -p "$PID" -o pid,ppid,pcpu,pmem,etime,cmd
        fi
        
        return 0
    else
        echo "🔴 Quatt Modbus Sniffer is not running"
        return 1
    fi
}

# Function to show recent logs
show_logs() {
    if [ -f "$LOG_FILE" ]; then
        echo "📄 Recent logs from $LOG_FILE:"
        echo "═══════════════════════════════════════════════════════════════"
        tail -n 50 "$LOG_FILE"
    else
        echo "❌ Log file not found at $LOG_FILE"
        return 1
    fi
}

# Function to follow logs in real-time
follow_logs() {
    if [ -f "$LOG_FILE" ]; then
        echo "📄 Following logs from $LOG_FILE (Press Ctrl+C to exit):"
        echo "═══════════════════════════════════════════════════════════════"
        tail -f "$LOG_FILE"
    else
        echo "❌ Log file not found at $LOG_FILE"
        return 1
    fi
}

# Function to show usage
show_usage() {
    echo "Quatt Modbus Sniffer - Background Daemon Control Script"
    echo "Usage: $0 {start|stop|restart|status|logs|tail|help}"
    echo ""
    echo "Commands:"
    echo "  start     - Start the Quatt Modbus Sniffer in background"
    echo "  stop      - Stop the running Quatt Modbus Sniffer"
    echo "  restart   - Restart the Quatt Modbus Sniffer"
    echo "  status    - Show current status and process information"
    echo "  logs      - Show recent log entries (last 50 lines)"
    echo "  tail      - Follow logs in real-time"
    echo "  help      - Show this usage information"
    echo ""
    echo "Examples:"
    echo "  ./start_sniffer.sh start       # Start in background"
    echo "  ./start_sniffer.sh status      # Check if running"
    echo "  ./start_sniffer.sh logs        # View recent logs"
    echo "  ./start_sniffer.sh stop        # Stop the service"
    echo ""
    echo "Files:"
    echo "  Script:     $PYTHON_SCRIPT"
    echo "  Config:     $CONFIG_FILE"
    echo "  PID file:   $PID_FILE"
    echo "  Log file:   $LOG_FILE"
}

# Main script logic
case "$1" in
    start)
        start_sniffer
        ;;
    stop)
        stop_sniffer
        ;;
    restart)
        restart_sniffer
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    tail|follow)
        follow_logs
        ;;
    help|--help|-h)
        show_usage
        ;;
    *)
        echo "❌ Invalid command: $1"
        echo ""
        show_usage
        exit 1
        ;;
esac

exit $?
