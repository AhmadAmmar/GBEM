from graphviz import Digraph

# Initialize the flowchart with a title
flowchart = Digraph("Workflow", format="png", node_attr={"shape": "box", "style": "rounded"})
flowchart.attr(nodesep='0.3', ranksep='0.3', rankdir='TB', size='15', dpi='600', label='Proposed Workflow', labelloc='t', fontsize='20', fontcolor='black')

# Data Acquisition
flowchart.node("A", '''<
    <B>Data Acquisition:</B><BR/>
    &#45; Remote Sensing Data: Sentinel&#45;1 SAR, Sentinel&#45;2 MSI, Thermal Imagery, LiDaR<BR/>
    &#45; Aerial &amp; Street-view (Google Maps API)<BR/>
    &#45; EPC Data<BR/>
    &#45; Building Geometries: OSM, OS, Verisk<BR/>
    &#45; Socioeconomic &amp; Demographic Data: Density, Consumption, Usage Patterns<BR/>
    &#45; Climatic Data: ERA5, Met Office
>''', style="filled", color="lightblue", fontsize="12")

# Preprocessing
flowchart.node("B", '''<
    <B>Preprocessing:</B><BR/>
    &#45; CRS Standardization, Resampling, Normalization, Patching<BR/>
    &#45; Noise Reduction: Cloud Masking, SAR Filtering<BR/>
    &#45; EPC Data Cleaning &amp; Harmonization<BR/>
    &#45; Raster to Vector Mapping: Building Footprints Overlay
>''', style="filled", color="lightyellow", fontsize="12")

# Feature Engineering
flowchart.node("C", '''<
    <B>Feature Engineering:</B><BR/>
    &#45; Urban Indices: NDVI, NDBI, UI, IBI<BR/>
    &#45; SAR Features: VV/VH Ratio, Texture Metrics<BR/>
    &#45; LiDAR Features: Heights, Shadow Analysis
>''', style="filled", color="palegreen", fontsize="12")

# Model Development
flowchart.node("D", '''<
    <B>Model Development:</B><BR/>
    &#45; ML Models: Random Forest, XGBoost, Ensemble<BR/>
    &#45; DL Models: CNNs, Transformers<BR/>
    &#45; Explainable AI (XAI): Model Interpretability<BR/>
    &#45; Statistical, Linear, and Physics-based Modelling
>''', style="filled", color="lightcoral", fontsize="12")

# Refinement
flowchart.node("E", '''<
    <B>Refinement:</B><BR/>
    &#45; Hyperparameter Tuning<BR/>
    &#45; Feature Importance Analysis
>''', style="filled", color="lightsalmon", fontsize="12")

# Validation
flowchart.node("F", '''<
    <B>Validation:</B><BR/>
    &#45; Cross-validation: Accuracy, RMSE, F1-score<BR/>
    &#45; Real-world &amp; Ground Validation
>''', style="filled", color="thistle", fontsize="12")

# Analysis
flowchart.node("G", '''<
    <B>Analysis:</B><BR/>
    &#45; Spatial Clustering: DBSCAN, K-means<BR/>
    &#45; Planning Retrofitting Interventions
>''', style="filled", color="khaki", fontsize="12")

# Automation & Scalability
flowchart.node("H", '''<
    <B>Automation &amp; Scalability:</B><BR/>
    &#45; Automated Pipeline: Spatiotemporal Assessments to Monitor Decarbonization Efforts<BR/>
    &#45; Development of Dashboards/Visualization Tools<BR/>
    &#45; BIM/BEM Integration<BR/>
    &#45; Policy Integration &amp; Urban Planning Recommendations<BR/>
    &#45; Publications &amp; Dissemination
>''', style="filled", color="orange", fontsize="12")

# Workflow Connections
flowchart.edge("A", "B")
flowchart.edge("B", "C")
flowchart.edge("C", "D")
flowchart.edge("D", "E", dir='both')  # Bi-directional for Refinement
flowchart.edge("E", "F", dir='both')  # Bi-directional for Validation
flowchart.edge("F", "G")
flowchart.edge("G", "H")

# Render and save the flowchart
output_file = "D:/OneDrive - Ulster University/PhD/Output/workflow_flowchart_bold"
flowchart.render(output_file, view=True)
print(f"Flowchart saved to: {output_file}.png")
