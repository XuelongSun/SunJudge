"""Generate a route inventory without creating the Flask app or starting workers."""
from pathlib import Path
import ast
import argparse

ROOT = Path(__file__).resolve().parents[2]
PREFIXES = {"auth": "/api/auth", "admin": "/api/admin", "classes": "/api/classes", "assignments": "/api", "markdown_documents": "/api"}


def generate() -> str:
    lines = ["# API 路由索引（自动生成）", "", "由 `backend/scripts/generate_api_reference.py` 静态读取路由生成。完整调用规则和示例见 [API.md](API.md)。", "", "参数是代码中读取的字段，并不表示全部必填；辅助函数中的作业字段见主文档。响应字段包含成功与错误分支，类型见 `backend/app/models.py` 的序列化方法。", ""]
    for module, prefix in PREFIXES.items():
        path = ROOT / "backend" / "app" / "routes" / f"{module}.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        lines += [f"## {module}", "", "| 方法 | 路径 | 角色 | 请求字段 | JSON 顶层字段 | 实现 |", "| --- | --- | --- | --- | --- | --- |"]
        for fn in tree.body:
            if not isinstance(fn, ast.FunctionDef):
                continue
            roles = []
            authenticated = False
            routes = []
            for decorator in fn.decorator_list:
                if isinstance(decorator, ast.Name) and decorator.id == "login_required":
                    authenticated = True
                if isinstance(decorator, ast.Call):
                    if isinstance(decorator.func, ast.Name) and decorator.func.id == "roles_required":
                        roles = [arg.attr.removeprefix("ROLE_").lower() for arg in decorator.args if isinstance(arg, ast.Attribute)]
                    if isinstance(decorator.func, ast.Attribute) and decorator.func.attr in {"get", "post", "patch", "put", "delete"}:
                        routes.append((decorator.func.attr.upper(), ast.literal_eval(decorator.args[0])))
            fields, responses = set(), set()
            for node in ast.walk(fn):
                if not isinstance(node, ast.Call):
                    continue
                if isinstance(node.func, ast.Attribute) and node.func.attr == "get" and node.args and isinstance(node.args[0], ast.Constant):
                    owner = ast.unparse(node.func.value)
                    if owner.endswith("payload") or owner in {"request.args", "request.form", "request.files"}:
                        fields.add(f"{owner}.{node.args[0].value}")
                if isinstance(node.func, ast.Name) and node.func.id == "jsonify" and node.args and isinstance(node.args[0], ast.Dict):
                    responses.update(key.value for key in node.args[0].keys if isinstance(key, ast.Constant) and isinstance(key.value, str))
            for method, route in routes:
                role = ", ".join(roles) or ("登录用户" if authenticated else "公开")
                source = f"[{fn.name}](../backend/app/routes/{module}.py#L{fn.lineno})"
                lines.append(f"| {method} | `{prefix}{route}` | {role} | {'; '.join(sorted(fields)) or '—'} | {', '.join(sorted(responses)) or '文件响应'} | {source} |")
        lines.append("")
    lines += ["## 运维", "", "`GET /api/health`：公开；返回 `200 {\"status\":\"ok\"}`，只检查 HTTP 进程存活，不检查数据库、Docker 或任务队列。", "", "框架自动提供 OPTIONS/HEAD；它们不计入业务路由。", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = ROOT / "docs" / "API_REFERENCE.md"
    result = generate()
    if args.check:
        if not target.exists() or target.read_text(encoding="utf-8") != result:
            raise SystemExit("API_REFERENCE.md is stale; regenerate it.")
        print("API route reference is up to date.")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(result, encoding="utf-8")
        print("Generated docs/API_REFERENCE.md")
