import pandas as pd

# File paths
input_file = "D:/OneDrive - Ulster University/PhD/data/reduced_merged_certificates.csv"
output_file = "D:/OneDrive - Ulster University/PhD/data/column_datatypes.csv"

# List of columns to analyze
columns_to_check = [
    "BUILDING_REFERENCE_NUMBER", "CURRENT_ENERGY_RATING", "POTENTIAL_ENERGY_RATING",
    "CURRENT_ENERGY_EFFICIENCY", "POTENTIAL_ENERGY_EFFICIENCY", "PROPERTY_TYPE",
    "BUILT_FORM", "LOCAL_AUTHORITY", "CONSTITUENCY", "COUNTY", "TRANSACTION_TYPE",
    "ENVIRONMENT_IMPACT_CURRENT", "ENVIRONMENT_IMPACT_POTENTIAL", "ENERGY_CONSUMPTION_CURRENT",
    "ENERGY_CONSUMPTION_POTENTIAL", "CO2_EMISSIONS_CURRENT", "CO2_EMISS_CURR_PER_FLOOR_AREA",
    "CO2_EMISSIONS_POTENTIAL", "LIGHTING_COST_CURRENT", "LIGHTING_COST_POTENTIAL",
    "HEATING_COST_CURRENT", "HEATING_COST_POTENTIAL", "HOT_WATER_COST_CURRENT",
    "HOT_WATER_COST_POTENTIAL", "TOTAL_FLOOR_AREA", "ENERGY_TARIFF", "MAINS_GAS_FLAG",
    "FLOOR_LEVEL", "FLAT_TOP_STOREY", "FLAT_STOREY_COUNT", "MAIN_HEATING_CONTROLS",
    "MULTI_GLAZE_PROPORTION", "GLAZED_TYPE", "GLAZED_AREA", "EXTENSION_COUNT",
    "NUMBER_HABITABLE_ROOMS", "NUMBER_HEATED_ROOMS", "LOW_ENERGY_LIGHTING",
    "NUMBER_OPEN_FIREPLACES", "HOTWATER_DESCRIPTION", "HOT_WATER_ENERGY_EFF",
    "HOT_WATER_ENV_EFF", "FLOOR_DESCRIPTION", "FLOOR_ENERGY_EFF", "FLOOR_ENV_EFF",
    "WINDOWS_DESCRIPTION", "WINDOWS_ENERGY_EFF", "WINDOWS_ENV_EFF", "WALLS_DESCRIPTION",
    "WALLS_ENERGY_EFF", "WALLS_ENV_EFF", "SECONDHEAT_DESCRIPTION", "SHEATING_ENERGY_EFF",
    "SHEATING_ENV_EFF", "ROOF_DESCRIPTION", "ROOF_ENERGY_EFF", "ROOF_ENV_EFF",
    "MAINHEAT_DESCRIPTION", "MAINHEAT_ENERGY_EFF", "MAINHEAT_ENV_EFF",
    "MAINHEATCONT_DESCRIPTION", "MAINHEATC_ENERGY_EFF", "MAINHEATC_ENV_EFF",
    "LIGHTING_DESCRIPTION", "LIGHTING_ENERGY_EFF", "LIGHTING_ENV_EFF", "MAIN_FUEL",
    "WIND_TURBINE_COUNT", "HEAT_LOSS_CORRIDOR", "UNHEATED_CORRIDOR_LENGTH", "FLOOR_HEIGHT",
    "SOLAR_WATER_HEATING_FLAG", "MECHANICAL_VENTILATION", "CONSTRUCTION_AGE_BAND", "TENURE",
    "FIXED_LIGHTING_OUTLETS_COUNT", "LOW_ENERGY_FIXED_LIGHT_COUNT", "LATITUDE", "LONGITUDE"
]

# Initialize data types dictionary
column_datatypes = {col: None for col in columns_to_check}

# Chunk size for processing
chunk_size = 100000

# Process the file in chunks
print("Processing file in chunks...")
with pd.read_csv(input_file, usecols=columns_to_check, chunksize=chunk_size, low_memory=False) as reader:
    for chunk_idx, chunk in enumerate(reader):
        print(f"Processing chunk {chunk_idx + 1}...")
        for col in columns_to_check:
            try:
                inferred_dtype = pd.api.types.infer_dtype(chunk[col], skipna=True)
                if column_datatypes[col] is None:
                    column_datatypes[col] = inferred_dtype
                elif column_datatypes[col] != inferred_dtype:
                    column_datatypes[col] = "mixed"
            except Exception as e:
                print(f"Error processing column {col}: {e}")
                column_datatypes[col] = "error"

# Save results to a file
print("Saving results...")
dtype_df = pd.DataFrame.from_dict(column_datatypes, orient="index", columns=["DataType"])
dtype_df.index.name = "Column"
dtype_df.reset_index(inplace=True)
dtype_df.to_csv(output_file, index=False)

print(f"Column datatypes saved to: {output_file}")
