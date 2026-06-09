import subprocess

from voice import speak


def handle(command):

    command = command.lower().strip()

    # ================= 🖥️ OPEN CMD =================

    if any(x in command for x in [

        "open command prompt",
        "open cmd",
        "launch cmd",
        "start command prompt",
        "terminal"

    ]):

        subprocess.Popen(
            "start cmd",
            shell=True
        )

        speak(
            "Opening command prompt"
        )

        return True

    # ================= ⚡ RUN TERMINAL COMMAND =================

    RUN_WORDS = [

        "run command",
        "execute command",
        "run",
        "execute",
        "cmd"
    ]

    for word in RUN_WORDS:

        if command.startswith(word):

            cmd = command.replace(
                word,
                "",
                1
            ).strip()

            if not cmd:

                speak(
                    "No command was provided"
                )

                return True

            try:

                subprocess.Popen(
                    cmd,
                    shell=True
                )

                speak(
                    "Running command"
                )

                return True

            except Exception as e:

                print(
                    "CMD error:",
                    e
                )

                speak(
                    "Command execution failed"
                )

                return True

    return False