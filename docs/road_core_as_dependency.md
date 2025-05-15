---
layout: default
nav_order: 4
---

# Road-core service as a dependency for other projects

It is possible to use road-core service as a dependency for other projects. In order to use it for a new project, the following steps needs to be taken:

## Stub with new project

### create directory for a new project, for example `xyzzy`

```shell
mkdir xyzzy
```

### Create stub for a new project

```shell
pdm init
```

Respond to all questions in following manner:

```
Please enter the Python interpreter to use
 0. cpython@3.12 (/usr/bin/python)
 1. cpython@3.13 (/usr/bin/python3.13)
 2. cpython@3.12 (/usr/bin/python3.12)
 3. cpython@3.11 (/usr/bin/python3.11)
Please select (0): 0
Virtualenv is created successfully at /tmp/ramdisk/xyzzy/.venv
Project name (xyzzy): 
Project version (0.1.0): 
Do you want to build this project for distribution(such as wheel)?
If yes, it will be installed by default when running `pdm install`. [y/n] (n): 
License(SPDX name) (MIT): 
Author name (John Doe): 
Author email (john@doe.com): 
Python requires('*' to allow any) (==3.12.*): >=3.11.1,<=3.12.*
Project is initialized successfully
INFO: PDM 2.22.2 is installed, while 2.24.1 is available.
Please run `pdm self update` to upgrade.
Run `pdm config check_update false` to disable the check.
```

### Check project file

Display project file that was generated:

```shell
$ cat pyproject.toml 
```

Project file should have following format:

```toml
[project]
name = "xyzzy"
version = "0.1.0"
description = "Default template for PDM package"
authors = [
    {name = "John Doe", email = "john@doe.com"},
]
dependencies = []
requires-python = ">=3.11.1,<=3.12.*"
readme = "README.md"
license = {text = "MIT"}


[tool.pdm]
distribution = false

```

## Configure project

Add following three sections into project file:

```toml
[[tool.pdm.source]]
name = "road-core"
url = "https://test.pypi.org/simple"

[[tool.pdm.source]]
type = "find_links"
url = "https://download.pytorch.org/whl/cpu/torch/"
name = "torch"

[tool.pdm.resolution]
respect-source-order = true
# Don't let PDM install all these runtime libraries -- they add GB's of bloat!
excludes = [
  "nvidia-cublas-cu12",
  "nvidia-cuda-cupti-cu12",
  "nvidia-cuda-nvrtc-cu12",
  "nvidia-cuda-runtime-cu12",
  "nvidia-cudnn-cu12",
  "nvidia-cufft-cu12",
  "nvidia-curand-cu12",
  "nvidia-cusolver-cu12",
  "nvidia-cusparse-cu12",
  "nvidia-nccl-cu12",
  "nvidia-nvtx-cu12",
  "triton",
]
```

### Check project file structure

Now the project file should have the following format:

```toml
[[tool.pdm.source]]
name = "road-core"
url = "https://test.pypi.org/simple"

[[tool.pdm.source]]
type = "find_links"
url = "https://download.pytorch.org/whl/cpu/torch/"
name = "torch"

[tool.pdm.resolution]
respect-source-order = true
# Don't let PDM install all these runtime libraries -- they add GB's of bloat!
excludes = [
  "nvidia-cublas-cu12",
  "nvidia-cuda-cupti-cu12",
  "nvidia-cuda-nvrtc-cu12",
  "nvidia-cuda-runtime-cu12",
  "nvidia-cudnn-cu12",
  "nvidia-cufft-cu12",
  "nvidia-curand-cu12",
  "nvidia-cusolver-cu12",
  "nvidia-cusparse-cu12",
  "nvidia-nccl-cu12",
  "nvidia-nvtx-cu12",
  "triton",
]
```

## Add road-core as dependency

Add a new package as a dependency into your project:

```
$ pdm add road-core==0.3.2
```

Progress:

```
Adding packages to default dependencies: road-core==0.3.2
  0:03:36 🔒 Lock successful.  
Changes are written to pyproject.toml.
Synchronizing working set with resolved packages: 171 to add, 0 to update, 0 to remove

  ✔ Install setuptools 80.1.0 successful
  ✔ Install aiolimiter 1.2.1 successful
    ...
    ...
    ...
  ✔ Install regex 2024.11.6 successful
  ✔ Install pydantic-core 2.33.2 successful
  ✔ Install torch 2.7.0+cpu successful

  0:01:53 🎉 All complete! 171/171
```

### Check project file

Now the project file should have the following structure:

```toml
[project]
name = "xyzzy"
version = "0.1.0"
description = "Default template for PDM package"
authors = [
    {name = "John Doe", email = "john@doe.com"},
]
dependencies = ["road-core==0.3.2"]
requires-python = ">=3.11.1,<=3.12.*"
readme = "README.md"
license = {text = "MIT"}

[[tool.pdm.source]]
name = "road-core"
url = "https://test.pypi.org/simple"

[[tool.pdm.source]]
type = "find_links"
url = "https://download.pytorch.org/whl/cpu/torch/"
name = "torch"

[tool.pdm.resolution]
respect-source-order = true
# Don't let PDM install all these runtime libraries -- they add GB's of bloat!
excludes = [
  "nvidia-cublas-cu12",
  "nvidia-cuda-cupti-cu12",
  "nvidia-cuda-nvrtc-cu12",
  "nvidia-cuda-runtime-cu12",
  "nvidia-cudnn-cu12",
  "nvidia-cufft-cu12",
  "nvidia-curand-cu12",
  "nvidia-cusolver-cu12",
  "nvidia-cusparse-cu12",
  "nvidia-nccl-cu12",
  "nvidia-nvtx-cu12",
  "triton",
]

[tool.pdm]
distribution = false
```
