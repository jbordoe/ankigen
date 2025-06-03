import os
import logging
from rich.logging import RichHandler

# Configure rich logging
FORMAT = "%(message)s"
logging.basicConfig(
    level="INFO", format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)
log = logging.getLogger("rich")

if not os.environ.get("GOOGLE_API_KEY"):
    log.error("GOOGLE_API_KEY environment variable not set. Please set it to your Google Cloud API key.")
    exit(1)

log.info("Hello World!")
