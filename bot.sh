#!/bin/bash
# Work Hunter Bot - Start/Stop/Status script

BOT_DIR="/home/retro/Projects/web/work-hunter-bot"
VIRTUAL_ENV="$BOT_DIR/.venv"

BACKEND_PID_FILE="$BOT_DIR/bot.pid"
BACKEND_LOG="$BOT_DIR/work_hunter.log"

FRONTEND_DIR="$BOT_DIR/frontend"
FRONTEND_PID_FILE="$BOT_DIR/frontend.pid"
FRONTEND_LOG="$BOT_DIR/frontend.log"

kill_tree() {
    local pid="$1"
    local children
    children=$(pgrep -P "$pid" 2>/dev/null)
    for c in $children; do
        kill_tree "$c"
    done
    kill "$pid" 2>/dev/null
}

kill_pid() {
    local pid="$1"
    if ps -o pgid= -p "$pid" | grep -q "^ *$pid$" 2>/dev/null; then
        kill -- -"$pid" 2>/dev/null
    else
        kill_tree "$pid"
    fi
}

is_running() {
    [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null
}

start_backend() {
    if is_running "$BACKEND_PID_FILE"; then
        echo "Backend is already running (PID: $(cat $BACKEND_PID_FILE))"
        return
    fi
    cd "$BOT_DIR"
    PATH="$VIRTUAL_ENV/bin:$PATH"
    nohup "$VIRTUAL_ENV/bin/python" run.py >> "$BACKEND_LOG" 2>&1 &
    echo $! > "$BACKEND_PID_FILE"
    echo "Backend started (PID: $!)"
}

start_frontend() {
    if is_running "$FRONTEND_PID_FILE"; then
        echo "Frontend is already running (PID: $(cat $FRONTEND_PID_FILE))"
        return
    fi
    cd "$FRONTEND_DIR"
    setsid bash -c 'exec npm run dev' >> "$FRONTEND_LOG" 2>&1 &
    echo $! > "$FRONTEND_PID_FILE"
    echo "Frontend started (PID: $!)"
}

stop_backend() {
    if is_running "$BACKEND_PID_FILE"; then
        PID=$(cat "$BACKEND_PID_FILE")
        echo "Stopping backend (PID: $PID)..."
        kill_pid "$PID"
        sleep 2
        rm -f "$BACKEND_PID_FILE"
        echo "Backend stopped."
    else
        rm -f "$BACKEND_PID_FILE"
        echo "Backend is not running"
    fi
}

stop_frontend() {
    if is_running "$FRONTEND_PID_FILE"; then
        PID=$(cat "$FRONTEND_PID_FILE")
        echo "Stopping frontend (PID: $PID)..."
        kill_pid "$PID"
        sleep 2
        rm -f "$FRONTEND_PID_FILE"
        echo "Frontend stopped."
    else
        rm -f "$FRONTEND_PID_FILE"
        echo "Frontend is not running"
    fi
}

case "$1" in
    start)
        start_backend
        start_frontend
        echo "Logs: ./bot.sh logs (backend), ./bot.sh logs-frontend"
        ;;
    stop)
        stop_backend
        stop_frontend
        ;;
    restart)
        stop_backend
        stop_frontend
        start_backend
        start_frontend
        ;;
    status)
        if is_running "$BACKEND_PID_FILE"; then
            echo "Backend is running (PID: $(cat $BACKEND_PID_FILE))"
        else
            echo "Backend is not running"
        fi
        if is_running "$FRONTEND_PID_FILE"; then
            echo "Frontend is running (PID: $(cat $FRONTEND_PID_FILE))"
        else
            echo "Frontend is not running"
        fi
        ;;
    logs)
        tail -f "$BACKEND_LOG"
        ;;
    logs-frontend)
        tail -f "$FRONTEND_LOG"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|logs-frontend}"
        exit 1
        ;;
esac