from pathlib import Path


def get_relative_path(*parts: str) -> str:
    """Build a relative path that works on both Windows and Linux."""
    return str(Path(*parts))


def list_files(directory: str) -> list[str]:
    """Return a list of all files at the given path."""
    p = Path(directory)
    pattern = "*"
    return [str(f) for f in p.glob(pattern) if f.is_file()]


def get_filename(filepath: str) -> str:
    """Extract the filename from a full path."""
    p = Path(filepath)
    return p.name


print(get_relative_path("../micropython/libraries"))
print(list_files(get_relative_path("../micropython/libraries")))
for i in list_files(get_relative_path("../micropython/libraries")):
    print(get_filename(i))
