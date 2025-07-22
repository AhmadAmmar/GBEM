from graphviz import Digraph

# Create a new directed graph
flowchart = Digraph('Technical Methodology Workflow', format='png')
flowchart.attr(rankdir='TB', size='15', dpi='600')

# Data Acquisition
flowchart.node('A1', 'Data Acquisition', shape='parallelogram')
flowchart.node('A2', 'Remote Sensing Data (Sentinel-2 MSI, Sentinel-1 SAR, Landsat-8 LST)', shape='parallelogram')
flowchart.node('A3', 'LiDAR, Aerial, Street-view Imagery', shape='parallelogram')
flowchart.node('A4', 'Socioeconomic & Demographic Data', shape='parallelogram')

# Preprocessing
flowchart.node('B1', 'Data Preprocessing', shape='rectangle')
flowchart.node('B2', 'Georeferencing & Normalization', shape='rectangle')
flowchart.node('B3', 'Cloud Removal & Data Cleaning', shape='rectangle')
flowchart.node('B4', 'EPC Data Harmonization', shape='rectangle')

# Feature Extraction
flowchart.node('C1', 'Feature Extraction', shape='diamond')
flowchart.node('C2', 'Urban Indices (NDVI, NDBI, SAR Backscatter)', shape='diamond')
flowchart.node('C3', 'LiDAR-derived Metrics (Heights, Shadowing)', shape='diamond')
flowchart.node('C4', 'Socioeconomic Proxies for Energy Use', shape='diamond')

# Model Development
flowchart.node('D1', 'Model Development', shape='rectangle')
flowchart.node('D2', 'ML Models (Random Forest, XGBoost)', shape='rectangle')
flowchart.node('D3', 'DL Architectures (CNNs, Transformers)', shape='rectangle')
flowchart.node('D4', 'Hyperparameter Tuning', shape='rectangle')

# Evaluation & Refinement
flowchart.node('E1', 'Model Evaluation & Refinement', shape='rectangle')
flowchart.node('E2', 'Feature Importance Analysis', shape='rectangle')
flowchart.node('E3', 'Model Validation with Energy Audits', shape='rectangle')
flowchart.node('E4', 'Explainable AI (XAI)', shape='rectangle')

# Scalability & Integration
flowchart.node('F1', 'Scalability & Integration', shape='parallelogram')
flowchart.node('F2', 'Automated Geospatial Pipelines', shape='parallelogram')
flowchart.node('F3', 'Integration with BIM/BEM Frameworks', shape='parallelogram')
flowchart.node('F4', 'Continuous Monitoring (Temporal/Spatial)', shape='parallelogram')

# Results & Policy Applications
flowchart.node('G1', 'Results & Policy Applications', shape='rectangle')
flowchart.node('G2', 'Policy Impact Analysis', shape='rectangle')
flowchart.node('G3', 'Development of Dashboards/Visualization Tools', shape='rectangle')
flowchart.node('G4', 'Publication & Dissemination', shape='rectangle')

# Connecting the nodes
flowchart.edges([
    ('A1', 'A2'), ('A1', 'A3'), ('A1', 'A4'),
    ('A2', 'B1'), ('A3', 'B1'), ('A4', 'B1'),
    ('B1', 'B2'), ('B1', 'B3'), ('B1', 'B4'),
    ('B4', 'C1'),
    ('C1', 'C2'), ('C1', 'C3'), ('C1', 'C4'),
    ('C4', 'D1'),
    ('D1', 'D2'), ('D1', 'D3'), ('D1', 'D4'),
    ('D4', 'E1'),
    ('E1', 'E2'), ('E1', 'E3'), ('E1', 'E4'),
    ('E4', 'F1'),
    ('F1', 'F2'), ('F1', 'F3'), ('F1', 'F4'),
    ('F4', 'G1'),
    ('G1', 'G2'), ('G1', 'G3'), ('G1', 'G4')
])

# Render and save the flowchart
output_file = "D:/OneDrive - Ulster University/PhD/Output/workflow_flowchart4"
flowchart.render(output_file, view=True)
print(f"Flowchart saved to: {output_file}.png")
