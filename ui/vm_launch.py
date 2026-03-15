# ============================================
# FILE: ui/vm_launch.py
# Standalone entry point for the VM IDE.
# ============================================

import os
import sys
import traceback

# Add AURA root to path
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root not in sys.path:
    sys.path.insert(0, root)

if __name__ == "__main__":
    try:
        from ui.vm_gui import VMGui
        gui = VMGui()
        gui.show()
    except Exception as e:
        print("\n" + "="*55)
        print("VM IDE CRASHED:")
        print("="*55)
        traceback.print_exc()
        print("\n" + "="*55)
        input("\nPress Enter to close...")