from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.websocket.manager import manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # We don't expect inbound data from the browser on this socket,
            # but we must keep reading or the connection is considered idle/closed.
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"event": "pong", "data": {}}')
    except WebSocketDisconnect:
        manager.disconnect(websocket)
