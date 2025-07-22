import os

folder_path = r"D:\OneDrive - Ulster University\PhD\Data"
file_extensions = set()

for file in os.listdir(folder_path):
    if os.path.isfile(os.path.join(folder_path, file)):
        _, extension = os.path.splitext(file)
        if extension:
            file_extensions.add(extension.lower())

print("File extensions found:", file_extensions)
