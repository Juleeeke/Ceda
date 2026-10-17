"""Private CLI executable used by the native macOS client."""
import sys
from ceda.cli import main

if __name__ == '__main__':
    if len(sys.argv)<2 or sys.argv[1] not in {'native-export','native-mesh','model-mesh','worker','inspect','transient'}:
        raise SystemExit('This executable is the Ceda native analysis engine.')
    raise SystemExit(main())
