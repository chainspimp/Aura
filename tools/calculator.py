import ast
import operator

def calculate(expression: str) -> str:
    """Safely evaluate math expressions"""
    try:
        ops = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.Pow: operator.pow,
            ast.USub: operator.neg
        }
        
        def eval_expr(node):
            if isinstance(node, ast.Num):
                return node.n
            elif isinstance(node, ast.BinOp):
                return ops[type(node.op)](eval_expr(node.left), eval_expr(node.right))
            elif isinstance(node, ast.UnaryOp):
                return ops[type(node.op)](eval_expr(node.operand))
            else:
                raise ValueError("Invalid expression")
        
        print(f"🧮 Calculating: {expression}")
        result = eval_expr(ast.parse(expression, mode='eval').body)
        return f"Result: {result}"
    except Exception as e:
        return f"Calculation error: {str(e)}"
