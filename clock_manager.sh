#!/bin/bash

# Name of the python script
APP_SCRIPT="adhan_clock.py"
# File to store the process ID
PID_FILE="adhan.pid"
# Log file
LOG_FILE="adhan.log"

start() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null; then
            echo "Adhaan clock is already running (PID: $PID)."
            return
        fi
    fi

    echo "Starting Adhaan clock..."
    nohup python3 "$APP_SCRIPT" > "$LOG_FILE" 2>&1 &
    NEW_PID=$!
    echo $NEW_PID > "$PID_FILE"
    echo "Adhaan clock started with PID: $NEW_PID."
}

stop() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null; then
            echo "Stopping Adhaan clock (PID: $PID)..."
            kill "$PID"
            rm "$PID_FILE"
            echo "Adhaan clock stopped."
        else
            echo "Adhaan clock was not running, but PID file existed. Removing PID file."
            rm "$PID_FILE"
        fi
    else
        echo "Adhaan clock is not running."
    fi
}

status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null; then
            echo "Adhaan clock is running (PID: $PID)."
        else
            echo "PID file exists, but Adhaan clock is not running."
        fi
    else
        echo "Adhaan clock is not running."
    fi
}

case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        stop
        sleep 2
        start
        ;;
    status)
        status
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
