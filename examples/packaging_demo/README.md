# Cullinan Packaging Demo

Example application demonstrating Cullinan DI framework in frozen
(Nuitka/PyInstaller) environments.  The unified scan pipeline automatically
detects the packaging mode and selects the correct strategy chain.

## Structure

```
packaging_demo/
├── __main__.py          # python -m entry point
├── main.py              # @configure(...) + @application entry method
├── services.py          # @service components
├── controllers.py       # @controller components
├── nuitka_args.txt      # Nuitka argument file
├── pyinstaller.spec     # PyInstaller spec template
├── build_nuitka.sh      # Nuitka build helper (Linux/macOS)
└── README.md            # This file
```

## Development Run

```bash
python -m packaging_demo
# or
python main.py
```

`main.py` uses the standard Cullinan entry form: `@configure(...)` attaches the
packaging settings and `@application` marks `main` as the entry method, which the
runner calls directly.

## Build & Run (4 modes)

### Nuitka standalone
```bash
nuitka @nuitka_args.txt
./main.bin
```

### Nuitka onefile
```bash
nuitka --onefile --include-package=myapp --include-package=cullinan main.py
./main.bin
```

### PyInstaller onedir
```bash
pyinstaller --onedir main.py
./dist/main/main
```

### PyInstaller onefile
```bash
pyinstaller --onefile main.py
./dist/main
```

## Configuration

Uses `explicit_modules` (S0 strategy) for reliable onefile discovery,
and `user_packages` (S1 strategy) for filesystem-based discovery.
The pipeline automatically selects strategies based on the detected
packaging environment.
