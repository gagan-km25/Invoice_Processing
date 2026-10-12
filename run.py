"""Entry point: `python run.py` → http://127.0.0.1:5000

Localhost-only by design (NFR-1). Stop with Ctrl+C.
"""
from app import create_app
from app.config import Config

app = create_app()

if __name__ == "__main__":
    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG,
        use_reloader=Config.USE_RELOADER,
        threaded=True,  # UI stays responsive while the worker processes jobs
    )
