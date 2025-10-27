import os

def read_md_files_from_folder(folder_path):
    md_files = {}
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.endswith(".md"):
                file_path = os.path.join(root, file)
                with open(file_path, "r", encoding="utf-8") as f:
                    md_files[file] = f.read()
    return md_files

def get_context_from_md_files(md_files):
    return "\n".join(md_files.values())