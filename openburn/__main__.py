"""
CLI interface for OpenBurn Core
"""
import sys
import argparse
from .project import Project
from .profile import DeviceProfile
from .gcode import compile_project
from .api import run_server

def main():
    parser = argparse.ArgumentParser(prog="openburn", description="OpenBurn Core Laser CAM Engine")
    subparsers = parser.add_subparsers(dest="command")

    # compile
    compile_parser = subparsers.add_parser("compile", help="Compile .lbrn/.lbrn2/svg to G-code")
    compile_parser.add_argument("input", help="Input project file (.lbrn, .lbrn2, .svg)")
    compile_parser.add_argument("-o", "--output", required=True, help="Output G-code file")
    compile_parser.add_argument("--profile", help="Path to device_profile.json", default=None)

    # serve
    serve_parser = subparsers.add_parser("serve", help="Start REST API and SSE server")
    serve_parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    serve_parser.add_argument("--bind", default="127.0.0.1", help="Address to bind to")

    args = parser.parse_args()

    if args.command == "compile":
        profile = DeviceProfile.load(args.profile) if args.profile else DeviceProfile()
        filepath = args.input
        if filepath.endswith(".lbrn"):
            proj = Project.load_lbrn(filepath)
        elif filepath.endswith(".lbrn2"):
            proj = Project.load_lbrn2(filepath)
        elif filepath.endswith(".svg"):
            from .svg import import_svg
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            w, h, shapes = import_svg(content)
            proj = Project()
            proj.shapes = shapes
        else:
            raise ValueError(f"Unknown file extension for {filepath}")

        gcode_text = compile_project(proj, profile)
        with open(args.output, "w", encoding="utf-8", newline="\n") as f:
            f.write(gcode_text)
        print(f"Compiled {filepath} -> {args.output}")

    elif args.command == "serve":
        run_server(port=args.port, bind=args.bind)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
