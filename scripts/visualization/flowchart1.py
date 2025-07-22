from graphviz import Digraph

# Create a new directed graph
flowchart = Digraph('Proposed Methodology', format='png')
flowchart.attr(rankdir='TB', size='15', dpi='600')

# Adding nodes
flowchart.node('Start', 'Start', shape='circle')
flowchart.node('DA', 'Data Acquisition\n(Sentinel, LiDAR, EPC, etc.)', shape='box')
flowchart.node('DP', 'Data Preprocessing\n(Cleaning, Alignment, Feature Extraction)', shape='box')
flowchart.node('FE', 'Feature Engineering\n(Spectral Indices, Urban Morphology, Socioeconomic Data)', shape='box')
flowchart.node('ML', 'Initial ML Modeling\n(Random Forest, XGBoost)', shape='diamond')
flowchart.node('VAL', 'Validation\n(Accuracy, Feature Importance)', shape='parallelogram')

# Planned Improvements
flowchart.node('ADV', 'Advanced Modeling\n(Deep Learning, Ensemble Methods)', shape='diamond')
flowchart.node('EXP', 'Expand Dataset\n(High-res Imagery, Climatic, Socioeconomic Data)', shape='box')
flowchart.node('FUS', 'Data Fusion\n(Multisource Integration)', shape='box')
flowchart.node('BIMBEM', 'Integration with BIM/BEM Models', shape='box')
flowchart.node('XAI', 'Explainable AI\n(Model Interpretability)', shape='box')

# Outputs
flowchart.node('POL', 'Policy Applications\n(Retrofit Planning, Urban Policy)', shape='box')
flowchart.node('PUB', 'Publications & Dissemination\n(Papers, Conferences)', shape='parallelogram')
flowchart.node('END', 'End', shape='circle')

# Connecting nodes with proper edges (arrows)
flowchart.edges([
    ('Start', 'DA'),
    ('DA', 'DP'),
    ('DP', 'FE'),
    ('FE', 'ML'),
    ('ML', 'VAL'),
    ('VAL', 'ADV'),
    ('ADV', 'EXP'),
    ('ADV', 'FUS'),
    ('FUS', 'BIMBEM'),
    ('BIMBEM', 'XAI'),
    ('XAI', 'POL'),
    ('POL', 'PUB'),
    ('PUB', 'END')
])

# Render and save the flowchart
output_file = "D:/OneDrive - Ulster University/PhD/Output/workflow_flowchart1"
flowchart.render(output_file, view=True)
print(f"Flowchart saved to: {output_file}.png")
