import os
import shutil

from voice import speak

# ================= 📂 TARGET FOLDER =================

DOWNLOADS = os.path.expanduser(
    "~/Downloads"
)

# ================= 📁 FILE CATEGORIES =================

CATEGORIES = {

    "Images": (
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp"
    ),

    "Videos": (
        ".mp4",
        ".mov",
        ".avi",
        ".mkv"
    ),

    "Music": (
        ".mp3",
        ".wav",
        ".flac"
    ),

    "Documents": (
        ".pdf",
        ".docx",
        ".txt",
        ".pptx",
        ".xlsx",
        ".csv"
    ),

    "Programs": (
        ".exe",
        ".msi"
    ),

    "Code": (
        ".py",
        ".html",
        ".css",
        ".js",
        ".cpp",
        ".ino",
        ".java"
    ),

    "Archives": (
        ".zip",
        ".rar",
        ".7z"
    )
}

# ================= 📂 ORGANIZER =================

def organize_folder(folder_path):

    moved_count = 0

    for file in os.listdir(folder_path):

        path = os.path.join(
            folder_path,
            file
        )

        # skip folders
        if os.path.isdir(path):

            continue

        destination_folder = None

        # ================= 📁 CATEGORY MATCH =================

        for category, extensions in CATEGORIES.items():

            if file.lower().endswith(extensions):

                destination_folder = os.path.join(
                    folder_path,
                    category
                )

                break

        # ================= ❓ UNKNOWN FILES =================

        if not destination_folder:

            destination_folder = os.path.join(
                folder_path,
                "Remaining"
            )

        os.makedirs(
            destination_folder,
            exist_ok=True
        )

        try:

            shutil.move(
                path,
                os.path.join(
                    destination_folder,
                    file
                )
            )

            moved_count += 1

        except Exception as e:

            print(
                "Move error:",
                e
            )

    return moved_count

# ================= 🎯 HANDLER =================

def handle(command):

    command = command.lower().strip()

    # ================= 📂 DOWNLOADS =================

    if any(x in command for x in [

        "organize downloads",
        "clean downloads",
        "sort downloads",
        "arrange downloads",
        "clean my downloads",
        "sort my files"

    ]):

        speak("Organizing downloads")

        moved = organize_folder(
            DOWNLOADS
        )

        speak(
            f"Organized {moved} files"
        )

        return True

    # ================= 🖥️ DESKTOP =================

    elif any(x in command for x in [

        "organize desktop",
        "clean desktop",
        "sort desktop"

    ]):

        desktop = os.path.expanduser(
            "~/Desktop"
        )

        speak("Organizing desktop")

        moved = organize_folder(
            desktop
        )

        speak(
            f"Organized {moved} files"
        )

        return True

    return False