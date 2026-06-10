import ast
import os
from pathlib import Path

def get_complexity(node):
    """Calculate McCabe cyclomatic complexity of an AST node."""
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.IfExp, ast.While, ast.For, ast.AsyncFor, ast.ExceptHandler, ast.With, ast.AsyncWith)):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
    return complexity

def analyze_directory(dir_path):
    results = {
        'total_loc': 0,
        'functions': 0,
        'classes': 0,
        'high_complexity_funcs': [],
        'total_complexity': 0,
        'files': 0
    }
    
    for root, dirs, files in os.walk(dir_path):
        # Skip vendor, cache, and tests
        dirs[:] = [d for d in dirs if d not in ('_vendor', '__pycache__', 'tests', 'legacy_grounding')]
        
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        source = f.read()
                        
                    results['total_loc'] += len(source.splitlines())
                    results['files'] += 1
                    
                    tree = ast.parse(source)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            results['functions'] += 1
                            comp = get_complexity(node)
                            results['total_complexity'] += comp
                            
                            if comp > 10:  # Threshold for "spaghetti"
                                results['high_complexity_funcs'].append({
                                    'name': node.name,
                                    'file': os.path.relpath(filepath, dir_path),
                                    'complexity': comp,
                                    'loc': node.end_lineno - node.lineno
                                })
                        elif isinstance(node, ast.ClassDef):
                            results['classes'] += 1
                except Exception as e:
                    pass
                    
    return results

if __name__ == "__main__":
    core_path = Path("b:/EXO_GANS/maccre_core")
    res = analyze_directory(core_path)
    
    print(f"--- MACCREv2 Spaghetti Analysis ---")
    print(f"Total Python Files: {res['files']}")
    print(f"Total Lines of Code: {res['total_loc']}")
    print(f"Total Classes: {res['classes']}")
    print(f"Total Functions: {res['functions']}")
    print(f"Average Function Complexity: {res['total_complexity'] / max(1, res['functions']):.2f}")
    print(f"Functions with Complexity > 10 (Spaghetti candidates): {len(res['high_complexity_funcs'])}")
    
    print("\nTop 10 Most Spaghettified Functions:")
    sorted_funcs = sorted(res['high_complexity_funcs'], key=lambda x: x['complexity'], reverse=True)
    for f in sorted_funcs[:10]:
        print(f" - {f['file']} :: {f['name']} (Complexity: {f['complexity']}, LOC: {f['loc']})")
