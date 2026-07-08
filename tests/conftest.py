import os
import sys

# engine.py der Integration importierbar machen (ohne HA-Import).
ENGINE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "custom_components", "ev_assistant",
)
sys.path.insert(0, ENGINE_DIR)
