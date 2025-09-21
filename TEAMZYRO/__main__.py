import os
from flask import Flask
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"

port = int(os.getenv("PORT", 8080))
app.run(host="0.0.0.0", port=port)
from TEAMZYRO import *
import importlib
import logging
from TEAMZYRO.modules import ALL_MODULES


def main() -> None:
    for module_name in ALL_MODULES:
        imported_module = importlib.import_module("TEAMZYRO.modules." + module_name)
    LOGGER("TEAMZYRO.modules").info("𝐀𝐥𝐥 𝐅𝐞𝐚𝐭𝐮𝐫𝐞𝐬 𝐋𝐨𝐚𝐝𝐞𝐝 𝐁𝐚𝐛𝐲🥳...")

    ZYRO.start()
    application.run_polling(drop_pending_updates=True)
    send_start_message()
    LOGGER("TEAMZYRO").info(
        "╔═════ஜ۩۞۩ஜ════╗\n  ☠︎︎MADE BY GOJOXNETWORK☠︎︎\n╚═════ஜ۩۞۩ஜ════╝"
    )

if __name__ == "__main__":
    main()
    
    
