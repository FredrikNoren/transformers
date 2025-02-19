import ast
import os
from collections import defaultdict


FILE_TYPE_PREFIXES = (
    "modular_",
    "modeling_",
    "configuration_",
    "tokenization_",
    "processing_",
    "image_processing_",
    "feature_extractor_",
)


def get_model_name_from_filename(filename: str) -> str:
    """From a filename pointing to a model file of any type, extract the model name."""
    # If it contains the extension, remove it
    modified_filename = filename[:-3] if filename.endswith(".py") else filename
    # If it's a full path, extract last part
    modified_filename = os.path.basename(modified_filename)
    # It may also appear as a pathname, but in Python import form (i.e. with `.` instead of `/` to separate)
    modified_filename = modified_filename.split(".")[-1]

    file_prefix = None
    for prefix in FILE_TYPE_PREFIXES:
        if modified_filename.startswith(prefix):
            file_prefix = prefix
            break

    if file_prefix is None:
        raise ValueError(f"It looks like `{filename}` is not a Transformers model file!")

    model_name = modified_filename.replace(file_prefix, "", 1)
    # This filetype may have the "_fast" suffix as well
    if file_prefix == "image_processing_" and model_name.endswith("_fast"):
        model_name = model_name[:-5]

    return model_name


# Function to perform topological sorting
def topological_sort(dependencies: dict):
    # Nodes are the name of the models to convert (we only add those to the graph)
    nodes = {node.rsplit("modular_", 1)[1].replace(".py", "") for node in dependencies.keys()}
    # This will be a graph from models to convert, to models to convert that should be converted before (as they are a dependency)
    graph = {}
    name_mapping = {}
    for node, deps in dependencies.items():
        node_name = node.rsplit("modular_", 1)[1].replace(".py", "")
        dep_names = {get_model_name_from_filename(dep) for dep in deps}
        dependencies = {dep for dep in dep_names if dep in nodes and dep != node_name}
        graph[node_name] = dependencies
        name_mapping[node_name] = node

    sorting_list = []
    while len(graph) > 0:
        # Find the nodes with 0 out-degree
        leaf_nodes = {node for node in graph if len(graph[node]) == 0}
        # Add them to the list
        sorting_list += list(leaf_nodes)
        # Remove the leafs from the graph (and from the deps of other nodes)
        graph = {node: deps - leaf_nodes for node, deps in graph.items() if node not in leaf_nodes}

    return [name_mapping[x] for x in sorting_list]


# Function to extract class and import info from a file
def extract_classes_and_imports(file_path):
    with open(file_path, "r") as file:
        tree = ast.parse(file.read(), filename=file_path)
    imports = set()

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = node.module if isinstance(node, ast.ImportFrom) else None
            if module and (".modeling_" in module or "transformers.models" in module):
                imports.add(module)
    return imports


# Function to map dependencies between classes
def map_dependencies(py_files):
    dependencies = defaultdict(set)
    # First pass: Extract all classes and map to files
    for file_path in py_files:
        # dependencies[file_path].add(None)
        class_to_file = extract_classes_and_imports(file_path)
        for module in class_to_file:
            dependencies[file_path].add(module)
    return dependencies


def find_priority_list(py_files):
    """
    Given a list of modular files, sorts them by topological order. Modular models that DON'T depend on other modular
    models will be higher in the topological order.

    Args:
        py_files: List of paths to the modular files

    Returns:
        A tuple with the ordered files (list) and their dependencies (dict)
    """
    dependencies = map_dependencies(py_files)
    ordered_files = topological_sort(dependencies)
    return ordered_files, dependencies
