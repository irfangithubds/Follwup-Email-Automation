import sys
import webbrowser
import threading
import time
import uvicorn

def open_browser():
    time.sleep(1.2)
    webbrowser.open("http://127.0.0.1:8000")

if __name__ == "__main__":
    print("==================================================")
    print("   Ensaan FollowUp Copilot - Starting Server      ")
    print("==================================================")
    print("Opening dashboard at http://127.0.0.1:8000 ...")
    
    # Launch browser in separate thread
    threading.Thread(target=open_browser, daemon=True).start()
    
    # Run FastAPI app
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False)
