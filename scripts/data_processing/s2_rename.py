import os
import shutil

# Define the input and output folders
input_folder = r"D:\OneDrive - Ulster University\PhD\data\london\Sat\Bands"
output_folder = r"D:\OneDrive - Ulster University\PhD\data\london\Sat\Renamed_Bands"

# Ensure the output folder exists
os.makedirs(output_folder, exist_ok=True)

# Define the mapping for renaming
rename_map = {
    "B1": "B2",
    "B2": "B3",
    "B3": "B4",
    "B4": "B5",
    "B5": "B6",
    "B6": "B7",
    "B7": "B8",
    "B8": "B8A",
    "B9": "B11",
    "B10": "B12"
}

# Iterate through files in the input folder
for filename in os.listdir(input_folder):
    old_name, ext = os.path.splitext(filename)  # Split filename and extension
    if old_name in rename_map:
        new_name = rename_map[old_name] + ext  # Map the new name and add the extension
        old_path = os.path.join(input_folder, filename)
        new_path = os.path.join(output_folder, new_name)
        shutil.copy2(old_path, new_path)  # Copy the file to the new folder with the new name
        print(f"Copied and renamed: {filename} -> {new_name}")
    else:
        print(f"Skipped: {filename} (no mapping found)")

print("Renaming and copying completed.")
