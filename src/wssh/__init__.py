"""SSH client for Warpgate bastions.

No ``__version__`` here on purpose. The distribution version comes from git at
build time, and nothing in wssh displays it — ``wssh version`` prints the commit
pip recorded, which is what actually identifies a build. A hardcoded constant
here could only drift out of step with the wheel.
"""
