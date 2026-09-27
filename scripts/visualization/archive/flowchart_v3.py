from graphviz import Digraph

# Create the flowchart object
flowchart = Digraph('Flexible Methodology Workflow', format='png')
flowchart.attr(rankdir='TB', size='15', dpi='600')  # Top to Bottom layout

# Data Acquisition
flowchart.node('A', 'Data Acquisition', shape='parallelogram')
flowchart.node('A1', 'Remote Sensing Data - Sentinel-2, Sentinel-1, Landsat-8, LiDAR)', shape='parallelogram')
flowchart.node('A2', 'EPC Data & Socioeconomic Data', shape='parallelogram')
flowchart.node('A3', 'Environmental Data - UHI, LCZ, Climate)', shape='parallelogram')

# Data Preprocessing
flowchart.node('B', 'Data Preprocessing', shape='rectangle')
flowchart.node('B1', 'Georeferencing, Cloud Masking, Normalization', shape='rectangle')
flowchart.node('B2', 'Spatial Alignment - Raster-to-Vector)', shape='rectangle')

# Feature Engineering
flowchart.node('C', 'Feature Engineering', shape='rectangle')
flowchart.node('C1', 'Spectral Indices - NDVI, NDBI, IBI)', shape='rectangle')
flowchart.node('C2', 'SAR Metrics - VV/VH Ratio, Coherence)', shape='rectangle')
flowchart.node('C3', 'LiDAR-based Urban Morphology - Height, SVF, Shadows)', shape='rectangle')
flowchart.node('C4', 'Socioeconomic & Demographic Proxies', shape='rectangle')

# Machine Learning Modeling
flowchart.node('D', 'Machine Learning Modeling', shape='rectangle')
flowchart.node('D1', 'Baseline Models - Random Forest, XGBoost)', shape='rectangle')
flowchart.node('D2', 'Advanced Models - CNNs, Ensemble Learning)', shape='rectangle')
flowchart.node('D3', 'Hyperparameter Tuning & Optimization', shape='rectangle')

# Validation & Evaluation
flowchart.node('E', 'Validation & Evaluation', shape='diamond')
flowchart.node('E1', 'Accuracy Metrics - Confusion Matrix, RMSE)', shape='rectangle')
flowchart.node('E2', 'Spatial Cross-Validation', shape='rectangle')
flowchart.node('E3', 'Ground Truth Comparison against Energy Audits)', shape='rectangle')

# Planned Enhancements
flowchart.node('F', 'Planned Enhancements', shape='rectangle', style='filled', fillcolor='lightblue')
flowchart.node('F1', 'Integration with BIM/BEM Models', shape='rectangle', style='filled', fillcolor='lightblue')
flowchart.node('F2', 'Explainable AI (XAI) for Model Interpretation', shape='rectangle', style='filled', fillcolor='lightblue')
flowchart.node('F3', 'Automated Geospatial Pipeline, Scalable Assessments)', shape='rectangle', style='filled', fillcolor='lightblue')
flowchart.node('F4', 'Temporal Monitoring of Urban Energy Trends', shape='rectangle', style='filled', fillcolor='lightblue')

# Connecting Nodes
flowchart.edges([('A', 'A1'), ('A', 'A2'), ('A', 'A3')])
flowchart.edge('A1', 'B')
flowchart.edge('A2', 'B')
flowchart.edge('A3', 'B')
flowchart.edge('B', 'B1')
flowchart.edge('B1', 'B2')
flowchart.edge('B2', 'C')
flowchart.edge('C', 'C1')
flowchart.edge('C1', 'C2')
flowchart.edge('C2', 'C3')
flowchart.edge('C3', 'C4')
flowchart.edge('C4', 'D')
flowchart.edge('D', 'D1')
flowchart.edge('D1', 'D2')
flowchart.edge('D2', 'D3')
flowchart.edge('D3', 'E')
flowchart.edge('E', 'E1')
flowchart.edge('E1', 'E2')
flowchart.edge('E2', 'E3')

# Linking Planned Enhancements
flowchart.edge('E3', 'F')
flowchart.edge('F', 'F1')
flowchart.edge('F1', 'F2')
flowchart.edge('F2', 'F3')
flowchart.edge('F3', 'F4')

# Render and save the flowchart
output_file = "D:/OneDrive - Ulster University/PhD/Output/workflow_flowchart3"
flowchart.render(output_file, view=True)
print(f"Flowchart saved to: {output_file}.png")