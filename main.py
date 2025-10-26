import uvicorn
from src.api_server import APIServer

if __name__ == "__main__":
    server = APIServer()
    uvicorn.run(server.app, host="0.0.0.0", port=8000, log_level="info")