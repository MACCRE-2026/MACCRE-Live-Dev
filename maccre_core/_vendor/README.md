# Vendor Sovereignty Layer

This directory stores third-party dependencies sourced physically into the MACCREv2 engine. The rule of this directory is that the overarching project should never rely on `pip install <package>` for anything contained here.

## 1. Rule of Excision
Before vendoring a new module here, ask if a stripped down native standard library implementation could fulfill 80% of its role perfectly. See `_net` directory.

## 2. Rule of the Shim
All access to vendored code must come explicitly through `maccre_core._vendor.__init__` rather than direct namespace mapping to prevent naming clashes with standard library files or future environment overrides.
