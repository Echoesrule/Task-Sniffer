#!/bin/bash
# Work Hunter Bot - Start/Stop/Status script

BOT_DIR="/home/retro/work-hunter-bot"
PID_FILE="$BOT_DIR/bot.pid"
LOG_FILE="$BOT_DIR/work_hunter.log"

case "$1" in
    start)
        if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
            echo "Bot is already running (PID: $(cat $PID_FILE))"
            exit 1
        fi
        echo "Starting Work Hunter Bot..."
        cd "$BOT_DIR"
        source venv/bin/activate
        nohup python run.py >> "$LOG_FILE" 2>&1 &
        echo $! > "$PID_FILE"
        echo "Bot started (PID: $!)"
        echo "Logs: tail -f $LOG_FILE"
        ;;
    stop)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if kill -0 "$PID" 2>/dev/null; then
                echo "Stopping bot (PID: $PID)..."
                kill "$PID"
                sleep 2
                rm -f "$PID_FILE"
                echo "Bot stopped."
            else
                echo "Bot not running (stale PID file)"
                rm -f "$PID_FILE"
            fi
        else
            echo "Bot is not running"
        fi
        ;;
    status)
        if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
            echo "Bot is running (PID: $(cat $PID_FILE))"
        else
            echo "Bot is not running"
        fi
        ;;
    logs)
        tail -f "$LOG_FILE"
        ;;
    *)
        echo "Usage: $0 {start|stop|status|logs}"
        exit 1
        ;;
esac
