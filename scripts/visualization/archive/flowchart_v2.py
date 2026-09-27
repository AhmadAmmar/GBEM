from graphviz import Digraph

# Create the Digraph object
flowchart = Digraph('Building Energy Efficiency Methodology', format='png')
flowchart.attr(rankdir='TB', size='8', dpi='600', splines='ortho')  # Top-to-bottom layout

# Function to connect nodes horizontally without arrows
def connect_horizontal(flowchart, nodes):
    for i in range(len(nodes) - 1):
        flowchart.edge(nodes[i], nodes[i + 1], arrowhead='none')  # Line without arrow

# Data Acquisition Cluster
with flowchart.subgraph(name='cluster_A') as da:
    da.attr(label='Data Acquisition', style='rounded', color='black', fontsize='16')
    da.attr(rank='same')
    da.node('A1', 'Remote Sensing Data\n(Sentinel-1 SAR, Sentinel-2 MSI, Thermal Imagery, LiDaR)', shape='parallelogram')
    da.node('A2', 'Aerial & Street-view\n(Google Maps API)', shape='parallelogram')
    da.node('A3', 'EPC Data\n(Energy Performance Certificates)', shape='parallelogram')
    da.node('A4', 'Building Geometries\n(OSM, OS, Verisk)', shape='parallelogram')
    da.node('A5', 'Socioeconomic & Demographic Data\n(Density, Consumption, Usage Patterns)', shape='parallelogram')
    da.node('A6', 'Climatic Data\n(ERA5, Met Office)', shape='parallelogram')
    connect_horizontal(da, ['A1', 'A2', 'A3', 'A4', 'A5', 'A6'])

# Data Preprocessing Cluster
with flowchart.subgraph(name='cluster_B') as dp:
    dp.attr(label='Data Preprocessing', style='rounded', color='black', fontsize='16')
    dp.attr(rank='same')
    dp.node('B1', 'Geospatial Alignment\n(CRS Standardization, Resampling, Normalization, Patching)', shape='parallelogram')
    dp.node('B2', 'Noise Reduction\n(Cloud Masking, SAR Filtering)', shape='parallelogram')
    dp.node('B3', 'EPC Data Cleaning & Harmonization', shape='parallelogram')
    dp.node('B4', 'Raster to Vector Mapping\n(Building Footprints Overlay)', shape='parallelogram')
    connect_horizontal(dp, ['B1', 'B2', 'B3', 'B4'])

# Feature Engineering Cluster
with flowchart.subgraph(name='cluster_C') as fe:
    fe.attr(label='Feature Engineering', style='rounded', color='black')
    fe.attr(rank='same')
    fe.node('C1', 'Urban Indices\n(NDVI, NDBI, UI, IBI)', shape='parallelogram')
    fe.node('C2', 'SAR Features\n(VV/VH Ratio, Texture Metrics)', shape='parallelogram')
    fe.node('C3', 'LiDAR Features\n(Height, Shadow Analysis)', shape='parallelogram')
    connect_horizontal(fe, ['C1', 'C2', 'C3'])

# Model Development Cluster
with flowchart.subgraph(name='cluster_D') as md:
    md.attr(label='Model Development', style='rounded', color='black')
    md.attr(rank='same')
    md.node('D1', 'ML Models\n(Random Forest, XGBoost, Ensemble)', shape='parallelogram')
    md.node('D2', 'DL Models (CNNs, Transformers)\nExplainable AI (XAI - Model Interpretability)', shape='parallelogram')
    md.node('D3', 'Statistical, Linear and Physics-based Modelling', shape='parallelogram')
    connect_horizontal(md, ['D1', 'D2', 'D3'])

# Model Refinement Cluster
with flowchart.subgraph(name='cluster_E') as mr:
    mr.attr(label='Model Refinement', style='rounded', color='black')
    mr.attr(rank='same')
    mr.node('E1', 'Hyperparameter Tuning', shape='parallelogram')
    mr.node('E2', 'Feature Importance Analysis', shape='parallelogram')
    connect_horizontal(mr, ['E1', 'E2'])

# Validation and Analysis Cluster
with flowchart.subgraph(name='cluster_F') as va:
    va.attr(label='Validation & Analysis', style='rounded', color='black')
    va.attr(rank='same')
    va.node('F1', 'Cross-validation\n(Accuracy, RMSE, F1-score)', shape='parallelogram')
    va.node('F2', 'Spatial Clustering\n(DBSCAN, K-means)', shape='parallelogram')
    va.node('F3', 'Real-world & Ground Validation', shape='parallelogram')
    connect_horizontal(va, ['F1', 'F2', 'F3'])

# Automation & Scalability Cluster
with flowchart.subgraph(name='cluster_G') as asb:
    asb.attr(label='Automation & Scalability', style='rounded', color='black')
    asb.attr(rank='same')
    asb.node('G1', 'Automated Geospatial Pipeline\n(Scalable Assessments)', shape='parallelogram')
    asb.node('G2', 'Temporal Monitoring\n(Monitor Decarbonization Efforts)', shape='parallelogram')
    asb.node('G3', 'Development of Dashboards/Visualization Tools', shape='parallelogram')
    asb.node('G4', 'BIM/BEM Integration', shape='parallelogram')
    asb.node('G5', 'Policy Integration\n(Urban Planning Recommendations)', shape='parallelogram')
    asb.node('G6', 'Publication & Dissemination', shape='parallelogram')
    connect_horizontal(asb, ['G1', 'G2', 'G3', 'G4', 'G5', 'G6'])

# Connect Clusters (centered vertically)
flowchart.edge('A3', 'B2', constraint='true')  # Connecting cluster centers
flowchart.edge('B2', 'C2', constraint='true')
flowchart.edge('C2', 'D2', constraint='true')
flowchart.edge('D2', 'E1', constraint='true')
flowchart.edge('E2', 'F2', constraint='true')
flowchart.edge('F2', 'G3', constraint='true')

# Render and save the flowchart
output_file = "D:/OneDrive - Ulster University/PhD/Output/final_workflow_flowchart"
flowchart.render(output_file, view=True)

print(f"Flowchart saved to: {output_file}.png")
