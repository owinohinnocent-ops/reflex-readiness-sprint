import importlib.util

spec = importlib.util.spec_from_file_location("reflex_backend", "main (2).py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

app = module.app
