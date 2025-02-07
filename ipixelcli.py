import json
import asyncio
import argparse
import websockets
from websockets.server import serve
from bleak import BleakClient, BleakError
from commands import *

COMMANDS = {
    "clear": clear,
    "set_brightness": set_brightness,
    "set_clock_mode": set_clock_mode,
    "set_fun_mode": set_fun_mode,
    "set_pixel": set_pixel,
    "delete_screen": delete_screen,
    "send_text": send_text,
    "set_screen": set_screen,
    "set_speed": set_speed,
    "send_animation": send_animation,
    "set_orientation": set_orientation
}

# Attempt to connect to the BLE device with retries
async def connect_to_device(address, max_retries=5):
    retries = 0
    while retries < max_retries:
        try:
            client = BleakClient(address)
            await client.connect()
            if client.is_connected:
                print("[INFO] Connected to the device")
                return client
        except BleakError as e:
            print(f"[ERROR] Connection failed ({retries + 1}/{max_retries}): {e}")
            retries += 1
            await asyncio.sleep(5)  # Wait before retrying
    print("[ERROR] Could not connect to the device after multiple attempts")
    return None

async def handle_websocket(websocket, path, address):
    client = await connect_to_device(address)
    if not client:
        return

    try:
        while True:
            message = await websocket.recv()
            try:
                command_data = json.loads(message)
                command_name = command_data.get("command")
                params = command_data.get("params", [])

                if command_name in COMMANDS:
                    positional_args = []
                    keyword_args = {}
                    for param in params:
                        if "=" in param:
                            key, value = param.split("=", 1)
                            keyword_args[key.replace('-', '_')] = value
                        else:
                            positional_args.append(param)

                    data = COMMANDS[command_name](*positional_args, **keyword_args)
                    await client.write_gatt_char("0000fa02-0000-1000-8000-00805f9b34fb", data)
                    response = {"status": "success", "command": command_name}
                else:
                    response = {"status": "error", "message": "Unknown command"}
            except Exception as e:
                response = {"status": "error", "message": str(e)}

            await websocket.send(json.dumps(response))
    except websockets.ConnectionClosed:
        print("[INFO] Websocket connection closed")
    except BleakError:
        print("[ERROR] BLE connection lost, attempting to reconnect...")
        await handle_websocket(websocket, path, address)  # Reconnect and restart
    finally:
        await client.disconnect()

async def start_server(ip, port, address):
    server = await serve(lambda ws, path: handle_websocket(ws, path, address), ip, port)
    print(f"WebSocket server started on ws://{ip}:{port}")
    await server.wait_closed()

async def execute_command(command_name, params, address):
    client = await connect_to_device(address)
    if not client:
        return

    try:
        if command_name in COMMANDS:
            positional_args = []
            keyword_args = {}
            for param in params:
                if "=" in param:
                    key, value = param.split("=", 1)
                    keyword_args[key.replace('-', '_')] = value
                else:
                    positional_args.append(param)

            data = COMMANDS[command_name](*positional_args, **keyword_args)
            await client.write_gatt_char("0000fa02-0000-1000-8000-00805f9b34fb", data)
            print(f"[INFO] Command '{command_name}' executed successfully.")
        else:
            print(f"[ERROR] Unknown command: {command_name}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WebSocket BLE Server")
    parser.add_argument("-s", "--server", action="store_true", help="Run as WebSocket server")
    parser.add_argument("-p", "--port", type=int, default=4444, help="Specify the port for the server")
    parser.add_argument("-c", "--command", nargs="+", metavar="COMMAND PARAMS",
                        help="Execute a specific command with parameters")
    parser.add_argument("-a", "--address", required=True, help="Specify the Bluetooth device address")

    args = parser.parse_args()

    if args.server:
        asyncio.run(start_server("localhost", args.port, args.address))
    elif args.command:
        command_name = args.command[0]
        params = args.command[1:]
        asyncio.run(execute_command(command_name, params, args.address))
    else:
        print("[ERROR] No mode specified. Use --server or -c with -a to specify an address.")
