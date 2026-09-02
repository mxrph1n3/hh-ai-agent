import asyncio
import os
from agent.runner import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Остановка.")
        os._exit(0)
