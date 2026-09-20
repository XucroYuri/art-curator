"""Isolated HPSv3 evidence producer; coordinator owns all persistence."""
from .worker_runtime import serve


if __name__ == "__main__":
    serve("hpsv3")
